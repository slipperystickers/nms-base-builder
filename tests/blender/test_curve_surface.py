"""Surface outlines preserve geometry, holes and independent source objects."""
from pathlib import Path
import sys, bpy
from mathutils import Matrix, Vector
sys.path.insert(0, str(Path(__file__).parent))
from test_support import module, report, QA
s = module('curve_surface'); c = module('curve_tools')
bpy.context.scene.nms_main.new_file()

def mesh(name, vertices, faces):
    data = bpy.data.meshes.new(name); data.from_pydata(vertices, [], faces); data.update()
    obj = bpy.data.objects.new(name, data); bpy.context.collection.objects.link(obj)
    return obj

# Triangles have duplicated vertices at their material seam.
obj = mesh('Seamed square', [(0,0,0),(2,0,0),(2,2,0),(0,0,0),(2,2,0),(0,2,0)], [(0,1,2),(3,4,5)])
obj.matrix_world = Matrix.Translation((4,5,6)) @ Matrix.Rotation(.7,4,'X') @ Matrix.Diagonal((2,3,1,1))
snapshot = s.Surface(obj.data, obj.matrix_world)
assert snapshot.patch(0) == frozenset((0,1))
edges = snapshot.boundary(snapshot.patch(0))
assert len(edges) == 4
paths = s.paths_from_edges(snapshot.vertices, edges)
assert len(paths) == 1 and paths[0][1] and len(paths[0][0]) == 4

# A hole remains a separate closed loop instead of being filled or bridged.
ring = mesh('Ring', [(-2,-2,0),(2,-2,0),(2,2,0),(-2,2,0),(-1,-1,0),(1,-1,0),(1,1,0),(-1,1,0)],
            [(0,1,5,4),(1,2,6,5),(2,3,7,6),(3,0,4,7)])
sr = s.Surface(ring.data, Matrix.Identity(4))
loops = s.paths_from_edges(sr.vertices, sr.boundary(sr.patch(0)))
assert len(loops) == 2 and all(closed and len(points)==4 for points,closed in loops)

# Neighboring angled faces must not merge; selecting both removes the shared edge.
fold = mesh('Fold', [(0,0,0),(1,0,0),(1,1,0),(0,1,0),(0,0,1),(1,0,1)], [(0,1,2,3),(1,0,4,5)])
sf = s.Surface(fold.data, Matrix.Identity(4))
assert sf.patch(0) == frozenset((0,)) and len(sf.boundary({0,1})) == 6

branch = s.paths_from_edges([Vector(v) for v in [(0,0,0),(1,0,0),(2,0,0),(1,1,0),(9,0,0),(10,0,0)]],
                           {(0,1),(1,2),(1,3),(4,5)})
assert len(branch) == 4 and all(not closed for _,closed in branch)

before = [(o, o.matrix_world.copy(), [v.co.copy() for v in o.data.vertices]) for o in (obj,ring,fold)]
guides = s.create_guides(bpy.context, paths+loops)
assert len(guides) == 3
bpy.context.view_layer.update()
for guide,(points,closed) in zip(guides,paths+loops):
    spline = guide.data.splines[0]
    assert spline.use_cyclic_u == closed
    assert guide.get('bbe_easy_curve') and not guide.get('ObjectID')
    assert all((guide.matrix_world @ bp.co-co).length < 1e-5 for bp,co in zip(spline.bezier_points,points))
    assert all(bp.handle_left_type == 'VECTOR' for bp in spline.bezier_points)
for o,matrix,vertices in before:
    assert o.matrix_world == matrix and all(v.co == co for v,co in zip(o.data.vertices,vertices))

# Traced curves use the existing duplication and Studio editing paths.
builder = module('builder_v2'); studio = module('curve_studio'); curve = module('utils.curve')
seed = builder.add_part('BUILDWALL',high_res=False,user_data=0).object
studio.choose(bpy.context,[seed,guides[0]]); bpy.context.view_layer.objects.active=guides[0]
bpy.context.scene.nms_build_tool.duplicate_along_curve(6,1)
guide=bpy.context.active_object
assert len(curve.get_all_curve_children(guide)) == 6
assert c.control_plane_normal(guide) is not None
bpy.ops.wm.save_as_mainfile(filepath=str(QA/'curve-surface.blend'))
bpy.ops.wm.open_mainfile(filepath=str(QA/'curve-surface.blend'))
assert len([o for o in bpy.data.objects if o.get('bbe_surface_trace')]) == 3
report('curve_surface',dict(status='passed',seams=True,transforms=True,holes=True,branches=True,
                           source_unchanged=True,editable=True,duplication=True,save_reopen=True))
