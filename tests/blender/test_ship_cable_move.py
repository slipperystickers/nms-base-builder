"""Translate a ship with socket-bound ends, free ends, and shared cable junctions."""
from pathlib import Path
import sys

import bpy
from mathutils import Vector

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_support import addon, module

cables = module('cable_connections')
builder = addon.BUILDER
scene = bpy.context.scene
layer = bpy.context.view_layer
scene.nms_main.new_file()


def select_parts(parts, active):
    bpy.ops.object.select_all(action='DESELECT')
    for obj in parts:
        obj.select_set(True)
    layer.objects.active = active
    layer.update()


def line(kind, start, end):
    part = builder.add_part(kind, build_rigs=False)
    part.build_rig(start, end)
    return part.object


def near(actual, expected, message):
    assert (Vector(actual) - Vector(expected)).length < 1e-4, (message, actual, expected)


device = builder.add_part('U_MINIPORTAL', build_rigs=False).object
bound = cables.make_control(builder, 'powered socket', cables.POWER)
cables.bind(bound, device, 'POWER_A', cables.POWER)
joint = cables.junction(builder, cables.POWER, (3, 1, 2))
tails = [cables.make_control(builder, 'free wire end', cables.POWER) for _ in range(2)]
tails[0].location = (7, 0, 3)
tails[1].location = (3, 5, 0)
lines = [line(cables.POWER, bound, joint),
         line(cables.POWER, joint, tails[0]),
         line(cables.POWER, joint, tails[1])]
for i, kind in enumerate((cables.BYTEBEAT, cables.SUPPLY, cables.TELEPORT)):
    start = cables.make_control(builder, 'start', kind)
    end = cables.make_control(builder, 'end', kind)
    start.location = (10 + i, 3, 4)
    end.location = (10 + i, 7, 9)
    lines.append(line(kind, start, end))

unselected = builder.add_part(cables.SUPPLY, build_rigs=False)
unselected.build_rig()
unmoved = [unselected.object, *cables.endpoints(unselected.object)]
layer.update()
select_parts([device, *lines], lines[0])  # Box selection of visible ship pieces can miss the tiny controls.
ends = {end for obj in lines for end in cables.endpoints(obj)}
before = {o: o.matrix_world.translation.copy() for o in [device, *ends, *lines, *unmoved]}
records = [builder.get_builder_object_from_bpy_object(o).serialise() for o in lines]
delta = Vector((4, -6, 1.5))
assert bpy.ops.transform.translate(value=delta) == {'FINISHED'}
layer.update()
for obj, position in before.items():
    near(obj.matrix_world.translation, position if obj in unmoved else position + delta, obj.name)
for obj, original in zip(lines, records):
    row = builder.get_builder_object_from_bpy_object(obj).serialise()
    near(row['Position'], Vector(original['Position']) + Vector((delta.x, delta.z, -delta.y)), obj.name)
    near(row['At'], original['At'], obj.name + ' changed direction or length')
assert cables.attached_device(bound) == device

# A shared junction stays put when one incident branch is outside the selection.
select_parts([], None)
select_parts([device, lines[0], lines[1]], device)
assert not joint.select_get() and not tails[1].select_get()
assert tails[0].select_get()
# Native Select All includes endpoint controls as well as their driven spans.
# Every part must move exactly once, including the pipe omitted above.
bpy.ops.object.select_all(action='SELECT')
layer.update()
tracked = {o.name: o.matrix_world.translation.copy() for o in before}
bpy.context.preferences.edit.use_global_undo = True
bpy.ops.ed.undo_push(message='Before translating ship')
assert bpy.ops.transform.translate(value=delta) == {'FINISHED'}
layer.update()


def check_all(offset):
    for name, position in tracked.items():
        near(bpy.data.objects[name].matrix_world.translation, position + offset, name)


check_all(delta)
bpy.ops.ed.undo_push(message='After translating ship')
assert bpy.ops.ed.undo() == {'FINISHED'}
bpy.context.view_layer.update()
check_all(Vector())
assert bpy.ops.ed.redo() == {'FINISHED'}
bpy.context.view_layer.update()
check_all(delta)
print('WHOLE SHIP CABLE MOVE PASS', bpy.app.version_string)
