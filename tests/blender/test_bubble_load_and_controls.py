"""Load repair, idle update, branch-angle and first-direction regressions."""
import math
import os
import sys
from pathlib import Path
import bpy
from mathutils import Matrix, Vector

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_support import addon, module, QA, report
pr = module('bubble_preview')
results = {}

def add(ident='BASE_BUBPIPE'):
    assert bpy.ops.object.nms_asset_browser_object_selected(object_id=ident) == {'FINISHED'}
    return bpy.context.view_layer.objects.active

def fresh():
    pr._restore_joint_rotation_guard()
    bpy.context.scene.nms_main.new_file()
    bpy.context.scene.bbe_detailed_proxies = False

def select(obj):
    bpy.ops.object.select_all(action='DESELECT')
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj

# Exercise the same browser buttons used by the tube card, in every direction.
for port in pr._ARMS:
    for ident in ('BASE_BUBPIPE', 'BASE_BUBPIPE_L'):
        fresh()
        first = add()
        before = first.matrix_world.copy()
        assert bpy.ops.bbe.bubble_start_direction(port=port) == {'FINISHED'}
        assert first.matrix_world == before
        second = add(ident)
        expected = before @ Vector((0, 1, 0)) + before.to_3x3() @ (2 * pr._ARMS[port])
        assert (second.matrix_world @ Vector((0, 1, 0)) - expected).length < 1e-4, (port, ident)
        assert pr._joined_sockets(second, first)[0] == port
        assert not pr.can_set_start_direction(bpy.context.scene, first)
        assert len(addon.BUILDER.serialise()['Objects']) == 2
results['starting_directions'] = 'all six directions, straight and elbow, browser placement and export'

# The unfinished elbow previously let 45 degrees through the issue-set check.
fresh()
target = add()
source = add('BASE_BUBPIPE_L')
before = source.matrix_world.copy()
for op in (bpy.ops.bbe.turn_bubble_elbow, bpy.ops.bbe.bubble_joint_pivot):
    assert op(angle=math.radians(45)) == {'CANCELLED'}
    assert source.matrix_world == before
assert bpy.ops.bbe.turn_bubble_elbow(angle=math.radians(5)) == {'FINISHED'}
after5 = source.matrix_world.copy()
assert bpy.ops.bbe.turn_bubble_elbow(angle=math.radians(5)) == {'CANCELLED'}
assert source.matrix_world == after5
source.matrix_world = before
bpy.context.view_layer.update()
assert bpy.ops.bbe.turn_bubble_elbow(angle=math.pi/2) == {'FINISHED'}
for degrees in (0, 5, 90, -90, 180):
    assert pr._joint_turn_error(Matrix.Rotation(math.radians(degrees),4,'Y'), Matrix.Identity(4)) is None
for degrees in (10, 45, -45):
    assert pr._joint_turn_error(Matrix.Rotation(math.radians(degrees),4,'Y'), Matrix.Identity(4))
results['turns'] = '45 rejected by both operators; cumulative 5+5 rejected; 5 and 90 accepted'

# Malformed legacy hints are repaired, meaningful draft intentions preserved.
fresh()
first = add()
first[pr._INTENT_KEY] = 'ELBOW:NoSuchPort'
first['bbe_native_snap_target'] = 'deleted tube'
first['bbe_native_target_socket'] = 'Top'
before = first.matrix_world.copy()
r = pr.inspect_loaded_tubes(bpy.context.scene)
assert r['repaired'] == 2, r
assert first[pr._INTENT_KEY] == 'STRAIGHT:Y'
assert 'bbe_native_snap_target' not in first
assert first.matrix_world == before
assert pr.inspect_loaded_tubes(bpy.context.scene)['repaired'] == 0
source = add('BASE_BUBPIPE_L')
intent = source[pr._INTENT_KEY]
assert pr.inspect_loaded_tubes(bpy.context.scene)['problems']
assert source[pr._INTENT_KEY] == intent
assert bpy.ops.bbe.repair_bubble_tubes() == {'FINISHED'}
results['repair'] = 'malformed hint and deleted neighbor repaired; draft preserved; idempotent'

# A saved starting direction survives a load and controls the next placement.
fresh()
first = add()
assert bpy.ops.bbe.bubble_start_direction(port='Left') == {'FINISHED'}
bpy.ops.wm.save_as_mainfile(filepath=str(QA/'bubble-start-roundtrip.blend'))
bpy.ops.wm.open_mainfile(filepath=str(QA/'bubble-start-roundtrip.blend'))
first = bpy.context.view_layer.objects.active
assert first[pr._START_KEY] == 'Left'
second = add()
assert pr._joined_sockets(second, first)[0] == 'Left'
results['direction_roundtrip'] = True

fixture = os.environ.get('BBE_GIZMO_FILE')
if fixture:
    bpy.ops.wm.open_mainfile(filepath=fixture)
    snapshot = {o.name: o.matrix_world.copy() for o in bpy.context.scene.objects}
    r = pr.inspect_loaded_tubes(bpy.context.scene)
    assert r['tubes'] > 0
    assert all(bpy.context.scene.objects[n].matrix_world == m for n,m in snapshot.items())
    results['fixture'] = dict(tubes=r['tubes'], problems=len(r['problems']), transforms_preserved=True)

bpy.ops.mesh.primitive_cube_add(location=(100,100,100))
cube = bpy.context.view_layer.objects.active
pr.refresh(bpy.context.scene)
bpy.context.view_layer.update()
updates = []
def observe(scene, dg):
    updates.append(len(dg.updates))
bpy.app.handlers.depsgraph_update_post.append(observe)
for _ in range(5):
    updates.clear()
    assert pr.refresh(bpy.context.scene) == 0
    bpy.context.view_layer.update()
    assert not updates, updates
    assert bpy.context.view_layer.objects.active == cube and cube.select_get()
bpy.app.handlers.depsgraph_update_post.remove(observe)
results['idle'] = 'five refreshes, zero dependency-graph updates, selection preserved'
report('bubble_load_controls_pass', dict(version=bpy.app.version_string, addon_path=addon.__file__, **results))
