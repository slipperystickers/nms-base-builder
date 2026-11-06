"""Native NMS vertex normals, including Forsaken's packed tangent layout."""
import numpy as np


def decode_octahedral(packed):
    # Semantic 11 stores the normal in the low two unsigned 10-bit fields.
    # 512 is zero, 1/1023 are -1/+1; the remaining bits encode the tangent.
    x = ((packed & 1023).astype(np.float64) - 512.0) / 511.0
    y = (((packed >> 10) & 1023).astype(np.float64) - 512.0) / 511.0
    n = np.column_stack((x, y, 1.0 - np.abs(x) - np.abs(y)))
    fold = np.maximum(-n[:, 2], 0.0)
    n[:, :2] += np.where(n[:, :2] >= 0, -fold[:, None], fold[:, None])
    length = np.linalg.norm(n, axis=1)
    if not np.isfinite(length).all() or np.any(length < 1e-8):
        raise ValueError('Invalid packed native normals')
    return n / length[:, None]


def read_normals(geometry, stream, raw, count, legacy_decode):
    layout = geometry.VertexLayout
    element = next((v for v in layout.VertexElements if v.SemanticID in (2, 11)), None)
    if element is None:
        raise ValueError('Native normal format is missing or unsupported')
    packed = np.ndarray((count,), dtype=np.uint32, buffer=raw,
                        offset=stream.VertexDataOffset + element.Offset,
                        strides=(layout.Stride,))
    if element.SemanticID == 11:
        return decode_octahedral(packed)
    return np.nan_to_num(legacy_decode(packed.astype(np.int64)).T)
