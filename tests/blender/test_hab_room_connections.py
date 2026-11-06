"""Room connections open both native hab walls, preserve frames and export data."""
from pathlib import Path
import sys,time,bpy
from mathutils import Matrix
sys.path.insert(0,str(Path(__file__).parent))
from test_support import module,report,addon
b=module('builder_v2');h=module('hab_windows');s=module('corvette_snapping');d=module('hab_doorways')
for o in tuple(bpy.data.objects):bpy.data.objects.remove(o,do_unlink=True)
results=[]
for detailed in (False,True):
 bpy.context.scene.bbe_detailed_proxies=detailed
 for pid in h.table():
  hab=b.add_part(pid,high_res=detailed);other=b.add_part('B_HAB1_B',high_res=detailed)
  hab.matrix_world=Matrix.Translation((13,-7,5))@Matrix.Rotation(.6,4,'Z')@b.X_ROT_90@Matrix.Scale(.3,4)
  bpy.context.view_layer.update();closed=hab.object.data;other_closed=other.object.data
  covered=set()
  for choice in s.options(other.object,hab.object):
   other.matrix_world=choice[3];bpy.context.view_layer.update()
   connections=h.room_connections([hab.object,other.object],[hab.object,other.object]);slots=connections[hab.object]
   if not slots or slots<=covered:continue
   covered.update(slots);before=[p.serialise() for p in (hab,other)]
   h.refresh(force=True)
   for p in (hab,other):
    actual=set(p.object.data.get(h.DOORWAYS,'').split(','))
    assert actual==connections[p.object] and actual,(pid,actual,connections)
    removed=h.open_mesh(h.source_mesh(p.object),p.object_id,actual,detailed)
    expected=len(removed.polygons)+sum(len(d.doorway_mesh(p.object_id[-1],'NS' if x[4] in 'NS' else 'EW',detailed).polygons) for x in actual)
    assert len(p.object.data.polygons)==expected
   assert [p.serialise() for p in (hab,other)]==before
   pose=other.matrix_world.copy();other.object.location.x+=3;bpy.context.view_layer.update();h.refresh(force=True)
   assert hab.object.data==closed and other.object.data==other_closed
   other.matrix_world=pose@Matrix.Rotation(.15,4,'Y');bpy.context.view_layer.update();h.refresh(force=True)
   assert hab.object.data==closed,'Rotated near a socket must not open it'
   other.matrix_world=pose@Matrix.Scale(1.1,4);bpy.context.view_layer.update();h.refresh(force=True)
   assert hab.object.data==closed,'Wrong scale must not open it'
  assert covered==set(h.table()[pid]['slots']),(pid,detailed,covered)
  results.append(dict(hab=pid,detailed=detailed,slots=len(covered)))
  bpy.data.objects.remove(other.object,do_unlink=True);h.refresh(force=True);assert hab.object.data==closed
  bpy.data.objects.remove(hab.object,do_unlink=True)
# Cockpit-to-hab, including all three Vantage rear sockets from the reported scene.
for cid in ('B_COK_A','B_COK_E'):
 cockpit=b.add_part(cid);hab=b.add_part('B_HAB_B');bpy.context.view_layer.update()
 covered=set()
 for choice in s.options(hab.object,cockpit.object):
  key=int(choice[0].split(':')[0]);name=s.DATA[cid][key]['name']
  if not name.startswith('SnapPoint_N') or name in covered:continue
  s.apply(hab.object,cockpit.object,choice);bpy.context.view_layer.update()
  connections=h.room_connections([hab.object,cockpit.object],[hab.object])
  if not connections[hab.object]:continue
  saved=[p.serialise() for p in (cockpit,hab)];h.refresh(force=True)
  assert hab.object.data.get(h.DOORWAYS)
  if cid=='B_COK_E':
   hp=module('habitat_preview');mask=hp.opening_mask(cockpit.object,[hab.object])
   assert mask,choice
   hp.refresh(bpy.context.scene)
   assert cockpit.object.data.get('bbe_vantage_openings')==mask
  assert saved==[p.serialise() for p in (cockpit,hab)]
  covered.add(name)
 assert len(covered)==(3 if cid=='B_COK_E' else 1),(cid,covered)
 bpy.data.objects.remove(hab.object,do_unlink=True);bpy.data.objects.remove(cockpit.object,do_unlink=True)
report('hab_room_connections',dict(cases=results,total_slots=sum(r['slots'] for r in results),cockpit_sockets=4,detach_and_invalid_pose=True,exports_unchanged=True))
