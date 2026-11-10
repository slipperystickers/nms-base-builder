"""Magnetic wall variants and reversible native hab openings in both proxy modes."""
from pathlib import Path
import sys,bpy
from mathutils import Matrix
sys.path.insert(0,str(Path(__file__).parent))
from test_support import module,report,QA
b=module('builder_v2');h=module('hab_windows');s=module('corvette_snapping');m=module('magnetic_mounts');pc=module('part_controls')
for o in tuple(bpy.data.objects):bpy.data.objects.remove(o,do_unlink=True)
results=[]
for detailed in (False,True):
 bpy.context.scene.bbe_detailed_proxies=detailed
 for pid in h.table():
  hab=b.add_part(pid,high_res=detailed);hab.matrix_world=Matrix.Translation((17,2,-4))@Matrix.Rotation(.7,4,'Z')@b.X_ROT_90@Matrix.Scale(.3,4)
  bpy.context.view_layer.update();closed=hab.object.data;hab_saved=hab.serialise()
  for aid in sorted(h.MAGNETS):
   part=b.add_part(aid,high_res=detailed);obj=part.object;free=obj.data;covered=set();cases=0
   for choice in s.options(obj,hab.object):
    obj.matrix_world=choice[3];bpy.context.view_layer.update()
    slots=h.matching_slots(obj,hab.object)
    if not slots or slots.issubset(covered):continue
    saved=part.serialise();covered.update(slots);h.refresh(force=True)
    assert slots.issubset(set(hab.object.data.get(h.OPEN,'').split(','))),(pid,aid,slots)
    assert obj.data.get(m.MOUNT),(pid,aid,choice[:2])
    assert hab.serialise()==hab_saved and part.serialise()==saved
    if aid=='B_MAG_1X1':
     variant,frame=m.mounting_frame(obj,hab.object,slots)
     assert obj.data['bbe_magnetic_variant']==variant
     assert len(obj.data.polygons)>100
     assert obj.data[m.REVISION_KEY]==m.REVISION
     # Simulate a project containing the previous mounted mesh and named
     # variant. Refresh must load the new asset even when the old name exists.
     if not results and cases==0:
      previous=obj.data
      previous[m.MOUNT]='legacy:'+previous[m.MOUNT]
      previous[m.REVISION_KEY]=1
      cached=m.variant_mesh(variant,detailed);cached[m.REVISION_KEY]=1
      h.refresh(force=True)
      assert obj.data!=previous and obj.data[m.REVISION_KEY]==m.REVISION
      current=m.variant_mesh(variant,detailed)
      assert current!=cached and current[m.REVISION_KEY]==m.REVISION
      assert m.variant_mesh(variant,detailed)==current
      assert part.serialise()==saved
    pc.update_beam(obj)
    if detailed:
     obj.bbe_show_magnetic_beam=True;bpy.context.view_layer.update();full=len(obj.evaluated_get(bpy.context.evaluated_depsgraph_get()).data.polygons)
     obj.bbe_show_magnetic_beam=False;bpy.context.view_layer.update();hidden=len(obj.evaluated_get(bpy.context.evaluated_depsgraph_get()).data.polygons)
     assert hidden<full,(aid,full,hidden)
    obj.location.x+=8;bpy.context.view_layer.update();h.refresh(force=True)
    assert hab.object.data==closed and obj.data==free
    cases+=1
   if aid=='B_MAG_1X1':
    assert set(h.deck_slots()[pid]['detailed']) <= covered
    # Exterior Block placements at the same wall keep the loose projector.
    for choice in s.options(obj,hab.object):
     if s.DATA[pid][int(choice[0].split(':')[0])]['name']!='SnapPoint_E1':continue
     obj.matrix_world=choice[3];bpy.context.view_layer.update()
     if not h.matching_slots(obj,hab.object):break
    else:raise AssertionError('No exterior placement found')
    h.refresh(force=True)
    assert obj.data==free and hab.object.data==closed
   assert covered,(pid,aid,detailed)
   results.append(dict(hab=pid,part=aid,detailed=detailed,slots=len(covered),poses=cases))
   bpy.data.objects.remove(obj,do_unlink=True);h.refresh(force=True);assert hab.object.data==closed
  bpy.data.objects.remove(hab.object,do_unlink=True)
report('magnetic_hab_mounts',dict(cases=results,export_unchanged=True,detach_restores=True,beam_toggle=True))
