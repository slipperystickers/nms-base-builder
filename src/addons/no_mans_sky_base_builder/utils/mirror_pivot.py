"""Blender display pivots for native parts whose mirror meshes have offset pivots.

Native save positions remain unchanged.  A displayed mesh uses p + u while
its object uses M_native @ T(-u); export applies the inverse conversion.
Existing scene objects are converted only when an operation needs the new
frame, so opening an older project never silently rewrites its geometry.
"""
import json
from pathlib import Path

from mathutils import Matrix, Vector

_PATH = Path(__file__).resolve().parents[1] / 'resources/mirror_display_pivots.json'
_PIVOTS = {key: Vector(value) for key, value in json.loads(_PATH.read_text())['pivots'].items()}
MESH_TAG = 'bbe_display_pivot_mesh_v1'
OBJECT_TAG = 'bbe_display_pivot_object_v1'


def pivot(object_id):
    return _PIVOTS.get(str(object_id or '').lstrip('^'), Vector((0.0, 0.0, 0.0)))


def has_pivot(object_id):
    return str(object_id or '').lstrip('^') in _PIVOTS


def display_matrix(native_matrix, object_id):
    u = pivot(object_id)
    return native_matrix @ Matrix.Translation(-u) if u.length_squared else native_matrix.copy()


def native_matrix(display, object_id, *, normalized=True):
    u = pivot(object_id)
    return display @ Matrix.Translation(u) if normalized and u.length_squared else display.copy()


def normalize_mesh(mesh, object_id):
    """Normalize a newly loaded, unshared library mesh in place."""
    if mesh is None or not has_pivot(object_id):
        return mesh
    identity = str(object_id).lstrip('^')
    if mesh.get(MESH_TAG) == identity:
        return mesh
    if mesh.users:
        raise ValueError('Normalize a copy of an occupied mesh: ' + mesh.name)
    mesh.transform(Matrix.Translation(pivot(identity)))
    mesh[MESH_TAG] = identity
    mesh.update()
    return mesh


def ensure_object(obj):
    """Convert a legacy placed object without changing a single world vertex."""
    if obj is None or obj.type != 'MESH':
        return False
    identity = str(obj.get('ObjectID', '')).lstrip('^')
    if not has_pivot(identity):
        return False
    if obj.get(OBJECT_TAG) == identity:
        return True
    old_world = obj.matrix_world.copy()
    if obj.data.get(MESH_TAG) != identity:
        new_mesh = obj.data.copy()
        # The copy is not shared until assignment, but Blender may count a
        # temporary user on copied datablocks. Shift this private copy only.
        new_mesh.transform(Matrix.Translation(pivot(identity)))
        new_mesh[MESH_TAG] = identity
        new_mesh.update()
        obj.data = new_mesh
    obj.matrix_world = display_matrix(old_world, identity)
    obj[OBJECT_TAG] = identity
    return True


def is_normalized(obj):
    return obj is not None and obj.get(OBJECT_TAG) == str(obj.get('ObjectID', '')).lstrip('^')


def display_relation(native_relation, source_id, target_id):
    """The native relation expressed in the two visible mesh frames."""
    return (Matrix.Translation(pivot(source_id)) @ native_relation @
            Matrix.Translation(-pivot(target_id)))
