"""Build the six-part zero using browser placement and the Builder snap controls."""
import sys
from pathlib import Path
import bpy
from mathutils import Matrix, Vector

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_support import addon, module
ducts = module('bubble_preview')
bpy.context.scene.nms_main.new_file()
bpy.context.scene.bbe_detailed_proxies = False
assert bpy.ops.object.nms_asset_browser_object_selected(object_id='BASE_BUBPIPE_L') == {'FINISHED'}
first = bpy.context.active_object
# Rotate the first elbow as a builder would; subsequent placement is by Snap.
rotation = next(r for r in ducts._ROTATIONS
                if (r.to_3x3() @ ducts._ARMS['Bot'] - ducts._ARMS['Top']).length < 1e-5
                and (r.to_3x3() @ ducts._ARMS['Front'] - ducts._ARMS['Right']).length < 1e-5)
center = Vector((0, 1, 0))
first.matrix_world = rotation @ Matrix.Translation(-center)
parts = [first]
positions = ((0, 2, 0), (0, 4, 0), (2, 4, 0), (2, 2, 0), (2, 0, 0))
openings = ({'Top', 'Bot'}, {'Bot', 'Right'}, {'Bot', 'Left'}, {'Top', 'Bot'}, {'Top', 'Left'})

def arm_names(obj):
    return {max(ducts._ARMS, key=lambda n: (obj.matrix_world.to_3x3() @ ducts._ARMS[port]).normalized().dot(ducts._ARMS[n]))
            for port in ducts._visible_sockets(obj)}

for i, (position, wanted) in enumerate(zip(positions, openings), 1):
    target = parts[-1]
    bpy.ops.object.select_all(action='DESELECT')
    target.select_set(True)
    bpy.context.view_layer.objects.active = target
    ident = 'BASE_BUBPIPE' if i in (1, 4) else 'BASE_BUBPIPE_L'
    assert bpy.ops.object.nms_asset_browser_object_selected(object_id=ident) == {'FINISHED'}
    source = bpy.context.active_object
    assert source != target
    bpy.ops.object.select_all(action='DESELECT')
    source.select_set(True)
    target.select_set(True)
    bpy.context.view_layer.objects.active = target
    for _ in range(3):
        if (source.matrix_world @ center - Vector(position)).length < 1e-4:
            break
        assert bpy.ops.object.nms_snap(next_target=True) == {'FINISHED'}
    else:
        raise AssertionError('Target cycling missed ' + str(position))
    for _ in range(9):
        if arm_names(source) == wanted:
            break
        assert bpy.ops.object.nms_snap(next_source=True) == {'FINISHED'}
    else:
        raise AssertionError('Source cycling missed ' + str(wanted))
    parts.append(source)
    assert len([obj for obj in bpy.context.scene.objects if obj.get('ObjectID')]) == i + 1

assert all(len(v) == 2 for v in ducts._editor_contacts(parts).values())
assert sum(obj['bbe_bubble_shape'].startswith('ELBOW:') for obj in parts) == 4
before = [(obj.matrix_world.copy(), obj['bbe_bubble_shape']) for obj in parts]
payload = addon.BUILDER.serialise()['Objects']
# This editor test was constructed in Blender XY. Compare after the normal
# Blender-to-game -90 X conversion, the same rigid transform for every piece.
compensate = module('part').z_compensate.to_3x3()
# The common grid may be encoded using an equivalent axis permutation; check
# shape openings in world space as well as the native connection graph.
export = module('bubble_export')
nodes = {i: export.frame(p) for i,p in enumerate(payload)}
contacts, uncertain = export.native_contacts(nodes)
assert not uncertain and all(len(v) == 2 for v in contacts.values())
assert len(payload) == 6
for i, obj in enumerate(parts):
    c, r, scale = nodes[i]
    expected_center = compensate @ (obj.matrix_world @ center)
    assert (c - expected_center).length < 1e-5
    actual_arms = [r @ export.ARMS[port] for port in export.shape(contacts[i])]
    expected_arms = [compensate @ obj.matrix_world.to_3x3() @ ducts._ARMS[port] for port in ducts._visible_sockets(obj)]
    assert all(max(a.dot(b.normalized()) for a in actual_arms) > .9999 for b in expected_arms)
    assert obj.matrix_world == before[i][0] and obj['bbe_bubble_shape'] == before[i][1]
print('BUBBLE_LOOP_WORKFLOW_PASS', bpy.app.version_string, flush=True)
