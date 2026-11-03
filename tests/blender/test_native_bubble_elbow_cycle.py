"""Two fixed elbows snap by their visible ends and can close a four-elbow loop."""
import sys
from pathlib import Path

import bpy
from mathutils import Matrix, Vector

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_support import addon
from no_mans_sky_base_builder import bubble_preview as ducts


def elbow():
    obj = addon.BUILDER.add_part('BASE_BUBPIPE').object
    obj['bbe_bubble_shape'] = 'ELBOW:Bot+Front'
    return obj


def world_center(obj):
    return obj.matrix_world @ Vector((0, 1, 0))


target = elbow()
source = elbow()
source.matrix_world = Matrix.Translation((5, 0, 0))
bpy.ops.object.select_all(action='DESELECT')
source.select_set(True)
target.select_set(True)
bpy.context.view_layer.objects.active = target
assert bpy.ops.object.nms_snap() == {'FINISHED'}
first = source.matrix_world.copy()
assert len(ducts._snapped([source, target])[source.name]) == 1
assert bpy.ops.object.nms_snap(next_source=True) == {'FINISHED'}
assert (world_center(source) - (first @ Vector((0, 1, 0)))).length < 1e-5
assert source.matrix_world != first, 'Source Next must turn the elbow in place'
assert len(ducts._snapped([source, target])[source.name]) == 1
assert bpy.ops.object.nms_snap(prev_source=True) == {'FINISHED'}
assert all(abs(source.matrix_world[i][j] - first[i][j]) < 1e-5
           for i in range(4) for j in range(4))
assert bpy.ops.object.nms_snap(next_target=True) == {'FINISHED'}
assert (world_center(source) - (first @ Vector((0, 1, 0)))).length > 1
assert len(ducts._snapped([source, target])[source.name]) == 1

# Build a loop using the same snap/cycle path as the Builder buttons.
bpy.data.objects.remove(source, do_unlink=True)
bpy.data.objects.remove(target, do_unlink=True)
directions = (
    ((0, 0, 0), ('Right', 'Front')),
    ((2, 0, 0), ('Left', 'Front')),
    ((2, 0, 2), ('Left', 'Back')),
    ((0, 0, 2), ('Right', 'Back')),
)
def outward_names(obj):
    transform = obj.matrix_world.to_3x3()
    return {min(ducts._ARMS, key=lambda name:
                (transform @ ducts._ARMS[local] - ducts._ARMS[name]).length)
            for local in ('Bot', 'Front')}


loop = [elbow()]
first_rotation = next(rotation for rotation in ducts._ROTATIONS
                      if (rotation.to_3x3() @ ducts._ARMS['Bot'] - ducts._ARMS['Right']).length < 1e-5
                      and (rotation.to_3x3() @ ducts._ARMS['Front'] - ducts._ARMS['Front']).length < 1e-5)
loop[0].matrix_world = Matrix.Translation(-(first_rotation.to_3x3() @ Vector((0, 1, 0)))) @ first_rotation
for position, wanted in directions[1:]:
    obj = elbow()
    obj.matrix_world = Matrix.Translation(position)
    assert ducts.snap_native(obj, loop[-1])
    assert (world_center(obj) - Vector(position)).length < 1e-5
    for _ in range(8):
        if outward_names(obj) == set(wanted):
            break
        assert ducts.snap_native(obj, loop[-1], next_source=True)
    else:
        raise AssertionError(f'Source Next never produced {wanted}')
    loop.append(obj)
bpy.context.view_layer.update()
snapped = ducts._snapped(loop)
assert all(snapped[obj.name] == {'Bot', 'Front'} for obj in loop), snapped
ducts.validate_game_shapes(bpy.context.scene)
assert len(addon.BUILDER.serialise()['Objects']) == 4
print('NATIVE_BUBBLE_ELBOW_CYCLE_PASS', bpy.app.version_string, flush=True)
