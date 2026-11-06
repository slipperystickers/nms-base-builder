"""Colored, clickable cable sockets; independent of structural snap markers."""
import math
import bpy
import gpu
from bpy.app.handlers import persistent
from bpy_extras.view3d_utils import location_3d_to_region_2d
from gpu_extras.batch import batch_for_shader
from mathutils import Matrix, Vector
from . import cable_connections as cables

SESSIONS = {}
_index_key = None
_devices = ()
_cables = ()


def scene_index(context):
    global _index_key, _devices, _cables
    key = (context.scene.as_pointer(), len(context.scene.objects))
    if key != _index_key:
        _devices = tuple(o for o in context.scene.objects if o.get('ObjectID') and o.get('ObjectID') not in cables.KINDS
                         and (cables.local_sockets(o, cables.POWER) or cables.local_sockets(o, cables.TELEPORT)))
        _cables = tuple(o for o in context.scene.objects if o.get('ObjectID') in cables.KINDS)
        _index_key = key
    return _devices, _cables


def session(context):
    return SESSIONS.get(context.scene.as_pointer())


def redraw(context):
    for window in context.window_manager.windows:
        for area in window.screen.areas:
            if area.type == 'VIEW_3D':
                area.tag_redraw()


def cancel(context):
    previous=SESSIONS.pop(context.scene.as_pointer(), None)
    if previous and previous.get('cursor_owner'):previous['cursor_owner'].release_cursor()
    redraw(context)


def visible(context, obj):
    return obj.name in context.view_layer.objects and obj.visible_get(view_layer=context.view_layer)


def targets(context):
    """During placement: compatible sockets. Otherwise: selected connections."""
    current = session(context)
    devices, connections = scene_index(context)
    result = {}
    def add(obj, kind):
        if not visible(context, obj):
            return
        for key, position in cables.sockets(obj, kind).items():
            result[(obj.name, key, kind)] = position
    if current:
        for obj in devices:
            add(obj, current['kind'])
    else:
        selected = set(context.selected_objects)
        for obj in selected:
            if obj.get('ObjectID') not in cables.KINDS:
                for kind in cables.KINDS:
                    add(obj, kind)
        for cable in connections:
            kind = cable.get('ObjectID')
            if kind not in cables.KINDS or not visible(context, cable):
                continue
            ends = cables.endpoints(cable)
            owners = [cables.control_owner(e) if e else None for e in ends]
            if cable not in selected and not any(o in selected for o in owners) and not any(e in selected for e in ends):
                continue
            for end, owner in zip(ends, owners):
                if end is None:
                    continue
                if owner is not None and end.get('bbe_socket_key') in cables.sockets(owner, kind):
                    key = end['bbe_socket_key']
                    result[(owner.name, key, kind)] = cables.sockets(owner, kind)[key]
                else:
                    result[(end.name, '', kind)] = end.matrix_world.translation.copy()
    return [(name, key, kind, point) for (name, key, kind), point in result.items()]


class BBE_OT_cable_start(bpy.types.Operator):
    bl_idname = 'bbe.start_cable_connection'
    bl_label = 'Choose Cable Connectors'
    bl_description = 'Click two matching colored targets to connect; Escape or right-click cancels'
    bl_options = {'REGISTER'}
    kind: bpy.props.EnumProperty(items=[(cables.POWER, 'Electrical Cable', ''), (cables.TELEPORT, 'Teleport Cable', '')])

    def execute(self, context):
        if context.mode != 'OBJECT':
            self.report({'WARNING'}, 'Switch to Object Mode to connect devices.')
            return {'CANCELLED'}
        if not any(cables.local_sockets(o, self.kind) and visible(context, o) for o in context.scene.objects if o.get('ObjectID')):
            self.report({'WARNING'}, 'No visible compatible connectors. Add the devices first.')
            return {'CANCELLED'}
        cancel(context)
        SESSIONS[context.scene.as_pointer()] = {'kind': self.kind, 'first': None}
        for window in context.window_manager.windows:
            for area in window.screen.areas:
                if area.type == 'VIEW_3D':
                    area.spaces.active.show_gizmo = True
        redraw(context)
        return {'FINISHED'}

    def invoke(self, context, event):
        result = self.execute(context)
        if result == {'FINISHED'}:
            self._session=session(context);self._session['cursor_owner']=self
            self._window=context.window;self._area=context.area;self._wm=context.window_manager
            self._region=next(r for r in self._area.regions if r.type=='WINDOW')
            self._xy=None;self._cursor_hidden=False
            self._handle=bpy.types.SpaceView3D.draw_handler_add(self.draw_cursor,(),'WINDOW','POST_PIXEL')
            self._timer=self._wm.event_timer_add(.1,window=self._window)
            self.update_cursor(event)
            context.window_manager.modal_handler_add(self)
            return {'RUNNING_MODAL'}
        return result

    def release_cursor(self):
        if getattr(self,'_handle',None) is not None:
            bpy.types.SpaceView3D.draw_handler_remove(self._handle,'WINDOW');self._handle=None
        if getattr(self,'_timer',None) is not None:
            self._wm.event_timer_remove(self._timer);self._timer=None
        if getattr(self,'_cursor_hidden',False):
            self._window.cursor_modal_restore();self._cursor_hidden=False
        self._xy=None

    def update_cursor(self,event):
        r=self._region;x,y=event.mouse_x,event.mouse_y
        inside=(r.x<=x<r.x+r.width and r.y<=y<r.y+r.height
                and not any(a.type!='WINDOW' and a.x<=x<a.x+a.width and a.y<=y<a.y+a.height for a in self._area.regions))
        if inside and not self._cursor_hidden:
            self._window.cursor_modal_set('NONE');self._cursor_hidden=True
        elif not inside and self._cursor_hidden:
            self._window.cursor_modal_restore();self._cursor_hidden=False
        self._xy=(x-r.x,y-r.y) if inside else None
        self._area.tag_redraw()

    def draw_cursor(self):
        context=bpy.context
        if self._xy is None or context.area!=self._area or context.region!=self._region:return
        x,y=self._xy;radius=9*max(.75,context.preferences.system.ui_scale)
        ring=[(x+math.cos(i*math.tau/40)*radius,y+math.sin(i*math.tau/40)*radius) for i in range(41)]
        shader=gpu.shader.from_builtin('UNIFORM_COLOR');batch=batch_for_shader(shader,'LINE_STRIP',{'pos':ring})
        blend=gpu.state.blend_get();width=gpu.state.line_width_get()
        try:
            gpu.state.blend_set('ALPHA');shader.bind()
            gpu.state.line_width_set(5);shader.uniform_float('color',(.01,.02,.025,1));batch.draw(shader)
            gpu.state.line_width_set(2.5);shader.uniform_float('color',cables.COLORS[self.kind]);batch.draw(shader)
        finally:
            gpu.state.line_width_set(width);gpu.state.blend_set(blend)

    def modal(self, context, event):
        if session(context) is not self._session:
            self.release_cursor();return {'FINISHED'}
        if event.type in {'ESC', 'RIGHTMOUSE'} or context.mode != 'OBJECT':
            cancel(context);return {'CANCELLED'}
        if event.type in {'MOUSEMOVE','INBETWEEN_MOUSEMOVE','LEFTMOUSE'}:self.update_cursor(event)
        return {'PASS_THROUGH'}

    def cancel(self,context):
        if session(context) is self._session:cancel(context)
        self.release_cursor()


class BBE_OT_cable_target(bpy.types.Operator):
    bl_idname = 'bbe.click_cable_target'
    bl_label = 'Cable Connector'
    bl_options = {'REGISTER', 'UNDO'}
    owner: bpy.props.StringProperty()
    key: bpy.props.StringProperty()
    kind: bpy.props.StringProperty()

    @classmethod
    def description(cls, context, properties):
        color = 'Blue teleport' if properties.kind == cables.TELEPORT else 'Green electrical'
        return color + ' connector on ' + properties.owner

    def execute(self, context):
        obj = context.scene.objects.get(self.owner)
        if obj is None:
            cancel(context)
            return {'CANCELLED'}
        current = session(context)
        if not current:
            if not obj.hide_select:
                for selected in context.selected_objects:
                    selected.select_set(False)
                obj.select_set(True)
                context.view_layer.objects.active = obj
            return {'FINISHED'}
        if self.kind != current['kind'] or self.key not in cables.local_sockets(obj, self.kind):
            self.report({'WARNING'}, 'Choose a matching connector.')
            return {'CANCELLED'}
        first = current['first']
        if first is None:
            current['first'] = (obj, self.key)
            self.report({'INFO'}, 'First connector selected. Click the second target; Escape cancels.')
            redraw(context)
            return {'FINISHED'}
        try:
            from .builder import get_builder
            if first[0].name not in context.scene.objects:
                raise ValueError('The first device was removed. Choose the cable again.')
            cable = cables.connect(first[0], first[1], obj, self.key, self.kind, get_builder())
        except (ValueError, ReferenceError) as error:
            self.report({'WARNING'}, str(error))
            return {'CANCELLED'}
        cancel(context)
        for selected in context.selected_objects:
            selected.select_set(False)
        cable.select_set(True)
        context.view_layer.objects.active = cable
        self.report({'INFO'}, 'Teleport cable connected.' if self.kind == cables.TELEPORT else 'Electrical cable connected.')
        return {'FINISHED'}


class BBE_OT_cable_repair(bpy.types.Operator):
    bl_idname = 'bbe.repair_srt_connections'
    bl_label = 'Repair Selected SRT Connections'
    bl_description = 'Reattach existing selected SRT cables to their correct typed sockets; overlapping ambiguous devices are left unchanged'
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        count, ambiguous = cables.repair_srt(context)
        self.report({'WARNING'} if ambiguous else {'INFO'},
                    f'Reattached {count} connectors.' + (f' Left {ambiguous} ambiguous endpoints unchanged.' if ambiguous else ''))
        redraw(context)
        return {'FINISHED'}


class BBE_GT_cable_target(bpy.types.Gizmo):
    bl_idname = 'BBE_GT_cable_target'
    __slots__ = ('tint', 'chosen')

    def setup(self):
        self.tint = cables.COLORS[cables.POWER]
        self.chosen = False

    def draw(self, context):
        x, y = self.matrix_basis.translation[:2]
        radius = 15
        ring = [(x+math.cos(i*math.tau/48)*radius, y+math.sin(i*math.tau/48)*radius) for i in range(49)]
        shader = gpu.shader.from_builtin('UNIFORM_COLOR')
        gpu.state.blend_set('ALPHA')
        try:
            shader.bind()
            shader.uniform_float('color', (.015, .02, .025, .95))
            gpu.state.line_width_set(7)
            batch_for_shader(shader, 'LINE_STRIP', {'pos': ring}).draw(shader)
            shader.uniform_float('color', (1,1,1,1) if self.chosen or self.is_highlight else self.tint)
            gpu.state.line_width_set(3)
            batch_for_shader(shader, 'LINE_STRIP', {'pos': ring}).draw(shader)
            batch_for_shader(shader, 'LINES', {'pos': [(x-8,y),(x+8,y),(x,y-8),(x,y+8)]}).draw(shader)
            # Inner colored ring remains readable when the hover ring is white.
            shader.uniform_float('color', self.tint)
            inner = [(x+math.cos(i*math.tau/24)*5, y+math.sin(i*math.tau/24)*5) for i in range(25)]
            batch_for_shader(shader, 'LINE_STRIP', {'pos': inner}).draw(shader)
        finally:
            gpu.state.line_width_set(1)
            gpu.state.blend_set('NONE')

    def draw_select(self, context, select_id):
        pass

    def test_select(self, context, location):
        return 0 if (Vector(location)-Vector(self.matrix_basis.translation[:2])).length <= 19 else -1


class BBE_GGT_cable_targets(bpy.types.GizmoGroup):
    bl_idname = 'BBE_GGT_cable_targets'
    bl_label = 'Cable Connection Targets'
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'WINDOW'
    bl_options = {'PERSISTENT', 'SHOW_MODAL_ALL'}

    @classmethod
    def poll(cls, context):
        return context.mode == 'OBJECT' and bool(session(context) or any(
            o.get('ObjectID') in cables.KINDS or o.get('ObjectID') in cables.SRT_IDS or
            o.get('rig_item') or cables.local_sockets(o, cables.POWER)
            for o in context.selected_objects))

    def setup(self, context):
        self.targets = []

    def draw_prepare(self, context):
        choices = targets(context)
        while len(self.targets) < len(choices):
            gizmo = self.gizmos.new('BBE_GT_cable_target')
            gizmo.use_tooltip = True
            self.targets.append(gizmo)
        current = session(context)
        first = current['first'] if current else None
        for index, gizmo in enumerate(self.targets):
            gizmo.hide = True
            if index >= len(choices):
                continue
            name, key, kind, position = choices[index]
            point = location_3d_to_region_2d(context.region, context.region_data, position)
            if point is None or not (0 <= point.x <= context.region.width and 0 <= point.y <= context.region.height):
                continue
            gizmo.hide = False
            gizmo.tint = cables.COLORS[kind]
            try:
                gizmo.chosen = bool(first and first[0].name == name and first[1] == key)
            except ReferenceError:
                cancel(context)
                gizmo.chosen = False
            gizmo.matrix_basis = Matrix.Translation((point.x, point.y, 0))
            operator = gizmo.target_set_operator('bbe.click_cable_target')
            operator.owner, operator.key, operator.kind = name, key, kind


CLASSES = (BBE_OT_cable_start, BBE_OT_cable_target, BBE_OT_cable_repair,
           BBE_GT_cable_target, BBE_GGT_cable_targets)


@persistent
def reset(*_args):
    global _index_key, _devices, _cables
    for current in tuple(SESSIONS.values()):
        if current.get('cursor_owner'):current['cursor_owner'].release_cursor()
    SESSIONS.clear()
    _index_key, _devices, _cables = None, (), ()


def register():
    for cls in CLASSES:
        bpy.utils.register_class(cls)
    for handlers in (bpy.app.handlers.load_post, bpy.app.handlers.undo_post, bpy.app.handlers.redo_post):
        if reset not in handlers:
            handlers.append(reset)


def unregister():
    reset()
    for handlers in (bpy.app.handlers.load_post, bpy.app.handlers.undo_post, bpy.app.handlers.redo_post):
        if reset in handlers:
            handlers.remove(reset)
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)
