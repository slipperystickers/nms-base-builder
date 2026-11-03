"""Add a test decal to HalloweenBuild; never write the supplied scene."""
import hashlib
import math
import sys
import types
import zipfile
from pathlib import Path

import bpy
from mathutils import Matrix, Vector

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_support import addon, module, report

ctrl = module('decal_controls')
decals = module('decals')
builder = module('builder_v2')
source = Path(bpy.data.filepath)
digest = hashlib.sha256(source.read_bytes()).hexdigest()
original_matrices = {o.name: o.matrix_world.copy() for o in bpy.context.scene.objects}
target = bpy.data.objects['B_STR_H_Y_NW.023']
poly = target.data.polygons[252]
point = target.matrix_world @ poly.center
normal = (target.matrix_world.to_3x3().inverted().transposed() @ poly.normal).normalized()
hit = ctrl.surface_hit(bpy.context, point+normal*.15, -normal)
assert hit and hit[2] == target

for obj in bpy.context.selected_objects:
    obj.select_set(False)
bpy.context.scene.bbe_detailed_proxies = True
decal = builder.add_part('BUILDDECALNUM0', user_data=1, build_rigs=False).object
assert decals.has_native_artwork(decal.data), 'Use the real decal artwork, not the FBX fallback'
decal.matrix_world = Matrix.Diagonal((.265, .265, .265, 1))
bpy.context.view_layer.objects.active = decal
decal.select_set(True)
decal.matrix_world = ctrl.surface_matrix(decal, hit[0], hit[1])
bpy.context.view_layer.update()
outward = (decal.matrix_world.to_3x3().inverted().transposed() @ Vector((0, 1, 0))).normalized()
assert outward.dot(hit[1]) > .99999
assert (decal.matrix_world.translation-hit[0]).length < .00201
assert all(abs(v-.265) < 1e-6 for v in decal.matrix_world.to_scale())
assert ctrl.BBE_GGT_decal_controls.poll(bpy.context)

receivers = [o for o in bpy.context.scene.objects if o.type == 'MESH' and o.get('ObjectID')
             and not decals.is_decal(o) and not o.hide_render and not o.hide_viewport]
assert decals.project(decal, receivers, {})
actual_receivers = list(decal.data.get('bbe_decal_receivers', []))
assert target.name in actual_receivers, actual_receivers
assert ctrl.surface_hit(bpy.context, point+normal*.15, -normal)[2] == target
record = addon.BUILDER.get_builder_object_from_bpy_object(decal).serialise()
assert record['ObjectID'] == '^BUILDDECALNUM0'
expected = Matrix.Rotation(-math.pi/2, 4, 'X') @ decal.matrix_world
assert (Vector(record['Position'])-expected.translation).length < 1e-5
assert (Vector(record['Up'])-expected.col[1].to_3d()).length < 1e-5
before = decal.matrix_world.copy()
assert bpy.ops.bbe.adjust_decal(distance=.01) == {'FINISHED'}
bpy.context.view_layer.update()
assert (decal.matrix_world.translation-before.translation-outward*.01).length < 1e-5
assert bpy.ops.bbe.adjust_decal(angle=math.radians(5)) == {'FINISHED'}
bpy.context.view_layer.update()
after_normal = (decal.matrix_world.to_3x3().inverted().transposed() @ Vector((0, 1, 0))).normalized()
assert after_normal.dot(outward) > .99999
target.select_set(True)
assert not ctrl.BBE_GGT_decal_controls.poll(bpy.context)
target.select_set(False)

# The game paints protrusions AND recesses. Never select a single depth band.
def plane(name, y):
    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata([(-2, y, -2), (-2, y, 2), (2, y, 2), (2, y, -2)], [], [(0, 1, 2, 3)])
    mesh.update()
    obj = bpy.data.objects.new(name, mesh)
    obj['ObjectID'] = 'BLD_FIREPIT'
    bpy.context.collection.objects.link(obj)
    return obj
front, rear = plane('Test front surface', .12), plane('Test rear surface', .01)
for y in (0, .04, .1, .16):
    decal.matrix_world = Matrix.Translation((0, y, 0))
    bpy.context.view_layer.update()
    matrix = decal.matrix_world.copy()
    assert decals.project(decal, [rear, front], {})
    assert set(decal.data['bbe_decal_receivers']) == {front.name, rear.name}
    assert decal.matrix_world == matrix, 'Preview moved the exported placement'
# A narrow front strip off the centre ray must still receive artwork.
for vertex in front.data.vertices:
    vertex.co.x = .2 if vertex.co.x < 0 else .5
front.data.update()
assert decals.project(decal, [rear, front], {})
assert set(decal.data['bbe_decal_receivers']) == {front.name, rear.name}
saved_record = addon.BUILDER.get_builder_object_from_bpy_object(decal).serialise()
saved_matrix = decal.matrix_world.copy()
assert bpy.ops.bbe.toggle_decal_projection() == {'FINISHED'}
decals.project(decal, [rear, front], {})
assert decal.data.get('bbe_decal_floating')
assert len(decal.data.vertices) == 4
assert not decal.data['bbe_decal_receivers']
assert addon.BUILDER.get_builder_object_from_bpy_object(decal).serialise() == saved_record
assert decal.matrix_world == saved_matrix
assert bpy.ops.bbe.toggle_decal_projection() == {'FINISHED'}
decals.project(decal, [rear, front], {})
assert set(decal.data['bbe_decal_receivers']) == {front.name, rear.name}
assert addon.BUILDER.get_builder_object_from_bpy_object(decal).serialise() == saved_record
previous = Path(__file__).resolve().parents[2] / 'dist/no_mans_sky_base_builder-18.2.14.zip'
with zipfile.ZipFile(previous) as archive:
    baseline_code = archive.read('decals.py').decode('utf-8')
legacy = types.ModuleType(addon.__name__ + '.previous_decal_test')
legacy.__package__ = addon.__name__
exec(compile(baseline_code, '18.2.14/decals.py', 'exec'), legacy.__dict__)
white = builder.add_part('BUILDDECAL2', build_rigs=False).object
white.matrix_world = Matrix.Identity(4)
def displayed(obj):
    return (tuple(tuple(v.co) for v in obj.data.vertices),
            tuple(tuple(p.vertices) for p in obj.data.polygons),
            tuple(tuple(v.uv) for v in obj.data.uv_layers.active.data))
# Include a vertical step wall in the calibrated back-wrap range.
step_mesh = bpy.data.meshes.new('Stair riser')
step_mesh.from_pydata([(-.5, -.25, 0), (.5, -.25, 0), (.5, .1, 0), (-.5, .1, 0)], [], [(0, 1, 2, 3)])
step_mesh.update()
step = bpy.data.objects.new('Stair riser', step_mesh)
step['ObjectID'] = 'B_WALL_Q_H1'
bpy.context.collection.objects.link(step)
stair_receivers = [front, rear, step]
legacy.project(white, stair_receivers, {})
expected_white = displayed(white)
decals.project(white, stair_receivers, {})
assert displayed(white) == expected_white, 'Calibrated White Border stair projection changed'
for name, matrix in original_matrices.items():
    assert bpy.data.objects[name].matrix_world == matrix, name
assert hashlib.sha256(source.read_bytes()).hexdigest() == digest
report('decal_surface_placement', dict(blender=bpy.app.version_string, target=target.name,
       projected_receivers=actual_receivers, multiple_depths=True, flat_preview_export_unchanged=True,
       white_border_matches_18_2_14=True, source_unchanged=True))
print('DECAL_SURFACE_PLACEMENT_PASS', flush=True)

