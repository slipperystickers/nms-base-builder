"""Standalone, responsive BBE messenger using the extension's bundled Qt.

The window may open offline; chat requests require explicit enablement. The private
recovery key is read from the existing profile file, never put on a command line.
"""

import json
import hashlib
import math
import os
from pathlib import Path
import secrets
import re
import sys
import tempfile
import threading
import time


def _load_qt():
    # Blender installs extension wheels here; -I excludes this user site path.
    sys.path.insert(0, sys.argv[1])
    from PySide6 import QtCore, QtGui, QtNetwork, QtWidgets
    return QtCore, QtGui, QtNetwork, QtWidgets


QtCore, QtGui, QtNetwork, QtWidgets = _load_qt()
sys.path.insert(0, str(Path(__file__).resolve().parent))
import bbe_chat_helper as helper
import bbe_chat_state as chat_state
from bbe_chat_compact import CompactMessengerMixin
from bbe_chat_lifetime import BlenderLifetime

IMAGE_MIMES = {'image/png', 'image/jpeg', 'image/gif', 'image/webp'}
FILE_TYPES = 'Supported files (*.png *.jpg *.jpeg *.gif *.webp *.mp4 *.webm *.blend *.zip *.pdf *.json *.nmsbase *.nmsship *.nmsprefab *.txt *.log);;Images and video (*.png *.jpg *.jpeg *.gif *.webp *.mp4 *.webm);;Project files (*.blend *.zip *.json *.nmsbase *.nmsship *.nmsprefab);;Documents (*.pdf *.txt *.log)'
MEDIA_SUFFIXES = {'.png', '.jpg', '.jpeg', '.gif', '.webp', '.mp4', '.webm'}


class TaskSignals(QtCore.QObject):
    finished = QtCore.Signal(object, object)


class Task(QtCore.QRunnable):
    def __init__(self, function):
        super().__init__()
        self.function = function
        self.signals = TaskSignals()

    def run(self):
        try:
            value, error = self.function(), None
        except Exception as exc:
            value, error = None, str(exc)
        self.signals.finished.emit(value, error)


class Composer(QtWidgets.QTextEdit):
    send_requested = QtCore.Signal()
    image_pasted = QtCore.Signal(QtGui.QImage)
    image_file_pasted = QtCore.Signal(object)

    def canInsertFromMimeData(self, source):
        return source.hasImage() or source.hasFormat('image/png') or source.hasUrls() or source.hasText()

    def insertFromMimeData(self, source):
        # Prefer a copied local image file over an optional bitmap preview so
        # its original type (including animated GIF) is retained.
        if source.hasUrls() and len(source.urls()) == 1:
            url = source.urls()[0]
            if url.isLocalFile():
                path = Path(url.toLocalFile())
                if path.suffix.lower() in {'.png', '.jpg', '.jpeg', '.gif', '.webp'}:
                    self.image_file_pasted.emit(path)
                    return
        # QTextEdit's default image paste embeds an image in its rich-text
        # document; toPlainText() cannot send that image. Queue it through the
        # normal attachment path instead, including Windows screenshot/DIB data.
        if source.hasImage():
            data = source.imageData()
            image = data.toImage() if isinstance(data, QtGui.QPixmap) else QtGui.QImage(data)
            if not image.isNull():
                self.image_pasted.emit(image)
                return
        if source.hasFormat('image/png'):
            image = QtGui.QImage.fromData(source.data('image/png'), 'PNG')
            if not image.isNull():
                self.image_pasted.emit(image)
                return
        if source.hasText():
            self.insertPlainText(source.text())

    def keyPressEvent(self, event):
        if event.key() in (QtCore.Qt.Key_Return, QtCore.Qt.Key_Enter) and not (event.modifiers() & QtCore.Qt.ShiftModifier):
            self.send_requested.emit()
            event.accept()
            return
        super().keyPressEvent(event)


class StatusLabel(QtWidgets.QLabel):
    changed = QtCore.Signal()

    def setText(self, text):
        super().setText(text)
        self.changed.emit()


class MessageLabel(QtWidgets.QLabel):
    """Use lightweight labels for ordinary text that can wrap between words."""
    def __init__(self, text, **kwargs):
        super().__init__(text, **kwargs)
        self.setTextFormat(QtCore.Qt.PlainText)
        self.setWordWrap(True)

    def minimumSizeHint(self):
        hint = super().minimumSizeHint()
        hint.setWidth(0)
        return hint

    def resizeEvent(self, event):
        super().resizeEvent(event)
        height = self.heightForWidth(event.size().width())
        if height >= 0 and self.minimumHeight() != height:
            self.setMinimumHeight(height)


class UnbrokenMessageText(QtWidgets.QTextBrowser):
    """Read-only text that wraps unbroken names/URLs without changing their text."""
    def __init__(self, text, **kwargs):
        super().__init__(**kwargs)
        self.setFrameShape(QtWidgets.QFrame.NoFrame)
        self.setStyleSheet('QTextBrowser { background: transparent; border: 0; padding: 0; margin: 0; }')
        self.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        for bar in (self.horizontalScrollBar(), self.verticalScrollBar()):
            bar.rangeChanged.connect(lambda low, high, bar=bar: bar.setRange(0, 0) if low or high else None)
        self.setWordWrapMode(QtGui.QTextOption.WrapAtWordBoundaryOrAnywhere)
        self.setTextInteractionFlags(QtCore.Qt.TextSelectableByMouse)
        self.setOpenLinks(False)
        self.document().setDocumentMargin(0)
        self.setPlainText(text)
        self.setSizePolicy(QtWidgets.QSizePolicy.Preferred, QtWidgets.QSizePolicy.Preferred)

    def sizeHint(self):
        width = min(480, max((self.fontMetrics().horizontalAdvance(line)
                             for line in self.toPlainText().splitlines()), default=0))
        return QtCore.QSize(width, max(self.fontMetrics().height(), self.minimumHeight()))

    def minimumSizeHint(self):
        return QtCore.QSize(0, self.minimumHeight())

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.document().setTextWidth(max(1, self.viewport().width()))
        height = math.ceil(self.document().documentLayout().documentSize().height())
        height += self.height() - self.viewport().height()
        if self.height() != height or self.minimumHeight() != height:
            self.setFixedHeight(height)

    def wheelEvent(self, event):
        event.ignore()  # Scroll the outer history, never inside an individual bubble.


def message_label(text, **kwargs):
    metrics = QtGui.QFontMetrics(QtWidgets.QApplication.font())
    # Reserve space for the reply button and padding even at the narrowest mini size.
    kind = UnbrokenMessageText if any(metrics.horizontalAdvance(word) > 120 for word in text.split()) else MessageLabel
    return kind(text, **kwargs)


class ElidedButton(QtWidgets.QPushButton):
    """Keep long attachment/reply captions from widening a compact window."""
    def __init__(self, text='', **kwargs):
        super().__init__(text, **kwargs)
        self.setSizePolicy(QtWidgets.QSizePolicy.Ignored, QtWidgets.QSizePolicy.Fixed)

    def paintEvent(self, event):
        option = QtWidgets.QStyleOptionButton()
        self.initStyleOption(option)
        rect = self.style().subElementRect(QtWidgets.QStyle.SE_PushButtonContents, option, self)
        option.text = self.fontMetrics().elidedText(self.text(), QtCore.Qt.ElideMiddle, max(0, rect.width()-12))
        painter = QtWidgets.QStylePainter(self)
        painter.drawControl(QtWidgets.QStyle.CE_PushButton, option)


class ConversationDelegate(QtWidgets.QStyledItemDelegate):
    """Keep native compact list selection, with a close target for each DM."""
    def __init__(self, owner):
        super().__init__(owner.rooms)
        self.owner = owner

    @staticmethod
    def close_rect(rect):
        return QtCore.QRect(rect.right()-24, rect.top(), 24, rect.height())

    def paint(self, painter, option, index):
        styled = QtWidgets.QStyleOptionViewItem(option)
        self.initStyleOption(styled, index)
        if index.data(QtCore.Qt.UserRole):
            styled.text = styled.fontMetrics.elidedText(styled.text, QtCore.Qt.ElideRight, max(0, styled.rect.width()-42))
        option.widget.style().drawControl(QtWidgets.QStyle.CE_ItemViewItem, styled, painter, option.widget)
        if index.data(QtCore.Qt.UserRole):
            painter.save()
            painter.setPen(styled.palette.color(QtGui.QPalette.HighlightedText if styled.state & QtWidgets.QStyle.State_Selected else QtGui.QPalette.Text))
            painter.drawText(self.close_rect(styled.rect), QtCore.Qt.AlignCenter, '×')
            painter.restore()

    def editorEvent(self, event, model, option, index):
        if (index.data(QtCore.Qt.UserRole) and event.type() in (QtCore.QEvent.MouseButtonPress, QtCore.QEvent.MouseButtonRelease)
                and event.button() == QtCore.Qt.LeftButton and self.close_rect(option.rect).contains(event.position().toPoint())):
            if event.type() == QtCore.QEvent.MouseButtonRelease:
                self.owner.close_conversation(index.data(QtCore.Qt.UserRole))
            return True
        return super().editorEvent(event, model, option, index)

    def helpEvent(self, event, view, option, index):
        if index.data(QtCore.Qt.UserRole) and self.close_rect(option.rect).contains(event.pos()):
            QtWidgets.QToolTip.showText(event.globalPos(), 'Close conversation (history is kept)', view)
            return True
        return super().helpEvent(event, view, option, index)


class Messenger(CompactMessengerMixin, QtWidgets.QMainWindow):
    transfer_progress = QtCore.Signal(object)

    def __init__(self, identity_path, settings_path, snapshot_dir, *, prewarm=False):
        super().__init__()
        if prewarm:
            self.setAttribute(QtCore.Qt.WA_DontShowOnScreen, True)
        self.setAttribute(QtCore.Qt.WA_TranslucentBackground)
        self.identity_path = Path(identity_path)
        self.settings_path = Path(settings_path)
        self.window_path = self.settings_path.with_name('bbe_messenger_window.json')
        self.snapshot_dir = Path(snapshot_dir)
        self.closed_conversations = chat_state.load(self.snapshot_dir/'closed-conversations.json')
        self.identity = json.loads(self.identity_path.read_text(encoding='utf-8'))
        self.secret = self.identity['secret']
        self.persona = self.identity.get('id')
        self.names = self.identity.get('names', [])
        self.target = None
        self.online = []
        self.contacts = []
        self.messages = []
        self.message_ids = ()
        self.message_generation = 0
        self.media_cache = {}
        self.media_loading = set()
        self.media_labels = {}
        self.media_buttons = {}
        self.message_frames = []
        self.expanded_media = set()
        self.active_file = None
        self.capabilities = {}
        self.pending = None
        self.reply_to = None
        self._follow_latest = True
        self.pending_owned = False
        self.pending_preserve_alpha = False
        self.snapshot_id = None
        self.snapshot_at = 0
        self.syncing = False
        self.sending = False
        self.transfer_cancel = None
        self.transfer_id = None
        self.transfer_progress.connect(self._transfer_progress)
        self.claiming = False
        self.account_dialog = None
        self.jobs = set()
        self.pool = QtCore.QThreadPool(self)
        self.pool.setMaxThreadCount(3)
        self.media_pool = QtCore.QThreadPool(self)
        self.media_pool.setMaxThreadCount(2)
        self.setWindowTitle('BBE Messenger')
        self.mini = False
        self._full_size = QtCore.QSize(940, 680)
        self.setMinimumSize(320, 260)
        self.resize(940, 680)
        self._theme_signature = None
        self._apply_theme()
        self._build_ui()
        self._init_compact()
        self._notifications = chat_state.load(self.snapshot_dir/'notifications.json')
        if self._notifications.get('persona') != self.persona:
            self._notifications = {}
        self.unread = self._notifications.setdefault('unread', {})
        self._last_received = chat_state.latest_received(self._notifications, self.target)
        self._seen_inbox = self._notifications.get('seen')
        if not self._enabled():
            self.status.setText('Chat is off. Enable it in account settings to join.')
            self.online_label.setText('  Chat is off')
        elif not self.persona:
            self.status.setText('Claim a name in account settings to join.')
            self.online_label.setText('  Not connected')
        self._restore_window()
        if prewarm:
            self.hide()
            self.setAttribute(QtCore.Qt.WA_DontShowOnScreen, False)
        self.timer = QtCore.QTimer(self)
        self.timer.timeout.connect(self._periodic)
        self.timer.start(5000)
        self.snapshot_timer = QtCore.QTimer(self)
        self.snapshot_timer.timeout.connect(self._check_snapshot)
        self.snapshot_timer.start(350)
        QtCore.QTimer.singleShot(0, self.sync)
        if not self.persona or not self._enabled():
            QtCore.QTimer.singleShot(0, self.show_account_settings)

    def _build_ui(self):
        root = QtWidgets.QWidget(objectName="chatRoot")
        self.setCentralWidget(root)
        horizontal = QtWidgets.QHBoxLayout(root)
        horizontal.setContentsMargins(0, 0, 0, 0)
        horizontal.setSpacing(0)

        side = QtWidgets.QFrame(objectName='side')
        self.sidebar = side
        side.setFixedWidth(232)
        s = QtWidgets.QVBoxLayout(side)
        s.setContentsMargins(12, 14, 12, 12)
        s.setSpacing(8)
        s.addWidget(QtWidgets.QLabel('Chatting as', objectName='sectionLabel'))
        identity_row = QtWidgets.QHBoxLayout()
        self.persona_box = QtWidgets.QComboBox()
        for item in self.names:
            self.persona_box.addItem(item['name'], item['id'])
        index = self.persona_box.findData(self.persona)
        self.persona_box.setCurrentIndex(max(0, index))
        self.persona_box.currentIndexChanged.connect(self._switch_persona)
        identity_row.addWidget(self.persona_box, 1)
        account_button = QtWidgets.QToolButton()
        account_button.setText('⚙')
        account_button.setFont(QtGui.QFont('Segoe UI Symbol', 14))
        account_button.setToolTip('Chat and account settings')
        account_button.setFixedSize(30, 30)
        account_button.clicked.connect(self.show_account_settings)
        identity_row.addWidget(account_button)
        s.addLayout(identity_row)
        s.addWidget(QtWidgets.QLabel('Conversations', objectName='sectionLabel'))
        self.rooms = QtWidgets.QListWidget(objectName='conversationList')
        self.rooms.setItemDelegate(ConversationDelegate(self))
        self.rooms.currentItemChanged.connect(self._select_room)
        self.rooms.setMinimumHeight(0)
        s.addWidget(self.rooms)
        self.online_label = QtWidgets.QLabel('Online users: connecting...', objectName='sectionLabel')
        s.addWidget(self.online_label)
        self.dm_hint = QtWidgets.QLabel('Click a name to start a DM', objectName='hint')
        self.dm_hint.setWordWrap(True)
        s.addWidget(self.dm_hint)
        self.online_users = QtWidgets.QListWidget(objectName='onlineList')
        self.online_users.currentItemChanged.connect(self._select_online_user)
        for listing in (self.rooms, self.online_users):
            listing.setUniformItemSizes(True)
            listing.setWordWrap(False)
            listing.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
            listing.setVerticalScrollMode(QtWidgets.QAbstractItemView.ScrollPerPixel)
        s.addWidget(self.online_users, 1)
        horizontal.addWidget(side)

        main = QtWidgets.QFrame(objectName='chatSurface')
        m = QtWidgets.QVBoxLayout(main)
        self.main_layout = m
        m.setContentsMargins(18, 13, 18, 12)
        m.setSpacing(10)
        self.heading = QtWidgets.QLabel('Main Room', objectName='heading')
        header = QtWidgets.QHBoxLayout()
        self.header_layout = header
        header.addWidget(self.heading, 1)
        self.chat_enabled_toggle = QtWidgets.QCheckBox('Enable chat')
        self.chat_enabled_toggle.setChecked(self._settings().get('enabled') is True)
        self.chat_enabled_toggle.setEnabled(self._settings().get('online_access', True))
        self.chat_enabled_toggle.setToolTip('Turn chat off without giving up your names')
        self.chat_enabled_toggle.toggled.connect(self._set_enabled)
        header.addWidget(self.chat_enabled_toggle)
        self.options_button = QtWidgets.QToolButton()
        self.options_button.setText('...')
        self.options_button.setFixedWidth(32)
        self.options_button.setToolTip('Mini mode, sidebar, pin and attachments')
        self.options_button.setPopupMode(QtWidgets.QToolButton.InstantPopup)
        menu = QtWidgets.QMenu(self.options_button)
        menu.addAction('Chat & account settings...', self.show_account_settings)
        menu.addAction('How to use BBE Chat', self.show_chat_help)
        menu.addSeparator()
        self.mini_action = menu.addAction('Mini mode')
        self.mini_action.setCheckable(True)
        self.mini_action.toggled.connect(self._set_mini)
        self.sidebar_action = menu.addAction('Show users and conversations')
        self.sidebar_action.setCheckable(True)
        self.sidebar_action.setChecked(True)
        self.sidebar_action.toggled.connect(self._set_sidebar)
        self.pin_action = menu.addAction('Always on top')
        self.pin_action.setCheckable(True)
        self.pin_action.toggled.connect(self._set_pin)
        menu.addSeparator()
        menu.addAction('Snapshot', self.snapshot)
        menu.addAction('Attach file, image or video', self.attach)
        menu.addAction('Remove queued attachment', self.clear_attachment)
        self.cancel_transfer_action = menu.addAction('Cancel file transfer', self.cancel_transfer)
        self.cancel_transfer_action.setEnabled(False)
        self.remove_shared_action = menu.addAction('Remove my shared file', self.remove_shared_file)
        self.remove_shared_action.setEnabled(False)
        menu.addSeparator()
        placement = menu.addMenu('Attach Mini to Blender')
        for key, label in (('toolbar', 'In BBE toolbar'), ('top-left', 'Top left'), ('top-right', 'Top right'),
                           ('bottom-left', 'Bottom left'), ('bottom-right', 'Bottom right'),
                           ('top', 'Top bar'), ('bottom', 'Bottom bar'), ('floating', 'Floating')):
            placement.addAction(label, lambda checked=False, value=key: self._dock(value))
        menu.addSeparator()
        menu.addAction('Close Messenger', self.close)
        self.options_button.setMenu(menu)
        header.addWidget(self.options_button)
        help_button = QtWidgets.QToolButton()
        help_button.setText('?')
        help_button.setToolTip('How to use BBE Chat')
        help_button.setAccessibleName('How to use BBE Chat')
        help_button.clicked.connect(self.show_chat_help)
        header.addWidget(help_button)
        self.header_extras = []
        mini_button = QtWidgets.QPushButton('Mini')
        mini_button.setToolTip('Show only messages and the message field')
        mini_button.clicked.connect(lambda: self.mini_action.setChecked(True))
        header.addWidget(mini_button)
        self.header_extras.append(mini_button)
        self.pin_button = QtWidgets.QPushButton('Always on top')
        self.pin_button.setCheckable(True)
        self.pin_button.setToolTip('Keep Messenger above Blender while you work')
        self.pin_button.toggled.connect(self._set_pin)
        header.addWidget(self.pin_button)
        self.header_extras.append(self.pin_button)
        for label, side in (('Dock left', 'left'), ('Dock right', 'right')):
            button = QtWidgets.QPushButton(label)
            button.setToolTip('Place Messenger beside Blender; drag its edge to resize')
            button.clicked.connect(lambda _checked=False, value=side: self._dock(value))
            header.addWidget(button)
            self.header_extras.append(button)
        m.addLayout(header)
        self.scroll = QtWidgets.QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        self.message_container = QtWidgets.QWidget()
        self.message_layout = QtWidgets.QVBoxLayout(self.message_container)
        self.message_layout.setAlignment(QtCore.Qt.AlignTop)
        self.message_layout.setSizeConstraint(QtWidgets.QLayout.SetMinAndMaxSize)
        self.message_layout.setSpacing(9)
        self.scroll.setWidget(self.message_container)
        self.scroll.verticalScrollBar().rangeChanged.connect(lambda *_: self._scroll_to_latest())
        self.scroll.verticalScrollBar().actionTriggered.connect(
            lambda *_: QtCore.QTimer.singleShot(0, self._user_scrolled))
        self.scroll.viewport().installEventFilter(self)
        self.history_region = QtWidgets.QWidget(objectName='historyRegion')
        history = QtWidgets.QHBoxLayout(self.history_region)
        history.setContentsMargins(0, 0, 0, 0)
        history.addWidget(self.scroll)
        m.addWidget(self.history_region, 1)
        self.preview = QtWidgets.QLabel('')
        self.preview.hide()
        m.addWidget(self.preview)
        self.composer = Composer()
        self.composer.setPlaceholderText('Write a message. Enter sends; Shift+Enter makes a new line.')
        self.composer.setAcceptRichText(False)
        self.composer.setToolTip('Ctrl+V pastes text or queues an image attachment. Enter sends; Shift+Enter adds a new line.')
        self.composer.setFixedHeight(75)
        self.composer.send_requested.connect(self.send)
        self.composer.image_pasted.connect(self._paste_image)
        self.composer.image_file_pasted.connect(lambda path: self._stage(path, owned=False))
        self.composer_row = QtWidgets.QWidget(objectName='composerRow')
        composer_layout = QtWidgets.QHBoxLayout(self.composer_row)
        composer_layout.setContentsMargins(0, 0, 0, 0)
        composer_layout.setSpacing(5)
        self.attach_button = QtWidgets.QToolButton(objectName='composerAction')
        self.attach_button.setText('+')
        self.attach_button.setToolTip('Attach a snapshot, image, video or file')
        self.attach_button.setAccessibleName('Add attachment')
        self.attach_button.setFixedSize(30, 36)
        self.attach_button.setPopupMode(QtWidgets.QToolButton.InstantPopup)
        self.attachment_menu = QtWidgets.QMenu(self.attach_button)
        self.attachment_menu.addAction('Blender snapshot', self.snapshot)
        self.attachment_menu.addSeparator()
        for label, kind in (('Image…', 'image'), ('Video…', 'video'), ('File…', 'file')):
            self.attachment_menu.addAction(label, lambda checked=False, value=kind: self.attach(value))
        self.attach_button.setMenu(self.attachment_menu)
        composer_layout.addWidget(self.attach_button)
        composer_layout.addWidget(self.composer, 1)
        self.emoji_button = QtWidgets.QToolButton(objectName='composerAction')
        self.emoji_button.setText('☺')
        self.emoji_button.setFont(QtGui.QFont('Segoe UI Symbol', 18))
        self.emoji_button.setToolTip('Insert an emoji')
        self.emoji_button.setAccessibleName('Emoji picker')
        self.emoji_button.setFixedSize(30, 36)
        self.emoji_button.setPopupMode(QtWidgets.QToolButton.InstantPopup)
        self.emoji_menu = QtWidgets.QMenu(self.emoji_button)
        picker = QtWidgets.QWidget()
        emoji_layout = QtWidgets.QGridLayout(picker)
        emoji_layout.setContentsMargins(8, 8, 8, 8)
        emoji_layout.setSpacing(4)
        self.emoji_choices = []
        emojis = ('😀', '😄', '😂', '😍', '😎', '🤔', '😅', '😭', '😮', '😴', '👍', '👎',
                  '👋', '🙏', '💪', '❤️', '🎉', '🔥', '✨', '🚀', '🛠️', '✅', '❓', '👀')
        for index, emoji in enumerate(emojis):
            button = QtWidgets.QPushButton(emoji, objectName='emojiChoice')
            button.setFixedSize(36, 36)
            button.clicked.connect(lambda checked=False, value=emoji: self._insert_emoji(value))
            emoji_layout.addWidget(button, index//6, index%6)
            self.emoji_choices.append(button)
        emoji_action = QtWidgets.QWidgetAction(self.emoji_menu)
        emoji_action.setDefaultWidget(picker)
        self.emoji_menu.addAction(emoji_action)
        self.emoji_button.setMenu(self.emoji_menu)
        composer_layout.addWidget(self.emoji_button)
        self.reply_banner = ElidedButton()
        self.reply_banner.setToolTip('Click to cancel this reply')
        self.reply_banner.clicked.connect(self.cancel_reply)
        self.reply_banner.hide()
        m.addWidget(self.reply_banner)
        m.addWidget(self.composer_row)
        tools = QtWidgets.QHBoxLayout()
        self.snapshot_button = QtWidgets.QPushButton('Snapshot')
        self.snapshot_button.clicked.connect(self.snapshot)
        tools.addWidget(self.snapshot_button)
        attach = QtWidgets.QPushButton('Attach file, image or video')
        attach.clicked.connect(self.attach)
        tools.addWidget(attach)
        self.remove_button = QtWidgets.QPushButton('Remove file')
        self.remove_button.clicked.connect(self.clear_attachment)
        self.remove_button.hide()
        tools.addWidget(self.remove_button)
        tools.addStretch()
        self.tools_widget = QtWidgets.QWidget()
        self.tools_widget.setLayout(tools)
        tools.setContentsMargins(0, 0, 0, 0)
        m.addWidget(self.tools_widget)
        send_row = QtWidgets.QHBoxLayout()
        self.optimize = QtWidgets.QCheckBox('Send smaller images')
        self.optimize.setChecked(True)
        send_row.addWidget(self.optimize)
        send_row.addStretch()
        self.send_button = QtWidgets.QPushButton('Send', objectName='send')
        self.send_button.clicked.connect(self.send)
        send_row.addWidget(self.send_button)
        self.send_widget = QtWidgets.QWidget()
        self.send_widget.setLayout(send_row)
        send_row.setContentsMargins(0, 0, 0, 0)
        m.addWidget(self.send_widget)
        self.status = StatusLabel('Connecting...')
        self.status.setWordWrap(True)
        self.status.changed.connect(self._update_status_visibility)
        m.addWidget(self.status)
        horizontal.addWidget(main, 1)
        self._draw_rooms()

    def _settings(self):
        try:
            data = json.loads(self.settings_path.read_text(encoding='utf-8'))
            return data if isinstance(data, dict) else {}
        except (OSError, ValueError):
            return {}

    def _apply_theme(self):
        palette = self._settings().get('theme', {})
        defaults = {'background': '#202020', 'surface': '#303030', 'raised': '#4c4c4c',
                    'text': '#e5e5e5', 'accent': '#4772b3', 'outline': '#181818'}
        colors = {key: value if isinstance(value, str) and len(value) == 7 and
                  value.startswith('#') and all(c in '0123456789abcdefABCDEF' for c in value[1:])
                  else defaults[key] for key, value in ((k, palette.get(k)) for k in defaults)}
        signature = tuple(colors.values())
        if signature == self._theme_signature:
            return
        self._theme_signature = signature
        bg, surface, raised, text, accent, outline = signature
        self.setStyleSheet(f'''
            QMainWindow, QWidget {{ background: {bg}; color: {text}; font-size: 12px; }}
            QMainWindow, QWidget#chatRoot {{ background: transparent; }}
            QFrame#side {{ background: {bg}; border: 1px solid {raised}; border-radius: 14px; }}
            QFrame#side QLabel {{ background: transparent; }}
            QLabel#sectionLabel {{ font-weight: bold; padding: 5px 0 2px; }}
            QLabel#hint {{ color: {text}; font-size: 11px; padding: 0 2px; }}
            QDialog#peopleDrawer {{ background: transparent; }}
            QFrame#chatSurface {{ border: 1px solid {outline}; border-radius: 10px; }}
            QToolButton {{ background: {surface}; color: {text}; border: 1px solid {outline};
                           border-radius: 7px; padding: 2px; }}
            QToolButton:hover {{ background: {raised}; border-color: {accent}; }}
            QToolButton::menu-indicator {{ image: none; width: 0px; }}
            QToolButton#composerAction {{ font-size: 22px; padding: 0; }}
            QToolButton#peopleHandle {{ padding: 0; background: {raised};
                                       border: 1px solid {accent}; border-radius: 10px; }}
            QMenu {{ background: {bg}; color: {text}; border: 1px solid {raised}; padding: 5px; }}
            QMenu::item {{ padding: 7px 12px; border-radius: 6px; }}
            QMenu::item:selected {{ background: {accent}; color: white; }}
            QPushButton#emojiChoice {{ font-family: "Segoe UI Emoji"; font-size: 22px; padding: 0; }}
            QComboBox {{ background: {surface}; border: 1px solid {outline}; border-radius: 7px; padding: 6px; }}
            QLabel#heading {{ font-size: 17px; font-weight: bold; color: {text}; }}
            QListWidget, QTextEdit {{ background: {surface}; color: {text};
                border: 1px solid {outline}; border-radius: 6px; }}
            QFrame#side QListWidget {{ background: transparent; border: 0; outline: 0; }}
            QListWidget::item {{ padding: 4px 7px; margin: 1px 0; border-radius: 5px; background: {surface}; }}
            QListWidget#onlineList::item {{ padding: 2px 7px; margin: 0; border-radius: 4px; background: transparent; }}
            QListWidget::item:hover {{ background: {raised}; }}
            QListWidget::item:selected {{ background: {accent}; color: white; }}
            QListWidget#onlineList::item:hover {{ background: {raised}; }}
            QListWidget#onlineList::item:selected {{ background: {accent}; color: white; }}
            QPushButton {{ background: {raised}; color: {text}; border: 1px solid {outline};
                           border-radius: 5px; padding: 6px 10px; }}
            QPushButton:hover {{ border: 1px solid {accent}; }}
            QPushButton:checked, QPushButton#send {{ background: {accent}; color: white;
                                                     font-weight: bold; }}
            QPushButton:disabled {{ color: {outline}; }}
            QFrame#message {{ background: {surface}; border: 1px solid {outline}; border-radius: 8px; }}
            QLabel#sender, QTextBrowser#sender {{ font-weight: bold; color: {accent}; }}
            QLabel#attachment {{ background: {raised}; border: 1px solid {outline}; border-radius: 5px; }}
            QScrollArea {{ border: 0; background: {bg}; }}
            QFrame#message QLabel {{ background: transparent; }}
            QScrollBar:vertical {{ background: {bg}; width: 7px; margin: 0; border: 0; }}
            QScrollBar::handle:vertical {{ background: {raised}; min-height: 24px; border-radius: 3px; }}
            QScrollBar::handle:vertical:hover {{ background: {accent}; }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{ background: transparent; }}
            QComboBox, QCheckBox {{ color: {text}; }}
        ''')

    def _restore_window(self):
        try:
            data = json.loads(self.window_path.read_text(encoding='utf-8'))
        except (OSError, ValueError, TypeError):
            data = {}
        if not isinstance(data, dict):
            data = {}
        migrate = data.get('layout_version') != 2
        self.mini_action.setChecked(True if migrate else data.get('mini', True) is True)
        self.sidebar_action.setChecked(data.get('sidebar', not self.mini) is True)
        geometry = QtCore.QByteArray.fromBase64(str(data.get('geometry', '')).encode('ascii', 'ignore'))
        if geometry:
            self.restoreGeometry(geometry)
        # Earlier versions saved their default false as if the user chose it.
        # Migrate once; subsequent explicit choices always win.
        self._set_pin(data.get('pin', True) is True if data.get('pin_preference_version') == 1 else True)
        self.dock_mode = 'toolbar' if migrate else data.get('dock', 'toolbar')
        size = data.get('mini_size', [340, 300])
        if isinstance(size, list) and len(size) == 2 and all(isinstance(v, int) for v in size):
            self._mini_size = QtCore.QSize(max(280, min(1000, size[0])), max(180, min(1000, size[1])))
        if self.mini:
            self.resize(self._mini_size)
            self._collapse(True if migrate else data.get('collapsed', True) is True)
            self._place_attached()

    def _update_status_visibility(self):
        text = self.status.text()
        self.options_button.setToolTip('Chat options · ' + text)
        self.status.setVisible(not getattr(self, 'collapsed', False) and (not self.mini or text not in ('Connected', 'Sent', 'Connecting...', '')))

    def _job(self, function, done, *, media=False):
        task = Task(function)
        self.jobs.add(task)

        def finish(value, error):
            self.jobs.discard(task)
            if not self._closing:
                done(value, error)

        task.signals.finished.connect(finish)
        (self.media_pool if media else self.pool).start(task)

    def _enabled(self):
        settings = self._settings()
        return settings.get('enabled') is True and settings.get('online_access', True) is True

    def _set_enabled(self, enabled):
        if enabled and not self._settings().get('online_access', True):
            self.status.setText('Enable Online Access in Blender Preferences first')
            return
        settings = self._settings()
        settings['enabled'] = bool(enabled)
        temporary = self.settings_path.with_suffix('.messenger-new')
        try:
            temporary.write_text(json.dumps(settings), encoding='utf-8')
            os.replace(temporary, self.settings_path)
        except OSError as exc:
            self.status.setText('Could not save chat setting: ' + str(exc))
            return
        self.message_generation += 1
        if not enabled:
            self.cancel_transfer()
            self.online = []
            self.online_label.setText('  Chat is off')
            self._draw_rooms()
            self.status.setText('Chat is off. Your names and draft are kept.')
            if self.mini and self.dock_mode == 'toolbar':
                self._collapse(True)
        else:
            self.status.setText('Connecting...' if self.persona else 'Claim a name to join.')
            self.sync()
        self.chat_enabled_toggle.blockSignals(True)
        self.chat_enabled_toggle.setChecked(bool(enabled))
        self.chat_enabled_toggle.blockSignals(False)

    def show_chat_help(self):
        message = '\n\n'.join(heading + '\n' + body for heading, body in chat_state.CHAT_HELP)
        QtWidgets.QMessageBox.information(self, 'How to use BBE Chat', message)

    def show_account_settings(self):
        if self.account_dialog and self.account_dialog.isVisible():
            self.account_dialog.raise_()
            return
        dialog = QtWidgets.QDialog(self)
        self.account_dialog = dialog
        dialog.setWindowTitle('Chat & account settings')
        dialog.setMinimumWidth(360)
        layout = QtWidgets.QVBoxLayout(dialog)
        enabled = QtWidgets.QCheckBox('Enable chat')
        enabled.setChecked(self._settings().get('enabled') is True)
        enabled.setEnabled(self._settings().get('online_access', True))
        enabled.toggled.connect(self._set_enabled)
        layout.addWidget(enabled)
        hint = QtWidgets.QLabel('Chat is optional. Your names stay reserved when it is off.' if enabled.isEnabled()
                               else 'Enable Online Access in Blender Preferences to connect.')
        hint.setWordWrap(True)
        layout.addWidget(hint)
        layout.addWidget(QtWidgets.QLabel('Your names (up to 3)'))
        personas = QtWidgets.QComboBox()
        for item in self.names:
            personas.addItem(item['name'], item['id'])
        personas.setCurrentIndex(max(0, personas.findData(self.persona)))
        personas.currentIndexChanged.connect(lambda: self.persona_box.setCurrentIndex(
            self.persona_box.findData(personas.currentData())))
        layout.addWidget(personas)
        name = QtWidgets.QLineEdit()
        name.setPlaceholderText('Name to claim or restore (2–24 characters)')
        name.setMaxLength(24)
        layout.addWidget(name)
        claim = QtWidgets.QPushButton('Claim name')
        claim.clicked.connect(lambda: self._claim_name(name.text()))
        layout.addWidget(claim)
        copy = QtWidgets.QPushButton('Copy private recovery key')
        copy.setEnabled(bool(self.persona))
        copy.clicked.connect(self._copy_recovery_key)
        layout.addWidget(copy)
        key = QtWidgets.QLineEdit()
        key.setEchoMode(QtWidgets.QLineEdit.Password)
        key.setPlaceholderText('Recovery key to restore your names')
        layout.addWidget(key)
        restore = QtWidgets.QPushButton('Restore name with key')
        restore.clicked.connect(lambda: self._claim_name(name.text(), key.text()))
        layout.addWidget(restore)
        feedback = QtWidgets.QLabel(self.status.text())
        feedback.setWordWrap(True)
        layout.addWidget(feedback)
        update_feedback = lambda: feedback.setText(self.status.text())
        self.status.changed.connect(update_feedback)
        def finished(_result):
            self.status.changed.disconnect(update_feedback)
            if self.account_dialog is dialog:
                self.account_dialog = None
            dialog.deleteLater()
        dialog.finished.connect(finished)
        close = QtWidgets.QPushButton('Done')
        close.clicked.connect(dialog.accept)
        layout.addWidget(close)
        dialog.show()

    def _copy_recovery_key(self):
        QtWidgets.QApplication.clipboard().setText(self.secret)
        self.status.setText('Private recovery key copied. Keep it safe; do not post it in chat.')

    def _claim_name(self, name, recovery=None):
        if self.claiming or self.sending:
            self.status.setText('Wait for the current request to finish.')
            return
        if not self._enabled():
            self.status.setText('Enable chat in account settings first.')
            return
        name = name.strip()
        if not 2 <= len(name) <= 24:
            self.status.setText('Enter a name of 2–24 characters.')
            return
        secret = recovery.strip() if recovery is not None else self.secret
        if recovery is not None and not re.fullmatch(r'[A-Za-z0-9_-]{40,128}', secret):
            self.status.setText('Paste a valid recovery key.')
            return
        if self.persona and secret != self.secret:
            self.status.setText('This profile already owns names. Restore a different key in another Blender profile.')
            return
        if len(self.names) >= 3 and name.casefold() not in {item['name'].casefold() for item in self.names}:
            self.status.setText('This recovery key already owns three names.')
            return
        self.claiming = True
        self.message_generation += 1
        self.status.setText('Claiming name...')
        self._job(lambda: helper.run('claim', {'name': name, 'secret': secret}),
                  lambda value, error: self._claimed(value, error, secret))

    def _claimed(self, value, error, secret):
        self.claiming = False
        if error:
            self.status.setText(error)
            self._online_synced_at = float('-inf')
            return
        self.secret, self.persona = secret, value['id']
        self.names = value.get('names', [{'id': value['id'], 'name': value['name']}])
        self.identity.update(secret=secret, id=self.persona, name=value['name'], names=self.names, active=True)
        self._write_identity()
        self.persona_box.blockSignals(True)
        self.persona_box.clear()
        for item in self.names:
            self.persona_box.addItem(item['name'], item['id'])
        self.persona_box.setCurrentIndex(self.persona_box.findData(self.persona))
        self.persona_box.blockSignals(False)
        self.target, self.messages, self.message_ids = None, [], ()
        self.message_generation += 1
        self._draw_rooms()
        self._draw_messages()
        self.heading.setText('Main Room')
        self.status.setText('Name saved: ' + value['name'])
        if self.account_dialog and self.account_dialog.isVisible():
            self.account_dialog.close()
            self.show_account_settings()
        self.sync()

    def _write_identity(self):
        temporary = self.identity_path.with_suffix('.messenger-new')
        temporary.write_text(json.dumps(self.identity), encoding='utf-8')
        os.replace(temporary, self.identity_path)

    def _periodic(self):
        self._apply_theme()
        if not self._enabled():
            self.status.setText('Chat is off. Open account settings to enable it.')
            return
        self.sync()

    def sync(self):
        if self.syncing or self.claiming or not self.persona or not self._enabled():
            return
        self.syncing = True
        target, persona, generation = self.target, self.persona, self.message_generation
        known = [k for k,v in self._notifications.get('content',{}).items() if 'text' in v]
        self._job(lambda: helper.sync_chat({'secret': self.secret, 'as': persona, 'to': target, 'known_content': known}),
                  lambda value, error: self._synced(value, error, target, persona, generation))

    def _synced(self, value, error, target, persona, generation):
        self.syncing = False
        if not self._enabled() or self.claiming:
            return
        if error:
            self.status.setText(error)
            self._online_synced_at = float('-inf')
            return
        if target != self.target or persona != self.persona or generation != self.message_generation:
            self.sync()
            return
        self.capabilities = value.get('capabilities', {})
        self.active_file = value.get('activeFile')
        self.remove_shared_action.setEnabled(bool(self.active_file))
        self.remove_shared_action.setText('Remove shared file: ' + self.active_file['name'] if self.active_file else 'No active shared file')
        self.online = value.get('online', [])
        self._online_synced_at = time.monotonic()
        self.contacts = value.get('contacts', [])
        names = value.get('names', self.names)
        if names != self.names:
            self.names = names
            self.identity['names'] = names
            self._write_identity()
            self.persona_box.blockSignals(True)
            self.persona_box.clear()
            for item in names:
                self.persona_box.addItem(item['name'], item['id'])
            self.persona_box.setCurrentIndex(max(0, self.persona_box.findData(self.persona)))
            self.persona_box.blockSignals(False)
        online_count = sum(person['id'] != self.persona for person in self.online)
        self.online_label.setText(f'  Online users: {online_count}')
        self.dm_hint.setText('  Click a name to start a DM' if online_count
                             else '  Other builders will appear here')
        self._draw_rooms()
        messages = value.get('messages', [])
        ids = tuple((item['id'], item.get('text'), json.dumps(item.get('attachment'), sort_keys=True),
                     (item.get('attachment') or {}).get('expiresAt', float('inf')) <= time.time()*1000) for item in messages)
        self.messages = messages
        self._notify_inbox(value.get('inbox', []))
        if ids != getattr(self, '_render_signature', None):
            self._render_signature = ids
            self.message_ids = tuple(item['id'] for item in messages)
            self._draw_messages()
        if not self.sending and not self.transfer_cancel:
            self.status.setText('Connected')

    def _draw_rooms(self):
        positions = [listing.verticalScrollBar().value() for listing in (self.rooms, self.online_users)]
        self.rooms.blockSignals(True)
        self.online_users.blockSignals(True)
        self.rooms.clear()
        self.online_users.clear()
        main = QtWidgets.QListWidgetItem('●  Main Room' + (f" ({self.unread['main']})" if getattr(self, 'unread', {}).get('main') else ''))
        main.setData(QtCore.Qt.UserRole, '')
        self.rooms.addItem(main)
        online_ids = set()
        for person in self.online:
            if person['id'] == self.persona:
                continue
            item = QtWidgets.QListWidgetItem('●  ' + person['name'])
            item.setData(QtCore.Qt.UserRole, person['id'])
            item.setToolTip('Click to send ' + person['name'] + ' a direct message')
            self.online_users.addItem(item)
            online_ids.add(person['id'])
        for person in self.contacts:
            if person['id'] != self.persona and person['id'] not in self.closed_conversations.get(self.persona, {}):
                item = QtWidgets.QListWidgetItem(('●  ' if person['id'] in online_ids else '○  ') + person['name'])
                if self.unread.get(person['id']):
                    item.setText(item.text() + f" ({self.unread[person['id']]})")
                item.setData(QtCore.Qt.UserRole, person['id'])
                self.rooms.addItem(item)
        selected = False
        if self.target:
            for index in range(self.online_users.count()):
                if self.online_users.item(index).data(QtCore.Qt.UserRole) == self.target:
                    self.online_users.setCurrentRow(index)
                    selected = True
                    break
        for index in range(self.rooms.count()):
            if not selected and self.rooms.item(index).data(QtCore.Qt.UserRole) == (self.target or ''):
                self.rooms.setCurrentRow(index)
                break
        self.rooms.blockSignals(False)
        self.online_users.blockSignals(False)
        if getattr(self, 'mini', False):
            self._position_drawer()
        else:
            self.rooms.setMaximumHeight(max(1, min(8, self.rooms.count())) * max(26, self.rooms.sizeHintForRow(0)) + 4)
        for listing, position in zip((self.rooms, self.online_users), positions):
            listing.verticalScrollBar().setValue(position)

    def _select_room(self, current, _previous):
        if current is None:
            return
        self.online_users.blockSignals(True)
        self.online_users.clearSelection()
        self.online_users.setCurrentRow(-1)
        self.online_users.blockSignals(False)
        self._open_conversation(current.data(QtCore.Qt.UserRole) or None, current.text()[3:])

    def _select_online_user(self, current, _previous):
        if current is None:
            return
        self.rooms.blockSignals(True)
        self.rooms.clearSelection()
        self.rooms.setCurrentRow(-1)
        self.rooms.blockSignals(False)
        self._open_conversation(current.data(QtCore.Qt.UserRole), current.text()[3:])

    def _open_conversation(self, target, name):
        if target in self.closed_conversations.get(self.persona, {}):
            self.closed_conversations[self.persona].pop(target)
            chat_state.save(self.snapshot_dir/'closed-conversations.json', self.closed_conversations)
            self._draw_rooms()
        if target == self.target:
            return
        self.message_generation += 1
        self.cancel_reply()
        self.target = target
        self.unread.pop(target or 'main', None)
        self._notifications.get('directed', {}).pop(target or 'main', None)
        self._render_signature = None
        self._collapse(False)
        self.heading.setText('Main Room' if not target else 'Direct Message · ' + name)
        self.message_ids = ()
        self.messages = []
        self._update_badge()
        self._publish_toolbar_status()
        self._clear_messages()
        self.sync()

    def close_conversation(self, target):
        if not target:
            return
        self.closed_conversations.setdefault(self.persona, {})[target] = time.time()*1000
        chat_state.save(self.snapshot_dir/'closed-conversations.json', self.closed_conversations)
        self.unread.pop(target, None)
        self._notifications.get('directed', {}).pop(target, None)
        if self.target == target:
            self._open_conversation(None, 'Main Room')
        self._draw_rooms()
        self._update_badge()

    def _switch_persona(self):
        next_id = self.persona_box.currentData()
        if not next_id or next_id == self.persona:
            return
        self._seen_inbox = None
        self.cancel_reply()
        self._notifications = {}
        self._last_received = None
        self.unread.clear()
        self._render_signature = None
        self.message_generation += 1
        self.persona = next_id
        self.identity['id'] = next_id
        self.identity['name'] = self.persona_box.currentText()
        self.identity['active'] = True
        self._write_identity()
        self.target, self.message_ids = None, ()
        self._clear_messages()
        self.heading.setText('Main Room')
        self._draw_rooms()
        self.sync()

    def _clear_messages(self):
        def clear(layout):
            while layout.count():
                item = layout.takeAt(0)
                if item.widget():
                    item.widget().deleteLater()
                elif item.layout():
                    clear(item.layout())
                    item.layout().deleteLater()
        clear(self.message_layout)
        self.media_labels.clear()
        self.media_buttons.clear()
        self.message_frames.clear()

    def _draw_messages(self):
        self._remember_received(self.messages)
        self._update_badge()
        self._follow_latest = True
        self._clear_messages()
        if not self.messages:
            empty = message_label('No messages yet. Say hello!')
            self.message_layout.addWidget(empty)
        for index, message in enumerate(self.messages):
            frame = QtWidgets.QFrame(objectName='message')
            frame.setMaximumWidth(520)
            block = QtWidgets.QVBoxLayout(frame)
            stamp = time.strftime('%I:%M %p', time.localtime(message['time'] / 1000))
            sender = 'You' if message['from'] == self.persona else message.get('name', 'User')
            header = QtWidgets.QHBoxLayout()
            header.addWidget(message_label(f'{sender}  ·  {stamp}', objectName='sender'), 1)
            reply_button = QtWidgets.QToolButton()
            reply_button.setText('↪'); reply_button.setToolTip('Reply to ' + message.get('name','User'))
            reply_button.clicked.connect(lambda _=False, m=message: self.begin_reply(m))
            header.addWidget(reply_button)
            block.addLayout(header)
            body = message.get('text', '')
            reply = chat_state.reply_parts(body)
            if reply:
                quote = message_label(f'↪ @{reply[0]}: {reply[1]}')
                if reply[0].casefold() in {n['name'].casefold() for n in self.names}:
                    quote.setStyleSheet('color: #ffbd66; border-left: 3px solid #ffbd66; padding-left: 5px;')
                block.addWidget(quote)
                body = reply[2]
            if body:
                label = message_label(body)
                label.setTextInteractionFlags(QtCore.Qt.TextSelectableByMouse)
                block.addWidget(label)
            attachment = message.get('attachment')
            if attachment:
                expired = attachment.get('expired') or (attachment.get('expiresAt', float('inf')) <= time.time() * 1000)
                image = attachment.get('mime') in IMAGE_MIMES
                if expired:
                    block.addWidget(message_label('Expired · ' + attachment.get('name', 'attachment')))
                elif image:
                    ident = attachment['id']
                    show = ElidedButton(('Hide image' if ident in self.expanded_media else 'View image') + ' · ' + attachment.get('name', 'image'))
                    show.setToolTip(attachment.get('name', 'image'))
                    if self.mini:
                        show.setText('Hide image' if ident in self.expanded_media else 'View image')
                    show.clicked.connect(lambda _checked=False, ident=ident: self._toggle_image(ident))
                    if self.mini:
                        block.addWidget(show)
                    if not self.mini or ident in self.expanded_media:
                        picture = QtWidgets.QLabel('Loading image...', objectName='attachment')
                        picture.setAlignment(QtCore.Qt.AlignCenter)
                        picture.setMinimumSize(0, 40)
                        picture.setSizePolicy(QtWidgets.QSizePolicy.Ignored, QtWidgets.QSizePolicy.Preferred)
                        block.addWidget(picture)
                        self.media_labels.setdefault(ident, []).append(picture)
                        if ident in self.media_cache or self.mini or index >= len(self.messages) - 10:
                            self._load_media(ident)
                        else:
                            picture.setText('Image available')
                            show.clicked.connect(lambda _checked=False, ident=ident: self._load_media(ident))
                            block.addWidget(show)
                            self.media_buttons.setdefault(ident, []).append(show)
                elif not expired:
                    label = ('Video' if attachment.get('mime', '').startswith('video/') else 'File')
                    file_label = message_label(label + ' · ' + attachment.get('name', 'file'))
                    block.addWidget(file_label)
                if not expired:
                    if attachment.get('kind') == 'file':
                        minutes = max(0, int((attachment.get('expiresAt', 0)/1000-time.time())/60))
                        block.addWidget(message_label(f'Expires in {minutes} min · save before expiry'))
                    if not self.mini or not image or attachment['id'] in self.expanded_media:
                        save = ElidedButton('Save attachment' if self.mini else 'Save ' + attachment.get('name', 'file'))
                        save.setToolTip(attachment.get('name', 'file'))
                        save.clicked.connect(lambda _checked=False, a=attachment: self.save_attachment(a))
                        block.addWidget(save)
            row = QtWidgets.QHBoxLayout()
            if message['from'] == self.persona:
                row.addStretch()
            row.addWidget(frame)
            if message['from'] != self.persona:
                row.addStretch()
            self.message_layout.addLayout(row)
            frame.setProperty('naturalWidth', 520 if frame.findChildren(QtWidgets.QLabel, 'attachment')
                              else frame.sizeHint().width())
            self.message_frames.append(frame)
        self._fit_message_widths()
        QtCore.QTimer.singleShot(0, self._fit_message_widths)
        QtCore.QTimer.singleShot(0, self._scroll_to_latest)

    def _fit_message_widths(self):
        if not hasattr(self, 'scroll'):
            return
        margins = self.message_layout.contentsMargins()
        available = max(60, self.scroll.viewport().width()-margins.left()-margins.right())
        for frame in self.message_frames:
            width = min(520, available, max(100, frame.property('naturalWidth') or 520))
            if frame.width() != width or frame.minimumWidth() != width:
                frame.setFixedWidth(width)
        for ident in self.media_labels:
            if ident in self.media_cache:
                self._paint_media(ident)

    def _scroll_to_latest(self):
        if getattr(self, '_follow_latest', True):
            self.scroll.verticalScrollBar().setValue(self.scroll.verticalScrollBar().maximum())

    def _user_scrolled(self):
        bar = self.scroll.verticalScrollBar()
        self._follow_latest = bar.value() >= bar.maximum()-40

    def begin_reply(self, message):
        if self.sending:
            return
        self.reply_to = dict(message)
        self.reply_banner.setText('↪ ' + message.get('name','User') + ': ' + chat_state.preview(message)[:65] + '  ×')
        self.reply_banner.show()
        self._collapse(False)
        self.composer.setFocus()

    def cancel_reply(self):
        self.reply_to = None
        self.reply_banner.hide()

    def _load_media(self, media_id):
        if not self._enabled():
            return
        if media_id in self.media_cache:
            self._paint_media(media_id)
            return
        if media_id in self.media_loading:
            return
        self.media_loading.add(media_id)
        self._job(lambda: helper.request('media/' + media_id,
                                       headers={'Authorization': 'Bearer ' + self.secret, 'X-BBE-As': self.persona},
                                       binary=True, timeout=30),
                  lambda value, error: self._media_loaded(media_id, value, error), media=True)

    def _media_loaded(self, media_id, value, error):
        self.media_loading.discard(media_id)
        if error:
            for label in self.media_labels.get(media_id, []):
                label.setText('Image unavailable: ' + error)
            return
        buffer = QtCore.QBuffer()
        buffer.setData(value)
        buffer.open(QtCore.QIODevice.ReadOnly)
        reader = QtGui.QImageReader(buffer)
        size = reader.size()
        if not size.isValid() or size.width() * size.height() > 35_000_000:
            for label in self.media_labels.get(media_id, []):
                label.setText('Image is too large to preview')
            return
        if max(size.width(), size.height()) > 600:
            factor = 600 / max(size.width(), size.height())
            reader.setScaledSize(QtCore.QSize(round(size.width() * factor), round(size.height() * factor)))
        decoded = reader.read()
        if decoded.isNull():
            for label in self.media_labels.get(media_id, []):
                label.setText('Image could not be decoded. Use Save attachment to open it.')
            return
        pixmap = QtGui.QPixmap.fromImage(decoded)
        self.media_cache[media_id] = pixmap.scaled(320, 240, QtCore.Qt.KeepAspectRatio, QtCore.Qt.SmoothTransformation)
        if len(self.media_cache) > 24:
            self.media_cache.pop(next(iter(self.media_cache)))
        self._paint_media(media_id)

    def _paint_media(self, media_id):
        for label in self.media_labels.get(media_id, []):
            width = max(1, min(320, label.contentsRect().width(), self.scroll.viewport().width()-48))
            pixmap = self.media_cache[media_id].scaled(width, 100 if self.mini else 240,
                                                      QtCore.Qt.KeepAspectRatio, QtCore.Qt.SmoothTransformation)
            label.setPixmap(pixmap)
            label.setMinimumSize(0, 0)
            label.setFixedHeight(pixmap.height()+2)
        for button in self.media_buttons.get(media_id, []):
            button.hide()

    def moveEvent(self, event):
        super().moveEvent(event)
        if hasattr(self, 'drawer') and self.drawer.isVisible():
            self._position_drawer()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, 'drawer') and self.drawer.isVisible():
            self._position_drawer()
        if hasattr(self, 'scroll'):
            self._update_window_shape()
            if hasattr(self, 'people_button'):
                self._layout_people_handle()
            for ident in self.media_labels:
                if ident in self.media_cache:
                    self._paint_media(ident)

    def _toggle_image(self, ident):
        if ident in self.expanded_media:
            self.expanded_media.remove(ident)
        else:
            self.expanded_media.add(ident)
        self._draw_messages()

    def remove_shared_file(self):
        if not self.active_file or not self._enabled():
            return
        ident = self.active_file['id']
        self._job(lambda: helper.request('remove-file', {'secret': self.secret, 'as': self.persona, 'id': ident}),
                  lambda value, error: self.status.setText(error) if error else self.sync())

    def _insert_emoji(self, emoji):
        self.emoji_menu.hide()
        self.composer.insertPlainText(emoji)
        self.composer.setFocus(QtCore.Qt.PopupFocusReason)

    def attach(self, kind='all'):
        if not self._enabled():
            self.status.setText('Enable chat in account settings first')
            return
        filters = {'image': 'Images (*.png *.jpg *.jpeg *.gif *.webp)',
                   'video': 'Videos (*.mp4 *.webm)',
                   'file': 'Files (*.blend *.zip *.pdf *.json *.nmsbase *.nmsship *.nmsprefab *.txt *.log)'}
        path, _ = QtWidgets.QFileDialog.getOpenFileName(self, 'Choose a file to share', str(Path.home()), filters.get(kind, FILE_TYPES))
        if path:
            self._stage(Path(path), owned=False)

    def _paste_image(self, image):
        """Keep clipboard pixels in an owned PNG draft; never send on paste."""
        if self.sending:
            self.status.setText('Wait for the current send, or cancel it in chat options.')
            return
        if image.isNull():
            self.status.setText('The clipboard image could not be read.')
            return
        path = Path(tempfile.gettempdir()) / ('bbe-chat-paste-' + secrets.token_hex(12) + '.png')
        try:
            if not image.save(str(path), 'PNG'):
                raise OSError('The clipboard image could not be saved.')
            self._stage(path, owned=True, preserve_alpha=True)
        except OSError as error:
            self.status.setText(str(error))
        finally:
            if self.pending != path:
                try:
                    path.unlink(missing_ok=True)
                except OSError:
                    pass

    def _stage(self, path, owned, preserve_alpha=False):
        if self.sending:
            self.status.setText("Wait for the current send, or cancel it in chat options.")
            return
        if not path.is_file() or not 0 < path.stat().st_size <= helper.file_limit(path) or path.suffix.lower() not in helper.MIMES:
            self.status.setText('BLEND, ZIP and PDF: up to 2 GB. Other supported files: up to 20 MB.')
            return
        if path.suffix.lower() not in MEDIA_SUFFIXES:
            if not self.capabilities.get('files'):
                self.status.setText('File sharing requires the updated chat server. Images and videos still work.')
                return
            if path.stat().st_size > helper.MAX_BYTES and not self.capabilities.get('chunkedFiles'):
                self.status.setText('Large-file transfers require the updated chat server. Please try again after deployment.')
                return
            if self.active_file:
                self.status.setText('Remove your shared file in chat options, or wait for its two-hour expiry.')
                return
        self._collapse(False)
        self.clear_attachment()
        self.pending, self.pending_owned = path, owned
        self.pending_preserve_alpha = preserve_alpha
        self.preview.setText(f'Ready: {path.name} ({path.stat().st_size / 1024 / 1024:.1f} MB)' + (' · expires after 2 hours' if path.suffix.lower() not in MEDIA_SUFFIXES else ''))
        self.preview.setWordWrap(True)
        self.preview.show()
        self.remove_button.show()
        self.status.setText('File queued. Press Enter or Send when ready.')

    def clear_attachment(self):
        if self.sending:
            self.status.setText("Cancel the transfer in chat options before removing its attachment.")
            return
        if self.pending_owned and self.pending:
            try:
                self.pending.unlink(missing_ok=True)
            except OSError:
                pass
        self.pending, self.pending_owned = None, False
        self.pending_preserve_alpha = False
        self.preview.hide()
        self.remove_button.hide()

    def snapshot(self):
        if not self._enabled():
            self.status.setText('Enable chat in account settings first')
            return
        if self.snapshot_id:
            return
        self.snapshot_dir.mkdir(parents=True, exist_ok=True)
        self.snapshot_id = secrets.token_hex(12)
        self.snapshot_at = time.monotonic()
        request = self.snapshot_dir / 'snapshot-request.json'
        temporary = request.with_suffix('.new')
        temporary.write_text(json.dumps({'id': self.snapshot_id}), encoding='utf-8')
        os.replace(temporary, request)
        self.status.setText('Capturing the Blender window...')

    def _check_snapshot(self):
        if not self.snapshot_id:
            return
        response = self.snapshot_dir / ('snapshot-' + self.snapshot_id + '.json')
        if response.exists():
            try:
                result = json.loads(response.read_text(encoding='utf-8'))
                if result.get('path'):
                    self._stage(Path(result['path']), owned=True)
                else:
                    self.status.setText(result.get('error', 'Could not capture Blender'))
            except (OSError, ValueError):
                self.status.setText('Could not read the screenshot')
            response.unlink(missing_ok=True)
            self.snapshot_id = None
        elif time.monotonic() - self.snapshot_at > 20:
            self.snapshot_id = None
            self.status.setText('Blender did not respond to the snapshot request')

    def _small_image(self, source, force_jpeg=False):
        if source.suffix.lower() == '.gif':
            return source, False
        reader = QtGui.QImageReader(str(source))
        size = reader.size()
        if not size.isValid() or size.width() * size.height() > 35_000_000:
            return source, False
        if source.stat().st_size < 700_000 and max(size.width(), size.height()) <= 1600:
            return source, False
        if max(size.width(), size.height()) > 1600:
            factor = 1600 / max(size.width(), size.height())
            reader.setScaledSize(QtCore.QSize(round(size.width() * factor), round(size.height() * factor)))
        image = reader.read()
        if image.isNull():
            return source, False
        suffix = '.png' if image.hasAlphaChannel() and not force_jpeg else '.jpg'
        output = Path(tempfile.gettempdir()) / ('bbe-chat-small-' + secrets.token_hex(12) + suffix)
        if not image.save(str(output), 'PNG' if suffix == '.png' else 'JPEG', 82):
            return source, False
        if output.stat().st_size >= source.stat().st_size:
            output.unlink(missing_ok=True)
            return source, False
        return output, True

    def send(self):
        if not self.persona:
            self.status.setText('Claim a name in account settings first.')
            return
        if self.sending or self.claiming or self.transfer_cancel:
            return
        if not self._enabled():
            self.status.setText('Enable chat in account settings first')
            return
        text = self.composer.toPlainText().strip()
        if not text and not self.pending:
            return
        reply = self.reply_to
        wire_text = chat_state.make_reply(reply['name'], chat_state.preview(reply), text) if reply else text
        if len(wire_text) > 1000:
            self.status.setText('Message is too long (1,000 characters maximum)')
            return
        self.sending = True
        self.send_button.setEnabled(False)
        self.status.setText('Sending...' if not self.pending else 'Optimizing and uploading in the background...')
        pending = self.pending
        pending_owned = self.pending_owned
        preserve_alpha = self.pending_preserve_alpha
        target, persona = self.target, self.persona
        received = chat_state.latest_received(self._notifications, target) if target else None
        optimize = self.optimize.isChecked()
        transfer = self._begin_transfer("Uploading") if pending else {}
        transfer['_chunkedFiles'] = bool(self.capabilities.get('chunkedFiles'))

        def work():
            optimized = None
            try:
                path = pending
                if path and optimize and path.suffix.lower() in ('.png', '.jpg', '.jpeg', '.webp'):
                    path, made = self._small_image(path, force_jpeg=pending_owned and not preserve_alpha)
                    optimized = path if made else None
                return helper.run('send', {'secret': self.secret, 'as': persona, 'to': target or '',
                                           'text': wire_text, 'file': str(path) if path else '', **transfer})
            finally:
                if optimized:
                    optimized.unlink(missing_ok=True)

        self._job(work, lambda value, error: self._sent(value, error, text, pending, target, persona, received))

    def _sent(self, value, error, text, pending, target, persona, received=None):
        self._end_transfer()
        self.sending = False
        self.send_button.setEnabled(True)
        if error:
            self.status.setText(error)
            return
        if self.composer.toPlainText().strip() == text:
            self.composer.clear()
            self.cancel_reply()
        if self.pending == pending:
            self.clear_attachment()
        self.status.setText('Sent')
        if target and persona == self.persona:
            chat_state.answered(self._notifications, target, received)
            self._update_badge()
            self._publish_toolbar_status()
        message = value.get('message') if isinstance(value, dict) else None
        if message and target == self.target and persona == self.persona and message['id'] not in self.message_ids:
            self.message_generation += 1
            self.messages.append(message)
            self.message_ids = tuple(item['id'] for item in self.messages)
            self._draw_messages()
        self.sync()

    def _begin_transfer(self, label):
        self.transfer_cancel = threading.Event()
        self.transfer_id = secrets.token_hex(8)
        ident = self.transfer_id
        self.cancel_transfer_action.setEnabled(True)
        return {'_cancel': self.transfer_cancel,
                '_progress': lambda done, total: self.transfer_progress.emit((ident, label, done, total))}

    @QtCore.Slot(object)
    def _transfer_progress(self, update):
        ident, label, done, total = update
        if ident == self.transfer_id and not self.transfer_cancel.is_set():
            self.status.setText(f'{label}: {done / max(1, total):.0%} · {done / 1048576:.0f}/{total / 1048576:.0f} MB · Cancel in …')

    def cancel_transfer(self):
        if self.transfer_cancel:
            self.transfer_cancel.set()
            self.status.setText('Cancelling transfer…')

    def _end_transfer(self):
        self.transfer_cancel = None
        self.transfer_id = None
        self.cancel_transfer_action.setEnabled(False)

    def save_attachment(self, attachment):
        if not self._enabled():
            self.status.setText('Enable chat first')
            return
        if self.transfer_cancel:
            self.status.setText('Wait for this transfer, or cancel it in chat options.')
            return
        destination, _ = QtWidgets.QFileDialog.getSaveFileName(self, 'Save chat file',
                                                               str(Path.home() / 'Downloads' / attachment['name']))
        if not destination:
            return
        path = Path(destination)
        if path.exists():
            self.status.setText('Choose a new filename; chat will not overwrite a file')
            return
        self.status.setText('Downloading...')
        transfer = self._begin_transfer('Downloading')
        def completed(_value, error):
            self._end_transfer()
            self.status.setText(error or 'Saved to ' + str(path))
        self._job(lambda: helper.run('download', {'secret': self.secret, 'as': self.persona,
                                                 'id': attachment['id'], 'path': str(path), 'size': attachment.get('size') if self.capabilities.get('chunkedFiles') else None,
                                                 'sha256': attachment.get('sha256'), **transfer}), completed)

    def blender_exited(self):
        """Close even when the native-toolbar companion has no visible window."""
        self.close()
        self.pool.clear()
        self.media_pool.clear()
        # A network read can be blocked for up to a minute. Give cancellation
        # time to clean up, but do not leave Qt waiting forever on a worker.
        if self.pool.activeThreadCount() or self.media_pool.activeThreadCount():
            deadline = threading.Timer(8, lambda: os._exit(0))
            deadline.daemon = True
            deadline.start()
        QtWidgets.QApplication.instance().quit()

    def closeEvent(self, event):
        self.cancel_transfer()
        if not self.sending:
            self.clear_attachment()
        self._closing = True
        self.compact_timer.stop()
        self.drawer.hide()
        self.timer.stop()
        self.snapshot_timer.stop()
        try:
            temporary = self.window_path.with_suffix('.new')
            temporary.write_text(json.dumps({
                'geometry': bytes(self.saveGeometry().toBase64()).decode('ascii'),
                'pin': self.pin_button.isChecked(),
                'pin_preference_version': 1,
                'dock': self.dock_mode,
                'layout_version': 2,
                'collapsed': self.collapsed,
                'mini_size': [self._mini_size.width(), self._mini_size.height()] if self.collapsed or not self.mini else [self.width(), self.height()],
                'mini': self.mini,
                'sidebar': self.sidebar_action.isChecked(),
            }), encoding='utf-8')
            os.replace(temporary, self.window_path)
        except OSError:
            pass
        super().closeEvent(event)


def main():
    if len(sys.argv) not in (5, 7, 8) or (len(sys.argv) >= 7 and sys.argv[5] != '--blender-pid') or (len(sys.argv) == 8 and sys.argv[7] != '--prewarm'):
        raise SystemExit('Missing messenger configuration')
    owner_pid = int(sys.argv[6]) if len(sys.argv) >= 7 else os.getppid()
    prewarm = len(sys.argv) == 8
    app = QtWidgets.QApplication(sys.argv)
    app.setApplicationName('BBE Messenger')
    lifetime = BlenderLifetime(app)
    if not lifetime.add_owner(owner_pid):
        return 0  # Blender may have exited while Qt was starting.
    app.aboutToQuit.connect(lifetime.close)
    if sys.platform == 'win32':
        font_file = Path(os.environ.get('WINDIR', r'C:\Windows')) / 'Fonts' / 'segoeui.ttf'
        if font_file.is_file():
            font_id = QtGui.QFontDatabase.addApplicationFont(str(font_file))
            families = QtGui.QFontDatabase.applicationFontFamilies(font_id)
            if families:
                app.setFont(QtGui.QFont(families[0], 10))
    identity_path = Path(sys.argv[2])
    server_name = 'bbe-messenger-' + hashlib.sha256(str(identity_path).lower().encode()).hexdigest()[:20]
    socket = QtNetwork.QLocalSocket()
    socket.connectToServer(server_name)
    if socket.waitForConnected(150):
        socket.write(json.dumps({'action': 'attach' if prewarm else 'activate',
                                 'owner_pid': owner_pid}).encode('utf-8'))
        socket.waitForBytesWritten(150)
        lifetime.close()
        return
    QtNetwork.QLocalServer.removeServer(server_name)
    listener = QtNetwork.QLocalServer()
    listener.listen(server_name)
    window = (Messenger(identity_path, sys.argv[3], sys.argv[4], prewarm=True) if prewarm
              else Messenger(identity_path, sys.argv[3], sys.argv[4]))
    lifetime.ended.connect(window.blender_exited)

    def activate():
        connection = listener.nextPendingConnection()
        connection.waitForReadyRead(150)
        payload = bytes(connection.read(4096))
        if payload != b'activate':
            try:
                command = json.loads(payload)
            except (ValueError, UnicodeDecodeError):
                command = None
            if (not isinstance(command, dict) or command.get('action') not in ('activate', 'attach')
                    or not lifetime.add_owner(command.get('owner_pid'))):
                connection.disconnectFromServer()
                return
        if payload == b'activate' or command['action'] == 'activate':
            window.showNormal()
            window.raise_()
            window.activateWindow()
        connection.disconnectFromServer()

    listener.newConnection.connect(activate)
    if not prewarm and not (window.mini and window.collapsed and window.dock_mode == 'toolbar'
            and window._settings().get('native_chat_toolbar')):
        window.show()
    QtCore.QTimer.singleShot(0, window._consume_blender_command)
    return app.exec()


if __name__ == '__main__':
    sys.exit(main() or 0)
