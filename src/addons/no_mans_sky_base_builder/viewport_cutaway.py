"""World-axis clipping in the 3D viewport. Meshes and export records are untouched."""
import math

import numpy as np

import bpy
import gpu
from bpy.app.handlers import persistent
from bpy.props import BoolProperty, FloatVectorProperty, PointerProperty
from mathutils import Vector

from . import curve_widgets as paint, i18n, cutaway_materials

FULL = (0., 1.) * 3
AXES = 'XYZ'
COLORS = ((.99,.43,.41), (.53,.91,.50), (.46,.72,1.))
_saved_views = {}
_hover = {}
_drag = {}
_keys = []
_handler = None
_suspended = False
_rendering = False
_needs_recovery = False
_shaded_scenes = set()
_shaded_views = set()


def visibility_changed(state, context):
    if state.shown and getattr(context, 'visible_objects', None) is not None:
        fit(context, reset=not state.fitted)
    synchronize()
    from . import settings_memory
    settings_memory.flush()


class BBE_PG_cutaway(bpy.types.PropertyGroup):
    shown: BoolProperty(name='Viewport Cutaway', default=True, update=visibility_changed,
                        description='Show the XYZ sliders and use the current cutaway')
    slicing: BoolProperty(default=True)
    fitted: BoolProperty(default=False)
    hull_fitted: BoolProperty(default=False)
    bounds: FloatVectorProperty(size=6, default=(-1., 1.) * 3)
    handles: FloatVectorProperty(size=6, min=0., max=1., default=FULL)


def build_bounds(context):
    """Measure visible hull vertices. Box bounds only prune candidates for each extreme."""
    def belongs(obj):
        while obj:
            if any(key in obj for key in ('ObjectID', 'GroupID', 'station_reference_only', 'nms_station_reference')):
                return True
            obj = obj.parent
        return False

    visible = {o.as_pointer() for o in context.visible_objects}
    build, fallback = [], []
    for instance in context.evaluated_depsgraph_get().object_instances:
        obj = instance.object
        owner = instance.parent if instance.is_instance else obj
        if (owner.original.as_pointer() not in visible or obj.type != 'MESH' or
                not instance.show_self or not len(obj.data.vertices)):
            continue
        if any(obj.get(tag) or owner.get(tag) for tag in
               ('bbe_boundary', 'bbe_stage_owned', 'bbe_asset_browser_pin')):
            continue
        matrix = np.array(instance.matrix_world)
        box = obj.bound_box
        a, b = np.array(box[0]), np.array(box[6])
        center = matrix[:3,:3] @ ((a+b)*.5) + matrix[:3,3]
        radius = np.abs(matrix[:3,:3]) @ (np.abs(b-a)*.5)
        row = (center-radius, center+radius, obj.data, matrix)
        (build if belongs(owner) or belongs(obj) else fallback).append(row)
    rows = build or fallback
    if not rows:
        return None
    vertices = {}
    result = []
    for axis in range(3):
        for upper in (False, True):
            sign = 1 if upper else -1
            side = int(upper)
            best = -math.inf
            for row in sorted(rows, key=lambda row: row[side][axis], reverse=upper):
                _, _, mesh, matrix = row
                if sign*row[side][axis] <= best:
                    break
                key = mesh.as_pointer()
                if key not in vertices:
                    coords = np.empty((len(mesh.vertices), 3), dtype=np.float32)
                    mesh.vertices.foreach_get('co', coords.ravel())
                    vertices[key] = coords
                projection = np.einsum('ij,j->i', vertices[key], matrix[axis,:3])
                extreme = projection.max() if upper else projection.min()
                best = max(best, sign*(float(extreme)+matrix[axis,3]))
            result.append(sign*best)
    return result


def fit(context, reset=True):
    state = context.scene.bbe_cutaway
    bounds = build_bounds(context)
    state.fitted = bounds is not None
    state.hull_fitted = state.fitted
    if bounds is not None:
        state.bounds = bounds
    if reset:
        state.handles = FULL


def clear_build(scene):
    state = getattr(scene, 'bbe_cutaway', None)
    if state and (state.fitted or state.shown):
        state.fitted = False
        state.handles = FULL
        _drag.pop(scene.session_uid, None)
        synchronize()


def handle_values(scene):
    temporary = _drag.get(scene.session_uid)
    return temporary if temporary is not None else scene.bbe_cutaway.handles[:]


def limits(scene):
    space = bpy.context.space_data
    if space and space.type == 'VIEW_3D' and getattr(bpy.context.region_data, 'use_box_clip', False):
        return None
    return scene_limits(scene)


def scene_limits(scene):
    state = getattr(scene, 'bbe_cutaway', None)
    if not state or not state.shown or not state.slicing or not state.fitted:
        return None
    values = handle_values(scene)
    if tuple(values) == FULL:
        return None
    bounds = state.bounds[:]
    return tuple(None if value == FULL[j] else
                 bounds[j & ~1] + value*(bounds[j | 1]-bounds[j & ~1])
                 for j,value in enumerate(values))


def contains(cuts, point):
    return cuts is None or all((cuts[2*i] is None or v >= cuts[2*i]) and
                               (cuts[2*i+1] is None or v <= cuts[2*i+1])
                               for i,v in enumerate(point))


def ray_segment(cuts, origin, direction, distance=1.7e38):
    """Restrict a world-space picking ray to the visible half-spaces."""
    start, end = 0., distance
    if cuts is not None:
        for j, coordinate in enumerate(cuts):
            if coordinate is None:
                continue
            axis = j//2
            sign = -1 if j%2 else 1
            inward = direction[axis]*sign
            offset = (coordinate-origin[axis])*sign
            if abs(inward) < 1e-12:
                if offset > 0:
                    return None
            elif inward > 0:
                start = max(start, offset/inward)
            else:
                end = min(end, offset/inward)
            if end < start:
                return None
    return (origin+direction*start if start else origin), end-start


def scene_pick(scene, graph, origin, direction, distance=1.7e38):
    ray = ray_segment(limits(scene), origin, direction, distance)
    if ray is None:
        return False, None, None, -1, None, None
    return scene.ray_cast(graph, ray[0], direction, distance=ray[1])


def equations(cuts):
    result = []
    for j, coordinate in enumerate(cuts):
        plane = [0.,0.,0.,1.]  # An untouched end admits every world coordinate.
        if coordinate is not None:
            sign = 1. if j%2 == 0 else -1.
            plane[j//2] = sign
            plane[3] = -coordinate*sign
        result.append(plane)
    return result


def views(space):
    return tuple(space.region_quadviews) or (space.region_3d,)


def restore(view, override=None):
    record = _saved_views.pop(view.as_pointer(), None)
    if record is None:
        return
    original_enabled, original_planes, _, owned = record
    if owned and override:
        # INVOKE releases the native bounding box when clipping is already on.
        with bpy.context.temp_override(**override):
            # In newer Blender versions this operator is unavailable in
            # Material Preview. Restore the RNA settings in either case.
            if bpy.ops.view3d.clip_border.poll():
                view.use_clip_planes = True
                bpy.ops.view3d.clip_border('INVOKE_DEFAULT')
    view.clip_planes = original_planes
    view.use_clip_planes = original_enabled


def apply_view(scene, view, cuts, override):
    key = view.as_pointer()
    if not scene.bbe_cutaway.shown:
        restore(view, override)
        return
    record = _saved_views.get(key)
    desired = (scene.session_uid, cuts)
    if record and record[2] == desired:
        return
    if record is None:
        record = (view.use_clip_planes, tuple(map(tuple, view.clip_planes)), None, False)
    original_enabled, original_planes, _, owned = record
    if cuts is not None:
        if not owned and not original_enabled:
            # Blender requires a native bounding box as well as six plane equations.
            with bpy.context.temp_override(**override):
                # The native background pass draws this box using the theme border
                # colour. A point supplies the required allocation without a visible face.
                bpy.ops.view3d.clip_border('EXEC_DEFAULT', xmin=0, ymin=0, xmax=0, ymax=0)
            owned = True
        view.clip_planes = equations(cuts)
    view.use_clip_planes = cuts is not None
    if cuts is not None and record[2] and record[2][1] is not None:
        # Workbench caches completed AA samples. Updated equations alone do
        # not invalidate them. Tag the scene once, without touching part meshes.
        scene.update_tag(refresh={'TIME'})
    _saved_views[key] = (original_enabled, original_planes, desired, owned)


def active_views():
    for window in bpy.context.window_manager.windows:
        for area in window.screen.areas:
            if area.type != 'VIEW_3D':
                continue
            for region in area.regions:
                if region.type == 'WINDOW' and region.data:
                    yield window, area, region, region.data


def synchronize():
    global _needs_recovery
    if _suspended:
        return
    if _needs_recovery:
        _needs_recovery = False
        cutaway_materials.recover()
    shaded = set()
    current_views = set()
    for window, area, region, view in active_views():
        space = area.spaces.active
        state = window.scene.bbe_cutaway
        if state.shown and state.fitted and not state.hull_fitted:
            # Older .blend files stored padded object-box bounds. Preserve their handles.
            with bpy.context.temp_override(window=window, area=area, region=region):
                fit(bpy.context, reset=False)
        if view.use_box_clip:
            # Blender owns these four linked side-view planes in synchronized quad view.
            restore(view, dict(window=window, area=area, region=region))
            continue
        cuts = scene_limits(window.scene)
        if state.shown and space.shading.type in {'MATERIAL', 'RENDERED'}:
            current_views.add(view.as_pointer())
            if cuts or (state.fitted and window.scene in _shaded_scenes):
                shaded.add(window.scene)
        override = dict(window=window, area=area, region=region)
        if view.as_pointer() in current_views:
            # Eevee and Cycles use the material mask. Creating a Workbench clip
            # region here needlessly restarts viewport accumulation.
            restore(view, override)
        else:
            apply_view(window.scene, view, cuts, override)
        area.tag_redraw()
    _shaded_views.clear()
    _shaded_views.update(current_views)
    if shaded:
        if shaded != _shaded_scenes:
            cutaway_materials.dirty()
        for scene in _shaded_scenes - shaded:
            cutaway_materials.set_bounds(scene, None)
        cutaway_materials.prepare(shaded)
        for scene in shaded:
            cutaway_materials.set_bounds(scene, scene_limits(scene))
    elif _shaded_scenes:
        cutaway_materials.clear()
    _shaded_scenes.clear()
    _shaded_scenes.update(shaded)


@persistent
def scene_updated(scene, graph):
    if not _suspended and scene in _shaded_scenes and any(
            graph.id_type_updated(kind) for kind in ('OBJECT', 'MESH', 'MATERIAL', 'COLLECTION')):
        cutaway_materials.dirty()
        queue_sync()


def queue_sync():
    if not _suspended and not bpy.app.timers.is_registered(synchronize):
        bpy.app.timers.register(synchronize, first_interval=0.)


@persistent
def suspend(*_):
    global _suspended
    _suspended = True
    if bpy.app.timers.is_registered(synchronize):
        bpy.app.timers.unregister(synchronize)
    if _saved_views:
        for window, area, region, view in active_views():
            restore(view, dict(window=window, area=area, region=region))
        for screen in bpy.data.screens:
            for area in screen.areas:
                for space in area.spaces:
                    if space.type == 'VIEW_3D':
                        for view in views(space):
                            if view:
                                restore(view)
    _shaded_scenes.clear()
    _shaded_views.clear()
    cutaway_materials.clear()
    _saved_views.clear()
    _hover.clear()
    _drag.clear()


@persistent
def resume(*_):
    global _suspended, _needs_recovery
    if _rendering:
        return
    _suspended = False
    _needs_recovery = not _shaded_scenes
    queue_sync()


@persistent
def after_save(*_):
    # Restore the complete view in the save callback before Blender can display
    # an intermediate frame between the clean file write and the next UI timer.
    global _suspended, _needs_recovery
    if not _rendering:
        _suspended = False
        _needs_recovery = False
        synchronize()


@persistent
def render_begin(*_):
    global _rendering
    _rendering = True
    suspend()


@persistent
def render_end(*_):
    global _rendering
    _rendering = False
    resume()


class BBE_OT_cutaway_controls(bpy.types.Operator):
    bl_idname = 'bbe.cutaway_controls'
    bl_label = 'Viewport Cutaway'
    bl_translation_context = i18n.CONTEXT
    bl_description = 'Show the X, Y and Z sliders for cutting away the viewport'
    refit: BoolProperty(default=False, options={'SKIP_SAVE'})

    def execute(self, context):
        state = context.scene.bbe_cutaway
        if self.refit:
            fit(context)
            state.slicing = True
        else:
            state.shown = not state.shown
        synchronize()
        return {'FINISHED'}


def draw_menu(layout, context):
    state = context.scene.bbe_cutaway
    row = layout.row(align=True)
    row.prop(state, 'shown', text='Viewport Cutaway', toggle=True,
             icon='CHECKBOX_HLT' if state.shown else 'CHECKBOX_DEHLT')
    if state.shown:
        row.operator('bbe.cutaway_controls', text='Refit to Build', icon='FULLSCREEN_ENTER').refit = True


def geometry(context):
    region = context.region
    s = context.preferences.system.ui_scale
    left, right, bottom = 0., float(region.width), 0.
    for other in context.area.regions:
        if other.width <= 1 or other.height <= 1:
            continue
        x, y = other.x-region.x, other.y-region.y
        if other.type == 'UI' and context.space_data.show_region_ui and x+other.width > 0 and x < right:
            right = min(right, max(0., x))
        elif other.type == 'TOOLS' and context.space_data.show_region_toolbar and x <= 0:
            left = max(left, x+other.width)
        elif other.type in {'HEADER','TOOL_HEADER','ASSET_SHELF','ASSET_SHELF_HEADER'} and y <= region.height*.5:
            bottom = max(bottom, y+other.height)
    width = right-left
    if width < 150*s or region.height-bottom < 105*s:
        return None
    bx,by = right-58*s,bottom+23*s
    length = min(166*s, (width-119*s)/2)
    z_length = min(158*s,region.height-bottom-75*s)
    gap = 28*s
    end = bx-59*s
    return ((end-2*length-gap,by,length,0.), (end-length,by,length,0.),
            (bx,by+29*s,0.,z_length)), (bx-47*s,by-12*s,94*s,24*s)


def hit_test(layout, values, x, y, scale):
    if layout is None:
        return None
    rails, (bx,by,w,h) = layout
    if bx <= x <= bx+w and by <= y <= by+h:
        return 6
    for i,(rx,ry,dx,dy) in enumerate(rails):
        along, cross, length = (x-rx,y-ry,dx) if dx else (y-ry,x-rx,dy)
        if -7*scale <= along <= length+7*scale and abs(cross) <= 12*scale:
            mid = (values[2*i]+values[2*i+1])*.5*length
            return 2*i+int(along>mid)
    return None


def draw():
    context = bpy.context
    if _suspended or not context.region_data or not context.scene:
        return
    state = context.scene.bbe_cutaway
    if context.region_data.use_box_clip:
        return
    view_id = context.region_data.as_pointer()
    record = _saved_views.get(view_id)
    shaded = state.shown and context.space_data.shading.type in {'MATERIAL', 'RENDERED'}
    if ((view_id in _shaded_views) != shaded or
            state.shown and not shaded and (record is None or record[2] != (context.scene.session_uid, limits(context.scene))) or
            not state.shown and record):
        queue_sync()
    if not state.shown:
        return
    layout = geometry(context)
    if layout is None:
        return
    rails, (bx,by,w,h) = layout
    s = context.preferences.system.ui_scale
    hot = _hover.get(view_id)
    values = handle_values(context.scene)
    shader = gpu.shader.from_builtin('UNIFORM_COLOR')
    with paint.canvas(context):
        for i,(x,y,dx,dy) in enumerate(rails):
            vertical = not dx
            active = hot in (2*i,2*i+1)
            alpha = .99 if active else .28
            tint = (*COLORS[i],alpha)
            lo,hi = values[i*2:i*2+2]
            paint.rounded(shader,x-4*s,y-4*s,dx+8*s,dy+8*s,4*s,(.07,.08,.10,.77 if active else .20))
            paint.rounded(shader,x+dx*lo-s,y+dy*lo-s,dx*(hi-lo)+2*s,dy*(hi-lo)+2*s,s,tint)
            for f in (lo,hi):
                hw,hh = (7*s,4*s) if vertical else (4*s,7*s)
                paint.rounded(shader,x+dx*f-hw,y+dy*f-hh,2*hw,2*hh,2*s,tint)
            paint.text(AXES[i],x-(0 if vertical else 12)*s,y+(dy+9*s if vertical else -4*s),11*s,tint,'CENTER')
        alpha = 1. if hot==6 else .74
        paint.rounded(shader,bx,by,w,h,8*s,(.11,.16,.18,alpha))
        on = state.slicing
        msg = i18n.interface('Slice on' if on else 'Slice off')
        track = (.17,.51,.31,alpha) if on else (.36,.37,.39,alpha)
        paint.rounded(shader,bx+5*s,by+5*s,28*s,14*s,7*s,track)
        paint.disc(shader,bx+(26 if on else 12)*s,by+12*s,5*s,(.98,.98,.98,alpha))
        label_x = bx+(w+28*s)/2
        paint.text(msg,label_x,by+7*s,11*s,(.96,.98,1.,alpha),'CENTER')


class BBE_OT_cutaway_pick(bpy.types.Operator):
    """Route an ordinary object click through geometry discarded by the material shader."""
    bl_idname = 'bbe.cutaway_pick'
    bl_label = 'Select Inside Cutaway'
    bl_options = {'INTERNAL', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return (context.mode == 'OBJECT' and BBE_OT_cutaway_input.poll(context)
                and context.space_data.shading.type in {'MATERIAL', 'RENDERED'}
                and scene_limits(context.scene) is not None)

    def invoke(self, context, event):
        from bpy_extras import view3d_utils
        from . import asset_strip, menu_surface, toolbar_surface
        if toolbar_surface.over_header(context.area, event):
            return {'PASS_THROUGH'}
        x, y = event.mouse_region_x, event.mouse_region_y
        strip = asset_strip._states.get(asset_strip.key(context))
        if strip and strip.get('enabled'):
            surfaces = (strip.get('bounds'), strip.get('choice') and strip.get('choice_bounds'))
            if any(rect and asset_strip.inside(rect, x, y) for rect in surfaces) and asset_strip.visible(context):
                return {'PASS_THROUGH'}
        if (context.area.as_pointer() in menu_surface._sessions or
                hit_test(geometry(context), handle_values(context.scene), x, y,
                         context.preferences.system.ui_scale) is not None):
            return {'PASS_THROUGH'}
        tool = context.workspace.tools.from_space_view3d_mode(context.mode)
        if tool and not (tool.idname.startswith('builtin.select') or tool.idname in
                         {'builtin.move', 'builtin.rotate', 'builtin.scale', 'builtin.transform'}):
            return {'PASS_THROUGH'}
        region, view = context.region, context.region_data
        origin = view3d_utils.region_2d_to_origin_3d(region, view, (x,y))
        direction = view3d_utils.region_2d_to_vector_3d(region, view, (x,y))
        scene = context.scene
        graph = context.evaluated_depsgraph_get()
        raw = scene.ray_cast(graph, origin, direction)
        if not raw[0] or contains(scene_limits(scene), raw[1]):
            return {'PASS_THROUGH'}
        hit = scene_pick(scene, graph, origin, direction)
        obj = hit[4] if hit[0] else None
        if obj and (obj.hide_select or not obj.visible_get(view_layer=context.view_layer,
                                                           viewport=context.space_data)):
            obj = None
        if not event.shift:
            for selected in context.selected_objects:
                if selected != obj:
                    selected.select_set(False)
        if obj:
            selected = not (event.shift and obj.select_get() and context.active_object == obj)
            obj.select_set(selected)
            if selected:
                context.view_layer.objects.active = obj
        elif not event.shift:
            context.view_layer.objects.active = None
        return {'FINISHED'}


class BBE_OT_cutaway_input(bpy.types.Operator):
    bl_idname = 'bbe.cutaway_input'
    bl_label = 'Adjust Viewport Cutaway'
    bl_options = {'INTERNAL'}

    @classmethod
    def poll(cls, context):
        return (context.area and context.area.type=='VIEW_3D' and context.region and
                context.region.type=='WINDOW' and context.region_data and not context.region_data.use_box_clip and
                context.scene.bbe_cutaway.shown)

    def invoke(self, context, event):
        from . import menu_surface
        key = context.region_data.as_pointer()
        x,y = event.mouse_x-context.region.x,event.mouse_y-context.region.y
        values = handle_values(context.scene)
        layout = geometry(context)
        hit = None if context.area.as_pointer() in menu_surface._sessions else hit_test(
            layout, values, x, y, context.preferences.system.ui_scale)
        if _hover.get(key) != hit:
            _hover[key] = hit
            context.area.tag_redraw()
        if event.type != 'LEFTMOUSE' or hit is None:
            return {'PASS_THROUGH'}
        state = context.scene.bbe_cutaway
        if hit == 6:
            state.slicing = not state.slicing
            synchronize()
            return {'FINISHED'}
        if not state.fitted:
            fit(context)
            if not state.fitted:
                self.report({'INFO'}, 'Load a build to fit the cutaway sliders')
                return {'CANCELLED'}
            values = handle_values(context.scene)
        self.scene_id = context.scene.session_uid
        if self.scene_id in _drag:
            return {'CANCELLED'}
        self.index = hit
        self.was_on = state.slicing
        self.view_key = key
        self.area = context.area
        self.region = context.region
        rx,ry,dx,dy = layout[0][hit//2]
        pos = (x-rx)/dx if dx else (y-ry)/dy
        self.offset = pos-values[hit] if abs(pos-values[hit])*(dx or dy)<=8*context.preferences.system.ui_scale else 0.
        _drag[self.scene_id] = list(values)
        self.move(context,event)
        context.window_manager.modal_handler_add(self)
        return {'RUNNING_MODAL'}

    def move(self, context, event):
        layout = geometry(context)
        if layout is None:
            return
        rx,ry,dx,dy = layout[0][self.index//2]
        fraction = ((event.mouse_x-self.region.x-rx)/dx if dx else (event.mouse_y-self.region.y-ry)/dy)-self.offset
        # A subpixel difference should never leave an apparently open end clipping.
        pixel = 1. / max(1., dx or dy)
        if fraction <= pixel:
            fraction = 0.
        elif fraction >= 1. - pixel:
            fraction = 1.
        values = _drag[self.scene_id]
        j = self.index
        gap = .001
        f = min(1.,max(values[j-1]+gap,fraction)) if j%2 else max(0.,min(values[j+1]-gap,fraction))
        if f != values[j]:
            values[j] = f
            synchronize()

    def finish(self,context,commit):
        values = _drag.pop(self.scene_id,None)
        if values is not None and context.scene.session_uid == self.scene_id:
            state = context.scene.bbe_cutaway
            if commit:
                state.handles = values
            else:
                state.slicing = self.was_on
        _hover.pop(self.view_key,None)
        synchronize()

    def modal(self,context,event):
        if (self.scene_id not in _drag or context.scene.session_uid != self.scene_id or
                context.area != self.area or not context.scene.bbe_cutaway.shown or
                event.type in {'ESC','RIGHTMOUSE','WINDOW_DEACTIVATE'}):
            self.finish(context,False)
            return {'CANCELLED'}
        if event.type == 'MOUSEMOVE':
            self.move(context,event)
        elif event.type=='LEFTMOUSE' and event.value=='RELEASE':
            self.move(context,event)
            self.finish(context,True)
            return {'FINISHED'}
        return {'RUNNING_MODAL'}

    def cancel(self,context):
        self.finish(context,False)


_CLASSES = (BBE_PG_cutaway, BBE_OT_cutaway_controls, BBE_OT_cutaway_input, BBE_OT_cutaway_pick)
_EVENTS = ((bpy.app.handlers.depsgraph_update_post,scene_updated),
           (bpy.app.handlers.render_init,render_begin),(bpy.app.handlers.render_complete,render_end),
           (bpy.app.handlers.render_cancel,render_end),(bpy.app.handlers.save_pre,suspend),(bpy.app.handlers.save_post,after_save),
           (bpy.app.handlers.save_post_fail,after_save),(bpy.app.handlers.load_pre,suspend),
           (bpy.app.handlers.load_post,resume),(bpy.app.handlers.load_post_fail,resume),
           (bpy.app.handlers.undo_pre,suspend),(bpy.app.handlers.undo_post,resume),
           (bpy.app.handlers.redo_pre,suspend),(bpy.app.handlers.redo_post,resume))


def register():
    global _handler
    for cls in _CLASSES:
        bpy.utils.register_class(cls)
    bpy.types.Scene.bbe_cutaway = PointerProperty(type=BBE_PG_cutaway)
    for handlers, callback in _EVENTS:
        handlers.append(callback)
    _handler = bpy.types.SpaceView3D.draw_handler_add(draw, (), 'WINDOW', 'POST_PIXEL')
    config = bpy.context.window_manager.keyconfigs.addon
    if config:
        km = config.keymaps.new(name='3D View',space_type='VIEW_3D',region_type='WINDOW')
        for event in ('MOUSEMOVE','LEFTMOUSE'):
            item = km.keymap_items.new(BBE_OT_cutaway_input.bl_idname,event,'ANY' if event=='MOUSEMOVE' else 'PRESS',head=True)
            _keys.append((km,item))
        prefs = bpy.context.window_manager.keyconfigs.active.preferences
        select_mouse = getattr(prefs, 'select_mouse', 'LEFT') + 'MOUSE'
        for extend in (False, True):
            item = km.keymap_items.new(BBE_OT_cutaway_pick.bl_idname, select_mouse, 'PRESS',
                                       shift=extend, head=True)
            _keys.append((km, item))
    resume()


def unregister():
    suspend()
    for km,item in _keys:
        km.keymap_items.remove(item)
    _keys.clear()
    bpy.types.SpaceView3D.draw_handler_remove(_handler,'WINDOW')
    for handlers, callback in _EVENTS:
        handlers.remove(callback)
    del bpy.types.Scene.bbe_cutaway
    for cls in reversed(_CLASSES):
        bpy.utils.unregister_class(cls)

