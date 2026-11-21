"""Native doorway frames merged into temporary hab display meshes."""
import json
from pathlib import Path
from functools import lru_cache
import bpy
import numpy as np
from mathutils import Matrix

ROOT=Path(__file__).parent/'resources'

@lru_cache(None)
def frames():
    return json.loads((ROOT/'hab_doorway_frames.json').read_text())

def doorway_mesh(style,axis,detailed):
    key=axis+'_'+style+(' detailed' if detailed else ' simple')
    mesh=next((m for m in bpy.data.meshes if m.get('bbe_doorway_asset')==key),None)
    if mesh is None:
        with bpy.data.libraries.load(str(ROOT/'hab_doorways.blend'),link=False) as (a,b):
            b.meshes=['BBE Doorway '+key]
        mesh=b.meshes[0]
    return mesh

def column(collection, field, dtype, width=1):
    data = np.empty(len(collection) * width, dtype=dtype)
    collection.foreach_get(field, data)
    return data.reshape(-1, width) if width > 1 else data


def build_preview(source, original, pid, keep, slots, detailed, name):
    """Copy the kept polygons and native frames directly into one display mesh."""
    pieces = [(source, None)]
    locators = frames()['hab' if pid.startswith('B_HAB_') else 'walkway'] if slots else {}
    for slot in sorted(slots):
        axis = 'NS' if slot[4] in 'NS' else 'EW'
        pieces.append((doorway_mesh(pid[-1], axis, detailed), Matrix(locators[slot])))

    coords, sizes, corners, indices, smooth, normals = [], [], [], [], [], []
    materials = list(original.materials)
    uvs = {layer.name: [] for mesh, _ in pieces for layer in mesh.uv_layers}
    offset = 0
    for mesh, transform in pieces:
        counts = column(mesh.polygons, 'loop_total', np.int32)
        face_mask = keep if transform is None else slice(None)
        loop_mask = np.repeat(keep, counts) if transform is None else slice(None)
        positions = column(mesh.vertices, 'co', np.float32, 3)
        vectors = column(mesh.corner_normals, 'vector', np.float32, 3)[loop_mask]
        material = column(mesh.polygons, 'material_index', np.int32)[face_mask]
        if transform is not None:
            basis = np.asarray(transform.to_3x3(), dtype=np.float32)
            positions = positions @ basis.T + np.asarray(transform.translation, dtype=np.float32)
            vectors = vectors @ np.linalg.inv(basis)
            vectors /= np.maximum(np.linalg.norm(vectors, axis=1, keepdims=True), 1e-12)
            remap = []
            for mat in mesh.materials:
                if mat not in materials:
                    materials.append(mat)
                remap.append(materials.index(mat))
            if remap:
                material = np.asarray(remap, dtype=np.int32)[material]
        coords.append(positions)
        sizes.append(counts[face_mask])
        corners.append(column(mesh.loops, 'vertex_index', np.int32)[loop_mask] + offset)
        indices.append(material)
        smooth.append(column(mesh.polygons, 'use_smooth', np.bool_)[face_mask])
        normals.append(vectors)
        for key, buffers in uvs.items():
            layer = mesh.uv_layers.get(key)
            buffers.append(column(layer.uv, 'vector', np.float32, 2)[loop_mask] if layer
                           else np.zeros((len(corners[-1]), 2), dtype=np.float32))
        offset += len(positions)

    result = bpy.data.meshes.new(name)
    try:
        lengths = np.concatenate(sizes)
        starts = np.cumsum(lengths, dtype=np.int32) - lengths
        result.vertices.add(offset)
        result.vertices.foreach_set('co', np.concatenate(coords).ravel())
        result.loops.add(sum(map(len, corners)))
        result.loops.foreach_set('vertex_index', np.concatenate(corners))
        result.polygons.add(len(starts))
        result.polygons.foreach_set('loop_start', starts)
        for mat in materials:
            result.materials.append(mat)
        result.polygons.foreach_set('material_index', np.concatenate(indices))
        result.polygons.foreach_set('use_smooth', np.concatenate(smooth))
        result.update(calc_edges=True)
        for key, buffers in uvs.items():
            result.uv_layers.new(name=key).uv.foreach_set('vector', np.concatenate(buffers).ravel())
        # Blender 5.1 accepts float corner normals directly. Avoid constructing
        # hundreds of thousands of Python vectors for a single detailed hab.
        directions = np.concatenate(normals)
        lengths = np.linalg.norm(directions, axis=1)
        missing = lengths < 1e-8
        directions /= np.maximum(lengths[:, None], 1e-8)
        if missing.any():
            directions[missing] = column(result.corner_normals, 'vector', np.float32, 3)[missing]
        custom = result.attributes.new('custom_normal', 'FLOAT_VECTOR', 'CORNER')
        custom.data.foreach_set('vector', directions.ravel())
        result.update()
        for key, value in original.items():
            result[key] = value
        return result
    except Exception:
        bpy.data.meshes.remove(result)
        raise
