"""Typed SRT endpoints, transformed devices, export round trips and target UI."""
import json
import math
import sys
from pathlib import Path
import bpy
from mathutils import Matrix, Vector
sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_support import addon, module, report

c = module('cable_connections')
t = module('cable_targets')
builder = addon.BUILDER
for obj in list(bpy.context.scene.objects):
    bpy.data.objects.remove(obj, do_unlink=True)
builder.clear_caches()

def near(a, b, eps=2e-4):
    assert (Vector(a)-Vector(b)).length < eps, (list(a), list(b))

def select(*objects):
    for o in bpy.context.selected_objects: o.select_set(False)
    for o in objects: o.select_set(True)
    bpy.context.view_layer.objects.active = objects[-1]

def new(pid, pos):
    part = builder.add_part(pid, build_rigs=False)
    part.object.location = pos
    bpy.context.view_layer.update()
    return part.object

a = new('U_MINIPORTAL', (-3,0,0))
b = new('U_MINIPORTAL', (3,0,0))
cv = new('U_MINIPORTAL_CV', (8,0,0))
assert len(c.local_sockets(a,c.POWER)) == len(c.local_sockets(a,c.TELEPORT)) == 1
assert not c.local_sockets(cv,c.POWER)
near(c.local_sockets(a,c.TELEPORT)['PORTAL_A'], (0,1.593752,-.889160))
near(c.local_sockets(a,c.POWER)['POWER_A'], (0,.606372,-1.495064))

# The game-native source must match independently of BBE's previous rounded table.
import xml.etree.ElementTree as ET
native = Path(r'C:\Users\kengo\OneDrive\Desktop\NMS\outputs\srt-connections-20261103\native')
for file in native.rglob('*miniportal.scene.MXML'):
    root = ET.parse(file).getroot()
    node = next(n for n in root.iter('Property') if n.find("Property[@name='Name'][@value='PortalSocket_Out_']") is not None)
    tr = node.find("Property[@name='Transform']")
    near([float(tr.find(f"Property[@name='Trans{x}']").get('value')) for x in 'XYZ'], (0,1.593752,-.889160), 1e-6)

select(a,b)
for stored, expected in enumerate(('POWER','TELEPORT','BYTEBEAT','PIPE')):
    bpy.context.scene.nms_main['line_switch']=stored
    assert bpy.context.scene.nms_main.line_switch == expected
bpy.context.scene.nms_main.line_switch = 'AUTO'
assert addon.get_line_type_from_enum(bpy.context) == c.TELEPORT
assert bpy.ops.object.nms_connect() == {'FINISHED'}
tele = next(o for o in bpy.context.scene.objects if o.get('ObjectID') == c.TELEPORT)
assert not any(o.get('ObjectID') == c.POWER for o in bpy.context.scene.objects)
power = c.connect(a,'POWER_A',b,'POWER_A',c.POWER,builder)
assert c.connect(a,'POWER_A',b,'POWER_A',c.POWER,builder) == power
assert tele.color[:] != power.color[:]
assert max(abs(v.co.x) for v in tele.data.vertices) > max(abs(v.co.x) for v in power.data.vertices)
assert tele.users_collection[0].name.startswith('Teleport Connections')
assert power.users_collection[0].name.startswith('Electrical Connections')
for cable, key, kind in ((tele,'PORTAL_A',c.TELEPORT),(power,'POWER_A',c.POWER)):
    start,end = c.endpoints(cable)
    owners = [c.control_owner(start),c.control_owner(end)]
    assert set(owners) == {a,b}
    for ctrl,owner in zip((start,end),owners):
        near(ctrl.matrix_world.translation,c.sockets(owner,kind)[key])
    near(cable.matrix_world.translation,start.matrix_world.translation)
    near(cable.matrix_world @ Vector((0,0,1)),end.matrix_world.translation)

# Follow device movement, rotated non-unit scale and a transformed parent.
parent = bpy.data.objects.new('Test transform parent',None)
bpy.context.scene.collection.objects.link(parent)
parent.location = (4,-3,2)
parent.rotation_euler.z = .4
a.parent = parent
a.rotation_euler = (1.1,.3,-.6)
a.scale = (.3,.3,.3)
b.scale = (2,2,2)
b.location = (-1,4,2)
a.name = 'Renamed teleporter'
bpy.context.view_layer.update()
for cable,kind in ((tele,c.TELEPORT),(power,c.POWER)):
    for ctrl in c.endpoints(cable):
        owner = c.control_owner(ctrl)
        key = ctrl['bbe_socket_key']
        near(ctrl.matrix_world.translation,c.sockets(owner,kind)[key])
    start,end=c.endpoints(cable)
    near(cable.matrix_world.translation,start.matrix_world.translation)
    near(cable.matrix_world @ Vector((0,0,1)),end.matrix_world.translation)
    payload=builder.get_builder_object_from_bpy_object(cable).serialise()
    rotate=Matrix.Rotation(math.pi/2,4,'X')
    position=rotate@Vector(payload['Position'])
    at=Vector(payload['At'])
    finish=rotate@(Vector(payload['Position'])+at-at.normalized())
    near(position,start.matrix_world.translation)
    near(finish,end.matrix_world.translation)

# Correct targets persist for either selected device or cable, not the whole scene.
select(tele)
assert len(t.targets(bpy.context)) == 2
select(a)
assert len(t.targets(bpy.context)) == 4
assert all(row[0] != cv.name for row in t.targets(bpy.context))
assert bpy.ops.bbe.start_cable_connection(kind=c.TELEPORT) == {'FINISHED'}
assert len(t.targets(bpy.context)) == 3
assert bpy.ops.bbe.click_cable_target(owner=b.name,key='PORTAL_A',kind=c.TELEPORT) == {'FINISHED'}
assert bpy.ops.bbe.click_cable_target(owner=cv.name,key='PORTAL_A',kind=c.TELEPORT) == {'FINISHED'}
assert t.session(bpy.context) is None
assert len(t.targets(bpy.context)) == 2
assert bpy.context.active_object.get('ObjectID') == c.TELEPORT
assert bpy.ops.bbe.start_cable_connection(kind=c.POWER) == {'FINISHED'}
assert {row[0] for row in t.targets(bpy.context)} == {a.name,b.name}
t.cancel(bpy.context)

# Incorrect socket requests cannot create orphan objects or cross wire types.
before=len(bpy.data.objects)
try: c.connect(a,'POWER_A',b,'PORTAL_A',c.TELEPORT,builder)
except ValueError: pass
else: raise AssertionError('mixed sockets accepted')
assert len(bpy.data.objects)==before

# Collection visibility hides both cable and network markers.
select(tele)
tele.hide_set(True)
assert not t.targets(bpy.context)
tele.hide_set(False)

# Old nearest-power misattachment is repaired only by explicit request.
end=c.endpoints(tele)[0]
owner=c.control_owner(end)
for axis in range(3): end.driver_remove('location',axis)
end.location=c.sockets(owner,c.POWER)['POWER_A']
end['snapped_to']=owner.name
select(tele)
bpy.context.view_layer.update()
fixed,ambiguous=c.repair_srt(bpy.context)
assert fixed==2 and not ambiguous
near(end.matrix_world.translation,c.sockets(owner,c.TELEPORT)['PORTAL_A'])

payload=builder.serialise()
assert all(row['ObjectID'] != '^POWER_CONTROL' for row in payload['Objects'])
assert sum(row['ObjectID'] == '^U_PORTALLINE' for row in payload['Objects']) == 2
assert sum(row['ObjectID'] == '^U_POWERLINE' for row in payload['Objects']) == 1
out=Path(r'C:\Users\kengo\OneDrive\Desktop\NMS\outputs\srt-connections-20261103')
(out/'connection-export.json').write_text(json.dumps(payload,indent=2))
bpy.ops.wm.save_as_mainfile(filepath=str(out/'SRT-connection-test.blend'))

# Import the exported game objects through the shipping V2 importer. Endpoint
# offsets and cable visibility must survive, with no helper objects exported.
before_rows=[row for row in payload['Objects'] if row['ObjectID'] in {'^'+c.POWER,'^'+c.TELEPORT}]
for obj in list(bpy.context.scene.objects): bpy.data.objects.remove(obj,do_unlink=True)
builder.clear_caches()
module('builder_v2').deserialise_from_data(payload)
bpy.context.view_layer.update()
after_payload=builder.serialise()
after_rows=[row for row in after_payload['Objects'] if row['ObjectID'] in {'^'+c.POWER,'^'+c.TELEPORT}]
assert len(after_rows)==len(before_rows)
for old in before_rows:
    candidates=[r for r in after_rows if r['ObjectID']==old['ObjectID']]
    matched=min(candidates,key=lambda row:(Vector(row['Position'])-Vector(old['Position'])).length + (Vector(row['At'])-Vector(old['At'])).length)
    near(matched['Position'],old['Position'])
    near(matched['At'],old['At'])
for cable in bpy.context.scene.objects:
    if cable.get('ObjectID') not in c.KINDS: continue
    assert not cable.hide_get() and cable.data.get('bbe_hd') is None
    for control in c.endpoints(cable):
        assert control.get('bbe_socket_key'), (cable.name,control.name)
        assert c.control_owner(control) is not None

# Different cable types at an identical free endpoint cannot be merged.
loose=[]
for kind in c.KINDS:
    part=builder.add_part(kind,build_rigs=False)
    s=c.make_control(builder,'shared location',kind)
    e=c.make_control(builder,'other location',kind)
    s.location=(20,0,0);e.location=(22,0,0)
    part.build_rig(s,e)
    loose.append(part.object)
builder.optimise_control_points()
assert set(c.endpoints(loose[0])).isdisjoint(c.endpoints(loose[1]))

# Auto-connect does not inject an electrical cable into Corvette teleporters.
cv1=new('U_MINIPORTAL_CV',(30,0,0)); cv2=new('U_MINIPORTAL_CV',(34,0,0))
select(cv1,cv2)
old_power=sum(o.get('ObjectID')==c.POWER for o in bpy.context.scene.objects)
bpy.context.scene.nms_main.line_switch='AUTO'
assert bpy.ops.object.nms_connect()=={'FINISHED'}
assert sum(o.get('ObjectID')==c.POWER for o in bpy.context.scene.objects)==old_power

# Legacy point/Snap Next uses cable type, never the nearest incompatible socket.
test_line=next(o for o in bpy.context.scene.objects if o.get('ObjectID')==c.TELEPORT)
control=c.endpoints(test_line)[0]
wrapper=builder.get_builder_object_from_bpy_object(control)
destination=builder.get_builder_object_from_bpy_object(cv1)
assert wrapper.snap_to(destination,next_target=True)
bpy.context.view_layer.update()
near(control.matrix_world.translation,c.sockets(cv1,c.TELEPORT)['PORTAL_A'])
report('srt_connections',dict(status='passed',exported=len(payload['Objects']),types=[c.POWER,c.TELEPORT]))
print('SRT_CONNECTIONS_PASS',flush=True)
