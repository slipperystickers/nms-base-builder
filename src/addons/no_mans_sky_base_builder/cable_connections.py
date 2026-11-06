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
from mathutils import Matrix, Vector
from .utils import mirror_pivot

POWER = 'U_POWERLINE'
TELEPORT = 'U_PORTALLINE'
KINDS = (POWER, TELEPORT)
SRT_IDS = frozenset(('U_MINIPORTAL', 'U_MINIPORTAL_CV'))
COLORS = {POWER: (0.08, 1.0, 0.22, 1.0), TELEPORT: (0.20, 0.75, 1.0, 1.0)}
COLLECTIONS = {POWER: 'Electrical Connections', TELEPORT: 'Teleport Connections'}
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
    bpy.context.scene.collection.objects.link(control)
    control.empty_display_type = 'SPHERE'
    control.empty_display_size = .001  # Visible targets are constant-size gizmos.
    control.hide_render = True
    control['rig_item'] = True
    control['SnapID'] = 'POWER_CONTROL'
    control['bbe_cable_kind'] = kind
    return control


def style(cable):
    kind = cable.get('ObjectID')
    if kind not in KINDS or cable.type != 'MESH':
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


def organize(cable):
    """Real exportable cable objects, in independently toggleable collections."""
    kind = cable.get('ObjectID')
    if kind not in KINDS:
        return
    scene = bpy.context.scene
    collection = next((c for c in scene.collection.children if c.get('bbe_cable_kind') == kind), None)
    if collection is None:
        collection = bpy.data.collections.new(COLLECTIONS[kind])
        collection['bbe_cable_kind'] = kind
        scene.collection.children.link(collection)
    for obj in (cable, *endpoints(cable)):
        if obj is None:
            continue
        if obj.name not in collection.objects:
            collection.objects.link(obj)
        for old in list(obj.users_collection):
            if old != collection:
                old.objects.unlink(obj)


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
        raise ValueError('Both selected objects need a compatible ' + ('teleport' if kind == TELEPORT else 'electrical') + ' socket.')
    return min(((ka, kb) for ka in aa for kb in bb), key=lambda pair: (aa[pair[0]]-bb[pair[1]]).length_squared)


def connect(a, akey, b, bkey, kind, builder):
    if a == b:
        raise ValueError('Choose a connector on a different object.')
    if akey not in local_sockets(a, kind) or bkey not in local_sockets(b, kind):
        raise ValueError('These connectors do not accept this cable type.')
    if (sockets(a, kind)[akey] - sockets(b, kind)[bkey]).length < 1e-6:
        raise ValueError('The two connectors occupy the same position.')
    desired = {(a.as_pointer(), akey), (b.as_pointer(), bkey)}
    for existing in bpy.context.scene.objects:
        if existing.get('ObjectID') != kind:
            continue
        ends = endpoints(existing)
        if all(ends):
            identities = {(control_owner(e).as_pointer(), e.get('bbe_socket_key'))
                          for e in ends if control_owner(e) is not None}
            if identities == desired:
                return existing
    controls = []
    cable = None
    try:
        for obj, key in ((a, akey), (b, bkey)):
            control = make_control(builder, obj.name + ' ' + key, kind)
            controls.append(control)
            bind(control, obj, key, kind)
        bpy.context.view_layer.update()
        cable = builder.add_part(kind, build_rigs=False)
        cable.build_rig(*controls)
        style(cable.object)
        organize(cable.object)
        bpy.context.view_layer.update()
        return cable.object
    except Exception:
        for obj in controls + ([cable.object] if cable else []):
            bpy.data.objects.remove(obj, do_unlink=True)
        raise


def connect_selected(context, kind, builder):
    objects = list(context.selected_objects)
    active = context.active_object
    if len(objects) < 2 or active not in objects:
        raise ValueError('Select two devices, with the destination active.')
    # Validate the entire request before creating anything.
    pairs = [(active, obj, nearest_pair(active, obj, kind)) for obj in objects if obj != active]
    return [connect(a, keys[0], b, keys[1], kind, builder) for a, b, keys in pairs]


def repair_srt(context):
    """Explicit repair only. Never guess between overlapping/stacked devices."""
    selected = set(context.selected_objects)
    repaired = ambiguous = 0
    devices = [o for o in context.scene.objects if o.get('ObjectID') in SRT_IDS]
    for cable in list(context.scene.objects):
        kind = cable.get('ObjectID')
        if kind not in KINDS:
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
