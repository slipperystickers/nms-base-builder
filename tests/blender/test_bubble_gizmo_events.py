"""Real viewport mouse-event regression; run with --enable-event-simulate.

BBE_GIZMO_FILE supplies a read-only affected .blend fixture. The round-trip
copy and screenshots go to QA. Optional baseline restores the old functions
from QA/bubble_preview_baseline.py to verify the regression reproduces.
"""
import bpy,sys,json,os,traceback,ast
from pathlib import Path
from mathutils import Quaternion,Vector
from bpy_extras.view3d_utils import location_3d_to_region_2d
sys.path.insert(0,str(Path(__file__).resolve().parent))
from test_support import addon,module,QA
pr=module('bubble_preview')
label=os.environ.get('BBE_GIZMO_PROBE','fixed')
if label=='baseline':
 tree=ast.parse((QA/'bubble_preview_baseline.py').read_text(encoding='utf-8-sig'))
 names={'refresh','_group_transform_active','_sync_elbow_controls','_sync_draft_shading'}
 for node in tree.body:
  if isinstance(node,ast.FunctionDef) and node.name in names:
   exec(compile(ast.Module(body=[node],type_ignores=[]),'baseline','exec'),pr.__dict__)
state={'step':0,'phase':0,'file':os.environ['BBE_GIZMO_FILE']}
def run():
 try:
  s=state['step'];state['step']+=1
  if s==0:
   bpy.ops.wm.open_mainfile(filepath=state['file'])
   return 2
  if s==1:
   cube=bpy.context.scene.objects.get('GIZMO_PROBE_CUBE')
   if cube is None:
    bpy.ops.mesh.primitive_cube_add(location=(100,100,100))
    cube=bpy.context.view_layer.objects.active;cube.name='GIZMO_PROBE_CUBE'
   state['cube']=cube
   area=next(a for a in bpy.context.window.screen.areas if a.type=='VIEW_3D');sp=area.spaces.active
   sp.show_region_ui=False;sp.show_gizmo=True;sp.show_gizmo_tool=True
   sp.region_3d.view_rotation=Quaternion((1,0,0,0));sp.region_3d.view_location=cube.location.copy();sp.region_3d.view_distance=12;sp.region_3d.view_perspective='ORTHO'
   with bpy.context.temp_override(area=area):bpy.ops.wm.tool_set_by_id(name='builtin.move')
   state['area']=area;state['before']=list(cube.location)
   return 3
  area=state['area'];region=next(r for r in area.regions if r.type=='WINDOW');win=bpy.context.window
  p=location_3d_to_region_2d(region,area.spaces.active.region_3d,Vector(state['before']))
  x=int(region.x+p.x+65);y=int(region.y+p.y)
  if s==2:
   bpy.ops.screen.screenshot(filepath=str(QA/f'gizmo-{label}-{state["phase"]}-before.png'))
   print('PROBE_COORD',x,y,'CENTER',tuple(p),'REGION',region.x,region.y,flush=True)
   win.event_simulate(type='MOUSEMOVE',value='NOTHING',x=x,y=y)
  elif s==3:win.event_simulate(type='LEFTMOUSE',value='PRESS',x=x,y=y)
  elif 4<=s<=8:win.event_simulate(type='MOUSEMOVE',value='NOTHING',x=x+(s-3)*20,y=y)
  elif s==9:win.event_simulate(type='LEFTMOUSE',value='RELEASE',x=x+100,y=y)
  else:
   cube=state['cube'];result=dict(label=label,phase=state['phase'],version=bpy.app.version_string,addon_path=addon.__file__,before=state['before'],after=list(cube.location),selected=cube.select_get(),active=bpy.context.active_object.name if bpy.context.active_object else None)
   print('GIZMO_UI_RESULT',json.dumps(result),flush=True)
   (QA/f'gizmo-{label}-{state["phase"]}.json').write_text(json.dumps(result))
   bpy.ops.screen.screenshot(filepath=str(QA/f'gizmo-{label}-{state["phase"]}-after.png'))
   moved=(cube.location-Vector(state['before'])).length>.1
   assert moved == (label!='baseline'),result
   if label!='baseline' and state['phase']==0:
    state['file']=str(QA/'bubble-gizmo-roundtrip.blend')
    bpy.ops.wm.save_as_mainfile(filepath=state['file'])
    state['phase']=1;state['step']=0
    return 1
   print('BUBBLE_GIZMO_EVENTS_PASS',label,flush=True)
   bpy.ops.wm.quit_blender();return None
  return .25
 except Exception:
  traceback.print_exc();bpy.ops.wm.quit_blender();return None
bpy.app.timers.register(run,first_interval=2,persistent=True)
