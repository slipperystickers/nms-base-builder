"""Check reproducible world directions and orientations using a real Flat Panel."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_support import bpy, module
from mathutils import Vector

duplicate = module('duplication_tools')
surface = module('curve_surface')
trim = module('edge_trim')
context = bpy.context
seed = module('builder_v2').add_part('BUILDFLATPANEL', high_res=False).object
seed.location = (1, 2, -3)
seed.rotation_euler = (.37, -.54, 1.22)
context.view_layer.update()
basis = seed.matrix_world.to_quaternion().normalized()


def check_rotation(guide):
    context.view_layer.update()
    for obj in duplicate.backend.children(guide):
        rotation = obj.matrix_world.to_quaternion().normalized()
        assert abs(rotation.dot(basis)) > .99999, (obj.name, rotation, basis)


guide = duplicate.create_axis(context, [seed])
for space, axis in [('GLOBAL', 'Y'), ('GLOBAL', 'X'), ('GLOBAL', 'Z'),
                    ('LOCAL', 'X'), ('LOCAL', 'Y'), ('LOCAL', 'Z'), ('GLOBAL', 'X')]:
    duplicate.change_axis(guide, axis, space)
    check_rotation(guide)
    direction = Vector(tuple(float(letter == axis) for letter in 'XYZ'))
    if space == 'LOCAL':
        direction = basis @ direction
    positions = [obj.matrix_world.translation for obj in duplicate.backend.children(guide)]
    for i, position in enumerate(sorted(positions, key=lambda p: p.dot(direction)), 1):
        expected = seed.location + direction * i * duplicate.step(guide)
        assert (position - expected).length < .0001, (space, axis, position, expected)

points = [Vector(p) for p in [(0,1,0), (.5,.2,0), (1,0,0), (9,0,0), (9.5,.2,0), (10,1,0)]]
limits = trim.Trace.from_path(points, False).longest_straight()
for trim_in_picker in (False, True):
    guide = surface.create_guides(context, [(points, False)])[0]
    duplicate.finish_edge(context, guide, [seed.name], limits if trim_in_picker else (0., 1.))
    if not trim_in_picker:
        trim.trim(guide, trim.Trace(guide), *limits)
    check_rotation(guide)
    assert len(guide.data.splines[0].bezier_points) == 2
    duplicate.adjust(guide, 'objects_count', 5)
    check_rotation(guide)
    assert max(abs(a-b) for a,b in zip(trim.Trace(guide).limits, limits)) < 1e-5
print('PASS Global and Part Local XYZ, return to X, pre-creation and post-creation Flat Panel trims')
