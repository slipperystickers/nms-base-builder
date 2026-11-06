"""A concave top strip follows its middle instead of bridging across its hook."""
import math,sys
from pathlib import Path
import bpy
from mathutils import Matrix,Vector
sys.path.insert(0,str(Path(__file__).parent))
from test_support import module
s=module('curve_surface')
centers=[]
for i in range(41):centers.append(Vector((2-i*.05,1,0)))
for i in range(1,101):
 a=math.pi/2+math.pi*i/100;centers.append(Vector((math.cos(a),math.sin(a),0)))
for i in range(1,201):centers.append(Vector((i*.05,-1,0)))
vertices=[]
for i,p in enumerate(centers):
 tangent=centers[min(i+1,len(centers)-1)]-centers[max(i-1,0)]
 across=Vector((-tangent.y,tangent.x,0)).normalized()*.15
 vertices.extend([p-across,p+across])
faces=[]
for i in range(len(centers)-1):
 a=2*i;faces.extend([(a,a+2,a+3),(a,a+3,a+1)])
mesh=bpy.data.meshes.new('Hooked strip');mesh.from_pydata(vertices,[],faces);mesh.update()
obj=bpy.data.objects.new('Hooked strip',mesh);bpy.context.collection.objects.link(obj)
for surface in (s.Surface(mesh,Matrix.Identity(4)),s.DenseSurface(mesh,Matrix.Identity(4),obj)):
 patch=surface.patch(0);assert len(patch)==len(faces)
 path,_,_=surface.guide(patch)
 assert len(path)>30 and min(p.x for p in path)<-.9
 assert max(p.x for p in path)>9.8
 assert any(p.x>1.8 and p.y>.9 for p in path)
 assert all(not(p.x>.2 and abs(p.y)<.8) for p in path), 'bridged across empty hook'
 for p in path:
  distance=abs(math.hypot(p.x,p.y)-1) if p.x<0 else min(abs(p.y-1),abs(p.y+1))
  assert distance<.08,(p,distance)
 turns=[(b-a).angle(c-b) for a,b,c in zip(path,path[1:],path[2:]) if (b-a).length>1e-5 and (c-b).length>1e-5]
 print('MAX_TURN',max(turns),flush=True)
 assert max(turns)<.12, 'visible corners in smooth face centerline'
 # The long rim is a substantial section; the turn cannot consume the loop.
 if isinstance(surface,s.DenseSurface):
  boundary=surface.boundary_ids(patch)
  edge=next(i for i,e in enumerate(surface.edge_vertices[boundary]) if min(surface.coords[e,0])>5)
  chain=surface.boundary_chain(0,edge)
  assert 100<len(chain)<len(boundary)*.8,(len(chain),len(boundary))
print('HOOKED_SURFACE_PASS',flush=True)

# Tiny bevel triangles must not join the broad top and wall into one patch.
profile=[(3.,1.),(1.,1.)]+[(1-math.sin(i*math.pi/100),math.cos(i*math.pi/100)) for i in range(1,51)]+[(0.,-3.)]
nv=len(profile);verts=[(x*.1,y,z) for x in range(81) for y,z in profile]
polys=[]
for x in range(80):
 for j in range(nv-1):
  a=x*nv+j;polys.extend([(a,a+nv,a+nv+1),(a,a+nv+1,a+1)])
bevel=bpy.data.meshes.new('Dense rounded lip');bevel.from_pydata(verts,[],polys);bevel.update()
bevel_obj=bpy.data.objects.new('Dense rounded lip',bevel);bpy.context.collection.objects.link(bevel_obj)
dense=s.DenseSurface(bevel,Matrix.Identity(4),bevel_obj)
patch=dense.patch((40*(nv-1)+31)*2)
normals=dense.normals_np[patch]
assert not ((abs(normals[:,2])>.99).any() and (abs(normals[:,1])>.99).any()),'bevel merged top and wall'
assert len(patch)>100
print('BEVEL_SURFACE_PASS',flush=True)
