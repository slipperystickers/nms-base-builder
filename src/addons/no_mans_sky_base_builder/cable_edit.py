"""Direct supply-pipe roll and explicit snapping for moved cable endpoints."""
import math
import bpy
from bpy.app.handlers import persistent
from bpy_extras.view3d_utils import location_3d_to_region_2d
from mathutils import Matrix, Vector

from . import cable_connections as cables, cable_targets, i18n

def pipe_points(obj):
    a, b = cables.endpoints(obj)
    if a and b:
        return a.matrix_world.translation, b.matrix_world.translation

def pipe_selected(ctx):
    obj = ctx.active_object
    if ctx.mode == 'OBJECT' and obj and obj.select_get() and obj.get('ObjectID') == cables.SUPPLY:
        ends = cables.endpoints(obj)
        if all(ends) and all(o == obj or o in ends for o in ctx.selected_objects):
            return obj

def source(ctx):
    obj = ctx.active_object
    if ctx.mode != 'OBJECT' or not obj or not obj.get('rig_item') or len(ctx.selected_objects) != 1:
        return
    kind = obj.get('bbe_cable_kind', cables.POWER)
    if kind in cables.EDITABLE_LINES and cables.free_control(obj) and not cable_targets.session(ctx):
        return obj, 0, kind, obj.matrix_world.translation

def targets(ctx, obj, index, kind):
    devices, wires = cable_targets.scene_index(ctx)
    excluded = {obj}
    far_ends = []
    for wire in wires:
        if wire.get('ObjectID') == kind:
            ends = cables.endpoints(wire)
            if obj in ends:
                excluded.update(ends)
                far_ends.extend(end.matrix_world.translation for end in ends if end and end != obj)
    for other in devices[kind]:
        if other not in excluded and other.visible_get(view_layer=ctx.view_layer):
            for key, point in cables.sockets(other, kind).items():
                if all((end-point).length_squared > 1e-8 for end in far_ends):
                    yield other, key, point

def attach(ctx, obj, index, kind, other, key, point):
    # Resolve a bound junction to its device, and reject any dependency cycle.
    visited = {obj}
    while other.get('rig_item'):
        if other in visited:
            return False
        visited.add(other)
        parent = cables.attached_device(other)
        if parent is None:
            break
        key = other.get('bbe_socket_key')
        other = parent
    cables.bind(obj, other, key, kind)
    return True

# Limit the offer in world space so a socket behind the endpoint cannot win
# merely because it overlaps the endpoint on screen.
SNAP_DISTANCE = .18
_cache = {}
_keymaps = []

@persistent
def invalidate(*_):
    _cache.clear()

def candidate(ctx, *, fresh=False):
    src = source(ctx)
    if not src or not getattr(ctx.scene,'bbe_show_connectors',True):
        return
    obj, index, kind, position = src
    stamp = (ctx.scene.as_pointer(), ctx.view_layer.as_pointer(), obj.as_pointer(), index, tuple(position))
    if not fresh and stamp in _cache:
        return _cache[stamp]
    closest = None
    limit = SNAP_DISTANCE ** 2
    for other, key, point in targets(ctx, obj, index, kind):
        distance = (point - position).length_squared
        if distance < limit:
            closest = (obj, index, kind, other, key, point.copy())
            limit = distance
    _cache.clear()
    _cache[stamp] = closest
    return closest

class BBE_OT_attach_moved_end(bpy.types.Operator):
    bl_idname = 'bbe.attach_moved_end'
    bl_label = 'Snap Endpoint'
    bl_description = 'Attach this free end to the nearby matching socket'
    bl_options = {'UNDO', 'INTERNAL'}
    owner: bpy.props.StringProperty(options={'SKIP_SAVE'})
    socket: bpy.props.StringProperty(options={'SKIP_SAVE'})

    def execute(self, ctx):
        hit = candidate(ctx, fresh=True)
        if not hit or (hit[3].name, hit[4]) != (self.owner, self.socket):
            return {'CANCELLED'}
        ok = attach(ctx, *hit)
        invalidate()
        return {'FINISHED'} if ok else {'CANCELLED'}

class BBE_GGT_endpoint_snap(bpy.types.GizmoGroup):
    bl_idname = 'BBE_GGT_endpoint_snap'
    bl_label = 'Nearby Cable Socket'
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'WINDOW'
    bl_options = {'PERSISTENT'}

    @classmethod
    def poll(cls, ctx):
        return source(ctx) is not None

    def setup(self, ctx):
        self.button = self.gizmos.new('BBE_GT_part_button')
        self.button.use_tooltip = True

    def draw_prepare(self, ctx):
        hit = candidate(ctx)
        button = self.button
        button.hide = True
        if not hit:
            return
        pixel = location_3d_to_region_2d(ctx.region,ctx.region_data,hit[-1])
        if pixel is None:
            return
        scale = ctx.preferences.system.ui_scale
        button.hide = False
        button.label = 'Snap Endpoint'
        button.width, button.height = 122*scale, 25*scale
        button.matrix_basis = Matrix.Translation((pixel.x+20*scale,pixel.y-32*scale,0))
        op = button.target_set_operator('bbe.attach_moved_end')
        op.owner, op.socket = hit[3].name, hit[4]

def wrapped(angle):
    return (angle + math.pi) % math.tau - math.pi

class BBE_OT_roll_pipe(bpy.types.Operator):
    bl_idname = 'bbe.roll_pipe'
    bl_label = 'Roll Supply Pipe'
    bl_description = 'Turn both tubes around their span with the endpoints fixed'
    bl_options = {'UNDO', 'BLOCKING'}
    angle: bpy.props.FloatProperty(subtype='ANGLE', options={'SKIP_SAVE'})
    release_confirm: bpy.props.BoolProperty(options={'HIDDEN','SKIP_SAVE'})

    @classmethod
    def poll(cls, ctx):
        return ctx.area and ctx.area.type == 'VIEW_3D' and pipe_selected(ctx) is not None

    def execute(self, ctx):
        obj = pipe_selected(ctx)
        obj.bbe_supply_roll = wrapped(obj.bbe_supply_roll + self.angle)
        return {'FINISHED'}

    def invoke(self, ctx, event):
        self.pipe = pipe_selected(ctx)
        self.start = self.pipe.bbe_supply_roll
        self.x = event.mouse_x
        self.degrees = 0.
        self.drag_button = event.type if self.release_confirm else None
        if self.release_confirm and event.value == 'CLICK_DRAG':
            self.degrees = (event.mouse_x - event.mouse_prev_press_x) * .5
            self.pipe.bbe_supply_roll = wrapped(self.start + math.radians(self.degrees))
        self.number = ''
        ctx.window_manager.modal_handler_add(self)
        self.status(ctx)
        return {'RUNNING_MODAL'}

    def status(self, ctx):
        value = self.number or f'{self.degrees:.1f}'
        ctx.area.header_text_set(i18n.interface('Pipe roll {angle}° · Move the mouse or type an angle · Enter to confirm · Esc to cancel').format(angle=value))

    def modal(self, ctx, event):
        if event.type in {'ESC','WINDOW_DEACTIVATE'} or (event.type == 'RIGHTMOUSE' and event.type != self.drag_button):
            self.pipe.bbe_supply_roll = self.start
            ctx.area.header_text_set(None)
            return {'CANCELLED'}
        released_drag = event.type == self.drag_button and event.value == 'RELEASE'
        confirmed = event.type in {'LEFTMOUSE','RET','NUMPAD_ENTER'} and event.value == 'PRESS'
        if released_drag or confirmed:
            ctx.area.header_text_set(None)
            return {'FINISHED'}
        if event.type == 'MOUSEMOVE':
            self.degrees += (event.mouse_x - self.x) * (.05 if event.shift else .5)
            self.x = event.mouse_x
        elif event.value == 'PRESS':
            char = event.unicode
            if char and char in '0123456789.-':
                trial = self.number + char
                if trial.count('.') <= 1 and '-' not in trial[1:]:
                    self.number = trial
            elif event.type == 'BACK_SPACE':
                self.number = self.number[:-1]
        try:
            degrees = float(self.number) if self.number else self.degrees
        except ValueError:
            degrees = 0.
        self.pipe.bbe_supply_roll = wrapped(self.start + math.radians(degrees))
        self.status(ctx)
        return {'RUNNING_MODAL'}


# Blender gives builtin.rotate its own three-axis gizmo and a drag action.
# Lease only that tool's gizmo visibility, separately for each live viewport.
_rotate_spaces = {}

def using_rotate_tool(ctx):
    tool = ctx.workspace.tools.from_space_view3d_mode(ctx.mode, create=False)
    return tool is not None and tool.idname == 'builtin.rotate'

def queue_rotate_refresh():
    if not bpy.app.timers.is_registered(sync_rotate_spaces):
        bpy.app.timers.register(sync_rotate_spaces, first_interval=0.0)

def restore_rotate_space(key):
    space, area = _rotate_spaces.pop(key)
    try:
        space.show_gizmo_tool = True
        area.tag_redraw()
    except ReferenceError:
        pass  # The area may have been closed.

def sync_rotate_spaces():
    ctx = bpy.context
    active = set()
    for win in ctx.window_manager.windows:
        for area in win.screen.areas:
            if area.type != 'VIEW_3D':
                continue
            space = area.spaces.active
            region = next((r for r in area.regions if r.type == 'WINDOW'), None)
            if region is None:
                continue
            with ctx.temp_override(window=win, area=area, region=region):
                if not pipe_selected(ctx) or not using_rotate_tool(ctx):
                    continue
            key = space.as_pointer()
            active.add(key)
            if space.show_gizmo_tool:
                _rotate_spaces[key] = (space, area)
                space.show_gizmo_tool = False
                area.tag_redraw()
    for key in _rotate_spaces.keys() - active:
        restore_rotate_space(key)
    # Also release hidden or detached viewports that no longer receive draws.
    return .10 if _rotate_spaces else None

@persistent
def release_rotate_spaces(*_):
    if bpy.app.timers.is_registered(sync_rotate_spaces):
        bpy.app.timers.unregister(sync_rotate_spaces)
    for key in tuple(_rotate_spaces):
        restore_rotate_space(key)

@persistent
def refresh_after_file_event(*_):
    if not bpy.app.background:
        queue_rotate_refresh()

def rotate_handlers():
    hooks = bpy.app.handlers
    return ((hooks.save_pre, release_rotate_spaces), (hooks.save_post, refresh_after_file_event),
            (hooks.save_post_fail, refresh_after_file_event), (hooks.load_pre, release_rotate_spaces),
            (hooks.undo_pre, release_rotate_spaces), (hooks.redo_pre, release_rotate_spaces),
            (hooks.undo_post, refresh_after_file_event), (hooks.redo_post, refresh_after_file_event))

class BBE_GGT_pipe_axis(bpy.types.GizmoGroup):
    bl_idname = 'BBE_GGT_pipe_axis'
    bl_label = 'Roll Supply Pipe'
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'WINDOW'
    bl_options = {'3D','PERSISTENT','SCALE'}

    @classmethod
    def poll(cls, ctx):
        pipe = pipe_selected(ctx)
        if pipe and ctx.space_data.show_gizmo_tool and using_rotate_tool(ctx):
            queue_rotate_refresh()
        return pipe is not None

    def setup(self, ctx):
        self.dial = self.gizmos.new('GIZMO_GT_dial_3d')
        self.dial.color = (.95,.45,.08)
        self.dial.color_highlight = (1,.75,.28)
        self.dial.alpha, self.dial.alpha_highlight = .72, 1.
        self.dial.line_width = 5
        self.dial.scale_basis = 1.85
        self.dial.use_draw_value = True
        self.dial.use_undo = True
        self.owner = None

    def draw_prepare(self, ctx):
        obj = ctx.active_object
        points = pipe_points(obj)
        self.dial.hide = not points or (points[1]-points[0]).length_squared < 1e-10
        if self.dial.hide:
            return
        a,b = points
        center = (a+b)*.5
        axis = (b-a).normalized()
        view = ctx.region_data
        toward_eye = ((view.view_matrix.inverted().translation-center).normalized()
                      if view.is_perspective else view.view_rotation @ Vector((0,0,1)))
        # Give the handle a visible rim even when looking exactly across the
        # pipe. This affects the picking plane only. Roll always uses the span.
        facing = axis.dot(toward_eye)
        if abs(facing) < .32:
            projected = (axis - facing*toward_eye).normalized()
            axis = projected * math.sqrt(1-.32**2) + math.copysign(.32,facing)*toward_eye
        matrix = axis.to_track_quat('Z','Y').to_matrix().to_4x4()
        matrix.translation = center
        self.dial.matrix_basis = matrix
        if self.owner != obj:
            self.dial.target_set_prop('offset',obj,'bbe_supply_roll')
            self.owner = obj

CLASSES = (BBE_OT_roll_pipe, BBE_OT_attach_moved_end, BBE_GGT_pipe_axis, BBE_GGT_endpoint_snap)
def register():
    
    for cls in CLASSES:
        bpy.utils.register_class(cls)
    config = bpy.context.window_manager.keyconfigs.addon
    if config:
        km = config.keymaps.new(name='Object Mode',space_type='EMPTY')
        _keymaps.append((km, km.keymap_items.new('bbe.roll_pipe','R','PRESS',head=True)))
        # Mirror the built-in Rotate tool's drag fallback for selected pipes.
        # When poll fails Blender continues to the user's native transform.
        name = '3D View Tool: Rotate'
        tool_map = config.keymaps.new(name=name, space_type='VIEW_3D', tool=True)
        native = bpy.context.window_manager.keyconfigs.active.keymaps.get(name)
        if native:
            for item in native.keymap_items:
                if item.idname == 'transform.rotate' and item.active:
                    drag = tool_map.keymap_items.new_from_item(item, head=True)
                    drag.idname = 'bbe.roll_pipe'
                    drag.properties.release_confirm = True
                    _keymaps.append((tool_map, drag))
        else:
            # During startup the tool preset may not have initialized yet.
            drag = tool_map.keymap_items.new('bbe.roll_pipe', 'LEFTMOUSE', 'CLICK_DRAG', head=True)
            drag.properties.release_confirm = True
            _keymaps.append((tool_map, drag))
    for handlers, callback in rotate_handlers():
        handlers.append(callback)
    bpy.app.handlers.depsgraph_update_post.append(invalidate)
    bpy.app.handlers.load_pre.append(invalidate)
    from . import cable_clipboard
    cable_clipboard.register()

def unregister():
    from . import cable_clipboard
    cable_clipboard.unregister()
    release_rotate_spaces()
    for handlers, callback in rotate_handlers():
        if callback in handlers:
            handlers.remove(callback)
    for handlers in (bpy.app.handlers.depsgraph_update_post,bpy.app.handlers.load_pre):
        if invalidate in handlers:
            handlers.remove(invalidate)
    invalidate()
    for km, item in _keymaps:
        km.keymap_items.remove(item)
    _keymaps.clear()
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)
    
