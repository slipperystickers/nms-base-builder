"""Focused Qt composer paste, with draft-only transport and owned-file cleanup.

Pass the bundled Qt site path. Set BBE_CHAT_NATIVE_CLIPBOARD=1 to exercise the
Windows platform clipboard; existing MIME data is restored in finally.
"""
import json
import os
from pathlib import Path
import sys
import tempfile

root=Path(__file__).resolve().parents[1]
source=Path(os.environ.get('NMS_KUMA_TEST_ADDON', str(root/'src/addons/no_mans_sky_base_builder')))
site=Path(sys.argv[1])
sys.path.insert(0,str(source))
sys.argv=[str(source/'bbe_chat_messenger.py'),str(site),'identity','settings','snapshot']
native=os.environ.get('BBE_CHAT_NATIVE_CLIPBOARD')=='1'
os.environ['QT_QPA_PLATFORM']='windows' if native else 'offscreen'
import bbe_chat_messenger as m
from PySide6 import QtTest
app=m.QtWidgets.QApplication([])
font=Path('C:/Windows/Fonts/segoeui.ttf')
if font.is_file():
    m.QtGui.QFontDatabase.addApplicationFont(str(font))
    app.setFont(m.QtGui.QFont('Segoe UI',10))
clipboard=app.clipboard()
preserved=m.QtCore.QMimeData()
current=clipboard.mimeData()
if current:
    for mime in current.formats():
        preserved.setData(mime,current.data(mime))
calls=[]
def forbidden(*args,**kwargs):
    calls.append(args)
    raise AssertionError('Pasting must not contact the chat server')
m.helper.request=m.helper.run=forbidden
window=None
try:
    with tempfile.TemporaryDirectory() as temporary:
        folder=Path(temporary)
        identity=folder/'identity.json';settings=folder/'settings.json'
        identity.write_text(json.dumps({'secret':'s'*43,'id':'a'*32,'name':'Clipboard test',
                                       'names':[{'id':'a'*32,'name':'Clipboard test'}]}))
        settings.write_text('{"enabled":false}')
        window=m.Messenger(identity,settings,folder)
        window.timer.stop();window.snapshot_timer.stop()
        if not os.environ.get('BBE_CHAT_SHOW_CLIPBOARD'):
            window.setAttribute(m.QtCore.Qt.WA_DontShowOnScreen)
        window._collapse(False);window.show()
        if os.environ.get('BBE_CHAT_SHOW_CLIPBOARD'):
            window.mini_action.setChecked(False)
            window.resize(940,680)
            window.setWindowTitle('BBE Messenger — offline clipboard draft test')
        window.composer.setFocus()
        app.processEvents()
        sends=[]
        window.composer.send_requested.connect(lambda:sends.append(True))
        def paste():
            window.composer.setFocus()
            QtTest.QTest.keyClick(window.composer,m.QtCore.Qt.Key_V,m.QtCore.Qt.ControlModifier)
            app.processEvents()
        clipboard.setText('Unicode text: café 🌍\nSecond line')
        window.composer.setPlainText('Replace me')
        window.composer.selectAll();paste()
        assert window.composer.toPlainText()=='Unicode text: café 🌍\nSecond line'
        assert window.pending is None and not sends
        html=m.QtCore.QMimeData();html.setHtml('<b>Plain draft</b>');html.setText('Plain draft')
        clipboard.setMimeData(html);window.composer.selectAll();paste()
        assert window.composer.toPlainText()=='Plain draft'
        image=m.QtGui.QImage(12,8,m.QtGui.QImage.Format_RGBA8888)
        image.fill(m.QtGui.QColor(20,40,80,70))
        clipboard.setImage(image);paste()
        first=window.pending
        assert first and first.is_file() and window.pending_owned and first.suffix=='.png'
        assert window.pending_preserve_alpha
        decoded=m.QtGui.QImage(str(first))
        assert decoded.size()==image.size() and decoded.pixelColor(0,0)==image.pixelColor(0,0)
        assert window.composer.toPlainText()=='Plain draft' and not sends
        if os.environ.get('BBE_CHAT_SHOW_CLIPBOARD'):
            app.processEvents()
            QtTest.QTest.qWait(250)
            assert window.grab().save(str(root/'tests/.artifacts/chat-clipboard-native-draft.png'))
        # MIME-only PNG is used by some browser/image applications.
        data=m.QtCore.QByteArray();buffer=m.QtCore.QBuffer(data);buffer.open(m.QtCore.QIODevice.WriteOnly)
        assert image.save(buffer,'PNG');buffer.close()
        mime=m.QtCore.QMimeData();mime.setData('image/png',data)
        clipboard.setMimeData(mime);paste()
        second=window.pending
        assert second!=first and second.is_file() and not first.exists()
        # Explorer file copy keeps the original file and its media type.
        local=folder/'existing-image.png';assert image.save(str(local),'PNG')
        mime=m.QtCore.QMimeData();mime.setUrls([m.QtCore.QUrl.fromLocalFile(str(local))]);mime.setImageData(image)
        clipboard.setMimeData(mime);paste()
        assert window.pending==local and not window.pending_owned and not second.exists()
        window.clear_attachment();assert local.is_file()
        # Busy and rejected pastes preserve the existing draft and leak no PNG.
        before=set(Path(tempfile.gettempdir()).glob('bbe-chat-paste-*.png'))
        window.sending=True;clipboard.setImage(image);paste()
        assert window.pending is None
        window.sending=False
        original_limit=m.helper.file_limit;m.helper.file_limit=lambda path:1
        paste();m.helper.file_limit=original_limit
        assert window.pending is None
        assert set(Path(tempfile.gettempdir()).glob('bbe-chat-paste-*.png'))==before
        assert not calls and not sends and not window.messages
        paste();closing_draft=window.pending
        assert closing_draft and closing_draft.exists()
        window.close();window=None
        assert not closing_draft.exists() and local.exists()
finally:
    if window:
        window.sending=False;window.clear_attachment();window.close()
    if native:
        clipboard.setMimeData(preserved)
    else:
        clipboard.clear()
    app.processEvents()
print('BBE_CHAT_CLIPBOARD_OK', 'native Windows' if native else 'offscreen Qt')
