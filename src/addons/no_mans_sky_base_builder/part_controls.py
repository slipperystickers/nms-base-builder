"""Reversible proxy display controls and contextual two-part snapping."""
import bpy
import gpu
from bpy.app.handlers import persistent
from bpy_extras.view3d_utils import location_3d_to_region_2d
from mathutils import Matrix, Vector
from . import cable_connections, door_circuit, snap_markers

ROOF='BBE Interior Cutaway'
BEAM='BBE Magnetic Beam'
BEAM_IDS={'B_MAG_1X1','B_MAG_1X2'}
ROOMS={'MAINROOM','MAINROOMCUBE','MAINROOM_WATER','MAINROOMCUBE_W','BIOROOM',
       'CUBEROOM','CUBEGLASS','CUBEROOM_SPACE','CUBEROOMB_SPACE','CUBEROOMC_SPACE',
       'NPCFRIGTERM','CORRIDOR','CORRIDORC','CORRIDORL','CORRIDORT','CORRIDORX','GLASSCORRIDOR',
       'CORRIDOR_SPACE','CORRIDORL_SPACE','CORRIDORT_SPACE','CORRIDORX_SPACE','CORSTAIRS_SPACE'}
_busy=False


def enclosed(obj):
    if obj is None or obj.type!='MESH':return False
    pid=obj.get('ObjectID','')
    return pid in ROOMS or pid.startswith(('B_COK_','B_HAB','FRE_ROOM_','FRE_CORR_'))


def node_group(name):
    group=bpy.data.node_groups.new(name,'GeometryNodeTree')
    group.interface.new_socket(name='Geometry',in_out='INPUT',socket_type='NodeSocketGeometry')
    group.interface.new_socket(name='Geometry',in_out='OUTPUT',socket_type='NodeSocketGeometry')
    source=group.nodes.new('NodeGroupInput');dest=group.nodes.new('NodeGroupOutput')
    delete=group.nodes.new('GeometryNodeDeleteGeometry');delete.domain='FACE';delete.mode='ALL'
    group.links.new(source.outputs['Geometry'],delete.inputs['Geometry'])
    group.links.new(delete.outputs['Geometry'],dest.inputs['Geometry'])
    return group,source,delete


def roof_group():
    group=bpy.data.node_groups.get(ROOF+' v1')
    if group:return group
    group,source,delete=node_group(ROOF+' v1')
    height=group.interface.new_socket(name='Opening Height',in_out='INPUT',socket_type='NodeSocketFloat')
    height.default_value=.65;height.min_value=.15;height.max_value=.95
    bounds=group.nodes.new('GeometryNodeBoundBox')
    group.links.new(source.outputs['Geometry'],bounds.inputs['Geometry'])
    lower=group.nodes.new('ShaderNodeSeparateXYZ');upper=group.nodes.new('ShaderNodeSeparateXYZ')
    group.links.new(bounds.outputs['Min'],lower.inputs[0]);group.links.new(bounds.outputs['Max'],upper.inputs[0])
    level=group.nodes.new('ShaderNodeMapRange')
    group.links.new(source.outputs['Opening Height'],level.inputs['Value'])
    group.links.new(lower.outputs['Y'],level.inputs['To Min']);group.links.new(upper.outputs['Y'],level.inputs['To Max'])
    position=group.nodes.new('GeometryNodeInputPosition');axis=group.nodes.new('ShaderNodeSeparateXYZ')
    group.links.new(position.outputs[0],axis.inputs[0])
    compare=group.nodes.new('ShaderNodeMath');compare.operation='GREATER_THAN'
    group.links.new(axis.outputs['Y'],compare.inputs[0]);group.links.new(level.outputs['Result'],compare.inputs[1])
    group.links.new(compare.outputs[0],delete.inputs['Selection'])
    clamp=group.nodes.new('ShaderNodeMath');clamp.operation='MINIMUM'
    group.links.new(axis.outputs['Y'],clamp.inputs[0]);group.links.new(level.outputs['Result'],clamp.inputs[1])
    clipped=group.nodes.new('ShaderNodeCombineXYZ')
    group.links.new(axis.outputs['X'],clipped.inputs['X']);group.links.new(axis.outputs['Z'],clipped.inputs['Z'])
    group.links.new(clamp.outputs[0],clipped.inputs['Y'])
    position_node=group.nodes.new('GeometryNodeSetPosition')
    group.links.new(delete.outputs['Geometry'],position_node.inputs['Geometry'])
    group.links.new(clipped.outputs[0],position_node.inputs['Position'])
    destination=next(n for n in group.nodes if n.type=='GROUP_OUTPUT')
    group.links.new(position_node.outputs['Geometry'],destination.inputs['Geometry'])
    return group


def update_roof(obj,context=None):
    if not enclosed(obj):return
    modifier=obj.modifiers.get(ROOF)
    if modifier is None and obj.bbe_hide_ceiling:
        modifier=obj.modifiers.new(ROOF,'NODES')
    if modifier is not None and modifier.node_group is None:
        modifier.node_group=roof_group()
    if modifier is not None:
        modifier.show_viewport=obj.bbe_hide_ceiling
        modifier.show_render=False
        for item in modifier.node_group.interface.items_tree:
            if item.item_type=='SOCKET' and item.in_out=='INPUT' and item.name=='Opening Height':
                interface = getattr(modifier, 'properties', None)
                if hasattr(interface, 'inputs'):
                    # Blender 5.2 stores each socket value inside its input record.
                    interface.inputs[item.identifier]['value'] = obj.bbe_ceiling_height
                else:
                    modifier[item.identifier] = obj.bbe_ceiling_height
        obj.update_tag(refresh={'DATA'})
        if context and context.window_manager:
            for window in context.window_manager.windows:
                for area in window.screen.areas:
                    if area.type == 'VIEW_3D':
                        area.tag_redraw()


def beam_materials(obj):
    return tuple(mat for mat in obj.data.materials if mat and
                 'tractorbeamcone' in (mat.name+' '+mat.get('nms_material_path','')).lower())


def update_beam(obj,context=None):
    if obj.type!='MESH' or obj.get('ObjectID') not in BEAM_IDS:return
    materials=beam_materials(obj)
    if not materials:return
    modifier=obj.modifiers.get(BEAM)
    if modifier is None:
        modifier=obj.modifiers.new(BEAM,'NODES')
    # Bind the actual beam materials, including after switching proxy packs.
    signature='|'.join(mat.name for mat in materials)
    if modifier.node_group is None or modifier.node_group.get('bbe_beam_materials')!=signature:
        group=next((g for g in bpy.data.node_groups if g.get('bbe_beam_materials')==signature),None)
        if group is None:
            group,source,delete=node_group(BEAM)
            previous=None
            for mat in materials:
                selection=group.nodes.new('GeometryNodeMaterialSelection');selection.inputs['Material'].default_value=mat
                output=selection.outputs['Selection']
                if previous is not None:
                    either=group.nodes.new('FunctionNodeBooleanMath');either.operation='OR'
                    group.links.new(previous,either.inputs[0]);group.links.new(output,either.inputs[1]);output=either.outputs[0]
                previous=output
            group.links.new(previous,delete.inputs['Selection']);group['bbe_beam_materials']=signature
        modifier.node_group=group
    enabled=not obj.bbe_show_magnetic_beam
    if modifier.show_viewport!=enabled:modifier.show_viewport=enabled
    if modifier.show_render!=enabled:modifier.show_render=enabled


def display_settings(obj):
    if obj.get('ObjectID') in BEAM_IDS and obj.bbe_show_magnetic_beam:
        return {'bbe_show_magnetic_beam': True}
    if enclosed(obj):
        return {key: getattr(obj, key) for key in ('bbe_hide_ceiling', 'bbe_ceiling_height')
                if obj.is_property_set(key)}
    return {}


def restore_display(obj, entry):
    for key, value in entry.get('display', {}).items():
        if key in ('bbe_hide_ceiling', 'bbe_ceiling_height', 'bbe_show_magnetic_beam'):
            setattr(obj, key, value)


_GROUP_ROOF = 'BBE Group Cutaway'
_ROOF_MODE = 'bbe_group_roof_mode'


def group_roof_modifier(obj):
    if _ROOF_MODE not in obj.data.attributes or obj.modifiers.get(_GROUP_ROOF):
        return
    group = bpy.data.node_groups.get(_GROUP_ROOF)
    if group is None:
        group, _, delete = node_group(_GROUP_ROOF)
        mode = group.nodes.new('GeometryNodeInputNamedAttribute')
        mode.data_type = 'INT'
        mode.inputs['Name'].default_value = _ROOF_MODE
        viewport = group.nodes.new('GeometryNodeIsViewport')
        switch = group.nodes.new('GeometryNodeSwitch')
        switch.input_type = 'INT'
        switch.inputs['True'].default_value = 1   # Full room is render-only.
        switch.inputs['False'].default_value = 2  # Cutaway is viewport-only.
        group.links.new(viewport.outputs[0], switch.inputs['Switch'])
        compare = group.nodes.new('FunctionNodeCompare')
        compare.data_type = 'INT'
        compare.operation = 'EQUAL'
        inputs = [i for i in compare.inputs if i.enabled and i.name in ('A', 'B')]
        group.links.new(mode.outputs['Attribute'], inputs[0])
        group.links.new(switch.outputs[0], inputs[1])
        group.links.new(compare.outputs[0], delete.inputs['Selection'])
    obj.modifiers.new(_GROUP_ROOF, 'NODES').node_group = group


def merge_display_parts(objects):
    """Join each child's display geometry, retaining complete rooms for renders."""
    from .utils import blend_utils
    temporary, meshes, sources = [], [], []

    def scratch(obj):
        part = obj.copy()
        temporary.append(part)
        obj.users_collection[0].objects.link(part)
        if 'ObjectID' in part:
            del part['ObjectID']
        return part

    def mark(mesh, mode):
        from array import array
        attr = mesh.attributes.new(_ROOF_MODE, 'INT', 'FACE')
        attr.data.foreach_set('value', array('i', [mode]) * len(mesh.polygons))

    try:
        for obj in objects:
            is_roof = enclosed(obj) and obj.bbe_hide_ceiling
            is_beam = obj.get('ObjectID') in BEAM_IDS and not obj.bbe_show_magnetic_beam
            if not (is_roof or is_beam):
                sources.append(obj)
                continue
            if is_beam:
                update_beam(obj)
            else:
                update_roof(obj)
            display = scratch(obj)
            for modifier in list(display.modifiers):
                if modifier.name not in (BEAM, ROOF):
                    display.modifiers.remove(modifier)
            graph = bpy.context.evaluated_depsgraph_get()
            evaluated = display.evaluated_get(graph)
            mesh = bpy.data.meshes.new_from_object(evaluated, preserve_all_data_layers=True, depsgraph=graph)
            meshes.append(mesh)
            display.modifiers.clear()
            for key, value in obj.data.items():
                if key not in mesh:
                    mesh[key] = value
            display.data = mesh
            sources.append(display)
            if is_roof:
                mark(mesh, 2)
                full = scratch(obj)
                full.modifiers.clear()
                full.data = obj.data.copy()
                meshes.append(full.data)
                mark(full.data, 1)
                sources.append(full)
        merged = blend_utils.merge_objects(sources, 'Grouped_Objects')
        if merged:
            for name in (ROOF, BEAM):
                modifier = merged.modifiers.get(name)
                if modifier:
                    merged.modifiers.remove(modifier)
            group_roof_modifier(merged)
        return merged
    finally:
        if temporary:
            bpy.data.batch_remove(temporary)
        for mesh in meshes:
            if not mesh.users:
                bpy.data.meshes.remove(mesh)


class BBE_OT_part_display(bpy.types.Operator):
    bl_idname='bbe.part_display';bl_label='Part Display';bl_options={'REGISTER','UNDO'}
    bl_description='Open the interior for decorating, or toggle the magnetic beam; game exports retain the complete part'
    owner: bpy.props.StringProperty(options={'HIDDEN', 'SKIP_SAVE'})
    def invoke(self,context,event):
        self.object = context.scene.objects.get(self.owner) if self.owner else context.active_object
        if self.object is None:
            return {'CANCELLED'}
        return context.window_manager.invoke_popup(self,width=290)
    def draw(self,context):
        obj=self.object
        from .save_editor.function_help import corner_help
        heading = self.layout.row(align=True)
        heading.label(text=obj.name, icon='OBJECT_DATA')
        corner_help(heading, 'PART_DISPLAY')
        if enclosed(obj):
            self.layout.prop(obj,'bbe_hide_ceiling',text='Hide Ceiling / Roof')
            if obj.bbe_hide_ceiling:
                self.layout.prop(obj,'bbe_ceiling_height',text='Opening Height',slider=True)
                self.layout.label(text='Lower for sloped roofs and upper walls.')
            self.layout.label(text='Viewport only; full part stays in exports.',icon='INFO')
        if obj.get('ObjectID') in BEAM_IDS:
            self.layout.prop(obj,'bbe_show_magnetic_beam',text='Show Magnetic Beam')
            self.layout.label(text='Display only; game part stays intact.',icon='INFO')
    def execute(self,context):return {'FINISHED'}


class BBE_GT_part_button(bpy.types.Gizmo):
    bl_idname='BBE_GT_part_button'
    __slots__=('label','width','height')
    def setup(self):self.label='';self.width=90;self.height=24
    def draw(self,context):
        from . import curve_widgets as w
        w.update_theme(context)
        shader=gpu.shader.from_builtin('UNIFORM_COLOR')
        x,y=self.matrix_basis.translation[:2];scale=context.preferences.system.ui_scale
        with w.canvas(context):
            w.rounded(shader,x,y,self.width,self.height,5*scale,(.1,.65,.3,.95) if self.is_highlight else (.035,.12,.09,.95))
            w.text(self.label,x+self.width/2,y+7*scale,11*scale,(.65,1,.8,1),'CENTER')
    def draw_select(self,context,select_id):pass
    def test_select(self,context,location):
        x,y=self.matrix_basis.translation[:2]
        return 0 if x<=location[0]<=x+self.width and y<=location[1]<=y+self.height else -1
    def cursor_get(self):return 'HAND'


class BBE_GGT_part_controls(bpy.types.GizmoGroup):
    bl_idname='BBE_GGT_part_controls';bl_label='Selected Part Controls'
    bl_space_type='VIEW_3D';bl_region_type='WINDOW';bl_options={'PERSISTENT'}
    @classmethod
    def poll(cls,context):
        from . import curve_surface,cable_targets
        if context.mode!='OBJECT' or curve_surface._sessions or cable_targets.session(context):return False
        obj=context.active_object
        return obj is not None and obj.select_get() and (enclosed(obj) or obj.get('ObjectID') in BEAM_IDS or snap_markers.selected_pair(context) is not None
            or bool(cable_connections.local_sockets(obj, cable_connections.BYTEBEAT))
            or bool(cable_connections.local_sockets(obj, cable_connections.POWER)))
    def setup(self,context):
        self.snap=self.gizmos.new('BBE_GT_part_button');self.snap.use_tooltip=True
        self.display=self.gizmos.new('BBE_GT_part_button');self.display.use_tooltip=True
        self.wiring=self.gizmos.new('BBE_GT_part_button');self.wiring.use_tooltip=True
        self.prox=self.gizmos.new('BBE_GT_part_button');self.prox.use_tooltip=True
        self.beat=self.gizmos.new('BBE_GT_part_button');self.beat.use_tooltip=True
    def draw_prepare(self,context):
        obj=context.active_object;scale=context.preferences.system.ui_scale
        point=location_3d_to_region_2d(context.region,context.region_data,obj.matrix_world.translation)
        self.snap.hide=self.display.hide=self.wiring.hide=self.beat.hide=self.prox.hide=True
        if point is None:return
        x=max(10,min(context.region.width-120*scale,point.x+30*scale));y=max(12,min(context.region.height-100*scale,point.y+25*scale))
        if snap_markers.selected_pair(context) and snap_markers.objects(context) is None:
            self.snap.hide=False;self.snap.label='Snap';self.snap.width=70*scale;self.snap.height=25*scale
            self.snap.matrix_basis=Matrix.Translation((x,y,0));self.snap.target_set_operator('bbe.quick_snap');y+=30*scale
        if enclosed(obj) or obj.get('ObjectID') in BEAM_IDS:
            self.display.hide=False;self.display.label='Interior' if enclosed(obj) else 'Beam Options'
            self.display.width=105*scale;self.display.height=25*scale
            self.display.matrix_basis=Matrix.Translation((x,y,0));self.display.target_set_operator('bbe.part_display').owner=obj.name
            y += 30 * scale
        if cable_connections.local_sockets(obj, cable_connections.POWER):
            self.wiring.hide = False
            self.wiring.label = '+Attach Wiring'
            self.wiring.width = 110 * scale
            self.wiring.height = 25 * scale
            self.wiring.matrix_basis = Matrix.Translation((x, y, 0))
            op = self.wiring.target_set_operator('bbe.start_cable_connection')
            op.kind = cable_connections.POWER
            op.source_name = obj.name
            y += 30 * scale
        if obj.get('ObjectID') in door_circuit.DOORS:
            self.prox.hide = False
            self.prox.label = '+Prox Control'
            self.prox.width = 110 * scale
            self.prox.height = 25 * scale
            self.prox.matrix_basis = Matrix.Translation((x, y, 0))
            self.prox.target_set_operator('bbe.add_door_proximity').owner = obj.name
            y += 30 * scale
        if cable_connections.local_sockets(obj, cable_connections.BYTEBEAT):
            self.beat.hide = False
            self.beat.label = '+Attach ByteBeat'
            self.beat.width = 115 * scale
            self.beat.height = 25 * scale
            self.beat.matrix_basis = Matrix.Translation((x,y,0))
            op = self.beat.target_set_operator('bbe.start_cable_connection')
            op.kind = cable_connections.BYTEBEAT
            op.source_name = obj.name


@persistent
def changed(scene,depsgraph):
    global _busy
    if _busy:return
    _busy=True
    try:
        for update in depsgraph.updates:
            obj=update.id.original
            if isinstance(obj,bpy.types.Object) and obj.get('ObjectID') in BEAM_IDS:update_beam(obj)
    finally:_busy=False


@persistent
def loaded(*args):
    for obj in bpy.data.objects:
        if obj.get('ObjectID') in BEAM_IDS:update_beam(obj)
        if enclosed(obj) and obj.bbe_hide_ceiling:update_roof(obj)


CLASSES=(door_circuit.BBE_OT_door_proximity,BBE_OT_part_display,BBE_GT_part_button,BBE_GGT_part_controls)
def register():
    bpy.types.Object.bbe_hide_ceiling=bpy.props.BoolProperty(name='Hide Ceiling',default=False,update=update_roof)
    bpy.types.Object.bbe_ceiling_height=bpy.props.FloatProperty(name='Opening Height',default=.65,min=.15,max=.95,subtype='FACTOR',update=update_roof)
    bpy.types.Object.bbe_show_magnetic_beam=bpy.props.BoolProperty(name='Show Magnetic Beam',default=False,update=update_beam)
    for cls in CLASSES:bpy.utils.register_class(cls)
    bpy.app.handlers.depsgraph_update_post.append(changed);bpy.app.handlers.load_post.append(loaded)
    bpy.app.timers.register(loaded,first_interval=.1)

def unregister():
    if bpy.app.timers.is_registered(loaded):bpy.app.timers.unregister(loaded)
    if changed in bpy.app.handlers.depsgraph_update_post:bpy.app.handlers.depsgraph_update_post.remove(changed)
    if loaded in bpy.app.handlers.load_post:bpy.app.handlers.load_post.remove(loaded)
    for cls in reversed(CLASSES):bpy.utils.unregister_class(cls)
    for prop in ('bbe_hide_ceiling','bbe_ceiling_height','bbe_show_magnetic_beam'):delattr(bpy.types.Object,prop)
