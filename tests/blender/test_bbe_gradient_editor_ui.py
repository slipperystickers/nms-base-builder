from pathlib import Path
import sys,traceback
import bpy
sys.path.insert(0,str(Path(__file__).resolve().parent))
from test_support import module,QA
state={'step':0};themes=module('bbe_themes')
def run():
 try:
  s=state['step'];state['step']+=1
  if s==0:
   bpy.context.window.event_simulate(type='ESC',value='PRESS');bpy.context.window.event_simulate(type='ESC',value='RELEASE')
   themes.apply_theme('VIOLET')
  elif s==1:
   area=next(a for a in bpy.context.window.screen.areas if a.type=='VIEW_3D')
   with bpy.context.temp_override(area=area):bpy.ops.bbe.custom_theme('INVOKE_DEFAULT')
  elif s==2:
   bpy.ops.screen.screenshot(filepath=str(QA/'bbe-gradient-editor-18213.png'))
   print('BBE_GRADIENT_EDITOR_VISIBLE',flush=True)
   bpy.context.window.event_simulate(type='ESC',value='PRESS');bpy.context.window.event_simulate(type='ESC',value='RELEASE')
  elif s==3:
   bpy.ops.wm.quit_blender();return None
  return 1
 except Exception:
  traceback.print_exc();bpy.ops.wm.quit_blender();return None
bpy.app.timers.register(run,first_interval=2)
