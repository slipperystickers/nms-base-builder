"""Join two open Curve Tools paths at the endpoints picked in the viewport."""
import blf
from mathutils import Matrix, Vector
import bpy
from bpy_extras.view3d_utils import location_3d_to_region_2d

from . import curve_links
from . import i18n
from .curve_shapes import SHAPES

FIRST = "Click the first curve endpoint. Esc cancels."
SECOND = "Click another endpoint to join or close the path. Esc cancels."
HELP = "Click two endpoints to join paths or close one path. Esc cancels."
GUIDE = 'bbe_easy_curve'


def endpoints(context):
    from .utils.curve import is_guide_object
    for obj in context.visible_objects:
        if (not is_guide_object(obj) or obj.hide_select or obj.library or obj.data.library or obj.data.shape_keys):
            continue
        for index, spline in enumerate(obj.data.splines):
            if spline.type != 'BEZIER' or spline.use_cyclic_u or len(spline.bezier_points) < 2:
                continue
            for end in (0, -1):
                yield (obj.name, index, end), obj.matrix_world @ spline.bezier_points[end].co


def ordered_points(spline, transform, reverse):
    records = []
    for point in spline.bezier_points:
        left = point.handle_right if reverse else point.handle_left
        right = point.handle_left if reverse else point.handle_right
        records.append([transform @ point.co, transform @ left, transform @ right,
                        point.radius, -point.tilt if reverse else point.tilt, point.weight_softbody])
    return records[::-1] if reverse else records


def join(context, first, second):
    from . import curve_tools
    a, ai, ae = first
    b, bi, be = second
    keep = context.view_layer.objects.get(a)
    donor = context.view_layer.objects.get(b)
    if keep is None or donor is None or first == second:
        raise ValueError("Choose endpoints on two different paths.")
    if first not in dict(endpoints(context)) or second not in dict(endpoints(context)):
        raise ValueError("Choose two visible, open Bezier paths.")
    if (a, ai) == (b, bi):
        # Joining two arcs leaves one open spline; allow its remaining ends
        # to close without duplicating or reversing the existing geometry.
        curve_tools.own_data(keep)
        spline = keep.data.splines[ai]
        start, end = spline.bezier_points[0], spline.bezier_points[-1]
        gap = start.co - end.co
        end.handle_right_type = start.handle_left_type = 'FREE'
        end.handle_right = end.co + gap / 3
        start.handle_left = start.co - gap / 3
        spline.use_cyclic_u = True
        keep[GUIDE] = True
        props = keep.bbe_curve
        props.kind, props.spline, props.selected = 'FREE', ai, 0
        for key in ('bbe_curve_baseline', 'bbe_curve_handle_baseline'):
            if key in keep: del keep[key]
        for obj in context.selected_objects:
            obj.select_set(False)
        keep.select_set(True)
        context.view_layer.objects.active = keep
        curve_tools.open_viewport_controls(context, keep)
        curve_tools.refresh(keep)
        return
    # Keep an existing array attached to its guide. Two independent arrays cannot
    # both control one path without changing their spacing and ownership.
    if keep != donor and curve_links.has_followers(donor):
        if curve_links.has_followers(keep):
            raise ValueError("Unlink one array before connecting two guides with attached parts.")
        return join(context, second, first)
    if keep != donor and len(donor.data.splines) == 1 and donor.children:
        raise ValueError("The second curve has children. Pick that curve first to keep its children.")
    if keep != donor and keep.matrix_world.to_3x3().determinant() == 0:
        raise ValueError("The first curve has zero scale.")
    sa, sb = keep.data.splines[ai], donor.data.splines[bi]
    to_local = Matrix.Identity(4) if keep == donor else keep.matrix_world.inverted() @ donor.matrix_world
    left = ordered_points(sa, Matrix.Identity(4), ae == 0)
    right = ordered_points(sb, to_local, be == -1)
    gap = right[0][0] - left[-1][0]
    seam = len(left) - 1
    if (keep.matrix_world.to_3x3() @ gap).length < 0.00001:
        left[-1][2] = right[0][2]
        right = right[1:]
    else:
        left[-1][2] = left[-1][0] + gap / 3
        right[0][1] = right[0][0] - gap / 3
    records = left + right
    curve_tools.own_data(keep)
    if donor != keep and len(donor.data.splines) > 1:
        curve_tools.own_data(donor)
    sa, sb = keep.data.splines[ai], donor.data.splines[bi]
    # Replace the keeper spline in place to retain its order and spline settings.
    sa.bezier_points.add(len(records) - len(sa.bezier_points))
    for point, (co, hl, hr, radius, tilt, weight) in zip(sa.bezier_points, records):
        point.handle_left_type = point.handle_right_type = 'FREE'
        point.co, point.handle_left, point.handle_right = co, hl, hr
        point.radius, point.tilt, point.weight_softbody = radius, tilt, weight
    if keep == donor or len(donor.data.splines) > 1:
        donor.data.splines.remove(sb)
        if keep == donor and bi < ai:
            ai -= 1
        if donor != keep:
            donor.bbe_curve.kind = 'FREE'
            curve_tools.refresh(donor)
    else:
        bpy.data.objects.remove(donor, do_unlink=True)
    keep[GUIDE] = True
    props = keep.bbe_curve
    props.kind, props.spline, props.selected = 'FREE', ai, seam
    for key in ('bbe_curve_baseline', 'bbe_curve_handle_baseline'):
        if key in keep:
            del keep[key]
    for obj in context.selected_objects:
        obj.select_set(False)
    keep.select_set(True)
    context.view_layer.objects.active = keep
    curve_tools.open_viewport_controls(context, keep)
    curve_tools.refresh(keep)




ACTIONS = (
    ('LINE', 'Connect with Line', 'Pick two endpoints. Join the paths with a straight segment without moving either curve'),
    ('MOVE', 'Move & Connect Curves', 'Pick the endpoint to move, then a destination endpoint. Move the whole first curve and join both into one path'),
    ('NEW', 'Start New Curve Here', 'Pick a curve point, then choose an arc, half circle, corkscrew, other preset, or free drawing'),
)


def curve_points(context):
    # Same editable-owner filter as endpoint joining, including closed paths.
    from .utils.curve import is_guide_object
    for obj in context.visible_objects:
        if (not is_guide_object(obj) or obj.hide_select or obj.library or obj.data.library or obj.data.shape_keys):
            continue
        for index,spline in enumerate(obj.data.splines):
            if spline.type=='BEZIER':
                for point,bp in enumerate(spline.bezier_points):
                    yield (obj.name,index,point),obj.matrix_world @ bp.co


def point_position(context,key):
    obj=context.view_layer.objects.get(key[0])
    if obj is None:raise ValueError('That curve is no longer available.')
    return obj.matrix_world @ obj.data.splines[key[1]].bezier_points[key[2]].co


def move_curve(context,first,second):
    from . import curve_tools
    if first not in dict(endpoints(context)):
        raise ValueError('Choose an open endpoint on the curve to move.')
    source=context.view_layer.objects.get(first[0]);target=context.view_layer.objects.get(second[0])
    if source is None or target is None or source==target:
        raise ValueError('Choose a point on a different curve.')
    if second not in dict(curve_points(context)) and second not in dict(endpoints(context)):
        raise ValueError('Choose a visible curve point.')
    parent=target.parent
    while parent:
        if parent==source:raise ValueError('The destination is a child of the curve being moved.')
        parent=parent.parent
    if any(source.lock_location) or source.constraints:
        raise ValueError('Unlock the curve location and remove movement constraints before snapping.')
    delta=point_position(context,second)-point_position(context,first)
    transform=source.matrix_world.copy();transform.translation+=delta
    source.matrix_world=transform
    context.view_layer.update();curve_tools.refresh(source)
    for obj in context.selected_objects:obj.select_set(False)
    source.select_set(True);context.view_layer.objects.active=source
    return source


def move_and_connect(context,first,second):
    available=dict(endpoints(context))
    if first not in available or second not in available or first[0]==second[0]:
        raise ValueError('Choose open endpoints on two different curves.')
    source=context.view_layer.objects[first[0]]
    target=context.view_layer.objects[second[0]]
    if curve_links.has_followers(source) and curve_links.has_followers(target):
        raise ValueError('Unlink one array before joining two guides with attached parts.')
    # Keep the object that owns children/array settings. Validate before moving.
    keep,donor=(source,target) if source.children or curve_links.has_followers(source) else (target,source)
    if len(donor.data.splines)==1 and donor.children:
        raise ValueError('Both curves have attached children. Unlink one set before joining.')
    if keep.matrix_world.to_3x3().determinant()==0:
        raise ValueError('The keeper curve has zero scale.')
    previous=source.matrix_world.copy()
    move_curve(context,first,second)
    try:
        join(context,first,second) if keep==source else join(context,second,first)
    except ValueError:
        source.matrix_world=previous
        context.view_layer.update()
        raise


class BBE_OT_curve_start_here(bpy.types.Operator):
    bl_idname='bbe.curve_start_here'
    bl_label='Start Curve Here'
    bl_description='Choose a curve shape starting at the picked point'
    bl_options={'REGISTER','UNDO'}
    kind:bpy.props.EnumProperty(name='Curve type',items=SHAPES,default='HALF')
    start_position:bpy.props.FloatVectorProperty(size=3,options={'HIDDEN','SKIP_SAVE'})
    plane:bpy.props.StringProperty(default='XY',options={'HIDDEN','SKIP_SAVE'})
    def invoke(self,context,event):
        return context.window_manager.invoke_props_dialog(self,width=320)
    def draw(self,context):
        layout=i18n.localized_layout(self.layout)
        layout.prop(self,'kind',text='Curve')
        layout.label(text='Starts at your chosen point.',icon='SNAP_ON')
    def execute(self,context):
        from . import curve_tools
        if self.kind=='FREE':
            bpy.ops.bbe.curve_draw('INVOKE_DEFAULT',plane=self.plane,start_at_point=True,start_position=self.start_position)
        else:
            obj=curve_tools.new_curve(context,self.kind)
            obj['bbe_curve_start_at_origin']=True
            curve_tools.rebuild(obj,reset=True)
            normal=(context.region_data.view_rotation@Vector((0,0,1)) if self.plane=='VIEW' else
                    Vector({'XY':(0,0,1),'XZ':(0,1,0),'REAR':(0,-1,0),'YZ':(1,0,0)}[self.plane]))
            obj.rotation_euler=Vector((0,0,1)).rotation_difference(normal).to_euler()
            obj.location=self.start_position
            context.view_layer.update()
        return {'FINISHED'}


class BBE_MT_curve_connections(bpy.types.Menu):
    bl_idname='BBE_MT_curve_connections'
    bl_label='Curve Connections'
    def draw(self,context):
        layout=i18n.localized_layout(self.layout)
        layout.operator_context='INVOKE_DEFAULT'
        for mode,label,tip in ACTIONS:
            op=layout.operator('bbe.connect_curve_endpoints',text=label,icon={'LINE':'LINKED','MOVE':'TRANSFORM_MOVE','NEW':'GREASEPENCIL'}[mode])
            op.mode=mode


class BBE_OT_curve_connections(bpy.types.Operator):
    bl_idname='bbe.curve_connections'
    bl_label='Curve Connections'
    bl_description='Connect with a line, move a whole curve to a point, or draw from a chosen point'
    def invoke(self,context,event):
        from . import menu_surface
        getattr(getattr(bpy.ops,'bbe'),'custom_menu')('INVOKE_DEFAULT',menu='MENU:BBE_MT_curve_connections')
        return {'FINISHED'}

class BBE_OT_connect_endpoints(bpy.types.Operator):
    bl_idname = 'bbe.connect_curve_endpoints'
    bl_label = 'Connect Endpoints'
    bl_description = HELP
    bl_translation_context = 'BBEExtendedInterface'
    bl_options = {'UNDO', 'BLOCKING'}
    mode: bpy.props.EnumProperty(name='Action',items=ACTIONS,default='LINE')

    @classmethod
    def description(cls,context,properties):
        return next((tip for mode,_,tip in ACTIONS if mode==properties.mode),HELP)

    @classmethod
    def poll(cls, context):
        return context.mode == 'OBJECT' and context.area and context.area.type == 'VIEW_3D'

    def invoke(self, context, event):
        self.targets = tuple(curve_points(context) if self.mode=='NEW' else endpoints(context))
        if len(self.targets) < (1 if self.mode=='NEW' else 2):
            self.report({'INFO'}, i18n.interface('No editable curve points found.' if self.mode=='NEW' else 'Choose visible, open Bezier paths.'))
            return {'CANCELLED'}
        self.area = context.area
        self.region = next(r for r in self.area.regions if r.type == 'WINDOW')
        self.first = self.hover = None
        self.area.header_text_set(i18n.interface('Pick a curve point to start drawing. Esc cancels.' if self.mode=='NEW' else 'Pick the endpoint of the curve to move. Esc cancels.' if self.mode=='MOVE' else FIRST))
        self.handler = bpy.types.SpaceView3D.draw_handler_add(self.draw_targets, (), 'WINDOW', 'POST_PIXEL')
        context.window_manager.modal_handler_add(self)
        self.area.tag_redraw()
        return {'RUNNING_MODAL'}

    def markers(self, context):
        for key, world in self.targets:
            xy = location_3d_to_region_2d(self.region, self.region.data, world)
            if xy is not None:
                yield key, xy

    def draw_targets(self):
        context = bpy.context
        if context.region != self.region:
            return
        scale = context.preferences.system.ui_scale
        blf.size(0, 18 * scale)
        for key, xy in self.markers(context):
            color = (1, .7, .15, 1) if key in (self.first, self.hover) else (.25, 1, .85, 1)
            glyph = '●' if key == self.first else '◉'
            w, h = blf.dimensions(0, glyph)
            blf.color(0, *color)
            blf.position(0, xy.x - w / 2, xy.y - h / 2, 0)
            blf.draw(0, glyph)

    def cancel(self, context):
        bpy.types.SpaceView3D.draw_handler_remove(self.handler, 'WINDOW')
        self.area.header_text_set(None)
        self.area.tag_redraw()

    def modal(self, context, event):
        if event.type in {'ESC', 'RIGHTMOUSE'}:
            self.cancel(context)
            return {'CANCELLED'}
        if event.type not in {'MOUSEMOVE', 'LEFTMOUSE'} or event.alt:
            return {'PASS_THROUGH'}
        x = event.mouse_x - self.region.x
        y = event.mouse_y - self.region.y
        if not (0 <= x < self.region.width and 0 <= y < self.region.height):
            return {'PASS_THROUGH'}
        radius = 14 * context.preferences.system.ui_scale
        candidates = (((xy.x-x)**2 + (xy.y-y)**2, key) for key, xy in self.markers(context)
                      if not self.first or key != self.first)
        distance, key = min(candidates, default=(float('inf'), None))
        self.hover = key if distance <= radius**2 else None
        self.area.tag_redraw()
        if event.type == 'LEFTMOUSE' and event.value == 'PRESS' and self.hover:
            if self.mode=='NEW':
                world=tuple(point_position(context,self.hover))
                window,area,region=context.window,self.area,self.region
                plane=context.scene.bbe_curve_plane
                self.cancel(context)
                def begin():
                    if window not in bpy.context.window_manager.windows[:] or area not in window.screen.areas[:]:return
                    with bpy.context.temp_override(window=window,area=area,region=region):
                        bpy.ops.bbe.curve_start_here('INVOKE_DEFAULT',plane=plane,start_position=world)
                bpy.app.timers.register(begin,first_interval=.01)
                return {'FINISHED'}
            if self.first is None:
                self.first = self.hover
                if self.mode=='MOVE':
                    self.targets=((self.first,point_position(context,self.first)),)+tuple((key,world) for key,world in endpoints(context) if key[0]!=self.first[0])
                self.area.header_text_set(i18n.interface('Pick the destination endpoint. Move and join into one curve. Esc cancels.' if self.mode=='MOVE' else SECOND))
            else:
                try:
                    if self.mode=='MOVE':move_and_connect(context,self.first,self.hover)
                    else:join(context, self.first, self.hover)
                except ValueError as error:
                    self.report({'WARNING'}, i18n.interface(str(error)))
                    self.cancel(context)
                    return {'CANCELLED'}
                self.cancel(context)
                return {'FINISHED'}
        return {'RUNNING_MODAL'}

