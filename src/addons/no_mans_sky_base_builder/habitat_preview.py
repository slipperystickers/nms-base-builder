"""Vantage rear connections and interior side doors on the cockpit display mesh."""
import hashlib
import json
from functools import lru_cache
from pathlib import Path

import bmesh
import bpy
import numpy as np
from bpy.app.handlers import persistent
from . import builder_v2, corvette_snapping, hd_library, undo_guard

SIGNATURES = {}
_pending = False


# Bits 0..2 select the shipped rear variant. An interior door supplies its
# own wall assembly at IntE1/IntW1; the cockpit omits its empty wall there.
REAR = 7
SIDE_DOORS = {'SnapPoint_IntE1': 8, 'SnapPoint_IntW1': 16}
REAR_SOCKETS = {f'SnapPoint_{prefix}N{i}': 1 << i for prefix in ('', 'Int') for i in range(3)}


def opening_mask(cockpit, neighbors):
    mask = 0
    points = corvette_snapping.DATA['B_COK_E']
    for other in neighbors:
        for key, _, _, candidate in corvette_snapping.options(other, cockpit):
            name = points[int(key.split(':', 1)[0])]['name']
            bit = REAR_SOCKETS.get(name, 0)
            if other.get('ObjectID') in {'B_DOOR0', 'B_WALL_TOIL0'}:
                bit |= SIDE_DOORS.get(name, 0)
            if not bit or mask & bit:
                continue
            delta = candidate.inverted_safe() @ other.matrix_world
            if (delta.translation.length < .025 and
                    abs(delta.to_quaternion().angle) < .002 and
                    max(abs(s-1) for s in delta.to_scale()) < .001):
                mask |= bit
    return mask


@lru_cache(maxsize=1)
def side_walls():
    return json.loads((Path(__file__).parent / 'resources/vantage_side_walls.json').read_text())


def remove_side_walls(mesh, mask, detailed):
    # Face ranges were matched triangle-for-triangle to the native WALLE1_
    # and WALLW1_ components. Only apply them to the verified proxy topology.
    spec = side_walls()['HD' if detailed else 'BASE'][str(mask & REAR)]
    coords = np.empty(len(mesh.vertices) * 3, dtype='<f4')
    indices = np.empty(len(mesh.loops), dtype='<i4')
    mesh.vertices.foreach_get('co', coords)
    mesh.loops.foreach_get('vertex_index', indices)
    digest = hashlib.sha256(indices)
    digest.update(coords)
    if len(mesh.polygons) != spec['faces'] or digest.hexdigest() != spec['sha256']:
        return False
    bm = bmesh.new()
    try:
        bm.from_mesh(mesh)
        bm.faces.ensure_lookup_table()
        faces = [bm.faces[i] for bit, side in ((8, 'E'), (16, 'W')) if bit & mask
                 for start, stop in spec[side] for i in range(start, stop)]
        bmesh.ops.delete(bm, geom=faces, context='FACES')
        bm.to_mesh(mesh)
    finally:
        bm.free()
    mesh.update()
    return True


def mesh_key(cockpit, mask, use_hd):
    key = f'NMS_VANTAGE_{"HD" if use_hd else "BASE"}_{mask}_713'
    return key if use_hd else key + '_' + str(cockpit.get('UserData', '0'))


def rear_mesh(cockpit, mask, root):
    use_hd = root is not None
    key = mesh_key(cockpit, mask, use_hd)
    mesh = bpy.data.meshes.get(key)
    # Older builds named the untextured fallback "HD". Do not reuse it
    # after the actual detailed pack becomes available.
    if use_hd and mesh is not None and mesh.get(builder_v2.MESH_TAG) != 'B_COK_E':
        mesh.name = key + '_base_fallback'
        mesh = None
    if mesh is not None:
        return mesh
    filename = f'B_COK_E_OPEN_{mask}.blend'
    path = root / 'habitat' / filename if root else Path(builder_v2.FILE_PATH) / 'resources/habitat_variants' / filename
    if not path.is_file():
        return None
    with bpy.data.libraries.load(str(path), link=False) as (source, target):
        target.meshes = [source.meshes[0]]
    mesh = target.meshes[0]
    mesh.name = key
    mesh['bbe_vantage_openings'] = mask
    mesh[builder_v2.MESH_REVISION_TAG] = builder_v2.MESH_REVISIONS['B_COK_E']
    if use_hd:
        mesh[builder_v2.MESH_TAG] = 'B_COK_E'
        builder_v2._relink_mesh_textures(mesh)
        builder_v2.materials_v2.note_appended_data()
        builder_v2.materials_v2.dedupe_appended_data()
    else:
        builder_v2.apply_proxy_mesh(cockpit, 'B_COK_E', cockpit.get('UserData','0'))
        for mat in cockpit.data.materials:mesh.materials.append(mat)
        mesh['bbe_forsaken_revision'] = builder_v2.COCKPIT_BASE_REVISION
    return mesh


def display_mesh(cockpit, mask, root):
    use_hd = root is not None
    sides_open = bool(mask & ~REAR)
    if sides_open:
        key = mesh_key(cockpit, mask, use_hd)
        cached = bpy.data.meshes.get(key)
        if cached is not None and cached.get('bbe_vantage_openings') == mask:
            return cached
    rear = rear_mesh(cockpit, mask & REAR, root)
    if rear is None or not sides_open:
        return rear
    mesh = rear.copy()
    if not remove_side_walls(mesh, mask, use_hd):
        bpy.data.meshes.remove(mesh)
        print(f'BBE: unrecognized Vantage side-wall geometry in {rear.name}')
        return rear
    mesh.name = key
    mesh['bbe_vantage_openings'] = mask
    return mesh


def refresh(scene):
    if not undo_guard.history_ready():
        return 0
    objects = [o for o in scene.objects if o.get('ObjectID') == 'B_COK_E'
               or str(o.get('ObjectID','')).startswith('B_HAB') or o.get('ObjectID') in {'B_DOOR0', 'B_WALL_TOIL0'}]
    detailed = bool(getattr(scene, 'bbe_detailed_proxies', True))
    root = hd_library.additions_root() if detailed else None
    # A pack can finish installing without any object moving. Include its
    # availability so an existing base preview upgrades immediately.
    signature = (detailed, str(root), tuple((o.name, o.get('ObjectID'), o.get('UserData','0'), tuple(v for row in o.matrix_world for v in row)) for o in objects))
    if (SIGNATURES.get(scene.as_pointer()) == signature and
            all('bbe_vantage_openings' in o.data for o in objects if o.get('ObjectID')=='B_COK_E' and o.type=='MESH')):
        return 0
    SIGNATURES[scene.as_pointer()] = signature
    changed = 0
    for cockpit in objects:
        if cockpit.get('ObjectID') != 'B_COK_E' or cockpit.type != 'MESH':
            continue
        mask = opening_mask(cockpit, [o for o in objects if o != cockpit and o.get('ObjectID') != 'B_COK_E'])
        mesh = display_mesh(cockpit, mask, root)
        if mesh is None or cockpit.data == mesh:
            continue
        undo_guard.track_generated_preview()
        cockpit.data = mesh
        changed += 1
    return changed


def _timer():
    global _pending
    if not undo_guard.history_ready():
        return .2
    _pending = False
    for scene in bpy.data.scenes:
        refresh(scene)


@persistent
def _changed(scene, *args):
    global _pending
    if not _pending:
        _pending = True
        bpy.app.timers.register(_timer, first_interval=.2)


@persistent
def _loaded(*args):
    SIGNATURES.clear()
    _changed(None)


def register():
    bpy.app.handlers.depsgraph_update_post.append(_changed)
    bpy.app.handlers.load_post.append(_loaded)
    bpy.app.handlers.undo_post.append(_loaded)
    bpy.app.handlers.redo_post.append(_loaded)


def unregister():
    global _pending
    for handlers, callback in ((bpy.app.handlers.depsgraph_update_post, _changed),
                               (bpy.app.handlers.load_post, _loaded),
                               (bpy.app.handlers.undo_post, _loaded),
                               (bpy.app.handlers.redo_post, _loaded)):
        if callback in handlers:handlers.remove(callback)
    if bpy.app.timers.is_registered(_timer):bpy.app.timers.unregister(_timer)
    _pending = False
    SIGNATURES.clear()
