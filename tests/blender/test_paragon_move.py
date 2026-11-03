"""U_PARAGON remains visible and movable through import, proxy switches and export."""
import sys,json,math
from pathlib import Path
import bpy
from mathutils import Vector,Matrix
sys.path.insert(0,str(Path(__file__).parent))
from test_support import module,QA
b=module('builder').get_builder();v2=module('builder_v2');ops=module('tools_menu.base_builder_menu_operators')
report=[]
record=dict(ObjectID='^U_PARAGON',Position=[4,5,6],Up=[0,1,0],At=[0,0,1],UserData=0,Timestamp=123)
for detailed,importer in [(False,b.deserialise_from_data),(True,v2.deserialise_from_data)]:
 for obj in list(bpy.data.objects):bpy.data.objects.remove(obj,do_unlink=True)
 b.clear_caches();bpy.context.scene.bbe_detailed_proxies=detailed
 importer({'BaseVersion':8,'Objects':[record]});bpy.context.view_layer.update()
 o=next(o for o in bpy.context.scene.objects if o.get('ObjectID')=='U_PARAGON')
 assert o.users_collection and o.name.startswith('U_PARAGON')
 assert o.visible_get() and not o.hide_select and not any(o.lock_location),(detailed,o.hide_get(),list(o.lock_location))
 p=b.get_builder_object_from_bpy_object(o);start=p.serialise()
 bpy.ops.object.select_all(action='DESELECT');o.select_set(True);bpy.context.view_layer.objects.active=o
 delta=Vector((2.5,-3,1.25));bpy.ops.transform.translate(value=delta);bpy.context.view_layer.update()
 end=p.serialise();expected=Vector(start['Position'])+Matrix.Rotation(-math.pi/2,3,'X')@delta
 assert (Vector(end['Position'])-expected).length<1e-4,(end,expected)
 for key in ('ObjectID','Up','At','UserData','Timestamp'):assert end[key]==start[key],(key,end,start)
 for high in (not detailed,detailed):
  ops._switch_scene_proxies(bpy.context,high,show_progress=False);bpy.context.view_layer.update()
  assert o.visible_get() and not o.hide_select and not any(o.lock_location)
  p=b.get_builder_object_from_bpy_object(o);assert (Vector(p.serialise()['Position'])-expected).length<1e-4
 report.append({'mode':'HD' if detailed else 'base','collections':[c.name for c in o.users_collection],'name':o.name,'movable':True,'before':start['Position'],'after':end['Position'],'proxy_roundtrip_preserves_move':True})
(QA/'paragon-results.json').write_text(json.dumps(report,indent=2))
print('U_PARAGON_VISIBLE_MOVABLE_EXPORT_PASS',report,flush=True)
