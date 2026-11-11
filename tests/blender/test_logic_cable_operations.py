"""Exercise Logic menu operations on disposable Blender cable rigs."""
import sys
from pathlib import Path

import bpy
from mathutils import Vector

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_support import addon, module

c = module('cable_connections')
t = module('cable_targets')
ctx = bpy.context
builder = addon.BUILDER
ctx.scene.nms_main.new_file()


def select(*objs):
    for obj in ctx.selected_objects:
        obj.select_set(False)
    for obj in objs:
        obj.select_set(True)
    ctx.view_layer.objects.active = objs[-1]


def click(kind, **kwargs):
    assert bpy.ops.bbe.click_cable_target(kind=kind, **kwargs) == {'FINISHED'}


def lines(kind):
    return [o for o in ctx.scene.objects if o.get('ObjectID') == kind]


def device(x):
    obj = builder.add_part('U_MINIPORTAL', build_rigs=False).object
    obj.location.x = x
    ctx.view_layer.update()
    return obj


a, b, d, other = [device(x) for x in (0, 4, 8, 16)]
ctx.scene.nms_main.line_switch = 'TELEPORT'
assert not bpy.ops.object.nms_point.poll()
select(a, b)
assert bpy.ops.object.nms_connect() == {'FINISHED'}
ctx.scene.nms_main.line_switch = 'POWER'
select(a, b, d)
assert bpy.ops.object.nms_connect() == {'FINISHED'}
click(c.POWER, owner=d.name, key='POWER_A')
assert len(lines(c.POWER)) == 2
select(a, b, d)
assert bpy.ops.object.nms_connect() == {'FINISHED'}
click(c.POWER, owner=d.name, key='POWER_A')
assert len(lines(c.POWER)) == 2
select(other, d)
assert bpy.ops.object.nms_connect() == {'FINISHED'}
click(c.POWER, owner=d.name, key='POWER_A')
select(a, b, d)
removed_ends = [e.name for wire in lines(c.POWER) for e in c.endpoints(wire)
                if all(c.control_owner(point) in {a,b,d} for point in c.endpoints(wire))]
assert bpy.ops.object.nms_split() == {'FINISHED'}
assert len(lines(c.POWER)) == len(lines(c.TELEPORT)) == 1
assert all(ctx.scene.objects.get(name) is None for name in removed_ends)
assert {c.control_owner(end) for end in c.endpoints(lines(c.POWER)[0])} == {d, other}

for choice, kind in [('POWER', c.POWER), ('BYTEBEAT', c.BYTEBEAT)]:
    ctx.scene.nms_main.line_switch = choice
    assert bpy.ops.bbe.start_cable_connection(kind=kind) == {'FINISHED'}
    click(kind, free=True, position=(0,10,0))
    click(kind, free=True, position=(12,10,0))
    cable = ctx.active_object
    original_start, original_end = c.endpoints(cable)
    assert bpy.ops.object.nms_point() == {'FINISHED'}
    click(kind, span=cable.name, fraction=.25)
    joint = ctx.active_object
    assert (joint.matrix_world.translation - Vector((3,10,0))).length < .0001
    click(kind, free=True, position=(3,13,0))
    branch = ctx.active_object
    assert sum(joint in c.endpoints(w) for w in lines(kind)) == 3
    assert c.endpoints(cable) == (original_start, joint)
    assert any(c.endpoints(w) == (joint, original_end) for w in lines(kind))
    select(joint, c.endpoints(branch)[1])
    assert bpy.ops.object.nms_split() == {'FINISHED'}
    assert sum(joint in c.endpoints(w) for w in lines(kind)) == 2
    assert bpy.ops.object.nms_point() == {'FINISHED'}
    click(kind, free=True, position=(42,1,0))
    loose = ctx.active_object
    t.cancel(ctx)
    assert loose.get('bbe_junction') and c.control_owner(loose) is None
    select(cable)
    assert bpy.ops.object.nms_divide(starts=2) == {'FINISHED'}
    first = t.session(ctx)['first'][0]
    second, = t.session(ctx)['next_starts']
    assert abs(first.matrix_world.translation.x-1) < .0001
    assert abs(second.matrix_world.translation.x-2) < .0001
    click(kind, free=True, position=(1,14,0))
    assert t.session(ctx)['first'][0] == second
    click(kind, owner=loose.name, key='ENDPOINT')
    assert t.session(ctx) is None
    assert all(sum(pt in c.endpoints(w) for w in lines(kind)) == 3 for pt in (first, second))

# The chosen source starts the chain, regardless of selection order or active device.
ctx.scene.nms_main.new_file()
a, d, far, b = [device(x) for x in (0, 9, 20, 3)]
ctx.scene.nms_main.line_switch = 'POWER'
select(a, b, far, d)
assert bpy.ops.object.nms_connect(routing='CHAIN') == {'FINISHED'}
assert not lines(c.POWER)
click(c.POWER, owner=a.name, key='POWER_A')

def links(kind):
    return {frozenset(c.control_owner(end) for end in c.endpoints(w)) for w in lines(kind)}

assert links(c.POWER) == {frozenset(pair) for pair in ((a,b), (b,d), (d,far))}
select(b,d,far,a)
assert bpy.ops.object.nms_split() == {'FINISHED'}
assert bpy.ops.object.nms_connect(routing='FAN') == {'FINISHED'}
click(c.POWER, owner=a.name, key='POWER_A')
assert links(c.POWER) == {frozenset((a,obj)) for obj in (b,d,far)}

# An outside source automatically feeds the IN terminal of an intermediate switch.
ctx.scene.nms_main.new_file()
a, b = device(0), device(12)
middle = builder.add_part('U_TRANSISTOR1', build_rigs=False).object
middle.location.x = 6
ctx.view_layer.update()
select(middle, b)
ctx.scene.nms_main.line_switch = 'POWER'
assert bpy.ops.object.nms_connect(routing='CHAIN') == {'FINISHED'}
assert a.name in {r[0] for r in t.targets(ctx)}
click(c.POWER, owner=a.name, key='POWER_A')
assert t.session(ctx) is None
assert {tuple((c.control_owner(end),end['bbe_socket_key']) for end in c.endpoints(w))
        for w in lines(c.POWER)} == {((a,'POWER_A'),(middle,'POWER_A')),((middle,'POWER_A'),(b,'POWER_A'))}

select(lines(c.POWER)[0])
assert bpy.ops.object.nms_divide(starts=3, layout_mode='MIDPOINT') == {'FINISHED'}
shared = t.session(ctx)['first'][0]
assert t.session(ctx)['next_starts'] == [shared,shared]
for i in range(3):
    assert t.session(ctx)['first'][0] == shared
    click(c.POWER, free=True, position=(3,i,5))
assert sum(shared in c.endpoints(w) for w in lines(c.POWER)) == 5
assert t.session(ctx) is None

for kind in (c.POWER, c.BYTEBEAT, c.TELEPORT):
    assert bpy.ops.bbe.start_cable_connection(kind=kind, repeat_placement=True) == {'FINISHED'}
    for i in range(2):
        if kind == c.TELEPORT:
            portal = device(20+i*5)
            click(kind,owner=a.name,key='PORTAL_A')
            click(kind,owner=portal.name,key='PORTAL_A')
        else:
            click(kind,free=True,position=(12,i,3))
            click(kind,free=True,position=(15,i,3))
        assert t.session(ctx)['first'] is None
    t.cancel(ctx)

# Every logic device takes power at IN, even when the free source is closer
# to OUT or TRIGGER. Reuse one fan junction and retain existing links on error.
from types import SimpleNamespace
from unittest.mock import patch
ctx.scene.nms_main.new_file()
devices = []
for i, pid in enumerate(c.LOGIC_ROLES):
    obj = builder.add_part(pid, build_rigs=False).object
    obj.location.x = 3*i
    devices.append(obj)
    for socket, role in c.LOGIC_ROLES[pid].items():
        kind = c.BYTEBEAT if socket == 'BYTEBEAT_A' else c.POWER
        assert socket in c.local_sockets(obj,kind)
        props = SimpleNamespace(owner=obj.name, kind=kind, key=socket)
        assert t.BBE_OT_cable_target.description(ctx,props).startswith(role+' on ')
ctx.view_layer.update()
select(*devices)
ctx.scene.nms_main.line_switch = 'POWER'
assert bpy.ops.object.nms_connect(routing='FAN') == {'FINISHED'}
assert not lines(c.POWER)
click(c.POWER,free=True,position=(24,2,0))
ends = [c.endpoints(wire) for wire in lines(c.POWER)]
assert len({left for left,right in ends}) == 1
assert {(c.control_owner(right),right['bbe_socket_key']) for left,right in ends} == {(obj,c.POWER_IN) for obj in devices}

before = set(ctx.scene.objects)
real_connect = c.connect
def fail_second(*args, **kwargs):
    if len(lines(c.POWER)) > len(ends):
        raise RuntimeError('simulated allocation failure')
    return real_connect(*args, **kwargs)
with patch.object(c, 'connect', side_effect=fail_second):
    try:
        c.route_power(ctx,devices,None,'',Vector((-4,0,0)),builder,False)
    except RuntimeError as error:
        assert 'simulated allocation' in str(error)
    else:
        raise AssertionError('batch failure was not reported')
assert set(ctx.scene.objects) == before
# A real box selection also includes attached socket controls, including ones
# left behind by Blender's native Delete. These are aliases of their device.
ctx.scene.nms_main.new_file()
source, other = device(0), device(10)
button = builder.add_part('U_SWITCHBUTTON', build_rigs=False).object
button.location.x = 5
ctx.view_layer.update()
helpers = []
for obj in (source, button, button, other):
    helper = c.make_control(builder, 'old socket control', c.POWER)
    c.bind(helper, obj, 'POWER_A', c.POWER)
    helpers.append(helper)
ctx.view_layer.update()
free = c.junction(builder,c.POWER,(16,1,0))
ctx.view_layer.update()
select(source,other,button,*helpers,free)
ctx.scene.nms_main.line_switch = 'POWER'
assert bpy.ops.object.nms_connect(routing='CHAIN') == {'FINISHED'}
assert set(t.session(ctx)['devices']) == {source, other, button, free}
click(c.POWER,owner=source.name,key='POWER_A')
assert len(lines(c.POWER)) == 3 and t.session(ctx) is None
select(source,button,other,free,*helpers,*lines(c.POWER))
assert bpy.ops.object.nms_connect(routing='FAN') == {'FINISHED'}
click(c.POWER,owner=source.name,key='POWER_A')
assert t.session(ctx) is None
assert all(c.existing_connection(source,'POWER_A',o,k,c.POWER) is not None for o,k in
           ((button,'POWER_A'),(other,'POWER_A'),(free,'ENDPOINT')))
print('LOGIC CABLE OPERATIONS PASS', bpy.app.version_string)
