"""Supply placement through the same click operators used by viewport targets."""
import sys
from pathlib import Path
import bpy
from mathutils import Vector, Matrix
sys.path.insert(0,str(Path(__file__).resolve().parent))
from test_support import addon,module
c=module('cable_connections');t=module('cable_targets');snap=module('snap_markers')
ctx=bpy.context;builder=addon.BUILDER
ctx.scene.nms_main.new_file()
objs=[]
for i,pid in enumerate(('U_EXTRACTOR_S','U_GASEXTRACTOR','U_SILO_S')):
    obj=builder.add_part(pid,build_rigs=False).object;obj.location.x=i*5;objs.append(obj)
ctx.view_layer.update()
for obj,n in zip(objs,(1,1,4)):
    supply=c.sockets(obj,c.SUPPLY);power=c.sockets(obj,c.POWER)
    assert len(supply)==n
    assert not any((s-p).length<.01 for s in supply.values() for p in power.values())
assert not c.sockets(objs[-1],c.POWER)
a,b=objs[0],objs[-1]
b.rotation_euler=(.2,.3,.4);b.scale=(1.2,1.2,1.2);ctx.view_layer.update()
assert bpy.ops.bbe.start_cable_connection(kind=c.SUPPLY,repeat_placement=True)=={'FINISHED'}
for obj,key in ((a,'SUPPLY_1'),(b,'SUPPLY_4')):
    assert bpy.ops.bbe.click_cable_target(kind=c.SUPPLY,owner=obj.name,key=key)=={'FINISHED'}
wire=next(o for o in ctx.scene.objects if o.get('ObjectID')==c.SUPPLY)
assert t.session(ctx) and t.session(ctx)['first'] is None
assert any(col.get('bbe_cable_kind')==c.SUPPLY for col in wire.users_collection)
b.location.x+=3;ctx.view_layer.update()
start,end=c.endpoints(wire)
assert (end.matrix_world.translation-c.sockets(b,c.SUPPLY)['SUPPLY_4']).length<1e-4
record=builder.get_builder_object_from_bpy_object(wire).serialise();assert record['ObjectID']=='^U_PIPELINE'
for pt in ((0,3,0),(4,3,0)):
    assert bpy.ops.bbe.click_cable_target(kind=c.SUPPLY,free=True,position=pt)=={'FINISHED'}
assert len([o for o in ctx.scene.objects if o.get('ObjectID')==c.SUPPLY])==2
t.cancel(ctx)
ctx.scene.bbe_show_connectors=False
assert t.targets(ctx)==[] and not t.BBE_GGT_cable_targets.poll(ctx) and not snap.BBE_GGT_snap_targets.poll(ctx)
ctx.scene.bbe_show_connectors=True
print('PASS BBE supply ports (1/1/4), typed isolation, transformed bindings, collections, free placement, repeat placement, export, hidden targets',flush=True)

# Regression: a shared junction has multiple outgoing cables. Its old text
# backlink identifies only one, so all live references must be rebound.
w1=c.connect(None,'',None,'',c.POWER,builder,free_start=Vector((20,0,0)),free_end=Vector((25,0,0)))
w2=c.connect(None,'',None,'',c.POWER,builder,free_start=Vector((20,0,0)),free_end=Vector((20,5,0)))
w3=c.connect(None,'',None,'',c.POWER,builder,free_start=Vector((20,0,0)),free_end=Vector((20,10,0)))
duplicate,end=c.endpoints(w2)
builder.get_builder_object_from_bpy_object(w3).build_rig(duplicate,c.endpoints(w3)[1])
ctx.view_layer.update()
expected={w:tuple(p.matrix_world.translation.copy() for p in c.endpoints(w)) for w in (w1,w2,w3)}
builder.optimise_control_points();ctx.view_layer.update()
assert len({c.endpoints(w)[0] for w in expected})==1
for wire,positions in expected.items():
    assert all(c.endpoints(wire))
    assert all((p.matrix_world.translation-v).length<1e-4 for p,v in zip(c.endpoints(wire),positions))
controls_before={o for o in ctx.scene.objects if o.get('rig_item')}
ends_before={w:c.endpoints(w) for w in expected}
builder.build_rigs();ctx.view_layer.update()
assert controls_before=={o for o in ctx.scene.objects if o.get('rig_item')}
assert ends_before=={w:c.endpoints(w) for w in expected}
builder.deserialise_from_data({'Objects':[{'ObjectID':'^W_FLOOR','Position':[40,0,0],'Up':[0,1,0],'At':[0,0,1],'UserData':0}]})
ctx.view_layer.update()
for wire,positions in expected.items():
    assert all((p.matrix_world.translation-v).length<1e-4 for p,v in zip(c.endpoints(wire),positions))
print('PASS shared-junction merge keeps every cable; build/paste preserve existing rigs',flush=True)
