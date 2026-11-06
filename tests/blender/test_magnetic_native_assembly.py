"""Native lid copies must form a level, symmetric four-part ring."""
from pathlib import Path
import ast,sys
R=Path(__file__).resolve().parents[2];sys.path.insert(0,str(R/'tests/blender'))
p=R/'tests/blender/build_magnetic_mounts.py';tree=ast.parse(p.read_text());nodes=[]
for node in tree.body:
 if isinstance(node,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='out' for t in node.targets):break
 nodes.append(node)
env={'__file__':str(p),'__name__':'magnetic_geometry_test'};exec(compile(ast.Module(body=nodes,type_ignores=[]),str(p),'exec'),env)
ns=env['ns'];np=ns['np'];path='MODELS/COMMON/SPACECRAFT/BIGGS/MODULES/PARTS/MAG_1X1.SCENE.MBIN';root=ns['scene'](path)
g,raw,meta=ns['geometry'](root.attributes['GEOMETRY']);layout=g.PositionVertexLayout
centers=[]
for node in root.children:
 if not node.Name.startswith('lid_'):continue
 m=meta[node.Name.upper()];count=m.VertexPositionDataSize//layout.Stride;ve=next(v for v in layout.VertexElements if v.SemanticID==0);dtype={5131:np.float16,5126:np.float32}[ve.Type]
 xyz=np.ndarray((count,ve.Size),dtype=dtype,buffer=raw,offset=m.VertexPositionDataOffset+ve.Offset,strides=(layout.Stride,np.dtype(dtype).itemsize)).astype(np.float32)[:,:3]
 from mathutils import Vector
 center=Vector(((xyz.min(axis=0)+xyz.max(axis=0))*.5).tolist());correct=env['magnetic_matrix'](node,path)@center;old=node.matrix_local@center
 print(node.Name,'CORRECT',tuple(correct),'OLD',tuple(old),flush=True);centers.append(list(correct))
centers=np.asarray(centers)
assert len(centers)==4
assert np.ptp(centers[:,1])<.00001,centers
ring=centers[:,[0,2]];ring-=ring.mean(axis=0)
assert np.ptp(np.linalg.norm(ring,axis=1))<.00001,ring
assert np.linalg.norm(ring[0]+ring[2])<.00001
assert np.linalg.norm(ring[1]+ring[3])<.00001
from test_support import report
report('magnetic_native_assembly',dict(lids=4,height_spread=float(np.ptp(centers[:,1])),equal_spacing=True))
