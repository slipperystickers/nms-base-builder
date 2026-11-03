"""Exercise the grouped Flip action through Blender's native operator search."""
import bpy,sys,math,traceback,json,os
from pathlib import Path
from mathutils import Matrix,Euler,Vector
sys.path.insert(0,str(Path(__file__).resolve().parent))
from test_support import addon,module,QA
Group=module('group').Group
state={'step':-1}
def key(kind,value='PRESS',**kw):bpy.context.window.event_simulate(type=kind,value=value,**kw)
def run():
 try:
  s=state['step'];state['step']+=1
  if s==-1:
   key('ESC');key('ESC','RELEASE');return 1
  if s==0:
   bpy.context.scene.nms_main.new_file();bpy.context.scene.bbe_detailed_proxies=True
   objects=[]
   for ident,position,scale,angles in [('STA_21',(.2253,0,4.5721),-.012,(-25.235,182.05,-15.636)),('B_WNG_O_2_R',(5.9285,-.75074,2.8767),.312,(90,-16.65,0))]:
    bpy.ops.object.select_all(action='DESELECT')
    bpy.ops.object.nms_asset_browser_object_selected(object_id=ident)
    obj=bpy.context.view_layer.objects.active
    obj.matrix_world=Matrix.Translation(position)@Euler(tuple(math.radians(a) for a in angles)).to_matrix().to_4x4()@Matrix.Scale(scale,4)
    bpy.context.view_layer.update();objects.append(obj)
   group=Group.group_objects(objects);group.select_set(True);bpy.context.view_layer.objects.active=group
   bpy.context.view_layer.update()
   state['before']=[group.matrix_world@v.co for v in group.data.vertices][::1000]
   area=next(a for a in bpy.context.window.screen.areas if a.type=='VIEW_3D')
   region=next(r for r in area.regions if r.type=='WINDOW');state['area']=area;state['region']=region
   area.spaces.active.show_region_ui=False
   area.spaces.active.region_3d.view_rotation=Euler((math.radians(70),0,math.radians(20))).to_quaternion()
   with bpy.context.temp_override(area=area,region=region):bpy.ops.view3d.view_selected(use_all_regions=False)
   return 2
  if s==1:
   bpy.ops.wm.save_as_mainfile(filepath=str(QA/'Nibiru-mirror-reproduction.blend'))
   bpy.ops.screen.screenshot(filepath=str(QA/'mirror-group-before.png'))
   r=state['region'];key('MOUSEMOVE','NOTHING',x=r.x+r.width//2,y=r.y+r.height//2)
  elif s==2:
   with bpy.context.temp_override(area=state['area'],region=state['region']):
    bpy.ops.wm.call_panel(name='NMS_PT_snap_panel',keep_open=True)
  elif s==3:
   bpy.ops.screen.screenshot(filepath=str(QA/'mirror-group-panel.png'))
   if 'BBE_FLIP_X' not in os.environ:
    bpy.ops.wm.quit_blender();return None
   key('MOUSEMOVE','NOTHING',x=int(os.environ['BBE_FLIP_X']),y=int(os.environ['BBE_FLIP_Y']))
  elif s==4:key('LEFTMOUSE',x=int(os.environ['BBE_FLIP_X']),y=int(os.environ['BBE_FLIP_Y']))
  elif s==5:key('LEFTMOUSE','RELEASE',x=int(os.environ['BBE_FLIP_X']),y=int(os.environ['BBE_FLIP_Y']))
  elif s==6:return 2
  else:
   obj=bpy.context.view_layer.objects.active
   after=[obj.matrix_world@v.co for v in obj.data.vertices][::1000]
   delta=max((a-b).length for a,b in zip(state['before'],after))
   ops=[o.bl_idname for o in bpy.context.window_manager.operators]
   assert 'OBJECT_OT_nms_flip' in ops,ops
   assert delta>.01,delta
   bpy.ops.screen.screenshot(filepath=str(QA/'mirror-group-after.png'))
   print('MIRROR_GROUP_UI_PASS',json.dumps(dict(version=bpy.app.version_string,addon_path=addon.__file__,geometry_delta=delta)),flush=True)
   bpy.ops.wm.quit_blender();return None
  return .5
 except Exception:
  traceback.print_exc();bpy.ops.wm.quit_blender();return None
bpy.app.timers.register(run,first_interval=2,persistent=True)
