import bpy,sys,os,json,math
from pathlib import Path
from mathutils import Matrix,Vector
OUT=Path(__file__).resolve().parents[1]/'.artifacts'
R=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(R/'tests/blender'))
from test_support import module,addon
b=module('builder_v2');hd=module('hd_library');pivot=module('utils.mirror_pivot');ui=module('hd_library_ui')
def clear():
 bpy.data.batch_remove(list(bpy.data.objects));bpy.data.batch_remove(list(bpy.data.meshes));addon.BUILDER.clear_caches()
def add(pid,quality=True):
 bpy.ops.object.select_all(action='DESELECT');bpy.context.view_layer.objects.active=None
 bpy.context.scene.bbe_detailed_proxies=quality
 o=b.add_part(pid).object;bpy.context.view_layer.update();return o
def err(a,c):return max(abs(a[i][j]-c[i][j]) for i in range(4) for j in range(4))
clear();results={}
for quality in (False,True):
 for pid in ('B_WNG_S','B_WNG_S_R','B_GEN_4','B_GEN_5','B_TUR_F'):
  o=add(pid,quality);native=pivot.native_matrix(o.matrix_world,pid,normalized=pivot.is_normalized(o))
  assert err(native,Matrix.Rotation(1.5708,4,'X'))<1e-5,(pid,quality,list(o.rotation_euler))
  points=[o.matrix_world@v.co for v in o.data.vertices]
  dimensions=[max(p[i] for p in points)-min(p[i] for p in points) for i in range(3)]
  if pid.startswith('B_WNG_S'): assert dimensions[1]>2*dimensions[2],(pid,dimensions)
  for axis in 'XYZ':
   original=o.matrix_world.copy();original_id=o['ObjectID']
   for turn in range(2):
    bpy.ops.object.select_all(action='DESELECT');o.select_set(True);bpy.context.view_layer.objects.active=o
    bpy.context.scene.nms_build_tool.mirror(axis=axis,center=Vector((0,0,0)),objects_to_mirror=[o])
    bpy.context.view_layer.update()
   assert err(o.matrix_world,original)<1e-5,(pid,quality,axis)
   assert o['ObjectID']==original_id
  results[pid+str(quality)]=dict(dimensions=list(o.dimensions),rotation=list(o.rotation_euler))
root=hd.additions_root
clear();hd.additions_root=lambda **kw:None;b.get_asset_index(rebuild=True)
for pid in ('B_GEN_4','B_GEN_5','B_TUR_F'):
 assert pid not in b.get_asset_index()
 o=add(pid);assert o.data.get(b.MESH_TAG) is None,pid
# Old .43 cached wrong HD mesh must not defeat either fallback or later update.
pid='B_GEN_5';mesh=bpy.data.meshes.new(b.MESH_PREFIX+pid);mesh[b.MESH_TAG]=pid;mesh[b.MESH_REVISION_TAG]=b.MESH_REVISIONS[pid]
assert b.load_high_res_mesh(pid) is None
hd.additions_root=root;b.get_asset_index(rebuild=True)
correct=b.load_high_res_mesh(pid);assert correct is not mesh and len(correct.vertices)==214992
assert correct.get(b.MESH_SOURCE_TAG)
# Download control must auto-start an existing install's missing content.
originals={name:getattr(hd,name) for name in ('ready','available','start')}
calls=[];hd.ready=lambda:False;hd.available=lambda:True;hd.start=lambda archive=None:calls.append(archive) or True
if bpy.app.online_access:
 result=bpy.ops.bbe.hd_library('INVOKE_DEFAULT');assert result=={'FINISHED'} and calls==[None]
 ui.cancel_activation()
for name,value in originals.items():setattr(hd,name,value)
(OUT/'fix-validation.json').write_text(json.dumps(results,indent=2))
print('FIX_VALIDATION_PASS',len(results),'placements; X/Y/Z mirrors twice; missing-HD fallback; stale cache; update control',flush=True)
