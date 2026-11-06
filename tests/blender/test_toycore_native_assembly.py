"""The corrected detailed generator keeps native parts and textures."""
import json
import os
from pathlib import Path
import sys

import bpy
from mathutils import Matrix, Vector
from mathutils.kdtree import KDTree

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_support import module

builder = module('builder_v2')
simple = module('simple_library')
part = module('part')
scene = bpy.context.scene
scene.bbe_detailed_proxies = True
assert simple.load_mesh('BASE_TOYCORE') is None  # Withdraw the invented model.

addon = Path(builder.FILE_PATH)
spec = json.loads((addon / 'resources/hd_library.json').read_text(encoding='utf-8'))
pack = Path(os.environ.get('BBE_ASSET_LIBRARY_ROOT') or
            Path(os.environ['LOCALAPPDATA']) / 'BaseBuilderExtended/asset-libraries')
original_path = pack / spec['id'] / 'assets/BASE_TOYCORE.blend'
correction_path = addon / 'resources/hd_corrections/BASE_TOYCORE.blend'
assert Path(builder.get_asset_index()['BASE_TOYCORE']).samefile(correction_path)

def read_mesh(path):
    with bpy.data.libraries.load(str(path), link=False) as (source, target):
        target.meshes = list(source.meshes)
    return next(mesh for mesh in target.meshes if mesh)

def coords(mesh, material_index, dy=0):
    vertices = {vertex for face in mesh.polygons if face.material_index == material_index
                for vertex in face.vertices}
    return sorted(tuple(round(value + (dy if axis == 1 else 0), 5)
                        for axis, value in enumerate(mesh.vertices[index].co))
                  for index in vertices)


def same_vertices(actual, expected, material_index, shift=0):
    original_points = [Vector(value) for value in coords(expected, material_index, shift)]
    corrected_points = [Vector(value) for value in coords(actual, material_index)]
    assert len(original_points) == len(corrected_points)
    tree = KDTree(len(original_points))
    for index, point in enumerate(original_points):
        tree.insert(point, index)
    tree.balance()
    assert max(tree.find(point)[2] for point in corrected_points) < 2e-5

original = read_mesh(original_path)
corrected = read_mesh(correction_path)
tip = max(vertex[1] for vertex in coords(original, 1))
assert 1.7 < tip < 1.9
same_vertices(corrected, original, 0)  # Base unchanged.
same_vertices(corrected, original, 1)  # Needle unchanged.
for index in range(4, 6):
    same_vertices(corrected, original, index, tip)
assert all(abs(p[1] - tip) < 2e-5 and Vector((p[0], p[2])).length < .773
           for p in coords(corrected, 3))
for index in (6, 7, 8):
    points = [Vector(p) for p in coords(corrected, index)]
    spans = [max(p[k] for p in points) - min(p[k] for p in points) for k in range(3)]
    assert min(spans) > .99 * max(spans), (index, spans)  # No flat card.
    radius = max(p.x for p in points)
    center = Vector((0, tip, 0))
    assert max(abs((p - center).length - radius) for p in points) < 2e-5
    # Use the native artwork, with view-dependent projection onto real geometry.
    mat = corrected.materials[index]
    assert Path(mat.node_tree.nodes.get('Diffuse').image.filepath).name == Path(original.materials[index].node_tree.nodes.get('Diffuse').image.filepath).name
    assert any(n.type == 'VECT_TRANSFORM' and n.convert_to == 'CAMERA' for n in mat.node_tree.nodes)
assert not any(face.material_index == 9 for face in corrected.polygons)

# A saved pre-fix display upgrades at file load without moving its part.
obj = bpy.data.objects.new('BASE_TOYCORE', original)
scene.collection.objects.link(obj)
obj['ObjectID'] = 'BASE_TOYCORE'
obj['UserData'] = str(part.Part.DEFAULT_USER_DATA)
original[builder.MESH_TAG] = 'BASE_TOYCORE'
obj.matrix_world = Matrix.Translation(Vector((3, 4, 5)))
placement = obj.matrix_world.copy()
assert builder.refresh_toycore_proxies(scene) == 1
assert obj.matrix_world == placement and obj['ObjectID'] == 'BASE_TOYCORE'
assert obj.data.get(builder.MESH_REVISION_TAG) == builder.MESH_REVISIONS['BASE_TOYCORE']
assert not any(face.material_index == 9 for face in obj.data.polygons)
assert builder.refresh_toycore_proxies(scene) == 0

scene.bbe_detailed_proxies = False
assert builder.refresh_toycore_proxies(scene) == 1
assert len(obj.data.vertices) == 92 and obj.matrix_world == placement
scene.bbe_detailed_proxies = True
assert builder.refresh_toycore_proxies(scene) == 1
assert len(obj.data.polygons) == len(corrected.polygons) and obj.matrix_world == placement
print('TOYCORE_NATIVE_ASSEMBLY_PASS', len(corrected.polygons), round(tip, 5), flush=True)
