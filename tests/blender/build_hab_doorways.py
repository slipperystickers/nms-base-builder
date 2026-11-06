"""Build native room doorway frames and authored hab locator transforms."""
from pathlib import Path
import ast,json,sys
R=Path(__file__).resolve().parents[2];sys.path.insert(0,str(R/'tests/blender'))
p=R/'tests/blender/build_magnetic_mounts.py';nodes=[]
for node in ast.parse(p.read_text()).body:
 if isinstance(node,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='out' for t in node.targets):break
 nodes.append(node)
env={'__file__':str(p),'__name__':'doorway_builder'}
exec(compile(ast.Module(body=nodes,type_ignores=[]),str(p),'exec'),env)
ns=env['ns'];bpy=ns['bpy'];out=R/'tests/.artifacts/hab-doorway-build'
for folder in ['assets','simple']:(out/folder).mkdir(parents=True,exist_ok=True)
ns['OUT']=out
for o in tuple(bpy.data.objects):bpy.data.objects.remove(o,do_unlink=True)
for style in 'ABCD':
 for axis in ['NS','EW']:
  name=axis+'_'+style;path='MODELS/COMMON/SPACECRAFT/BIGGS/MODULES/PARTS/DOORWAY_'+name+'.SCENE.MBIN'
  root=ns['scene'](path)
  ns['build'](dict(id=name,placementScene=path,components=[dict(scene=path,locator=root.Name,entity='')]))
  print('Built',name,flush=True)
meshes=set()
for style in 'ABCD':
 for axis in ['NS','EW']:
  name=axis+'_'+style
  for quality,folder in [('detailed','assets'),('simple','simple')]:
   with bpy.data.libraries.load(str(out/folder/(name+'.blend')),link=False) as (a,b):b.meshes=list(a.meshes)
   mesh=b.meshes[0];mesh.name='BBE Doorway '+name+' '+quality;meshes.add(mesh)
   mesh['bbe_doorway_asset']=name+' '+quality
D=R/'src/addons/no_mans_sky_base_builder/resources'
ns['module']('utils.materials_v2').dedupe_appended_data()
bpy.data.libraries.write(str(D/'hab_doorways.blend'),meshes,path_remap='NONE',fake_user=True,compress=True)
frames={}
for kind,file in [('hab','HAB_1X2_POSITIONLOCATORS'),('walkway','PARTS/HAB_1X1_POSITIONLOCATORS')]:
 root=ns['scene']('MODELS/COMMON/SPACECRAFT/BIGGS/MODULES/'+file+'.SCENE.MBIN')
 frames[kind]={n.Name:[list(row) for row in n.matrix_local] for n in root.iter() if n.Name.startswith('WALL')}
(D/'hab_doorway_frames.json').write_text(json.dumps(frames,indent=2))
