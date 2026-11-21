"""Editable outlines and closed shells built from ordinary BBE parts."""
from pathlib import Path

import bpy
from bpy.props import BoolProperty, EnumProperty, FloatProperty, FloatVectorProperty, IntProperty, PointerProperty, StringProperty
from mathutils import Euler, Matrix, Vector

from . import shape_layout, shape_placement

ROOT = 'bbe_shape_controller'
INDEX = 'bbe_shape_slot'
FRAME = 'bbe_shape_frame'
HELPER = 'bbe_shape_helper'
FIELDS = ('dimension','outline','shell','width','depth','height','detail','sides','fit','edge_detail','edge_quality','part_limit',
          'flat','filled_2d','preserve_edges','tube_ratio','pole_taper','fill_gaps','twist','bend','pinch','part_id','paint','face','offset','turn','size')
_requests = {}


def placement_target(context):
    active=context.view_layer.objects.active
    if active and active.select_get():return active
    return next(iter(context.selected_objects),None)


def selected_root(context):
    obj = context.active_object
    if not obj or not obj.select_get():
        return None
    while obj:
        if obj.get(ROOT):
            return obj
        obj = obj.parent
    return None


def settings(context):
    root = selected_root(context)
    return root.bbe_shape if root else context.scene.bbe_shape


def preset_items(presets):
    return [(key, label, '') for key, label in presets]


def get_part_id(s):
    return s.get('chosen_part','BUILDFLATPANEL' if s.dimension=='D2' else 'CUBEFLOOR')


def set_part_id(s,value):
    value=value.strip().lstrip('^').upper()
    if value!=get_part_id(s):
        s.paint=''
    if value:
        s['chosen_part']=value
    elif 'chosen_part' in s:
        del s['chosen_part']


def new_shape_default(s, key):
    # Files predating layout choices need their original geometry on the next edit.
    return s.get(key, isinstance(s.id_data, bpy.types.Scene))


def part_limit(s):
    # A shape saved before limits existed can already exceed the new default.
    return s.get('part_limit',min(shape_layout.MAX_PARTS,max(512,s.id_data.get('bbe_shape_count',0))))


class BBE_PG_shape(bpy.types.PropertyGroup):
    dimension: EnumProperty(name='Shape type', items=[('D2','2D shape','Build a filled shape or an outline'),('D3','3D shell','Cover the outside surface')],default='D3')
    outline: EnumProperty(name='Outline', items=preset_items(shape_layout.OUTLINES))
    shell: EnumProperty(name='Shell', items=preset_items(shape_layout.SHELLS))
    width: FloatProperty(name='Width', min=.05, soft_max=100, default=12, subtype='DISTANCE', unit='LENGTH')
    depth: FloatProperty(name='Depth', min=.05, soft_max=100, default=12, subtype='DISTANCE', unit='LENGTH')
    height: FloatProperty(name='Height', min=.05, soft_max=100, default=12, subtype='DISTANCE', unit='LENGTH')
    detail: IntProperty(name='Detail', description='Higher values use more, smaller pieces', min=1,max=16,soft_max=8,default=2)
    edge_detail: IntProperty(name='Edge detail',description='Use smaller pieces along the silhouette of a filled 2D shape',min=0,max=5,default=2)
    edge_quality: FloatProperty(name='Edge detail',description='Refine the perimeter within the part limit. Release to rebuild',
        min=0,max=100,subtype='PERCENTAGE',precision=1,
        get=lambda s:s.get('edge_quality',s.edge_detail*20.),set=lambda s,v:s.__setitem__('edge_quality',v))
    part_limit: IntProperty(name='2D part limit',description='Maximum number of game parts in this shape',
        min=1,max=shape_layout.MAX_PARTS,get=part_limit,set=lambda s,v:s.__setitem__('part_limit',v))
    sides: IntProperty(name='Sides',min=3,max=128,default=7)
    pole_taper: FloatProperty(name='Pole taper',description='Use smaller fitted pieces and narrower rows near the poles',min=0,max=1,default=.80,subtype='FACTOR')
    tube_ratio: FloatProperty(name='Tube radius',min=.05,max=.48,default=.30,subtype='FACTOR')
    fill_gaps: BoolProperty(name='Fill gaps',default=True,description='Refit the surface with more or fewer pieces when their size changes')
    fit: BoolProperty(name='Fit pieces to outline or shell',description='Match each span using game-compatible uniform scale',default=True)
    filled_2d: BoolProperty(name='Fill', get=lambda s: new_shape_default(s,'filled_2d'),
        set=lambda s,v: s.__setitem__('filled_2d',v))
    preserve_edges: BoolProperty(name='Preserve edges', get=lambda s: new_shape_default(s,'preserve_edges'),
        set=lambda s,v: s.__setitem__('preserve_edges',v))
    flat: BoolProperty(name='Lay border flat',description='Lay the broad face in the outline plane. Turn off for upright edging',default=True)
    part_id: StringProperty(name='Object ID',get=get_part_id,set=set_part_id)
    paint: StringProperty(default='')
    face: EnumProperty(name='Outside face',items=[('AUTO','Automatic','Use the broad face of the part')]+
        [(a,a,'Face this local side outward') for a in ('+X','-X','+Y','-Y','+Z','-Z')])
    offset: FloatVectorProperty(name='Move pieces',subtype='TRANSLATION',unit='LENGTH')
    turn: FloatVectorProperty(name='Rotate pieces',subtype='EULER',unit='ROTATION')
    size: FloatProperty(name='Piece scale',min=.001,soft_max=4,default=1)
    controls: EnumProperty(name='Edit settings',items=[('SHAPE','Shape','Shape dimensions and placement'),
        ('PIECES','Pieces','Fine-tune all pieces in their own axes')])
    twist: FloatProperty(name='Twist',subtype='ANGLE',soft_min=-6.2832,soft_max=6.2832)
    bend: FloatProperty(name='Bend',subtype='ANGLE',min=-2.96706,max=2.96706)
    pinch: FloatProperty(name='Pinch',min=-1,max=.90,description='Narrow the middle; negative values widen it')
    piece_axes: EnumProperty(items=[('offset','Move','Local piece offset'),('turn','Rotate','Local piece rotation')])
    studio_tab: EnumProperty(items=[('SHAPE','Shape','Dimensions and layout'),('DEFORM','Deform','Bend, twist and pinch'),('PARTS','Pieces','Part size and local transform'),('LAYOUT','Layout','Piece count, surface and fit'),('HOME','Home','Shape Studio overview')],default='HOME')
    parent_size: FloatProperty(name='Scale shape',min=.001,soft_max=5,
        get=lambda s: s.id_data.scale.y if isinstance(s.id_data,bpy.types.Object) else 1.,
        set=lambda s,v: setattr(s.id_data,'scale',(v,v,v)) if isinstance(s.id_data,bpy.types.Object) else None)
    pose: BoolProperty(name='Parent transform',default=False)


def preview_icon(key):
    from . import menu_backend
    icons=menu_backend._icons
    name='shape_'+key
    if name not in icons:
        icons.load(name,str(Path(__file__).parent/'images'/'shapes'/(key+'.png')),'IMAGE')
    return icons[name].icon_id


class BBE_OT_shape_preset(bpy.types.Operator):
    bl_idname='bbe.shape_preset'
    bl_label='Choose Shape'
    bl_options={'UNDO'}
    kind: StringProperty()
    @classmethod
    def description(cls,context,properties):
        return shape_layout.LABELS.get(properties.kind,'Choose shape')
    def execute(self,context):
        s=settings(context)
        if self.kind not in shape_layout.LABELS:
            return {'CANCELLED'}
        set_preset(s,self.kind)
        return {'FINISHED'}


def set_preset(s,kind):
    if kind in dict(shape_layout.OUTLINES):
        s.dimension='D2'
        s.outline=kind
        if kind in {'CIRCLE','ELLIPSE'}:
            s.depth=s.width*(.65 if kind=='ELLIPSE' else 1)
    else:
        s.dimension='D3'
        s.shell=kind
        if kind in {'SPHERE','OBLATE','PROLATE','ELLIPSOID','TORUS'}:
            s.depth=s.width*(.76 if kind=='ELLIPSOID' else 1)
            s.height=s.width*{'OBLATE':.55,'PROLATE':1.5,'TORUS':s.tube_ratio,'ELLIPSOID':.6}.get(kind,1)


class BBE_OT_start_shape(bpy.types.Operator):
    bl_idname='bbe.start_shape'
    bl_label='Start Shape Studio'
    bl_description='Pick a starting point, edge or face, or place the base at the 3D cursor'
    bl_options={'REGISTER','UNDO'}
    kind: StringProperty()
    at_cursor: BoolProperty(options={'HIDDEN','SKIP_SAVE'})
    @classmethod
    def description(cls,context,properties):
        return 'Create '+shape_layout.LABELS.get(properties.kind,'shape')+' in Shape Studio'
    def invoke(self,context,event):
        if context.area and context.area.type=='VIEW_3D':
            region=next(r for r in context.area.regions if r.type=='WINDOW')
            with context.temp_override(region=region):
                bpy.ops.bbe.align_geometry('INVOKE_DEFAULT',shape_kind=self.kind)
            return {'CANCELLED'}  # Align owns the creation and its single Undo step.
        return self.execute(context)
    def execute(self,context):
        target=placement_target(context)
        origin=target.matrix_world.translation if target and not self.at_cursor else context.scene.cursor.location
        return self.create(context,Matrix.Translation(origin))
    def create(self,context,pose):
        if self.kind not in shape_layout.LABELS or context.mode!='OBJECT':
            return {'CANCELLED'}
        s=context.scene.bbe_shape
        source=selected_root(context)
        # Copy only the asset and paint. Each preset keeps its own shape settings.
        set_preset(s,self.kind)
        if source:use_id(s,source.bbe_shape.part_id,source.bbe_shape.paint)
        try:
            root=build(context,new=True,placement=pose)
        except (ValueError,RuntimeError) as exc:
            self.report({'ERROR'},str(exc))
            return {'CANCELLED'}
        if context.area and context.area.type=='VIEW_3D':
            context.space_data.show_gizmo=True
            context.space_data.show_gizmo_context=True
            context.area.tag_redraw()
        root.bbe_shape.studio_tab='HOME'
        return {'FINISHED'}


def use_id(s,part,paint=None):
    s.part_id=part.lstrip('^').upper()
    s.paint='' if paint is None else str(paint)


def replace_part(context,root,part,paint=None):
    settings=root.bbe_shape if root else context.scene.bbe_shape
    previous=(settings.part_id,settings.paint,'chosen_part' in settings)
    use_id(settings,part,paint)
    if root:
        try:
            from .progress_ui import Activity
            with Activity('Applying shape part',settings.part_id) as progress:
                build(context,owner=root,progress=progress)
                progress.update(1,'Shape ready')
        except Exception:
            settings.part_id=previous[0] if previous[2] else ''
            settings.paint=previous[1]
            raise


def pick_from_browser(context,part,is_preset,variants):
    pointer=context.window.as_pointer()
    request=_requests.get(pointer)
    if not request:return False
    if request['picked']:return True  # Ignore a second click until the gallery closes.
    if is_preset or part.startswith('BBE_REF'):
        raise ValueError('Choose one native NMS part from the catalogue.')
    if variants:return False
    from .utils import dictionary
    from . import builder_v2
    if part not in dictionary.get_nice_names_diictionary() and not builder_v2.BUILDER.get_obj_path(part):
        raise ValueError('Choose a native NMS part.')
    request['picked']=True
    # Window destruction must happen outside the gallery's own event handler.
    def close_gallery():
        if _requests.get(pointer) is not request:return
        from .tools import asset_browser_grid
        gallery=next((w for w in bpy.context.window_manager.windows if w.as_pointer()==pointer),None)
        if gallery:
            request['cursor'].close()
            asset_browser_grid.close_picker_window(gallery)
        bpy.app.timers.register(apply_in_studio)
    def apply_in_studio():
        if _requests.get(pointer) is not request:return
        if any(w.as_pointer()==pointer for w in bpy.context.window_manager.windows):
            return .02
        del _requests[pointer]
        window,area,scene,root=request['owner']
        try:
            if window not in tuple(bpy.context.window_manager.windows) or window.scene!=scene:return
            if area not in tuple(window.screen.areas) or area.type!='VIEW_3D':return
            region=next(r for r in area.regions if r.type=='WINDOW')
            with bpy.context.temp_override(window=window,area=area,region=region):
                if root is not None and (scene.objects.get(root.name)!=root or not root.get(ROOT)):return
                try:
                    bpy.ops.bbe.apply_shape_pick('EXEC_DEFAULT',True,part=part,owner=root.name if root else '')
                except RuntimeError as exc:
                    message=str(exc).strip()
                    bpy.context.window_manager.popup_menu(lambda menu,ctx:menu.layout.label(text=message),
                                                         title='Could not change shape part',icon='ERROR')
        except ReferenceError:
            return  # The original scene or shape was removed before application.
    bpy.app.timers.register(close_gallery)
    return True


class BBE_OT_apply_shape_pick(bpy.types.Operator):
    bl_idname='bbe.apply_shape_pick'
    bl_label='Change Shape Part'
    bl_options={'INTERNAL','UNDO'}
    part:StringProperty()
    owner:StringProperty()
    def execute(self,context):
        root=context.scene.objects.get(self.owner) if self.owner else None
        if self.owner and (not root or not root.get(ROOT)):return {'CANCELLED'}
        try:replace_part(context,root,self.part)
        except (ValueError,RuntimeError) as exc:
            self.report({'ERROR'},str(exc))
            return {'CANCELLED'}
        return {'FINISHED'}


class PickPointer:
    """Draw the pipette at the actual pick hotspot on either picking surface."""
    def __init__(self, window):
        self.window = window
        self.position = None

    def move(self, area, region, event):
        xy = event.mouse_x-region.x, event.mouse_y-region.y
        inside = 0 <= xy[0] < region.width and 0 <= xy[1] < region.height
        if not inside and self.position is None:return
        if inside and xy==self.position:return
        if inside and self.position is None:
            self.window.cursor_modal_set('NONE')
        elif not inside and self.position is not None:
            self.close()
        self.position = xy if inside else None
        area.tag_redraw()

    def close(self):
        if self.position is not None:
            try:self.window.cursor_modal_restore()
            except ReferenceError:pass
            self.position = None

    def draw(self, context):
        if self.position is None:return
        import gpu
        from . import curve_widgets as ui
        x,y = self.position
        scale=max(.8,context.preferences.system.ui_scale)
        def pt(px,py):return x+px*scale,y+py*scale
        ink=(.025,.03,.04,1); white=(1.,1.,1.,1)
        with ui.canvas(context):
            shader=gpu.shader.from_builtin('UNIFORM_COLOR')
            # Glass tube, rubber bulb and guard. The point is the click position.
            ui.polygon(shader,[pt(0,0),pt(2,7),pt(16,21),pt(22,15),pt(7,2)],ink)
            ui.polygon(shader,[pt(2,2),pt(4,7),pt(16,19),pt(20,15),pt(7,4)],white)
            ui.line(shader,pt(6,6),pt(14,14),2*scale,(.08,.55,.64,1))
            ui.line(shader,pt(13,21),pt(21,13),4*scale,ink)
            ui.line(shader,pt(17,17),pt(24,24),8*scale,ink)
            ui.disc(shader,*pt(23,23),4*scale,ink)
            ui.line(shader,pt(17,19),pt(23,25),1.7*scale,white)


_viewport_pickers = {}


@bpy.app.handlers.persistent
def stop_viewport_picks(*_):
    for op in tuple(_viewport_pickers.values()):
        op.cancel(bpy.context)


class BBE_OT_shape_assets(bpy.types.Operator):
    bl_idname='bbe.shape_assets'
    bl_label='Choose from Asset Browser'
    bl_options={'INTERNAL'}
    bl_description='Click a part to use it for this shape. Close the asset window to cancel'
    def execute(self,context):
        wm=context.window_manager
        before={w.as_pointer() for w in wm.windows}
        for pointer in set(_requests)-before:
            del _requests[pointer]
        owner=(context.window,context.area,context.scene,selected_root(context))
        if 'FINISHED' not in bpy.ops.object.nms_launch_asset_browser_window():
            return {'CANCELLED'}
        for window in wm.windows:
            if window.as_pointer() not in before:
                _requests[window.as_pointer()]={'owner':owner,'picked':False,'cursor':PickPointer(window)}
                return {'FINISHED'}
        return {'CANCELLED'}


class BBE_OT_shape_dropper(bpy.types.Operator):
    bl_idname='bbe.shape_dropper'
    bl_label='Pick a Viewport Part'
    bl_description='Click a placed NMS part to use its Object ID and colour'
    bl_options={'UNDO','BLOCKING'}
    def invoke(self,context,event):
        self.owner=selected_root(context)
        self.window=context.window
        self.area=context.area
        self.region=next(r for r in self.area.regions if r.type=='WINDOW')
        self.key=self.window.as_pointer()
        if self.key in _viewport_pickers:return {'CANCELLED'}
        self.pointer=PickPointer(self.window)
        self.handler=bpy.types.SpaceView3D.draw_handler_add(self.draw_pointer,(),'WINDOW','POST_PIXEL')
        _viewport_pickers[self.key]=self
        self.pointer.move(self.area,self.region,event)
        self.area.header_text_set('Pick a shape part in the viewport. Esc cancels.')
        context.window_manager.modal_handler_add(self)
        return {'RUNNING_MODAL'}
    def draw_pointer(self):
        ctx=bpy.context
        if ctx.window==self.window and ctx.area==self.area and ctx.region==self.region:
            self.pointer.draw(ctx)
    def cancel(self,context):
        if _viewport_pickers.pop(self.key,None) is not self:return
        bpy.types.SpaceView3D.draw_handler_remove(self.handler,'WINDOW')
        self.pointer.close()
        try:
            self.area.header_text_set(None)
            self.area.tag_redraw()
        except ReferenceError:pass
    def modal(self,context,event):
        if self.key not in _viewport_pickers:return {'CANCELLED'}
        if event.type in {'ESC','RIGHTMOUSE','WINDOW_DEACTIVATE'}:
            self.cancel(context)
            return {'CANCELLED'}
        if event.type in {'MOUSEMOVE','INBETWEEN_MOUSEMOVE'}:
            self.pointer.move(self.area,self.region,event)
            return {'RUNNING_MODAL'}
            return {'RUNNING_MODAL'}
        if event.type=='LEFTMOUSE' and event.value=='PRESS':
            from bpy_extras import view3d_utils as view
            xy=(event.mouse_x-self.region.x,event.mouse_y-self.region.y)
            if not (0<=xy[0]<self.region.width and 0<=xy[1]<self.region.height):
                return {'RUNNING_MODAL'}
            rv=self.area.spaces.active.region_3d
            origin=view.region_2d_to_origin_3d(self.region,rv,xy)
            ray=view.region_2d_to_vector_3d(self.region,rv,xy)
            from .viewport_cutaway import scene_pick
            hit,_,_,_,obj,_=scene_pick(context.scene,context.evaluated_depsgraph_get(),origin,ray)
            obj=obj.original if hit else None
            while obj and not obj.get('ObjectID'):
                obj=obj.parent
            if obj:
                self.cancel(context)  # Restore the pointer before showing the loading bar.
                try:
                    replace_part(context,self.owner,obj['ObjectID'],obj.get('UserData'))
                except (ValueError,RuntimeError) as exc:
                    self.report({'ERROR'},str(exc))
                    return {'CANCELLED'}
                return {'FINISHED'}
            self.report({'INFO'},'Click a placed NMS part')
        return {'PASS_THROUGH'} if event.type in {'MIDDLEMOUSE','WHEELUPMOUSE','WHEELDOWNMOUSE','MOUSEMOVE'} else {'RUNNING_MODAL'}


def part_geometry(obj):
    # Model coordinates can be offset from the game pivot. Fit the actual
    # outside face, then move the pivot back by the same local offset.
    descendants=[item for item in obj.children_recursive if INDEX not in obj or item.get(HELPER)]
    for item in (obj,*descendants):
        if item.type not in {'MESH','CURVE'}:continue
        # Measure in native mesh space. A world/inverse round trip introduces
        # pose-dependent noise at the thresholds between adjacent tile counts.
        relative=Matrix.Identity(4)
        ancestor=item
        while ancestor!=obj:
            relative=ancestor.matrix_local @ relative
            ancestor=ancestor.parent
        yield item,relative


def part_face(obj,face,*,with_depth=False):
    points=[relative @ Vector(c) for item,relative in part_geometry(obj) for c in item.bound_box]
    if not points:
        raise ValueError('This proxy has no measurable surface. Pick a part with visible geometry.')
    lo=Vector(tuple(min(p[i] for p in points) for i in range(3)))
    hi=Vector(tuple(max(p[i] for p in points) for i in range(3)))
    extent=hi-lo
    if face=='AUTO':
        axis=min(range(3),key=lambda i:extent[i])
        sign=-1 if obj.get('ObjectID')=='STORAGEPANEL' and axis==1 else 1
    else:
        axis='XYZ'.index(face[1])
        sign=1 if face[0]=='+' else -1
    a,b=sorted((i for i in range(3) if i!=axis),key=lambda i:-extent[i])
    if min(extent[a],extent[b])<.00001:
        raise ValueError('This face has no usable area. Choose another outside face.')
    normal=Vector();normal[axis]=sign
    along=Vector();along[a]=1
    center=(lo+hi)/2;center[axis]=hi[axis] if sign>0 else lo[axis]
    frame=Matrix((along,normal.cross(along),normal)).transposed().to_4x4()
    frame.translation=center
    footprint = (extent[a], extent[b], extent[axis]) if with_depth else (extent[a], extent[b])
    return footprint, frame.inverted()


PART_FACES=('+X','-X','+Y','-Y','+Z','-Z')


def resolved_part_face(root):
    if root.bbe_shape.face!='AUTO':return root.bbe_shape.face
    saved=root.get('bbe_shape_auto_face')
    if saved in PART_FACES:return saved
    part=next((p for p in root.children if INDEX in p),None)
    return automatic_part_face(part) if part else '+Z'


def automatic_part_face(part):
    _,correction=part_face(part,'AUTO')
    direction=correction.to_3x3()[2]
    axis=max(range(3),key=lambda i:abs(direction[i]))
    return ('+' if direction[axis]>0 else '-')+'XYZ'[axis]


def apply_part_face(context,root,face):
    if face not in PART_FACES:raise ValueError('Choose one of the six part faces')
    s=root.bbe_shape
    old=s.face
    if face==old:return
    s.face=face
    try:build(context,owner=root,reflow=True)
    except (RuntimeError,ValueError):
        s.face=old
        raise


def native_pieces(context,root):
    addon=context.preferences.addons.get(__package__)
    return bool(addon and addon.preferences.shape_use_blender_tools and root.bbe_shape.studio_tab=='PARTS')


def encode(matrix):
    return [v for row in matrix for v in row]


def decode(values):
    return Matrix([values[i:i+4] for i in (0,4,8,12)])


def choose(context,objects):
    for other in context.selected_objects:
        other.select_set(False)
    if len(objects)==1 and objects[0].get(ROOT):
        root=objects[0];parts=shape_parts(root)
        objects=parts if parts and native_pieces(context,root) else [root,*parts]
    for obj in objects:
        if obj.name in context.view_layer.objects and not obj.hide_get():obj.select_set(True)
    context.view_layer.objects.active=objects[0] if objects else None


def copy_settings(source,target):
    for key in FIELDS:
        setattr(target,key,getattr(source,key))
    if 'chosen_part' not in source and 'chosen_part' in target:
        del target['chosen_part']


def shape_parts(root):
    return sorted((c for c in root.children if INDEX in c),key=lambda c:c[INDEX])


# A representative piece lets a direct click on the controller be recognized
# without enumerating a large shape on every dependency graph update.
_group_probe=None

def select_clicked_shape():
    global _group_probe
    context=bpy.context
    from . import undo_guard
    if undo_guard.restoring or context.mode!='OBJECT' or shape_placement.busy(context.area):return
    root=selected_root(context)
    if not root or native_pieces(context,root):return
    active=context.active_object
    if active!=root and INDEX not in active and not active.get(HELPER):return
    parts=shape_parts(root)
    _group_probe=(root.session_uid,next((p for p in parts if p.visible_get()),None))
    # The explicit Pieces selection remains available for individual edits.
    if active!=root and len(parts)>1 and all(p.select_get() for p in parts):return
    for obj in [root,*parts]:
        if obj.name in context.view_layer.objects and obj.visible_get() and not obj.hide_select and not obj.select_get():
            obj.select_set(True)
    context.view_layer.objects.active=root


@bpy.app.handlers.persistent
def shape_selection_changed(*_):
    context=bpy.context
    active=getattr(context, 'active_object', None)
    if not active or context.mode!='OBJECT' or not active.select_get():return
    if (INDEX in active or active.get(ROOT)) and native_pieces(context,selected_root(context) or active):return
    if active.get(ROOT):
        if _group_probe and _group_probe[0]==active.session_uid:
            probe=_group_probe[1]
            try:
                if probe is None or probe.select_get():return
            except (ReferenceError,RuntimeError):pass
    elif INDEX not in active and not active.get(HELPER):return
    if not bpy.app.timers.is_registered(select_clicked_shape):
        bpy.app.timers.register(select_clicked_shape,first_interval=0)


def ungroup_shapes(context):
    roots={obj for obj in context.selected_objects if obj.get(ROOT)}
    if not roots:
        active=selected_root(context)
        if active:roots.add(active)
    restored=[]
    for root in roots:
        pieces=shape_parts(root)
        for obj in tuple(root.children):
            world=obj.matrix_world.copy()
            obj.parent=root.parent
            obj.matrix_world=world
        for piece in pieces:
            del piece[INDEX]
            if FRAME in piece:del piece[FRAME]
            for helper in piece.children_recursive:
                if HELPER in helper:del helper[HELPER]
        bpy.data.objects.remove(root,do_unlink=True)
        restored.extend(pieces)
    return restored


def build(context,*,new=False,owner=None,refine=False,reflow=False,progress=None,placement=None):
    from . import builder_v2
    from .utils import dictionary
    root=owner if owner is not None else None if new else selected_root(context)
    if root is None and placement is None:
        target=placement_target(context)
        placement=Matrix.Translation(target.matrix_world.translation if target else context.scene.cursor.location)
    s=root.bbe_shape if root else context.scene.bbe_shape
    part=s.part_id.strip().lstrip('^').upper()
    if part not in dictionary.get_nice_names_diictionary() and not builder_v2.BUILDER.get_obj_path(part):
        raise ValueError('Unknown Object ID. Choose a part from Assets or the viewport.')
    kind=s.outline if s.dimension=='D2' else s.shell
    old=shape_parts(root) if root else []
    collection=root.users_collection[0] if root else context.collection
    selection=list(context.selected_objects)
    active=context.active_object
    reusable=bool(old and root.get('bbe_shape_part')==part and root.get('bbe_shape_paint','')==s.paint)
    stage=[]
    created_root=False
    new_objects_before=None
    try:
        if reusable:
            template=old[0]
            # Measure only the native part and helpers, never a user-parented part.
        else:
            new_objects_before=set(bpy.data.objects)
            template=builder_v2.add_part(part,user_data=int(s.paint) if s.paint else None,build_rigs=False).object
            stage.append(template)
            context.view_layer.update()
        footprint,correction=part_face(template,s.face,with_depth=True)
        planar=s.dimension=='D2' and s.filled_2d and s.fit
        if planar:
            from .shape_planar import face_profile
            footprint,correction=face_profile(part_geometry(template),footprint,correction,context.evaluated_depsgraph_get())
        if progress:progress.update(.16,'Fitting the shape surface')
        from . import shape_deform
        auto_face=automatic_part_face(template)
        surface=shape_deform.surface(root,s,footprint,correction,refined=True if refine else None,
                                     reflow=reflow,planar=planar,budgeted=True)
        frames=[Matrix(m) for m in surface.matrices(s).tolist()]
        if not root:
            root=bpy.data.objects.new('Shapes | '+shape_layout.LABELS[kind],None)
            created_root=True
            collection.objects.link(root)
            root.empty_display_type='PLAIN_AXES'
            root.empty_display_size=max(.25,min(s.width,s.depth)*.1)
            root[ROOT]=True
            copy_settings(s,root.bbe_shape)
        # Allocate first, mutate existing pieces only once all copies are ready.
        reuse_layout=reusable and not (refine and not root.get('bbe_shape_refined'))
        by_slot={p[INDEX]:p for p in old} if reuse_layout else {}
        pieces=[]
        retained=set()
        helpers=[h for h in template.children_recursive if h.get(HELPER)] if reusable else list(template.children_recursive)
        base_order=len(bpy.data.objects)
        count=len(surface.slots)
        for index,slot in enumerate(surface.slots):
            if progress and index%16==0:progress.batch(index,count,.28,.70,'Preparing pieces')
            if slot in by_slot:
                obj=by_slot[slot]
                retained.add(obj)
                pieces.append(obj)
                continue
            if not reusable and index==0:
                obj=template
                for h in helpers:
                    h[HELPER]=True
            else:
                obj=template.copy()
                stage.append(obj)
                collection.objects.link(obj)
                remap={template:obj}
                for helper in helpers:
                    clone=helper.copy()
                    stage.append(clone)
                    collection.objects.link(clone)
                    remap[helper]=clone
                for helper in helpers:
                    remap[helper].parent=remap[helper.parent]
            obj.parent=root
            obj.matrix_parent_inverse=Matrix.Identity(4)
            obj['order']=base_order+index
            pieces.append(obj)
        for i,(obj,frame) in enumerate(zip(pieces,frames)):
            if progress and i%32==0:progress.batch(i,count,.70,.89,'Positioning pieces')
            # Carry individual G/R/S edits forward while the topology matches.
            delta=Matrix.Identity(4)
            if obj in retained and root.get('bbe_shape_kind')==kind and FRAME in obj:
                delta=decode(obj[FRAME]).inverted_safe() @ obj.matrix_basis
            obj.matrix_basis=frame @ delta
            obj[FRAME]=encode(frame)
            obj[INDEX]=surface.slots[i]
        if progress:progress.update(.90,'Replacing the previous pieces')
        stale=[p for p in old if p not in retained]
        if not pieces and not reusable:
            bpy.data.batch_remove([template,*helpers])
        remove=[h for p in stale for h in p.children_recursive if h.get(HELPER)]
        if stale:
            removing=set(stale+remove)
            # Preserve separately authored objects attached to a replaced part.
            for parent in removing:
                for child in parent.children:
                    if child not in removing:
                        world=child.matrix_world.copy()
                        child.parent=root
                        child.matrix_world=world
            bpy.data.batch_remove(stale+remove)
        prior=shape_layout.LABELS.get(root.get('bbe_shape_kind',''))
        if prior and root.name=='Shapes | '+prior:
            root.name='Shapes | '+shape_layout.LABELS[kind]
        if created_root or refine:root['bbe_shape_refined']=True
        if surface.fill_scale is None:
            if 'bbe_shape_fill_scale' in root:del root['bbe_shape_fill_scale']
        else:root['bbe_shape_fill_scale']=surface.fill_scale
        root['bbe_shape_rest_dims']=surface.dims.tolist()
        root['bbe_shape_auto_face']=auto_face
        root['bbe_shape_kind']=kind
        root['bbe_shape_part']=part
        root['bbe_shape_paint']=s.paint
        if s.dimension=='D2':
            root.bbe_shape.part_limit=s.part_limit
            root['bbe_shape_budgeted']=True
        root['bbe_shape_count']=len(frames)
        if planar:
            root['bbe_shape_rim_layout']=True
            root['bbe_shape_planar_face']=encode(correction)
            root['bbe_shape_planar_size']=list(footprint)
        elif 'bbe_shape_planar_face' in root:
            del root['bbe_shape_planar_face'],root['bbe_shape_planar_size']
        choose(context,[root])
        if progress:progress.update(.97,'Updating the viewport')
        context.view_layer.update()
        if created_root:
            shape_placement.seat_shape(context,root,placement)
        return root
    except Exception:
        cleanup=set(stage) if new_objects_before is None else set(bpy.data.objects)-new_objects_before
        if created_root:
            cleanup.add(root)
        if cleanup:
            bpy.data.batch_remove(cleanup)
        choose(context,[o for o in selection if o.name in context.scene.objects])
        context.view_layer.objects.active=active
        raise


class BBE_OT_shape_build(bpy.types.Operator):
    bl_idname='bbe.shape_build'
    bl_label='Build Shape'
    bl_description='Create at the 3D cursor, or apply settings to the selected shape'
    bl_options={'REGISTER','UNDO'}
    @classmethod
    def poll(cls,context):
        return context.mode=='OBJECT'
    def execute(self,context):
        try:
            root=build(context)
        except (ValueError,RuntimeError,KeyError) as exc:
            self.report({'ERROR'},str(exc))
            return {'CANCELLED'}
        self.report({'INFO'},f"{root.name} · {root['bbe_shape_count']} parts")
        return {'FINISHED'}


class BBE_OT_shape_select(bpy.types.Operator):
    bl_idname='bbe.shape_select'
    bl_label='Shape Selection'
    bl_options={'UNDO'}
    target: EnumProperty(items=[('NEW','New shape','Start a separate shape at the 3D cursor'),('PARENT','Parent','Select the entire shape'),('PARTS','Pieces','Select the individual build parts')])
    def execute(self,context):
        root=selected_root(context)
        if not root:
            return {'CANCELLED'}
        if self.target=='NEW':
            copy_settings(root.bbe_shape,context.scene.bbe_shape)
            choose(context,[])
        else:
            choose(context,[root] if self.target=='PARENT' else shape_parts(root))
        return {'FINISHED'}


def draw(layout,context,sidebar=False,*,guided=False):
    from . import i18n
    ui=i18n.localized_layout(layout)
    s=context.scene.bbe_shape
    tabs=ui.row(align=True)
    from .save_editor.function_help import corner_help
    for key,label,icon,native in [('D2','2D shape','RECTANGLE','MESH_PLANE'),
                                   ('D3','3D shell','BOX','MESH_CUBE')]:
        # Blender's native prop_enum accepts a built-in icon only. The top
        # bar's renderer also accepts the full-colour shape thumbnails.
        artwork = {'icon': native} if sidebar else {'icon_value': preview_icon(icon)}
        tabs.prop_enum(s,'dimension',key,text=label,**artwork)
    if not guided:corner_help(tabs, 'SHAPES')
    presets=shape_layout.OUTLINES if s.dimension=='D2' else shape_layout.SHELLS
    field='outline' if s.dimension=='D2' else 'shell'
    kind=getattr(s,field)
    columns=(2 if context.region.width<330*context.preferences.system.ui_scale else 3) if sidebar else 4
    grid=ui.grid_flow(row_major=True,columns=columns,even_columns=True,even_rows=True,align=True)
    grid.operator_context='INVOKE_DEFAULT' if guided else 'EXEC_DEFAULT'
    grid.scale_y=1.45
    for key,label in presets:
        item=grid.operator('bbe.start_shape',text=label if sidebar else '',icon_value=preview_icon(key),depress=key==kind)
        item.kind=key


class VIEW3D_PT_bbe_shapes(bpy.types.Panel):
    bl_label='Shapes'
    bl_idname='VIEW3D_PT_bbe_shapes'
    bl_space_type='VIEW_3D'
    bl_region_type='UI'
    bl_category='No Mans Sky Base Builder'
    bl_options={'DEFAULT_CLOSED'}
    def draw_header(self,context):
        from . import sidebar_builder
        sidebar_builder.begin_header(self, context, 'shapes')
        self.layout.label(text='',icon_value=preview_icon('BOX'))
    def draw(self,context):
        from . import sidebar_builder
        if not sidebar_builder.draw_inline(self, context, 'shapes'):
            draw(self.layout,context,sidebar=True)


classes=(BBE_PG_shape,BBE_OT_shape_preset,BBE_OT_start_shape,BBE_OT_apply_shape_pick,BBE_OT_shape_assets,BBE_OT_shape_dropper,
         BBE_OT_shape_build,BBE_OT_shape_select,VIEW3D_PT_bbe_shapes)

