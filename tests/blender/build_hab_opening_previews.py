from pathlib import Path
import sys,json,re
from functools import lru_cache
R=Path(r'C:\Users\kengo\OneDrive\Documents\GitHub\nms-base-builder')
sys.path.insert(0,str(R/'tests/blender'));from test_support import module
D=R/'src/addons/no_mans_sky_base_builder'
WORK=Path(r'C:\Users\kengo\OneDrive\Desktop\NMS')
import numpy as np
import bpy,bmesh,math,os
import xml.etree.ElementTree as ET
from types import SimpleNamespace
from mathutils import Matrix,Vector
from mathutils.kdtree import KDTree
sys.path.insert(0,str(WORK/'fusion_nms_base_builder/.tools/NMSDK/src/addon'));sys.path.insert(0,str(WORK/'fusion_nms_base_builder/.tools/hgpaktool'))
from nmsdk.serialization.NMS_Structures import MBINHeader,TkSceneNodeData,TkGeometryData
from nmsdk.ModelImporter.SceneNodeData import SceneNodeData
SOURCE=WORK/'outputs/nms-update-20261028/native';PREFIX='MODELS/COMMON/SPACECRAFT/BIGGS/MODULES/';v=module('builder_v2')
def norm(s):return s.replace('\\','/').lower()
@lru_cache(None)
def scene(path):
    def val(e,name):return e.find(f"Property[@name='{name}']").get('value','')
    def node(e):
        return SimpleNamespace(Name=val(e,'Name'),Type=val(e,'Type'),
            Transform=SimpleNamespace(**{p.get('name'):float(p.get('value')) for p in e.find("Property[@name='Transform']")}),
            Attributes=[SimpleNamespace(Name=val(p,'Name'),Value=val(p,'Value')) for p in e.find("Property[@name='Attributes']")],
            Children=[node(p) for p in e.find("Property[@name='Children']")])
    return SceneNodeData(node(ET.parse((SOURCE/norm(path)).with_suffix('.MXML')).getroot()))
@lru_cache(maxsize=24)
def geometry(path):
    p=SOURCE/(norm(path)+'.pc')
    with p.open('rb') as f:MBINHeader.read(f);g=TkGeometryData.read(f)
    raw=p.with_name(p.name.replace('.geometry.','.geometry.data.')).read_bytes()
    return g,raw,{m.IdString.upper():m for m in g.StreamMetaDataArray}

def triangles(path,parent):
 root=scene(path);geo=root.attributes.get('GEOMETRY');out=[]
 levels={int(n.attributes.get('LODLEVEL','0')) for n in root.iter() if n.Type=='MESH'}
 level=max((l for l in levels if l<=2),default=0)
 def walk(node,parent):
  world=parent@node.matrix_local;a=node.attributes;name=node.Name
  lod=re.search(r'LOD(\d+)',name,re.I)
  if lod and int(lod.group(1))!=level:return
  if node.Type=='REFERENCE':out.extend(triangles(a['SCENEGRAPH'],world))
  if node.Type=='MESH' and 'MATERIAL' in a and int(a.get('LODLEVEL','0'))==level:
   if any(t in norm(a['MATERIAL']) for t in ['COLLISION','LIGHTBLOCK','TERRAINEDIT','WATERPROXY','EXCLUSIONVOLUME','SHADOWONLY']):return
   g,data,meta=geometry(geo);m=meta[name.upper()];layout=g.PositionVertexLayout;count=m.VertexPositionDataSize//layout.Stride;ve=next(x for x in layout.VertexElements if x.SemanticID==0);dt={5131:np.float16,5126:np.float32}[ve.Type]
   points=np.ndarray((count,ve.Size),dtype=dt,buffer=data,offset=m.VertexPositionDataOffset+ve.Offset,strides=(layout.Stride,np.dtype(dt).itemsize)).astype(np.float32)[:,:3];points=[world@Vector(p) for p in points]
   ic=int(a['BATCHCOUNT']);stride=m.IndexDataSize//ic;indices=np.frombuffer(data,dtype=np.uint16 if stride==2 else np.uint32,count=ic,offset=m.VertexDataOffset+m.IndexDataOffset)
   out.extend(tuple(points[i] for i in tri) for tri in indices.reshape(-1,3))
  for child in node.children:walk(child,world)
 walk(root,parent);return out

def key(points):return tuple(sorted(tuple(round(c,3) for c in p) for p in points))
def ranges(ids):
 out=[]
 for i in sorted(ids):
  if out and i==out[-1][1]+1:out[-1][1]=i
  else:out.append([i,i])
 return out

P=Path(os.environ.get('BBE_HAB_BUILD_DIR', str(WORK/'outputs/hab-opening-build')));out=P/'simple-habs';out.mkdir(parents=True,exist_ok=True)
rows=json.loads((D/'resources/hab_wall_slots.json').read_text())
native=json.loads((WORK/'outputs/nms-update-20261028/new-objects.json').read_text());templates={r['id']:r for r in native}
for pid,row in rows.items():
 template=templates['B_HAB_D' if pid.startswith('B_HAB_') else 'B_HAB1_D']
 locpath=PREFIX+('HAB_1X2_POSITIONLOCATORS.SCENE.MBIN' if pid.startswith('B_HAB_') else 'PARTS/HAB_1X1_POSITIONLOCATORS.SCENE.MBIN')
 locs={n.Name:n.matrix_local for n in scene(locpath).iter()}
 verts=[];faces=[];slots={}
 for c in template['components']:
  locator=c['locator'];path=c['scene'].replace('_D','_'+pid[-1])
  if locator.startswith('WALL'):path=row['slots'][locator]['source']
  tris=triangles(path,locs[locator] if locator else Matrix.Identity(4))
  m=bpy.data.meshes.new('LOD2 component');m.from_pydata([v for tri in tris for v in tri],[],[list(range(i,i+3)) for i in range(0,len(tris)*3,3)])
  bm=bmesh.new();bm.from_mesh(m);bmesh.ops.remove_doubles(bm,verts=list(bm.verts),dist=1e-6);bmesh.ops.dissolve_limit(bm,angle_limit=.02,verts=list(bm.verts),edges=list(bm.edges),use_dissolve_boundaries=False)
  bm.to_mesh(m);bm.free();m.update()
  o=bpy.data.objects.new('Simplify low detail',m);bpy.context.scene.collection.objects.link(o)
  for other in bpy.context.selected_objects:other.select_set(False)
  o.select_set(True);bpy.context.view_layer.objects.active=o
  if len(m.polygons)>200:
   mod=o.modifiers.new('Low detail budget','DECIMATE');mod.ratio=.3;bpy.ops.object.modifier_apply(modifier=mod.name)
  m=o.data
  start=len(faces);offset=len(verts);verts.extend([v.co[:] for v in m.vertices]);faces.extend([[i+offset for i in f.vertices] for f in m.polygons])
  if locator.startswith('WALL'):slots[locator]={'faces':[[start,len(faces)-1]]}
  bpy.data.objects.remove(o,do_unlink=True)
  bpy.data.meshes.remove(m)
 mesh=bpy.data.meshes.new(pid+' native low-detail opening preview');mesh.from_pydata(verts,[],faces);mesh.update()
 mesh.set_sharp_from_angle(angle=math.radians(35))
 for poly in mesh.polygons:poly.use_smooth=True
 bpy.data.libraries.write(str(out/(pid+'.blend')),{mesh},compress=True,fake_user=True)
 row['simple']={'vertices':len(mesh.vertices),'polygons':len(mesh.polygons),'slots':slots,'file':'hab_simple_openings/'+pid+'.blend','native_lod':2}
 print(pid,len(mesh.vertices),len(mesh.polygons),flush=True)
(P/'slots-candidate.json').write_text(json.dumps(rows,separators=(',',':')))
