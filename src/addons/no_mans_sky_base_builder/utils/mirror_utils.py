import json
import bpy
import math
from pathlib import Path

from mathutils import Matrix, Euler, Vector

MIRROR_CORRECTIONS_PATH = (
    Path(__file__).resolve().parents[1] / "resources" / "mirror_corrections.json"
)


def load_mirror_corrections():
    with open(MIRROR_CORRECTIONS_PATH, "r", encoding="utf-8") as stream:
        return json.load(stream)


MIRROR_CORRECTIONS = load_mirror_corrections()
LOCAL_Y_180_ROTATION_PARTS = set(MIRROR_CORRECTIONS["local_y_180_rotation_parts"])
LOCAL_Y_90_ROTATION_PARTS = set(MIRROR_CORRECTIONS["local_y_90_rotation_parts"])
MIRROR_Z_180_IDENTIFIERS = set(MIRROR_CORRECTIONS["mirror_z_180_identifiers"])
POSITION_OFFSETS = {
    part: Vector(offset)
    for part, offset in MIRROR_CORRECTIONS["position_offsets"].items()
}


def ShowMessageBox(message="", title="Message Box", icon="INFO"):
    def draw(self, context):
        self.layout.label(text=message)
    bpy.context.window_manager.popup_menu(draw, title=title, icon=icon)


def mirror_matrix_world(object_id, old_matrix_world, across_x=True):
    """Compatibility entry point using the same geometry-aware reflection."""
    center = Vector((0, 0, 0))
    if not across_x:
        center.x = old_matrix_world.translation.x
    return mirror_matrix_world_universal(object_id, old_matrix_world, "X", center)

def reflect_point_across(source,origin):
    return (2 * origin) - source


def reflect_point(source,origin, axis):
    """reflects a point across give asix assuming origin as center of reflection

    Args:
        source (Vector): location of point to be mirrored
        origin (Vector): center of reflection
        axis (String): ( Takes "X","Y","Z" ), direction in which to morror

    Returns:
        Vector: Location of mirrored point
    """
    if origin is None:
        return source
    
    x = reflect_point_across(source.x, origin.x) if axis == "X" else source.x
    y = reflect_point_across(source.y, origin.y) if axis == "Y" else source.y
    z = reflect_point_across(source.z, origin.z) if axis == "Z" else source.z
    return Vector((x,y,z))

# Each entry maps the target native mesh back to the reflected source mesh.
# Generated and checked against actual asset surfaces, including variant offsets.
with open(Path(__file__).resolve().parents[1] / "resources" / "mirror_geometry.json",
          encoding="utf-8") as _stream:
    GEOMETRY_RELATIONS = json.load(_stream)


def mirror_matrix_world_universal(object_id, old_matrix_world, axis=None,
                                  center=None, mirror_part_exist=False):
    """Reflect the world placement and compensate the native mesh's handedness.

    S_world @ placement @ source_to_target_reflection keeps object transforms
    right-handed, so the result survives NMS Position/Up/At serialization.
    Euler sign changes only cover a mesh symmetric about local X; that was
    wrong for angled walls, rotated native variants, and off-centre meshes.
    """
    if axis not in {"X", "Y", "Z"} or center is None:
        return old_matrix_world.copy()
    relation = native_geometry_reflection(object_id, mirror_part_exist)
    if relation is None:
        # Preserve legacy part-specific corrections for unaudited/asymmetric
        # assets. Full matrices also preserve all scale axes and avoid Euler
        # singularities for every world reflection plane.
        relation = Matrix.Diagonal((-1.0, 1.0, 1.0, 1.0))
        if object_id:
            relation = relation @ mirror_correction(object_id, Matrix.Identity(4))
    world = Matrix.Identity(4)
    index = "XYZ".index(axis)
    world[index][index] = -1.0
    world[index][3] = 2.0 * center[index]
    return world @ old_matrix_world @ relation


def native_geometry_reflection(object_id, mirror_part_exist=False):
    identity = str(object_id or "").lstrip("^")
    record = GEOMETRY_RELATIONS.get(identity)
    if record is None:
        return None
    # A counterpart relation must only be used when its mesh is also swapped.
    expected_target = record["target"]
    if expected_target != identity and not mirror_part_exist:
        return None
    return Matrix(record["matrix"])


def mirror_matrix_world_universal_2(object_id, old_matrix_world, axis=None, center=None, mirror_part_exist = False):
    if axis not in {"X", "Y", "Z"} or center is None:
        return old_matrix_world.copy()

    # Extract the basic transformation components
    location, rotation_quaternion, scale = old_matrix_world.decompose()
    
    flip_vector = Vector((
        -1.0 if axis == "X" else 1.0,
        -1.0 if axis == "Y" else 1.0,
        -1.0 if axis == "Z" else 1.0,
    ))
    
    rotation_matrix = rotation_quaternion.to_matrix()
    rotation_matrix.col[0] *= flip_vector       # local X
    rotation_matrix.col[1] *= flip_vector * -1  # local Y
    rotation_matrix.col[2] *= flip_vector       # local Z
    
    # Mirror Position based on the chosen global mirror plane
    location_vector = reflect_point(location, center, axis)

    # rotation matrix
    new_rotation_matrix = rotation_matrix.to_4x4()
    # translation matrix
    new_translation_matrix = Matrix.Translation(location_vector)
    # scale matrix
    new_scale_matrix = Matrix.Scale(scale.x, 4)
    
    rotation_correction = Matrix.Rotation(math.pi, 4, "Z" if mirror_part_exist else "X")
    # combined matrix
    matrix_world = new_translation_matrix @ new_rotation_matrix @ new_scale_matrix @ rotation_correction

    return matrix_world


# This function changes orientation of object my adding 180 degree to its rotation value
# This is useful when used on Corvette parts
def change_orientation(object_id, old_matrix_world, axis = None, has_mirror_part = False):
    #mirror rotation across x axis
    local_rotation = Matrix.Rotation(0, 4, "X")
    if axis == "X" and not has_mirror_part:
        local_rotation = Matrix.Rotation(math.pi, 4, "X")
    if axis == "Y":
        local_rotation = Matrix.Rotation(math.pi, 4, "Y")
    elif axis == "Z":
        local_rotation = Matrix.Rotation(math.pi, 4, "Z")

    return old_matrix_world @ local_rotation


#This function provides additional corrections after mirroring object
def mirror_correction(object_id, matrix_world):
    #All triangular floor tiles
    if any(identifier in object_id for identifier in MIRROR_Z_180_IDENTIFIERS):
        angle = math.pi  #180 degrees
        z_rot_180 = Matrix.Rotation(angle, 4, "Z")
        return matrix_world @ z_rot_180

    #Apply per-part position offset corrections
    if object_id in POSITION_OFFSETS:
        translation_matrix = Matrix.Translation(POSITION_OFFSETS[object_id])
        return matrix_world @ translation_matrix

    #Parts that need rotation by 180 on local Y axis
    if object_id in LOCAL_Y_180_ROTATION_PARTS:
        angle = math.pi  #180 degrees
        y_rot_180 = Matrix.Rotation(angle, 4, "Y")
        return matrix_world @ y_rot_180
    
    #Parts that need rotation by 90 on local Y axis
    if object_id in LOCAL_Y_90_ROTATION_PARTS:
        angle = math.pi/2  #90 degrees
        y_rot_90 = Matrix.Rotation(angle, 4, "Y")
        return matrix_world @ y_rot_90

    return matrix_world

