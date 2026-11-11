"""Power-door circuit topology, grid discovery, handoff and game export."""
from pathlib import Path
import sys
import bpy
from mathutils import Matrix

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_support import addon, module
c = module('cable_connections')
d = module('door_circuit')
targets = module('cable_targets')
v = module('builder_v2')
select = module('utils.blend_utils').select
ctx = bpy.context
builder = addon.BUILDER
ctx.scene.nms_main.new_file()

def part(pid, x):
    obj = v.add_part(pid, high_res=False, builder_object=builder).object
    obj.location.x = x
    ctx.view_layer.update()
    return obj

def wire(a, ka, b, kb):
    return c.connect(a, ka, b, kb, c.POWER, builder)

def run(door):
    select(door)
    return bpy.ops.bbe.add_door_proximity(owner=door.name)

def find_parts(door):
    links, _ = d.electrical_grid(ctx.scene)
    nodes = [(door, k) for k in c.local_sockets(door,c.POWER)]
    return d.installed_pair(nodes,links), links

def count(pid):
    return sum(o.get('ObjectID') == pid for o in ctx.scene.objects)

door = part('F_GDOOR',0)
door.matrix_world = Matrix.Translation((1,3,2)) @ Matrix.Rotation(.7,4,'Z') @ v.X_ROT_90 @ Matrix.Scale(.6,4)
battery = part('U_BATTERY_S',80)
lamp = part('BUILDLIGHT2',5)
unwired = part('BUILDLIGHT2',1)
powerkey = next(iter(c.local_sockets(lamp,c.POWER)))
key = next(iter(c.local_sockets(battery,c.POWER)))
wire(battery,key,lamp,powerkey)
# An ordinary wire junction can also carry power, including a remote branch.
control = c.junction(builder,c.POWER,(30,0,0))
ctx.view_layer.update()
wire(lamp,powerkey,control,'ENDPOINT')
assert run(door) == {'FINISHED'} and targets.session(ctx) is None
(inv,prox), links = find_parts(door)
assert (lamp,powerkey) in links[inv,d.FEED] and (unwired,powerkey) not in links[inv,d.FEED]
assert len(links[inv,d.FEED]) == 2 and (prox,d.FEED) in links[inv,d.FEED]
assert abs(inv.matrix_world.to_scale().x-.6) < 1e-5
assert run(door) == {'FINISHED'}
assert count(d.SENSOR) == count(d.INVERTER) == 1 and count(c.POWER) == 6
payload = builder.serialise()['Objects']
assert sum(r['ObjectID'] == '^U_POWERLINE' for r in payload) == 6

# Retrofit an existing direct supply cable, keeping the actual wire.
door2 = part('C_GDOOR',12)
old = wire(battery,key,door2,'POWER_B')
assert run(door2) == {'FINISHED'}
(inv2,prox2), links = find_parts(door2)
assert (inv2,d.FEED) in [c.socket_identity(e) for e in c.endpoints(old)]
assert all(c.control_owner(e) != door2 for e in c.endpoints(old))

# No source. Start with the inverter feed selected; leave isolated loads alone.
ctx.scene.nms_main.new_file()
door = part('B_GDOORT0',0)
lamp = part('BUILDLIGHT2',.5)
assert run(door) == {'FINISHED'}
(inv,prox),links = find_parts(door)
session = targets.session(ctx)
assert session['first'] == (inv,d.FEED)
choices = targets.targets(ctx)
assert {row[0] for row in choices} == {lamp.name}, choices
targets.cancel(ctx)
assert run(door) == {'FINISHED'} and count(d.INVERTER) == count(d.SENSOR) == 1
assert bpy.ops.bbe.click_cable_target(kind=c.POWER,owner=lamp.name,key=powerkey) == {'FINISHED'}
assert targets.session(ctx) is None and count(c.POWER) == 4

# A generator on a switch input cannot promote the switch output to a supply.
ctx.scene.nms_main.new_file()
door = part('T_GDOOR',0)
panel = part('U_SOLAR_S',60)
switch = part('U_TRANSISTOR2',25)
lamp = part('BUILDLIGHT2',1)
wire(panel, 'POWER_A',switch,'POWER_A')
wire(switch,'POWER_B',lamp,powerkey)
assert run(door) == {'FINISHED'}
(inv,prox),links = find_parts(door)
assert (switch,'POWER_A') in links[inv,d.FEED] and (lamp,powerkey) not in links[inv,d.FEED]
# Export and reimport rebuilds socket identities without private circuit tags.
payload = builder.serialise()
ctx.scene.nms_main.new_file()
v.deserialise_from_data(payload)
ctx.view_layer.update()
door = next(o for o in ctx.scene.objects if o.get('ObjectID') == 'T_GDOOR')
assert find_parts(door)[0]
assert run(door) == {'FINISHED'} and count(d.SENSOR) == count(d.INVERTER) == 1

for pid in ('U_GENERATOR_S', 'U_BIOGENERATOR'):
    ctx.scene.nms_main.new_file()
    source = part(pid, 50)
    loose = c.junction(builder,c.POWER,(5,1,0))
    ctx.view_layer.update()
    key = next(iter(c.local_sockets(source,c.POWER)))
    wire(source,key,loose,'ENDPOINT')
    door = part('S_GDOOR',0)
    assert run(door) == {'FINISHED'}
    (inv,prox), links = find_parts(door)
    assert (loose,'ENDPOINT') in links[inv,d.FEED]
print('PROXIMITY DOOR CIRCUITS PASS',bpy.app.version_string)
