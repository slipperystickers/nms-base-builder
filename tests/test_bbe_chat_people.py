"""Exercise real list geometry for a few contacts and a crowded drawer."""
import json, os, sys, tempfile
from pathlib import Path
root = Path(__file__).resolve().parents[1]
source = root/'src/addons/no_mans_sky_base_builder'
site = sys.argv[1]
sys.path.insert(0, str(source))
sys.argv = [str(source/'bbe_chat_messenger.py'), site, 'identity', 'settings', 'snapshot']
os.environ['QT_QPA_PLATFORM'] = 'offscreen'
import bbe_chat_messenger as m
app = m.QtWidgets.QApplication([])
for font in ('segoeui.ttf', 'seguiemj.ttf', 'seguisym.ttf'):
    m.QtGui.QFontDatabase.addApplicationFont('C:/Windows/Fonts/'+font)
app.setFont(m.QtGui.QFont('Segoe UI', 10))
m.Messenger.sync = lambda self: None
m.Messenger.show_account_settings = lambda self: None
with tempfile.TemporaryDirectory() as tmp:
    p = Path(tmp)
    identity, settings = p/'identity.json', p/'settings.json'
    identity.write_text(json.dumps({'secret':'test-only', 'id':'me', 'names':[{'id':'me','name':'Alice'}]}))
    settings.write_text(json.dumps({'enabled':True, 'native_chat_toolbar':True}))
    w = m.Messenger(identity, settings, p)
    w.timer.stop(); w.snapshot_timer.stop(); w.compact_timer.stop()
    w.dock_mode = 'floating'; w.move(300, 40); w.show(); w._collapse(False)
    w.sidebar_action.setChecked(True)
    people = [{'id':str(i),'name':name} for i,name in enumerate(('Bob','Zapper','Builder','Sam','Longer Builder Name'))]
    w.online = people[:2]; w.contacts = people[:2]; w._draw_rooms()
    w.online_label.setText('Online users: 2')
    w.drawer.show(); w._position_drawer()
    for _ in range(6): app.processEvents()
    assert w.drawer.y() == w.y()
    for listing in (w.rooms, w.online_users):
        assert listing.verticalScrollBar().maximum() == 0, (listing.objectName(), listing.height(), listing.sizeHintForRow(0))
    assert w.online_users.sizeHintForRow(0) <= m.QtGui.QFontMetrics(app.font()).height()+8
    small_height = w.drawer.height()
    w.online = people; w.contacts = people; w._draw_rooms()
    w.online_label.setText('Online users: 5')
    for _ in range(6): app.processEvents()
    assert w.drawer.height() > small_height
    assert w.rooms.verticalScrollBar().maximum() == 0
    assert w.online_users.verticalScrollBar().maximum() == 0
    w.drawer.grab().save(str(root/'tests/.artifacts/chat22-people-ui.png'))
    # Many people remain bounded, scrollable, and clickable without poll resets.
    w.online = [{'id':str(i),'name':f'Builder {i:02}'} for i in range(100)]
    w.contacts = w.online[:30]; w._draw_rooms()
    for _ in range(6): app.processEvents()
    assert w.drawer.geometry().bottom() <= w.screen().availableGeometry().bottom()
    bar = w.online_users.verticalScrollBar(); assert bar.maximum() > 0
    bar.setValue(bar.maximum()//2); old = bar.value()
    w._draw_rooms()
    for _ in range(6): app.processEvents()
    assert bar.value() == old, (bar.value(), old)
    chosen = w.online_users.item(20)
    w._select_online_user(chosen, None)
    assert w.target == '20' and w.heading.text() == 'Direct Message · Builder 20'
    # Close the active DM through its actual inline hit target.
    from PySide6.QtTest import QTest
    row = next(i for i in range(w.rooms.count()) if w.rooms.item(i).data(m.QtCore.Qt.UserRole) == '20')
    item = w.rooms.item(row)
    w.rooms.scrollToItem(item)
    app.processEvents()
    rect = w.rooms.visualItemRect(item)
    QTest.mouseClick(w.rooms.viewport(), m.QtCore.Qt.LeftButton, pos=m.ConversationDelegate.close_rect(rect).center())
    assert w.target is None
    assert '20' in w.closed_conversations['me']
    assert not any(w.rooms.item(i).data(m.QtCore.Qt.UserRole)=='20' for i in range(w.rooms.count()))
    w._draw_rooms()  # A normal refresh cannot bring it back.
    assert not any(w.rooms.item(i).data(m.QtCore.Qt.UserRole)=='20' for i in range(w.rooms.count()))
    assert '20' in m.chat_state.load(p/'closed-conversations.json')['me']
    # Clicking the person restores the existing conversation; new DMs also restore it.
    w._open_conversation('20','Builder 20')
    assert '20' not in w.closed_conversations['me']
    w.close_conversation('20')
    w._notify_inbox([{'id':'new-dm','from':'20','to':'me','name':'Builder 20','text':'Hello again','time':m.time.time()*1000+100}])
    w._draw_rooms()
    assert '20' not in w.closed_conversations['me']
    assert any(w.rooms.item(i).data(m.QtCore.Qt.UserRole)=='20' for i in range(w.rooms.count()))
    w.close()
print('CHAT22_COMPACT_PEOPLE_PASS')
