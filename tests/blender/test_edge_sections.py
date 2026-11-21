"""Exercise edge clicks and the precision-sensitive continuation on a real stone floor."""
import math
import sys
from pathlib import Path
from mathutils import Vector

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_support import bpy, module

surface = module('curve_surface')
repeat = module('duplication_tools')
trim = module('edge_trim')
context = bpy.context
obj = module('builder_v2').add_part('S_FLOOR', high_res=True).object
obj.rotation_euler = (math.pi / 2, .13, .24)
obj.location = (2.96, -.3, 3.14)
context.view_layer.update()

mesh = surface.Surface(obj.data, obj.matrix_world)
face = max(obj.data.polygons, key=lambda polygon: polygon.area).index
edges = mesh.boundary(mesh.patch(face))
graph = surface.EdgeSections(mesh.vertices, edges)

def pick(edge):
    section = graph.section(*edge, 35)
    lines = frozenset(surface.segment(mesh.vertices[a], mesh.vertices[b]) for a,b in section)
    return surface.Pick('EDGE', 1, lines, seed_edge=surface.segment(*(mesh.vertices[i] for i in edge)))

long_edge = max(edges, key=lambda e: (mesh.vertices[e[0]]-mesh.vertices[e[1]]).length)
straight = pick(long_edge)
assert len(straight.edges) == 1
corner_edge = next(e for e in edges if e != long_edge and set(e).intersection(long_edge))
corner = pick(corner_edge)
assert len(corner.edges) == 2 and corner.edges.isdisjoint(straight.edges)
assert all(pick(e).edges == corner.edges for e in graph.section(*corner_edge, 35))
end = next(i for e in graph.section(*corner_edge, 35) for i in e
           if any(i in neighbor and pick(neighbor).edges not in (corner.edges, straight.edges) for neighbor in edges))
next_side = pick(next(e for e in edges if end in e and pick(e).edges != corner.edges))

chain = ()
for hit in (straight, corner, next_side):
    chain, preview, hint = surface.edge_edit(chain, hit)
    assert preview
assert len(chain) == 3 and len(surface.selection_paths(chain)) == 1
kept, removed, hint = surface.edge_edit(chain, corner)
assert len(kept) == 1 and kept[0].edges == straight.edges and removed == corner.edges | next_side.edges
assert len(surface.edge_edit(chain, next_side)[0]) == 2
assert not surface.edge_edit((straight,), next_side)[1]
assert surface.edge_edit((), corner)[0][0].edges == corner.edges

# Recreate the old selection, a straight side and its two tiny end bevels.
both_ends = [p for e in edges if e != long_edge and set(e).intersection(long_edge) for p in [pick(e)]]
path, closed = surface.selection_paths((surface.Pick('EDGE',1,straight.edges.union(*(p.edges for p in both_ends))),))[0]
limits = trim.Trace.from_path(path, closed).longest_straight()
assert limits[0] > 0 and limits[1] < 1
guide = surface.create_guides(context,[(path,closed)])[0]
repeat.finish_edge(context,guide,[obj.name],limits)
original = [guide.matrix_world @ bp.co for bp in guide.data.splines[0].bezier_points]
assert len(original) == 2
assert min((original[0]-mesh.vertices[i]).length for i in long_edge) < 2e-5
direction = (original[-1]-original[0]).normalized()
for distance in (19.24, 8, 30, 19.24):
    repeat.adjust(guide,'distance',distance)
    context.view_layer.update()
    for child in repeat.backend.children(guide):
        assert (child.matrix_world.translation-original[0]).cross(direction).length < 2e-5
    tip = guide.matrix_world @ guide.data.splines[0].bezier_points[-1].co
    assert ((tip-original[0]).dot(direction) - distance) < .003
    assert (tip-original[0]).dot(direction) >= distance-.003
print('PASS stone floor straight/round sections, contiguous click editing and straight repeat at 19.24 m')


# The normal picker supplies the traced object. A repeat on its own edge must
# continue the source exactly once and keep physical mesh edges collinear.
a, b = (mesh.vertices[i] for i in long_edge)
guide = surface.create_guides(context, [([a, b], False)])[0]
repeat.finish_edge(context, guide, [obj.name], traced=obj)
heading = (b - a).normalized()
projected = [(obj.matrix_world @ vertex.co).dot(heading) for vertex in obj.data.vertices]
width = max(projected) - min(projected)
for count, spacing in ((3, width), (5, width), (5, width * 1.25)):
    if guide['objects_count'] != count:
        repeat.adjust(guide, 'objects_count', count)
    if abs(guide['bbe_curve_spacing'] - spacing) > .001:
        assert spacing != width, 'Default spacing should match the actual part width'
        repeat.adjust(guide, 'spacing', spacing)
    context.view_layer.update()
    copies = sorted(repeat.backend.children(guide), key=lambda child: child['curve_factor'])
    assert len(copies) == count
    for index, child in enumerate(copies, 1):
        for vertex_index in long_edge:
            delta = (child.matrix_world @ child.data.vertices[vertex_index].co
                     - obj.matrix_world @ obj.data.vertices[vertex_index].co)
            assert (delta - index * spacing * heading).length < .001
print('PASS picked mesh edge continues beyond source and survives copy count and spacing edits')
