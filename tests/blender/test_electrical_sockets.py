"""Exercise every native electrical device through target selection and export."""
import json, math, sys, time
from pathlib import Path
import bpy
from mathutils import Matrix, Vector
sys.path.insert(0,str(Path(__file__).resolve().parent))
from test_support import addon, module, report
c=module('cable_connections'); t=module('cable_targets')
builder=addon.BUILDER
scene=bpy.context.scene
scene.bbe_detailed_proxies=False
for o in list(scene.objects): bpy.data.objects.remove(o,do_unlink=True)
builder.clear_caches()
def near(a,b): assert (Vector(a)-Vector(b)).length<3e-4,(a,b)
def select(obj):
    for o in bpy.context.selected_objects:o.select_set(False)
    obj.select_set(True);bpy.context.view_layer.objects.active=obj
def new(pid,pos):
    obj=builder.add_part(pid,build_rigs=False).object
    obj.location=pos
    return obj

expected={'U_SOLAR_S':4,'U_BATTERY_S':4,'U_BIOGENERATOR':2,'U_GENERATOR_S':4,
          'U_SWITCHPROX':2,'U_SWITCHPRESS':2,'U_SWITCHBUTTON':2,'U_TRANSISTOR1':3,
          'MAINROOM':4,'MAINROOMCUBE':4,'CONTAINER7':4,'CEILINGLIGHT':1,
          'PLANTERMEGA':4,'BUILDLIGHT2':1,'U_EXTRACTOR_S':3,'BUILDDOOR':4}
for pid,count in expected.items():assert len(c._power_points(pid))==count,(pid,count)
for pid in ('W_WALL','C_WALL','U_SILO_S','U_MINIPORTAL_CV'):
    assert not c._power_points(pid),pid
# A directly authored solar connector position, independent of the old rounded table.
assert min((v-Vector((-.675974,.144766,0))).length for v in c._power_points('U_SOLAR_S').values())<.001

source=new('U_BATTERY_S',(-30,0,0)); sourcekey=next(iter(c.local_sockets(source,c.POWER)))
parts={pid:rows for pid,rows in c._native_power_points().items() if rows}
devices=[]; created=[]
for i,pid in enumerate(parts):
    obj=new(pid,((i%10)*15,(i//10)*15,0));devices.append(obj)
    obj.rotation_euler=(.25,.15,.7);obj.scale=(.7,1.2,.9)
    bpy.context.view_layer.update()
    select(obj)
    keys=c.local_sockets(obj,c.POWER)
    assert {r[1] for r in t.targets(bpy.context) if r[0]==obj.name and r[2]==c.POWER}==set(keys),pid
    for key in keys:
        # These are the same operators invoked by clicking the visible gizmos.
        assert bpy.ops.bbe.start_cable_connection(kind=c.POWER)=={'FINISHED'}
        assert bpy.ops.bbe.click_cable_target(owner=source.name,key=sourcekey,kind=c.POWER)=={'FINISHED'}
        assert bpy.ops.bbe.click_cable_target(owner=obj.name,key=key,kind=c.POWER)=={'FINISHED'}
        wire=bpy.context.active_object;created.append(wire)
        assert wire.get('ObjectID')==c.POWER and t.session(bpy.context) is None
        end=next(e for e in c.endpoints(wire) if c.control_owner(e)==obj)
        near(end.matrix_world.translation,c.sockets(obj,c.POWER)[key])

source.location.x-=2
bpy.context.view_layer.update()
for wire in created:
    start,end=c.endpoints(wire)
    near(wire.matrix_world.translation,start.matrix_world.translation)
    near(wire.matrix_world@Vector((0,0,1)),end.matrix_world.translation)
    payload=builder.get_builder_object_from_bpy_object(wire).serialise()
    rotate=Matrix.Rotation(math.pi/2,4,'X');at=Vector(payload['At'])
    near(rotate@Vector(payload['Position']),start.matrix_world.translation)
    near(rotate@(Vector(payload['Position'])+at-at.normalized()),end.matrix_world.translation)

# Target refresh operates on cached connector data, not mesh traversal.
bpy.ops.bbe.start_cable_connection(kind=c.POWER)
start=time.perf_counter()
for _ in range(10): choices=t.targets(bpy.context)
elapsed=(time.perf_counter()-start)/10
assert len(choices)==sum(map(len,parts.values()))+4
t.cancel(bpy.context)
assert len(created)==181 and len(devices)==76
report('electrical_sockets',dict(devices=len(devices),sockets=len(created),target_refresh_seconds=elapsed))
print('ELECTRICAL_SOCKETS_PASS',len(devices),len(created),elapsed,flush=True)
