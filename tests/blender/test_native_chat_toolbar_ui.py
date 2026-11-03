import sys,traceback,ctypes,os
from ctypes import wintypes
from pathlib import Path
import bpy
sys.path.insert(0,str(Path(__file__).resolve().parent))
from test_support import module,QA
chat=module('bbe_chat')
if bpy.app.timers.is_registered(chat._tick):bpy.app.timers.unregister(chat._tick)
chat._chat_enabled=True
chat._toolbar_status={'preview':'Builder: Here is the latest message in the room, with a longer ending','unread':3,'online':7}
state={'step':0}
def run():
    try:
        if state['step']==0:
            state['step']=1
            bpy.context.window.event_simulate(type='ESC',value='PRESS',x=0,y=0)
            api=ctypes.WinDLL('user32');handles=[]
            api.GetWindowThreadProcessId.argtypes=(wintypes.HWND,ctypes.POINTER(wintypes.DWORD))
            api.SetWindowPos.argtypes=(wintypes.HWND,wintypes.HWND,ctypes.c_int,ctypes.c_int,ctypes.c_int,ctypes.c_int,wintypes.UINT)
            callback=ctypes.WINFUNCTYPE(wintypes.BOOL,wintypes.HWND,wintypes.LPARAM)
            def collect(hwnd,_):
                pid=wintypes.DWORD();api.GetWindowThreadProcessId(hwnd,ctypes.byref(pid))
                if pid.value==os.getpid():handles.append(hwnd)
                return True
            api.EnumWindows(callback(collect),0)
            api.IsWindowVisible.argtypes=(wintypes.HWND,)
            api.ShowWindow.argtypes=(wintypes.HWND,ctypes.c_int)
            for hwnd in handles:
                if api.IsWindowVisible(hwnd):
                    api.ShowWindow(hwnd,9)
                    api.SetWindowPos(hwnd,None,50,50,1850,950,0x14)
            return 2
        if state['step']==1:
            state['step']=2
            for area in bpy.context.screen.areas:area.tag_redraw()
            print('WINDOW_SIZE',bpy.context.window.width,bpy.context.window.height,flush=True)
            return 3
        if state['step']==2:
            assert chat._chat_icon()>0
            bpy.ops.screen.screenshot(filepath=str(QA/'single-chat-toolbar.png'))
            chat._chat_enabled=False
            for area in bpy.context.screen.areas:area.tag_redraw()
            state['step']=3
            return 1
        if state['step']==3:
            bpy.ops.screen.screenshot(filepath=str(QA/'chat-disabled-toolbar.png'))
            bpy.context.window.event_simulate(type='MOUSEMOVE',value='NOTHING',x=1150,y=bpy.context.window.height-65)
            state['step']=4
            return .3
        if state['step'] in (4,5):
            bpy.context.window.event_simulate(type='LEFTMOUSE',value='PRESS' if state['step']==4 else 'RELEASE',x=1150,y=bpy.context.window.height-65)
            state['step']+=1
            return .5
        bpy.ops.screen.screenshot(filepath=str(QA/'chat-enable-popover.png'))
        assert bpy.ops.bbe.chat_open.get_rna_type().properties['view']
        print('NATIVE_CHAT_TOOLBAR_UI_PASS',flush=True)
    except Exception:traceback.print_exc()
    bpy.ops.wm.quit_blender();return None
bpy.app.timers.register(run,first_interval=4)
