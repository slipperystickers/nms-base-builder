"""Regression: reorganize only changed parts and keep deleted appearances out of exports."""
import copy
import json
from pathlib import Path
import sys

import bpy

sys.path.insert(0, str(Path(__file__).parent))
from test_support import addon, module

update = module('build_update')
ctx = bpy.context
scene = ctx.scene
scene.nms_main.new_file()
scene.bbe_detailed_proxies = False
parts = []
for i in range(5):
    part = addon.BUILDER.add_part('L_FLOOR_Q', user_data=0)
    obj = part.object
    obj.location = (i * 2., 0, 0)
    obj['Timestamp'] = str(9000 + i)
    parts.append(obj)
ctx.view_layer.update()
organized = bpy.data.collections.new('Lounge')
scene.collection.children.link(organized)
for obj in parts:
    organized.objects.link(obj)
records = [addon.BUILDER.get_part_class(o['ObjectID']).read_record(o) for o in parts]
incoming = copy.deepcopy(records[:4])
incoming[1]['Position'][0] += 5
incoming[2]['UserData'] = 7
incoming[3]['Position'][0] += .0001
incoming.append(dict(records[0], Timestamp=10001, ObjectID='^BUILDFLATPANEL', Position=[3, 0, 5]))
data = dict(Objects=incoming)
names = [o.name for o in parts]
plan = update.make_plan(ctx, data)
assert (plan[2], len(plan[3]), len(plan[4]), len(plan[5]), plan[6]) == (2,2,1,1,set()), plan
update.apply(ctx, data, plan)
again = update.make_plan(ctx, data)
assert again[2:6] == (5, [], [], []), again
root = scene.collection.children[update.ROOT]
for label in (update.ADDED, update.MOVED, update.EDITED, update.DELETED):
    assert len(root.children[label].objects) == 1
assert all(o.name in organized.objects for o in parts[:4])
assert root.children[update.DELETED].hide_viewport
assert all('ObjectID' not in o for o in root.children[update.DELETED].objects)
assert names[-1] not in scene.objects
assert len(addon.BUILDER.serialise()['Objects']) == 5
print('BUILD UPDATE PASS', flush=True)
