"""Hover is read-only, cached across traces, and clears over native/custom UI."""
from pathlib import Path
from types import SimpleNamespace
import sys,time,bpy
from mathutils import Matrix,Vector
sys.path.insert(0,str(Path(__file__).parent))
from test_support import module,report,QA
s=module('curve_surface')
fixture=QA/'burner-source.blend'
for o in tuple(bpy.context.scene.objects):bpy.data.objects.remove(o,do_unlink=True)
if fixture.exists():
    with bpy.data.libraries.load(str(fixture),link=False) as (a,b):b.objects=['Burner']
    obj=b.objects[0];bpy.context.collection.objects.link(obj)
else:
    bpy.ops.mesh.primitive_grid_add(x_subdivisions=80,y_subdivisions=20,size=10)
    obj=bpy.context.object
bpy.context.view_layer.update()
area=next(a for a in bpy.context.screen.areas if a.type=='VIEW_3D')
region=next(r for r in area.regions if r.type=='WINDOW')
depsgraph=bpy.context.evaluated_depsgraph_get();evaluated=obj.evaluated_get(depsgraph)
mesh=evaluated.data
index=max(range(len(mesh.polygons)),key=lambda i:mesh.polygons[i].normal.z)
key=(obj.as_pointer(),tuple(v for row in obj.matrix_world for v in row))
hit=(key,obj.matrix_world@mesh.polygons[index].center,index,obj,obj.matrix_world.copy(),depsgraph)
xy=Vector((region.width*.8,region.height*.5))

def drain(op):
    while op.job is not None or op.pending_click is not None:
        op.advance_preview()

class Harness:
    pass
for name,method in s.BBE_OT_curve_surface.__dict__.items():
    if callable(method) or isinstance(method,property):setattr(Harness,name,method)

def begin():
    op=Harness()
    op.area=area;op.region=region;op.window=bpy.context.window;op.workspace=bpy.context.workspace
    op.scene=bpy.context.scene;op.mode='DRAW';op.cache={};op.history=s.SelectionHistory()
    op.hover=None;op.selected_lines=[];op.hover_lines=[];op.stroke=None;op.last_xy=None
    op.stroke_hits={};op.active_pick=None;op.rotating=False;op.draw_guides={};op.next_guide_id=0
    op.rotation_input='';op.gizmo_lines=[];op.grabber_lines=[];op.gizmo_center=None;op.gizmo_normal=None
    op.job=None;op.progress='';op.last_hover_time=0.;op.dirty=True;op.job_is_hover=False
    op.hover_request=None;op.pending_click=None;op.face_previews={};op.hover_due=0.;op.hover_visible=False
    op.preview_lines=[];op.cursor_kind=None;op.batches=[];op.handles=[];op.helper=False;op.timer=None
    op.wm=SimpleNamespace(event_timer_remove=lambda _:None)
    s._sessions.append(op)
    return op

with bpy.context.temp_override(area=area,region=region):
    op=begin()
    start=time.perf_counter();op.change_mode('FACE');drain(op)
    topology_ms=(time.perf_counter()-start)*1000
    op.hover_request=(hit,xy,'FACE');op.hover_visible=True
    start=time.perf_counter();op.start_pick_job(op.hover_request,True);drain(op)
    first_ms=(time.perf_counter()-start)*1000
    assert op.hover and len(op.hover.points)>20 and not op.picks
    candidate=op.hover;surface=op.cache[key]
    start=time.perf_counter()
    for _ in range(50):
        op.start_pick_job(op.hover_request,True);drain(op)
        assert op.hover is candidate and not op.picks
    warm_ms=(time.perf_counter()-start)*20
    assert warm_ms<100,warm_ms
    start=time.perf_counter();op.accept_pick(candidate)
    click_ms=(time.perf_counter()-start)*1000
    assert len(op.picks)==1 and op.picks[0] is candidate
    scale,x,top,_=op.buttons()
    event=SimpleNamespace(type='MOUSEMOVE',value='NOTHING',mouse_x=region.x+x+30*scale,
        mouse_y=region.y+top-30*scale,mouse_region_x=x+30*scale,mouse_region_y=top-30*scale)
    assert op.modal(bpy.context,event)=={'RUNNING_MODAL'}
    assert op.cursor_kind=='DEFAULT' and op.hover is None and not op.hover_lines and not op.preview_lines
    event.mouse_y=region.y+region.height+20
    assert op.modal(bpy.context,event)=={'PASS_THROUGH'}
    assert op.cursor_kind=='DEFAULT'
    # A native confirmation must suspend work without losing the temporary path.
    timer=SimpleNamespace(type='TIMER',value='NOTHING')
    op.leave_prompt=True
    assert op.modal(bpy.context,timer)=={'PASS_THROUGH'}
    assert len(op.picks)==1 and op.picks[0] is candidate
    assert bpy.ops.bbe.surface_leave_choice(choice='KEEP')=={'FINISHED'}
    assert not op.leave_prompt and op.leave_action=='KEEP'
    assert op.modal(bpy.context,timer)=={'RUNNING_MODAL'}
    assert len(op.picks)==1 and op.picks[0] is candidate
    # Create uses the existing creation path, then discard explicitly ends a session.
    original_finish=op.finish
    created=[]
    op.finish=lambda context: created.extend(op.picks) or {'FINISHED'}
    op.leave_prompt=True
    assert bpy.ops.bbe.surface_leave_choice(choice='CREATE')=={'FINISHED'}
    assert op.leave_action=='CREATE' and not op.leave_prompt
    assert op.modal(bpy.context,timer)=={'FINISHED'} and created==[candidate]
    op.finish=original_finish
    op.cleanup()
    assert s._surface_snapshot.get('surface') is surface
    again=begin()
    start=time.perf_counter();again.change_mode('FACE');drain(again)
    again.hover_request=(hit,xy,'FACE');again.hover_visible=True
    again.start_pick_job(again.hover_request,True);drain(again)
    reopen_ms=(time.perf_counter()-start)*1000
    assert again.cache[key] is surface and again.hover is candidate and not again.picks
    assert reopen_ms<100,reopen_ms
    again.leave_prompt=True
    assert bpy.ops.bbe.surface_leave_choice(choice='DISCARD')=={'FINISHED'}
    assert again.leave_action=='DISCARD' and not again.leave_prompt
    assert again.modal(bpy.context,timer)=={'CANCELLED'} and again not in s._sessions
    s.invalidate_surface_snapshot(bpy.context.scene,SimpleNamespace(updates=[SimpleNamespace(
        is_updated_geometry=True,id=SimpleNamespace(original=obj.data))]))
    assert not s._surface_snapshot
report('curve_surface_hover',dict(facets=len(mesh.polygons),topology_ms=topology_ms,
    first_patch_ms=first_ms,cached_preview_ms=warm_ms,click_ms=click_ms,reopen_ms=reopen_ms,
    hover_does_not_select=True,pointer_over_ui=True,geometry_invalidates_cache=True))
