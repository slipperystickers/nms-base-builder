"""Clean center-of-mass constraint equations for pilot hand calibration.

Ordinary weighted centroid and derivative accumulation; no native executable,
runtime addresses, or process access is needed by these functions.
"""
import numpy as np

F32 = np.float32

def weighted_center(matrices, masses):
    matrices = np.asarray(matrices, dtype=np.float32).reshape(-1, 4, 4)
    masses = np.asarray(masses, dtype=np.float32)
    total = F32(0)
    center = np.zeros(3, dtype=np.float32)
    for matrix, mass in zip(matrices, masses, strict=True):
        center += matrix[3, :3] * mass
        total = F32(total + mass)
    if not total > 0:
        raise ValueError('Center-of-mass constraint needs positive total mass')
    return center * F32(1 / total), total

def prepare_target(initial_matrices, masses, offset):
    center, _ = weighted_center(initial_matrices, masses)
    return center + np.asarray(offset, dtype=np.float32)

def residual_and_jacobian(current_matrices, masses, target, solver_scale=1., point_jacobians=None):
    center, total = weighted_center(current_matrices, masses)
    residual = (center - np.asarray(target, dtype=np.float32)) * F32(solver_scale)
    if point_jacobians is None:
        return residual, None
    jacobians = np.asarray(point_jacobians, dtype=np.float32)
    derivative = np.zeros_like(jacobians[0])
    for derivative_i, mass in zip(jacobians, masses, strict=True):
        derivative += derivative_i * F32(mass)
    derivative *= F32(1 / total)
    derivative *= F32(solver_scale)
    return residual, derivative


