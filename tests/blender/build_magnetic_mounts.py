"""Build magnetic wall and deck variants from authored NMS scenes; no replacement geometry."""
from pathlib import Path
import ast,sys,os
R=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(R/'tests/blender'))
# Reuse the native geometry/normal/material decoder without running its catalog batch.
p=R/'tests/blender/build_forsaken_assets.py'
tree=ast.parse(p.read_text());nodes=[]
for node in tree.body:
 if isinstance(node,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='manifest_path' for t in node.targets):break
 nodes.append(node)
ns={'__file__':str(p),'__name__':'mag_native_builder'}
exec(compile(ast.Module(body=nodes,type_ignores=[]),str(p),'exec'),ns)
bpy=ns['bpy'];Matrix=ns['Matrix'];texture_root=ns['OUT']/'textures'
from mathutils import Euler
original_matrix=ns['component_matrix']
def magnetic_matrix(node,path):
 # The four lid copies yaw around the ring AFTER tilting about their own
 # hinge. XYZ incorrectly tilts every copy about the same world axis.
 if ns['norm'](path).endswith('/parts/mag_1x1.scene.mbin'):
  t=node.Transform
  return Matrix.Translation(t['Trans'])@Euler(t['Rot'],'ZYX').to_matrix().to_4x4()@Matrix.Diagonal((*t['Scale'],1))
 return original_matrix(node,path)
ns['component_matrix']=magnetic_matrix
from functools import lru_cache
@lru_cache(None)
def image(name,data):
 # Reuse the installed pack's existing texture quality and artwork.
 packed_name=Path(name.split('_',1)[1]).with_suffix('.webp').name.upper()
 library=ns['module']('hd_library').library_root()/'textures'
 textures={p.name.upper():p for p in library.iterdir() if p.is_file()}
 im=bpy.data.images.load(str(textures.get(packed_name,texture_root/name)),check_existing=False)
 im.colorspace_settings.name='Non-Color' if data else 'sRGB';im.pack()
 return im
ns['image']=image
out=R/'tests/.artifacts/magnetic-native-build';out.mkdir(exist_ok=True)
for folder in ['assets','simple']:(out/folder).mkdir(exist_ok=True)
ns['OUT']=out
for obj in list(bpy.data.objects):bpy.data.objects.remove(obj,do_unlink=True)
variants=os.environ.get('BBE_MAG_VARIANTS', 'NS,EW,TB').split(',')
for variant in variants:
 scene='MODELS/COMMON/SPACECRAFT/BIGGS/MODULES/PARTS/MAG_1X1_'+variant+'.SCENE.MBIN'
 root=ns['scene'](scene)
 result=ns['build'](dict(id='MAG_'+variant,placementScene=scene,components=[dict(scene=scene,locator=root.Name,entity='')]))
 print(result['id'],result['polygons'])
# Write mesh-only, texture-packed variants for both quality modes.
dest=R/'src/addons/no_mans_sky_base_builder/resources/magnetic_mounts';dest.mkdir(exist_ok=True)
for variant in variants:
 for quality,folder in [('detailed','assets'),('simple','simple')]:
  with bpy.data.libraries.load(str(out/folder/('MAG_'+variant+'.blend')),link=False) as (a,b):b.meshes=list(a.meshes)
  mesh=b.meshes[0];mesh.name='BBE Magnetic '+variant+' '+quality
  mesh['bbe_magnetic_variant']=variant;mesh['bbe_magnetic_quality']=quality
  mesh['bbe_magnetic_revision']=2
  folder = dest if quality == 'simple' else dest.parent / 'hd_additions/magnetic_mounts'
  folder.mkdir(exist_ok=True)
  bpy.data.libraries.write(str(folder/(variant+'_'+quality+'.blend')),{mesh},path_remap='NONE',fake_user=True,compress=True)
