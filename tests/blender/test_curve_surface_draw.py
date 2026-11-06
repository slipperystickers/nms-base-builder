"""Surface strokes, selection history, and bounded dense-mesh preparation."""
from pathlib import Path
from types import SimpleNamespace
import sys,time,bpy
from mathutils import Vector,Matrix
sys.path.insert(0,str(Path(__file__).parent))
from test_support import module,report,QA
s=module('curve_surface')
bpy.context.scene.nms_main.new_file()

edge=s.Pick('EDGE',('mesh',),frozenset((s.segment((0,0,0),(1,0,0)),)))
face=s.Pick('FACE',('mesh',),frozenset((s.segment((1,0,0),(1,1,0)),)))
history=s.SelectionHistory()
history.toggle(edge);history.toggle(face)
assert history.items==(edge,face)
history.undo();assert history.items==(edge,)
history.redo();assert history.items==(edge,face)
history.toggle(edge);assert history.items==(face,)
history.undo();assert history.items==(edge,face)
history.undo();history.toggle(edge)
assert history.items==() and not history.future

stroke=s.Stroke()
for co in [(0,0,0),(1,0,0),(1,1,1)]:stroke.add(('a',),co)
stroke.break_run()  # Off-model gap must not be bridged.
for co in [(3,0,0),(4,0,0)]:stroke.add(('a',),co)
stroke.add(('b',),(5,0,0));stroke.add(('b',),(6,0,0))
runs=stroke.finish();assert len(runs)==3
history.commit(runs);history.undo();assert not history.items
history.redo();assert history.items==runs
assert len(s.selection_paths(history.items))==3
assert len(s.stroke_samples(Vector((0,0)),Vector((1000,0))))<=32

# Exercise the actual modal shortcut dispatch, including shifted Blender redo.
shortcuts=[]
fake_op=SimpleNamespace(undo=lambda redo=False:shortcuts.append(redo),area=SimpleNamespace(tag_redraw=lambda:None),rotating=False)
s._sessions.append(fake_op)
for key,shift in [('Z',False),('Z',True),('Y',False)]:
    result=s.BBE_OT_curve_surface.modal(fake_op,None,SimpleNamespace(type=key,value='PRESS',ctrl=True,shift=shift))
    assert result=={'RUNNING_MODAL'}
assert shortcuts==[False,True,True]
s._sessions.remove(fake_op)

# Dense ordinary mesh, with no ObjectID. Hover must never construct Surface.
bpy.ops.mesh.primitive_uv_sphere_add(segments=384,ring_count=192,radius=5)
obj=bpy.context.object;obj.name='Dense ordinary mesh'
bpy.context.view_layer.update();depsgraph=bpy.context.evaluated_depsgraph_get()
mesh=obj.evaluated_get(depsgraph).data
key=(obj.as_pointer(),)
hit=(key,Vector((0,0,5)),0,obj,obj.matrix_world.copy(),depsgraph)
fake=SimpleNamespace(mode='FACE',ray=lambda context,xy:hit)
old=s.Surface.build_steps
def forbidden(*args):raise AssertionError('Hover started a full-mesh scan')
s.Surface.build_steps=forbidden
start=time.perf_counter()
for _ in range(100):
    pick,_=s.BBE_OT_curve_surface.local_pick(fake,bpy.context,Vector((0,0)))
    assert pick.kind=='FACE' and not pick.edges  # No misleading tiny-facet hover.
hover_ms=(time.perf_counter()-start)*10
s.Surface.build_steps=old

# Preparation explicitly yields after small batches, and can be canceled.
surface=s.Surface.__new__(s.Surface);job=surface.build_steps(mesh,Matrix.Identity(4))
assert 'vertices' in next(job)
job.close();assert not hasattr(surface,'faces')
surface=s.Surface.__new__(s.Surface);job=surface.build_steps(mesh,Matrix.Identity(4))
max_step=0.;steps=0
while True:
    start=time.perf_counter()
    try:next(job)
    except StopIteration:break
    max_step=max(max_step,time.perf_counter()-start);steps+=1
assert steps>100

# Sample a path on a curved mesh using Blender's actual ray intersections.
stroke=s.Stroke()
for i in range(41):
    x=-3+6*i/40
    found,location,normal,index,source,matrix=bpy.context.scene.ray_cast(depsgraph,Vector((x,0,10)),Vector((0,0,-1)))
    assert found and abs(location.length-5)<.002
    stroke.add(key,location)
runs=stroke.finish();assert len(runs)==1
before=[v.co.copy() for v in obj.data.vertices]
guides=s.create_guides(bpy.context,s.selection_paths(runs))
bpy.context.view_layer.update()
points=guides[0].data.splines[0].bezier_points
assert len(points)==41
assert all(abs((guides[0].matrix_world@p.co).length-5)<.002 for p in points)
assert all(v.co==co for v,co in zip(obj.data.vertices,before))
report('curve_surface_draw',dict(status='passed',undo_redo=True,deselect_undo=True,stroke_gaps=True,
    object_boundaries=True,hover_no_scan=True,hover_ms=round(hover_ms,3),faces=len(mesh.polygons),
    preparation_steps=steps,max_step_ms=round(max_step*1000,3),cancel_preparation=True,curved_surface=True))
