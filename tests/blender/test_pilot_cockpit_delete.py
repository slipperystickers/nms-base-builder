"""Pilot placement among slime props and ownership across real delete operators."""
from pathlib import Path
import sys
import time

import bpy
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_support import module

# Installed extensions defer preview updates briefly after Blender loads a file.
guard = module('undo_guard')
deadline = time.monotonic() + 5
while not guard.history_ready() and time.monotonic() < deadline:
    time.sleep(.05)
assert guard.history_ready()

pilot = module('pilot_reference')
pose = module('pilot_pose')
scene = bpy.context.scene
scene.bbe_detailed_proxies = False


def part(part_id, offset, order=0):
    obj = bpy.data.objects.new(part_id, None)
    scene.collection.objects.link(obj)
    obj['ObjectID'] = part_id
    obj['order'] = order
    obj.location.x = offset
    return obj


def select(obj):
    bpy.ops.object.select_all(action='DESELECT')
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    bpy.context.view_layer.update()


def choose(cockpit):
    select(cockpit)
    assert bpy.ops.bbe.choose_pilot_reference(race='ASTRO_DEFAULT') == {'FINISHED'}
    return pilot.preview(bpy.context)


def erase(cockpit, delete, also_model=False):
    model = pilot.references(scene, cockpit)[0]
    collection = model.users_collection[0].name
    anchor, name, mesh = model.parent.name, model.name, model.data.name
    private = bool(model.data.get(pose.PRIVATE))
    select(cockpit)
    if also_model:
        model.select_set(True)
    else:
        model.hide_set(True)
    bpy.context.view_layer.update()
    pose._dirty = False
    assert delete() == {'FINISHED'}
    bpy.context.view_layer.update()
    assert pose._dirty, 'Cockpit deletion did not schedule a refresh'
    time.sleep(.25)
    pose.tick()
    assert scene.objects.get(name) is None and bpy.data.objects.get(anchor) is None
    assert bpy.data.collections.get(collection) is None
    if private and not also_model:
        assert bpy.data.meshes.get(mesh) is None


cockpit = part('B_COK_D', 0)
other = part('B_COK_D', 50, 1)
model = choose(cockpit)
hands = model['bbe_pilot_hand_positions']
corrections = list(model['bbe_pilot_foot_corrections'])
props = [part('BASE_SLIMEP_05', 10 + i) for i in range(286)]
for i, obj in enumerate(props[:6], 1):
    obj['ObjectID'] = f'BASE_SLIMEP_{i:02}'
assert choose(cockpit) == model
assert model['bbe_pilot_hand_positions'] == hands
assert np.allclose(model['bbe_pilot_foot_corrections'], corrections)
assert model.data.get(pose.PRIVATE)

# If a slime capsule can actually touch the pilot, keep the seated reference
# but do not claim a calibrated hand pose until the obstruction moves away.
slime = props[4]
position = slime.location.copy()
slime.location = (0, 0, 0)
slime.scale = (40,) * 3
assert choose(cockpit) == model and 'bbe_pilot_hand_positions' not in model
assert 'feet' in model[pose.WARNING]
slime.location = position
slime.scale = (1,) * 3
assert choose(cockpit) == model and model['bbe_pilot_hand_positions'] == hands

# Unknown geometry must yield a usable baseline and one mention per distinct ID.
for obj in props[:4]:
    obj['ObjectID'] = 'QA_UNKNOWN'
assert choose(cockpit) == model and pilot.preview(bpy.context) == model
assert model[pose.WARNING].count('QA_UNKNOWN') == 1
assert 'bbe_pilot_hand_positions' not in model
for obj in props[:4]:
    obj['ObjectID'] = 'BASE_SLIMEP_05'
assert choose(cockpit) == model and model['bbe_pilot_hand_positions'] == hands

# A linked scene retains its cockpit and pilot if only the first scene unlinks it.
linked_scene = bpy.data.scenes.new('Cockpit still present here')
linked_scene.collection.objects.link(cockpit)
pilot_collection = model.users_collection[0]
linked_scene.collection.children.link(pilot_collection)
scene.collection.objects.unlink(cockpit)
pose.update_scene(scene)
assert model.name not in scene.objects and model.name in linked_scene.objects
assert model[pilot.TARGET] == cockpit
scene.collection.objects.link(cockpit)
scene.collection.children.link(pilot_collection)
bpy.data.scenes.remove(linked_scene)

# Deleting another cockpit must preserve the owner and its pilot.
select(other)
assert bpy.ops.object.delete(use_global=False) == {'FINISHED'}
bpy.context.view_layer.update()
pose.update_scene(scene)
assert pilot.references(scene, cockpit) == [model]
other = part('B_COK_D', 50, 1)
erase(cockpit, lambda: bpy.ops.object.delete(use_global=False))
assert other.name in scene.objects and not pilot.references(scene, other)
choose(other)
erase(other, bpy.ops.object.nms_delete)
assert all(obj.name in scene.objects for obj in props)
cockpit = part('B_COK_D', 0)
choose(cockpit)
erase(cockpit, lambda: bpy.ops.object.delete(use_global=False), also_model=True)

# In background Blender, push the snapshots which the UI normally creates.
# Redo may restore the post-delete state from before the deferred cleanup ran.
cockpit = part('B_COK_D', 0)
pilot_name = choose(cockpit).name
owner_name = cockpit.name
assert bpy.ops.ed.undo_push(message='Before cockpit delete') == {'FINISHED'}
assert bpy.ops.object.delete(use_global=False) == {'FINISHED'}
assert bpy.ops.ed.undo_push(message='Deleted cockpit') == {'FINISHED'}
pose.update_scene(scene)
assert pilot_name not in scene.objects
assert bpy.ops.ed.undo() == {'FINISHED'}
scene = bpy.context.scene
pose.update_scene(scene)
assert scene.objects[pilot_name][pilot.TARGET] == scene.objects[owner_name]
assert bpy.ops.ed.redo() == {'FINISHED'}
scene = bpy.context.scene
pose.update_scene(scene)
assert owner_name not in scene.objects and pilot_name not in scene.objects
print('PASS: placement among 288 parts, unknown fallback, linked scenes, both delete operators, undo and redo')
