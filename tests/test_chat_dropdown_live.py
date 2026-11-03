"""Isolated native Qt companion for the Blender toolbar interaction test."""
import sys,json,time,ctypes
from ctypes import wintypes
from pathlib import Path
source=Path(__file__).resolve().parents[1]/'src/addons/no_mans_sky_base_builder'
site,folder=sys.argv[1:3];folder=Path(folder)
sys.path.insert(0,str(source))
sys.argv=[str(source/'bbe_chat_messenger.py'),site,str(folder/'identity.json'),str(folder/'settings.json'),str(folder)]
import bbe_chat_messenger as m
app=m.QtWidgets.QApplication([])
m.Messenger.sync=lambda self:None
m.Messenger._periodic=lambda self:None
m.Messenger.show_account_settings=lambda self:None
for font in ('segoeui.ttf','seguiemj.ttf','seguisym.ttf'):
    m.QtGui.QFontDatabase.addApplicationFont('C:/Windows/Fonts/'+font)
app.setFont(m.QtGui.QFont('Segoe UI',10))
w=m.Messenger(folder/'identity.json',folder/'settings.json',folder)
w.messages=[{'id':'test','from':'b'*32,'name':'Builder','text':'A single chat control, attached below the toolbar.','time':1,'to':None}]
w._draw_messages()
(folder/'ready').write_text('ready')
state={'shown':False}
def check():
    if not state['shown'] and w.isVisible() and not w.collapsed and w._toolbar_anchor:
        state['shown']=True
        api=ctypes.WinDLL('user32')
        api.GetClientRect.argtypes=(wintypes.HWND,ctypes.POINTER(wintypes.RECT))
        api.ClientToScreen.argtypes=(wintypes.HWND,ctypes.POINTER(wintypes.POINT))
        rect=wintypes.RECT();origin=wintypes.POINT()
        hwnd=w._toolbar_anchor['hwnd']
        api.GetClientRect(hwnd,ctypes.byref(rect));api.ClientToScreen(hwnd,ctypes.byref(origin))
        class Info(ctypes.Structure):
            _fields_=[('size',wintypes.DWORD),('monitor',wintypes.RECT),('work',wintypes.RECT),('flags',wintypes.DWORD),('device',wintypes.WCHAR*32)]
        api.MonitorFromWindow.argtypes=(wintypes.HWND,wintypes.DWORD);api.MonitorFromWindow.restype=wintypes.HANDLE
        api.GetMonitorInfoW.argtypes=(wintypes.HANDLE,ctypes.POINTER(Info))
        info=Info();info.size=ctypes.sizeof(info);api.GetMonitorInfoW(api.MonitorFromWindow(hwnd,2),ctypes.byref(info))
        print('NATIVE_RECT',origin.x,origin.y,rect.right,rect.bottom,'MONITOR',repr(info.device),'SCREENS',[(s.name(),s.geometry().getRect(),s.devicePixelRatio()) for s in app.screens()],'PLATFORM',app.platformName(),flush=True)
        (folder/'native.json').write_text(json.dumps({'native':[origin.x,origin.y,rect.right,rect.bottom],'monitor':info.device,'screens':[(s.name(),s.geometry().getRect(),s.devicePixelRatio()) for s in app.screens()],'platform':app.platformName(),'pid':w._settings().get('blender_pid')}))
        w.grab().save(str(folder/'dropdown.png'))
        (folder/'shown.json').write_text(json.dumps({'x':w.x(),'y':w.y(),'width':w.width(),'height':w.height(),
            'bounds':w._blender_bounds().getRect(),'anchor':w._toolbar_anchor,'active':w.isActiveWindow()}))
    if state['shown'] and w.collapsed and not w.isVisible():
        (folder/'dismissed').write_text('dismissed')
        w.close();app.quit()
timer=m.QtCore.QTimer();timer.timeout.connect(check);timer.start(200)
m.QtCore.QTimer.singleShot(25000,app.quit)
app.exec()
