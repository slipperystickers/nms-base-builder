"""Reversible proxy display controls and contextual two-part snapping."""
import bpy
import gpu
from bpy.app.handlers import persistent
from bpy_extras.view3d_utils import location_3d_to_region_2d
from mathutils import Matrix, Vector
from . import snap_markers

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
        modifier=obj.modifiers.new(ROOF,'NODES');modifier.node_group=roof_group()
    if modifier is not None:
        modifier.show_viewport=obj.bbe_hide_ceiling
        modifier.show_render=False
        for item in modifier.node_group.interface.items_tree:
            if item.item_type=='SOCKET' and item.in_out=='INPUT' and item.name=='Opening Height':
                modifier[item.identifier]=obj.bbe_ceiling_height
        obj.update_tag()


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


class BBE_OT_part_display(bpy.types.Operator):
    bl_idname='bbe.part_display';bl_label='Part Display';bl_options={'REGISTER','UNDO'}
    bl_description='Open the interior for decorating, or toggle the magnetic beam; game exports retain the complete part'
    def invoke(self,context,event):
        self.object=context.active_object
        return context.window_manager.invoke_popup(self,width=290)
    def draw(self,context):
        obj=self.object
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
        return obj is not None and obj.select_get() and (enclosed(obj) or obj.get('ObjectID') in BEAM_IDS or snap_markers.selected_pair(context) is not None)
    def setup(self,context):
        self.snap=self.gizmos.new('BBE_GT_part_button');self.snap.use_tooltip=True
        self.display=self.gizmos.new('BBE_GT_part_button');self.display.use_tooltip=True
    def draw_prepare(self,context):
        obj=context.active_object;scale=context.preferences.system.ui_scale
        point=location_3d_to_region_2d(context.region,context.region_data,obj.matrix_world.translation)
        self.snap.hide=self.display.hide=True
        if point is None:return
        x=max(10,min(context.region.width-120*scale,point.x+30*scale));y=max(12,min(context.region.height-70*scale,point.y+25*scale))
        if snap_markers.selected_pair(context) and snap_markers.objects(context) is None:
            self.snap.hide=False;self.snap.label='Snap';self.snap.width=70*scale;self.snap.height=25*scale
            self.snap.matrix_basis=Matrix.Translation((x,y,0));self.snap.target_set_operator('bbe.quick_snap');y+=30*scale
        if enclosed(obj) or obj.get('ObjectID') in BEAM_IDS:
            self.display.hide=False;self.display.label='Interior' if enclosed(obj) else 'Beam Options'
            self.display.width=105*scale;self.display.height=25*scale
            self.display.matrix_basis=Matrix.Translation((x,y,0));self.display.target_set_operator('bbe.part_display')


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


CLASSES=(BBE_OT_part_display,BBE_GT_part_button,BBE_GGT_part_controls)
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
