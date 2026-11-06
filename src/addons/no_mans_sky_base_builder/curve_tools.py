"""Object-mode curve editing, parametric guides and persistent viewport controls."""
import json
from types import SimpleNamespace
import bpy
from bpy.app.handlers import persistent
from bpy_extras import view3d_utils as view
from mathutils import Matrix, Vector
from mathutils.geometry import intersect_line_plane
from .curve_shapes import SHAPES, shape_points, resample_offsets

_building = False
_drawing = {}
_anchors = {}


def active_curve(context):
    obj = context.active_object
    if obj is None or not obj.select_get():
        return None
    if obj.type == 'CURVE' and not obj.get('ObjectID'):
        return obj
    name = obj.get('curve_parent')
    parent = context.scene.objects.get(name) if name else obj.parent
    if parent is not None and parent.type == 'CURVE' and not parent.get('ObjectID'):
        return parent
    selected=[o for o in context.selected_objects if o.type=='CURVE' and not o.get('ObjectID')]
    return selected[0] if len(selected)==1 else None


def editable(obj):
    return obj is not None and obj.library is None and obj.data.library is None


def refresh(obj):
    for key in ('val_data', 'total_length'):
        if key in obj:
            del obj[key]
    obj.data.update_tag()
    obj.update_tag(refresh={'DATA'})
    if obj.get('has_linked_objects'):
        from .utils import curve, curve_utils
        count=int(obj.get('objects_count',1))
        # Point insertion is a shape edit, not a request to change copy count.
        if obj.get('bbe_easy_curve') and count>1:
            obj['density_step']=curve_utils.get_total_curve_density(obj,count)/(count-1)
        curve.update_curve_children(obj)
    for window in bpy.context.window_manager.windows:
        for area in window.screen.areas:
            if area.type == 'VIEW_3D':
                area.tag_redraw()


def own_data(obj):
    # A duplicated guide must not reshape its linked original's data.
    if obj.data.users > 1:
        obj.data = obj.data.copy()


def rebuild(obj, reset=False):
    global _building
    if _building or not editable(obj) or obj.bbe_curve.kind == 'FREE':
        return
    _building = True
    try:
        own_data(obj)
        p=obj.bbe_curve
        points,closed=shape_points(p.kind,p.radius,p.width,p.height,p.turns,p.sweep,p.points)
        if len(points)>p.points:p.points=len(points)
        old=json.loads(obj.get('bbe_curve_baseline','[]'))
        old_handles=json.loads(obj.get('bbe_curve_handle_baseline','[]'))
        offsets=[]
        left_offsets=[];right_offsets=[]
        profiles=[]
        if not reset and obj.data.splines and len(old)==len(obj.data.splines[0].bezier_points):
            offsets=[tuple(a-b for a,b in zip(bp.co,co)) for bp,co in zip(obj.data.splines[0].bezier_points,old)]
            profiles=[(bp.radius,bp.tilt) for bp in obj.data.splines[0].bezier_points]
            if len(old_handles)==len(old):
                for bp,co,handles in zip(obj.data.splines[0].bezier_points,old,old_handles):
                    left_offsets.append(tuple(bp.handle_left-bp.co-(Vector(handles[0])-Vector(co))))
                    right_offsets.append(tuple(bp.handle_right-bp.co-(Vector(handles[1])-Vector(co))))
        offsets=resample_offsets(offsets,len(points),closed)
        left_offsets=resample_offsets(left_offsets,len(points),closed)
        right_offsets=resample_offsets(right_offsets,len(points),closed)
        profiles=resample_offsets(profiles,len(points),closed) if profiles else [(.5 if obj.get('is_initialised') else 1,0)]*len(points)
        obj.data.splines.clear()
        spline=obj.data.splines.new('BEZIER');spline.bezier_points.add(len(points)-1)
        spline.use_cyclic_u=closed
        for bp,(co,left,right),offset,profile,lo,ro in zip(spline.bezier_points,points,offsets,profiles,left_offsets,right_offsets):
            bp.handle_left_type=bp.handle_right_type='FREE'
            bp.co=Vector(co)+Vector(offset)
            bp.handle_left=Vector(left)+Vector(offset)+Vector(lo);bp.handle_right=Vector(right)+Vector(offset)+Vector(ro)
            bp.radius,bp.tilt=profile
        obj['bbe_curve_baseline']=json.dumps([p[0] for p in points])
        obj['bbe_curve_handle_baseline']=json.dumps([(p[1],p[2]) for p in points])
        p.selected=min(p.selected,len(points)-1)
        obj['bbe_easy_curve']=True
        refresh(obj)
    finally:
        _building=False


def parameter_changed(self,context):
    if self.id_data.type=='CURVE' and self.id_data.get('bbe_easy_curve'):
        rebuild(self.id_data)


class BBE_PG_curve(bpy.types.PropertyGroup):
    kind: bpy.props.EnumProperty(name='Shape',items=SHAPES,default='FREE',update=parameter_changed)
    radius: bpy.props.FloatProperty(name='Radius',default=4,min=.01,soft_max=30,update=parameter_changed)
    width: bpy.props.FloatProperty(name='Width / end radius',default=2,min=.01,soft_max=40,update=parameter_changed)
    height: bpy.props.FloatProperty(name='Height',default=8,soft_min=-30,soft_max=30,update=parameter_changed)
    turns: bpy.props.FloatProperty(name='Turns',default=2,min=.1,max=12,update=parameter_changed)
    sweep: bpy.props.FloatProperty(name='Arc angle',default=120,min=1,max=359,update=parameter_changed)
    points: bpy.props.IntProperty(name='Control points',default=17,min=4,max=128,update=parameter_changed)
    selected: bpy.props.IntProperty(default=0,min=0,options={'HIDDEN'})
    spline: bpy.props.IntProperty(default=0,min=0,options={'HIDDEN'})
    linked_handles: bpy.props.BoolProperty(name='Linked handles',default=True,
        description='Keep the opposite handle aligned for a smooth tangent; turn off for independent handles and sharp corners')


def parameters(obj):
    kind=obj.bbe_curve.kind
    values=[]
    if kind not in {'LINE','FREE'}:
        values.append(('radius',{'WAVE':'Amplitude','ELLIPSE':'X radius','SPIRAL':'Start radius'}.get(kind,'Radius')))
    if kind in {'ELLIPSE','SPIRAL','LINE','WAVE'}:
        values.append(('width',{'SPIRAL':'End radius','ELLIPSE':'Y radius'}.get(kind,'Width')))
    if kind=='HELIX': values.append(('height','Height'))
    if kind in {'HELIX','SPIRAL','WAVE'}: values.append(('turns','Turns'))
    if kind=='ARC': values.append(('sweep','Arc angle'))
    return values


def new_curve(context,kind):
    data=bpy.data.curves.new('BBE Curve','CURVE');data.dimensions='3D';data.resolution_u=16
    data.bevel_depth=.018;data.bevel_resolution=2
    data.twist_mode='MINIMUM' if kind=='HELIX' else 'Z_UP'
    name=next((label for key,label,_ in SHAPES if key==kind),'Curve')
    obj=bpy.data.objects.new('BBE '+name,data);context.collection.objects.link(obj)
    obj.location=context.scene.cursor.location
    obj.color=(.15,.8,1,1);obj.show_in_front=True;obj.hide_render=True
    obj.bbe_curve.kind=kind
    if kind in {'CIRCLE','ELLIPSE'}:obj.bbe_curve.points=8
    elif kind in {'ARC','HALF'}:obj.bbe_curve.points=5
    elif kind=='LINE':obj.bbe_curve.points=4;obj.bbe_curve.width=8
    elif kind=='WAVE':obj.bbe_curve.width=12
    obj['bbe_easy_curve']=True
    if kind!='FREE':rebuild(obj,reset=True)
    # Keep a selected part as the seed for Duplicate Along Curve.
    seed=next((o for o in context.selected_objects if o.get('ObjectID') or o.get('GroupID')),None)
    for selected in context.selected_objects:selected.select_set(False)
    if seed:seed.select_set(True)
    obj.select_set(True);context.view_layer.objects.active=obj
    context.scene.bbe_curve_helper=True
    for area in context.screen.areas:
        if area.type=='VIEW_3D':area.spaces.active.show_gizmo=True
    context.scene.nms_properties.set_active_obect(obj)
    return obj


class BBE_OT_curve_add(bpy.types.Operator):
    bl_idname='bbe.curve_add';bl_label='Create Editable Curve';bl_options={'REGISTER','UNDO'}
    kind:bpy.props.EnumProperty(items=SHAPES,default='CIRCLE')
    @classmethod
    def poll(cls,context):return context.mode=='OBJECT'
    @classmethod
    def description(cls,context,properties):
        return next((label+' — '+tip for kind,label,tip in SHAPES if kind==properties.kind),'Create curve')
    def execute(self,context):
        new_curve(context,self.kind)
        return {'FINISHED'}


def plane_hit(context,event,origin,normal):
    xy=(event.mouse_region_x,event.mouse_region_y)
    start=view.region_2d_to_origin_3d(context.region,context.region_data,xy)
    direction=view.region_2d_to_vector_3d(context.region,context.region_data,xy)
    return intersect_line_plane(start,start+direction,origin,normal,False)


def control_plane_normal(obj):
    """World normal of a flat guide; None leaves spatial curves unrestricted."""
    if not obj.get('bbe_easy_curve') or obj.bbe_curve.kind=='HELIX':return None
    if obj.bbe_curve.kind!='FREE' or obj.get('bbe_curve_draw_plane'):
        normal=Vector((0,0,1))
    else:
        # Older drawn curves stored their drawing plane in the point coordinates.
        coords=[v.copy() for s in obj.data.splines for p in s.bezier_points
                for v in (p.co,p.handle_left,p.handle_right)]
        if len(coords)<2:return None
        origin=coords[0];axis=max((v-origin for v in coords),key=lambda v:v.length_squared)
        normal=max((axis.cross(v-origin) for v in coords),key=lambda v:v.length_squared)
        if normal.length_squared<1e-12:
            if max(abs(v.z-origin.z) for v in coords)>1e-5:return None
            normal=Vector((0,0,1))
        normal.normalize()
        tolerance=max(1e-5,axis.length*1e-5)
        if any(abs((v-origin).dot(normal))>tolerance for v in coords):return None
    return (obj.matrix_world.to_3x3().inverted_safe().transposed()@normal).normalized()


def control_drag_delta(delta,drag_normal,plane_normal=None,axis=None):
    """Axis shortcuts cannot lift a flat curve out of its own (possibly tilted) plane."""
    delta=delta.copy()
    if axis:
        direction=Vector(tuple(1 if i=='XYZ'.index(axis) else 0 for i in range(3)))
        if plane_normal is not None:direction-=plane_normal*direction.dot(plane_normal)
        projected=direction-drag_normal*direction.dot(drag_normal)
        delta=(direction*(delta.dot(projected)/projected.length_squared)
               if projected.length_squared>1e-6 else Vector((0,0,0)))
    if plane_normal is not None:delta-=plane_normal*delta.dot(plane_normal)
    return delta


def press_position(context,event):
    # Gizmo drag dispatch may start after Blender's movement threshold.
    # Anchor at the original press so short/fast drags do not become no-ops.
    if event.type=='LEFTMOUSE' and event.value=='PRESS':
        return event
    return SimpleNamespace(mouse_region_x=event.mouse_prev_press_x-context.region.x,
                           mouse_region_y=event.mouse_prev_press_y-context.region.y)


def point_record(bp):
    return (tuple(bp.co),tuple(bp.handle_left),tuple(bp.handle_right),bp.handle_left_type,bp.handle_right_type,bp.radius,bp.tilt)


def restore_point(bp,record):
    co,left,right,lt,rt,radius,tilt=record
    bp.handle_left_type=bp.handle_right_type='FREE'
    bp.co=co;bp.handle_left=left;bp.handle_right=right
    bp.handle_left_type=lt;bp.handle_right_type=rt;bp.radius=radius;bp.tilt=tilt


def ensure_handle_baseline(obj):
    """Upgrade an existing preset before its first explicit handle edit."""
    if obj.bbe_curve.kind=='FREE' or obj.get('bbe_curve_handle_baseline'):return
    p=obj.bbe_curve
    points,_=shape_points(p.kind,p.radius,p.width,p.height,p.turns,p.sweep,p.points)
    obj['bbe_curve_handle_baseline']=json.dumps([(r[1],r[2]) for r in points])


def move_control(bp,record,delta,part='POINT',linked=True):
    co,left,right,lt,rt,*_=record
    if part=='POINT':
        bp.co=Vector(co)+delta
        bp.handle_left=Vector(left)+delta;bp.handle_right=Vector(right)+delta
        return
    # Freeze auto handles at their visible positions before a manual adjustment.
    bp.handle_left_type=bp.handle_right_type='FREE'
    bp.co=co;bp.handle_left=left;bp.handle_right=right
    chosen,opposite=('handle_left','handle_right') if part=='LEFT' else ('handle_right','handle_left')
    start=Vector(left if part=='LEFT' else right)
    other=Vector(right if part=='LEFT' else left)
    moved=start+delta
    setattr(bp,chosen,moved)
    direction=moved-Vector(co)
    if linked and direction.length>1e-8:
        setattr(bp,opposite,Vector(co)-direction.normalized()*(other-Vector(co)).length)


class BBE_OT_curve_drag_point(bpy.types.Operator):
    bl_idname='bbe.curve_drag_point';bl_label='Move Curve Point';bl_options={'REGISTER','UNDO','BLOCKING'}
    bl_description='Drag to reshape; X/Y/Z constrain an axis, Shift gives fine control, Esc cancels'
    owner:bpy.props.StringProperty();spline:bpy.props.IntProperty();index:bpy.props.IntProperty()
    part:bpy.props.EnumProperty(items=[('POINT','Point','Move the point'),('LEFT','Incoming handle','Shape the incoming segment'),('RIGHT','Outgoing handle','Shape the outgoing segment')],default='POINT')
    def invoke(self,context,event):
        obj=context.scene.objects.get(self.owner)
        if not editable(obj):return {'CANCELLED'}
        own_data(obj)
        ensure_handle_baseline(obj)
        self.obj=obj;self.records=[point_record(p) for p in obj.data.splines[self.spline].bezier_points]
        obj.bbe_curve.selected=self.index;obj.bbe_curve.spline=self.spline
        self.origin=obj.matrix_world@Vector(self.records[self.index][{'POINT':0,'LEFT':1,'RIGHT':2}[self.part]])
        self.normal=context.region_data.view_rotation@Vector((0,0,1))
        self.flat_normal=control_plane_normal(obj)
        ray=view.region_2d_to_vector_3d(context.region,context.region_data,
                                      (event.mouse_region_x,event.mouse_region_y))
        # Near edge-on views use a projected drag instead of unstable far-away intersections.
        if self.flat_normal is not None and abs(ray.dot(self.flat_normal))>.05:
            self.normal=self.flat_normal
        self.hit=plane_hit(context,press_position(context,event),self.origin,self.normal);self.axis=None
        context.window_manager.modal_handler_add(self)
        context.area.header_text_set('Drag '+('point' if self.part=='POINT' else 'handle')+
            (' | Curve plane locked' if self.flat_normal is not None else ' | 3D movement')+
            ' | X / Y / Z: axis | Shift: fine | Esc: cancel')
        return {'RUNNING_MODAL'}
    def modal(self,context,event):
        try:
            spline=self.obj.data.splines[self.spline]
            bp=spline.bezier_points[self.index]
        except (ReferenceError,IndexError):
            context.area.header_text_set(None);return {'CANCELLED'}
        if event.type in {'ESC','RIGHTMOUSE'}:
            for p,r in zip(spline.bezier_points,self.records):restore_point(p,r)
            refresh(self.obj);context.area.header_text_set(None);return {'CANCELLED'}
        if event.type in {'X','Y','Z'} and event.value=='PRESS':
            self.axis=None if self.axis==event.type else event.type
        if event.type in {'MOUSEMOVE','INBETWEEN_MOUSEMOVE','LEFTMOUSE'}:
            hit=plane_hit(context,event,self.origin,self.normal)
            if hit is not None and self.hit is not None:
                delta=control_drag_delta(hit-self.hit,self.normal,self.flat_normal,self.axis)
                if event.shift:delta*=.1
                local=self.obj.matrix_world.inverted_safe().to_3x3()@delta
                move_control(bp,self.records[self.index],local,self.part,self.obj.bbe_curve.linked_handles)
                refresh(self.obj)
        if event.type=='LEFTMOUSE' and event.value=='RELEASE':
            context.area.header_text_set(None);return {'FINISHED'}
        return {'RUNNING_MODAL'}


def set_free_points(obj,points,closed=False):
    own_data(obj)
    obj.data.splines.clear()
    if not points:return
    spline=obj.data.splines.new('BEZIER');spline.bezier_points.add(len(points)-1)
    spline.use_cyclic_u=closed
    for bp,co in zip(spline.bezier_points,points):
        bp.co=co;bp.handle_left_type=bp.handle_right_type='AUTO'
        bp.radius=.5 if obj.get('is_initialised') else 1
    refresh(obj)


class BBE_OT_curve_draw(bpy.types.Operator):
    bl_idname='bbe.curve_draw';bl_label='Draw Smooth Curve';bl_options={'REGISTER','UNDO'}
    bl_description='Click fit points in the viewport; Enter finishes, Backspace removes a point, Escape cancels'
    plane:bpy.props.EnumProperty(name='Drawing plane',items=[('VIEW','View','Plane facing the view at the 3D cursor'),('XY','Ground XY','Horizontal plane at the 3D cursor'),('XZ','Front XZ','Vertical plane at the 3D cursor'),('YZ','Side YZ','Vertical plane at the 3D cursor')])
    @classmethod
    def poll(cls,context):return context.mode=='OBJECT'
    def invoke(self,context,event):
        if context.area.type!='VIEW_3D':return {'CANCELLED'}
        if context.region.type!='WINDOW':
            region=next(r for r in context.area.regions if r.type=='WINDOW')
            with context.temp_override(region=region):
                result=bpy.ops.bbe.curve_draw('INVOKE_DEFAULT',plane=self.plane)
            # The inner modal operator owns the one completed-curve undo step.
            return {'CANCELLED'} if result=={'RUNNING_MODAL'} else result
        self.old_selection=[o.name for o in context.selected_objects]
        self.old_active=context.active_object.name if context.active_object else ''
        self.obj=new_curve(context,'FREE');self.points=[]
        self.origin=context.scene.cursor.location.copy()
        self.normal=(context.region_data.view_rotation@Vector((0,0,1)) if self.plane=='VIEW' else
                     Vector({'XY':(0,0,1),'XZ':(0,1,0),'YZ':(1,0,0)}[self.plane]))
        self.obj.rotation_mode='QUATERNION'
        self.obj.rotation_quaternion=Vector((0,0,1)).rotation_difference(self.normal)
        self.obj['bbe_curve_draw_plane']=True
        context.view_layer.update()
        context.window.cursor_modal_set('PAINT_BRUSH')
        self.key=context.scene.as_pointer();_drawing[self.key]={'action':'','count':0}
        self.timer=context.window_manager.event_timer_add(.1,window=context.window)
        context.window_manager.modal_handler_add(self)
        context.area.header_text_set('DRAW CURVE: Click to place points | Enter / right-click: finish | Backspace: undo point | Esc: cancel')
        context.workspace.status_text_set('Click in the viewport to start your curve. Enter finishes; Esc cancels.')
        return {'RUNNING_MODAL'}
    def end(self,context,cancel=False):
        _drawing.pop(self.key,None);context.window_manager.event_timer_remove(self.timer)
        context.area.header_text_set(None)
        context.window.cursor_modal_restore()
        context.workspace.status_text_set(None)
        if cancel or len(self.points)<2:
            data=self.obj.data;bpy.data.objects.remove(self.obj,do_unlink=True)
            if data.users==0:bpy.data.curves.remove(data)
            for name in self.old_selection:
                obj=context.scene.objects.get(name)
                if obj:obj.select_set(True)
            context.view_layer.objects.active=context.scene.objects.get(self.old_active)
            return {'CANCELLED'}
        set_free_points(self.obj,self.points)
        return {'FINISHED'}
    def modal(self,context,event):
        state=_drawing.get(self.key)
        if state is None:return self.end(context,True)
        action=state.pop('action','')
        if action=='CANCEL' or event.type=='ESC':return self.end(context,True)
        if action=='FINISH' or (event.type in {'RET','NUMPAD_ENTER','RIGHTMOUSE'} and event.value=='PRESS'):
            if len(self.points)<2:
                self.report({'INFO'},'Place at least two points, or press Escape to cancel.')
                return {'RUNNING_MODAL'}
            return self.end(context)
        if action=='BACK' or (event.type in {'BACK_SPACE','Z'} and event.value=='PRESS' and (event.type=='BACK_SPACE' or event.ctrl)):
            if self.points:self.points.pop()
            set_free_points(self.obj,self.points);state['count']=len(self.points)
        if event.type in {'MIDDLEMOUSE','WHEELUPMOUSE','WHEELDOWNMOUSE','NDOF_MOTION'}:
            return {'PASS_THROUGH'}
        if event.type in {'LEFTMOUSE','MOUSEMOVE'}:
            if in_card(context,event.mouse_region_x,event.mouse_region_y):
                if event.type=='MOUSEMOVE':set_free_points(self.obj,self.points)
                return {'PASS_THROUGH'}
            hit=plane_hit(context,event,self.origin,self.normal)
            if hit is not None:
                local=self.obj.matrix_world.inverted_safe()@hit
                if event.type=='LEFTMOUSE' and event.value=='PRESS':
                    if not self.points or (local-Vector(self.points[-1])).length>1e-5:
                        self.points.append(tuple(local));state['count']=len(self.points)
                preview=event.type=='MOUSEMOVE' and self.points and (local-Vector(self.points[-1])).length>.01
                if self.points:set_free_points(self.obj,self.points+[tuple(local)] if preview else self.points)
        return {'RUNNING_MODAL'}


class BBE_OT_curve_draw_action(bpy.types.Operator):
    """UI requests do not create intermediate undo states during drawing."""
    bl_idname='bbe.curve_draw_action';bl_label='Drawing Controls';bl_options={'INTERNAL'}
    action:bpy.props.StringProperty()
    def execute(self,context):
        state=_drawing.get(context.scene.as_pointer())
        if state is None:return {'CANCELLED'}
        state['action']=self.action
        return {'FINISHED'}


class BBE_OT_curve_action(bpy.types.Operator):
    bl_idname='bbe.curve_action';bl_label='Curve Action';bl_options={'REGISTER','UNDO'}
    action:bpy.props.StringProperty()
    @classmethod
    def description(cls,context,properties):
        return {'RESET':'Restore the preset shape and remove hand adjustments',
                'SMOOTH':'Smooth through the points; converts the preset to a free curve',
                'CLOSED':'Toggle the closing segment; converts the preset to a free curve',
                'ADD':'Insert after the selected diamond point; converts the preset to a free curve',
                'REMOVE':'Remove the selected diamond point; converts the preset to a free curve',
                'LINK':'On: the opposite handle follows to keep a smooth bend. Off: move each handle independently',
                'SELECT':'Select the curve that controls these objects'}.get(properties.action,'Edit curve')
    def execute(self,context):
        obj=active_curve(context)
        if not editable(obj):return {'CANCELLED'}
        p=obj.bbe_curve
        if self.action=='LINK':
            p.linked_handles=not p.linked_handles
            for window in context.window_manager.windows:
                for area in window.screen.areas:
                    if area.type=='VIEW_3D':area.tag_redraw()
            return {'FINISHED'}
        if self.action=='RESET':rebuild(obj,reset=True);return {'FINISHED'}
        if self.action=='SELECT':
            from .curve_studio import select_parent
            select_parent(context,obj);return {'FINISHED'}
        own_data(obj)
        if not obj.data.splines:return {'CANCELLED'}
        s=obj.data.splines[min(p.spline,len(obj.data.splines)-1)]
        if s.type!='BEZIER':
            self.report({'INFO'},'Point editing is available for Bezier curves. Existing duplication controls still work.')
            return {'CANCELLED'}
        if self.action=='CLOSED':
            p.kind='FREE';s.use_cyclic_u=not s.use_cyclic_u
        elif self.action=='SMOOTH':
            p.kind='FREE'
            for bp in s.bezier_points:bp.handle_left_type=bp.handle_right_type='AUTO'
        elif self.action in {'ADD','REMOVE'}:
            index=min(p.selected,len(s.bezier_points)-1)
            records=[point_record(bp) for bp in s.bezier_points]
            if self.action=='REMOVE':
                if len(records)<=2:
                    self.report({'INFO'},'Keep at least two curve points.');return {'CANCELLED'}
                records.pop(index);p.selected=max(0,index-1)
            else:
                a=Vector(records[index][0]);b=Vector(records[(index+1)%len(records)][0])
                co=(a+b)/2 if index+1<len(records) or s.use_cyclic_u else a+(a-Vector(records[index-1][0]))
                if len(records)==1:co=a+Vector((1,0,0))
                records.insert(index+1,(tuple(co),tuple(co),tuple(co),'AUTO','AUTO',records[index][5],0));p.selected=index+1
            closed=s.use_cyclic_u
            obj.data.splines.remove(s);s=obj.data.splines.new('BEZIER');s.bezier_points.add(len(records)-1);s.use_cyclic_u=closed
            for bp,r in zip(s.bezier_points,records):restore_point(bp,r)
            p.spline=len(obj.data.splines)-1;p.kind='FREE'
        refresh(obj);return {'FINISHED'}


class BBE_OT_curve_value(bpy.types.Operator):
    bl_idname='bbe.curve_value';bl_label='Adjust Curve';bl_options={'REGISTER','UNDO','BLOCKING'}
    bl_description='Click the track or drag its thumb; drag the value for smaller adjustments. Shift refines, Escape cancels. Exact fields are in Curve Tools'
    field:bpy.props.StringProperty()
    track_x:bpy.props.FloatProperty(options={'HIDDEN'})
    track_width:bpy.props.FloatProperty(default=0,options={'HIDDEN'})
    def invoke(self,context,event):
        self.obj=active_curve(context)
        if not editable(self.obj):return {'CANCELLED'}
        press=press_position(context,event)
        if self.track_width>0 and press.mouse_region_x>self.track_x+self.track_width-70 and press.mouse_region_y>self.track_y+14:
            bpy.ops.bbe.curve_number('INVOKE_DEFAULT',field=self.field)
            return {'CANCELLED'}
        self.start=value_get(self.obj,self.field);self.mouse=press.mouse_region_x
        self.limits=slider_range(self.obj,self.field)
        self.step=.01 if self.field=='turns' else .5 if self.field=='sweep' else max(.01,abs(self.start)*.005)
        if self.field=='objects_count':self.step=.1
        press=press_position(context,event)
        self.on_track=self.track_width>0 and abs(press.mouse_region_y-self.track_y)<=12*context.preferences.system.ui_scale
        if self.on_track:value_set(self.obj,self.field,self.slider_value(self.mouse))
        context.window_manager.modal_handler_add(self);return {'RUNNING_MODAL'}
    track_y:bpy.props.FloatProperty(options={'HIDDEN'})
    def slider_value(self,x):
        lo,hi=self.limits
        return lo+(hi-lo)*max(0,min(1,(x-self.track_x)/self.track_width))
    def modal(self,context,event):
        if event.type in {'ESC','RIGHTMOUSE'}:
            value_set(self.obj,self.field,self.start);return {'CANCELLED'}
        if event.type in {'MOUSEMOVE','INBETWEEN_MOUSEMOVE','LEFTMOUSE'}:
            value=self.slider_value(event.mouse_region_x) if self.on_track and not event.shift else self.start+(event.mouse_region_x-self.mouse)*self.step*(.1 if event.shift else 1)
            value_set(self.obj,self.field,value)
        if event.type=='LEFTMOUSE' and event.value=='RELEASE':return {'FINISHED'}
        return {'RUNNING_MODAL'}


class BBE_OT_curve_number(bpy.types.Operator):
    bl_idname='bbe.curve_number';bl_label='Exact Curve Value';bl_options={'REGISTER','UNDO'}
    field:bpy.props.StringProperty()
    value:bpy.props.FloatProperty(name='Value',precision=3)
    def invoke(self,context,event):
        obj=active_curve(context)
        if not obj:return {'CANCELLED'}
        self.value=value_get(obj,self.field)
        return context.window_manager.invoke_props_dialog(self,width=280)
    def draw(self,context):
        self.layout.prop(self,'value',text={'objects_count':'Copies','radius_multiplier':'Object size','spacing':'Spacing (m)'}.get(self.field,self.field.replace('_',' ').title()))
    def execute(self,context):
        obj=active_curve(context)
        if not obj:return {'CANCELLED'}
        value_set(obj,self.field,self.value);return {'FINISHED'}


def value_get(obj,field):
    if field=='spacing':
        from .curve_studio import spacing
        return spacing(obj)
    return float(obj.get(field,1)) if field in {'objects_count','radius_multiplier'} else float(getattr(obj.bbe_curve,field))


def value_set(obj,field,value):
    if field=='spacing':
        from .curve_studio import set_spacing
        set_spacing(obj,value);return
    if field in {'objects_count','radius_multiplier'}:
        from .utils import curve
        count=max(1,min(1000,round(value))) if field=='objects_count' else int(obj.get('objects_count',1))
        radius=max(.001,value) if field=='radius_multiplier' else obj.get('radius_multiplier',1)
        if field=='objects_count' and count>1:
            from .utils import curve_utils
            obj['density_step']=curve_utils.get_total_curve_density(obj,count)/(count-1)
        was_parent=obj.get('parent_selected',True)
        obj['parent_selected']=True
        curve.duplicate_along_curve(None,obj,count,radius)
        obj['parent_selected']=was_parent
        # Tool activation can dispatch a depsgraph update. Publish the new
        # slider values first so that update cannot apply the count delta twice.
        bpy.context.scene.nms_properties.show_curve_edit_options(obj)
        if not was_parent:
            children=curve.get_all_curve_children(obj) or []
            for child in children:child.hide_select=False
            if field=='objects_count' or not bpy.context.active_object or bpy.context.active_object==obj:
                from .curve_studio import select_children
                select_children(bpy.context,obj)
        refresh(obj)
    else:setattr(obj.bbe_curve,field,value)


def helper_parameters(obj):
    rows=parameters(obj) if obj and obj.get('bbe_easy_curve') else []
    if obj and obj.get('has_linked_objects'):
        rows+= [('objects_count','Copies'),('radius_multiplier','Object size')]
    return rows


def slider_range(obj,field):
    if field=='spacing':
        from .curve_studio import length
        count=int(obj.get('objects_count',1));divisor=count if obj.data.splines[0].use_cyclic_u else max(1,count-1)
        return 0,max(.001,length(obj)/divisor)
    lo,hi={'radius':(.01,30),'width':(.01,40),'height':(-30,30),'turns':(.1,12),
           'sweep':(1,359),'objects_count':(1,100),'radius_multiplier':(.05,5)}[field]
    value=value_get(obj,field)
    while value>hi:hi*=2
    while value<lo and lo<0:lo*=2
    return min(lo,value),hi


def draw_controls(layout,context):
    from . import icons
    layout.operator_context='INVOKE_REGION_WIN'
    help_row=layout.row(align=True)
    help_row.alignment='RIGHT'
    help_row.operator_context='INVOKE_DEFAULT'
    help_row.operator('bbe.function_help',text='',**icons.ui_icon('QUESTION')).topic='CURVES'
    row=layout.row(align=True)
    row.operator('bbe.curve_draw',text='Draw Smooth Curve',**icons.ui_icon('LINCURVE')).plane=context.scene.bbe_curve_plane
    row.prop(context.scene,'bbe_curve_plane',text='')
    from .curve_icons import icon_id
    grid=layout.row(align=True);grid.scale_y=1.65;grid.scale_x=1.65
    for kind,label,_ in SHAPES:
        if kind!='FREE':grid.operator('bbe.curve_add',text='',icon_value=icon_id(kind,context)).kind=kind
    layout.separator()
    layout.operator('bbe.curve_from_surface',text='Curve from Edges / Faces',**icons.ui_icon('RESTRICT_SELECT_OFF'))
    layout.operator('object.nms_duplicate_along_curve',**icons.ui_icon('MOD_DASH'))
    obj=active_curve(context)
    if obj is None:
        layout.label(text='Select a curve or its linked object to edit.',**icons.ui_icon('INFO'));return
    layout.label(text=obj.name,**icons.ui_icon('MOD_DASH'))
    layout.prop(context.scene,'bbe_curve_helper',text='Viewport controls & drag points')
    layout.prop(obj.bbe_curve,'linked_handles',text='Link tangent handles')
    if obj.get('bbe_easy_curve') and obj.bbe_curve.kind!='FREE':
        for field,label in parameters(obj):layout.prop(obj.bbe_curve,field,text=label)
        layout.prop(obj.bbe_curve,'points')
        layout.operator('bbe.curve_action',text='Reset Shape',**icons.ui_icon('LOOP_BACK')).action='RESET'
    row=layout.row(align=True)
    for label,action in [('Smooth','SMOOTH'),('Open / Close','CLOSED')]:row.operator('bbe.curve_action',text=label,**icons.ui_icon('LINCURVE' if action=='SMOOTH' else 'PARTICLES')).action=action
    row=layout.row(align=True)
    row.operator('bbe.curve_action',text='Insert Point',**icons.ui_icon('ADD')).action='ADD'
    row.operator('bbe.curve_action',text='Remove Point',**icons.ui_icon('REMOVE')).action='REMOVE'
    layout.label(text='Diamonds move points; round tips shape bends.')
    if obj.get('has_linked_objects'):
        props=context.scene.nms_properties
        if context.active_object==obj:
            layout.prop(props,'active_curve_number_of_objects',text='Number of Objects')
            layout.prop(props,'active_curve_radius_multiplier',text='Object Size')
            row=layout.row(align=True)
            row.operator('object.nms_curve_break_apart',text='Unlink Curve',**icons.ui_icon('UNLINKED'))
            row.operator('object.nms_select_children_of_curve',text='Select Children',**icons.ui_icon('MOD_OUTLINE'))
        else:layout.operator('bbe.curve_action',text='Select Parent Curve',**icons.ui_icon('MOD_DASH')).action='SELECT'
        layout.operator('object.nms_duplicate',text='Duplicate',**icons.ui_icon('DUPLICATE'))


def card_rect(context):
    scale=context.preferences.system.ui_scale
    width=312*scale
    from .curve_studio import child_mode
    obj=active_curve(context)
    height=(244 if context.scene.as_pointer() in _drawing else 456 if child_mode(context,obj) else 276+46*len(parameters(obj) if obj and obj.get('bbe_easy_curve') else []))*scale
    x,y=_anchors.get(context.area.as_pointer(),(64*scale,context.region.height-250*scale))
    x=max(8,min(x,context.region.width-width-8));y=max(height+8,min(y,context.region.height-12))
    return x,y-height,width,height


def in_card(context,x,y):
    a,b,w,h=card_rect(context)
    return a<=x<=a+w and b<=y<=b+h


class BBE_OT_curve_move_card(bpy.types.Operator):
    bl_idname='bbe.curve_move_card';bl_label='Move Curve Controls';bl_options={'INTERNAL','BLOCKING'}
    bl_description='Drag this header to move the helper'
    def invoke(self,context,event):
        x,y,w,h=card_rect(context);self.start=(x,y+h)
        press=press_position(context,event);self.mouse=(press.mouse_region_x,press.mouse_region_y)
        context.window_manager.modal_handler_add(self);return {'RUNNING_MODAL'}
    def modal(self,context,event):
        if event.type in {'ESC','RIGHTMOUSE'}:_anchors[context.area.as_pointer()]=self.start;return {'CANCELLED'}
        if event.type in {'MOUSEMOVE','INBETWEEN_MOUSEMOVE','LEFTMOUSE'}:
            _anchors[context.area.as_pointer()]=(self.start[0]+event.mouse_region_x-self.mouse[0],self.start[1]+event.mouse_region_y-self.mouse[1]);context.area.tag_redraw()
        if event.type=='LEFTMOUSE' and event.value=='RELEASE':return {'FINISHED'}
        return {'RUNNING_MODAL'}


class BBE_GGT_curve_controls(bpy.types.GizmoGroup):
    bl_idname='BBE_GGT_curve_controls';bl_label='Curve Tools';bl_space_type='VIEW_3D';bl_region_type='WINDOW'
    bl_options={'PERSISTENT','SHOW_MODAL_ALL'}
    @classmethod
    def poll(cls,context):
        from . import undo_guard
        return not undo_guard.restoring and context.mode=='OBJECT' and context.scene.bbe_curve_helper and editable(active_curve(context))
    def setup(self,context):
        self.card=self.gizmos.new('BBE_GT_curve_widget');self.card.hide_select=True
        self.card.style='CARD'
        self.buttons=[];self.points=[]
    def button(self,index,label,operator,x,y,w,props=None,style='BUTTON',height=28):
        while len(self.buttons)<=index:
            g=self.gizmos.new('BBE_GT_curve_widget');g.use_tooltip=True;self.buttons.append(g)
        g=self.buttons[index];g.hide=False;g.label=label;g.width=w;g.height=height*self.scale
        g.scale=self.scale;g.style=style;g.enabled=False;g.value=''
        g.matrix_basis=Matrix.Translation((x,y,0))
        op=g.target_set_operator(operator)
        for k,v in (props or {}).items():setattr(op,k,v)
        return g
    def draw_prepare(self,context):
        obj=active_curve(context)
        if obj is None:return
        scale=self.scale=context.preferences.system.ui_scale
        for g in self.buttons+self.points:g.hide=True
        x,y,w,h=card_rect(context)
        self.card.matrix_basis=Matrix.Translation((x,y,0))
        self.card.width=w;self.card.height=h;self.card.scale=scale
        state=_drawing.get(context.scene.as_pointer())
        from . import curve_studio,curve_widgets
        curve_widgets.update_theme(context)
        children_screen=curve_studio.child_mode(context,obj)
        header=self.button(0,'DRAW A CURVE' if state else 'CURVE STUDIO · CHILDREN' if children_screen else 'CURVE STUDIO · PARENT','bbe.curve_move_card',
                           x+8*scale,y+h-54*scale,w-16*scale,style='HEADER',height=46)
        header.subtitle='Click points. Watch the curve take shape.' if state else obj.name[:32]
        lines=[(16*scale,14*scale,'Drag points or handles  /  Shift: fine  /  X Y Z: axis',curve_widgets.MUTED)]
        if state is not None:
            lines=[(18*scale,h-81*scale,f'{state["count"]} points placed',curve_widgets.TEXT),
                   (18*scale,15*scale,'Enter: finish  /  Backspace: undo  /  Esc: cancel',curve_widgets.MUTED)]
            for index,(label,action) in enumerate([('Finish Curve','FINISH'),('Undo Last Point','BACK'),('Cancel Drawing','CANCEL')],1):
                self.button(index,label,'bbe.curve_draw_action',x+14*scale,y+h-(90+index*36)*scale,w-28*scale,
                            {'action':action},style='PRIMARY' if index==1 else 'BUTTON',height=29)
        else:
            yy=y+h-104*scale;index=1
            fields=([('objects_count','Copies'),('spacing','Spacing (m)'),('radius_multiplier','Object size')]
                    if children_screen else parameters(obj) if obj.get('bbe_easy_curve') else [])
            for field,label in fields:
                value=value_get(obj,field);lo,hi=slider_range(obj,field)
                g=self.button(index,label,'bbe.curve_value',x+18*scale,yy,w-36*scale,
                    {'field':field,'track_x':x+24*scale,'track_width':w-48*scale,'track_y':yy+10*scale},style='SLIDER',height=44)
                g.value=f'{value:.0f}' if field=='objects_count' else f'{value:.2f}'
                g.fraction=(value-lo)/(hi-lo);index+=1;yy-=46*scale
            def action(label,action,dx,dy,width=138,enabled=False,style='BUTTON',height=28,value=''):
                nonlocal index
                g=self.button(index,label,'bbe.studio_action',x+dx*scale,y+dy*scale,width*scale,{'action':action},style=style,height=height)
                g.enabled=enabled;g.value=value;index+=1
            if children_screen:
                lines=[(16*scale,14*scale,'Drag gizmo  /  G R S, then type a value',curve_widgets.MUTED)]
                action('Fill entire curve','FILL',14,222)
                action('Align curve face','FACE',160,222)
                for n,(label,a) in enumerate([('Move','MOVE'),('Rotate','ROTATE'),('Scale','SCALE')]):
                    action(label,a,14+n*97,184,89,curve_studio.active_native_tool(context)==a)
                local=context.scene.transform_orientation_slots[0].type=='LOCAL'
                action('Axes','AXES',14,148,284,local,style='SWITCH',value='Local' if local else 'Global')
                each=context.scene.tool_settings.transform_pivot_point=='INDIVIDUAL_ORIGINS'
                action('Pivot','PIVOT',14,114,284,each,style='SWITCH',value='Individual' if each else 'Median')
                action('Select All Children','ALL',14,80,284,height=26)
                action('Edit Parent','PARENT',14,32,284,style='NAV',height=36)
            else:
                for n,(label,a) in enumerate([('Smooth curve','SMOOTH'),('Open / Close','CLOSED'),('+  Add point','ADD'),('-  Remove point','REMOVE')]):
                    self.button(index,label,'bbe.curve_action',x+(14+146*(n%2))*scale,y+(168-34*(n//2))*scale,
                                138*scale,{'action':a});index+=1
                g=self.button(index,'Link handles','bbe.curve_action',
                              x+14*scale,y+100*scale,w-28*scale,{'action':'LINK'},style='SWITCH')
                g.enabled=obj.bbe_curve.linked_handles;index+=1
                action('Edit Children' if obj.get('has_linked_objects') else 'Duplicate Along Curve',
                       'CHILDREN' if obj.get('has_linked_objects') else 'DUPLICATE',14,62,284,
                       style='NAV' if obj.get('has_linked_objects') else 'PRIMARY',height=34)
                if obj.get('has_linked_objects'):
                    self.button(index,'Duplicate set','object.nms_duplicate',x+14*scale,y+32*scale,138*scale);index+=1
                    action('Unlink objects','DETACH',160,32)
                else:lines.append((16*scale,40*scale,'Select a part + this curve to create copies.',curve_widgets.MUTED))
                self.draw_points(context,obj)
        self.card.lines=tuple(lines);self.card.children=tuple(self.buttons)
    def marker(self,context,obj,si,pi,part,xy,stem=None):
        i=self.point_count
        while len(self.points)<=i:
            g=self.gizmos.new('BBE_GT_curve_point');g.use_tooltip=True;self.points.append(g)
        g=self.points[i];self.point_count+=1
        g.hide=False;g.scale=self.scale;g.handle=part!='POINT';g.stem=stem
        g.chosen=obj.bbe_curve.selected==pi and obj.bbe_curve.spline==si
        g.matrix_basis=Matrix.Translation((xy.x,xy.y,0))
        op=g.target_set_operator('bbe.curve_drag_point');op.owner=obj.name;op.spline=si;op.index=pi;op.part=part
    def draw_points(self,context,obj):
        self.point_count=0
        def project(co):
            xy=view.location_3d_to_region_2d(context.region,context.region_data,obj.matrix_world@co)
            return xy if xy is not None and 0<xy.x<context.region.width and 0<xy.y<context.region.height and not in_card(context,*xy) else None
        # Handles only for the active point: dense guides remain readable.
        si=min(obj.bbe_curve.spline,max(0,len(obj.data.splines)-1))
        if obj.data.splines:
            spline=obj.data.splines[si]
            if spline.type=='BEZIER':
                pi=min(obj.bbe_curve.selected,len(spline.bezier_points)-1);bp=spline.bezier_points[pi]
                center=project(bp.co)
                if center is not None:
                    for part,co in [('LEFT',bp.handle_left),('RIGHT',bp.handle_right)]:
                        xy=project(co)
                        if xy is not None and (xy-center).length>4*self.scale:
                            self.marker(context,obj,si,pi,part,xy,tuple(center))
        for si,spline in enumerate(obj.data.splines):
            if spline.type!='BEZIER':continue
            for pi,bp in enumerate(spline.bezier_points):
                xy=project(bp.co)
                if xy is not None:self.marker(context,obj,si,pi,'POINT',xy)


@persistent
def reset(*_):
    _anchors.clear();_drawing.clear()
    # Old child-edit mode saved the guide with selection disabled.
    for obj in bpy.data.objects:
        if obj.get('bbe_easy_curve') and obj.get('has_linked_objects') and not obj.library:
            obj.hide_select=False


CLASSES=(BBE_PG_curve,BBE_OT_curve_add,BBE_OT_curve_drag_point,BBE_OT_curve_draw,BBE_OT_curve_draw_action,BBE_OT_curve_action,BBE_OT_curve_value,BBE_OT_curve_number,BBE_OT_curve_move_card,BBE_GGT_curve_controls)
def register():
    from . import curve_widgets,curve_studio,curve_surface
    curve_widgets.register();curve_studio.register()
    curve_surface.register()
    for cls in CLASSES:bpy.utils.register_class(cls)
    bpy.types.Object.bbe_curve=bpy.props.PointerProperty(type=BBE_PG_curve)
    bpy.types.Scene.bbe_curve_helper=bpy.props.BoolProperty(default=True)
    bpy.types.Scene.bbe_curve_plane=bpy.props.EnumProperty(items=[('VIEW','View','Draw in the view plane'),('XY','Ground','Horizontal'),('XZ','Front','Vertical'),('YZ','Side','Vertical')])
    bpy.app.handlers.load_post.append(reset)
    bpy.app.timers.register(reset,first_interval=.1)
def unregister():
    from . import curve_surface
    curve_surface.unregister()
    if bpy.app.timers.is_registered(reset):bpy.app.timers.unregister(reset)
    reset()
    if reset in bpy.app.handlers.load_post:bpy.app.handlers.load_post.remove(reset)
    del bpy.types.Object.bbe_curve;del bpy.types.Scene.bbe_curve_helper;del bpy.types.Scene.bbe_curve_plane
    for cls in reversed(CLASSES):bpy.utils.unregister_class(cls)
    from . import curve_widgets,curve_studio,curve_icons
    curve_studio.unregister();curve_widgets.unregister();curve_icons.unregister()
