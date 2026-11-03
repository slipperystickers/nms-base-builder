import sys,subprocess,json,os,traceback
from pathlib import Path
import bpy
sys.path.insert(0,str(Path(__file__).resolve().parent))
from test_support import module,QA
chat=module('bbe_chat');state={}
def run():
 try:
  if 'child' not in state:
   site=Path(os.environ['APPDATA'])/'Blender Foundation/Blender/5.1/extensions/.local/lib/python3.13/site-packages'
   python=Path(bpy.app.binary_path).parent/'5.1/python/bin/python.exe'
   state['log']=(QA/'chat-native-dock.log').open('w')
   state['child']=subprocess.Popen([str(python),'-X','utf8',str(Path(__file__).resolve().parents[1]/'test_bbe_chat_native_dock.py'),str(site),str(os.getpid()),json.dumps({'viewport':chat._viewport_geometry(),'toolbar':chat._viewport_geometry('TOOL_HEADER')})],stdout=state['log'],stderr=subprocess.STDOUT)
  elif state['child'].poll() is not None:
   state['log'].close();text=(QA/'chat-native-dock.log').read_text();print(text,flush=True)
   assert state['child'].returncode==0,text
   bpy.ops.wm.quit_blender();return None
  return .5
 except Exception:
  traceback.print_exc();bpy.ops.wm.quit_blender();return None
bpy.app.timers.register(run,first_interval=3)
