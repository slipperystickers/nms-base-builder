"""Vantage rear wall states, using native socket matches without adding save parts."""
import re
from pathlib import Path
import bpy
from bpy.app.handlers import persistent
from . import builder_v2, corvette_snapping, hd_library, undo_guard

SIGNATURES = {}
_pending = False


def opening_mask(cockpit, neighbors):
    mask = 0
    points = corvette_snapping.DATA['B_COK_E']
    for other in neighbors:
        for key, _, _, candidate in corvette_snapping.options(other, cockpit):
            match = re.fullmatch(r'SnapPoint_(?:Int)?N([012])', points[int(key)]['name'])
            if not match:
                continue
            delta = candidate.inverted_safe() @ other.matrix_world
            if (delta.translation.length < .025 and
                    abs(delta.to_quaternion().angle) < .002 and
                    max(abs(s-1) for s in delta.to_scale()) < .001):
                mask |= 1 << int(match.group(1))
    return mask


def refresh(scene):
    if not undo_guard.history_ready():
        return 0
    objects = [o for o in scene.objects if o.get('ObjectID') == 'B_COK_E'
               or str(o.get('ObjectID','')).startswith('B_HAB') or o.get('ObjectID') == 'B_DOOR0']
    detailed = bool(getattr(scene, 'bbe_detailed_proxies', True))
    root = hd_library.additions_root() if detailed else None
    use_hd = root is not None
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
        key = f'NMS_VANTAGE_{"HD" if use_hd else "BASE"}_{mask}_713'
        if not use_hd:key += '_' + str(cockpit.get('UserData','0'))
        mesh = bpy.data.meshes.get(key)
        # Older builds named the untextured fallback "HD". Do not reuse it
        # after the actual detailed pack becomes available.
        if use_hd and mesh is not None and mesh.get(builder_v2.MESH_TAG) != 'B_COK_E':
            mesh.name = key + '_base_fallback'
            mesh = None
        if mesh is not None and cockpit.data == mesh:
            continue
        if mesh is None:
            filename = f'B_COK_E_OPEN_{mask}.blend'
            path = root / 'habitat' / filename if root else Path(builder_v2.FILE_PATH) / 'resources/habitat_variants' / filename
            if not path.is_file():
                continue
            with bpy.data.libraries.load(str(path), link=False) as (source, target):
                target.meshes = [source.meshes[0]]
            mesh = target.meshes[0];mesh.name = key
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
