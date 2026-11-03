"""Visual previews for the game's snap-selected native bubble ducts.

All objects keep ObjectID BASE_BUBPIPE and their original matrix. Only their
mesh datablock changes, so clipboard/save exports keep the native placement.
"""

from collections import defaultdict
from itertools import permutations, product
import math

import bpy
from bpy.app.handlers import persistent
from mathutils import Matrix, Vector


_OFFSETS = {
    "Front": (0, 1, 1), "Back": (0, 1, -1),
    "Left": (-1, 1, 0), "Right": (1, 1, 0),
    "Top": (0, 2, 0), "Bot": (0, 0, 0),
}
_ARMS = {
    "Front": Vector((0, 0, 1)), "Back": Vector((0, 0, -1)),
    "Left": Vector((-1, 0, 0)), "Right": Vector((1, 0, 0)),
    "Top": Vector((0, 1, 0)), "Bot": Vector((0, -1, 0)),
}
_MESH_KEY = "bbe_native_bubble_preview"
_MESH_QUALITY = "bbe_native_bubble_quality"
_MESH_REVISION = "bbe_native_bubble_revision"
_PREVIEW_REVISION = 3
_INTENT_KEY = "bbe_bubble_shape"
_START_KEY = "bbe_bubble_start_socket"
_refreshing = False
_route_cache = {}
_junction_option_cache = {}
_joint_pivot_sessions = {}
_joint_save_resume = {}
_warning_draw_handle = None
_elbow_lock_sessions = {}
_elbow_gizmo_sessions = {}
_draft_shading_sessions = {}
_highlight_selection = None
_pending_group_refresh = set()
_expansion_preview = {}
_direction_sessions = {}
_JUNCTION_PREFIXES = ('ELBOW:', 'TEE:', 'CROSS:', 'CORNER3:', 'CORNER4:', 'FIVE:', 'SIX:')
JUNCTION_LABELS = {'TEE': 'T-junction', 'CROSS': '+ junction', 'CORNER3': 'three-way corner',
                   'CORNER4': 'four-way corner', 'FIVE': 'five-way junction', 'SIX': 'six-way junction'}

ELBOW_HELP = (
    'DRAFT ELBOW - connect both ends',
    'Keep the elbow selected and add a tube to its free end.',
    'Grey-blue bands mean the bend is not ready yet.',
    'The bands disappear when both ends connect correctly.',
    'An unfinished elbow appears straight in game.',
    'To rotate it, use the controls beside the selected tube.',
)


def _is_elbow(obj):
    return (obj is not None and obj.get('ObjectID') == 'BASE_BUBPIPE'
            and str(obj.get(_INTENT_KEY, '')).startswith('ELBOW:'))


def _is_junction(obj):
    return (obj is not None and obj.get('ObjectID') == 'BASE_BUBPIPE'
            and str(obj.get(_INTENT_KEY, '')).startswith(_JUNCTION_PREFIXES))


def _restore_draft_shading():
    for space, previous in tuple(_draft_shading_sessions.values()):
        try:
            if space.shading.color_type == 'MATERIAL':
                space.shading.color_type = previous
        except ReferenceError:
            pass
    _draft_shading_sessions.clear()


def _sync_draft_shading():
    """Solid Single-color hides every draft material. Temporarily show materials."""
    wanted = set()
    for window in bpy.context.window_manager.windows:
        if not any(obj.type == 'MESH' and (obj.data.get('bbe_bubble_draft') or obj.data.get('bbe_bubble_target'))
                   for obj in window.scene.objects):
            continue
        for area in window.screen.areas:
            if area.type != 'VIEW_3D':
                continue
            space = area.spaces.active
            if space.shading.type != 'SOLID':
                continue
            key = space.as_pointer()
            wanted.add(key)
            if space.shading.color_type != 'MATERIAL':
                # Remember a user's latest color choice even during a draft.
                _draft_shading_sessions[key] = (space, space.shading.color_type)
                space.shading.color_type = 'MATERIAL'
    for key in set(_draft_shading_sessions) - wanted:
        space, previous = _draft_shading_sessions.pop(key)
        try:
            if space.shading.color_type == 'MATERIAL':
                space.shading.color_type = previous
        except ReferenceError:
            pass


def _restore_elbow_controls():
    for obj, rotation, w, four_d in tuple(_elbow_lock_sessions.values()):
        try:
            obj.lock_rotation = rotation
            obj.lock_rotation_w = w
            obj.lock_rotations_4d = four_d
        except ReferenceError:
            pass
    _elbow_lock_sessions.clear()
    for space, rotate, tool in tuple(_elbow_gizmo_sessions.values()):
        try:
            space.show_gizmo_object_rotate = rotate
            space.show_gizmo_tool = tool
        except ReferenceError:
            pass
    _elbow_gizmo_sessions.clear()


def _sync_elbow_controls(context):
    """Native rotation has no per-object valid-angle callback. Use checked turns."""
    selected = {obj.as_pointer(): obj for obj in context.selected_objects
                if _is_junction(obj)} if (context.mode == 'OBJECT'
                                         and len(context.selected_objects) == 1) else {}
    for key in tuple(_elbow_lock_sessions):
        if key not in selected:
            obj, rotation, w, four_d = _elbow_lock_sessions.pop(key)
            try:
                obj.lock_rotation, obj.lock_rotation_w = rotation, w
                obj.lock_rotations_4d = four_d
            except ReferenceError:
                pass
    for key, obj in selected.items():
        if key not in _elbow_lock_sessions:
            _elbow_lock_sessions[key] = (obj, tuple(obj.lock_rotation),
                                         obj.lock_rotation_w, obj.lock_rotations_4d)
        if not all(obj.lock_rotation):
            obj.lock_rotation = (True, True, True)
        if not obj.lock_rotation_w:
            obj.lock_rotation_w = True
        if not obj.lock_rotations_4d:
            obj.lock_rotations_4d = True
    if not selected:
        _restore_elbow_controls()
        return
    for window in context.window_manager.windows:
        tool = window.workspace.tools.from_space_view3d_mode('OBJECT', create=False)
        rotation_tool = tool is not None and tool.idname in {'builtin.rotate', 'builtin.transform'}
        for area in window.screen.areas:
            if area.type != 'VIEW_3D':
                continue
            space = area.spaces.active
            key = space.as_pointer()
            if key not in _elbow_gizmo_sessions:
                _elbow_gizmo_sessions[key] = (space, space.show_gizmo_object_rotate,
                                               space.show_gizmo_tool)
            if space.show_gizmo_object_rotate:
                space.show_gizmo_object_rotate = False
            show_tool = False if rotation_tool else _elbow_gizmo_sessions[key][2]
            if space.show_gizmo_tool != show_tool:
                space.show_gizmo_tool = show_tool


def _draft_material(index):
    name = 'BBE Draft Elbow - ' + ('Band' if index else 'Body')
    material = bpy.data.materials.get(name)
    if material is None:
        material = bpy.data.materials.new(name)
        color = (.12, .18, .25, 1) if index else (.46, .55, .64, 1)
        material.diffuse_color = color
        material.use_nodes = True
        shader = material.node_tree.nodes.get('Principled BSDF')
        shader.inputs['Base Color'].default_value = color
        shader.inputs['Roughness'].default_value = .85
    return material


def _conflict_material():
    material=bpy.data.materials.get('BBE Tube Connection Conflict')
    if material is None:
        material=bpy.data.materials.new('BBE Tube Connection Conflict')
        material.diffuse_color=(.75,.28,.045,1)
        material.use_nodes=True
        shader=material.node_tree.nodes.get('Principled BSDF')
        shader.inputs['Base Color'].default_value=material.diffuse_color
        shader.inputs['Roughness'].default_value=.7
    return material


def _visible_sockets(obj):
    """Return the openings drawn for a fixed duct, or all native sockets."""
    intent = str(obj.get(_INTENT_KEY, ''))
    if intent == 'STRAIGHT:X':
        return ('Left', 'Right')
    if intent == 'STRAIGHT:Y':
        return ('Bot', 'Top')
    if intent == 'STRAIGHT:Z':
        return ('Back', 'Front')
    if intent.startswith(_JUNCTION_PREFIXES):
        names = tuple(sorted(set(intent.split(':', 1)[1].split('+'))))
        if names and all(name in _ARMS for name in names):
            return names
    return tuple(sorted(_ARMS))


def _hidden_contacts(obj, snapped):
    """Connections the native game sees but the fixed preview does not show."""
    if not obj.get(_INTENT_KEY):
        return set()
    return snapped.get(obj.name, set()) - set(_visible_sockets(obj))


def mirror_openings(obj, old_world, new_world, axis):
    """Carry the visible openings through the same reflection as the tube."""
    if obj.get('ObjectID') != 'BASE_BUBPIPE' or not obj.get(_INTENT_KEY):
        return
    reflection = Matrix.Identity(3)
    reflection['XYZ'.index(axis)]['XYZ'.index(axis)] = -1
    local = new_world.to_3x3().inverted() @ reflection @ old_world.to_3x3()
    ports = []
    for port in _visible_sockets(obj):
        direction = (local @ _ARMS[port]).normalized()
        best = max(_ARMS, key=lambda name: direction.dot(_ARMS[name]))
        if direction.dot(_ARMS[best]) < .9999:
            raise ValueError('Mirrored tube opening is not aligned with its local axes')
        ports.append(best)
    _, intent, _ = _display_spec(ports, True)
    obj[_INTENT_KEY] = intent
    for key in ('snapped_to', 'bbe_native_snap_target', 'bbe_native_target_socket',
                'bbe_native_source_socket', 'bbe_native_source_option'):
        if key in obj:
            del obj[key]


def _cube_rotations():
    """All right-handed quarter-turn rotations of a native duct."""
    axes = (Vector((1, 0, 0)), Vector((0, 1, 0)), Vector((0, 0, 1)))
    result = []
    for order in permutations(range(3)):
        for signs in product((-1, 1), repeat=3):
            columns = [signs[i] * axes[order[i]] for i in range(3)]
            matrix = Matrix(tuple(tuple(columns[col][row] for col in range(3))
                                  for row in range(3)))
            if matrix.determinant() > 0:
                result.append(matrix.to_4x4())
    return result


_ROTATIONS = _cube_rotations()


def _native_objects(scene):
    return [obj for obj in scene.objects if obj.type == 'MESH'
            and obj.get('ObjectID') == 'BASE_BUBPIPE'
            and obj.data is not None]


def _snapped(parts):
    """Find coincident native sockets without a quadratic whole-scene scan."""
    candidates = []
    largest_scale = 1.0
    for obj in parts:
        matrix = obj.matrix_world
        scale = max(abs(value) for value in matrix.to_scale())
        largest_scale = max(largest_scale, scale)
        for name, offset in _OFFSETS.items():
            candidates.append((obj.name, name, matrix @ Vector(offset), scale))
    cell_size = max(1e-5, largest_scale * 0.025)
    buckets = defaultdict(list)
    for entry in candidates:
        point = entry[2]
        cell = tuple(math.floor(value / cell_size) for value in point)
        buckets[cell].append(entry)
    found = {obj.name: set() for obj in parts}
    for name, socket, point, scale in candidates:
        cell = tuple(math.floor(value / cell_size) for value in point)
        for offset in product((-1, 0, 1), repeat=3):
            nearby = tuple(cell[i] + offset[i] for i in range(3))
            for other, other_socket, other_point, other_scale in buckets.get(nearby, ()):
                if other == name:
                    continue
                if (point - other_point).length <= max(scale, other_scale) * 0.025:
                    found[name].add(socket)
                    found[other].add(other_socket)
    return found


def _editor_contacts(parts):
    """Drawn openings that meet; independent of native export frame encoding."""
    from .bubble_export import _pairs
    by_name = {obj.name: obj for obj in parts}
    points = [(obj.name, port, obj.matrix_world @ Vector(_OFFSETS[port]),
               max(abs(v) for v in obj.matrix_world.to_scale()))
              for obj in parts for port in _visible_sockets(obj)]
    found = {obj.name: set() for obj in parts}
    for a, b in _pairs(points):
        obj, other = by_name[a[0]], by_name[b[0]]
        direction = (obj.matrix_world.to_3x3() @ _ARMS[a[1]]).normalized()
        opposite = (other.matrix_world.to_3x3() @ _ARMS[b[1]]).normalized()
        if direction.dot(opposite) < -.9999:
            found[obj.name].add(a[1])
            found[other.name].add(b[1])
    return found


def _editor_port_links(parts, overrides=None):
    """Exact drawn opening contacts, retaining which end of each elbow joins."""
    from .bubble_export import _pairs
    by_name = {obj.name: obj for obj in parts}
    points = [(obj.name, port, _joint_point(obj, port),
               max(abs(v) for v in obj.matrix_world.to_scale()))
              for obj in parts for port in (overrides or {}).get(obj.name, _visible_sockets(obj))]
    links = defaultdict(set)
    for a, b in _pairs(points):
        left = (by_name[a[0]].matrix_world.to_3x3() @ _ARMS[a[1]]).normalized()
        right = (by_name[b[0]].matrix_world.to_3x3() @ _ARMS[b[1]]).normalized()
        if left.dot(right) < -.9999:
            links[a[:2]].add(b[:2])
            links[b[:2]].add(a[:2])
    return links


def _branches_complete(obj, parts, links, ports=None):
    """A branch ends at a straight, a connected junction, or a closed elbow loop.

    An elbow added to an opening must itself have a connected far end. Derive
    this from current geometry so delete, move, load and Undo cannot leave a
    stale 'finished' flag. The rule is local to this junction's arms.
    """
    by_name = {part.name: part for part in parts}

    def complete(name, port, visited):
        key = (name, port)
        if key in visited:
            return True
        neighbors = links.get(key, ())
        if len(neighbors) != 1:
            return False
        other_name, entrance = next(iter(neighbors))
        other = by_name[other_name]
        if str(other.get(_INTENT_KEY, '')).startswith('STRAIGHT:'):
            return True
        if _is_elbow(other):
            return all(complete(other_name, end, visited | {key})
                       for end in _visible_sockets(other) if end != entrance)
        return all(len(links.get((other_name, end), ())) == 1
                   for end in _visible_sockets(other))

    return all(complete(obj.name, port, set()) for port in (ports if ports is not None else _visible_sockets(obj)))


def _opening_clear(obj, port, parts):
    """Do not aim a new branch into an occupied neighboring tube position.

    An existing facing opening is a connection, not an obstruction. A hidden
    socket on a neighboring elbow cannot be used as if it were an open end.
    """
    center = obj.matrix_world @ Vector((0, 1, 0))
    arm = obj.matrix_world.to_3x3() @ _ARMS[port]
    destination = center + 2 * arm
    point = center + arm
    for other in parts:
        if other == obj:
            continue
        scale = max(arm.length, *(abs(v) for v in other.matrix_world.to_scale()))
        if (other.matrix_world @ Vector((0, 1, 0)) - destination).length >= .5 * scale:
            continue
        if not any((point - _joint_point(other, end)).length <= .025 * scale
                   and arm.normalized().dot((other.matrix_world.to_3x3() @ _ARMS[end]).normalized()) < -.9999
                   for end in _visible_sockets(other)):
            return False
    return True


def _opening_candidates(scene, obj, base_ports):
    from . import bubble_export as ex
    parts, (_, before, _) = _scene_plan(scene)
    options = {}
    records, hints = [], {}
    for i, part in enumerate(parts):
        matrix = part.matrix_world
        records.append({'ObjectID': '^BASE_BUBPIPE', 'Position': list(matrix.translation),
                        'Up': list(matrix.col[1].to_3d()), 'At': list(matrix.col[2].to_3d().normalized())})
        if part.get(_INTENT_KEY):
            hints[i] = {'name': part.name, 'shape': part[_INTENT_KEY]}
    index = parts.index(obj)
    for port in _ARMS:
        if port in base_ports or not _opening_clear(obj, port, parts):
            continue
        _, intent, _ = _display_spec(set(base_ports) | {port}, True)
        kind = intent.split(':')[0]
        if kind not in JUNCTION_LABELS:
            continue
        hints[index] = {'name': obj.name, 'shape': intent}
        _, after, _ = ex.plan_objects(records, hints)
        if not after.keys() - before.keys() - {index}:
            options.setdefault(kind, []).append((port, intent))
    return options


def editable_opening(scene, obj):
    """Find one unused arm without detaching any existing branch; works on old saves."""
    parts, _ = _scene_plan(scene)
    if obj not in parts or len(_visible_sockets(obj)) < 3:
        return None
    links = _editor_port_links(parts)
    ports = set(_visible_sockets(obj))
    free = ports - {port for port in ports if links.get((obj.name, port))}
    if len(free) != 1 or not _branches_complete(obj, parts, links, ports - free):
        return None
    return next(iter(free)), ports - free


def redirect_options(scene, obj):
    parts, _ = _scene_plan(scene)
    if obj not in parts:
        return {}
    key = ('redirect', scene.as_pointer(), obj.name)
    if key not in _junction_option_cache:
        opening = editable_opening(scene, obj)
        _junction_option_cache[key] = (_opening_candidates(scene, obj, opening[1]) if opening else {})
    return _junction_option_cache[key]


def expansion_options(scene, obj):
    """One added arm, grouped by resulting shape. Never mutate while drawing."""
    parts, _ = _scene_plan(scene)
    if obj not in parts or not obj.get(_INTENT_KEY):
        return {}
    key = ('expansion', scene.as_pointer(), obj.name)
    if key not in _junction_option_cache:
        options = {}
        ports = set(_visible_sockets(obj))
        if len(ports) < 6 and _branches_complete(obj, parts, _editor_port_links(parts)):
            options = _opening_candidates(scene, obj, ports)
        _junction_option_cache[key] = options
    return _junction_option_cache[key]


def _connected_to_straight(target, parts):
    """Whether the target's visible duct route contains a straight piece."""
    from .bubble_export import _pairs

    by_name = {obj.name: obj for obj in parts}
    points = [(obj.name, port, obj.matrix_world @ Vector(_OFFSETS[port]),
               max(abs(v) for v in obj.matrix_world.to_scale()))
              for obj in parts for port in _visible_sockets(obj)]
    links = {obj.name: set() for obj in parts}
    for a, b in _pairs(points):
        obj, other = by_name[a[0]], by_name[b[0]]
        direction = (obj.matrix_world.to_3x3() @ _ARMS[a[1]]).normalized()
        opposite = (other.matrix_world.to_3x3() @ _ARMS[b[1]]).normalized()
        if direction.dot(opposite) < -.9999:
            links[obj.name].add(other.name)
            links[other.name].add(obj.name)

    pending = [target.name]
    visited = set()
    while pending:
        name = pending.pop()
        if name in visited:
            continue
        visited.add(name)
        if str(by_name[name].get(_INTENT_KEY, '')).startswith('STRAIGHT:'):
            return True
        pending.extend(links[name] - visited)
    return False


def _native_contacts(parts):
    """Import prediction with socket types and the supported frame envelope."""
    from .bubble_export import frame, native_contacts
    nodes = {}
    for obj in parts:
        matrix = obj.matrix_world
        nodes[obj.name] = frame({'Position': list(matrix.translation),
                                'Up': list(matrix.col[1].to_3d()),
                                'At': list(matrix.col[2].to_3d())})
    return native_contacts(nodes)[0]


def placement_error(target, scene):
    """Explain why a selected duct cannot safely be extended."""
    parts = _native_objects(scene)
    connected = _editor_contacts(parts).get(target.name, set())
    if not (set(_visible_sockets(target)) - connected):
        return f'{target.name} has no open visible end. Select a duct at the end of the route.'
    return None


def _joint_point(obj, socket):
    return obj.matrix_world @ Vector(_OFFSETS[socket])


def _joined_sockets(source, target):
    """Return the actual meeting openings, preferring the recorded BBE snap."""
    pairs = []
    tolerance = 0.025 * max(
        *(abs(value) for value in source.matrix_world.to_scale()),
        *(abs(value) for value in target.matrix_world.to_scale()))
    for target_socket in _visible_sockets(target):
        for source_socket in _visible_sockets(source):
            if (_joint_point(source, source_socket)
                    - _joint_point(target, target_socket)).length < tolerance:
                pairs.append((target_socket, source_socket))
    recorded = (source.get('bbe_native_target_socket'),
                source.get('bbe_native_source_socket'))
    if source.get('bbe_native_snap_target') == target.name and recorded in pairs:
        return recorded
    return pairs[0] if len(pairs) == 1 else None


def _roll_about_joint(source, target, target_socket, direction):
    """Quarter-turn the source around the centreline through its joined end."""
    pivot = _joint_point(target, target_socket)
    axis = (target.matrix_world.to_3x3() @ _ARMS[target_socket]).normalized()
    turn = Matrix.Translation(pivot) @ Matrix.Rotation(
        direction * math.pi / 2, 4, axis) @ Matrix.Translation(-pivot)
    source.matrix_world = turn @ source.matrix_world


def _active_tube_joint(context):
    """Return a single selected elbow and its unambiguous joined opening."""
    scene = getattr(context, 'scene', None)
    view_layer = getattr(context, 'view_layer', None)
    if scene is None or view_layer is None or getattr(context, 'mode', None) != 'OBJECT':
        return None
    source = view_layer.objects.active
    if (source is None or not source.select_get()
            or source.get('ObjectID') != 'BASE_BUBPIPE'
            or not str(source.get(_INTENT_KEY, '')).startswith(('STRAIGHT:',) + _JUNCTION_PREFIXES)):
        return None
    if sum(obj.select_get() for obj in view_layer.objects) != 1:
        return None  # A selected run can still rotate freely as a group.

    remembered = scene.objects.get(source.get('bbe_native_snap_target', ''))
    others = ([remembered] if remembered is not None and remembered != source else
              [obj for obj in _native_objects(scene) if obj != source])
    matches = []
    for target in others:
        pair = _joined_sockets(source, target)
        if pair is None:
            continue
        target_socket, source_socket = pair
        source_arm = (source.matrix_world.to_3x3() @ _ARMS[source_socket]).normalized()
        target_arm = (target.matrix_world.to_3x3() @ _ARMS[target_socket]).normalized()
        if source_arm.dot(target_arm) < -.9999:
            matches.append((source, target, target_socket, source_socket))
    return matches[0] if len(matches) == 1 else None


def _active_elbow_joint(context):
    joint = _active_tube_joint(context)
    return joint if joint and str(joint[0].get(_INTENT_KEY, '')).startswith('ELBOW:') else None


def _visible_links(parts):
    """Map actual joined openings for the editor's fixed tube shapes."""
    from .bubble_export import _pairs

    by_name = {obj.name: obj for obj in parts}
    points = [(obj.name, port, _joint_point(obj, port),
               max(abs(v) for v in obj.matrix_world.to_scale()))
              for obj in parts for port in _visible_sockets(obj)]
    links = {obj.name: set() for obj in parts}
    for a, b in _pairs(points):
        source, target = by_name[a[0]], by_name[b[0]]
        direction = (source.matrix_world.to_3x3() @ _ARMS[a[1]]).normalized()
        opposite = (target.matrix_world.to_3x3() @ _ARMS[b[1]]).normalized()
        if direction.dot(opposite) < -.9999:
            links[source.name].add(target.name)
            links[target.name].add(source.name)
    return links


def _moving_branch(source, target, scene):
    """Return downstream objects, or None when this joint closes a loop."""
    parts = _native_objects(scene)
    links = _visible_links(parts)
    branch, pending = set(), [source.name]
    while pending:
        name = pending.pop()
        if name in branch:
            continue
        branch.add(name)
        pending.extend(links[name] - branch - {target.name})
    if any(target.name in links[name] for name in branch if name != source.name):
        return None
    return [obj for obj in parts if obj.name in branch]


def _joint_turn_error(source_matrix, target_matrix):
    """Check cumulative roll at the joint, allowing equivalent quarter turns.

    A popup angle and repeated small turns must obey the same native envelope.
    This applies only to turning one connected branch, never a whole build.
    """
    from .bubble_export import SUPPORTED_ROLL
    left = target_matrix.to_quaternion().to_matrix()
    right = source_matrix.to_quaternion().to_matrix()
    relative = left.transposed() @ right
    error = min((relative @ symmetry.to_3x3()).to_quaternion().angle
                for symmetry in _ROTATIONS)
    unit = all(abs(abs(v) - 1) < 1e-4 for matrix in (source_matrix, target_matrix)
               for v in matrix.to_scale())
    limit = SUPPORTED_ROLL if unit else math.radians(5.001)
    if not math.isfinite(error) or error > limit:
        return ('That turn would leave the joint outside the tested tube angles. '
                'Use a 90-degree turn, or keep the total adjustment within '
                f'{8 if unit else 5} degrees of it.')
    return None


class BBE_OT_turn_bubble_elbow(bpy.types.Operator):
    """Turn the selected elbow and its downstream tubes at the shared joint"""
    bl_idname = 'bbe.turn_bubble_elbow'
    bl_label = 'Turn Connected Tubes'
    bl_description = 'Turn at this joint and carry the attached branch; cancel if a previously valid bend would break'
    bl_options = {'REGISTER', 'UNDO'}

    direction: bpy.props.IntProperty(default=1, min=-1, max=1)
    angle: bpy.props.FloatProperty(name='Angle', subtype='ANGLE',
                                  default=math.pi / 2, min=0, max=math.pi)

    def execute(self, context):
        joint = _active_tube_joint(context)
        if joint is None:
            self.report({'ERROR'}, 'Select one connected tube to turn.')
            return {'CANCELLED'}
        source, target, target_socket, _ = joint
        scene = context.scene
        by_name = {obj.name: obj for obj in _native_objects(scene)}
        links = _visible_links(tuple(by_name.values()))
        pending = [source.name]
        branch = set()
        while pending:
            name = pending.pop()
            if name in branch:
                continue
            branch.add(name)
            pending.extend(links[name] - branch - {target.name})
        if any(target.name in links[name] for name in branch if name != source.name):
            self.report({'ERROR'}, 'This is a closed tube loop. Select the whole loop to rotate it.')
            return {'CANCELLED'}
        if not self.direction:
            return {'CANCELLED'}
        point = _joint_point(target, target_socket)
        axis = (target.matrix_world.to_3x3() @ _ARMS[target_socket]).normalized()
        turn = (Matrix.Translation(point)
                @ Matrix.Rotation(self.direction * self.angle, 4, axis)
                @ Matrix.Translation(-point))
        error = _joint_turn_error(turn @ source.matrix_world, target.matrix_world)
        if error:
            self.report({'WARNING'}, error)
            return {'CANCELLED'}
        original = {name: by_name[name].matrix_world.copy() for name in branch}
        before_parts, (_, before_issues, _) = _scene_plan(scene)
        editor_contacts = _editor_contacts(before_parts)
        # A free planned opening can accidentally contact a neighbor's hidden
        # socket. Do not treat that incidental native bend as a finished joint.
        unfinished = {i for i, obj in enumerate(before_parts)
                      if obj.name in branch and _is_junction(obj)
                      and len(editor_contacts[obj.name]) < len(_visible_sockets(obj))}
        for name in branch:
            by_name[name].matrix_world = turn @ original[name]
        context.view_layer.update()
        now_ready, reason = route_status(scene)
        _, (_, after_issues, _) = _scene_plan(scene)
        if after_issues.keys() - before_issues.keys() - unfinished:
            for name, matrix in original.items():
                by_name[name].matrix_world = matrix
            context.view_layer.update()
            self.report({'WARNING'}, 'That turn would break a tube connection. The branch was left in place.')
            return {'CANCELLED'}
        refresh(scene)
        if not now_ready:
            self.report({'WARNING'}, 'Turned the branch. An unfinished connection still needs attention.')
        else:
            self.report({'INFO'}, f'Turned {len(branch)} connected tube(s) {math.degrees(self.angle):g} degrees.')
        return {'FINISHED'}


def _restore_joint_rotation_guard():
    """Restore the user's controls, including their original rotation locks."""
    _restore_elbow_controls()
    for _, (scene, selection, cursor, pivot, orientation) in tuple(_joint_pivot_sessions.items()):
        try:
            scene.cursor.matrix = cursor
            scene.tool_settings.transform_pivot_point = pivot
            scene.transform_orientation_slots[0].type = orientation
        except ReferenceError:
            pass
    _joint_pivot_sessions.clear()


def _set_joint_pivot(scene, target, socket):
    point = _joint_point(target, socket)
    axis = (target.matrix_world.to_3x3() @ _ARMS[socket]).normalized()
    rotation = Vector((0, 0, 1)).rotation_difference(axis).to_matrix().to_4x4()
    rotation.translation = point
    scene.cursor.matrix = rotation
    scene.tool_settings.transform_pivot_point = 'CURSOR'
    scene.transform_orientation_slots[0].type = 'CURSOR'


def _sync_joint_rotation_guard():
    """Use the shared opening for straights; elbows use checked Builder turns.

    Set the pivot on selection change only. Moving the pivot during a modal
    transform, or restoring it the instant a joint separates, moves its center.
    """
    global _highlight_selection
    from . import undo_guard
    if not undo_guard.history_ready():
        return 0.1
    context = bpy.context
    scene = getattr(context, 'scene', None)
    if scene is None:
        return 0.1
    if _direction_sessions and direction_session(context) is None:
        _clear_direction_sessions()
        refresh(scene)
    if _group_transform_active():
        return 0.1
    if scene.name in _pending_group_refresh:
        _pending_group_refresh.discard(scene.name)
        refresh(scene)
    _sync_draft_shading()
    _sync_elbow_controls(context)
    selection = (context.active_object.as_pointer() if context.active_object else 0,
                 tuple(sorted(obj.as_pointer() for obj in context.selected_objects)))
    highlight_selection = (scene.as_pointer(), selection, context.mode)
    if _highlight_selection != highlight_selection:
        refresh(scene)
        _highlight_selection = highlight_selection
    cached = _joint_pivot_sessions.get(scene.as_pointer())
    if cached:
        try:
            cached[0].as_pointer()
        except ReferenceError:
            cached=None
    if cached and cached[1] == selection and context.mode == 'OBJECT':
        return 0.1
    _restore_joint_rotation_guard()
    _sync_elbow_controls(context)
    joint = _active_tube_joint(context)
    if joint:
        _joint_pivot_sessions[scene.as_pointer()] = (
            scene, selection, scene.cursor.matrix.copy(),
            scene.tool_settings.transform_pivot_point,
            scene.transform_orientation_slots[0].type)
        _set_joint_pivot(scene, joint[1], joint[2])
    return 0.1


@persistent
def _joint_guard_save_pre(_):
    if _direction_sessions:
        _clear_direction_sessions()
        refresh(bpy.context.scene)
    _restore_draft_shading()
    _joint_save_resume.clear()
    for key, session in _joint_pivot_sessions.items():
        try:
            scene = session[0]
            _joint_save_resume[key] = (session, scene.cursor.matrix.copy())
        except ReferenceError:
            pass  # Undo can replace Scene IDs before the quiet period ends.
    _restore_joint_rotation_guard()  # Do not save temporary editing pivots.


@persistent
def _joint_guard_save_post(_):
    for key, (session, cursor) in tuple(_joint_save_resume.items()):
        scene = session[0]
        scene.cursor.matrix = cursor
        scene.tool_settings.transform_pivot_point = 'CURSOR'
        scene.transform_orientation_slots[0].type = 'CURSOR'
        _joint_pivot_sessions[key] = session
    _joint_save_resume.clear()
    _sync_elbow_controls(bpy.context)
    _sync_draft_shading()


@persistent
def _joint_guard_load_pre(_):
    global _highlight_selection
    _clear_direction_sessions()
    _restore_draft_shading()
    _joint_save_resume.clear()
    _restore_joint_rotation_guard()
    _route_cache.clear()
    _junction_option_cache.clear()
    _pending_group_refresh.clear()
    _expansion_preview.clear()
    _highlight_selection = None


class BBE_OT_bubble_joint_pivot(bpy.types.Operator):
    """Choose a checked branch turn without enabling free elbow rotation"""
    bl_idname = 'bbe.bubble_joint_pivot'
    bl_label = 'Rotate Connected Branch'
    bl_description = 'Turn the elbow and attached tubes together; cancel a turn that breaks a working connection'
    bl_options = {'REGISTER', 'UNDO'}

    angle: bpy.props.FloatProperty(name='Turn', subtype='ANGLE',
                                  default=math.pi / 2, min=-math.pi, max=math.pi)

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self, width=380)

    def draw(self, context):
        self.layout.prop(self, 'angle')
        self.layout.label(text='Attached tubes turn together at this joint.')
        self.layout.label(text='Use quarter turns with small supported adjustments.')
        self.layout.label(text='Unsupported joint angles, including 45 degrees, are rejected.')

    def execute(self, context):
        selected = [obj for obj in context.selected_objects
                    if obj.get('ObjectID') == 'BASE_BUBPIPE']
        if len(selected) == 2:
            target = context.active_object
            source = next((obj for obj in selected if obj != target), None)
            candidates = ([(target, _joined_sockets(source, target))]
                          if source is not None and target in selected else [])
        elif len(selected) == 1:
            source = selected[0]
            remembered = context.scene.objects.get(
                source.get('bbe_native_snap_target', ''))
            targets = ([remembered] if remembered is not None else
                       [obj for obj in _native_objects(context.scene)
                        if obj != source])
            candidates = [(obj, _joined_sockets(source, obj)) for obj in targets]
        else:
            self.report({'ERROR'}, 'Select one connected tube, or the moving tube then its target')
            return {'CANCELLED'}
        connected = [(target, sockets) for target, sockets in candidates if sockets]
        if len(connected) != 1:
            self.report({'ERROR'}, 'Choose one tube joint: select the moving tube, then its neighbor last')
            return {'CANCELLED'}
        target, (target_socket, _) = connected[0]
        previous_selection = list(context.selected_objects)
        previous_active = context.view_layer.objects.active
        keys = ('bbe_native_snap_target', 'bbe_native_target_socket', 'bbe_native_source_socket')
        previous_snap = {key: source.get(key) for key in keys}
        try:
            for obj in previous_selection:
                obj.select_set(False)
            source.select_set(True)
            context.view_layer.objects.active = source
            source[keys[0]], source[keys[1]], source[keys[2]] = target.name, target_socket, connected[0][1][1]
            return bpy.ops.bbe.turn_bubble_elbow(
                direction=1 if self.angle >= 0 else -1, angle=abs(self.angle))
        finally:
            for key, value in previous_snap.items():
                if value is None:
                    source.pop(key, None)
                else:
                    source[key] = value
            source.select_set(False)
            for obj in previous_selection:
                obj.select_set(True)
            context.view_layer.objects.active = previous_active
            _sync_elbow_controls(context)


def snap_native(source, target, next_target=False, prev_target=False,
                next_source=False, prev_source=False):
    """Place a fixed duct at a free visible opening of another duct.

    Keep the preview's fixed shape and align one of its drawn openings with a
    free drawn opening on the target. Native frames are encoded on export.
    The source controls cycle orientations,
    including the roll needed to turn the other end of an elbow into a loop.
    """
    if (source == target or source.get('ObjectID') != 'BASE_BUBPIPE'
            or target.get('ObjectID') != 'BASE_BUBPIPE'):
        return False
    scene = target.users_scene[0] if target.users_scene else bpy.context.scene
    branch = [source]
    if _joined_sockets(source, target):
        branch = _moving_branch(source, target, scene)
        if branch is None and (next_source or prev_source or next_target or prev_target):
            return False
        branch = branch or [source]
    original_source = source.matrix_world.copy()
    downstream = {obj: obj.matrix_world.copy() for obj in branch if obj != source}

    def carry_branch():
        delta = source.matrix_world @ original_source.inverted_safe()
        for obj, matrix in downstream.items():
            obj.matrix_world = delta @ matrix
        scene.view_layers[0].update()

    others = [obj for obj in _native_objects(scene) if obj != source]
    before = _editor_contacts(others)
    occupied = before.get(target.name, set())
    if not others or target not in others:
        return False
    center = Vector((0, 1, 0))
    source_center = source.matrix_world @ center
    choices = []
    for name in _visible_sockets(target):
        if name in occupied:
            continue
        arm = _ARMS[name]
        candidate = target.matrix_world @ (center + 2 * arm)
        choices.append(((candidate - source_center).length_squared, name, arm))
    if not choices:
        return False
    choices.sort(key=lambda entry: entry[1])
    same_target = source.get('bbe_native_snap_target') == target.name
    old_target = source.get('bbe_native_target_socket') if same_target else None
    target_names = [entry[1] for entry in choices]
    if old_target in target_names:
        target_index = target_names.index(old_target)
    elif not occupied and target.get(_START_KEY) in target_names:
        target_index = target_names.index(target[_START_KEY])
    else:
        target_index = min(range(len(choices)), key=lambda i: choices[i][0])
    target_index = (target_index + int(next_target) - int(prev_target)) % len(choices)
    _, name, arm = choices[target_index]

    # Source Prev/Next rolls around the shared opening, without changing
    # which end is attached or swinging around the object's native origin.
    joint = _joined_sockets(source, target) if same_target else None
    if (same_target and old_target == name and (next_source or prev_source)
            and joint is not None and joint[0] == name):
        _roll_about_joint(source, target, name, 1 if next_source else -1)
        carry_branch()
        refresh(scene)
        return name

    options = []
    for source_socket in _visible_sockets(source):
        for rotation in _ROTATIONS:
            if (rotation.to_3x3() @ _ARMS[source_socket] + arm).length > 1e-5:
                continue
            key = (source_socket, tuple(round(value) for row in rotation for value in row))
            # A native duct's anchor lies one unit below its visible centre.
            matrix = (target.matrix_world @ Matrix.Translation(center + 2 * arm)
                      @ rotation @ Matrix.Translation(-center))
            options.append((key, matrix))
    if not options:
        return False
    previous_socket = (source.get('bbe_native_source_socket') or
                       (joint[1] if joint is not None else None)) if same_target else None
    if previous_socket in _visible_sockets(source):
        matching = [entry for entry in options if entry[0][0] == previous_socket]
        if matching:
            options = matching
    options.sort(key=lambda entry: entry[0])
    current_rotation = source.matrix_world.to_quaternion()
    source_index = max(range(len(options)), key=lambda i:
                       abs(current_rotation.dot(options[i][1].to_quaternion())))
    original_matrix = source.matrix_world.copy()
    step = -1 if prev_source else 1
    chosen = None
    for distance in range(len(options)):
        candidate_index = (source_index + distance * step) % len(options)
        source.matrix_world = options[candidate_index][1]
        candidate_center = source.matrix_world @ center
        if any((obj.matrix_world @ center - candidate_center).length < 1e-4
               for obj in others):
            continue
        chosen = candidate_index
        break
    if chosen is None:
        source.matrix_world = original_matrix
        return False
    source_index = chosen
    source['snapped_to'] = target.name
    source['bbe_native_snap_target'] = target.name
    source['bbe_native_target_socket'] = name
    source['bbe_native_source_socket'] = options[source_index][0][0]
    source['bbe_native_source_option'] = source_index
    if next_source or prev_source:
        _roll_about_joint(source, target, name, 1 if next_source else -1)
    carry_branch()
    refresh(scene)
    return name


def add_native_bend_point(builder, target=None, cursor=None):
    """Start or extend a planned bend; incomplete bends show native fallback."""
    from . import builder_v2

    if target is not None and target.get('ObjectID') == 'BASE_BUBPIPE_L':
        raise ValueError('This is an old preview-only corner. Convert the route first.')
    if target is not None and target.get('ObjectID') != 'BASE_BUBPIPE':
        target = None
    scene = target.users_scene[0] if target is not None and target.users_scene else bpy.context.scene
    if target is None:
        matrix = Matrix.Translation(Vector(cursor) if cursor is not None else scene.cursor.location)
    else:
        intent = str(target.get(_INTENT_KEY, ''))
        if not intent.startswith(('STRAIGHT:',) + _JUNCTION_PREFIXES):
            raise ValueError('Select a tube with an open end to extend it.')
        problem = placement_error(target, scene)
        if problem:
            raise ValueError(problem)
        connected = _editor_contacts(_native_objects(scene)).get(target.name, set())
        available = set(_visible_sockets(target)) - connected
        preferred = target.get(_START_KEY)
        direction = (preferred if not connected and preferred in available else
                     'Top' if 'Top' in available else sorted(available)[0])
        matrix = target.matrix_world @ Matrix.Translation(2 * _ARMS[direction])
    part = builder_v2.add_part('BASE_BUBPIPE', builder_object=builder)
    try:
        if target is None:
            matrix = part.object.matrix_world.copy()
            matrix.translation = Vector(cursor) if cursor is not None else scene.cursor.location
        part.object.matrix_world = matrix
        part.object[_INTENT_KEY] = 'ELBOW:Bot+Front'
        if target is not None and not snap_native(part.object, target):
            raise ValueError('No safe elbow orientation at this end. Move nearby ducts farther apart first.')
        scene.view_layers[0].update()
        refresh(scene)
        return part
    except BaseException:
        bpy.data.objects.remove(part.object, do_unlink=True)
        raise


def add_native_elbow(builder, target=None, cursor=None):
    """Create a placeable game elbow from native duct nodes.

    With a selected end duct, add a corner and an end duct. Otherwise create
    the same three-node elbow that was verified in game. Return the end part so
    the next Asset Browser click can continue the route.
    """
    from . import builder_v2

    if target is not None and target.get('ObjectID') == 'BASE_BUBPIPE_L':
        raise ValueError('This is an old preview-only corner. Convert the route first.')
    if target is not None and target.get('ObjectID') != 'BASE_BUBPIPE':
        target = None
    if target is not None:
        scene = target.users_scene[0] if target.users_scene else bpy.context.scene
        connected = _snapped(_native_objects(scene)).get(target.name, set())
        if len(connected) > 1:
            raise ValueError('Select an end bubble duct to extend. This duct already has multiple connections.')
        if len(connected) == 1:
            existing = next(iter(connected))
            direction = next(name for name, arm in _ARMS.items()
                             if arm.dot(_ARMS[existing]) == -1)
        else:
            direction = target.get(_START_KEY, 'Top')
        branch = 'Front' if direction in {'Top', 'Bot'} else 'Top'
        base = target.matrix_world.copy()
        positions = (base @ Matrix.Translation(2 * _ARMS[direction]),
                     base @ Matrix.Translation(2 * (_ARMS[direction] + _ARMS[branch])))
    else:
        scene = bpy.context.scene
        origin = Vector(cursor if cursor is not None else scene.cursor.location)
        base = Matrix.Translation(origin)
        positions = (base, base @ Matrix.Translation((0, 2, 0)),
                     base @ Matrix.Translation((0, 2, -2)))
    made = []
    try:
        for matrix in positions:
            part = builder_v2.add_part('BASE_BUBPIPE', builder_object=builder)
            part.object.matrix_world = matrix
            made.append(part)
        scene.view_layers[0].update()
        refresh(scene)
        return made[-1], made
    except BaseException:
        for part in reversed(made):
            bpy.data.objects.remove(part.object, do_unlink=True)
        raise


def _rotation_between_pairs(source_a, source_b, first, second):
    """Map two orthogonal source arms to two native socket directions."""
    source_c = source_a.cross(source_b)
    target_a = _ARMS[first]
    target_b = _ARMS[second]
    target_c = target_a.cross(target_b)
    source = Matrix((source_a, source_b, source_c)).transposed()
    target = Matrix((target_a, target_b, target_c)).transposed()
    return (target @ source.transposed()).to_4x4()


def _display_spec(snaps, high_res):
    names = tuple(sorted(snaps))
    if len(names) == 2 and _ARMS[names[0]].dot(_ARMS[names[1]]) == 0:
        # The authored elbow's openings are -Y and +Z around its own origin.
        # Native socket pairs sit one unit from the node's centre (0,1,0).
        transform = Matrix.Translation((0, 1, 0)) @ _rotation_between_pairs(
            Vector((0, -1, 0)), Vector((0, 0, 1)), *names)
        return 'BASE_BUBPIPE_L', 'ELBOW:' + '+'.join(names), transform
    if len(names) == 3:
        opposite = next(((left, right) for left in names for right in names
                         if left < right and _ARMS[left].dot(_ARMS[right]) == -1), None)
        if opposite is not None:
            branch = next(name for name in names if name not in opposite)
            transform = Matrix.Translation((0, 1, 0)) @ _rotation_between_pairs(
                Vector((0, 1, 0)), Vector((0, 0, 1)), branch, opposite[0])
            return '_PIPEBUBBLET', 'TEE:' + '+'.join(names), transform
        # The native three-way corner is authored along +X,+Y,+Z. The
        # placement entity maps all eight sign combinations to this mesh.
        for order in permutations(names):
            rotation = Matrix(tuple(_ARMS[p] for p in order)).transposed()
            if rotation.determinant() > 0:
                transform = Matrix.Translation((0, 1, 0)) @ rotation.to_4x4()
                return '_PIPEBUBBLE3CORNER', 'CORNER3:' + '+'.join(names), transform
    if len(names) == 4 and all(any(_ARMS[p].dot(_ARMS[q]) == -1 for q in names) for p in names):
        first = names[0]
        second = next(p for p in names if _ARMS[p].dot(_ARMS[first]) == 0)
        # Native _PIPEBUBBLEX is authored in the YZ plane (verified game rule).
        transform = Matrix.Translation((0, 1, 0)) @ _rotation_between_pairs(
            Vector((0, 1, 0)), Vector((0, 0, 1)), first, second)
        return '_PIPEBUBBLEX', 'CROSS:' + '+'.join(names), transform
    if len(names) >= 4:
        # Identity orientations from the game's PIPEBUBBLE_PLACEMENT rules.
        source_id, kind, authored = {
            4: ('_PIPEBUBBLE4CORNER', 'CORNER4', ('Bot', 'Front', 'Right', 'Top')),
            5: ('_PIPEBUBBLESTARHALF', 'FIVE', ('Back', 'Front', 'Left', 'Right', 'Top')),
            6: ('_PIPEBUBBLESTAR', 'SIX', tuple(_ARMS)),
        }[len(names)]
        wanted = {tuple(_ARMS[p]) for p in names}
        for rotation in _ROTATIONS:
            if {tuple(rotation.to_3x3() @ _ARMS[p]) for p in authored} == wanted:
                return source_id, kind + ':' + '+'.join(names), Matrix.Translation((0, 1, 0)) @ rotation
    if not names or set(names).issubset({'Top', 'Bot'}):
        if high_res:
            return 'BASE_BUBPIPE', 'STRAIGHT:Y', None
        return ('BASE_BUBPIPE', 'STRAIGHT:Y',
                Matrix.Translation((0, 1, 0)) @ Matrix.Rotation(-math.pi / 2, 4, 'X'))
    if set(names).issubset({'Front', 'Back'}):
        if high_res:
            rotation = Matrix.Rotation(math.pi / 2, 4, 'X')
            return 'BASE_BUBPIPE', 'STRAIGHT:Z', Matrix.Translation((0, 1, -1)) @ rotation
        return 'BASE_BUBPIPE', 'STRAIGHT:Z', Matrix.Translation((0, 1, 0))
    if set(names).issubset({'Left', 'Right'}):
        if high_res:
            rotation = Matrix.Rotation(-math.pi / 2, 4, 'Z')
            return 'BASE_BUBPIPE', 'STRAIGHT:X', Matrix.Translation((-1, 1, 0)) @ rotation
        return ('BASE_BUBPIPE', 'STRAIGHT:X',
                Matrix.Translation((0, 1, 0)) @ Matrix.Rotation(math.pi / 2, 4, 'Y'))
    # More than two occupied directions use other game-generated variants.
    fallback = (None if high_res else Matrix.Translation((0, 1, 0))
                @ Matrix.Rotation(-math.pi / 2, 4, 'X'))
    return 'BASE_BUBPIPE', 'UNRESOLVED:' + '+'.join(names), fallback


def _group_transform_active():
    """Leave every native transform alone until confirm or cancel.

    A single cube's gizmo also shares the viewport with bubble previews.
    """
    context = bpy.context
    return any(op.bl_idname.startswith('TRANSFORM_OT_')
               for window in getattr(getattr(context, 'window_manager', None), 'windows', ())
               for op in window.modal_operators)


def request_refresh(scene):
    """Defer dependency-graph work to the guarded timer, outside evaluation."""
    if scene is not None and not _refreshing:
        _pending_group_refresh.add(scene.name)


def refresh(scene):
    """Update native duct meshes after import, placement, move, or undo."""
    global _refreshing
    if _refreshing or scene is None:
        return 0
    if _group_transform_active():
        _pending_group_refresh.add(scene.name)
        return 0
    parts = _native_objects(scene)
    if not parts:
        _sync_draft_shading()
        return 0
    view_layer = bpy.context.view_layer if bpy.context.scene == scene else None
    selected = tuple(obj for obj in view_layer.objects if obj is not None and obj.select_get()) if view_layer else ()
    active = view_layer.objects.active if view_layer else None
    _refreshing = True
    try:
        from . import builder_v2

        try:
            parts, (_, issues, displays) = _scene_plan(scene)
        except ValueError:
            return 0  # Keep the last mesh during a zero-scale drag; status explains it.
        changed = 0
        editor_contacts = _editor_contacts(parts)
        port_links = _editor_port_links(parts)
        # Use exactly the palette's target. Amber means "this part will change"
        # for straights and corners alike, not a route-wide warning color.
        from .bubble_controls import available_junction
        preview_active = bpy.context.active_object
        target = None
        if (bpy.context.mode == 'OBJECT' and len(bpy.context.selected_objects) == 1
                and preview_active in parts and preview_active.select_get()):
            target, _ = available_junction(scene, preview_active, parts, issues)
        for index, obj in enumerate(parts):
            high_res = 'nms_high_res_id' in obj.data
            if _MESH_QUALITY in obj.data:
                high_res = obj.data[_MESH_QUALITY] == 'high'
            (center, rotation, scale), view_sockets = displays[index]
            native_matrix = rotation.to_4x4()
            for column in range(3):
                native_matrix.col[column] *= scale
            native_matrix.translation = center - rotation.col[1] * scale
            relative = obj.matrix_world.inverted_safe() @ native_matrix
            preview = _expansion_preview.get((scene.as_pointer(), obj.name))
            draft = bool(preview) or (_is_junction(obj) and (
                len(editor_contacts[obj.name]) < len(_visible_sockets(obj))
                or (len(_visible_sockets(obj)) >= 3 and not _branches_complete(obj, parts, port_links))))
            conflict = _is_junction(obj) and index in issues and not draft
            highlighted = obj == target
            # An unfinished junction can still have a complete native shape.
            # Use that planned frame so mirroring changes the visible handedness
            # as well as the export. Only fall back to the edit hint when the
            # planner cannot represent the intended number of openings yet.
            if preview or conflict or (draft and len(view_sockets) != len(_visible_sockets(obj))):
                view_sockets = preview.split(':', 1)[1].split('+') if preview else _visible_sockets(obj)
                relative = Matrix.Identity(4)
            source_id, key, transform = _display_spec(view_sockets, high_res)
            if draft:
                key = 'DRAFT/' + key
            elif conflict:
                key = 'WARNING/' + key
            if highlighted:
                key = 'TARGET/' + key
            transform = relative @ (transform if transform is not None else Matrix.Identity(4))
            # Private copies for differing frames keep drag updates bounded.
            variant = any(abs(relative[i][j] - float(i == j)) > 1e-5
                          for i in range(4) for j in range(4))
            if variant:
                key += '/' + ','.join(str(round(v, 5)) for row in relative for v in row)
            user_data = str(obj.get('UserData', 0))
            cache_key = key if high_res else key + '/' + user_data
            if (obj.data.get(_MESH_KEY) == cache_key
                    and obj.data.get(_MESH_REVISION) == _PREVIEW_REVISION):
                continue
            import hashlib
            mesh_name = ('NMS_NATIVE_BUBBLE_' + ('HR_' if high_res else 'LR_')
                         + hashlib.sha1(f'{_PREVIEW_REVISION}/{cache_key}'.encode('utf-8')).hexdigest()[:24])
            display = bpy.data.meshes.get(mesh_name)
            if display is not None and (display.get(_MESH_KEY) != cache_key
                                       or display.get(_MESH_REVISION) != _PREVIEW_REVISION):
                display = None
            if display is None and high_res:
                source = builder_v2.load_high_res_mesh(source_id, force=True)
                if source is None:
                    continue
                if transform is None:
                    display = source
                else:
                    display = source.copy()
                    display.name = mesh_name
                    display.transform(transform)
                    display[_MESH_KEY] = cache_key
                    display[_MESH_QUALITY] = 'high'
                    display[_MESH_REVISION] = _PREVIEW_REVISION
            elif display is None:
                previous = obj.data
                if not builder_v2.apply_proxy_mesh(obj, source_id, user_data):
                    continue
                display = obj.data.copy()
                display.name = mesh_name
                display.transform(transform)
                if 'nms_proxy_placement' in display:
                    del display['nms_proxy_placement']
                display[_MESH_KEY] = cache_key
                display[_MESH_QUALITY] = 'low'
                display[_MESH_REVISION] = _PREVIEW_REVISION
            else:
                # Existing preview cache already has the correct geometry and
                # per-UserData flat material for low-detail proxies.
                pass
            if highlighted and not display.get('bbe_bubble_target'):
                display.materials.clear()
                display.materials.append(_conflict_material())
                for polygon in display.polygons:
                    polygon.material_index = 0
                display['bbe_bubble_target'] = True
                if draft:
                    display['bbe_bubble_draft'] = True
            elif draft and not display.get('bbe_bubble_draft'):
                display.materials.clear()
                display.materials.append(_draft_material(0))
                display.materials.append(_draft_material(1))
                display.update()
                first, second = (_ARMS[port] for port in _visible_sockets(obj)[:2])
                bend_center = Vector((0, 1, 0)) + first + second
                for polygon in display.polygons:
                    # Geometry bands remain visible in Solid/Material shading,
                    # unlike shader-only transparency or object-color overrides.
                    offset = polygon.center - bend_center
                    angle = math.atan2(-offset.dot(second), -offset.dot(first))
                    polygon.material_index = (int(.53 < angle < 1.04) if _is_elbow(obj)
                                              else int(.65 < (polygon.center-Vector((0,1,0))).length < .9))
                display['bbe_bubble_draft'] = True
            if conflict:
                display['bbe_bubble_conflict'] = True
            if obj.data != display:
                previous = obj.data
                obj.data = display
                if variant:
                    display['bbe_bubble_variant'] = True
                # Undo states can still refer to a zero-user preview mesh.
                changed += 1
        _sync_draft_shading()
        return changed
    finally:
        # Mesh loading may use an FBX import internally, which deselects objects.
        # A preview refresh must never interrupt the user's selected tube/tool.
        if view_layer is not None:
            try:
                for obj in tuple(o for o in view_layer.objects if o is not None and o.select_get()):
                    if obj not in selected:
                        obj.select_set(False)
                for obj in selected:
                    if not obj.select_get():
                        obj.select_set(True)
                if view_layer.objects.active != active:
                    view_layer.objects.active = active
            except ReferenceError:
                pass
        _refreshing = False


def lock_scene_shapes(scene):
    """Record loaded native duct shapes once, after all save parts are present."""
    parts = _native_objects(scene)
    snapped = _native_contacts(parts)
    for obj in parts:
        if _INTENT_KEY not in obj:
            _, key, _ = _display_spec(snapped[obj.name], True)
            if not key.startswith('UNRESOLVED:'):
                obj[_INTENT_KEY] = key


def inspect_loaded_tubes(scene):
    """Repair persisted hints and rebuild previews without changing placements.

    Valid editor intentions include unfinished bends; preserve those and report
    connection problems instead of silently straightening the user's build.
    """
    from .bubble_export import sockets
    parts = _native_objects(scene)
    try:
        snapped = _native_contacts(parts)
    except ValueError as exc:
        return dict(tubes=len(parts), repaired=0, previews=0,
                    problems=(str(exc),), legacy=0)
    repaired = 0
    for obj in parts:
        intent = obj.get(_INTENT_KEY, '')
        ports = sockets(intent) if isinstance(intent, str) else ()
        canonical = _display_spec(ports, True)[1] if ports else None
        valid = canonical and intent.split(':', 1)[0] == canonical.split(':', 1)[0]
        wanted = canonical if valid else _display_spec(snapped[obj.name], True)[1]
        if not wanted.startswith('UNRESOLVED:') and wanted != intent:
            obj[_INTENT_KEY] = wanted
            repaired += 1
        if _START_KEY in obj and obj[_START_KEY] not in _visible_sockets(obj):
            del obj[_START_KEY]
            repaired += 1
    for obj in parts:
        keys = ('bbe_native_snap_target', 'bbe_native_target_socket', 'bbe_native_source_socket')
        if not any(key in obj for key in keys):
            continue
        target = scene.objects.get(str(obj.get(keys[0], '')))
        pair = (obj.get(keys[1]), obj.get(keys[2]))
        if (target not in parts or target == obj
                or pair[0] not in _visible_sockets(target)
                or pair[1] not in _visible_sockets(obj)
                or _joined_sockets(obj, target) != pair):
            for key in keys:
                if key in obj:
                    del obj[key]
            repaired += 1
    _route_cache.clear()
    _junction_option_cache.clear()
    changed = refresh(scene)
    try:
        _, (_, issues, _) = _scene_plan(scene)
        problems = tuple(issues.values())
    except ValueError as exc:
        problems = (str(exc),)
    legacy = sum(obj.get('ObjectID') == 'BASE_BUBPIPE_L' for obj in scene.objects)
    return dict(tubes=len(parts), repaired=repaired, previews=changed,
                problems=problems, legacy=legacy)


def can_set_start_direction(scene, obj):
    return (obj is not None and obj.get('ObjectID') == 'BASE_BUBPIPE'
            and str(obj.get(_INTENT_KEY, '')).startswith('STRAIGHT:')
            and not _editor_contacts(_native_objects(scene)).get(obj.name))


class BBE_OT_bubble_start_direction(bpy.types.Operator):
    bl_idname = 'bbe.bubble_start_direction'
    bl_label = 'Set Tube Starting Direction'
    bl_description = 'Aim an unconnected straight tube and choose the end for its first connection, using tube-local axes'
    bl_options = {'REGISTER', 'UNDO'}

    port: bpy.props.EnumProperty(name='Direction', items=[
        ('Right', '+X', 'Start toward local +X'), ('Left', '-X', 'Start toward local -X'),
        ('Top', '+Y', 'Start toward local +Y'), ('Bot', '-Y', 'Start toward local -Y'),
        ('Front', '+Z', 'Start toward local +Z'), ('Back', '-Z', 'Start toward local -Z')])

    @classmethod
    def poll(cls, context):
        return (context.mode == 'OBJECT' and len(context.selected_objects) == 1
                and can_set_start_direction(context.scene, context.active_object))

    def execute(self, context):
        obj = context.active_object
        axis = {'Left': 'X', 'Right': 'X', 'Top': 'Y', 'Bot': 'Y', 'Front': 'Z', 'Back': 'Z'}[self.port]
        obj[_INTENT_KEY] = 'STRAIGHT:' + axis
        obj[_START_KEY] = self.port
        refresh(context.scene)
        return {'FINISHED'}


class BBE_OT_repair_bubble_tubes(bpy.types.Operator):
    bl_idname = 'bbe.repair_bubble_tubes'
    bl_label = 'Check & Repair Bubble Tubes'
    bl_description = 'Check loaded tube shapes, repair old metadata and refresh previews; preserve tube positions'
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        result = inspect_loaded_tubes(context.scene)
        message = (f"Checked {result['tubes']} tubes; repaired {result['repaired']} records; "
                   f"refreshed {result['previews']} previews.")
        if result['problems']:
            message += f" {len(result['problems'])} connection issue(s): {result['problems'][0]}"
        if result['legacy']:
            message += f" {result['legacy']} legacy corners: use Convert Old Bubble Corners."
        self.report({'WARNING'} if result['problems'] or result['legacy'] else {'INFO'}, message)
        return {'FINISHED'}


def _scene_plan(scene):
    from . import bubble_export
    parts = _native_objects(scene)
    signature = tuple((obj.name, str(obj.get(_INTENT_KEY, '')),
                       tuple(value for row in obj.matrix_world for value in row))
                      for obj in parts)
    cached = _route_cache.get(scene.as_pointer())
    if cached is not None and cached[0] == signature:
        return parts, cached[1]
    records, hints = [], {}
    for i, obj in enumerate(parts):
        matrix = obj.matrix_world
        records.append({'ObjectID': '^BASE_BUBPIPE', 'Position': list(matrix.translation),
                        'Up': list(matrix.col[1].to_3d()), 'At': list(matrix.col[2].to_3d().normalized())})
        if obj.get(_INTENT_KEY):
            hints[i] = {'name': obj.name, 'shape': obj[_INTENT_KEY]}
    plan = bubble_export.plan_objects(records, hints)
    _route_cache.clear()
    _junction_option_cache.clear()
    _route_cache[scene.as_pointer()] = signature, plan
    return parts, plan


def validate_game_shapes(scene):
    _, (_, issues, _) = _scene_plan(scene)
    if issues:
        raise ValueError(next(iter(issues.values())))


def route_status(scene):
    try:
        validate_game_shapes(scene)
    except ValueError as exc:
        return False, str(exc)
    return True, 'Tube shapes match the tested connection model.'


def junction_option(scene, obj):
    """Offer a replacement supported by actual neighboring drawn openings."""
    return connection_junction_option(scene, obj)


def connection_junction_option(scene, obj, source=None):
    _scene_plan(scene)  # Invalidates option results when transforms/intents change.
    key = (scene.as_pointer(), obj.name if obj else None, source.name if source else None)
    if key not in _junction_option_cache:
        _junction_option_cache[key] = _connection_junction_option(scene, obj, source)
    return _junction_option_cache[key]


def _connection_junction_option(scene, obj, source=None):
    """Include a visible build tip meeting the side of a straight or tee.

    Ordinary export protects straight tubes from unintended side contacts.
    An explicit junction action can instead connect the selected opening there.
    Validate the proposed visible connection without mutating the scene.
    Native proximity warnings remain export checks; they must not hide a
    geometrically valid way to finish the selected branch.
    """
    if obj is None:
        return None
    parts, _ = _scene_plan(scene)
    if obj not in parts or (source is not None and source not in parts):
        return None
    visible = set(_visible_sockets(obj))
    wanted = set()
    source_touches = source is None or source == obj
    for neighbor in parts:
        if neighbor == obj:
            continue
        tolerance = .025 * max(*(abs(v) for v in obj.matrix_world.to_scale()),
                                *(abs(v) for v in neighbor.matrix_world.to_scale()))
        for port in _visible_sockets(neighbor):
            point = _joint_point(neighbor, port)
            direction = (neighbor.matrix_world.to_3x3() @ _ARMS[port]).normalized()
            for other in _ARMS:
                opposite = (obj.matrix_world.to_3x3() @ _ARMS[other]).normalized()
                if ((point - _joint_point(obj, other)).length <= tolerance
                        and direction.dot(opposite) < -.9999):
                    wanted.add(other)
                    source_touches |= neighbor == source
    # Never convert an open elbow because two hidden game sockets happen to
    # coincide. Every retained or added arm needs a visible neighboring opening.
    if not source_touches or not visible < wanted:
        return None
    links = _editor_port_links(parts, {obj.name: wanted})
    if not _branches_complete(obj, parts, links, ports=wanted):
        return None
    _, intent, _ = _display_spec(wanted, True)
    labels = JUNCTION_LABELS
    kind = intent.split(':')[0]
    if kind not in labels:
        return None
    return intent, labels[kind]


def draft_cross_option(scene, obj, source=None):
    """Reserve the fourth coplanar arm while choosing a proposed tee."""
    if obj is None:
        return None
    option = connection_junction_option(scene, obj, source)
    intent = option[0] if option else ''
    if not intent.startswith('TEE:'):
        return None
    ports = set(intent.split(':', 1)[1].split('+'))
    original_ports = set(ports)
    from .bubble_export import OPPOSITE
    ports.update(OPPOSITE[p] for p in tuple(ports))
    if any(not _opening_clear(obj, port, _native_objects(scene)) for port in ports - original_ports):
        return None
    _, cross, _ = _display_spec(ports, True)
    return (cross, 'draft + junction') if cross.startswith('CROSS:') else None


def junction_export_issues(scene, obj, intent):
    """Keep native export warnings visible while allowing local construction."""
    from . import bubble_export as ex
    parts, _ = _scene_plan(scene)
    key = ('export', scene.as_pointer(), obj.name, intent)
    if key not in _junction_option_cache:
        records, hints = [], {}
        for i, part in enumerate(parts):
            matrix = part.matrix_world
            records.append({'ObjectID': '^BASE_BUBPIPE', 'Position': list(matrix.translation),
                            'Up': list(matrix.col[1].to_3d()),
                            'At': list(matrix.col[2].to_3d().normalized())})
            if part.get(_INTENT_KEY):
                hints[i] = {'name': part.name, 'shape': intent if part == obj else part[_INTENT_KEY]}
        _junction_option_cache[key] = ex.plan_objects(records, hints)[1]
    return _junction_option_cache[key]


def direction_choices(scene, obj, kind, change=False):
    grouped = redirect_options(scene, obj) if change else expansion_options(scene, obj)
    return dict(item for shape, values in grouped.items() if change or shape == kind for item in values)


def direction_session(context):
    obj = context.active_object
    if obj is None or len(context.selected_objects) != 1 or context.mode != 'OBJECT':
        return None
    state = _direction_sessions.get((context.scene.as_pointer(), obj.name))
    return state if state and state['base'] == obj.get(_INTENT_KEY) else None


@persistent
def _clear_direction_sessions(_=None):
    # No RNA access or mesh edits inside Undo/Redo callbacks.
    _direction_sessions.clear()
    _expansion_preview.clear()


class BBE_OT_choose_bubble_opening(bpy.types.Operator):
    bl_idname = 'bbe.choose_bubble_opening'
    bl_label = 'Choose Opening Direction'
    bl_description = 'Preview the opening using the tube panel beside the part'
    obj_name: bpy.props.StringProperty()
    kind: bpy.props.StringProperty()
    change_direction: bpy.props.BoolProperty(default=False)

    def execute(self, context):
        obj = context.scene.objects.get(self.obj_name)
        if obj is None or obj != context.active_object or len(context.selected_objects) != 1:
            return {'CANCELLED'}
        choices = direction_choices(context.scene, obj, self.kind, self.change_direction)
        if not choices:
            self.report({'WARNING'}, 'There is no clear direction for this opening.')
            return {'CANCELLED'}
        _clear_direction_sessions()
        key = (context.scene.as_pointer(), obj.name)
        port = next(iter(choices))
        _direction_sessions[key] = {'base': obj[_INTENT_KEY], 'kind': self.kind,
                                    'change': self.change_direction, 'port': port}
        _expansion_preview[key] = choices[port]
        refresh(context.scene)
        return {'FINISHED'}


class BBE_OT_preview_bubble_opening(bpy.types.Operator):
    bl_idname = 'bbe.preview_bubble_opening'
    bl_label = 'Preview Opening Direction'
    bl_description = 'Cycle clear directions, or cancel the preview without changing the tube'
    action: bpy.props.EnumProperty(items=[('PREV', 'Previous', ''), ('NEXT', 'Next', ''), ('CANCEL', 'Cancel', '')])

    def execute(self, context):
        state = direction_session(context)
        if state is None:
            return {'CANCELLED'}
        if self.action == 'CANCEL':
            _clear_direction_sessions()
        else:
            obj = context.active_object
            choices = direction_choices(context.scene, obj, state['kind'], state['change'])
            if not choices:
                _clear_direction_sessions()
            else:
                ports = list(choices)
                current = ports.index(state['port']) if state['port'] in ports else 0
                port = ports[(current + (1 if self.action == 'NEXT' else -1)) % len(ports)]
                state['port'] = port
                _expansion_preview[(context.scene.as_pointer(), obj.name)] = choices[port]
        refresh(context.scene)
        return {'FINISHED'}


class BBE_OT_remove_bubble_opening(bpy.types.Operator):
    bl_idname = 'bbe.remove_bubble_opening'
    bl_label = 'Remove Unused Opening'
    bl_description = 'Remove this unused branch while keeping every connected opening'
    bl_options = {'REGISTER', 'UNDO'}
    obj_name: bpy.props.StringProperty()

    def execute(self, context):
        obj = context.scene.objects.get(self.obj_name)
        if obj is None or obj != context.active_object or len(context.selected_objects) != 1:
            return {'CANCELLED'}
        opening = editable_opening(context.scene, obj)
        if not opening:
            self.report({'WARNING'}, 'Only an unused opening can be removed.')
            return {'CANCELLED'}
        obj[_INTENT_KEY] = _display_spec(opening[1], True)[1]
        _clear_direction_sessions()
        refresh(context.scene)
        return {'FINISHED'}


class BBE_OT_expand_bubble_junction(bpy.types.Operator):
    """Preview one extra opening on the selected, completed junction"""
    bl_idname = 'bbe.expand_bubble_junction'
    bl_label = 'Add One Tube Opening'
    bl_description = 'Preview one new branch; finish it before adding another opening'
    bl_options = {'REGISTER', 'UNDO'}

    obj_name: bpy.props.StringProperty()
    kind: bpy.props.StringProperty()
    change_direction: bpy.props.BoolProperty(default=False)
    port: bpy.props.EnumProperty(items=[
        ('Front', 'Forward', 'New opening along the tube local +Z direction'),
        ('Back', 'Backward', 'New opening along the tube local -Z direction'),
        ('Left', 'Left', 'New opening along the tube local -X direction'),
        ('Right', 'Right', 'New opening along the tube local +X direction'),
        ('Top', 'Up', 'New opening along the tube local +Y direction'),
        ('Bot', 'Down', 'New opening along the tube local -Y direction'),
    ])

    def _options(self, context):
        obj = context.scene.objects.get(self.obj_name)
        return direction_choices(context.scene, obj, self.kind, self.change_direction)

    def _clear_preview(self, context):
        _clear_direction_sessions()
        refresh(context.scene)

    def execute(self, context):
        obj = context.scene.objects.get(self.obj_name)
        self._clear_preview(context)
        if (obj is None or context.active_object != obj or len(context.selected_objects) != 1):
            self.report({'WARNING'}, 'Select the junction you want to expand.')
            return {'CANCELLED'}
        intent = self._options(context).get(self.port)
        if intent is None:
            self.report({'WARNING'}, 'This direction is blocked or the branch is unfinished. Choose a clear direction.')
            return {'CANCELLED'}
        old_intent = obj.get(_INTENT_KEY)
        if intent == old_intent:
            return {'CANCELLED'}
        parts, (_, before, _) = _scene_plan(context.scene)
        obj[_INTENT_KEY] = intent
        _, (_, after, _) = _scene_plan(context.scene)
        if after.keys() - before.keys() - {parts.index(obj)}:
            obj[_INTENT_KEY] = old_intent
            refresh(context.scene)
            self.report({'WARNING'}, 'That opening conflicts with a nearby tube. Choose another direction.')
            return {'CANCELLED'}
        refresh(context.scene)
        _sync_elbow_controls(context)
        self.report({'INFO'}, 'Opening redirected. Connected tubes stayed in place.' if self.change_direction else
                    'Opening added. Connect a straight, or add an elbow and finish its far end.')
        return {'FINISHED'}


class BBE_OT_accept_bubble_junction(bpy.types.Operator):
    """Use the junction the game would create at the current tube contacts"""
    bl_idname = 'bbe.accept_bubble_junction'
    bl_label = 'Use Tube Junction'
    bl_description = 'Use the junction detected at this connection; keep the tubes in place'
    bl_options = {'REGISTER', 'UNDO'}

    obj_name: bpy.props.StringProperty()
    source_name: bpy.props.StringProperty()
    draft_cross: bpy.props.BoolProperty(default=False)

    def execute(self, context):
        obj = context.scene.objects.get(self.obj_name)
        source = context.scene.objects.get(self.source_name) if self.source_name else None
        from .bubble_controls import available_junction
        active = context.active_object
        parts, (_, issues, _) = _scene_plan(context.scene)
        target, _ = available_junction(context.scene, active, parts, issues) if active in parts else (None, None)
        if target != obj or (source is not None and active != source):
            self.report({'WARNING'}, 'The selected connection changed. Choose its junction again.')
            return {'CANCELLED'}
        option = (draft_cross_option(context.scene, obj, source) if self.draft_cross else
                  connection_junction_option(context.scene, obj, source))
        if option is None:
            self.report({'WARNING'}, 'No new junction is detected at this tube.')
            return {'CANCELLED'}
        obj[_INTENT_KEY] = option[0]
        # This changes only the requested preview intent. Geometry and all
        # connected arms are preserved. Export still refuses native mismatches.
        if self.draft_cross:
            for selected in context.selected_objects:
                selected.select_set(False)
            obj.select_set(True)
            context.view_layer.objects.active = obj
        refresh(context.scene)
        _sync_elbow_controls(context)
        if not self.draft_cross and _scene_plan(context.scene)[1][1]:
            self.report({'WARNING'}, f'Joined at {obj.name}. Nearby tube connections still need checking before export.')
            return {'FINISHED'}
        self.report({'INFO'}, ('Draft + added. Add a straight or elbow to its free opening.'
                              if self.draft_cross else
                              f'Using {option[1]} at {obj.name}. Tube positions are unchanged.'))
        return {'FINISHED'}


def _draw_route_header(self, context):
    """Show route compatibility while the user moves or rotates a tube."""
    obj = context.active_object
    if (len(context.selected_objects) != 1
            or obj is None or obj.get('ObjectID') != 'BASE_BUBPIPE'):
        return
    if not obj.get(_INTENT_KEY):
        self.layout.label(text='Tube shape unchecked', icon='INFO')
        return
    ready, reason = route_status(context.scene)
    row = self.layout.row(align=True)
    if ready:
        row.label(text='Tube connections ready', icon='CHECKMARK')
    else:
        row.alert = True
        name = reason.partition(': ')[0]
        problem = context.scene.objects.get(name) if ': ' in reason else None
        if problem is not None:
            button = row.operator('bbe.select_problem_bubble',
                                  text=f'Check connection: {name}', icon='ERROR')
            button.obj_name = name
        else:
            row.label(text='Tube connection needs fixing', icon='ERROR')


class BBE_OT_select_problem_bubble(bpy.types.Operator):
    """Select the tube named by the live route warning"""
    bl_idname = 'bbe.select_problem_bubble'
    bl_label = 'Select Problem Tube'
    bl_options = {'REGISTER'}

    obj_name: bpy.props.StringProperty()

    def execute(self, context):
        obj = context.scene.objects.get(self.obj_name)
        if obj is None or obj.get('ObjectID') != 'BASE_BUBPIPE':
            self.report({'ERROR'}, 'Problem tube is no longer in this scene')
            return {'CANCELLED'}
        for selected in context.selected_objects:
            selected.select_set(False)
        obj.select_set(True)
        context.view_layer.objects.active = obj
        return {'FINISHED'}


class BBE_OT_join_bubble_ducts(bpy.types.Operator):
    """Connect two selected native ducts and accept the resulting game shapes"""
    bl_idname = 'bbe.join_bubble_ducts'
    bl_label = 'Join Selected Bubble Ducts'
    bl_description = 'Snap the active duct to the other selected duct and accept their game shapes; this may change their previews'
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        selected = [obj for obj in context.selected_objects
                    if obj.get('ObjectID') == 'BASE_BUBPIPE']
        if len(selected) != 2 or len(context.selected_objects) != 2:
            self.report({'ERROR'}, 'Select exactly two native bubble ducts')
            return {'CANCELLED'}
        source = context.active_object
        if source not in selected:
            self.report({'ERROR'}, 'Make the duct to move active before joining')
            return {'CANCELLED'}
        target = next(obj for obj in selected if obj != source)
        def are_connected():
            return any(
                (source.matrix_world @ Vector(source_socket)
                 - target.matrix_world @ Vector(target_socket)).length < 0.025
                for source_socket in _OFFSETS.values() for target_socket in _OFFSETS.values()
            )
        connected = are_connected()
        original_matrix = source.matrix_world.copy()
        original_snap = source.get('snapped_to')
        if not connected:
            before = _snapped(_native_objects(context.scene))
            if before.get(source.name) or len(before.get(target.name, set())) > 1:
                self.report({'ERROR'}, 'Move a free duct next to an end duct before joining this route')
                return {'CANCELLED'}
            if not snap_native(source, target) or not are_connected():
                source.matrix_world = original_matrix
                if original_snap is None:
                    if 'snapped_to' in source:
                        del source['snapped_to']
                else:
                    source['snapped_to'] = original_snap
                refresh(context.scene)
                self.report({'ERROR'}, 'Could not snap the selected ducts')
                return {'CANCELLED'}
        snapped = _snapped(_native_objects(context.scene))
        intended = {}
        for obj in selected:
            _, key, _ = _display_spec(snapped[obj.name], True)
            if key.startswith('UNRESOLVED:'):
                if not connected:
                    source.matrix_world = original_matrix
                    if original_snap is None:
                        if 'snapped_to' in source:
                            del source['snapped_to']
                    else:
                        source['snapped_to'] = original_snap
                    refresh(context.scene)
                self.report({'ERROR'}, f'{obj.name} has unsupported connections')
                return {'CANCELLED'}
            intended[obj] = key
        for obj, key in intended.items():
            obj[_INTENT_KEY] = key
        refresh(context.scene)
        self.report({'INFO'}, 'Joined selected ducts to their game shapes')
        return {'FINISHED'}


def convert_legacy_corners(scene):
    """Convert old visual-only elbows only when native connections match.

    Roll back every change if a bend would become a junction or disconnect.
    The caller may then move the route before trying again.
    """
    legacy = [obj for obj in scene.objects
              if obj.type == 'MESH' and obj.get('ObjectID') == 'BASE_BUBPIPE_L']
    if not legacy:
        return 0
    snapshots = [(obj, obj.matrix_world.copy(), obj.data,
                  obj.get('ObjectID'), obj.get('SnapID')) for obj in legacy]
    native_before = _native_objects(scene)
    sockets_before = _snapped(native_before)
    original_native = {obj.name: set(sockets_before.get(obj.name, set()))
                       for obj in native_before}
    try:
        for obj, matrix, _, _, _ in snapshots:
            obj['ObjectID'] = 'BASE_BUBPIPE'
            obj['SnapID'] = 'BASE_BUBPIPE'
            obj.matrix_world = matrix @ Matrix.Translation((0, -1, 0))
        scene.view_layers[0].update()
        found = _snapped(_native_objects(scene))
        bad = []
        for obj, _, _, _, _ in snapshots:
            actual = found.get(obj.name, set())
            if actual != {'Bot', 'Front'}:
                bad.append(f"{obj.name}: connected on {', '.join(sorted(actual)) or 'no sides'}; needs both bend ends")
        for name, before in original_native.items():
            after = found.get(name, set())
            if len(after) > 2 and len(after) > len(before):
                bad.append(f'{name}: extra junction ({", ".join(sorted(after))})')
        if bad:
            raise ValueError('Native duct connections differ from the drawn bends: '
                             + '; '.join(bad[:4]) + '. Move or extend the route, then retry.')
        refresh(scene)
        return len(legacy)
    except BaseException:
        for obj, matrix, mesh, object_id, snap_id in snapshots:
            obj['ObjectID'] = object_id
            if snap_id is None:
                if 'SnapID' in obj:
                    del obj['SnapID']
            else:
                obj['SnapID'] = snap_id
            obj.matrix_world = matrix
            obj.data = mesh
        scene.view_layers[0].update()
        refresh(scene)
        raise


class BBE_OT_convert_legacy_bubble_corners(bpy.types.Operator):
    """Convert visual-only bubble corners to native ducts when the route matches"""
    bl_idname = 'bbe.convert_legacy_bubble_corners'
    bl_label = 'Convert Old Bubble Corners'
    bl_options = {'REGISTER', 'UNDO'}

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self, width=480)

    def draw(self, context):
        count = sum(obj.get('ObjectID') == 'BASE_BUBPIPE_L'
                    for obj in context.scene.objects)
        self.layout.label(text=f'Convert {count} old preview-only bubble corners?')
        self.layout.label(text='The route must match native game connections.')
        self.layout.label(text='If it does not, no objects will change.')

    def execute(self, context):
        try:
            count = convert_legacy_corners(context.scene)
        except ValueError as exc:
            self.report({'ERROR'}, str(exc))
            return {'CANCELLED'}
        self.report({'INFO'}, f'Converted {count} bubble corners to native ducts')
        return {'FINISHED'}


def register():
    bpy.utils.register_class(BBE_OT_bubble_start_direction)
    bpy.utils.register_class(BBE_OT_repair_bubble_tubes)
    bpy.utils.register_class(BBE_OT_choose_bubble_opening)
    bpy.utils.register_class(BBE_OT_preview_bubble_opening)
    bpy.utils.register_class(BBE_OT_remove_bubble_opening)
    bpy.utils.register_class(BBE_OT_expand_bubble_junction)
    bpy.utils.register_class(BBE_OT_accept_bubble_junction)
    bpy.utils.register_class(BBE_OT_select_problem_bubble)
    bpy.utils.register_class(BBE_OT_bubble_joint_pivot)
    bpy.utils.register_class(BBE_OT_turn_bubble_elbow)
    bpy.utils.register_class(BBE_OT_join_bubble_ducts)
    bpy.utils.register_class(BBE_OT_convert_legacy_bubble_corners)
    bpy.types.VIEW3D_HT_header.append(_draw_route_header)
    bpy.app.handlers.save_pre.append(_joint_guard_save_pre)
    bpy.app.handlers.save_post.append(_joint_guard_save_post)
    bpy.app.handlers.load_pre.append(_joint_guard_load_pre)
    bpy.app.handlers.undo_pre.append(_clear_direction_sessions)
    bpy.app.handlers.redo_pre.append(_clear_direction_sessions)
    bpy.app.timers.register(_sync_joint_rotation_guard, first_interval=0.1, persistent=True)
    from . import bubble_controls
    bubble_controls.register()


def unregister():
    global _warning_draw_handle
    from . import bubble_controls
    bubble_controls.unregister()
    if _warning_draw_handle is not None:
        bpy.types.SpaceView3D.draw_handler_remove(_warning_draw_handle, 'WINDOW')
        _warning_draw_handle = None
    if bpy.app.timers.is_registered(_sync_joint_rotation_guard):
        bpy.app.timers.unregister(_sync_joint_rotation_guard)
    _restore_joint_rotation_guard()
    _restore_draft_shading()
    _joint_save_resume.clear()
    for handlers, callback in (
            (bpy.app.handlers.save_pre, _joint_guard_save_pre),
            (bpy.app.handlers.save_post, _joint_guard_save_post),
            (bpy.app.handlers.undo_pre, _clear_direction_sessions),
            (bpy.app.handlers.redo_pre, _clear_direction_sessions),
            (bpy.app.handlers.load_pre, _joint_guard_load_pre)):
        if callback in handlers:
            handlers.remove(callback)
    bpy.types.VIEW3D_HT_header.remove(_draw_route_header)
    _route_cache.clear()
    _clear_direction_sessions()
    bpy.utils.unregister_class(BBE_OT_convert_legacy_bubble_corners)
    bpy.utils.unregister_class(BBE_OT_join_bubble_ducts)
    bpy.utils.unregister_class(BBE_OT_turn_bubble_elbow)
    bpy.utils.unregister_class(BBE_OT_bubble_joint_pivot)
    bpy.utils.unregister_class(BBE_OT_select_problem_bubble)
    bpy.utils.unregister_class(BBE_OT_accept_bubble_junction)
    bpy.utils.unregister_class(BBE_OT_expand_bubble_junction)
    bpy.utils.unregister_class(BBE_OT_remove_bubble_opening)
    bpy.utils.unregister_class(BBE_OT_preview_bubble_opening)
    bpy.utils.unregister_class(BBE_OT_choose_bubble_opening)
    bpy.utils.unregister_class(BBE_OT_repair_bubble_tubes)
    bpy.utils.unregister_class(BBE_OT_bubble_start_direction)
