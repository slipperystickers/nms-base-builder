"""Clean, binary-independent least-squares core of the native pilot IK solve.

All inputs are ordinary arrays. Float32 operation order intentionally follows the
observed bounded solver to retain agreement for nearly singular constraints.
"""
import numpy as np

F = np.float32

def assemble_normal_equations(constraints, dimension):
    """Each constraint is (strength, residual_vector, row_jacobian)."""
    stride = (dimension + 7) & ~7
    normal = np.zeros((dimension, stride), dtype=F)
    rhs = np.zeros(dimension, dtype=F)
    threshold = F(1.25e-7)
    for strength, values, jacobian in constraints:
        strength2 = F(F(strength) * F(strength))
        for value, row in zip(np.asarray(values, dtype=F), np.asarray(jacobian, dtype=F)):
            for i in range(dimension):
                if abs(row[i]) <= threshold:
                    continue
                rhs[i] -= F(F(row[i] * value) * strength2)
                start = i & ~7
                normal[i,start:dimension] += row[start:dimension] * F(row[i] * strength2)
    return normal, rhs

def regularize(normal, rhs, variables, weights):
    normal, rhs = np.array(normal, dtype=F, copy=True), np.array(rhs, dtype=F, copy=True)
    variables, weights = np.asarray(variables, dtype=F), np.asarray(weights, dtype=F)
    rhs += (variables * weights) * -weights
    idx = np.arange(len(rhs))
    normal[idx, idx] += weights * weights
    return normal, rhs

def solve_normal_equations(normal, rhs):
    """Upper Cholesky factorization with the native scalar summation order."""
    upper = np.array(normal, dtype=F, copy=True)
    rhs = np.asarray(rhs, dtype=F)
    n = len(rhs)
    diagonal = np.zeros(n, dtype=F)
    for i in range(n):
        start = i & ~7
        for j in range(i - 1, -1, -1):
            upper[i,start:] -= upper[j,start:] * upper[j,i]
        reciprocal = F(F(1) / np.sqrt(upper[i,i]))
        upper[i,start:] *= reciprocal
        diagonal[i] = upper[i,i]
    step = np.empty(n, dtype=F)
    for i in range(n):
        value = rhs[i]
        for j in range(i-1, -1, -1):
            value = F(value - F(upper[j,i] * step[j]))
        step[i] = F(value / diagonal[i])
    for i in range(n-1, -1, -1):
        value = step[i]
        for j in range(i+1, n):
            value = F(value - F(upper[i,j] * step[j]))
        step[i] = F(value / diagonal[i])
    return step, upper

def update_variables(variables, step, factor):
    return np.asarray(variables,dtype=F) + np.asarray(step,dtype=F) * F(factor)
