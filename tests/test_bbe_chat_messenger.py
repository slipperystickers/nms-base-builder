"""Offscreen smoke for the standalone messenger's key and picture flow."""

import json
import os
from pathlib import Path
import sys
import tempfile

root = Path(__file__).resolve().parents[1]
source = root / 'src/addons/no_mans_sky_base_builder'
site = Path(sys.argv[1])
sys.path.insert(0, str(source))
sys.argv = [str(source / 'bbe_chat_messenger.py'), str(site), 'identity', 'settings', 'snapshot']
os.environ['QT_QPA_PLATFORM'] = 'offscreen'
import bbe_chat_messenger as messenger

app = messenger.QtWidgets.QApplication([])
for font in ('seguiemj.ttf', 'seguisym.ttf'):
    messenger.QtGui.QFontDatabase.addApplicationFont(str(Path('C:/Windows/Fonts')/font))
font_id = messenger.QtGui.QFontDatabase.addApplicationFont(r'C:\Windows\Fonts\segoeui.ttf')
families = messenger.QtGui.QFontDatabase.applicationFontFamilies(font_id)
if families:
    app.setFont(messenger.QtGui.QFont(families[0], 10))
with tempfile.TemporaryDirectory() as directory:
    folder = Path(directory)
    identity = folder / 'identity.json'
    settings = folder / 'settings.json'
    identity.write_text(json.dumps({'secret': 's' * 43, 'id': 'a' * 32,
                                    'name': 'FF', 'names': [{'id': 'a' * 32, 'name': 'FF'}]}))
    settings.write_text('{"enabled":false}')
    window = messenger.Messenger(identity, settings, folder)
    assert window.mini and window.collapsed and window.dock_mode == "toolbar"
    window.timer.stop()
    window.snapshot_timer.stop()
    assert window.minimumWidth() <= window.width()
    assert 'Click a name to start a DM' in window.dm_hint.text()
    settings.write_text(json.dumps({'enabled': False, 'theme': {
        'background': '#18202b', 'surface': '#263141', 'raised': '#344259',
        'text': '#e5efff', 'accent': '#539acb', 'outline': '#101823'}}))
    window._apply_theme()
    assert '#18202b' in window.styleSheet()
    window.pin_button.setChecked(True)
    assert window.windowFlags() & messenger.QtCore.Qt.WindowStaysOnTopHint
    window._dock('right')
    assert window.geometry().width() >= 320
    sends = []
    window.composer.send_requested.connect(lambda: sends.append('sent'))
    window.composer.setPlainText('Hello')
    event = messenger.QtGui.QKeyEvent(messenger.QtCore.QEvent.KeyPress,
                                      messenger.QtCore.Qt.Key_Return, messenger.QtCore.Qt.NoModifier)
    window.composer.keyPressEvent(event)
    assert sends == ['sent']
    assert window.composer.toPlainText() == 'Hello'
    settings.write_text('{"enabled":true}')
    original_run = messenger.helper.run
    original_request = messenger.helper.request
    messenger.helper.run = lambda action, detail: {
        'message': {'id': 'send-test', 'from': 'a' * 32, 'name': 'FF', 'text': detail['text'],
                    'time': 1792625770000, 'attachment': None}}
    messenger.helper.request = lambda action, data=None, **kwargs: {
        'me': {'id': 'a' * 32, 'name': 'FF'}, 'names': window.names, 'online': [],
        'contacts': [], 'messages': window.messages}
    window.composer.keyPressEvent(event)
    for _ in range(100):
        app.processEvents()
        if any(item['id'] == 'send-test' for item in window.messages) and not window.sending:
            break
        messenger.QtCore.QThread.msleep(10)
    assert not window.sending, (window.status.text(), [item['id'] for item in window.messages])
    assert window.composer.toPlainText() == ''
    assert any(item['id'] == 'send-test' for item in window.messages)

    snapshot = folder / 'sample.png'
    pixels = os.urandom(2200 * 1400 * 3)
    image = messenger.QtGui.QImage(pixels, 2200, 1400, 2200 * 3,
                                   messenger.QtGui.QImage.Format_RGB888)
    assert image.save(str(snapshot), 'PNG')
    window._stage(snapshot, owned=False)
    assert window.pending == snapshot
    window.media_labels['image-test'] = [messenger.QtWidgets.QLabel()]
    window._media_loaded('image-test', snapshot.read_bytes(), None)
    assert 'image-test' in window.media_cache
    optimized, made = window._small_image(snapshot, force_jpeg=True)
    assert made and optimized.suffix == '.jpg' and optimized.stat().st_size < snapshot.stat().st_size
    optimized.unlink()
    window.online = [{'id': 'b' * 32, 'name': 'BuilderFriend'}]
    window._draw_rooms()
    assert window.online_users.count() == 1
    assert window.online_users.item(0).text().endswith('BuilderFriend')
    window.online_users.setCurrentRow(0)
    assert window.target == 'b' * 32
    assert window.heading.text() == 'Direct Message · BuilderFriend'
    window.rooms.setCurrentRow(0)
    assert window.target is None
    window.pool.waitForDone()
    app.processEvents()
    window.sync = lambda: None
    window.message_generation += 1
    window.media_cache['c' * 32] = messenger.QtGui.QPixmap.fromImage(
        image.scaled(320, 240, messenger.QtCore.Qt.KeepAspectRatio))
    window.messages = [
        {'id': '1', 'from': 'b' * 32, 'name': 'BuilderFriend', 'text': 'Does this tube connect?',
         'time': 1792625770000, 'attachment': {'id': 'c' * 32, 'name': 'tube.png', 'mime': 'image/png'}},
        {'id': '2', 'from': 'a' * 32, 'name': 'FF', 'text': 'I can see it right here.',
         'time': 1792625775000, 'attachment': None},
    ]
    window._draw_messages()
    window.show()
    app.processEvents()
    window.mini_action.setChecked(True)
    app.processEvents()
    assert not window.sidebar.isVisible() and window.tools_widget.isHidden()
    assert window.width() <= 400, window.width()
    assert window.composer.isVisible() and window.scroll.isVisible()
    assert not window.media_labels, 'Mini mode must not eagerly create image thumbnails'
    window._toggle_image('c' * 32)
    app.processEvents()
    assert 'c' * 32 in window.media_labels, (window.messages, window.expanded_media, window.media_labels)
    assert window.media_labels['c' * 32][0].pixmap().height() <= 100
    window.resize(280, 260)
    app.processEvents()
    assert window.media_labels['c' * 32][0].pixmap().width() <= window.scroll.viewport().width()
    window._collapse(True)
    app.processEvents()
    assert window.height() <= 40 and not window.composer.isVisible()
    window._collapse(False)
    assert window.composer.isVisible()
    for position in ('top-left', 'top-right', 'bottom-left', 'bottom-right', 'top', 'bottom'):
        window._dock(position)
        assert window.dock_mode == position and window.mini
    # Mini keeps both actions beside the editor, with emoji insertion unsent.
    assert window.attach_button.isVisible() and window.emoji_button.isVisible()
    assert window.composer_row.layout().indexOf(window.attach_button) == 0
    assert window.composer_row.layout().indexOf(window.emoji_button) == 2
    assert [a.text() for a in window.attachment_menu.actions() if not a.isSeparator()] == ['Blender snapshot', 'Image…', 'Video…', 'File…']
    before = len(sends)
    window.composer.setPlainText('Nice ')
    window.composer.moveCursor(messenger.QtGui.QTextCursor.End)
    window._insert_emoji('👍')
    assert window.composer.toPlainText() == 'Nice 👍' and len(sends) == before
    assert abs(window.people_button.geometry().center().y()-window.centralWidget().height()/2) <= 2
    window.resize(360, 300)
    window._dock('top-right')
    window.sidebar_action.setChecked(True)
    app.processEvents()
    assert not window.sidebar.findChildren(messenger.QtWidgets.QLabel, 'brand')
    preview = os.environ.get('BBE_CHAT_REFINED_SCREENSHOT')
    if preview:
        canvas = messenger.QtGui.QPixmap(window.drawer.width()+window.width()+4, max(window.drawer.height(), window.height()))
        canvas.fill(messenger.QtGui.QColor('#10151c'))
        painter = messenger.QtGui.QPainter(canvas)
        painter.drawPixmap(0, 0, window.drawer.grab())
        painter.drawPixmap(window.drawer.width()+4, 0, window.grab())
        painter.end()
        assert canvas.save(preview)
    window.sidebar_action.setChecked(False)
    # The composer spans the bottom, independent of the sidebar gutter.
    origin = window.composer_row.mapTo(window.centralWidget(), messenger.QtCore.QPoint(0,0))
    assert origin.x() <= 8, origin
    assert window.composer_row.width() >= window.width()-16
    assert not window.mask().contains(messenger.QtCore.QPoint(0,0))
    assert window.mask().contains(messenger.QtCore.QPoint(window.width()//2,1))
    assert window.grab().toImage().pixelColor(0,0).alpha() == 0
    actions = [a.text() for a in window.options_button.menu().actions()]
    assert 'Dock top right' not in actions and 'Dock bottom right' not in actions
    window._notify_inbox([{'id':'long-preview', 'from':'b'*32, 'name':'BuilderFriend', 'time':9999999999999,
                          'text':'Here is a long incoming message that should be truncated to fit the compact toolbar strip without wrapping or increasing its height.'}])
    window._dock('toolbar')
    app.processEvents()
    assert window.collapsed and window.height() == window._strip_height()
    assert window.mini_title.text().endswith('height.')
    assert window.mini_title.display_text().endswith('…'), window.mini_title.display_text()
    if preview:
        assert window.grab().save(str(Path(preview).with_name('bbe-chat-collapsed-strip.png')))
    window._collapse(False)
    window._seen_inbox = set()
    window._collapse(True)
    window._notify_inbox([{'id': 'notice', 'from': 'b' * 32, 'to': window.persona}])
    assert window.unread['b' * 32] == 1
    window._notify_inbox([{'id': 'notice', 'from': 'b' * 32, 'to': window.persona}])
    assert window.unread['b' * 32] == 1
    window.sidebar_action.setChecked(True)
    assert window.drawer.isVisible() and window.sidebar.isVisible()
    window.sidebar_action.setChecked(False)
    app.processEvents()
    messenger.QtCore.QCoreApplication.sendPostedEvents(None, messenger.QtCore.QEvent.DeferredDelete)
    app.processEvents()
    screenshot = os.environ.get('BBE_CHAT_TEST_SCREENSHOT')
    if screenshot:
        assert window.grab().save(screenshot)
    transfer = window._begin_transfer('Uploading')
    transfer['_progress'](2 * 1024**3, 2 * 1024**3)
    app.processEvents()
    assert '100%' in window.status.text() and '2048/2048 MB' in window.status.text()
    assert window.cancel_transfer_action.isEnabled()
    if os.environ.get('BBE_CHAT_TRANSFER_SCREENSHOT'):
        window._collapse(False)
        app.processEvents()
        assert window.grab().save(os.environ['BBE_CHAT_TRANSFER_SCREENSHOT'])
    window.cancel_transfer_action.trigger()
    assert transfer['_cancel'].is_set()
    window._end_transfer()
    assert not window.cancel_transfer_action.isEnabled()
    window.pin_button.setChecked(False)
    window.close()
    saved = json.loads((folder / 'bbe_messenger_window.json').read_text())
    assert saved['pin'] is False and saved['pin_preference_version'] == 1 and saved['geometry']
    restored = messenger.Messenger(identity, settings, folder)
    assert not restored.pin_action.isChecked()
    restored.close()
    messenger.helper.run = original_run
    messenger.helper.request = original_request
print('BBE_CHAT_MESSENGER_OK')
