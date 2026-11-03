"""Native-weight pilot skinning; pure NumPy, no game/process access.

Row-vector affine matrices are used throughout. Detailed assets retain four
native influences; lightweight assets retain all interpolated influences. The asset stores each native
vertex transformed into each influencing joint's bind space, which preserves
the separate inverse-bind matrices of referenced character components.
"""
import numpy as np


def global_matrices(parents, local_matrices):
    local = np.asarray(local_matrices, dtype=np.float64)
    result = np.empty_like(local)
    for i, parent in enumerate(parents):
        if parent >= i:
            raise ValueError('Skeleton must be ordered parent before child')
        result[i] = local[i] if parent < 0 else local[i] @ result[parent]
    return result


def apply_solver_pose(asset, solver_names=(), solver_local_matrices=()):
    local = np.array(asset['local_matrices'], dtype=np.float64)
    names = {str(n): i for i, n in enumerate(asset['names'])}
    for name, matrix in zip(solver_names, solver_local_matrices, strict=True):
        m = np.asarray(matrix, dtype=np.float64).reshape(4, 4).copy()
        m[:3, 3] = 0
        m[3, 3] = 1
        local[names[str(name)]] = m
    return global_matrices(asset['parents'], local)


def skin(asset, global_pose):
    matrices = np.asarray(global_pose, dtype=np.float64)
    joint_indices = asset['joint_indices']
    weights = asset['weights']
    points = asset['joint_points']
    result = np.zeros((len(points), 3), dtype=np.float64)
    for k in range(weights.shape[1]):
        transformed = np.einsum('ni,nij->nj', points[:, k], matrices[joint_indices[:, k]])
        result += transformed[:, :3] * weights[:, k, None]
    return result


def blender_coordinates(native_points):
    points = np.asarray(native_points)[:, [0, 2, 1]].copy()
    points[:, 1] *= -1
    return points
