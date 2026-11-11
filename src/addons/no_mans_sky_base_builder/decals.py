"""Project standalone NMS decal volumes onto build surfaces.

Only display meshes change. Object IDs, matrices and saved game records remain
on the original objects. Source meshes are retained for quality changes/undo.
"""
import bpy
import numpy as np
import time
from mathutils import Matrix, Vector
from bpy.app.handlers import persistent

SOURCE = 'bbe_decal_source'
PROJECTED = 'bbe_projected_decal'
PREVIEW = 'bbe_decal_preview'
DISPLAY = 'bbe_decal_display'
PREVIEW_DISABLED = 'bbe_decal_projection_disabled'
_signature = None
_busy = False
_undoing = False
_resume_after_undo = 0.0
_project_signatures = {}
_mesh_revisions = {}
_object_revisions = {}
_known_meshes = set()
_bounds_cache = {}
_geometry_stamps = {}
_triangle_cache = {}
_refresh_requested = True
_request_started = 0.0
_last_change = 0.0
_solid_signature = None
_solid_views = {}
SOLID_NODE = 'BBE Solid Reference'
SOLID_PREVIOUS = 'bbe_solid_previous_active'
# The 2026-10-13 imported stair test paints farther than the mesh cage's
# +/-0.08327 depth. Use the placed STRIPE_1 collision HEIGHT, transformed
# through its parent scale/rotation, as a bounded White Border calibration.
# This covers that stair edge while excluding the previous floor-to-stair
# test. It is not proof that the game's deferred shader uses its collider.
# Keep X/Z and UVs derived from the artwork cage; never enlarge the image.
WHITE_BORDER_HALF_DEPTH = .493681 * .625014 * .5
# The two game-tested stair labels continue down the riser to local Y=-.253m.
# Keep the shallow box above/in front of the decal for contact, but extend the
# display behind an anchored label far enough to reach that lower stair edge.
WHITE_BORDER_WRAP_BACK_DEPTH = .27


def is_decal(obj):
    pid = obj.get('ObjectID', '').lstrip('^')
    return obj.type == 'MESH' and pid.startswith(('BUILDDECAL', 'DECAL_', 'EXPD_DECAL', 'SPEC_DECAL'))


def is_scribe_trial(obj):
    return obj.get('ObjectID') == 'BUILDDECAL2' and bool(obj.get('nms_text_owner'))


def has_native_artwork(mesh):
    """Only the high-resolution asset carries the game's alpha artwork."""
    return any(mat and mat.use_nodes and
               any(node.bl_idname == 'ShaderNodeTexImage' and node.image
                   for node in mat.node_tree.nodes)
               for mat in mesh.materials)


def uses_white_border_preview(obj, source=None):
    """Use the origin-preserving display for manually placed HD decals too."""
    if obj.type != 'MESH' or obj.get('ObjectID') != 'BUILDDECAL2':
        return False
    return is_scribe_trial(obj) or has_native_artwork(source or obj.get(SOURCE, obj.data))


def is_legacy_scribe_proxy(obj, source=None):
    return is_scribe_trial(obj) and not has_native_artwork(source or obj.get(SOURCE, obj.data))


def preview_for(obj):
    if obj.data.get(DISPLAY):
        return obj
    return next((child for child in obj.children if child.get(PREVIEW)), None)


def retire_child_previews(scene):
    """Unlink old display helpers, retaining datablocks for Blender's undo.

    Includes orphans saved after deleting a parent in older builds. New
    displays live on the part itself and need no deletion handler or helper.
    """
    for preview in list(scene.collection.all_objects):
        if preview.get(PREVIEW) and not preview.get('ObjectID'):
            for collection in list(preview.users_collection):
                collection.objects.unlink(preview)


def update_trial_preview(obj, source, verts, faces, uvs, slot, receiver_names, floating=False):
    """Put the artwork on the selectable part, preserving its export frame.

    Keep ordinary display IDs stable: replacing them recompiles Material
    Preview. Reuse only singly-owned displays after history has settled, and
    never clear their material slots. White Border retains its existing path.
    """
    if not faces:
        obj.data = source
        obj.display_type = 'TEXTURED'
        return False
    from . import undo_guard
    reuse = (not uses_white_border_preview(obj, source) and obj.data.get(DISPLAY)
             and obj.data.users == 1 and undo_guard.history_ready() and not _undoing
             and tuple(obj.data.materials) == tuple(source.materials))
    if reuse:
        mesh = obj.data
        mesh.clear_geometry()
    else:
        mesh = bpy.data.meshes.new('BBE Decal Display / '+obj.name)
    mesh.from_pydata(verts, [], faces)
    if not reuse:
        for key in source.keys():
            mesh[key] = source[key]
        for material in source.materials:
            mesh.materials.append(material)
    mesh[PROJECTED] = True
    mesh[DISPLAY] = True
    mesh['bbe_decal_floating'] = floating
    mesh['bbe_decal_receivers'] = receiver_names
    layer = mesh.uv_layers.get(source.uv_layers.active.name) or mesh.uv_layers.new(name=source.uv_layers.active.name)
    mesh.polygons.foreach_set('material_index', [slot]*len(faces))
    layer.data.foreach_set('uv', np.array(uvs)[np.array(faces).ravel()].ravel())
    mesh.update()
    if not reuse:
        obj.data = mesh
    if obj.display_type != 'TEXTURED':
        obj.display_type = 'TEXTURED'
    return True


def update_trial_floating(obj, source, definition):
    """Show the real decal image at its saved origin when no face receives it."""
    lo, hi, mapping, slot = definition
    # A thin display quad replaces the six-sided placement cage. It is a
    # display mesh only; the original object and its export matrix stay put.
    verts = [Vector((lo[0], 0, lo[2])), Vector((lo[0], 0, hi[2])),
             Vector((hi[0], 0, hi[2])), Vector((hi[0], 0, lo[2]))]
    uvs = [np.array([p[0], p[2], 1]) @ mapping for p in verts]
    update_trial_preview(obj, source, verts, [(0, 1, 2), (0, 2, 3)],
                         uvs, slot, [], floating=True)
    return False


def source_mesh(obj):
    if not obj.data.get(PROJECTED) and obj.get(SOURCE) != obj.data:
        obj[SOURCE] = obj.data
    return obj.get(SOURCE, obj.data)


def bounds(points):
    return points.min(axis=0), points.max(axis=0)


def clip(poly, axis, value, sign):
    result = []
    previous = poly[-1]
    pd = sign*(previous[axis]-value)
    for current in poly:
        cd = sign*(current[axis]-value)
        if (cd >= 0) != (pd >= 0):
            result.append(previous+(current-previous)*(pd/(pd-cd)))
        if cd >= 0:
            result.append(current)
        previous, pd = current, cd
    return result


def projector(mesh, conservative=False):
    points = np.array([v.co[:] for v in mesh.vertices], dtype=float)
    if not len(points) or not mesh.uv_layers:
        return None
    lo, hi = bounds(points)
    if conservative:
        # White Border's calibrated receiver depth is centred on the saved
        # origin and independent of the thinner imported artwork cage.
        lo[1], hi[1] = -WHITE_BORDER_HALF_DEPTH, WHITE_BORDER_HALF_DEPTH
    else:
        # Existing BBE decal previews use a broad receiver search.
        lo[1] = min(lo[1], -max(hi[0]-lo[0], hi[2]-lo[2])*.5)
        hi[1] = max(hi[1], max(hi[0]-lo[0], hi[2]-lo[2])*.25)
    # Native standalone decals project along Y with artwork in X/Z. Derive
    # UV mapping from the authored +Y face, including atlas scale/orientation.
    face = max(mesh.polygons, key=lambda p: p.normal.y)
    if face.normal.y < .5:
        return None
    uv = mesh.uv_layers.active.data
    coords = np.array([[points[mesh.loops[i].vertex_index][0], points[mesh.loops[i].vertex_index][2], 1] for i in face.loop_indices])
    tex = np.array([uv[i].uv[:] for i in face.loop_indices])
    mapping = np.linalg.lstsq(coords, tex, rcond=None)[0]
    return lo, hi, mapping, face.material_index


def white_border_projector(mesh):
    """Match the imported White Border's in-game artwork orientation."""
    definition = projector(mesh, conservative=True)
    if definition is None:
        return None
    lo, hi, mapping, slot = definition
    # The 2026-10-13 single-part floor comparison shows the detached rule
    # above the notched stripe in game, opposite to the imported cage UVs.
    # Correct only preview sampling: never rotate the saved part or rewrite
    # its source UVs. Both floating and receiver previews share this mapping.
    mapping[:, 1] *= -1
    mapping[2, 1] += 1
    return lo, hi, mapping, slot


def surface_components(positions, indices):
    """Weld UV splits to identify separate receiver surfaces (seat vs frame)."""
    parents = list(range(len(indices)))
    owners = {}
    def root(i):
        while parents[i] != i:
            parents[i] = parents[parents[i]]
            i = parents[i]
        return i
    for i, triangle in enumerate(indices):
        for vertex in triangle:
            key = tuple(np.round(positions[vertex], 5))
            if key in owners:
                parents[root(i)] = root(owners[key])
            else:
                owners[key] = i
    return np.array([root(i) for i in range(len(indices))])


def project_scribe_trial(obj, receivers, cache, source, definition):
    """Preview the calibrated decal volume without moving the saved part.

    The game uses a deferred decal against visible scene fragments. Blender
    cannot use that G-buffer here, so coat outward-facing receiver faces
    inside the profile's box and let depth testing reveal the visible ones.
    This follows stepped hull surfaces without a centre-point snap or an
    arbitrary 3 cm contact layer.
    """
    lo, hi, mapping, slot = definition
    wrap_lo = lo.copy()
    wrap_lo[1] = min(wrap_lo[1], -WHITE_BORDER_WRAP_BACK_DEPTH)
    inverse = obj.matrix_world.inverted_safe()
    verts, faces, uvs, receiver_names = [], [], [], []
    offset = max(.01, min(.012, max(abs(v) for v in obj.matrix_world.to_scale()) * .003))
    # A decal can overlap a tread even when its saved origin is in open air.
    # Require actual front-facing receiver area inside the calibrated volume
    # before adding edge/riser faces. A nearby side face alone must not pull an
    # old floor decal onto the stairs.
    has_front_receiver = False
    for receiver in receivers:
        transform = inverse @ receiver.matrix_world
        corners = np.array([(transform @ Vector(c))[:] for c in receiver.bound_box])
        rlo, rhi = bounds(corners)
        if np.any(rhi < wrap_lo) or np.any(rlo > hi):
            continue
        key = receiver.data.as_pointer()
        if key not in cache:
            mesh = receiver.data
            mesh.calc_loop_triangles()
            positions = np.empty(len(mesh.vertices) * 3)
            mesh.vertices.foreach_get('co', positions)
            indices = np.empty(len(mesh.loop_triangles) * 3, dtype=np.int32)
            mesh.loop_triangles.foreach_get('vertices', indices)
            cache[key] = positions.reshape(-1, 3), indices.reshape(-1, 3)
        positions, indices = cache[key]
        mat = np.array(transform)
        points = positions @ mat[:3, :3].T + mat[:3, 3]
        triangles = points[indices]
        normals = np.cross(triangles[:, 1] - triangles[:, 0],
                           triangles[:, 2] - triangles[:, 0])
        lengths = np.linalg.norm(normals, axis=1)
        # Keep edge faces at 90 degrees to the projection direction too. The
        # game carries the White Border artwork over stair bevels and risers;
        # rejecting zero-Y normals left those faces bare in Blender. Faces
        # pointing away from the decal remain excluded.
        keep = (lengths > 1e-9) & (normals[:, 1] >= -lengths * 1e-5) & (
            np.all(triangles.max(axis=1) >= wrap_lo, axis=1)) & (
            np.all(triangles.min(axis=1) <= hi, axis=1))
        before = len(faces)
        for tri, normal, length in zip(triangles[keep], normals[keep], lengths[keep]):
            poly = list(tri)
            for axis in range(3):
                poly = clip(poly, axis, wrap_lo[axis], 1) if poly else []
                poly = clip(poly, axis, hi[axis], -1) if poly else []
            if len(poly) < 3:
                continue
            if normal[1] > length * .05:
                # The longer wrap range may reach a separate surface behind
                # the decal. Activation still requires a tread in the original
                # shallow volume, so side faces alone cannot pull it there.
                core = clip(poly, 1, lo[1], 1)
                core = clip(core, 1, hi[1], -1) if core else []
                has_front_receiver |= len(core) >= 3
            world_normal = obj.matrix_world.to_3x3().inverted_safe().transposed() @ Vector(normal)
            world_normal.normalize()
            shift = inverse.to_3x3() @ (world_normal * offset)
            start = len(verts)
            verts.extend(Vector(p) + shift for p in poly)
            uvs.extend(np.array([p[0], p[2], 1]) @ mapping for p in poly)
            faces.extend((start, start + i, start + i + 1)
                         for i in range(1, len(poly) - 1))
        if len(faces) > before:
            receiver_names.append(receiver.name)
    if not has_front_receiver or not faces:
        if has_native_artwork(source):
            return update_trial_floating(obj, source, definition)
        return update_trial_preview(obj, source, [], [], [], slot, [])
    return update_trial_preview(obj, source, verts, faces, uvs, slot, receiver_names)


def project_standard_volume(obj, receivers, cache, source, definition):
    """Ordinary decals cover fragments at multiple depths, without an anchor.

    Keep this separate from the calibrated White Border/stair path above.
    The existing ordinary-decal volume and UV mapping remain unchanged.
    """
    lo, hi, mapping, slot = definition
    inverse = obj.matrix_world.inverted_safe()
    normal_matrix = obj.matrix_world.to_3x3().inverted_safe().transposed()
    inverse_matrix = inverse.to_3x3()
    verts, faces, uvs, receiver_names = [], [], [], []
    offset = max(.003, min(.012, max(abs(v) for v in obj.matrix_world.to_scale())*.003))
    for receiver in receivers:
        transform = inverse @ receiver.matrix_world
        rlo, rhi = bounds(np.array([(transform @ Vector(c))[:] for c in receiver.bound_box]))
        if np.any(rhi < lo) or np.any(rlo > hi):
            continue
        key = receiver.data.as_pointer()
        if key not in cache:
            mesh = receiver.data
            mesh.calc_loop_triangles()
            positions = np.empty(len(mesh.vertices)*3)
            mesh.vertices.foreach_get('co', positions)
            indices = np.empty(len(mesh.loop_triangles)*3, dtype=np.int32)
            mesh.loop_triangles.foreach_get('vertices', indices)
            cache[key] = positions.reshape(-1, 3), indices.reshape(-1, 3)
        positions, indices = cache[key]
        mat = np.array(transform)
        triangles = (positions @ mat[:3, :3].T + mat[:3, 3])[indices]
        normals = np.cross(triangles[:, 1]-triangles[:, 0], triangles[:, 2]-triangles[:, 0])
        lengths = np.linalg.norm(normals, axis=1)
        keep = ((normals[:, 1] > lengths*.05)
                & np.all(triangles.max(axis=1) >= lo, axis=1)
                & np.all(triangles.min(axis=1) <= hi, axis=1))
        before = len(faces)
        selected, selected_normals = triangles[keep], normals[keep]
        inside = np.all((selected >= lo) & (selected <= hi), axis=(1, 2))
        # Most receiver triangles already fit inside the volume. Process
        # those in a batch; only boundary triangles need polygon clipping.
        if np.any(inside):
            whole = selected[inside]
            world_normals = selected_normals[inside] @ np.array(normal_matrix).T
            world_normals /= np.linalg.norm(world_normals, axis=1)[:, None]
            shifts = (world_normals*offset) @ np.array(inverse_matrix).T
            points = whole.reshape(-1, 3)
            start = len(verts)
            verts.extend((whole+shifts[:, None, :]).reshape(-1, 3))
            uvs.extend(points[:, (0, 2)] @ mapping[:2] + mapping[2])
            faces.extend(np.arange(start, start+len(points)).reshape(-1, 3))
        for tri, normal in zip(selected[~inside], selected_normals[~inside]):
            poly = list(tri)
            for axis in range(3):
                poly = clip(poly, axis, lo[axis], 1) if poly else []
                poly = clip(poly, axis, hi[axis], -1) if poly else []
            if len(poly) < 3:
                continue
            world_normal = normal_matrix @ Vector(normal)
            world_normal.normalize()
            shift = inverse_matrix @ (world_normal*offset)
            start = len(verts)
            verts.extend(Vector(p)+shift for p in poly)
            uvs.extend(np.array([p[0], p[2], 1]) @ mapping for p in poly)
            faces.extend((start, start+i, start+i+1) for i in range(1, len(poly)-1))
        if len(faces) > before:
            receiver_names.append(receiver.name)
    if not faces:
        return update_trial_floating(obj, source, definition)
    return update_trial_preview(obj, source, verts, faces, uvs, slot, receiver_names)



def project(obj, receivers, cache):
    source = source_mesh(obj)
    trial = uses_white_border_preview(obj, source)
    if is_legacy_scribe_proxy(obj, source):
        # The old opaque paired proxy did not match its game export.
        preview = preview_for(obj)
        if preview is not None:
            preview.hide_viewport = True
        obj.display_type = 'BOUNDS'
        return False
    definition = white_border_projector(source) if trial else projector(source)
    if definition is None:
        return False
    if obj.get(PREVIEW_DISABLED, False):
        return update_trial_floating(obj, source, definition)
    # Project onto all intersecting outward-facing fragments. A centre-point
    # receiver/nearest-depth band wrongly pulls artwork off protrusions when
    # the centre ray sees a recessed face. The game-tested nose uses both.
    # Depth testing supplies visible occlusion; the saved frame is untouched.
    if trial:
        return project_scribe_trial(obj, receivers, cache, source, definition)
    return project_standard_volume(obj, receivers, cache, source, definition)


def geometry_stamp(obj):
    key = obj.as_pointer()
    revision = (obj.data.as_pointer(), _object_revisions.get(key, 0),
                _mesh_revisions.get(obj.data.as_pointer(), 0),
                bool(obj.get(PREVIEW_DISABLED, False)))
    cached = _geometry_stamps.get(key)
    if cached is None or cached[0] != revision:
        stamp = (key, *revision, len(obj.data.vertices), len(obj.data.polygons),
                 tuple(v for row in obj.matrix_world for v in row))
        cached = _geometry_stamps[key] = (revision, stamp)
    return cached[1]


def signature(scene):
    return (scene.as_pointer(), getattr(scene, 'bbe_detailed_proxies', True),
            tuple((geometry_stamp(o), o.hide_viewport, o.hide_render)
                  for o in scene.collection.all_objects if o.type == 'MESH' and o.get('ObjectID')))


def receiver_bounds(obj):
    """Cache broad-phase bounds once per changed receiver, not per decal."""
    key = obj.as_pointer()
    stamp = geometry_stamp(obj)
    cached = _bounds_cache.get(key)
    if cached is None or cached[0] != stamp:
        corners = np.array([c[:] for c in obj.bound_box])
        matrix = np.array(obj.matrix_world)
        world = corners @ matrix[:3, :3].T + matrix[:3, 3]
        cached = (stamp, *bounds(world))
        _bounds_cache[key] = cached
    return cached


def request_refresh():
    """Coalesce scene edits; dependency handlers never rebuild geometry."""
    global _refresh_requested, _request_started, _last_change
    now = time.monotonic()
    if not _refresh_requested:
        _request_started = now
    _last_change = now
    _refresh_requested = True


def refresh(scene=None, force=False):
    global _signature, _busy, _refresh_requested, _solid_signature
    scene = scene or bpy.context.scene
    from . import undo_guard
    if _busy or _undoing or not undo_guard.history_ready() or bpy.context.mode != 'OBJECT':
        return 0
    # Replacing a display mesh during a native drag forces dependency-graph
    # evaluation mid-interaction. Finish/cancel the drag before projecting.
    if not force and transform_active():
        return 0
    if force:
        _geometry_stamps.clear()
    _refresh_requested = False
    # A wiring-only build has no decal geometry to project. Inspect cached
    # collection membership before touching receiver meshes or their transforms.
    members = scene.collection.all_objects
    decals = [obj for obj in members if is_decal(obj)]
    if not decals:
        if any(obj.get(PREVIEW) for obj in members):
            retire_child_previews(scene)
        _signature = (scene.as_pointer(), getattr(scene, 'bbe_detailed_proxies', True), ())
        _project_signatures.clear()
        _geometry_stamps.clear()
        _mesh_revisions.clear()
        _object_revisions.clear()
        _bounds_cache.clear()
        _triangle_cache.clear()
        _known_meshes.clear()
        return 0
    current = signature(scene)
    if not force and current == _signature:
        return 0
    _busy = True
    count = 0
    try:
        retire_child_previews(scene)
        detailed = getattr(scene, 'bbe_detailed_proxies', True)
        need_receivers = detailed and any(not o.get(PREVIEW_DISABLED, False) for o in decals)
        receivers = ([o for o in scene.collection.all_objects if o.type == 'MESH' and o.get('ObjectID')
                      and not is_decal(o) and not o.hide_render and not o.hide_viewport]
                     if need_receivers else [])
        # Reconcile membership after additions/deletions. Only integers and
        # numeric arrays survive between updates, never potentially stale RNA.
        _known_meshes.clear()
        _known_meshes.update(o.data.as_pointer() for o in receivers)
        _known_meshes.update(source_mesh(o).as_pointer() for o in decals)
        live_decals = {o.as_pointer() for o in decals}
        live_receivers = {o.as_pointer() for o in receivers}
        for key in set(_project_signatures) - live_decals:
            del _project_signatures[key]
        for key in set(_bounds_cache) - live_receivers:
            del _bounds_cache[key]
        for key in set(_mesh_revisions) - _known_meshes:
            del _mesh_revisions[key]
        for key in set(_object_revisions) - live_decals - live_receivers:
            del _object_revisions[key]
        for key in set(_geometry_stamps) - live_decals - live_receivers:
            del _geometry_stamps[key]
        for key in set(_triangle_cache) - _known_meshes:
            del _triangle_cache[key]
        receiver_records = [receiver_bounds(o) for o in receivers]
        world_lows = np.array([r[1] for r in receiver_records]).reshape(-1, 3)
        world_highs = np.array([r[2] for r in receiver_records]).reshape(-1, 3)
        if force:
            _triangle_cache.clear()
        cache = _triangle_cache
        for obj in decals:
            # Low-detail decals still show one artwork face, never the cage.
            if not detailed or obj.get(PREVIEW_DISABLED, False):
                source = source_mesh(obj)
                stamp = ('flat', source.as_pointer(), _mesh_revisions.get(source.as_pointer(), 0),
                         len(source.vertices), len(source.polygons))
                if not force and _project_signatures.get(obj.as_pointer()) == stamp:
                    continue
                trial = uses_white_border_preview(obj, source)
                definition = white_border_projector(source) if trial else projector(source)
                if is_legacy_scribe_proxy(obj, source):
                    preview = preview_for(obj)
                    if preview is not None:
                        preview.hide_viewport = True
                    obj.display_type = 'BOUNDS'
                elif definition is not None and has_native_artwork(source):
                    update_trial_floating(obj, source, definition)
                elif obj.data.get(PROJECTED):
                    obj.data = source_mesh(obj)
                _project_signatures[obj.as_pointer()] = stamp
                continue
            source = source_mesh(obj)
            trial = uses_white_border_preview(obj, source)
            definition = white_border_projector(source) if trial else projector(source)
            if definition is None:
                continue
            lo, hi, _, _ = definition
            search_lo = lo.copy()
            if trial:
                search_lo[1] = min(search_lo[1], -WHITE_BORDER_WRAP_BACK_DEPTH)
            inverse = obj.matrix_world.inverted_safe()
            nearby = []
            nearby_stamps = []
            cage = np.array([(x, y, z) for x in (lo[0], hi[0])
                             for y in (search_lo[1], hi[1]) for z in (lo[2], hi[2])])
            matrix = np.array(obj.matrix_world)
            wlo, whi = bounds(cage @ matrix[:3, :3].T + matrix[:3, 3])
            candidates = np.flatnonzero(np.all(world_highs >= wlo, axis=1)
                                       & np.all(world_lows <= whi, axis=1))
            for index in candidates:
                receiver = receivers[index]
                transform = inverse @ receiver.matrix_world
                corners = np.array([(transform @ Vector(c))[:] for c in receiver.bound_box])
                rlo, rhi = bounds(corners)
                if not (np.any(rhi < search_lo) or np.any(rlo > hi)):
                    nearby.append(receiver)
                    nearby_stamps.append(receiver_records[index][0])
            stamp = (source.as_pointer(), _mesh_revisions.get(source.as_pointer(), 0),
                     _object_revisions.get(obj.as_pointer(), 0),
                     len(source.vertices), len(source.polygons),
                     tuple(v for row in obj.matrix_world for v in row),
                     bool(obj.get(PREVIEW_DISABLED, False)), tuple(nearby_stamps))
            if force or stamp != _project_signatures.get(obj.as_pointer()):
                count += int(project(obj, nearby, cache))
                _project_signatures[obj.as_pointer()] = stamp
        _signature = signature(scene)
    finally:
        _busy = False
    return count


def transform_active():
    return any(op.bl_idname.startswith('TRANSFORM_OT_')
               for window in bpy.context.window_manager.windows for op in window.modal_operators)


def tick():
    global _solid_signature
    from . import undo_guard
    if not undo_guard.history_ready():
        return .2
    try:
        if bpy.context.window_manager is None or bpy.context.window_manager.is_interface_locked:
            return .2
        if not _undoing and time.monotonic() >= _resume_after_undo and not bpy.app.is_job_running('RENDER'):
            now = time.monotonic()
            scene = bpy.context.scene
            if _signature is not None and _signature[:2] != (
                    scene.as_pointer(), getattr(scene, 'bbe_detailed_proxies', True)):
                request_refresh()
            if _refresh_requested and not transform_active() and (now - _last_change >= .12 or now - _request_started >= .4):
                refresh()
            # View mode/settings can change without a geometry event. This
            # tiny UI stamp avoids rescanning every material on idle ticks.
            views = tuple((window.scene.as_pointer(),
                           getattr(window.scene, 'bbe_solid_decals', True),
                           getattr(window.scene, 'bbe_detailed_proxies', True),
                           area.spaces.active.as_pointer(), area.spaces.active.shading.type)
                          for window in bpy.context.window_manager.windows
                          for area in window.screen.areas if area.type == 'VIEW_3D')
            if views != _solid_signature:
                solid_references()
                _solid_signature = views
    except Exception as exc:
        print('BBE decal projection:', exc)
    return .2


def solid_references(force_disable=False):
    """Use Workbench's alpha-tested textures only for decal reference artwork.

    Disconnected one-pixel textures keep BBE hulls in their ordinary solid
    colours. They never enter the material shader or enable scene lighting.
    """
    # Material Preview does not use Workbench's active texture node. Avoid
    # changing material node trees while its dependency graph is rebuilding.
    if not force_disable and not any(
            area.type == 'VIEW_3D' and area.spaces.active.shading.type == 'SOLID'
            for window in bpy.context.window_manager.windows for area in window.screen.areas):
        return
    wanted = {}
    active_views = set()
    for window in bpy.context.window_manager.windows:
        scene = window.scene
        enabled = (not force_disable and getattr(scene, 'bbe_solid_decals', True) and
                   getattr(scene, 'bbe_detailed_proxies', True) and
                   any(is_decal(o) and not o.hide_viewport and not o.hide_render
                       for o in scene.collection.all_objects))
        for area in window.screen.areas:
            if area.type != 'VIEW_3D':
                continue
            space = area.spaces.active
            key = space.as_pointer()
            if enabled:
                active_views.add(key)
                if key not in _solid_views:
                    _solid_views[key] = (space, space.shading.color_type)
                    space.shading.color_type = 'TEXTURE'
                    area.tag_redraw()
            elif key in _solid_views:
                saved, previous = _solid_views.pop(key)
                if space.shading.color_type == 'TEXTURE':
                    space.shading.color_type = previous
                    area.tag_redraw()
        if enabled:
            for obj in scene.collection.all_objects:
                if obj.type == 'MESH' and obj.get('ObjectID'):
                    for mat in obj.data.materials:
                        if mat and mat.use_nodes:
                            wanted[mat] = wanted.get(mat, False) or is_decal(obj)
    for mat in bpy.data.materials:
        if not mat.use_nodes:
            continue
        nodes = mat.node_tree.nodes
        if mat not in wanted:
            if SOLID_PREVIOUS in mat:
                nodes.active = nodes.get(mat[SOLID_PREVIOUS])
                del mat[SOLID_PREVIOUS]
                if nodes.get(SOLID_NODE):
                    nodes.remove(nodes[SOLID_NODE])
            continue
        if SOLID_PREVIOUS not in mat:
            mat[SOLID_PREVIOUS] = nodes.active.name if nodes.active else ''
        if wanted[mat]:
            tex = nodes.get('Diffuse')
            if not tex or tex.type != 'TEX_IMAGE' or not tex.image:
                tex = next((n for n in nodes if n.type == 'TEX_IMAGE' and n.image), None)
        else:
            tex = nodes.get(SOLID_NODE)
            if tex is None:
                tex = nodes.new('ShaderNodeTexImage')
                tex.name = SOLID_NODE
                tex.label = 'Solid viewport only (not connected)'
                color = tuple(round(v, 4) for v in mat.diffuse_color[:3]) + (1.0,)
                name = 'BBE Solid ' + str(color)
                im = bpy.data.images.get(name)
                if im is None:
                    im = bpy.data.images.new(name, width=1, height=1)
                    im.pixels[:] = color
                    im.pack()
                tex.image = im
                tex.hide = True
                tex.location = (-1000, -1000)
        if tex is not None and nodes.active != tex:
            nodes.active = tex
    for key in set(_solid_views)-active_views:
        space, previous = _solid_views.pop(key)
        try:
            if space.shading.color_type == 'TEXTURE':
                space.shading.color_type = previous
        except ReferenceError:
            pass


def reset_tracking():
    global _signature, _solid_signature
    _signature = None
    _solid_signature = None
    _project_signatures.clear()
    _mesh_revisions.clear()
    _object_revisions.clear()
    _known_meshes.clear()
    _bounds_cache.clear()
    _geometry_stamps.clear()
    _triangle_cache.clear()
    request_refresh()


@persistent
def loaded(_):
    global _undoing, _resume_after_undo
    _undoing = False
    _resume_after_undo = 0.0
    reset_tracking()
    _solid_views.clear()


@persistent
def before_undo(_):
    global _undoing
    _undoing = True


@persistent
def after_undo(_):
    global _undoing, _resume_after_undo
    reset_tracking()
    _resume_after_undo = time.monotonic() + .75
    _undoing = False


@persistent
def before_render(scene, *_):
    refresh(scene)


@persistent
def changed(scene, depsgraph):
    global _signature, _solid_signature
    from . import undo_guard
    # undo_post has returned before Blender emits its first graph updates,
    # but those updates can still contain IDs from the discarded graph.
    # Do not even unwrap update.id until the shared history guard is ready.
    # after_undo already invalidates every projection cache for reconciliation.
    if _busy or _undoing or not undo_guard.history_ready():
        return
    relevant = False
    for update in depsgraph.updates:
        item = update.id.original
        key = item.as_pointer()
        if isinstance(item, bpy.types.Object):
            if item.type == 'MESH' and item.get('ObjectID'):
                relevant = True
                if update.is_updated_transform:
                    _geometry_stamps.pop(key, None)
                if update.is_updated_geometry and not item.data.get(PROJECTED):
                    _object_revisions[key] = _object_revisions.get(key, 0) + 1
                    _solid_signature = None
                    _triangle_cache.pop(item.data.as_pointer(), None)
        elif isinstance(item, bpy.types.Mesh):
            if key in _known_meshes and update.is_updated_geometry:
                _mesh_revisions[key] = _mesh_revisions.get(key, 0) + 1
                _triangle_cache.pop(key, None)
                _signature = None
                relevant = True
        elif isinstance(item, (bpy.types.Scene, bpy.types.Collection)):
            # Adding/removing/unlinking a part may report only membership.
            # The next reconciliation detects both old and new neighbours.
            # Selection-only Scene updates have no flags and need no scan.
            relevant |= update.is_updated_geometry or update.is_updated_transform
            if update.is_updated_geometry:
                _solid_signature = None
        elif isinstance(item, bpy.types.Material):
            _solid_signature = None
    if relevant:
        request_refresh()


def register():
    reset_tracking()
    bpy.types.Scene.bbe_solid_decals = bpy.props.BoolProperty(
        name='Decals in Solid', default=True,
        description='Show decal artwork over plain hull colours in Solid view, without rendered lighting')
    if not bpy.app.timers.is_registered(tick):
        bpy.app.timers.register(tick, first_interval=1, persistent=True)
    for handlers, callback in ((bpy.app.handlers.load_post, loaded), (bpy.app.handlers.render_pre, before_render),
                               (bpy.app.handlers.depsgraph_update_post, changed),
                               (bpy.app.handlers.undo_pre, before_undo), (bpy.app.handlers.undo_post, after_undo),
                               (bpy.app.handlers.redo_pre, before_undo), (bpy.app.handlers.redo_post, after_undo)):
        if callback not in handlers:
            handlers.append(callback)


def unregister():
    if bpy.app.timers.is_registered(tick):
        bpy.app.timers.unregister(tick)
    for handlers, callback in ((bpy.app.handlers.load_post, loaded), (bpy.app.handlers.render_pre, before_render),
                               (bpy.app.handlers.depsgraph_update_post, changed),
                               (bpy.app.handlers.undo_pre, before_undo), (bpy.app.handlers.undo_post, after_undo),
                               (bpy.app.handlers.redo_pre, before_undo), (bpy.app.handlers.redo_post, after_undo)):
        if callback in handlers:
            handlers.remove(callback)
    for obj in bpy.data.objects:
        if uses_white_border_preview(obj):
            obj.display_type = 'TEXTURED'
            preview = preview_for(obj)
            if preview is not None and preview != obj:
                preview.hide_viewport = True
        if is_decal(obj) and obj.data.get(PROJECTED) and obj.get(SOURCE):
            obj.data = obj[SOURCE]
    solid_references(force_disable=True)
    del bpy.types.Scene.bbe_solid_decals
