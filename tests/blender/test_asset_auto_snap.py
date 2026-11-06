"""Browser Auto-Snap preference persists and OFF preserves the exact target pose."""
from pathlib import Path
import sys,bpy
from mathutils import Matrix
sys.path.insert(0,str(Path(__file__).parent))
from test_support import module,report
b=module('builder_v2');snaps=module('snap_markers');prefs=module('utils.asset_browser_utils')
for obj in tuple(bpy.data.objects):bpy.data.objects.remove(obj,do_unlink=True)
original=dict(prefs.read_store())
try:
 assert prefs.write_store(dict(original,auto_snap=False))
 prefs.clear_store_cache();assert not prefs.auto_snap_enabled()
 target=b.add_part('W_FLOOR').object
 target.matrix_world=Matrix.Translation((17,4,-2))@Matrix.Rotation(.7,4,'Z')@Matrix.Rotation(.3,4,'X')@Matrix.Diagonal((1.2,.8,1.7,1))
 bpy.context.view_layer.update();expected=target.matrix_world.copy()
 area=next(a for a in bpy.context.screen.areas if a.type=='VIEW_3D');region=next(r for r in area.regions if r.type=='WINDOW')
 with bpy.context.temp_override(area=area,region=region):
  for pid in ['W_FLOOR','B_MAG_1X1','BASE_BUBPIPE_L']:
   for o in bpy.context.selected_objects:o.select_set(False)
   target.select_set(True);bpy.context.view_layer.objects.active=target
   assert bpy.ops.object.nms_asset_browser_object_selected(object_id=pid)=={'FINISHED'}
   added=bpy.context.active_object
   assert added!=target and snaps.objects(bpy.context) is None
   assert max(abs(added.matrix_world[r][c]-expected[r][c]) for r in range(4) for c in range(4))<1e-6
  assert prefs.toggle_auto_snap();prefs.clear_store_cache();assert prefs.auto_snap_enabled()
  for o in bpy.context.selected_objects:o.select_set(False)
  target.select_set(True);bpy.context.view_layer.objects.active=target
  assert bpy.ops.object.nms_asset_browser_object_selected(object_id='W_FLOOR')=={'FINISHED'}
  assert snaps.objects(bpy.context)[1]==target
  assert prefs.read_store()['favourite_objects']==original['favourite_objects']
 report('asset_auto_snap',dict(exact_transform_when_off=True,green_targets_when_on=True,persistence=True))
finally:
 prefs.write_store(original)
