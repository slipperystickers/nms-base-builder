"""Clean NumPy foot-constraint mathematics, independent of game binaries.

Supported scope: the enabled cockpit path, with foot glue disabled and no
external animated-foot provider. All matrices use row-vector XYZ conventions.
"""
from dataclasses import dataclass
import numpy as np

F = np.float32


def length3(vector):
    v = np.asarray(vector, dtype=np.float32)[:3]
    q = v * v
    return F(np.sqrt(F(F(q[1] + q[0]) + q[2])))


def point4(point, matrix, extra_w=False):
    """Native row affine transform; W is preserved only for fixture auditing."""
    p = np.asarray(point, dtype=np.float32)
    m = np.asarray(matrix, dtype=np.float32)
    result = p[0] * m[0]
    if extra_w:
        result = result + np.array([0, 0, 0, 1], dtype=np.float32)
    result = result + p[1] * m[1]
    result = result + p[2] * m[2]
    return result + m[3]


def world_point4(point, matrix):
    # This order matches the planted-target cache update, which sums Y then X.
    p = np.asarray(point, dtype=np.float32)
    m = np.asarray(matrix, dtype=np.float32)
    return ((p[1] * m[1] + p[0] * m[0]) + p[2] * m[2]) + m[3]


@dataclass
class FootSettings:
    bone: int
    chain_root: int
    local_offset: np.ndarray
    stored_target: np.ndarray
    target_stiffness: float
    base_height: float
    ray_correction: float
    slope_degrees: float
    plant_threshold: float
    character_extent: float
    reach_scale: float = 0.0
    foot_glue: bool = False
    plane_point: np.ndarray | None = None
    plane_normal: np.ndarray | None = None
    plane_weight: float = 1.0
    plane_offset: float = 0.0


def prepare_foot(settings, original_node_matrix, working_node_matrix,
                 global_matrices, global_rotations, parents, model_matrix=None):
    """Prepare a fixed point/orientation target for the generic IK solve.

    The ray correction is a collision-derived input, already clamped and
    smoothed by the foot-ray stage. It is NOT an additional model-root offset.
    Returns a new target; no input arrays are mutated.
    """
    if settings.foot_glue:
        raise NotImplementedError("Foot-glue history is outside the validated cockpit path")
    mats = np.asarray(global_matrices, dtype=np.float32)
    offset = np.asarray(settings.local_offset, dtype=np.float32).copy()
    stored = np.asarray(settings.stored_target, dtype=np.float32)
    chain_length = F(0)
    node = settings.bone
    visited = set()
    while node != settings.chain_root:
        if node in visited or node < 0 or node >= len(parents):
            raise ValueError("Foot chain does not reach its declared root")
        visited.add(node)
        parent = int(parents[node])
        if parent < 0:
            raise ValueError("Foot chain reached an invalid parent")
        chain_length = F(chain_length + length3(mats[node, 3] - mats[parent, 3]))
        node = parent

    old_point = point4(offset, original_node_matrix, extra_w=True)
    new_point = point4(offset, working_node_matrix, extra_w=True)
    target = new_point + (stored - old_point) * F(settings.target_stiffness)
    correction = F(settings.ray_correction)
    if settings.plane_point is not None:
        p = np.asarray(settings.plane_point, dtype=np.float32)
        normal = np.asarray(settings.plane_normal, dtype=np.float32)
        if normal[1] == 0:
            raise ValueError("The projected foot plane must have a nonzero Y normal")
        displacement = target - p
        height = F(p[1] - F(F(normal[0] * displacement[0] + normal[2] * displacement[2]) / normal[1]))
        correction = F(F(height * F(settings.plane_weight)) + F(settings.plane_offset))
    target[1] = F(F(settings.base_height) + correction)
    planted = F(settings.plant_threshold) > stored[1]
    planted_world = world_point4(target, model_matrix) if planted and model_matrix is not None else None
    unclamped_target = target.copy()

    if settings.reach_scale > 0 and settings.chain_root >= 0:
        root_position = mats[settings.chain_root, 3]
        displacement = target - root_position
        distance = length3(displacement)
        max_distance = F(F(length3(offset) + chain_length) * F(settings.reach_scale))
        if distance > max_distance and max_distance > F(1.52587890625e-5):
            target = F(max_distance / distance) * displacement + root_position
    if length3(target - mats[settings.bone, 3]) >= F(F(settings.character_extent) * F(20)):
        target = mats[settings.bone, 3].copy()

    rotation = np.asarray(global_rotations, dtype=np.float32)[settings.bone].copy()
    rotation = rotation + np.array([F(F(settings.slope_degrees) * F(0.01745329238474369)), 0, 0, 1], dtype=np.float32)
    return dict(target=target, local_offset=offset, rotation=rotation,
                chain_length=chain_length, planted=bool(planted),
                planted_world=planted_world, unclamped_target=unclamped_target,
                ray_correction=correction)


def foot_residual(position, rotation, position_jacobian, rotation_jacobian,
                  target, target_rotation, position_weight, rotation_weight):
    """Six residual rows and their analytic derivative rows.

    The shared kinematics kernel supplies point and rotation-vector values and
    Jacobians. Native wrapping changes the value, but leaves its Jacobian as
    supplied. Global constraint strength is applied by the solver separately.
    """
    p = np.asarray(position, dtype=np.float32)[:3]
    angle = np.asarray(rotation, dtype=np.float32)[:3].copy()
    goal = np.asarray(target_rotation, dtype=np.float32)[:3]
    if length3(angle) != 0:
        difference = goal - angle
        for _ in range(64):
            q = difference * difference
            squared = F(F(q[1] + q[0]) + q[2])
            if squared <= F(9.86960506439209):
                break
            angle = angle + (F(1) / F(np.sqrt(squared))) * difference * F(6.2831854820251465)
            difference = goal - angle
        else:
            raise ValueError("Rotation wrapping did not converge")
    wp, wr = F(position_weight), F(rotation_weight)
    residual = np.concatenate(((p - np.asarray(target, dtype=np.float32)[:3]) * wp,
                               (angle - goal) * wr))
    jacobian = np.concatenate((np.asarray(position_jacobian, dtype=np.float32) * wp,
                               np.asarray(rotation_jacobian, dtype=np.float32) * wr), axis=0)
    return residual, jacobian


def cache_solved_foot(global_matrices, bone):
    """Post callback: cache one solved foot matrix; never change the pose."""
    return np.asarray(global_matrices, dtype=np.float32)[bone].copy()
