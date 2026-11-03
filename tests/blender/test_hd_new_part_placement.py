"""Asset-browser placement coverage and installing HD after a base fallback."""
import bpy,sys,json,os,math
from pathlib import Path
sys.path.insert(0,str(Path(__file__).parent))
from test_support import module,D,QA
W=QA
b=module('builder_v2');hd=module('hd_library');hp=module('habitat_preview')
root=hd.additions_root();assert root
for obj in list(bpy.context.scene.objects):bpy.data.objects.remove(obj,do_unlink=True)
scene=bpy.context.scene;scene.bbe_detailed_proxies=True
# Reproduce an HD-enabled scene opened before the additions pack is installed.
hd.additions_root=lambda:None
cock=b.add_part('B_COK_E').object
bpy.context.view_layer.update();hp.refresh(scene)
assert cock.data.get(b.MESH_TAG) is None and '_BASE_' in cock.data.name
before=cock.matrix_world.copy()
# Reproduce the wrongly labelled fallback from r22 as well.
cock.data.name='NMS_VANTAGE_HD_0_713'
hd.additions_root=lambda:root
hp.refresh(scene)
assert cock.data.get(b.MESH_TAG)=='B_COK_E' and len(cock.data.materials)>20
assert cock.matrix_world==before
assert hp.refresh(scene)==0
bpy.data.objects.remove(cock,do_unlink=True)
rows=json.loads((D/'resources/forsaken_assets.json').read_text())['assets']
results=[]
for i,row in enumerate(rows):
 pid=row['id']
 bpy.ops.object.select_all(action='DESELECT');bpy.context.view_layer.objects.active=None
 status=bpy.ops.object.nms_asset_browser_object_selected(object_id=pid)
 obj=bpy.context.active_object
 assert status=={'FINISHED'} and obj and obj.get('ObjectID')==pid,(pid,status)
 mesh=obj.data
 images={node.image for mat in mesh.materials if mat and mat.node_tree for node in mat.node_tree.nodes if node.type=='TEX_IMAGE' and node.image}
 missing=[im.filepath for im in images if not im.packed_file and not Path(bpy.path.abspath(im.filepath)).is_file()]
 assert mesh.get(b.MESH_TAG)==pid,(pid,mesh.name,dict(mesh.items()))
 assert images and not missing,(pid,len(images),missing)
 assert len(mesh.polygons)>0 and mesh.uv_layers,(pid,'no mesh or UV')
 results.append(dict(id=pid,name=row.get('name'),polygons=len(mesh.polygons),materials=len(mesh.materials),textures=len(images),matrix=[list(r) for r in obj.matrix_world]))
 bpy.data.objects.remove(obj,do_unlink=True)
 if i%20==0:print('PLACEMENT_CHECK',i+1,len(rows),pid,flush=True)
(W/'catalog-placement-results.json').write_text(json.dumps(results,indent=2))
print('ACTUAL_ASSET_BROWSER_PLACEMENT_PASS',len(results),'VANTAGE_PACK_UPGRADE_PASS',flush=True)
