"""Curve Studio workflow over BBE's existing followers and Blender transforms."""
import math
import bpy
from mathutils import Vector, Matrix, Quaternion
from .utils import curve, curve_utils

def prepare_frame(obj):
    """Keep planar paths in local XY, so path-up is their face normal."""
    if not obj.get('bbe_easy_curve'):return False
    if obj.bbe_curve.kind!='FREE':
        obj.data.twist_mode='MINIMUM' if obj.bbe_curve.kind=='HELIX' else 'Z_UP'
        return True
    points=[p.co.copy() for s in obj.data.splines for p in s.bezier_points]
    if len(points)<3:return False
    origin=points[0];axis=max((p-origin for p in points),key=lambda v:v.length)
    normal=max((axis.cross(p-origin) for p in points),key=lambda v:v.length)
    if normal.length<1e-7:return False
    normal.normalize()
    extent=max((p-origin).length for p in points)
    if max(abs((p-origin).dot(normal)) for p in points)>max(1e-4,extent*1e-4):
        obj.data.twist_mode='MINIMUM';return False
    component=max(range(3),key=lambda i:abs(normal[i]))
    if normal[component]<0:normal.negate()
    rotation=Vector((0,0,1)).rotation_difference(normal).to_matrix().to_4x4()
    from .curve_tools import own_data
    own_data(obj)
    # Rebase coordinates only. No points or handles move in world space.
    obj.data.transform(rotation.inverted())
    obj.matrix_world=obj.matrix_world@rotation
    obj.data.twist_mode='Z_UP'
    for key in ('val_data','total_length'):
        if key in obj:del obj[key]
    return True

def child_mode(context,obj):return bool(obj and obj.get('has_linked_objects') and context.active_object!=obj)

def choose(context,objects):
    for item in context.selected_objects:item.select_set(False)
    for item in objects:item.hide_select=False;item.select_set(True)
    if objects:context.view_layer.objects.active=objects[0]

def activate_parent(obj):
    children=curve.get_all_curve_children(obj) or []
    for child in children:
        curve.calculate_base_scale(obj,child)
        child.select_set(False);child.hide_select=True
    obj['parent_selected']=True

def select_parent(context,obj):
    activate_parent(obj)
    choose(context,[obj])
    context.scene.nms_properties.set_active_obect(obj)

def select_children(context,obj):
    children=curve.select_children_of_curve(obj) or []
    choose(context,children)
    if children:context.scene.nms_properties.set_active_obect(children[0])
    if children:
        if not obj.get('bbe_studio_defaults_applied'):
            context.scene.transform_orientation_slots[0].type='LOCAL'
            context.scene.tool_settings.transform_pivot_point='INDIVIDUAL_ORIGINS'
            obj['bbe_studio_defaults_applied']=True
        set_native_tool(context,obj,obj.get('bbe_studio_tool','MOVE'))

def set_native_tool(context,obj,kind):
    obj['bbe_studio_tool']=kind
    area=context.area if context.area and context.area.type=='VIEW_3D' else next(
        (a for a in context.screen.areas if a.type=='VIEW_3D'),None)
    if area is None:return
    region=next((r for r in area.regions if r.type=='WINDOW'),None)
    if region is None:return
    space=area.spaces.active
    space.show_gizmo=True;space.show_gizmo_tool=True
    # The active tool supplies the gizmo; don't superimpose the context gizmos.
    space.show_gizmo_object_translate=False;space.show_gizmo_object_rotate=False;space.show_gizmo_object_scale=False
    with context.temp_override(area=area,region=region):
        bpy.ops.wm.tool_set_by_id(name={'MOVE':'builtin.move','ROTATE':'builtin.rotate','SCALE':'builtin.scale'}[kind])

def active_native_tool(context):
    tool=context.workspace.tools.from_space_view3d_mode('OBJECT',create=False)
    return {'builtin.move':'MOVE','builtin.rotate':'ROTATE','builtin.scale':'SCALE'}.get(tool.idname if tool else '')

def length(obj):
    return curve_utils.build_curve_eval_data(obj,32)[1]*obj.matrix_world.to_scale().x

def spacing(obj):
    n=int(obj.get('objects_count',1))
    if n<2:return 0
    interval=n if obj.data.splines[0].use_cyclic_u else n-1
    return min(float(obj.get('bbe_curve_spacing',1e30)),length(obj)/interval)

def set_spacing(obj,value):
    n=int(obj.get('objects_count',1))
    if n<2:return
    interval=n if obj.data.splines[0].use_cyclic_u else n-1
    obj['bbe_curve_spacing']=max(.001,min(value,length(obj)/interval))
    curve.update_curve_children(obj)

def apply_transform(context,kind,value,axis='Z'):
    """Transform evaluated follower poses using the selected axes and center.

    Path constraints offset the object origin; raw transform operators can use
    the offset origin rather than the visible one. Work from evaluated matrices
    and convert back through the existing path frame, keeping the same followers.
    """
    context.view_layer.update()
    objects=[o for o in context.selected_objects if o.get('curve_parent')]
    if not objects:return {'CANCELLED'}
    worlds=[o.matrix_world.copy() for o in objects]
    frames=[w@o.matrix_basis.inverted_safe() for o,w in zip(objects,worlds)]
    local=context.scene.transform_orientation_slots[0].type=='LOCAL'
    each=context.scene.tool_settings.transform_pivot_point=='INDIVIDUAL_ORIGINS'
    center=sum((w.translation for w in worlds),Vector())/len(worlds)
    active=context.active_object.matrix_world.to_quaternion().to_matrix()
    for obj,world,frame in zip(objects,worlds,frames):
        orientation=(world.to_quaternion().to_matrix() if each else active) if local else Matrix.Identity(3)
        if kind=='MOVE':
            desired=world.copy();desired.translation+=orientation@Vector(value)
        else:
            linear=Matrix.Rotation(value,3,axis) if kind=='ROTATE' else Matrix.Diagonal(Vector(value))
            linear=(orientation@linear@orientation.inverted()).to_4x4()
            pivot=world.translation if each else center
            desired=Matrix.Translation(pivot)@linear@Matrix.Translation(-pivot)@world
        obj.matrix_basis=frame.inverted_safe()@desired
    context.view_layer.update()
    for obj in objects:
        parent=context.scene.objects.get(obj.get('curve_parent'))
        if parent:curve.calculate_base_scale(parent,obj)
    return {'FINISHED'}

class BBE_OT_studio_drag(bpy.types.Operator):
    bl_idname='bbe.studio_drag';bl_label='Adjust Curve Objects';bl_options={'REGISTER','UNDO','BLOCKING'}
    bl_description='Drag left/right to adjust this axis. Shift: fine adjustment; Escape: restore'
    axis:bpy.props.EnumProperty(items=[(a,a,a) for a in 'XYZ'],default='X')
    def invoke(self,context,event):
        from .curve_tools import active_curve,press_position
        self.obj=active_curve(context)
        if not child_mode(context,self.obj):return {'CANCELLED'}
        self.kind=self.obj.get('bbe_studio_tool','MOVE')
        self.records=[(o,o.matrix_basis.copy()) for o in context.selected_objects if o.get('curve_parent')==self.obj.name]
        self.start=press_position(context,event).mouse_region_x
        context.window_manager.modal_handler_add(self)
        context.area.header_text_set(self.kind.title()+' '+self.axis+' | Drag left/right | Shift: fine | Esc: cancel')
        return {'RUNNING_MODAL'}
    def restore(self,context):
        for obj,matrix in self.records:obj.matrix_basis=matrix
        context.view_layer.update()
        for obj,_ in self.records:curve.calculate_base_scale(self.obj,obj)
    def modal(self,context,event):
        if event.type in {'ESC','RIGHTMOUSE'}:
            self.restore(context);context.area.header_text_set(None);return {'CANCELLED'}
        if event.type in {'MOUSEMOVE','INBETWEEN_MOUSEMOVE','LEFTMOUSE'}:
            self.restore(context)
            amount=(event.mouse_region_x-self.start)*(.001 if event.shift else .01)
            index='XYZ'.index(self.axis)
            if self.kind=='ROTATE':value=amount
            else:
                value=[1,1,1] if self.kind=='SCALE' else [0,0,0]
                value[index]=max(.001,1+amount) if self.kind=='SCALE' else amount
            apply_transform(context,self.kind,value,self.axis)
        if event.type=='LEFTMOUSE' and event.value=='RELEASE':
            context.area.header_text_set(None);return {'FINISHED'}
        return {'RUNNING_MODAL'}

class BBE_OT_studio_action(bpy.types.Operator):
    bl_idname='bbe.studio_action';bl_label='Curve Studio';bl_options={'REGISTER','UNDO'}
    action:bpy.props.StringProperty()
    @classmethod
    def description(cls,context,props):
        return {'CHILDREN':'Edit all objects on this curve; click one object afterward to adjust it alone',
          'PARENT':'Return to shaping the curve', 'ALL':'Select all objects on this curve',
          'DUPLICATE':'Select a part and its curve, then create linked copies using the existing BBE tool',
          'WORLD':'World axes: use the same scene directions for every object',
          'LOCAL':'Local axes: use the objects own directions',
          'EACH':'Individual origins: rotate or scale every selected object about itself',
          'AXES':'Toggle between Local axes and Global axes',
          'PIVOT':'Toggle between Individual origins and the selection Median point',
          'TOGETHER':'Group center: rotate or scale the selection around its shared center',
          'FILL':'Spread the current number of copies over the whole curve',
          'FACE':'Align an older drawn curve to its plane, keeping its shape and the first object orientation',
          'MOVE':'Use Blender\'s Move gizmo; drag an arrow or press G and type a value',
          'ROTATE':'Use Blender\'s Rotate gizmo; drag a ring or press R and type a value',
          'SCALE':'Use Blender\'s Scale gizmo; drag a handle or press S and type a value',
          'DETACH':'Make these copies independent of their guide, keeping their visible transforms'
        }.get(props.action,'Curve Studio control')
    def execute(self,context):
        from .curve_tools import active_curve,refresh
        obj=active_curve(context)
        if obj is None:
            if self.action=='DUPLICATE':curve.show_duplicate_selection_help(context)
            return {'CANCELLED'}
        a=self.action
        if a=='PARENT':select_parent(context,obj)
        elif a in {'CHILDREN','ALL'}:select_children(context,obj)
        elif a=='DUPLICATE':
            seeds=[o for o in context.selected_objects if o!=obj and (o.get('ObjectID') or o.get('GroupID')) and not o.get('curve_parent')]
            if len(seeds)!=1:
                curve.show_duplicate_selection_help(context)
                return {'CANCELLED'}
            choose(context,[obj,seeds[0]])
            context.scene.nms_build_tool.duplicate_along_curve(10,1)
            select_children(context,context.active_object)
        elif a in {'WORLD','LOCAL'}:context.scene.transform_orientation_slots[0].type='GLOBAL' if a=='WORLD' else 'LOCAL'
        elif a in {'EACH','TOGETHER'}:context.scene.tool_settings.transform_pivot_point='INDIVIDUAL_ORIGINS' if a=='EACH' else 'MEDIAN_POINT'
        elif a=='AXES':context.scene.transform_orientation_slots[0].type='GLOBAL' if context.scene.transform_orientation_slots[0].type=='LOCAL' else 'LOCAL'
        elif a=='PIVOT':context.scene.tool_settings.transform_pivot_point='MEDIAN_POINT' if context.scene.tool_settings.transform_pivot_point=='INDIVIDUAL_ORIGINS' else 'INDIVIDUAL_ORIGINS'
        elif a in {'MOVE','ROTATE','SCALE'}:
            set_native_tool(context,obj,a)
        elif a=='FILL':
            if 'bbe_curve_spacing' in obj:del obj['bbe_curve_spacing']
            refresh(obj)
        elif a=='FACE':
            children=curve.get_all_curve_children(obj) or []
            context.view_layer.update()
            seed=children[0] if children else None
            matrix=seed.matrix_world.copy() if seed else None
            if not prepare_frame(obj):
                self.report({'INFO'},'This curve is not planar; using minimum twist for its 3D bends.')
            if seed:
                probe=bpy.data.objects.new('Curve Studio orientation',None)
                context.collection.objects.link(probe);probe.matrix_world=matrix
                try:
                    alignment=curve.get_source_curve_alignment(obj,probe)
                    curve.set_source_curve_alignment(obj,alignment)
                    for child in children:
                        child.rotation_euler=Quaternion(alignment[0]).to_euler('XYZ')
                finally:bpy.data.objects.remove(probe,do_unlink=True)
            refresh(obj)
        elif a=='DETACH':
            select_parent(context,obj)
            return bpy.ops.object.nms_curve_break_apart()
        context.area.tag_redraw() if context.area else None
        return {'FINISHED'}

class BBE_OT_studio_transform(bpy.types.Operator):
    bl_idname='bbe.studio_transform';bl_label='Adjust Selected Objects';bl_options={'REGISTER','UNDO'}
    kind:bpy.props.EnumProperty(items=[('MOVE','Position','Move the selected objects'),('ROTATE','Rotation','Rotate the selected objects'),('SCALE','Size','Resize the selected objects')])
    move:bpy.props.FloatVectorProperty(name='Move by',subtype='TRANSLATION',unit='LENGTH')
    angle:bpy.props.FloatProperty(name='Rotate by',subtype='ANGLE')
    axis:bpy.props.EnumProperty(name='Axis',items=[(a,a,a) for a in 'XYZ'],default='Z')
    size:bpy.props.FloatVectorProperty(name='Multiply size',default=(1,1,1),min=.001,subtype='XYZ')
    axes:bpy.props.EnumProperty(name='Axes',items=[('GLOBAL','World axes','Same directions for all objects'),('LOCAL','Object axes','The objects own directions')])
    center:bpy.props.EnumProperty(name='Center',items=[('INDIVIDUAL_ORIGINS','Each center','Rotate or scale each object in place'),('MEDIAN_POINT','Group center','Transform around the shared center')])
    def invoke(self,context,event):
        self.axes='LOCAL' if context.scene.transform_orientation_slots[0].type=='LOCAL' else 'GLOBAL'
        self.center='INDIVIDUAL_ORIGINS' if context.scene.tool_settings.transform_pivot_point=='INDIVIDUAL_ORIGINS' else 'MEDIAN_POINT'
        return context.window_manager.invoke_props_dialog(self,width=340)
    def draw(self,context):
        l=self.layout
        l.prop(self,'kind',expand=True)
        l.prop(self,'axes',expand=True)
        l.prop(self,'center',expand=True)
        if self.kind=='MOVE':l.prop(self,'move')
        elif self.kind=='ROTATE':l.prop(self,'axis',expand=True);l.prop(self,'angle')
        else:l.prop(self,'size')
        l.label(text='Applies to the selected curve objects only.',icon='INFO')
    def execute(self,context):
        from .curve_tools import active_curve
        obj=active_curve(context)
        if not child_mode(context,obj):return {'CANCELLED'}
        if self.properties.is_property_set('axes'):context.scene.transform_orientation_slots[0].type=self.axes
        if self.properties.is_property_set('center'):context.scene.tool_settings.transform_pivot_point=self.center
        apply_transform(context,self.kind,self.move if self.kind=='MOVE' else self.angle if self.kind=='ROTATE' else self.size,self.axis)
        context.view_layer.update()
        for child in context.selected_objects:
            if child.get('curve_parent')==obj.name:curve.calculate_base_scale(obj,child)
        return {'FINISHED'}

CLASSES=(BBE_OT_studio_action,BBE_OT_studio_transform,BBE_OT_studio_drag)
def register():
    for cls in CLASSES:bpy.utils.register_class(cls)
def unregister():
    for cls in reversed(CLASSES):bpy.utils.unregister_class(cls)
