"""Typed cable sockets. Coordinates are native model-local, never screen guesses.

The SRT locators were checked against build 26386568 MINIPORTAL.SCENE and
BIGGSMINIPORTAL.SCENE: PortalSocket_Out_ and RefLinkSocket0 respectively.
The Corvette model deliberately has no electrical socket.
"""
import math
import json
from pathlib import Path
from functools import lru_cache
import bpy
from bpy.app.handlers import persistent
from mathutils import Matrix, Vector
from .utils import mirror_pivot

POWER = 'U_POWERLINE'
TELEPORT = 'U_PORTALLINE'
BYTEBEAT = 'U_BYTEBEATLINE'
KINDS = (POWER, TELEPORT, BYTEBEAT)
LABELS = {POWER: 'electrical', TELEPORT: 'teleport', BYTEBEAT: 'ByteBeat'}
TARGET_LABELS = {POWER: 'Green electrical', TELEPORT: 'Blue teleport', BYTEBEAT: 'Pink ByteBeat'}
# ByteBeatWire_Out locators from the device and switch placement scenes.
# The side-mounted ByteBeat_In/Out pair joins devices structurally.
BEAT_SOCKETS = {'BYTEBEAT': (.196310, 1.089710, -.468870),
                'BYTEBEATSWITCH': (.467437, .553212, .175408)}
# A/B are BBE wiring conventions for the interchangeable power terminals.
POWER_IN, POWER_OUT, POWER_TRIGGER = 'POWER_A', 'POWER_B', 'POWER_C'
SWITCH_ROLES = {POWER_IN: 'IN', POWER_OUT: 'OUT'}
TRANSISTOR_ROLES = {**SWITCH_ROLES, POWER_TRIGGER: 'TRIGGER'}
LOGIC_ROLES = {
    'U_SWITCHWALL': SWITCH_ROLES, 'U_SWITCHBUTTON': SWITCH_ROLES,
    'U_SWITCHPROX': SWITCH_ROLES, 'U_SWITCHPRESS': SWITCH_ROLES,
    'U_TRANSISTOR1': TRANSISTOR_ROLES, 'U_TRANSISTOR2': TRANSISTOR_ROLES,
    'BYTEBEATSWITCH': {POWER_IN: 'IN', 'POWER_C': 'OUT', 'BYTEBEAT_A': 'TRIGGER'},
}
SRT_IDS = frozenset(('U_MINIPORTAL', 'U_MINIPORTAL_CV'))
COLORS = {POWER: (0.08, 1.0, 0.22, 1.0), TELEPORT: (0.20, 0.75, 1.0, 1.0), BYTEBEAT: (1.0, .04, .3, 1.0)}
COLLECTIONS = {POWER: 'Electrical Connections', TELEPORT: 'Teleport Connections',
               BYTEBEAT: 'ByteBeat Connections', 'U_PIPELINE': 'Supply Pipes'}
RADII = {POWER: .025, TELEPORT: .045}


@lru_cache(maxsize=4096)
def _power_points(pid):
    native = _native_power_points()
    if pid in native:
        return {key: Vector(info['position']) for key, info in native[pid].items()}
    from .part import Part
    for group in Part.SNAP_MATRIX_DICTIONARY.values():
        if pid in group.get('parts', ()):
            return {key: Matrix(info['matrix']).translation
                    for key, info in group.get('snap_points', {}).items() if key.startswith('POWER')}
    return {}


@lru_cache(maxsize=1)
def _native_power_points():
    return json.loads((Path(__file__).parent / 'resources/electrical_sockets.json').read_text(encoding='utf-8'))['parts']


def local_sockets(obj, kind):
    """Return only sockets compatible with this cable, in the displayed frame."""
    pid = obj.get('ObjectID', '')
    if obj.get('rig_item'):
        return {'ENDPOINT': Vector()} if obj.get('bbe_cable_kind', POWER) == kind else {}
    if kind == BYTEBEAT:
        position = BEAT_SOCKETS.get(pid)
        if position is None:
            return {}
        point = Vector(position)
        if mirror_pivot.is_normalized(obj):
            point += mirror_pivot.pivot(pid)
        return {'BYTEBEAT_A': point}
    if pid in SRT_IDS:
        if kind == TELEPORT:
            points = {'PORTAL_A': Vector((0, 1.593752, -.889160))}
        elif kind == POWER and pid == 'U_MINIPORTAL':
            points = {'POWER_A': Vector((0, .606372, -1.495064))}
        else:
            return {}
        if mirror_pivot.is_normalized(obj):
            points = {k: v + mirror_pivot.pivot(pid) for k, v in points.items()}
        return points
    if kind == TELEPORT or pid in KINDS:
        return {}
    # Reading the static table avoids constructing wrappers (which can change
    # materials/caches) every time the viewport redraws.
    offset = mirror_pivot.pivot(pid) if mirror_pivot.is_normalized(obj) else Vector()
    return {key: value + offset for key, value in _power_points(pid).items()}


def sockets(obj, kind):
    return {key: obj.matrix_world @ point for key, point in local_sockets(obj, kind).items()}


def control_owner(control):
    """Use the actual driver ID, so renaming a connected device remains safe."""
    animation = control.animation_data
    if control.get('bbe_socket_key') and animation:
        for curve in animation.drivers:
            for variable in curve.driver.variables:
                if variable.targets[0].id:
                    return variable.targets[0].id
    return bpy.data.objects.get(control.get('snapped_to', ''))


def endpoints(cable):
    # The constraint retains the actual end ID even after an Outliner rename.
    end = next((c.target for c in cable.constraints if c.type == 'TRACK_TO'), None)
    start = None
    if cable.animation_data:
        for curve in cable.animation_data.drivers:
            if curve.data_path == 'location' and curve.driver.variables:
                start = curve.driver.variables[0].targets[0].id
                break
    return (start or bpy.data.objects.get(cable.get('start_control', '')),
            end or bpy.data.objects.get(cable.get('end_control', '')))


def bind(control, obj, key, kind):
    point = local_sockets(obj, kind)[key]
    control['snapped_to'] = obj.name
    control['bbe_socket_key'] = key
    control['bbe_cable_kind'] = kind
    control.parent = None
    control.location = obj.matrix_world @ point
    # Controls stay in world space for the existing line rig. Drivers use the
    # complete device matrix, including rotation, scale, and parent transforms.
    for axis in range(3):
        control.driver_remove('location', axis)
        driver = control.driver_add('location', axis).driver
        driver.type = 'SCRIPTED'
        for col in range(4):
            var = driver.variables.new()
            var.name = 'm' + str(col)
            var.targets[0].id = obj
            # RNA matrix array paths are column-major; mathutils indexing is
            # row-major. Swapping these is essential for translated devices.
            var.targets[0].data_path = f'matrix_world[{col}][{axis}]'
        driver.expression = '+'.join(f'm{col}*{float(value)!r}'
                                     for col, value in enumerate((*point, 1)))


def make_control(builder, name, kind):
    control = bpy.data.objects.new(name, None)
    cable_collection(bpy.context.scene, kind).objects.link(control)
    control.empty_display_type = 'SPHERE'
    control.empty_display_size = .001  # Visible targets are constant-size gizmos.
    control.hide_render = True
    control['rig_item'] = True
    control['SnapID'] = 'POWER_CONTROL'
    control['bbe_cable_kind'] = kind
    return control


def junction(builder, kind, position):
    point = make_control(builder, LABELS[kind] + ' junction', kind)
    point.location = position
    point.empty_display_size = .12
    point['bbe_junction'] = True
    return point


def subdivide(cable, fractions, builder):
    """Insert shared controls on the live span, keeping both outer attachments."""
    start, end = endpoints(cable)
    if start is None or end is None:
        raise ValueError('This cable has no editable endpoints.')
    a, b = start.matrix_world.translation, end.matrix_world.translation
    if (a - b).length < 1e-6:
        raise ValueError('This cable has zero length.')
    kind = cable['ObjectID']
    original = builder.get_builder_object_from_bpy_object(cable)
    points, extra = [], []
    try:
        for fraction in fractions:
            points.append(junction(builder, kind, a.lerp(b, fraction)))
            extra.append(builder.add_part(kind, user_data=original.user_data, build_rigs=False))
        chain = [start, *points, end]
        for part, left, right in zip([original, *extra], chain, chain[1:]):
            part.build_rig(left, right)
        bpy.context.view_layer.update()
        return points
    except Exception:
        original.build_rig(start, end)
        for obj in [part.object for part in extra] + points:
            bpy.data.objects.remove(obj, do_unlink=True)
        raise


def style(cable):
    kind = cable.get('ObjectID')
    if kind not in KINDS or cable.type != 'MESH':
        return
    if kind == BYTEBEAT:
        # Retain the native crossed ribbons and pink glow on detailed proxies.
        if any(abs(a-b) > 1e-6 for a,b in zip(cable.color, COLORS[kind])):
            cable.color = COLORS[kind]
        return
    # Change only preview geometry, never the transform that is exported.
    name = 'BBE ' + COLLECTIONS[kind] + ' Preview v1'
    mesh = bpy.data.meshes.get(name)
    if mesh is None:
        radius, sides = RADII[kind], 12
        vertices = [(radius * math.cos(i*math.tau/sides), radius * math.sin(i*math.tau/sides), z)
                    for z in (0, 1) for i in range(sides)]
        faces = [(i, (i+1)%sides, (i+1)%sides+sides, i+sides) for i in range(sides)]
        faces += [tuple(reversed(range(sides))), tuple(range(sides, sides*2))]
        mesh = bpy.data.meshes.new(name)
        mesh.from_pydata(vertices, [], faces)
        mesh.update()
    if cable.data != mesh:
        cable.data = mesh
    mat = bpy.data.materials.get(name)
    if mat is None:
        mat = bpy.data.materials.new(name)
        mat.diffuse_color = COLORS[kind]
        mat.use_nodes = True
        bsdf = mat.node_tree.nodes.get('Principled BSDF')
        bsdf.inputs['Base Color'].default_value = COLORS[kind]
        bsdf.inputs['Roughness'].default_value = .45
        bsdf.inputs['Emission Color'].default_value = COLORS[kind]
        bsdf.inputs['Emission Strength'].default_value = .35
    if not mesh.materials:
        mesh.materials.append(mat)
    for slot in cable.material_slots:
        if slot.link != 'DATA':
            slot.link = 'DATA'
    if any(abs(a-b) > 1e-6 for a,b in zip(cable.color,COLORS[kind])):
        cable.color = COLORS[kind]
    if cable.get('bbe_cable_preview') != 1:
        cable['bbe_cable_preview'] = 1


def cable_collection(scene, kind):
    root = scene.collection
    for collection in root.children_recursive:
        if collection.get('bbe_cable_kind') == kind and collection.library is None:
            return collection
    collection = bpy.data.collections.new(COLLECTIONS[kind])
    collection['bbe_cable_kind'] = kind
    root.children.link(collection)
    return collection


def assign_collections(obj, destinations, scene_collections):
    for collection in destinations:
        if obj.name not in collection.objects:
            collection.objects.link(obj)
    for old in obj.users_collection:
        if old in scene_collections and old not in destinations and old.library is None:
            old.objects.unlink(obj)


def organize(cable, *, with_endpoints=True):
    """Place the actual cable and its rig in the Outliner collection for its type."""
    kind = cable.get('ObjectID')
    if kind not in COLLECTIONS:
        return
    scene = bpy.context.scene
    collection = cable_collection(scene, kind)
    scene_collections = {scene.collection, *scene.collection.children_recursive}
    objects = [cable]
    if with_endpoints:
        objects.extend(end for end in endpoints(cable) if end is not None and end.get('rig_item'))
    for obj in objects:
        assign_collections(obj, {collection}, scene_collections)


@persistent
def organize_saved_cables(*_args):
    # Collect all destinations before unlinking. A .blend can share a cable or
    # a legacy junction between scenes, or a junction between cable types.
    destinations = {}
    scene_collections = set()
    for scene in bpy.data.scenes:
        if scene.library:
            continue
        members = {}
        for obj in scene.objects:
            kind = obj.get('ObjectID')
            if kind in COLLECTIONS:
                members.setdefault(obj, set()).add(kind)
                for end in endpoints(obj):
                    if end is not None and end.get('rig_item') and end.name in scene.objects:
                        members.setdefault(end, set()).add(kind)
        for obj in scene.objects:
            kind = obj.get('bbe_cable_kind')
            if obj.get('rig_item') and obj not in members and kind in COLLECTIONS:
                members[obj] = {kind}
        by_kind = {}
        for obj, kinds in members.items():
            if obj.library:
                continue
            for kind in kinds:
                if kind not in by_kind:
                    by_kind[kind] = cable_collection(scene, kind)
                destinations.setdefault(obj, set()).add(by_kind[kind])
        scene_collections.update((scene.collection, *scene.collection.children_recursive))
    for obj, collections in destinations.items():
        assign_collections(obj, collections, scene_collections)


def prepare_control(control, kind):
    """Replace the old lightning-bolt mesh; gizmos draw the visible targets."""
    control['bbe_cable_kind'] = kind
    if control.type == 'MESH':
        mesh = bpy.data.meshes.get('BBE Cable Endpoint (targets in viewport)')
        if mesh is None:
            mesh = bpy.data.meshes.new('BBE Cable Endpoint (targets in viewport)')
        control.data = mesh
    control.hide_render = True


def bind_imported(scene):
    """Restore device-following only for unambiguous, already-correct endpoints.

    Spatial buckets avoid a device-by-cable quadratic import cost. Deliberate
    free endpoints and incorrectly attached legacy cables are not relocated.
    """
    from collections import defaultdict
    buckets = defaultdict(list)
    cell = lambda point: tuple(round(v / .005) for v in point)
    for obj in scene.objects:
        if not obj.get('ObjectID') or obj.get('ObjectID') in KINDS:
            continue
        for kind in KINDS:
            for key, point in sockets(obj, kind).items():
                buckets[(kind, cell(point))].append((obj, key, point))
    for cable in list(scene.objects):
        kind = cable.get('ObjectID')
        if kind not in KINDS:
            continue
        for end in endpoints(cable):
            if end is None or end.get('bbe_socket_key'):
                continue
            position = end.matrix_world.translation
            c = cell(position)
            matches = []
            for dx in (-1,0,1):
                for dy in (-1,0,1):
                    for dz in (-1,0,1):
                        matches.extend(row for row in buckets.get((kind, (c[0]+dx,c[1]+dy,c[2]+dz)), ())
                                       if (row[2]-position).length < .002)
            if len(matches) == 1:
                obj, key, _ = matches[0]
                bind(end, obj, key, kind)


def nearest_pair(a, b, kind):
    aa, bb = sockets(a, kind), sockets(b, kind)
    if not aa or not bb:
        raise ValueError('Both selected objects need a compatible ' + LABELS[kind] + ' socket.')
    return min(((ka, kb) for ka in aa for kb in bb), key=lambda pair: (aa[pair[0]]-bb[pair[1]]).length_squared)


def socket_identity(control):
    owner = control_owner(control)
    if owner is not None:
        return owner, control.get('bbe_socket_key')
    return control, 'ENDPOINT'


def disconnect_selected(context, kind):
    selected = set(context.selected_objects)
    remove = []
    ends = set()
    keep = set()
    for cable in context.scene.objects:
        if cable.get('ObjectID') not in (*KINDS, 'U_PIPELINE'):
            continue
        pair = endpoints(cable)
        if (cable.get('ObjectID') == kind and all(pair) and
                all(end in selected or control_owner(end) in selected for end in pair)):
            remove.append(cable)
            ends.update(pair)
        else:
            keep.update(end for end in pair if end is not None)
    if not remove:
        return 0
    # Older rigs can drive an endpoint from another endpoint. Keep that source too.
    keep.update(control_owner(end) for end in tuple(keep))
    for cable in remove:
        bpy.data.objects.remove(cable, do_unlink=True)
    for end in ends - keep - selected:
        if end.get('rig_item') and not end.get('bbe_junction') and end.users <= len(end.users_collection):
            bpy.data.objects.remove(end, do_unlink=True)
    return len(remove)


def existing_connection(a, akey, b, bkey, kind):
    desired = {socket_identity(obj) if key == 'ENDPOINT' else (obj, key)
               for obj, key in ((a, akey), (b, bkey))}
    for existing in bpy.context.scene.objects:
        if existing.get('ObjectID') != kind:
            continue
        ends = endpoints(existing)
        if all(ends):
            identities = {socket_identity(end) for end in ends}
            if identities == desired:
                return existing
    return None


def connect(a, akey, b, bkey, kind, builder, *, free_start=None, free_end=None, check_existing=True):
    if a is not None and a == b:
        raise ValueError('Choose a connector on a different object.')
    ends = []
    for obj, key, free_position in ((a, akey, free_start), (b, bkey, free_end)):
        if obj is None and kind in (POWER, BYTEBEAT) and free_position is not None:
            position = Vector(free_position)
        elif obj is not None and key in local_sockets(obj, kind):
            position = sockets(obj, kind)[key]
        else:
            raise ValueError('These connectors do not accept this cable type.')
        ends.append((obj, key, position))
    if (ends[0][2] - ends[1][2]).length < 1e-6:
        raise ValueError('The two endpoints occupy the same position.')
    if check_existing and a is not None and b is not None:
        existing = existing_connection(a, akey, b, bkey, kind)
        if existing is not None:
            return existing
    controls = []
    created = []
    cable = None
    try:
        for obj, key, position in ends:
            if obj is not None and obj.get('rig_item'):
                controls.append(obj)
                continue
            name = LABELS[kind] + ' endpoint' if obj is None else obj.name + ' ' + key
            control = make_control(builder, name, kind)
            controls.append(control)
            created.append(control)
            if obj is None:
                control.location = position
            else:
                bind(control, obj, key, kind)
        bpy.context.view_layer.update()
        cable = builder.add_part(kind, build_rigs=False)
        cable.build_rig(*controls)
        style(cable.object)
        bpy.context.view_layer.update()
        return cable.object
    except Exception:
        for obj in ([cable.object] if cable else []) + created:
            bpy.data.objects.remove(obj, do_unlink=True)
        raise


def power_devices(selection):
    """Box selection includes line meshes and the socket controls that drive them."""
    devices = {}
    for obj in selection:
        if obj.get('ObjectID') in COLLECTIONS:
            continue
        if obj.get('rig_item'):
            if obj.get('bbe_cable_kind', POWER) != POWER:
                continue
            owner = control_owner(obj)
            if owner is not None:
                obj = owner
        devices[obj] = None
    return tuple(devices)


def route_power(context, devices, source, source_key, origin, builder, chain):
    """Plan from a clicked socket or shared free junction, then create the batch."""
    # A selected source is already part of the circuit, including when the
    # user selected its socket control as part of a box selection.
    if source is not None and source.get('rig_item'):
        source, source_key = socket_identity(source)
    remaining = {}
    for device in devices:
        if device == source:
            continue
        if context.scene.objects.get(device.name) != device:
            raise ValueError('A selected device is no longer in this scene.')
        choices = sockets(device, POWER)
        if device.get('ObjectID') in LOGIC_ROLES:
            choices = {POWER_IN: choices[POWER_IN]} if POWER_IN in choices else {}
        if not choices:
            raise ValueError(f'{device.name} has no compatible power input.')
        remaining[device] = choices
    if not remaining:
        raise ValueError('Choose a starting point for the selected devices.')

    plan = []
    start, key, position = source, source_key, origin
    while remaining:
        def closest(device):
            choices = remaining[device]
            return min(((position - p).length_squared, device.name, k) for k, p in choices.items())

        # A fan always uses the original position, so it needs no device ordering.
        end = min(remaining, key=closest) if chain else next(iter(remaining))
        distance, _, end_key = closest(end)
        if distance < 1e-12:
            raise ValueError('Two sockets overlap. Choose a different start or move the overlapping devices.')
        end_position = remaining.pop(end)[end_key]
        plan.append((start, key, end, end_key))
        if chain:
            start, key, position = end, end_key, end_position

    existing = set()
    for wire in context.scene.objects:
        if wire.get('ObjectID') == POWER:
            ends = endpoints(wire)
            if all(ends):
                existing.add(frozenset(socket_identity(e) for e in ends))
    created = []
    count = 0
    try:
        if source is None:
            source = junction(builder, POWER, origin)
            created.append(source)
            context.view_layer.update()
        for start, key, end, end_key in plan:
            if start is None:
                start, key = source, 'ENDPOINT'
            pair = frozenset(socket_identity(obj) if k == 'ENDPOINT' else (obj, k)
                             for obj, k in ((start, key), (end, end_key)))
            if pair in existing:
                continue
            wire = connect(start, key, end, end_key, POWER, builder, check_existing=False)
            created.append(wire)
            created.extend(control for control in endpoints(wire) if control not in (start, end))
            count += 1
            existing.add(pair)
    except Exception:
        if created:
            bpy.data.batch_remove(created)
        raise
    return count


def connect_selected(context, kind, builder, *, chain=False):
    objects = list(context.selected_objects)
    active = context.active_object
    if len(objects) < 2 or active not in objects:
        raise ValueError('Select two devices, with the destination active.')
    # Validate the entire request before creating anything.
    if chain:
        points = {}
        for obj in objects:
            choices = sockets(obj, kind)
            if len(choices) != 1:
                raise ValueError('Choose sockets on multi-socket devices in the viewport.')
            points[obj] = next(iter(choices.items()))
        remaining = set(points) - {active}
        pairs = []
        start = active
        while remaining:
            start_key, position = points[start]
            end = min(remaining, key=lambda obj: ((points[obj][1] - position).length_squared, obj.name))
            pairs.append((start, end, (start_key, points[end][0])))
            remaining.remove(end)
            start = end
    else:
        pairs = [(active, obj, nearest_pair(active, obj, kind)) for obj in objects if obj != active]
    if any((sockets(a, kind)[ka] - sockets(b, kind)[kb]).length < 1e-6
           for a, b, (ka, kb) in pairs):
        raise ValueError('Two selected sockets occupy the same position.')
    return [connect(a, keys[0], b, keys[1], kind, builder) for a, b, keys in pairs]


def repair_srt(context):
    """Explicit repair only. Never guess between overlapping/stacked devices."""
    selected = set(context.selected_objects)
    repaired = ambiguous = 0
    devices = [o for o in context.scene.objects if o.get('ObjectID') in SRT_IDS]
    for cable in list(context.scene.objects):
        kind = cable.get('ObjectID')
        if kind not in (POWER, TELEPORT):
            continue
        controls = endpoints(cable)
        owners = [control_owner(c) if c else None for c in controls]
        if cable not in selected and not any(o in selected for o in owners):
            continue
        for control, owner in zip(controls, owners):
            if control is None:
                continue
            candidates = [owner] if owner is not None else []
            if not candidates:
                # Older imports have no owner. Only match an exact old socket;
                # include the mislabeled power socket for old teleport cables.
                for device in devices:
                    points = list(sockets(device, kind).values())
                    if kind == TELEPORT:
                        points += list(sockets(device, POWER).values())
                    if any((p-control.matrix_world.translation).length < .005 for p in points):
                        candidates.append(device)
            if len(candidates) != 1:
                ambiguous += 1
                continue
            owner = candidates[0]
            if owner.get('ObjectID') not in SRT_IDS:
                continue
            keys = local_sockets(owner, kind)
            if len(keys) == 1:
                bind(control, owner, next(iter(keys)), kind)
                repaired += 1
        style(cable)
        organize(cable)
    context.view_layer.update()
    return repaired, ambiguous
