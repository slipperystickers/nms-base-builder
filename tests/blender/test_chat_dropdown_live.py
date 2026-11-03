"""Click the real toolbar using a local, network-disabled Messenger fixture."""
import sys,json,tempfile,subprocess,ctypes,traceback,os
from pathlib import Path
from ctypes import wintypes
import bpy
sys.path.insert(0,str(Path(__file__).resolve().parent))
from test_support import module,QA
chat=module('bbe_chat')
if bpy.app.timers.is_registered(chat._tick):bpy.app.timers.unregister(chat._tick)
folder=Path(tempfile.mkdtemp(prefix='chat-dropdown-',dir=QA/'tmp'))
(folder/'bbe-chat-temp').mkdir()
identity=folder/'identity.json';settings=folder/'settings.json';commands=folder/'bbe-chat-temp'
identity.write_text(json.dumps({'secret':'isolated-no-network','id':'a'*32,'name':'Test','names':[{'id':'a'*32,'name':'Test'}]}))
settings.write_text(json.dumps({'enabled':True,'native_chat_toolbar':True}))
chat._identity_path=lambda:identity
chat._settings_path=lambda:settings
chat._identity=json.loads(identity.read_text());chat._chat_enabled=True
chat._toolbar_status={'preview':'Builder: Here is the latest message in the room, with a longer ending','unread':3}
# Companion expects its identity/settings beside command files, use copies and
# point all Blender writes at those exact isolated paths.
identity.rename(commands/'identity.json');settings.rename(commands/'settings.json')
identity=commands/'identity.json';settings=commands/'settings.json'
chat._identity_path=lambda:folder/'identity.json'
# The command directory comes from identity.parent, while the fixture identity
# itself is already in memory and does not need saving during this test.
chat._settings_path=lambda:settings
api=ctypes.WinDLL('user32')
api.GetForegroundWindow.restype=wintypes.HWND
api.SetForegroundWindow.argtypes=(wintypes.HWND,)
api.ShowWindow.argtypes=(wintypes.HWND,ctypes.c_int)
api.GetWindowThreadProcessId.argtypes=(wintypes.HWND,ctypes.POINTER(wintypes.DWORD))
api.SetWindowPos.argtypes=(wintypes.HWND,wintypes.HWND,ctypes.c_int,ctypes.c_int,ctypes.c_int,ctypes.c_int,wintypes.UINT)
state={'step':0,'tries':0}
def event(kind,value):bpy.context.window.event_simulate(type=kind,value=value,x=1150,y=bpy.context.window.height-65)
def run():
    try:
        i=state['step']
        if i==0:
            bpy.context.window.event_simulate(type='ESC',value='PRESS',x=0,y=0)
            hwnd=api.GetForegroundWindow();pid=wintypes.DWORD();api.GetWindowThreadProcessId(hwnd,ctypes.byref(pid))
            assert pid.value==os.getpid(),'Isolated Blender must own foreground for this test'
            state['hwnd']=hwnd
            api.ShowWindow(hwnd,9)
            api.SetWindowPos(hwnd,None,int(os.environ.get('BBE_TEST_WINDOW_X','50')),int(os.environ.get('BBE_TEST_WINDOW_Y','50')),1850,950,0x14)
            chat.sync_theme()
            script=Path(__file__).resolve().parents[1]/'test_chat_dropdown_live.py'
            chat._messenger_process=subprocess.Popen([chat._python_executable(),str(script),chat._qt_site_packages(),str(commands)],creationflags=subprocess.CREATE_NO_WINDOW)
        elif i==1:
            if not (commands/'ready').exists():return .5
            event('MOUSEMOVE','NOTHING')
        elif i==2:event('LEFTMOUSE','PRESS')
        elif i==3:event('LEFTMOUSE','RELEASE')
        elif i==4:
            if not (commands/'shown.json').exists():
                state['tries']+=1;assert state['tries']<20,'Toolbar did not open live dropdown';return .5
            data=json.loads((commands/'shown.json').read_text())
            print('LIVE_GEOMETRY',data,'BLENDER',bpy.context.window.x,bpy.context.window.y,bpy.context.window.width,bpy.context.window.height,flush=True)
            native=json.loads((commands/'native.json').read_text())
            assert data['bounds']==native['native'],(data,native) # This workstation uses 100% DPI.
            x,y,width,height=data['bounds'];anchor=data['anchor']
            assert abs(data['y']-(y+round(anchor['bottom']*height)+2))<=2,data
            assert data['active'],'Composer window did not receive focus'
            (QA/'chat-dropdown-live-result.json').write_text(json.dumps(data,indent=2))
            (QA/'chat-dropdown-live.png').write_bytes((commands/'dropdown.png').read_bytes())
            api.SetForegroundWindow(state['hwnd'])
        elif i==5:
            if not (commands/'dismissed').exists():
                state['tries']+=1;assert state['tries']<30,'Dropdown did not dismiss on Blender focus';return .5
            print('LIVE_CHAT_DROPDOWN_PASS',flush=True)
            bpy.ops.wm.quit_blender();return None
        state['step']+=1
        return .6
    except Exception:
        traceback.print_exc()
        if chat._messenger_process and chat._messenger_process.poll() is None:chat._messenger_process.terminate()
        bpy.ops.wm.quit_blender();return None
bpy.app.timers.register(run,first_interval=4)
