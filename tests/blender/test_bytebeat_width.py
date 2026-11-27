"""Free ByteBeat thickness survives placement, division, JSON, and device binding."""
import sys
from pathlib import Path

import bpy
from mathutils import Vector

sys.path.insert(0, str(Path(__file__).parent))
from test_support import addon, module

cables = module('cable_connections')
builder = addon.BUILDER
kind = cables.BYTEBEAT
ctx = bpy.context

def near(a, b):
    assert (Vector(a) - Vector(b)).length < 1e-4, (a, b)

def assert_width(obj, width):
    ctx.view_layer.update()
    near([obj.scale.x, obj.scale.y], [width, width])
    record = builder.get_builder_object_from_bpy_object(obj).serialise()
    assert abs(Vector(record['Up']).length - width) < 1e-4, record
    return record

for detailed in (False, True):
    bpy.data.batch_remove(list(ctx.scene.objects))
    builder.clear_caches()
    ctx.scene.bbe_detailed_proxies = detailed
    a, b = Vector((3, -2, 1)), Vector((5, 4, -2))
    wire = cables.connect(None, '', None, '', kind, builder, free_start=a, free_end=b)
    ends = cables.endpoints(wire)
    original = assert_width(wire, 1.)
    original_dimensions = wire.dimensions.copy()
    wire.bbe_bytebeat_width = 3.25
    record = assert_width(wire, 3.25)
    near(wire.dimensions, (original_dimensions.x * 3.25, original_dimensions.y * 3.25, original_dimensions.z))
    near(ends[0].matrix_world.translation, a)
    near(ends[1].matrix_world.translation, b)
    for key in ('Position', 'At'):
        near(record[key], original[key])

    bpy.data.batch_remove(list(ctx.scene.objects))
    builder.clear_caches()
    importer = module('builder_v2') if detailed else builder
    importer.deserialise_from_data({'BaseVersion': 8, 'Objects': [record]})
    wire, = [o for o in ctx.scene.objects if o.get('ObjectID') == kind]
    restored = assert_width(wire, 3.25)
    for key in ('Position', 'At', 'Up'):
        near(restored[key], record[key])
    for end, expected in zip(cables.endpoints(wire), (a, b)):
        near(end.matrix_world.translation, expected)
    middle, = cables.subdivide(wire, [.5], builder)
    spans = [o for o in ctx.scene.objects if o.get('ObjectID') == kind]
    assert len(spans) == 2
    for obj in spans:
        assert_width(obj, 3.25)
    device = builder.add_part('BYTEBEAT', build_rigs=False).object
    device.location = (5, 1, 2)
    ctx.view_layer.update()
    key, = cables.local_sockets(device, kind)
    cables.bind(middle, device, key, kind)
    for obj in spans:
        assert not cables.free_bytebeat(obj)
        assert_width(obj, 1.)
        obj.bbe_bytebeat_width = 5
        assert_width(obj, 1.)
    device.location.x += 2
    ctx.view_layer.update()
    near(middle.matrix_world.translation, cables.sockets(device, kind)[key])
    outer = [next(e for e in cables.endpoints(obj) if e != middle) for obj in spans]
    for point in (a,b):
        assert any((e.matrix_world.translation - point).length < 1e-4 for e in outer)
print('PASS ByteBeat thickness, fixed endpoints, Simple and Detailed round trips, shared socket binding')
