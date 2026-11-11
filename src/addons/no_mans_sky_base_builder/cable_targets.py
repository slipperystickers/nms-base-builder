"""Colored, clickable cable sockets; independent of structural snap markers."""
import math
from collections import defaultdict
import bpy
import gpu
from bpy.app.handlers import persistent
from bpy_extras.view3d_utils import location_3d_to_region_2d, region_2d_to_location_3d
from gpu_extras.batch import batch_for_shader
from mathutils import Matrix, Vector
from . import cable_connections as cables

SESSIONS = {}
_index_key = None
_devices = {}
_cables = ()


def scene_index(context):
    global _index_key, _devices, _cables
    key = (context.scene.as_pointer(), len(context.scene.objects))
    if key != _index_key:
        _devices = {kind: [] for kind in cables.KINDS}
        _cables = []
        for obj in context.scene.objects:
            pid = obj.get('ObjectID')
            if pid in cables.KINDS:
                _cables.append(obj)
            elif pid:
                for kind in cables.KINDS:
                    if cables.local_sockets(obj, kind):
                        _devices[kind].append(obj)
            elif obj.get('rig_item') and not obj.get('bbe_socket_key'):
                kind = obj.get('bbe_cable_kind', cables.POWER)
                if kind in cables.KINDS:
                    _devices[kind].append(obj)
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
    try:
        return obj.name in context.view_layer.objects and obj.visible_get(view_layer=context.view_layer)
    except ReferenceError:
        return False


def allowed_target(current, obj):
    if obj in current.get('excluded_devices', ()):
        return False
    if 'source' in current:
        if current['first'] is None:
            return obj == current['source']
        return obj != current['source']
    if 'remaining' not in current:
        return True
    if current['first'] is None and current['active'] is not None:
        return obj.name == current['active']
    return obj.name in current['remaining']


def targets(context):
    """During placement: compatible sockets. Otherwise: selected connections."""
    current = session(context)
    if current and 'source' in current and current['first'] is None:
        devices = (current['source'],)
    elif current and 'remaining' in current:
        names = ((current['active'],) if current['first'] is None and current['active'] is not None
                 else current['remaining'])
        devices = (obj for name in names if (obj := context.scene.objects.get(name)) is not None)
    else:
        by_kind, connections = scene_index(context)
        devices = by_kind[current['kind']] if current else ()
    result = {}
    def add(obj, kind):
        if not visible(context, obj):
            return
        for key, position in cables.sockets(obj, kind).items():
            result[(obj.name, key, kind)] = position
    if current:
        for obj in devices:
            if obj.get('rig_item') and obj.get('bbe_socket_key') and 'remaining' not in current:
                continue
            if allowed_target(current, obj):
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
                    result[(end.name, 'ENDPOINT', kind)] = end.matrix_world.translation.copy()
    return [(name, key, kind, point) for (name, key, kind), point in result.items()]


def start_position(context, current):
    first = current['first']
    if first is None:
        return None
    owner = first[0]
    if owner is None:
        return current['first_local']
    if visible(context, owner):
        return owner.matrix_world @ current['first_local']
    return None


class BBE_OT_cable_start(bpy.types.Operator):
    bl_idname = 'bbe.start_cable_connection'
    bl_label = 'Choose Cable Connectors'
    bl_description = 'Click two matching colored targets to connect; Escape or right-click cancels'
    bl_options = {'REGISTER'}
    kind: bpy.props.EnumProperty(items=[(cables.POWER, 'Electrical Cable', ''), (cables.TELEPORT, 'Teleport Cable', ''),
                                      (cables.BYTEBEAT, 'ByteBeat Cable', '')])

    new_point: bpy.props.BoolProperty(options={'SKIP_SAVE', 'HIDDEN'})
    source_name: bpy.props.StringProperty(options={'SKIP_SAVE', 'HIDDEN'})
    source_key: bpy.props.StringProperty(options={'SKIP_SAVE', 'HIDDEN'})
    group_power: bpy.props.BoolProperty(options={'SKIP_SAVE', 'HIDDEN'})
    chain: bpy.props.BoolProperty(options={'SKIP_SAVE', 'HIDDEN'})
    repeat_placement: bpy.props.BoolProperty(options={'SKIP_SAVE', 'HIDDEN'})
    selected_only: bpy.props.BoolProperty(default=False, options={'SKIP_SAVE', 'HIDDEN'})

    @classmethod
    def description(cls, context, properties):
        if properties.repeat_placement:
            return 'Click a start and an end for each cable. Esc or right-click exits placement.'
        if properties.new_point:
            return 'Click a cable to insert a junction or click empty space to start a path.'
        if properties.source_name:
            return f'Start a {cables.LABELS.get(properties.kind, "device")} cable here and click its destination.'
        if properties.kind in (cables.POWER, cables.BYTEBEAT):
            return 'Click sockets or empty space to place both ends of the cable.'
        return cls.bl_description

    def execute(self, context):
        if context.mode != 'OBJECT':
            self.report({'WARNING'}, 'Switch to Object Mode to connect devices.')
            return {'CANCELLED'}
        if self.new_point and self.kind == cables.TELEPORT:
            return {'CANCELLED'}
        source = None
        if self.source_name:
            source = context.active_object
            if (source is None or source.name != self.source_name or not source.select_get()
                    or not visible(context, source)):
                self.report({'WARNING'}, 'Select the device to start wiring.')
                return {'CANCELLED'}
            keys = cables.local_sockets(source, self.kind)
            if self.source_key:
                keys = {self.source_key: keys[self.source_key]} if self.source_key in keys else {}
            if not keys:
                self.report({'WARNING'}, f'This device has no {cables.LABELS[self.kind]} sockets.')
                return {'CANCELLED'}
        elif self.kind == cables.TELEPORT and not any(visible(context, obj) for obj in scene_index(context)[0][self.kind]):
            self.report({'WARNING'}, 'No visible compatible connectors. Add the devices first.')
            return {'CANCELLED'}
        cancel(context)
        SESSIONS[context.scene.as_pointer()] = {'kind': self.kind, 'first': None, 'new_point': self.new_point,
                                               'repeat': self.repeat_placement}
        if source is not None:
            current = session(context)
            current['source'] = source
            if len(keys) == 1:
                key, position = next(iter(keys.items()))
                current['first'] = (source, key)
                current['first_local'] = position
                self.report({'INFO'}, 'Click a pink socket or empty space to finish.' if self.kind == cables.BYTEBEAT
                            else 'Start socket selected. Click a destination connector.')
            else:
                self.report({'INFO'}, 'Click a starting connector on the selected device.')
        elif self.group_power:
            devices = cables.power_devices(context.selected_objects)
            if (self.kind != cables.POWER or len(devices) < 2
                    or not all(cables.local_sockets(device, self.kind) for device in devices)):
                cancel(context)
                return {'CANCELLED'}
            session(context).update(devices=devices, chain=self.chain)
            self.report({'INFO'}, 'Choose a power source or starting position.')
        elif self.selected_only:
            active = context.active_object
            selected = context.selected_objects
            if active not in selected or len(selected) < 2 or not all(cables.local_sockets(o, self.kind) for o in selected):
                cancel(context)
                return {'CANCELLED'}
            current = session(context)
            if self.chain:
                current.update(active=None, remaining={o.name for o in selected}, chain=True)
                self.report({'INFO'}, 'Click the starting socket, then a socket on the next device.')
            else:
                current.update(active=active.name, remaining={o.name for o in selected if o != active})
                keys = cables.local_sockets(active, self.kind)
                if len(keys) == 1:
                    key, position = next(iter(keys.items()))
                    current.update(first=(active, key), first_local=position)
                self.report({'INFO'}, 'Click a connector on each selected device.' if current['first']
                            else 'Click the starting connector on the active device.')
        elif self.new_point:
            self.report({'INFO'}, 'Click a cable to insert a junction or empty space to place a starting point.')
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
            if self.repeat_placement:
                self._workspace = context.workspace
                self._workspace_tool = self.workspace_tool(context)
                self._scene_key = context.scene.as_pointer()
            self._xy=None;self._cursor_hidden=False
            self._cursor_shader = None
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
        self._cursor_shader = self._ring_batch = self._wire_batch = None

    def update_cursor(self,event):
        r=self._region;x,y=event.mouse_x,event.mouse_y
        inside=(r.x<=x<r.x+r.width and r.y<=y<r.y+r.height
                and not any(a.type!='WINDOW' and a.x<=x<a.x+a.width and a.y<=y<a.y+a.height for a in self._area.regions))
        if inside and not self._cursor_hidden:
            self._window.cursor_modal_set('NONE');self._cursor_hidden=True
        elif not inside and self._cursor_hidden:
            self._window.cursor_modal_restore();self._cursor_hidden=False
        xy = (x-r.x, y-r.y) if inside else None
        if xy != self._xy:
            self._xy = xy
            self._area.tag_redraw()

    def draw_cursor(self):
        context = bpy.context
        if self._xy is None or context.area != self._area or context.region != self._region:
            return
        if self._cursor_shader is None:
            self._cursor_shader = gpu.shader.from_builtin('UNIFORM_COLOR')
            circle = [(math.cos(i*math.tau/40), math.sin(i*math.tau/40)) for i in range(41)]
            self._ring_batch = batch_for_shader(self._cursor_shader, 'LINE_STRIP', {'pos': circle})
            self._wire_batch = batch_for_shader(self._cursor_shader, 'LINES', {'pos': [(0,0), (1,0)]})

        x, y = self._xy
        scale = max(.75, context.preferences.system.ui_scale)
        shader = self._cursor_shader
        blend = gpu.state.blend_get()
        width = gpu.state.line_width_get()
        try:
            gpu.state.blend_set('ALPHA')
            shader.bind()
            socket = start_position(context, self._session)
            if socket is not None:
                start = location_3d_to_region_2d(self._region, context.region_data, socket)
                if start is not None:
                    dx, dy = x - start.x, y - start.y
                    # Transform a reusable unit line into the current screen segment.
                    with gpu.matrix.push_pop():
                        gpu.matrix.multiply_matrix(Matrix(((dx, -dy, 0, start.x), (dy, dx, 0, start.y),
                                                           (0, 0, 1, 0), (0, 0, 0, 1))))
                        gpu.state.line_width_set(2.5 * scale)
                        shader.uniform_float('color', cables.COLORS[self.kind])
                        self._wire_batch.draw(shader)
            with gpu.matrix.push_pop():
                gpu.matrix.translate((x, y, 0))
                gpu.matrix.scale_uniform(9 * scale)
                for size, color in ((5, (.01, .02, .025, 1)), (2.5, cables.COLORS[self.kind])):
                    gpu.state.line_width_set(size * scale)
                    shader.uniform_float('color', color)
                    self._ring_batch.draw(shader)
            if self.group_power:
                from . import curve_widgets as widgets
                message = 'Choose power source / starting position'
                detail = 'Click a socket or empty space'
                import blf
                blf.size(0, 12 * scale)
                w = blf.dimensions(0, message)[0] + 18 * scale
                h = 40 * scale
                left = max(2, min(x + 20 * scale, context.region.width - w - 2))
                bottom = max(2, min(y + 16 * scale, context.region.height - h - 2))
                with widgets.canvas(context):
                    widgets.rounded(shader, left, bottom, w, h, 5 * scale, (.025,.08,.06,.95))
                    widgets.text(message, left + 9*scale, bottom + 24*scale, 12*scale, (.78,1,.83,1))
                    widgets.text(detail, left + 9*scale, bottom + 7*scale, 11*scale, (.93,.96,.94,1))
        finally:
            gpu.state.line_width_set(width)
            gpu.state.blend_set(blend)

    @staticmethod
    def workspace_tool(context):
        tool = context.workspace.tools.from_space_view3d_mode('OBJECT', create=False)
        return tool.idname if tool else None

    def modal(self, context, event):
        if self.repeat_placement and SESSIONS.get(self._scene_key) is self._session:
            if (context.scene.as_pointer() != self._scene_key or context.workspace != self._workspace
                    or self._area.type != 'VIEW_3D' or
                    (event.type == 'TIMER' and self.workspace_tool(context) != self._workspace_tool)):
                SESSIONS.pop(self._scene_key)
                self.release_cursor()
                redraw(context)
                return {'FINISHED', 'PASS_THROUGH'}
        if session(context) is not self._session:
            self.release_cursor();return {'FINISHED'}
        if 'source' in self._session and not visible(context, self._session['source']):
            cancel(context)
            return {'CANCELLED'}
        if event.type in {'ESC', 'RIGHTMOUSE'} or context.mode != 'OBJECT':
            cancel(context);return {'CANCELLED'}
        if event.type in {'MOUSEMOVE','INBETWEEN_MOUSEMOVE','LEFTMOUSE'}:
            self.update_cursor(event)
        if self.repeat_placement and event.value == 'PRESS':
            outside_click = event.type == 'LEFTMOUSE' and self._xy is None
            # Let the same click or shortcut reach the newly chosen tool/menu.
            shortcut = (event.type in {'F3', 'SPACE', 'TAB', 'ACCENT_GRAVE', 'F10', 'F11'}
                        or (len(event.type) == 1 and event.type.isalpha()))
            if outside_click or shortcut:
                cancel(context)
                return {'FINISHED', 'PASS_THROUGH'}
        # A wiring session launched by a gizmo owns the modal input handler.
        # Pick with the same screen positions used to draw the connector rings.
        if event.type == 'LEFTMOUSE' and event.value == 'PRESS' and self._xy is not None:
            mouse = Vector(self._xy)
            with context.temp_override(window=self._window, area=self._area, region=self._region):
                # The modal launcher owns no undo step. Commit a completed
                # group route in the nested click operator so redo has a snapshot.
                choices = projected_targets(context)
                hit = min(choices, key=lambda row: (row[4] - mouse).length_squared, default=None)
                if hit is not None and (hit[4] - mouse).length <= SOCKET_HIT_RADIUS:
                    owner, key, kind = hit[:3]
                    bpy.ops.bbe.click_cable_target('EXEC_DEFAULT', self.group_power, owner=owner, key=key, kind=kind)
                elif self.kind in (cables.POWER, cables.BYTEBEAT) and not self.selected_only:
                    span = pick_span(context, mouse, self.kind) if self.new_point else None
                    if span is not None:
                        cable, fraction = span
                        bpy.ops.bbe.click_cable_target(kind=self.kind, span=cable.name, fraction=fraction)
                        return {'RUNNING_MODAL'}
                    depth = start_position(context, self._session)
                    if depth is None:
                        depth = context.scene.cursor.location
                    position = region_2d_to_location_3d(self._region, context.region_data, mouse, depth)
                    bpy.ops.bbe.click_cable_target('EXEC_DEFAULT', self.group_power, kind=self.kind, free=True, position=position)
            return {'RUNNING_MODAL'}
        return {'PASS_THROUGH'}

    def cancel(self,context):
        if session(context) is self._session:cancel(context)
        self.release_cursor()


def pick_span(context, mouse, kind):
    """Pick in screen pixels, then recover the perspective-correct world fraction."""
    region, view = context.region, context.region_data
    closest = None
    for cable in scene_index(context)[1]:
        if cable.get('ObjectID') != kind or not visible(context, cable):
            continue
        pair = cables.endpoints(cable)
        if not all(pair):
            continue
        a, b = (p.matrix_world.translation for p in pair)
        p, q = (location_3d_to_region_2d(region, view, v) for v in (a, b))
        if p is None or q is None or (q-p).length_squared < 1e-6:
            continue
        t = max(0., min(1., (mouse-p).dot(q-p) / (q-p).length_squared))
        distance = (mouse-p.lerp(q, t)).length
        if distance > 8 * context.preferences.system.ui_scale:
            continue
        wa, wb = ((view.perspective_matrix @ v.to_4d()).w for v in (a, b))
        fraction = t * wa / ((1-t) * wb + t * wa)
        depth = (a.lerp(b, fraction) - view.view_matrix.inverted().translation).length
        if closest is None or (distance, depth) < closest[:2]:
            closest = distance, depth, cable, fraction
    return closest[2:] if closest else None


class BBE_OT_cable_target(bpy.types.Operator):
    bl_idname = 'bbe.click_cable_target'
    bl_label = 'Cable Connector'
    bl_options = {'REGISTER', 'UNDO'}
    free: bpy.props.BoolProperty(options={'HIDDEN', 'SKIP_SAVE'})
    span: bpy.props.StringProperty(options={'HIDDEN', 'SKIP_SAVE'})
    fraction: bpy.props.FloatProperty(min=0, max=1, options={'HIDDEN', 'SKIP_SAVE'})
    position: bpy.props.FloatVectorProperty(size=3, options={'HIDDEN', 'SKIP_SAVE'})
    owner: bpy.props.StringProperty()
    key: bpy.props.StringProperty()
    kind: bpy.props.StringProperty()

    @classmethod
    def description(cls, context, properties):
        color = cables.TARGET_LABELS.get(properties.kind, 'Cable')
        obj = context.scene.objects.get(properties.owner)
        pid = obj.get('ObjectID') if obj else None
        label = cables.LOGIC_ROLES.get(pid, {}).get(properties.key)
        if label:
            if label == 'TRIGGER':
                purpose = {
                    'U_TRANSISTOR1': 'Power this socket to turn the output off',
                    'U_TRANSISTOR2': 'Power this socket to turn the output on',
                    'BYTEBEATSWITCH': 'Connect a ByteBeat signal to control the switch',
                }[pid]
            elif label == 'IN':
                purpose = 'Group wiring supplies this socket and continues the chain here'
            else:
                purpose = 'Use Place Cables to wire the switched output'
            return f'{label} on {properties.owner} — {purpose}'
        return color + ' connector on ' + properties.owner

    def execute(self, context):
        obj = context.scene.objects.get(self.owner)
        if obj is None and not self.free and not self.span:
            cancel(context)
            return {'CANCELLED'}
        current = session(context)
        if not current:
            if obj is None or self.free or self.span:
                return {'CANCELLED'}
            if not obj.hide_select:
                for selected in context.selected_objects:
                    selected.select_set(False)
                obj.select_set(True)
                context.view_layer.objects.active = obj
            return {'FINISHED'}
        if self.kind != current['kind']:
            return {'CANCELLED'}
        from .builder import get_builder
        if self.span:
            cable = context.scene.objects.get(self.span)
            if (not current.get('new_point') or cable is None or cable.get('ObjectID') != self.kind
                    or not all(cables.endpoints(cable))):
                return {'CANCELLED'}
            start, end = cables.endpoints(cable)
            pos = start.matrix_world.translation.lerp(end.matrix_world.translation, self.fraction)
            first_pos = start_position(context, current)
            if first_pos is not None and (first_pos-pos).length < 1e-6:
                return {'CANCELLED'}
            if self.fraction <= 1e-6:
                obj = start
            elif self.fraction >= 1 - 1e-6:
                obj = end
            else:
                obj, = cables.subdivide(cable, [self.fraction], get_builder())
            self.key = 'ENDPOINT'
            position = Vector()
        elif self.free:
            if (self.kind not in (cables.POWER, cables.BYTEBEAT) or 'remaining' in current or
                    ('source' in current and current['first'] is None)):
                return {'CANCELLED'}
            obj = None
            position = Vector(self.position)
            if current.get('new_point') and current['first'] is None:
                obj = cables.junction(get_builder(), self.kind, position)
                self.key = 'ENDPOINT'
                position = Vector()
                context.view_layer.update()
        else:
            sockets = cables.local_sockets(obj, self.kind)
            if not allowed_target(current, obj) or self.key not in sockets:
                self.report({'WARNING'}, 'Choose a matching connector.')
                return {'CANCELLED'}
            position = sockets[self.key]
        if 'devices' in current:
            try:
                origin = obj.matrix_world @ position if obj is not None else position
                count = cables.route_power(context, current['devices'], obj, self.key, origin,
                                           get_builder(), current['chain'])
            except (ValueError, ReferenceError, RuntimeError) as error:
                self.report({'WARNING'}, str(error))
                return {'CANCELLED'}
            cancel(context)
            self.report({'INFO'}, f'Added {count} electrical cable(s).')
            return {'FINISHED'}
        first = current['first']
        if first is None:
            if current.get('new_point') and obj is not None:
                from .utils import blend_utils
                blend_utils.select(obj)
            if current.get('chain'):
                current['remaining'].discard(obj.name)
            current['first'] = (obj, self.key)
            current['first_local'] = position
            if self.kind == cables.TELEPORT or 'remaining' in current:
                hint = 'Click a destination connector.'
            elif current.get('new_point'):
                hint = 'Click a destination to branch, or press Escape to keep this junction.'
            else:
                hint = 'Click a connector or empty space to finish.'
            self.report({'INFO'}, hint)
            redraw(context)
            return {'FINISHED'}
        try:
            if first[0] is not None and first[0].name not in context.scene.objects:
                raise ValueError('The first device was removed. Choose the cable again.')
            cable = cables.connect(first[0], first[1], obj, self.key, self.kind, get_builder(),
                                   free_start=current['first_local'], free_end=position)
        except (ValueError, ReferenceError) as error:
            self.report({'WARNING'}, str(error))
            return {'CANCELLED'}
        if 'remaining' in current:
            current['remaining'].discard(obj.name)
            current['remaining'].intersection_update(context.scene.objects.keys())
            if current['remaining']:
                source = obj if current.get('chain') else first[0]
                current['active'] = source.name
                sockets = cables.local_sockets(source, self.kind)
                if len(sockets) == 1:
                    key, local = next(iter(sockets.items()))
                    current.update(first=(source, key), first_local=local)
                    self.report({'INFO'}, 'Click a connector on the next selected device.')
                else:
                    current['first'] = None
                    self.report({'INFO'}, f'Click the outgoing socket on {source.name} for the next cable.')
                redraw(context)
                return {'FINISHED'}
        while current.get('next_starts'):
            point = current['next_starts'].pop(0)
            if visible(context, point):
                current.update(source=point, first=(point, 'ENDPOINT'), first_local=Vector())
                redraw(context)
                self.report({'INFO'}, 'Click a destination for the next branch.')
                return {'FINISHED'}
        if current.get('repeat'):
            current['first'] = None
            current.pop('first_local', None)
            self.report({'INFO'}, 'Cable placed. Click the start of another cable, or Esc to finish.')
            redraw(context)
            return {'FINISHED'}
        cancel(context)
        for selected in context.selected_objects:
            selected.select_set(False)
        cable.select_set(True)
        context.view_layer.objects.active = cable
        self.report({'INFO'}, f'Connected {cables.LABELS[self.kind]} cable.')
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


SOCKET_HIT_RADIUS = 19


def marker_position(point, occupied, width, height):
    """Keep overlapping sockets on one device separately clickable in screen space."""
    spacing = 2 * SOCKET_HIT_RADIUS + 2
    def clear(candidate):
        return all((candidate - other).length_squared >= (2 * SOCKET_HIT_RADIUS)**2
                   for other in occupied)
    if clear(point):
        return point
    nearest = min(occupied, key=lambda other: (point - other).length_squared)
    angle = math.atan2(point.y - nearest.y, point.x - nearest.x)
    for ring in range(1, len(occupied) + 2):
        for step in (0, 1, -1, 2, -2, 3, -3, 4):
            direction = angle + step * math.pi / 4
            candidate = point + Vector((math.cos(direction), math.sin(direction))) * spacing * ring
            if (SOCKET_HIT_RADIUS <= candidate.x <= width - SOCKET_HIT_RADIUS and
                    SOCKET_HIT_RADIUS <= candidate.y <= height - SOCKET_HIT_RADIUS and clear(candidate)):
                return candidate
    return point


def projected_targets(context):
    width, height = context.region.width, context.region.height
    occupied = defaultdict(list)
    choices = []
    for name, key, kind, position in targets(context):
        point = location_3d_to_region_2d(context.region, context.region_data, position)
        if point is None or not (0 <= point.x <= width and 0 <= point.y <= height):
            continue
        center = marker_position(point, occupied[name], width, height)
        occupied[name].append(center)
        choices.append((name, key, kind, point, center))
    return choices


class BBE_GT_cable_target(bpy.types.Gizmo):
    bl_idname = 'BBE_GT_cable_target'
    __slots__ = ('tint', 'chosen', 'anchor', 'role')

    def setup(self):
        self.tint = cables.COLORS[cables.POWER]
        self.chosen = False
        self.anchor = None
        self.role = ''

    def draw(self, context):
        x, y = self.matrix_basis.translation[:2]
        radius = 15
        ring = [(x+math.cos(i*math.tau/48)*radius, y+math.sin(i*math.tau/48)*radius) for i in range(49)]
        shader = gpu.shader.from_builtin('UNIFORM_COLOR')
        gpu.state.blend_set('ALPHA')
        try:
            shader.bind()
            shader.uniform_float('color', (.015, .02, .025, .95))
            if self.anchor is not None:
                gpu.state.line_width_set(2)
                shader.uniform_float('color', self.tint)
                batch_for_shader(shader, 'LINES', {'pos': [self.anchor, (x,y)]}).draw(shader)
            gpu.state.line_width_set(7)
            batch_for_shader(shader, 'LINE_STRIP', {'pos': ring}).draw(shader)
            shader.uniform_float('color', (1,1,1,1) if self.chosen or self.is_highlight else self.tint)
            gpu.state.line_width_set(3)
            batch_for_shader(shader, 'LINE_STRIP', {'pos': ring}).draw(shader)
            batch_for_shader(shader, 'LINES', {'pos': [(x-8,y),(x+8,y),(x,y-8),(x,y+8)]}).draw(shader)
            if self.role:
                from . import curve_widgets as widgets
                scale = max(.85, context.preferences.system.ui_scale)
                width = (11 + 7 * len(self.role)) * scale
                left = max(1, min(context.region.width - width - 1, x - width/2))
                bottom = y - 16 - 16*scale if y > 16 + 16*scale else y + 16
                with widgets.canvas(context):
                    widgets.rounded(shader, left, bottom, width, 16*scale, 3*scale, (.02,.06,.04,.95))
                    widgets.text(self.role, left+width/2, bottom+3*scale, 11*scale, (1,1,1,1), 'CENTER')
                shader.bind()
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
        return 0 if (Vector(location)-Vector(self.matrix_basis.translation[:2])).length <= SOCKET_HIT_RADIUS else -1


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
            o.get('ObjectID') in cables.BEAT_SOCKETS or o.get('rig_item') or cables.local_sockets(o, cables.POWER)
            for o in context.selected_objects))

    def setup(self, context):
        self.targets = []

    def draw_prepare(self, context):
        choices = projected_targets(context)
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
            name, key, kind, point, center = choices[index]
            gizmo.hide = False
            gizmo.tint = cables.COLORS[kind]
            owner = context.scene.objects.get(name)
            gizmo.role = cables.LOGIC_ROLES.get(owner.get('ObjectID'), {}).get(key, '') if owner else ''
            try:
                gizmo.chosen = bool(first and first[0] is not None and first[0].name == name and first[1] == key)
            except ReferenceError:
                cancel(context)
                gizmo.chosen = False
            gizmo.anchor = tuple(point) if center != point else None
            gizmo.matrix_basis = Matrix.Translation((center.x, center.y, 0))
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
    _index_key, _devices, _cables = None, {}, ()


def register():
    bpy.app.handlers.load_post.append(cables.organize_saved_cables)
    # Data access is restricted while Blender is enabling the extension.
    bpy.app.timers.register(cables.organize_saved_cables, first_interval=0.0)
    for cls in CLASSES:
        bpy.utils.register_class(cls)
    for handlers in (bpy.app.handlers.load_post, bpy.app.handlers.undo_post, bpy.app.handlers.redo_post):
        if reset not in handlers:
            handlers.append(reset)


def unregister():
    if bpy.app.timers.is_registered(cables.organize_saved_cables):
        bpy.app.timers.unregister(cables.organize_saved_cables)
    if cables.organize_saved_cables in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.remove(cables.organize_saved_cables)
    reset()
    for handlers in (bpy.app.handlers.load_post, bpy.app.handlers.undo_post, bpy.app.handlers.redo_post):
        if reset in handlers:
            handlers.remove(reset)
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)
