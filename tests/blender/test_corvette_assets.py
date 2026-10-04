"""Corvette weapons retain textured geometry; hab details remain in the shell."""
from pathlib import Path
import sys,json,math,os
sys.path.insert(0,str(Path(__file__).resolve().parent));from test_support import *
from mathutils import Matrix
v2=module('builder_v2');mats=module('utils.materials_v2');select=module('utils.blend_utils').select
Part=module('part').Part;TURRET=module('part_overrides.turret').TURRET
bpy.context.scene.nms_main.new_file();rows=[]
weapons=[]
for index,id in enumerate('B_TUR_'+c for c in 'ABCDEF'):
 part=v2.add_part(id,user_data=0x14000001);obj=part.object
 assert mats.is_high_res(obj),(id,'fell back to an untextured proxy')
 if id!='B_TUR_F':assert isinstance(part,TURRET)
 assert len(obj.data.materials)>0 and any(n.type=='TEX_IMAGE' for m in obj.data.materials if m.use_nodes for n in m.node_tree.nodes)
 for mat in obj.data.materials:
  if mat.use_nodes:
   for n in mat.node_tree.nodes:
    if n.type=='TEX_IMAGE' and n.image:
     path=Path(bpy.path.abspath(n.image.filepath,library=n.image.library))
     assert path.is_file(),(id,'missing texture',str(path))
 obj.location.x=index*9;weapons.append(obj)
 rows.append({'id':id,'vertices':len(obj.data.vertices),'textured':True,'highRes':True})
# Every weapon gets coloured, and mesh swaps preserve identity and placement.
select(weapons);assert bpy.ops.object.nms_apply_colour(colour_index=37)=={'FINISHED'}
old={o['ObjectID']:(o.matrix_world.copy(),int(o['UserData'])) for o in weapons}
assert bpy.ops.object.nms_switch_proxies_to_low()=={'FINISHED'}
assert all(not mats.is_high_res(o) for o in weapons)
assert bpy.ops.object.nms_switch_proxies_to_high()=={'FINISHED'}
for obj in weapons:
 id=obj['ObjectID'];matrix,user=old[id]
 assert mats.is_high_res(obj) and int(obj['UserData'])==user,(id,mats.is_high_res(obj),obj['UserData'],user)
 assert max(abs(obj.matrix_world[r][c]-matrix[r][c]) for r in range(4) for c in range(4))<1e-6
# Actual Objects import uses the same HD path, with packed colour untouched.
data={'Objects':[{'ObjectID':'^'+id,'UserData':user,'Position':[i*9,0,0],'Up':[0,1,0],'At':[0,0,1]} for i,(id,(matrix,user)) in enumerate(old.items())]}
bpy.context.scene.nms_main.new_file();v2.deserialise_from_data(data)
assert len([o for o in bpy.context.scene.objects if 'ObjectID' in o])==6
for obj in bpy.context.scene.objects:
 if 'ObjectID' in obj:assert mats.is_high_res(obj) and int(obj['UserData'])==old[obj['ObjectID']][1]
# Simulate faulty caches carried by an older saved scene. Reloading the file
# must retain the user's old objects while new placements/quality switches
# resolve the revised assets instead of reusing those embedded meshes.
legacy=[]
for id in v2.MESH_REVISIONS:
 mesh=bpy.data.meshes.new(v2.MESH_PREFIX+id);mesh.from_pydata([(0,0,0),(12,0,0),(0,0,12)],[],[(0,1,2)])
 mesh[v2.MESH_TAG]=id;obj=bpy.data.objects.new(id,mesh);bpy.context.collection.objects.link(obj)
 obj['ObjectID']=id;obj['UserData']=0x14000001;obj.location.x=len(legacy)*9;legacy.append(obj)
saved=QA/'tmp/corvette_legacy_cache.blend';bpy.ops.wm.save_as_mainfile(filepath=str(saved));bpy.ops.wm.open_mainfile(filepath=str(saved))
legacy=[o for o in bpy.context.scene.objects if o.get('ObjectID') in v2.MESH_REVISIONS]
assert len(legacy)==7
for id in ['B_HAB_A','B_HAB_B','B_HAB_C','B_HAB1_A','B_HAB1_B','B_HAB1_C','B_ALK_C','B_ALK_Z_C']:
 mesh=v2.load_high_res_mesh(id);assert mesh is not None
 bb=[[min(v.co[a] for v in mesh.vertices) for a in range(3)],[max(v.co[a] for v in mesh.vertices) for a in range(3)]]
 assert max(abs(bb[0][0]),abs(bb[1][0]))<3.4,(id,'floating side details',bb)
 assert max(abs(bb[0][2]),abs(bb[1][2]))<(6.7 if id.startswith('B_HAB_') else 3.7),(id,'floating end details',bb)
 assert bb[0][1]>-.5 and bb[1][1]<3.4,(id,bb)
 assert len(mesh.polygons)>1000 and mesh.uv_layers
 if id in v2.MESH_REVISIONS:
  assert mesh.get(v2.MESH_REVISION_TAG)==v2.MESH_REVISIONS[id]
  assert v2.load_high_res_mesh(id)==mesh
 rows.append({'id':id,'bounds':bb,'shellDetailsAligned':True,'vertices':len(mesh.vertices)})
assert all(len(o.data.vertices)==3 for o in legacy),'Loading revised assets changed saved objects without a quality switch'
before={o.name:(o['ObjectID'],int(o['UserData']),o.matrix_world.copy()) for o in legacy}
select(legacy);assert bpy.ops.object.nms_switch_proxies_to_low()=={'FINISHED'}
assert bpy.ops.object.nms_switch_proxies_to_high()=={'FINISHED'}
for obj in legacy:
 id,user,matrix=before[obj.name]
 assert obj['ObjectID']==id and int(obj['UserData'])==user and len(obj.data.vertices)>1000
 assert obj.data.get(v2.MESH_REVISION_TAG)=='18.0.9'
 assert max(abs(obj.matrix_world[r][c]-matrix[r][c]) for r in range(4) for c in range(4))<1e-6
# Both Blender and the Qt browser resolve the new physical thumbnail.
icon=D/'images/asset_icons/B_TUR_F.png';img=bpy.data.images.load(str(icon),check_existing=False)
assert tuple(img.size)==(256,256)
pixels=list(img.pixels);assert sum(pixels[3::4])>1000 and all(pixels[i]==0 for i in [3,256*4-1,-1,-256*4+3])
assert 'B_TUR_F' in module('icons').get_asset_icons_pcoll()
os.environ['QT_QPA_PLATFORM']='offscreen'
qt=module('asset_browser.utils.qt');app=qt.QtWidgets.QApplication.instance() or qt.QtWidgets.QApplication([])
Thumb=module('asset_browser.item').Thumb;thumb=Thumb('B_TUR_F');assert thumb.pixmap() is not None and not thumb.pixmap().isNull()
thumb.deleteLater()
report('corvette_asset_verification',{'checks':rows,'colourAndProxySwitchPreserveRecords':True,'importedWeaponsHighRes':True,'bothAssetBrowserIconsValid':True,'olderSavedMeshCachesRefresh':True})
