import json,os,sys,tempfile
from pathlib import Path
root=Path(__file__).resolve().parents[1]
source=root/'src/addons/no_mans_sky_base_builder'
site=sys.argv[1];sys.path.insert(0,str(source));sys.argv=[str(source/'bbe_chat_messenger.py'),site,'identity','settings','snapshot']
os.environ['QT_QPA_PLATFORM']='offscreen'
import bbe_chat_messenger as m
app=m.QtWidgets.QApplication([])
for font in ('segoeui.ttf','seguiemj.ttf','seguisym.ttf'):
    m.QtGui.QFontDatabase.addApplicationFont('C:/Windows/Fonts/'+font)
app.setFont(m.QtGui.QFont('Segoe UI',10))
m.Messenger.sync=lambda self:None
m.Messenger.show_account_settings=lambda self:None
with tempfile.TemporaryDirectory() as folder:
    folder=Path(folder);identity=folder/'identity.json';settings=folder/'settings.json'
    identity.write_text(json.dumps({'secret':'test-only','id':'a'*32,'names':[]}))
    settings.write_text(json.dumps({'enabled':False,'native_chat_toolbar':True}))
    w=m.Messenger(identity,settings,folder)
    w.timer.stop();w.snapshot_timer.stop();w.compact_timer.stop()
    assert w.mini and w.collapsed and not w.isVisible()
    w._remember_received([{'id':'preview','from':'builder','to':None,'time':1000,'name':'Builder','text':'Latest message in the actual toolbar'}])
    w.unread={'main':2};w._publish_toolbar_status()
    status=json.loads((folder/'toolbar-status.json').read_text())
    assert status=={'preview':'Builder: Latest message in the actual toolbar','unread':0,'directed':0,'online':None,'target':None}
    enabled=w._enabled
    w._enabled=lambda:True
    w._online_synced_at=m.time.monotonic()
    w.online=[{'id':w.persona},{'id':'other'},{'id':'other'},{'id':'second'}]
    w._publish_toolbar_status()
    assert json.loads((folder/'toolbar-status.json').read_text())['online']==2
    w.online=[];w._publish_toolbar_status()
    assert json.loads((folder/'toolbar-status.json').read_text())['online']==0
    w._synced(None,'Offline',w.target,w.persona,w.message_generation)
    w._publish_toolbar_status()
    assert json.loads((folder/'toolbar-status.json').read_text())['online'] is None
    w._online_synced_at=m.time.monotonic()-31;w._publish_toolbar_status()
    assert json.loads((folder/'toolbar-status.json').read_text())['online'] is None
    w._enabled=enabled
    (folder/'messenger-command.json').write_text('{"action":"CHAT"}')
    w._consume_blender_command();app.processEvents()
    assert w.isVisible() and not w.collapsed
    assert w.y()>w._toolbar_bounds().bottom()
    (folder/'messenger-command.json').write_text('{"action":"PEOPLE"}')
    w._consume_blender_command();app.processEvents()
    assert w.drawer.isVisible()
    assert w.drawer.y()==w.y(), 'Users drawer must share the chat top edge'
    assert w.sidebar.mapToGlobal(m.QtCore.QPoint(0,0)).y()==w.y(), 'Visible sidebar top must align without inset'
    w.dock_mode='floating'
    w.move(300,100);app.processEvents()
    assert w.drawer.y()==w.y(), 'Drawer must follow a floating chat move'
    w.resize(360,320);app.processEvents()
    assert w.drawer.y()==w.y(), 'Drawer must stay aligned after resizing'
    screen=w.screen().availableGeometry()
    w.move(300,screen.bottom()-w.height()+1);app.processEvents()
    assert w.drawer.y()==w.y(), 'Bottom-edge placement must retain top alignment'
    assert w.drawer.geometry().bottom()<=screen.bottom(), 'Drawer should shrink to available height'
    w.move(300,100);app.processEvents()
    assert w.drawer.height()>=320, 'Restore drawer height when space is available'
    capture=m.QtGui.QPixmap(w.width()+w.drawer.width(), max(w.height(),w.drawer.height()))
    capture.fill(m.QtCore.Qt.transparent)
    painter=m.QtGui.QPainter(capture)
    windows=sorted((w,w.drawer),key=lambda item:item.x())
    left=min(item.x() for item in windows)
    for window in windows:
        painter.drawPixmap(window.x()-left,window.y()-w.y(),window.grab())
    painter.end()
    capture.save(str(root/'tests/.artifacts/chat-alignment-19.png'))
    w.dock_mode='toolbar'
    w._collapse(True)
    assert not w.isVisible() and not w.drawer.isVisible()
    w._dock('top-right');w.show();w._collapse(False);w._collapse(True)
    assert w.isVisible(), 'Explicit corner mode should retain its floating strip'
    (folder/'messenger-command.json').write_text(json.dumps({'action':'TOOLBAR','anchor':{'x':.7,'bottom':.15}}))
    w._consume_blender_command();app.processEvents()
    assert w.mini and w.dock_mode=='toolbar' and w.isVisible() and not w.collapsed
    bounds=w._blender_bounds()
    assert abs(w.y()-(bounds.top()+round(.15*bounds.height())+2))<=1
    assert abs(w.x()-(bounds.left()+round(.7*bounds.width())-w.width()//2))<=1
    w.chat_enabled_toggle.setChecked(True)
    w.messages=[{'id':'fixture','from':'builder','name':'Builder','text':'Chat lives here. Enter sends; the side arrow opens users and DMs.','time':1,'to':None}]
    w._draw_messages();app.processEvents()
    w.grab().save(str(root/'tests/.artifacts/chat-dropdown-18.png'))
    w.composer.setPlainText('Keep this draft when disabling chat')
    w._set_enabled(False)
    assert w.collapsed and not w.isVisible()
    assert not w.chat_enabled_toggle.isChecked()
    assert w.composer.toPlainText()=='Keep this draft when disabling chat'
    w._set_enabled(True)
    assert w.chat_enabled_toggle.isChecked()
    (folder/'messenger-command.json').write_text('{"action":"TOOLBAR"}')
    w._consume_blender_command();app.processEvents()
    w.isActiveWindow=lambda:False
    w.drawer.isActiveWindow=lambda:False
    w._dismiss_dropdown_if_inactive()
    assert w.collapsed and not w.isVisible(), 'Clicking outside should dismiss toolbar chat'
    w.close()
print('NATIVE_CHAT_TOOLBAR_PASS')
