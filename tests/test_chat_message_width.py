"""Offline mini-chat width, wrapping, controls and scroll regressions.

Run with Blender Python and tests/.artifacts/python_dependencies as argv[1].
The helper is blocked before construction; no account or network calls occur.
"""
import json
import math
import os
from pathlib import Path
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'src/addons/no_mans_sky_base_builder'
SITE = sys.argv[1]
LABEL = sys.argv[2] if len(sys.argv) > 2 else 'current'
sys.path.insert(0, str(SOURCE))
sys.argv = [str(SOURCE / 'bbe_chat_messenger.py'), SITE, 'identity', 'settings', 'snapshot']
os.environ['QT_QPA_PLATFORM'] = 'offscreen'
import bbe_chat_messenger as m
from PySide6.QtTest import QTest


def forbidden(*args, **kwargs):
    raise AssertionError('This regression must never call the chat service')


m.helper.run = forbidden
m.helper.request = forbidden
m.Messenger.sync = lambda self: None
m.Messenger._periodic = lambda self: None
m.Messenger.show_account_settings = lambda self: None
m.Messenger._place_attached = lambda self: None
m.Messenger._dismiss_dropdown_if_inactive = lambda self: None

app = m.QtWidgets.QApplication([])
for font in ('segoeui.ttf', 'seguiemj.ttf', 'seguisym.ttf'):
    m.QtGui.QFontDatabase.addApplicationFont('C:/Windows/Fonts/' + font)
app.setFont(m.QtGui.QFont('Segoe UI', 10))

failures = []
metrics = []


def check(condition, detail):
    if not condition:
        failures.append(detail)


def settle():
    m.QtCore.QCoreApplication.sendPostedEvents(None, m.QtCore.QEvent.DeferredDelete)
    for _ in range(12):
        app.processEvents()


def message(ident, **values):
    result = dict(id=ident, **{'from': 'bob'}, to=None, name='Bob',
                  text='Hello there', time=1793253000000, attachment=None)
    result.update(values)
    return result


def text_content(widget):
    if isinstance(widget, m.QtWidgets.QTextBrowser):
        return widget.toPlainText()
    if isinstance(widget, m.QtWidgets.QLabel):
        return widget.text()
    return None


def wheel_over(window, widget):
    viewport = window.scroll.viewport()
    origin = widget.mapTo(viewport, m.QtCore.QPoint())
    visible = m.QtCore.QRect(origin, widget.size()).intersected(viewport.rect())
    check(not visible.isEmpty(), 'Wheel target is outside the visible history')
    position = viewport.mapTo(window, visible.center())
    QTest.wheelEvent(window.windowHandle(), position, m.QtCore.QPoint(0, 120))
    settle()


def inspect_width(window, case, expected_width=340):
    settle()
    viewport = window.scroll.viewport()
    bar = window.scroll.horizontalScrollBar()
    frames = window.message_container.findChildren(m.QtWidgets.QFrame, 'message')
    metrics.append(dict(case=case, window=window.width(), viewport=viewport.width(),
                        container=window.message_container.width(), horizontalMax=bar.maximum(),
                        horizontalVisible=bar.isVisible(), bubbles=[frame.width() for frame in frames]))
    check(window.width() == expected_width, f'{case}: window grew to {window.width()} px')
    check(bar.maximum() == 0 and not bar.isVisible(), f'{case}: horizontal scrollbar {bar.maximum()}')
    check(window.message_container.width() <= viewport.width(), f'{case}: content wider than viewport')
    for frame in frames:
        origin = frame.mapTo(viewport, m.QtCore.QPoint(0, 0))
        check(origin.x() >= 0 and origin.x() + frame.width() <= viewport.width(),
              f'{case}: bubble exceeds viewport ({origin.x()}, {frame.width()}, {viewport.width()})')
        for widget in frame.findChildren(m.QtWidgets.QWidget):
            if widget.isHidden():
                continue
            point = widget.mapTo(frame, m.QtCore.QPoint(0, 0))
            check(point.x() >= 0 and point.x() + widget.width() <= frame.width(),
                  f'{case}: {type(widget).__name__} spills outside bubble')
            if isinstance(widget, m.QtWidgets.QLabel) and widget.wordWrap():
                needed = widget.heightForWidth(widget.width())
                check(needed < 0 or widget.height() >= needed,
                      f'{case}: wrapped label clipped vertically ({widget.height()} < {needed})')
            if isinstance(widget, m.QtWidgets.QLabel):
                pixmap = widget.pixmap()
                if pixmap is not None and not pixmap.isNull():
                    check(pixmap.width() <= widget.contentsRect().width(),
                          f'{case}: image clipped horizontally ({pixmap.width()} > {widget.contentsRect().width()})')
                    check(pixmap.height() <= widget.contentsRect().height(), f'{case}: image clipped vertically')
            if isinstance(widget, m.QtWidgets.QTextBrowser):
                check(widget.horizontalScrollBar().maximum() == 0, f'{case}: inner horizontal text scrolling')
                check(widget.verticalScrollBar().maximum() == 0,
                      f'{case}: inner vertical text scrolling (max={widget.verticalScrollBar().maximum()}, '
                      f'value={widget.verticalScrollBar().value()}, doc={widget.document().size().height()}, '
                      f'view={widget.viewport().height()}, text={widget.toPlainText()[:24]!r})')
                check(widget.viewport().height() >= math.ceil(widget.document().size().height()),
                      f'{case}: document extends below its viewport')
                block = widget.document().begin()
                while block.isValid():
                    layout = block.layout()
                    for index in range(layout.lineCount()):
                        line = layout.lineAt(index)
                        check(line.naturalTextWidth() <= widget.viewport().width() + 1,
                              f'{case}: rendered text line exceeds available width')
                    block = block.next()
    check(window.composer.isVisible() and window.composer.width() >= 80,
          f'{case}: composer not usable')


with tempfile.TemporaryDirectory() as temp:
    folder = Path(temp)
    identity = folder / 'identity.json'
    settings = folder / 'settings.json'
    identity.write_text(json.dumps({'secret': 'offline-only', 'id': 'alice',
                                    'names': [{'id': 'alice', 'name': 'Alice'}]}))
    settings.write_text(json.dumps({'enabled': True, 'native_chat_toolbar': True}))
    window = m.Messenger(identity, settings, folder)
    window.timer.stop()
    window.snapshot_timer.stop()
    window.compact_timer.stop()
    window._job = lambda *args, **kwargs: None
    window._collapse(False)
    window.resize(340, 300)
    window.show()
    settle()

    token = 'Abcdef0123456789' * 60
    url = 'https://example.invalid/builds/' + token + '?download=1'
    filename = 'VeryLongBuildName_' + 'C' * 180 + '.nmsprefab'
    cases = [
        ('sender', message('sender', name='VeryLongBuilderNameWithoutSpaces_' * 3)),
        ('body', message('body', text=token)),
        ('url', message('url', text=url)),
        ('quote', message('quote', text=m.chat_state.make_reply('Alice', token, 'That is the part.'))),
        ('file', message('file', attachment=dict(id='file', name=filename,
                     mime='application/octet-stream', kind='file', expiresAt=9999999999999))),
        ('expired', message('expired', attachment=dict(id='expired', name=filename,
                     mime='application/octet-stream', expired=True))),
        ('image', message('image', attachment=dict(id='image', name=filename + '.png', mime='image/png'))),
        ('own-body', message('own-body', **{'from': 'alice'}, text=token)),
    ]
    for case, item in cases:
        window.messages = [item]
        window._draw_messages()
        window.resize(340, 300)
        inspect_width(window, case)
        labels = window.message_container.findChildren(m.QtWidgets.QWidget)
        if case in ('body', 'url'):
            content = [label for label in labels if text_content(label) == item['text']]
            check(bool(content), f'{case}: original content lost')
            check(bool(content) and bool(content[0].textInteractionFlags() & m.QtCore.Qt.TextSelectableByMouse),
                  f'{case}: message/link cannot be selected for copying')
            if content:
                label = content[0]
                font = label.fontMetrics()
                minimum_lines = math.ceil(font.horizontalAdvance(item['text']) / max(1, label.viewport().width()))
                minimum_height = minimum_lines * font.height()
                check(label.height() >= minimum_height,
                      f'{case}: long token did not wrap fully ({label.height()} < {minimum_height}, {minimum_lines} lines)')
                block = label.document().begin()
                line_count = 0
                laid_out_characters = 0
                while block.isValid():
                    layout = block.layout()
                    line_count += layout.lineCount()
                    laid_out_characters += sum(layout.lineAt(i).textLength() for i in range(layout.lineCount()))
                    block = block.next()
                check(line_count >= minimum_lines, f'{case}: token has too few rendered lines')
                check(laid_out_characters == len(item['text']), f'{case}: not all characters were laid out')
                cursor = label.textCursor()
                cursor.select(m.QtGui.QTextCursor.Document)
                check(cursor.selectedText() == item['text'], f'{case}: copy selection changed original text')
        if case in ('sender', 'body', 'url', 'quote', 'file', 'expired'):
            window.scroll.verticalScrollBar().setValue(0)
            settle()
            check(window.grab().save(str(ROOT / 'tests/.artifacts' / f'chat_width36_case_{case}.png')),
                  f'Could not save {case} screenshot')

    # Real signal paths must still work with width-constrained controls.
    window.messages = [cases[0][1], cases[4][1], cases[6][1]]
    window._draw_messages()
    settle()
    replies = window.message_container.findChildren(m.QtWidgets.QToolButton)
    check(bool(replies), 'No reply controls')
    replies[0].click()
    check(window.reply_to and window.reply_to['id'] == 'sender', 'Reply click did not select source')
    inspect_width(window, 'reply-banner')
    window.reply_banner.click()
    check(window.reply_to is None, 'Reply cancellation failed')
    saved = []
    window.save_attachment = lambda item: saved.append(item['id'])
    saves = [button for button in window.message_container.findChildren(m.QtWidgets.QPushButton)
             if button.text().startswith('Save')]
    check(bool(saves), 'No attachment save control')
    saves[0].click()
    check(saved == ['file'], 'Attachment save control lost its target')
    pixmap = m.QtGui.QPixmap(640, 480)
    pixmap.fill(m.QtGui.QColor('#348dcc'))
    window.media_cache['image'] = pixmap
    image_buttons = [button for button in window.message_container.findChildren(m.QtWidgets.QPushButton)
                     if button.text().startswith('View image')]
    check(bool(image_buttons), 'No image expand control')
    image_buttons[0].click()
    inspect_width(window, 'expanded-image')
    check('image' in window.expanded_media and bool(window.media_labels.get('image')), 'Image did not expand')

    # A full-window message layout must shrink when switched back to mini.
    window.mini_action.setChecked(False)
    window.resize(800, 600)
    window.messages = [item for _, item in cases]
    window._draw_messages()
    settle()
    window.mini_action.setChecked(True)
    window.resize(340, 300)
    inspect_width(window, 'full-to-mini')

    window.messages = [message(str(i), text='A normal wrapped message ' * 8) for i in range(35)]
    window._draw_messages()
    inspect_width(window, 'history')
    vertical = window.scroll.verticalScrollBar()
    check(vertical.maximum() > 0 and vertical.value() == vertical.maximum(), 'History did not follow newest message')
    body_widgets = [widget for widget in window.message_container.findChildren(m.QtWidgets.QWidget)
                    if (text_content(widget) or '').startswith('A normal wrapped')]
    if body_widgets:
        body_widget = body_widgets[-1]
        prior_scroll = vertical.value()
        wheel_over(window, body_widget)
        check(vertical.value() < prior_scroll, 'Mouse wheel over message did not scroll chat history')
    window.messages.append(message('scroll-url', text=url))
    window._draw_messages()
    settle()
    browser = next(widget for widget in window.message_container.findChildren(m.QtWidgets.QTextBrowser)
                   if widget.toPlainText() == url)
    prior_scroll = vertical.value()
    wheel_over(window, browser.viewport())
    check(browser.verticalScrollBar().value() == 0, 'Mouse wheel scrolled inside long message')
    check(vertical.value() < prior_scroll, 'Mouse wheel over long message did not scroll chat history')
    vertical.setValue(0)
    window._user_scrolled()
    check(not window._follow_latest, 'Manual scroll state lost')
    window.messages.append(message('latest', text='The newest message'))
    window._draw_messages()
    inspect_width(window, 'latest')
    check(vertical.value() == vertical.maximum(), 'New message did not scroll to bottom')

    # Exercise real resizing at the minimum width, default width and a wider mini.
    # These fit checks include actual image pixmap dimensions, not only policies.
    preview_messages = [
        message('qa-file', text='The updated build is attached.', attachment=dict(
            id='qa-file', name='CorvetteEngineAssembly_WithCustomPanels_RevisionThirtySix.nmsprefab',
            mime='application/octet-stream', kind='file', expiresAt=time.time() * 1000 + 7200000)),
        message('qa-reply', **{'from': 'alice'}, text=m.chat_state.make_reply(
            'Bob', 'Does this fit the outer cowling?', 'Yes, the updated parts line up correctly.')),
    ]
    window.messages = preview_messages
    window._draw_messages()
    for width in (280, 340, 420):
        window.resize(width, 300)
        inspect_width(window, 'mini-resize-' + str(width), width)
        check(window.grab().save(str(ROOT / 'tests/.artifacts' / f'chat_width36_{width}_mixed.png')),
              f'Could not save {width}px screenshot')
    window.messages = [cases[6][1]]
    window._draw_messages()
    for width in (420, 280, 340):
        window.resize(width, 300)
        inspect_width(window, 'image-resize-' + str(width), width)
        for label in window.media_labels.get('image', []):
            pixmap = label.pixmap()
            check(pixmap is not None and pixmap.width() <= label.width(),
                  f'Expanded image exceeds label at {width}px')
    check(window.grab().save(str(ROOT / 'tests/.artifacts/chat_width36_340_image.png')), 'Could not save image screenshot')
    window.mini_action.setChecked(False)
    window.resize(800, 600)
    window.messages = preview_messages + [cases[6][1]]
    window._draw_messages()
    inspect_width(window, 'full-resize', 800)
    check(window.grab().save(str(ROOT / 'tests/.artifacts/chat_width36_800_full.png')), 'Could not save full screenshot')
    # Exercise the dropdown command route without opening native windows or
    # reading a real account. The watcher must reopen the existing mini window.
    window.mini_action.setChecked(True)
    window.resize(340, 300)
    window._collapse(True)
    command = folder / 'messenger-command.new'
    command.write_text(json.dumps({'action': 'TOOLBAR', 'target': None,
                                   'anchor': {'x': .4, 'bottom': .2}}))
    os.replace(command, folder / 'messenger-command.json')
    settle()
    check(window.isVisible() and window.mini and not window.collapsed, 'Toolbar command did not reopen mini chat')
    check(window._toolbar_anchor == {'x': .4, 'bottom': .2}, 'Toolbar command lost its anchor')
    inspect_width(window, 'toolbar-dropdown', 340)
    window.close()
    settle()

result = dict(cases=metrics, failures=failures, networkDisabled=True)
artifact = ROOT / 'tests/.artifacts' / ('chat_width36_' + LABEL + '.json')
artifact.write_text(json.dumps(result, indent=2))
for failure in failures:
    print('FAIL:', failure)
assert not failures, f'{len(failures)} failures; see {artifact}'
print('CHAT_MESSAGE_WIDTH_PASS')
