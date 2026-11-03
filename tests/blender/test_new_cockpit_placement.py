"""New cockpits stay horizontal when the asset browser inherits a selection."""
import math
import sys
from pathlib import Path

import bpy

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_support import addon  # noqa: F401 - registers asset browser operators


def place(part_id):
    result = bpy.ops.object.nms_asset_browser_object_selected(object_id=part_id)
    assert result == {'FINISHED'}, (part_id, result)
    obj = bpy.context.view_layer.objects.active
    bpy.context.view_layer.update()
    assert obj.get('ObjectID') == part_id
    direction = obj.matrix_world.to_3x3().col[2].normalized()
    assert abs(direction.z) < .2, (part_id, tuple(direction))
    return obj


bpy.ops.object.select_all(action='DESELECT')
bpy.ops.mesh.primitive_cube_add(location=(3, 4, 5))
cube = bpy.context.object
cube.scale = (.5, .5, .5)
bpy.context.view_layer.update()
for part_id in ('B_COK_C1', 'B_COK_E'):
    bpy.ops.object.select_all(action='DESELECT')
    cube.select_set(True)
    bpy.context.view_layer.objects.active = cube
    obj = place(part_id)
    assert all(abs(obj.location[i] - cube.location[i]) < 1e-5 for i in range(3))
    assert all(abs(obj.scale[i] - cube.scale[i]) < 1e-5 for i in range(3))

bpy.ops.object.select_all(action='DESELECT')
bpy.context.view_layer.objects.active = None
obj = place('B_COK_C2')
assert abs(obj.rotation_euler.x - math.pi / 2) < 1e-4
print('NEW_COCKPIT_PLACEMENT_OK', flush=True)
