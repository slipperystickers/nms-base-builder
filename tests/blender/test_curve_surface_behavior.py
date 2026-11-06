"""Faceted patches, edge chains, and directional surface guides."""
from pathlib import Path
import math
import sys
from types import SimpleNamespace
import bpy
from mathutils import Matrix, Vector

sys.path.insert(0, str(Path(__file__).parent))
from test_support import module, report

s = module('curve_surface')
bpy.context.scene.nms_main.new_file()

nx, ny = 80, 10
vertices = [(x * .125 - 5, y * .2 - 1, .1 * math.sin(x * .25))
            for y in range(ny + 1) for x in range(nx + 1)]
faces = []
for y in range(ny):
    for x in range(nx):
        a = y * (nx + 1) + x
        faces.extend(((a, a + 1, a + nx + 2), (a, a + nx + 2, a + nx + 1)))
data = bpy.data.meshes.new('Faceted strip')
data.from_pydata(vertices, [], faces)
data.update()
surface = s.Surface(data, Matrix.Identity(4))
patch = surface.patch(0)
assert len(patch) == nx * ny * 2, len(patch)

# One edge click follows the long, nearly straight rim instead of one triangle.
chain = surface.edge_chain((0, 1))
assert len(chain) == nx, len(chain)
assert all(max(vertices[a][1], vertices[b][1]) == -1 for a, b in chain)

long, center, normal = surface.guide(patch)
across, _, _ = surface.guide(patch, angle=math.pi / 2)
assert len(long) > 20 and len(across) > 20
assert abs(long[-1].x - long[0].x) > 9.5
assert abs(across[-1].y - across[0].y) > 1.8
for path in (long, across):
    assert all(abs(p.z - .1 * math.sin((p.x + 5) * 2)) < .005 for p in path)

# A deliberately wavy mark gives a clean directional line across the patch.
scribble = [Vector((-4, -.3, 0)), Vector((-2, .6, 0)),
            Vector((0, -.5, 0)), Vector((2, .4, 0)), Vector((4, .2, 0))]
highlighted, _, _ = surface.guide(patch, hint=scribble[-1] - scribble[0])
assert max(abs(p.y) for p in highlighted) < .4
assert len(highlighted) > 20

# A strong 90-degree fold remains a meaningful boundary.
fold = bpy.data.meshes.new('Fold')
fold.from_pydata([(0,0,0),(1,0,0),(1,1,0),(0,1,0),(0,0,1),(1,0,1)],
                 [],[(0,1,2,3),(1,0,4,5)])
fold.update()
assert s.Surface(fold, Matrix.Identity(4)).patch(0) == frozenset((0,))

# Dense open topology uses the vectorized path and treats open rims as chains.
dx,dy=250,205
dense_vertices=[(x*.1,y*.1,0) for y in range(dy+1) for x in range(dx+1)]
dense_faces=[]
for y in range(dy):
    for x in range(dx):
        a=y*(dx+1)+x
        dense_faces.extend(((a,a+1,a+dx+2),(a,a+dx+2,a+dx+1)))
dense_mesh=bpy.data.meshes.new('Dense open sheet')
dense_mesh.from_pydata(dense_vertices,[],dense_faces);dense_mesh.update()
dense_obj=bpy.data.objects.new('Dense open sheet',dense_mesh)
bpy.context.collection.objects.link(dense_obj)
dense=s.DenseSurface(dense_mesh,Matrix.Identity(4),dense_obj)
dense_patch=dense.patch(0)
assert len(dense_patch)==len(dense_faces)
boundary=dense.boundary_ids(dense_patch)
assert len(boundary)==2*(dx+dy)
first=next(i for i,eid in enumerate(boundary)
           if set(dense.edge_vertices[eid])=={0,1})
chain=dense.boundary_chain(0,first)
assert len(chain)==dx and all(dense.coords[v,1]==0
                              for i in chain for v in dense.edge_vertices[boundary[i]])
dense_guide,_,_=dense.guide(dense_patch)
assert len(dense_guide)>20 and abs(dense_guide[-1].x-dense_guide[0].x)>24

# Numeric keys entered during a held ring drag specify exact degrees.
angles=[]
fake_rotation=SimpleNamespace(rotating=True,rotation_input='',rotation_start_angle=0,
    set_active_angle=lambda value,record=False:angles.append((value,record)),
    area=SimpleNamespace(tag_redraw=lambda:None))
s._sessions.append(fake_rotation)
for key in ('FOUR','FIVE'):
    assert s.BBE_OT_curve_surface.modal(fake_rotation,None,
        SimpleNamespace(type=key,value='PRESS'))=={'RUNNING_MODAL'}
s._sessions.remove(fake_rotation)
assert fake_rotation.rotation_input=='45'
assert abs(angles[-1][0]-math.radians(45))<1e-8 and not angles[-1][1]

# Enter during an unfinished brush stroke must wait for its projection job.
messages=[]
fake=SimpleNamespace(job=None,commit_stroke=lambda:None,report=lambda kinds,message:messages.append(message))
fake.commit_stroke=lambda:setattr(fake,'job',object())
assert s.BBE_OT_curve_surface.finish(fake,bpy.context)=={'RUNNING_MODAL'}
assert messages and 'clean surface path' in messages[-1]
report('curve_surface_behavior', dict(status='passed', facets=len(patch), edge_chain=len(chain),
                                      longest_direction=True, rotated=True, stroke_smoothed=True,
                                      dense_open_faces=len(dense_patch),numeric_rotation=True,
                                      finish_waits_for_projection=True))
