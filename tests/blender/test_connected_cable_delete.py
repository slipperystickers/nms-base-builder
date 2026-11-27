"""Exercise bulk deletion on live BBE rigs, including points shared by several spans."""
from pathlib import Path
import sys

import bpy

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_support import addon, module

cables = module('cable_connections')
deletion = module('cable_delete')
ctx = bpy.context
builder = addon.BUILDER


def device(pid, x):
    obj = builder.add_part(pid, build_rigs=False).object
    obj.location.x = x
    ctx.view_layer.update()
    return obj


def select(*objects):
    for obj in ctx.selected_objects:
        obj.select_set(False)
    for obj in objects:
        obj.select_set(True)
    ctx.view_layer.objects.active = objects[0]


for clean in (False, True):
    ctx.scene.nms_main.new_file()
    targets, snapped, removed, kept = [], [], set(), set()
    pairs = []
    supply = next(iter(cables._supply_points()))
    for number, (pid, kind) in enumerate((('L_FLOOR_Q', cables.POWER), (supply, cables.SUPPLY),
                                          ('U_MINIPORTAL', cables.TELEPORT), ('BYTEBEAT', cables.BYTEBEAT))):
        left, right = device(pid, number*20), device(pid, number*20+8)
        key = next(iter(cables.local_sockets(left, kind)))
        wire = cables.connect(left, key, right, key, kind, builder)
        a, b = cables.endpoints(wire)
        targets.append(left)
        snapped.append(wire)
        removed.update(obj.name for obj in (a,b,wire))
        kept.add(right.name)
        pairs.append((wire, a, b, right, a.matrix_world.translation.copy()))
    # Two selected tiles share one cable. One endpoint also serves a surviving span.
    first, second = device('L_FLOOR_Q', 91), device('L_FLOOR_Q', 98)
    key = next(iter(cables.local_sockets(first, cables.POWER)))
    bridge = cables.connect(first, key, second, key, cables.POWER, builder)
    targets.extend((first, second))
    snapped.append(bridge)
    removed.update(obj.name for obj in (bridge,*cables.endpoints(bridge)))
    junction = cables.junction(builder, cables.POWER, (108,0,2))
    ctx.view_layer.update()
    branch = cables.connect(first,key,junction,'ENDPOINT',cables.POWER,builder)
    survivor = cables.connect(junction,'ENDPOINT',None,'',cables.POWER,builder,free_end=(115,0,2))
    junction['power_line'] = branch.name
    snapped.append(branch)
    removed.update((branch.name,cables.endpoints(branch)[0].name))
    kept.update(obj.name for obj in (survivor,*cables.endpoints(survivor)))
    # An old name-only snap is still a connection. A free end at the same position is not.
    old = cables.connect(None,'',None,'',cables.POWER,builder,free_start=(91,0,0),free_end=(92,1,0))
    cables.endpoints(old)[0]['snapped_to'] = first.name
    snapped.append(old)
    removed.update(obj.name for obj in (old,*cables.endpoints(old)))
    free = cables.connect(None,'',None,'',cables.POWER,builder,free_start=(91,0,0),free_end=(92,1,0))
    kept.update(obj.name for obj in (free,*cables.endpoints(free)))
    # The connector on older builds can itself be driven by a second control.
    hub = cables.make_control(builder,'floor socket adapter',cables.POWER)
    cables.bind(hub,first,key,cables.POWER)
    indirect = cables.connect(None,'',None,'',cables.POWER,builder,free_start=(91,2,0),free_end=(92,4,0))
    cables.bind(cables.endpoints(indirect)[0],hub,'ENDPOINT',cables.POWER)
    snapped.append(indirect)
    removed.update(obj.name for obj in (hub,indirect,*cables.endpoints(indirect)))
    old.hide_set(True)
    orphan = cables.make_control(builder,'unused tile socket',cables.POWER)
    cables.bind(orphan,first,key,cables.POWER)
    orphan_name = orphan.name
    targets[0].name = 'renamed lighted floor'
    target_names = {o.name for o in targets}
    select(*targets)
    plan = deletion.make_plan(ctx,'BUILDER')
    assert plan.attached == set(snapped)
    assert bpy.ops.object.nms_delete(remove_cabling=clean) == {'FINISHED'}
    ctx.view_layer.update()
    remaining = set(ctx.scene.objects.keys())
    assert not remaining & target_names and orphan_name not in remaining
    assert kept <= remaining
    if clean:
        assert not remaining & removed, remaining & removed
        assert junction['power_line'] == survivor.name
        for kind in (cables.SUPPLY,cables.TELEPORT,cables.BYTEBEAT):
            assert cables.COLLECTIONS[kind] not in ctx.scene.collection.children
        assert cables.COLLECTIONS[cables.POWER] in ctx.scene.collection.children
        # Removing the final span removes the previously shared junction too.
        last_run = {obj.name for obj in (survivor,*cables.endpoints(survivor))}
        select(survivor)
        assert bpy.ops.object.nms_delete() == {'FINISHED'}
        assert not last_run.intersection(ctx.scene.objects.keys())
    else:
        assert removed <= remaining
        for wire, end, opposite, other, before in pairs:
            assert cables.free_control(end) and 'snapped_to' not in end
            assert (end.matrix_world.translation-before).length < .0001
            assert cables.attached_device(opposite) == other
            assert cables.endpoints(wire) == (end,opposite)
print('CONNECTED CABLE DELETE PASS', flush=True)
