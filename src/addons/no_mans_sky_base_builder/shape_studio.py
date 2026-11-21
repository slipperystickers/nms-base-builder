"""Selection-driven Shape Studio. Idle viewports do no layout or deformation work."""
import math
import time

import bpy
from bpy.props import BoolProperty, EnumProperty, FloatProperty, IntProperty, StringProperty
from bpy_extras.view3d_utils import location_3d_to_region_2d
from mathutils import Matrix, Vector

from . import shape_faces
from . import i18n, curve_tools, curve_widgets as widgets, shape_deform, shape_layout, shapes

_anchors={}
FACE_ROW_HEIGHT=44
LABELS={'width':'Width','depth':'Depth','height':'Height','twist':'Twist','bend':'Bend',
        'pinch':'Pinch','size':'Piece scale','parent_size':'Overall scale',
        'edge_quality':'Edge detail','part_limit':'Part limit'}
for axis in 'xyz':
    LABELS['offset_'+axis]='Move '+axis.upper()
    LABELS['turn_'+axis]='Rotate '+axis.upper()


def get(s,key):
    if key.startswith(('turn_','offset_')):
        field,axis=key.split('_')
        value=getattr(s,field)['xyz'.index(axis)]
    else:
        value=getattr(s,key)
    if key.startswith('turn_') or key in {'twist','bend'}:return math.degrees(value)
    if key=='pinch':return value*100
    return value


def set_value(s,key,value):
    if key.startswith('turn_') or key in {'twist','bend'}:value=math.radians(value)
    if key=='pinch':value/=100
    if key=='part_limit':value=round(value)
    if key.startswith(('turn_','offset_')):
        field,axis=key.split('_')
        getattr(s,field)['xyz'.index(axis)]=value
    else:
        setattr(s,key,value)


def limits(s,key):
    if key=='edge_quality':return 0,100
    if key=='part_limit':return 1,shape_layout.MAX_PARTS
    if key=='bend':return -170,170
    if key=='twist' or key.startswith('turn_'):return -180,180
    if key=='pinch':return -100,90
    if key in {'parent_size','size'}:return .02,max(3,get(s,key)*1.5)
    if key.startswith('offset_'):
        span=max(2,s.width/2,abs(get(s,key))*1.5)
        return -span,span
    return .05,max(24,get(s,key)*1.65)


class Gesture:
    """Keep rest cells and hand edits fixed until release; update existing pieces in place."""
    def __init__(self,root,key):
        self.root=root
        self.key=key
        self.start=get(root.bbe_shape,key)
        self.final_frames=None
        if key in {'parent_size','edge_quality','part_limit'}:return
        import numpy as np
        self.pieces=shapes.shape_parts(root)
        if not self.pieces and root.get('bbe_shape_count')==0:return
        if not self.pieces:raise ValueError('This shape has no pieces.')
        s=root.bbe_shape
        planar='bbe_shape_planar_face' in root
        if planar:
            footprint=root['bbe_shape_planar_size']
            correction=shapes.decode(root['bbe_shape_planar_face'])
        else:footprint,correction=shapes.part_face(self.pieces[0],s.face,with_depth=True)
        self.surface=shape_deform.surface(root,s,footprint,correction,planar=planar)
        self.before=[p.matrix_basis.copy() for p in self.pieces]
        if len(self.surface.points)!=len(self.pieces) or any(shapes.FRAME not in p for p in self.pieces):
            raise ValueError('Pieces or layout changed. Use Layout to refit this shape first.')
        self.deltas=np.array([np.asarray(shapes.decode(p[shapes.FRAME]).inverted_safe() @ old)
                              for p,old in zip(self.pieces,self.before)])
        if np.max(np.abs(self.deltas-np.eye(4)))<1e-6:self.deltas=None

    def preview(self,value):
        set_value(self.root.bbe_shape,self.key,value)
        if self.key in {'parent_size','edge_quality','part_limit'} or not self.pieces:return
        frames=self.surface.matrices(self.root.bbe_shape)
        display=frames if self.deltas is None else frames @ self.deltas
        for piece,matrix in zip(self.pieces,display.tolist()):
            piece.matrix_basis=Matrix(matrix)
        self.final_frames=frames

    def commit(self):
        s=self.root.bbe_shape
        if self.key in {'edge_quality','part_limit'}:
            if get(s,self.key)!=self.start:
                try:shapes.build(bpy.context,owner=self.root,reflow=True)
                except (ValueError,RuntimeError):
                    self.cancel()
                    raise
            return
        refit_size=self.key=='size' and s.fill_gaps and s.fit
        refit_bounds=self.key in {'width','depth','height'} and self.pieces and (self.surface.protected or 'bbe_shape_planar_face' in self.root)
        if (refit_size or refit_bounds) and abs(get(s,self.key)-self.start)>1e-6:
            target=get(s,self.key)
            self.cancel()
            set_value(s,self.key,target)
            try:shapes.build(bpy.context,owner=self.root,reflow=True)
            except (ValueError,RuntimeError):
                set_value(s,self.key,self.start)
                raise
            return
        if self.final_frames is None:return
        for p,flat in zip(self.pieces,self.final_frames.reshape(-1,16).tolist()):
            p[shapes.FRAME]=flat
        self.root['bbe_shape_rest_dims']=self.surface.dims.tolist()

    def cancel(self):
        set_value(self.root.bbe_shape,self.key,self.start)
        if self.key!='parent_size' and self.final_frames is not None:
            for piece,matrix in zip(self.pieces,self.before):piece.matrix_basis=matrix


def valid_root(context):
    from . import undo_guard
    if undo_guard.restoring or context.mode!='OBJECT':return None
    from . import shape_placement
    if shape_placement.busy(context.area):return None
    return shapes.selected_root(context)


def fields(s):
    if s.studio_tab=='HOME':
        return ('size','edge_quality') if s.dimension=='D2' and s.filled_2d and s.fit else ('size',)
    if s.studio_tab=='DEFORM':return ('twist','bend','pinch')
    if s.studio_tab=='PARTS':
        if shapes.native_pieces(bpy.context,s.id_data):return ()
        mode=s.piece_axes
        return ('size',)+tuple(mode+'_'+axis for axis in 'xyz')
    return ('width','depth')+(('height',) if s.dimension=='D3' else ())+('parent_size',)


def rect(context,root):
    s=context.preferences.system.ui_scale
    n=len(fields(root.bbe_shape))
    # Keep the complete editor in smaller viewports by scaling its contents together.
    settings=root.bbe_shape
    tab='SHAPE' if settings.studio_tab=='LAYOUT' else settings.studio_tab
    rows={'HOME':5,'SHAPE':2,'DEFORM':1,'PARTS':3 if shapes.native_pieces(context,root) else 4}[tab]
    if tab=='SHAPE':rows+=len(dimension_options(settings))
    if tab=='HOME' and (settings.dimension=='D2' or settings.shell in shape_layout.FACETED):rows+=1
    height=76+29*rows+43*n+((55-25)+(FACE_ROW_HEIGHT-25) if tab=='HOME' else 0)
    region=context.region
    shelf=next((r for r in context.area.regions if r.type=='TOOLS' and r.width>1),None)
    margin=max(8,(shelf.x+shelf.width-region.x+8) if shelf else 8)
    ceiling=region.height-8
    for other in context.area.regions:
        if other.type in {'HEADER','TOOL_HEADER'} and other.height>1 and other.y>region.y+region.height/2:
            ceiling=min(ceiling,other.y-region.y-6)
    s=max(.25,min(s,(ceiling-6)/height,(region.width-margin-8)/308))
    w,h=308*s,height*s
    x,top=_anchors.get(context.area.as_pointer(),(margin+10*s,ceiling-45*s))
    left=max(margin,min(x,region.width-w-4))
    top=max(h+5,min(top,ceiling))
    return left,top-h,w,h,s


class BBE_OT_shape_card_move(bpy.types.Operator):
    bl_idname='bbe.shape_card_move'
    bl_label='Move Shape Studio'
    bl_options={'INTERNAL','BLOCKING'}
    def invoke(self,context,event):
        root=valid_root(context)
        if not root:return {'CANCELLED'}
        x,y,w,h,s=rect(context,root)
        p=curve_tools.press_position(context,event)
        self.start=(x,y+h);self.press=(p.mouse_region_x,p.mouse_region_y)
        context.window_manager.modal_handler_add(self)
        return {'RUNNING_MODAL'}
    def modal(self,context,event):
        key=context.area.as_pointer()
        if event.type in {'ESC','RIGHTMOUSE'}:
            _anchors[key]=self.start;context.area.tag_redraw();return {'CANCELLED'}
        _anchors[key]=(self.start[0]+event.mouse_region_x-self.press[0],
                       self.start[1]+event.mouse_region_y-self.press[1])
        context.area.tag_redraw()
        return {'FINISHED'} if event.type=='LEFTMOUSE' and event.value=='RELEASE' else {'RUNNING_MODAL'}


class BBE_OT_shape_exact(bpy.types.Operator):
    bl_idname='bbe.shape_exact'
    bl_label='Exact Shape Value'
    bl_options={'UNDO'}
    field:StringProperty()
    value:FloatProperty(name='Value',precision=3)
    limit:IntProperty(name='Part limit',description='Maximum number of game parts for this 2D shape',min=1,max=shape_layout.MAX_PARTS)
    detail:FloatProperty(name='Edge detail',min=0,max=100,subtype='PERCENTAGE',precision=1)
    def value_field(self):
        return {'part_limit':'limit','edge_quality':'detail'}.get(self.field,'value')
    def invoke(self,context,event):
        root=valid_root(context)
        if not root:return {'CANCELLED'}
        setattr(self,self.value_field(),get(root.bbe_shape,self.field))
        return context.window_manager.invoke_props_dialog(self,width=245)
    def draw(self,context):
        self.layout.prop(self,self.value_field(),text=LABELS[self.field])
    def execute(self,context):
        root=valid_root(context)
        if not root:return {'CANCELLED'}
        try:
            edit=Gesture(root,self.field);edit.preview(getattr(self,self.value_field()));edit.commit()
        except (ValueError,RuntimeError) as error:
            self.report({'ERROR'},str(error));return {'CANCELLED'}
        return {'FINISHED'}


class BBE_OT_shape_drag(bpy.types.Operator):
    bl_idname='bbe.shape_drag'
    bl_label='Reshape'
    bl_options={'UNDO','BLOCKING'}
    field:StringProperty()
    track_x:FloatProperty(options={'HIDDEN','SKIP_SAVE'})
    track_y:FloatProperty(options={'HIDDEN','SKIP_SAVE'})
    track_width:FloatProperty(options={'HIDDEN','SKIP_SAVE'})
    grip:BoolProperty(options={'HIDDEN','SKIP_SAVE'})
    @classmethod
    def description(cls,context,props):
        return LABELS.get(props.field,'Shape')+' · Drag to adjust. Shift for fine control. Click the number for exact entry.'
    def invoke(self,context,event):
        root=valid_root(context)
        if not root:return {'CANCELLED'}
        p=curve_tools.press_position(context,event)
        self.press=Vector((p.mouse_region_x,p.mouse_region_y))
        scale=rect(context,root)[4]
        self.exact=(not self.grip and self.press.x>self.track_x+self.track_width-64*scale
                    and self.press.y>self.track_y+12*scale)
        self.timer=None
        if self.exact and event.type=='LEFTMOUSE' and event.value=='RELEASE':
            self.open_number(context,root)
            return {'CANCELLED'}
        self.edit_owner=root
        if not self.exact:
            try:self.edit=Gesture(root,self.field)
            except (ValueError,RuntimeError) as error:
                self.report({'WARNING'},str(error));return {'CANCELLED'}
            self.bounds=limits(root.bbe_shape,self.field)
            self.track=not self.grip and abs(self.press.y-self.track_y)<=12*scale
            self.delta=Vector((1,0))
            self.rate=(self.bounds[1]-self.bounds[0])/max(100,self.track_width or 240*scale)
            if self.grip and self.field in ('width','depth','height'):
                axis=('width','depth','height').index(self.field)
                unit=Vector();unit[axis]=.5
                project=lambda co:location_3d_to_region_2d(context.region,context.space_data.region_3d,root.matrix_world @ co)
                a,b=project(Vector()),project(unit)
                if a is not None and b is not None and (b-a).length>1:
                    self.delta=(b-a).normalized();self.rate=1/(b-a).length
            self.pending=None;self.next_frame=0.
            self.timer=context.window_manager.event_timer_add(.025,window=context.window)
            if self.track:self.queue(event,p.mouse_region_x,p.mouse_region_y)
        context.window_manager.modal_handler_add(self)
        return {'RUNNING_MODAL'}
    def open_number(self,context,owner):
        win,area,region=context.window,context.area,context.region
        field=self.field
        def open_exact():
            if win not in tuple(bpy.context.window_manager.windows) or area not in tuple(win.screen.areas):return
            with bpy.context.temp_override(window=win,area=area,region=region):
                if valid_root(bpy.context)==owner:
                    bpy.ops.bbe.shape_exact('INVOKE_DEFAULT',field=field)
        bpy.app.timers.register(open_exact,first_interval=.01)

    def queue(self,event,x,y):
        lo,hi=self.bounds
        if self.track and not event.shift:
            self.pending=lo+(hi-lo)*max(0,min(1,(x-self.track_x)/self.track_width))
        else:
            dx=(Vector((x,y))-self.press).dot(self.delta)
            self.pending=max(lo,min(hi,self.edit.start+dx*self.rate*(.1 if event.shift else 1)))
    def flush(self,force=False):
        if self.pending is None or (not force and time.perf_counter()<self.next_frame):return
        if abs(get(self.edit.root.bbe_shape,self.field)-self.pending)<1e-6:
            self.pending=None
            return
        start=time.perf_counter()
        self.edit.preview(self.pending);self.pending=None
        self.next_frame=start+max(1/45,(time.perf_counter()-start)*1.8)
    def release(self,context):
        if self.timer:
            context.window_manager.event_timer_remove(self.timer);self.timer=None
        context.area.tag_redraw()
    def cancel(self,context):
        if not self.exact and hasattr(self,'edit'):self.edit.cancel()
        self.release(context)
    def modal(self,context,event):
        if event.type in {'ESC','RIGHTMOUSE'}:
            self.cancel(context);return {'CANCELLED'}
        if not self.exact:
            if event.type in {'MOUSEMOVE','INBETWEEN_MOUSEMOVE','LEFTMOUSE'}:
                self.queue(event,event.mouse_region_x,event.mouse_region_y)
            self.flush()
            if self.field=='edge_quality':context.area.tag_redraw()
        if event.type=='LEFTMOUSE' and event.value=='RELEASE':
            if self.exact:
                self.open_number(context,self.edit_owner)
                self.release(context)
                return {'CANCELLED'}
            else:
                try:
                    self.flush(True);self.edit.commit()
                except (ValueError,RuntimeError) as error:
                    self.release(context);self.report({'WARNING'},str(error));return {'CANCELLED'}
            self.release(context);return {'FINISHED'}
        return {'RUNNING_MODAL'}


class BBE_OT_shape_action(bpy.types.Operator):
    bl_idname='bbe.shape_action'
    bl_label='Shape Studio'
    bl_options={'UNDO'}
    action:StringProperty()
    def execute(self,context):
        root=valid_root(context)
        if not root:return {'CANCELLED'}
        s=root.bbe_shape
        if self.action=='PRESETS':
            bpy.ops.bbe.open_menu('INVOKE_DEFAULT',menu='NEW_SHAPE')
        elif self.action in {'HOME','SHAPE','DEFORM','PARTS','LAYOUT'}:
            was_native=shapes.native_pieces(context,root)
            s.studio_tab='SHAPE' if self.action=='LAYOUT' else self.action
            if was_native or shapes.native_pieces(context,root):shapes.choose(context,[root])
        elif self.action=='NATIVE':
            prefs=context.preferences.addons[__package__].preferences
            prefs.shape_use_blender_tools=not prefs.shape_use_blender_tools
            shapes.choose(context,[root])
            try:
                saved=bpy.ops.wm.save_userpref()
            except RuntimeError:
                saved={'CANCELLED'}
            if 'FINISHED' not in saved:
                self.report({'WARNING'},'Tool choice applied for this session. Blender could not save preferences.')
        elif self.action=='ALL_PARTS':shapes.choose(context,[root])
        elif self.action in {'offset','turn'}:s.piece_axes=self.action
        elif self.action=='DONE':shapes.choose(context,[])
        elif self.action in {'MOVE','ROTATE','SCALE'}:
            shapes.choose(context,[root])
            op={'MOVE':bpy.ops.transform.translate,'ROTATE':bpy.ops.transform.rotate,
                'SCALE':bpy.ops.transform.resize}[self.action]
            op('INVOKE_DEFAULT')
        context.area.tag_redraw()
        return {'FINISHED'}


class BBE_OT_shape_part_id(bpy.types.Operator):
    bl_idname='bbe.shape_part_id'
    bl_label='Choose shape part'
    bl_options={'UNDO'}
    part:StringProperty(name='Object ID',options={'SKIP_SAVE'})
    def invoke(self,context,event):
        root=valid_root(context)
        if not root:return {'CANCELLED'}
        # The update callback ignores the ID already applied to this shape.
        context.window_manager.bbe_shape_part_input=root.bbe_shape.part_id
        x,y,width,height,scale=rect(context,root)
        region=context.region
        right=x+width+8*scale
        picker_width=310*max(.65,context.preferences.system.ui_scale*.88)
        sidebar=next((p for p in context.area.regions if p.type=='UI' and p.width>1),None)
        if right+picker_width>(sidebar.x-region.x if sidebar else region.width) and x>=picker_width:
            right=x-picker_width-8*scale
        bpy.ops.bbe.custom_menu('INVOKE_DEFAULT',menu='PANEL:VIEW3D_PT_bbe_shape_part_picker',
                                anchor_x=round(region.x+right),anchor_y=round(region.y+y+height))
        return {'FINISHED'}
    def execute(self,context):
        root=valid_root(context)
        if not root:return {'CANCELLED'}
        part=self.part if self.properties.is_property_set('part') else context.window_manager.bbe_shape_part_input
        try:shapes.replace_part(context,root,part)
        except (RuntimeError,ValueError) as exc:
            self.report({'WARNING'},str(exc));return {'CANCELLED'}
        return {'FINISHED'}


class VIEW3D_PT_bbe_shape_part_picker(bpy.types.Panel):
    bl_label='Choose shape part'
    bl_space_type='VIEW_3D'
    bl_region_type='WINDOW'
    bl_ui_units_x=19
    def draw(self,context):
        col=self.layout.column(align=True)
        col.prop(context.window_manager,'bbe_shape_part_input',text='Object ID')
        col.separator()
        col.operator_context='INVOKE_DEFAULT'
        col.operator('bbe.shape_dropper',text='Pick in viewport',icon='EYEDROPPER')
        col.operator('bbe.shape_assets',text='Pick in asset browser',icon='EYEDROPPER')


class BBE_OT_shape_layout(bpy.types.Operator):
    bl_idname='bbe.shape_layout'
    bl_label='Piece Layout'
    bl_description='Change the number, fit or facing of pieces'
    bl_options={'UNDO'}
    detail:IntProperty(name='Detail',min=1,max=16)
    sides:IntProperty(name='Sides',min=3,max=128)
    fit:BoolProperty(name='Fitted scaling')
    flat:BoolProperty(name='Lay border flat')
    tube_ratio:FloatProperty(name='Tube radius',min=.05,max=.48)
    pole_taper:FloatProperty(name='Pole taper',min=0,max=1,subtype='FACTOR')
    face:EnumProperty(name='Outside face',items=[(k,k.title(),'') for k in ('AUTO','+X','-X','+Y','-Y','+Z','-Z')])
    def keys(self,s):
        kind=s.outline if s.dimension=='D2' else s.shell
        keys=['detail','fit']
        if s.dimension=='D2' and not s.filled_2d:keys.append('flat')
        if kind in {'POLYGON','PRISM'}:keys.insert(0,'sides')
        if kind=='TORUS':keys.append('tube_ratio')
        if kind in shape_layout.POLAR:keys.append('pole_taper')
        return keys
    def invoke(self,context,event):
        root=valid_root(context)
        if not root:return {'CANCELLED'}
        for k in self.keys(root.bbe_shape):setattr(self,k,getattr(root.bbe_shape,k))
        return context.window_manager.invoke_props_dialog(self,width=280)
    def draw(self,context):
        root=valid_root(context)
        if root:
            for k in self.keys(root.bbe_shape):
                if k!='detail':self.layout.prop(self,k)
    def execute(self,context):
        root=valid_root(context)
        if not root:return {'CANCELLED'}
        s=root.bbe_shape
        original={k:getattr(s,k) for k in self.keys(s)}
        for k in original:
            if self.properties.is_property_set(k):setattr(s,k,getattr(self,k))
        try:shapes.build(context,owner=root,reflow=True)
        except (RuntimeError,ValueError) as exc:
            for k,v in original.items():setattr(s,k,v)
            self.report({'ERROR'},str(exc));return {'CANCELLED'}
        return {'FINISHED'}


LAYOUT_LABELS={'sides':'Sides','detail':'Detail','flat':'Flat border','fit':'Fitted scaling',
               'face':'Outside face','tube_ratio':'Tube radius','pole_taper':'Pole taper'}


def layout_rows(s):
    kind=s.outline if s.dimension=='D2' else s.shell
    keys=['detail','fit','face']
    if s.dimension=='D2' and not s.filled_2d:keys.append('flat')
    if kind in {'POLYGON','PRISM'}:keys.insert(0,'sides')
    if kind=='TORUS':keys.append('tube_ratio')
    if s.fit and kind in shape_layout.POLAR:keys.append('pole_taper')
    return keys


def needs_first_fill(root):
    # A saved pre-fill shape may already have its individual pieces shrunk.
    s=root.bbe_shape
    return s.fill_gaps and s.fit and 'bbe_shape_fill_scale' not in root and abs(s.size-1)>.00001


def dimension_options(s):
    return [key for key in layout_rows(s) if key not in {'detail','face'} and not (key=='fit' and s.fill_gaps and s.fit)]


class BBE_OT_shape_option(bpy.types.Operator):
    bl_idname='bbe.shape_option'
    bl_label='Change Piece Layout'
    bl_options={'UNDO'}
    field:StringProperty()
    step:IntProperty(options={'SKIP_SAVE'})
    @classmethod
    def description(cls,context,props):
        if props.field=='face':return 'Previous outside face' if props.step<0 else 'Next outside face'
        if props.field=='filled_2d':return 'Build the perimeter or cover the whole plane with the selected part'
        if props.field=='preserve_edges':return 'Fit parts inside the shell edges. Switch off for the overlapping layout'
        if props.field=='fill_gaps':return 'Refill the surface when piece scale changes. Switch off to resize the existing pieces and leave space between them'
        return cls.bl_label
    def invoke(self,context,event):
        root=valid_root(context)
        if not root:return {'CANCELLED'}
        if self.field=='face' and self.step==0:
            bpy.ops.bbe.shape_faces('INVOKE_DEFAULT',part_face=True)
            return {'FINISHED'}
        if self.step==0:
            bpy.ops.bbe.shape_layout('INVOKE_DEFAULT')
            return {'FINISHED'}
        return self.execute(context)
    def execute(self,context):
        root=valid_root(context)
        if not root:return {'CANCELLED'}
        s=root.bbe_shape;k=self.field
        if k in {'filled_2d','preserve_edges'}:
            if k=='filled_2d' and s.dimension!='D2' or k=='preserve_edges' and (s.dimension!='D3' or s.shell not in shape_layout.FACETED):
                return {'CANCELLED'}
            old,old_fit=getattr(s,k),s.fit
            value=self.step>0 if k=='filled_2d' else not (old and s.fit)
            if k=='preserve_edges' and value:s.fit=True
            if value==old and s.fit==old_fit:return {'FINISHED'}
            setattr(s,k,value)
            try:shapes.build(context,owner=root,reflow=True)
            except (ValueError,RuntimeError) as error:
                setattr(s,k,old);s.fit=old_fit
                self.report({'WARNING'},str(error));return {'CANCELLED'}
            return {'FINISHED'}
        if k=='fill_gaps':
            old_fill,old_fit=s.fill_gaps,s.fit
            s.fill_gaps=needs_first_fill(root) or not (old_fill and old_fit)
            if s.fill_gaps:s.fit=True
            try:shapes.build(context,owner=root,reflow=True)
            except (ValueError,RuntimeError) as error:
                s.fill_gaps,s.fit=old_fill,old_fit
                self.report({'WARNING'},str(error));return {'CANCELLED'}
            return {'FINISHED'}
        if k not in layout_rows(s):return {'CANCELLED'}
        old=getattr(s,k)
        if k=='face':
            index=shapes.PART_FACES.index(shapes.resolved_part_face(root))
            face=shapes.PART_FACES[(index+self.step)%6]
            try:shapes.apply_part_face(context,root,face)
            except (ValueError,RuntimeError) as exc:
                self.report({'WARNING'},str(exc));return {'CANCELLED'}
            return {'FINISHED'}
        elif k in {'flat','fit'}:value=not old
        else:value=old+self.step*(1 if k in {'sides','detail'} else .05)
        setattr(s,k,value)
        if getattr(s,k)==old:return {'FINISHED'}
        try:shapes.build(context,owner=root,reflow=k in {'detail','fit'})
        except (ValueError,RuntimeError) as error:
            setattr(s,k,old);self.report({'WARNING'},str(error));return {'CANCELLED'}
        return {'FINISHED'}


class BBE_GT_shape_grip(bpy.types.Gizmo):
    bl_idname='BBE_GT_shape_grip'
    __slots__=('label','scale','shader')
    def setup(self):
        import gpu
        self.shader=gpu.shader.from_builtin('UNIFORM_COLOR')
        self.scale=1.;self.label=''
    def draw(self,context):
        x,y=self.matrix_basis.translation[:2];s=self.scale
        color=widgets.TEXT if self.is_highlight or self.is_modal else widgets.CYAN
        with widgets.canvas(context):
            widgets.disc(self.shader,x,y,8*s,widgets.INK)
            widgets.disc(self.shader,x,y,6*s,color)
            widgets.disc(self.shader,x,y,3*s,widgets.HEADER)
            import blf
            blf.size(0,11*s)
            width=blf.dimensions(0,self.label)[0]+10*s
            widgets.rounded(self.shader,x+9*s,y-9*s,width,18*s,5*s,widgets.INK)
            widgets.text(i18n.interface(self.label),x+14*s,y-4*s,11*s,widgets.TEXT)
    def draw_select(self,context,select_id):pass
    def test_select(self,context,location):
        return 0 if (Vector(location)-self.matrix_basis.translation.xy).length<11*self.scale else -1


class BBE_GGT_shape_studio(bpy.types.GizmoGroup):
    bl_idname='BBE_GGT_shape_studio'
    bl_label='Shape Studio'
    bl_space_type='VIEW_3D'
    bl_region_type='WINDOW'
    bl_options={'PERSISTENT','SHOW_MODAL_ALL'}
    # Share the widget pool and binding logic with Curve Studio.
    button=curve_tools.BBE_GGT_curve_controls.button
    @classmethod
    def poll(cls,context):
        return valid_root(context) is not None
    def setup(self,context):
        self.card=self.gizmos.new('BBE_GT_curve_widget')
        self.card.style='STUDIO_CARD';self.card.hide_select=True
        self.buttons=[];self.button_ops={};self.grips=[]
        for _ in range(3):
            g=self.gizmos.new('BBE_GT_shape_grip')
            op=g.target_set_operator('bbe.shape_drag');op.grip=True
            self.grips.append((g,op))
    def draw_prepare(self,context):
        root=valid_root(context)
        if not root:return
        s=root.bbe_shape
        widgets.update_theme(context)
        x,y,w,h,scale=rect(context,root);self.scale=scale
        self.used_buttons=set()
        self.card.matrix_basis=Matrix.Translation((x,y,0))
        self.card.width=w;self.card.height=h;self.card.scale=scale
        idx=0;top=y+h-8*scale
        def row(items,height=25,widths=None):
            nonlocal idx,top
            top-=height*scale
            gap=4*scale;left=x+10*scale;size=(w-20*scale-gap*(len(items)-1))/len(items)
            result=[]
            for i,(label,op,props,style) in enumerate(items):
                cell=widths[i]*scale if widths else size
                g=self.button(idx,label,op,left,top,cell,props,style=style,height=height)
                result.append(g);idx+=1;left+=cell+gap
            top-=4*scale
            return result
        def action(label,key,selected=False):
            return label,'bbe.shape_action',{'action':key},'STUDIO_ACTIVE' if selected or key=='DONE' else 'STUDIO_LINK'
        tab='SHAPE' if s.studio_tab=='LAYOUT' else s.studio_tab
        native=shapes.native_pieces(context,root)
        header=row([('SHAPE STUDIO','bbe.shape_card_move',{},'SHAPE_HEADER')],39)[0]
        title=shape_layout.LABELS.get(root.get('bbe_shape_kind'),root.name)
        page={'HOME':'','SHAPE':'Dimensions','DEFORM':'Deform','PARTS':'Pieces','LAYOUT':'Dimensions'}[tab]
        header.subtitle=' · '.join(filter(None,(i18n.interface(page), i18n.interface(title), i18n.interface("{count} parts").format(count=root.get("bbe_shape_count", 0)))))
        if tab=='HOME':
            part=(s.part_id,'bbe.shape_part_id',{},'STUDIO_PART')
            thumb=(s.part_id,'bbe.shape_part_id',{},'ASSET_PREVIEW')
            if s.dimension=='D3':
                tile=row([thumb,part,('Populate shell faces','bbe.shape_faces',{'part_face':False},'FACE_PREVIEW')],55,(55,107,118))[2]
                tile.subtitle=s.shell
            else:row([thumb,part],55,(55,229))
            previous,picker,following=row([
                ('Previous outside face','bbe.shape_option',{'field':'face','step':-1},'FACE_STEP'),
                ('Pick outside face','bbe.shape_faces',{'part_face':True},'PART_FACE'),
                ('Next outside face','bbe.shape_option',{'field':'face','step':1},'FACE_STEP'),
            ],FACE_ROW_HEIGHT,(48,184,48))
            previous.value='LEFT'
            following.value='RIGHT'
            picker.value=i18n.interface('Part orientation')+'   '+shapes.resolved_part_face(root)
            if s.dimension=='D2':
                mode=[(label,'bbe.shape_option',{'field':'filled_2d','step':step},
                      'STUDIO_ACTIVE' if s.filled_2d==(step>0) else 'STUDIO_LINK')
                     for label,step in (('Outline',-1),('Fill',1))]
                row([*mode,(i18n.interface('Part limit')+f'   {s.part_limit}','bbe.shape_exact',{'field':'part_limit'},'PRIMARY')],widths=(80,75,125))
            elif s.shell in shape_layout.FACETED:
                switch=row([('Preserve edges','bbe.shape_option',{'field':'preserve_edges','step':1},'SWITCH')])[0]
                switch.enabled=s.preserve_edges and s.fit
                switch.value='On' if switch.enabled else 'Off'
        if tab=='PARTS':
            switch=row([('Use Blender Tools','bbe.shape_action',{'action':'NATIVE'},'SWITCH')])[0]
            switch.enabled=native;switch.value='On' if native else 'Off'
            if native:row([action('Select all pieces','ALL_PARTS')])
            else:row([action('Move pieces','offset',s.piece_axes=='offset'),action('Rotate pieces','turn',s.piece_axes=='turn')])
        for field in fields(s):
            value=get(s,field);lo,hi=limits(s,field)
            top-=40*scale;left=x+12*scale;ww=w-24*scale
            g=self.button(idx,LABELS[field],'bbe.shape_drag',left,top,ww,
                {'field':field,'track_x':left+6*scale,'track_width':ww-12*scale,'track_y':top+10*scale,'grip':False},
                style='SLIDER',height=40)
            # Gizmos otherwise inherit the last invocation's unset default after a grip drag.
            self.button_ops[idx][1].grip=False
            g.value=(f'{value:.1f}°' if field in {'twist','bend'} or field.startswith('turn_')
                     else f'{value:.0f}%' if field=='pinch' else f'{value:.1f}%' if field=='edge_quality' else f'{value:.2f}')
            g.fraction=max(0,min(1,(value-lo)/(hi-lo)))
            idx+=1;top-=3*scale
        if tab=='SHAPE':
            for key in dimension_options(s):
                label=LAYOUT_LABELS[key]
                value=getattr(s,key)
                def option(text,step,style='BUTTON'):
                    return text,'bbe.shape_option',{'field':key,'step':step},style
                if key in {'flat','fit'}:
                    row([option(i18n.interface(label)+'   '+i18n.interface('On' if value else 'Off'),1,'PRIMARY' if value else 'BUTTON')])
                else:
                    number=str(value) if key in {'sides','detail'} else f'{value:.0%}'
                    row([option('−',-1),option(i18n.interface(label)+'  '+number,0),option('+',1)])
        if tab in {'HOME','PARTS'} and not native:
            filled=s.fill_gaps and s.fit
            switch=row([('Fill gaps','bbe.shape_option',{'field':'fill_gaps','step':1},'SWITCH')])[0]
            pending=needs_first_fill(root)
            switch.enabled=filled and not pending
            switch.value='Apply' if pending else 'On' if filled else 'Off'
        if tab=='HOME':
            row([action('Dimensions','SHAPE'),action('Deform','DEFORM'),action('Pieces','PARTS')])
            row([action('New shape…','PRESETS'),action('Done','DONE')])
        else:
            if tab=='SHAPE':row([action('Move shape','MOVE'),action('Rotate','ROTATE'),action('Scale','SCALE')])
            back=[action('‹  Home','HOME')]
            row(back)
        for i,g in enumerate(self.buttons):
            hidden=i not in self.used_buttons
            if g.hide!=hidden:g.hide=hidden
        self.card.children=tuple(self.buttons)
        hint=('Select pieces and use your Blender transform tool' if native else 'Release to refill · Click a value to type' if tab in {'HOME','PARTS'} and s.fill_gaps and s.fit
              else 'Click a value to type' if tab!='LAYOUT' else 'Settings for this shape')
        self.card.lines=((12*scale,10*scale,hint,widgets.MUTED),)
        self.draw_grips(context,root,x,y,w,h,scale)
    def draw_grips(self,context,root,x,y,w,h,scale):
        s=root.bbe_shape
        if s.studio_tab in {'HOME','PARTS'}:
            handles=[]
        elif s.studio_tab in {'SHAPE','LAYOUT'}:
            handles=[('width',(s.width/2,0,0)),('depth',(0,s.depth/2,0))]
            if s.dimension=='D3':handles.append(('height',(0,0,s.height/2)))
        else:
            high=s.height/2 if s.dimension=='D3' else s.depth/2
            handles=[('pinch',(s.width/2,0,0)),
                     ('bend',(0,0,high) if s.dimension=='D3' else (0,high,0)),
                     ('twist',(s.width*.28,0,high*.75) if s.dimension=='D3' else (s.width*.28,high*.75,0))]
        if handles and (s.bend or s.twist or s.pinch):
            import numpy as np
            labels,points=zip(*handles)
            handles=list(zip(labels,shape_deform.map_points(np.array(points,dtype=float),s)))
        for i,(g,op) in enumerate(self.grips):
            pos=None
            if i<len(handles):
                field,local=handles[i]
                pos=location_3d_to_region_2d(context.region,context.space_data.region_3d,root.matrix_world @ Vector(local))
            hidden=(pos is None or (x<=pos.x<=x+w and y<=pos.y<=y+h))
            if g.hide!=hidden:g.hide=hidden
            if not hidden:
                g.scale=scale;g.label=LABELS[field];op.field=field
                g.matrix_basis=Matrix.Translation((pos.x,pos.y,0))


CLASSES=(VIEW3D_PT_bbe_shape_part_picker,shape_faces.BBE_OT_shape_faces,BBE_OT_shape_card_move,BBE_OT_shape_exact,BBE_OT_shape_drag,BBE_OT_shape_action,
         BBE_OT_shape_part_id,BBE_OT_shape_layout,BBE_OT_shape_option,BBE_GT_shape_grip,BBE_GGT_shape_studio)

def apply_typed_part(wm,context):
    root=valid_root(context)
    part=wm.bbe_shape_part_input.strip().upper().lstrip('^')
    if not root or part==root.bbe_shape.part_id:return
    window,area=context.window,context.area
    if not area or area.type!='VIEW_3D':return
    def apply():
        if window not in tuple(bpy.context.window_manager.windows) or area not in tuple(window.screen.areas):return
        region=next((r for r in area.regions if r.type=='WINDOW'),None)
        if region:
            with bpy.context.temp_override(window=window,area=area,region=region):
                if valid_root(bpy.context)==root:
                    from . import menu_surface
                    picker=menu_surface._sessions.get(area.as_pointer())
                    result=bpy.ops.bbe.shape_part_id('EXEC_DEFAULT',True,part=part)
                    if picker and picker.menu=='PANEL:VIEW3D_PT_bbe_shape_part_picker':
                        if 'FINISHED' in result:picker.finish()
                        else:picker.message='Could not apply this Object ID. Check the ID or pick a part.'
                        area.tag_redraw()
    bpy.app.timers.register(apply,first_interval=.01)


def register():
    for cls in CLASSES:bpy.utils.register_class(cls)
    bpy.types.WindowManager.bbe_shape_part_input=StringProperty(name='Object ID',description='Type an NMS Object ID and press Enter to use it',options={'SKIP_SAVE'},update=apply_typed_part)
    bpy.app.handlers.load_pre.append(shape_faces.close_all)
    bpy.app.handlers.load_pre.append(shapes.stop_viewport_picks)
    bpy.app.handlers.depsgraph_update_post.append(shapes.shape_selection_changed)

def unregister():
    bpy.app.handlers.depsgraph_update_post.remove(shapes.shape_selection_changed)
    if bpy.app.timers.is_registered(shapes.select_clicked_shape):bpy.app.timers.unregister(shapes.select_clicked_shape)
    bpy.app.handlers.load_pre.remove(shapes.stop_viewport_picks)
    shapes.stop_viewport_picks()
    bpy.app.handlers.load_pre.remove(shape_faces.close_all)
    shape_faces.close_all()
    del bpy.types.WindowManager.bbe_shape_part_input
    for cls in reversed(CLASSES):bpy.utils.unregister_class(cls)
    _anchors.clear()

