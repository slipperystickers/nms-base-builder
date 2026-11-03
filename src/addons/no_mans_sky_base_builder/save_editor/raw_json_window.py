"""Separate advanced save JSON window; launched only for a selected Steam save."""
import argparse
import atexit
import ctypes
import itertools
import json
from pathlib import Path
import re
import sys


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--qt-site', required=True)
    parser.add_argument('--save', required=True)
    parser.add_argument('--backup-root', required=True)
    parser.add_argument('--parent-pid', type=int, default=0)
    args = parser.parse_args()
    sys.path.insert(0, args.qt_site)
    from PySide6 import QtCore, QtGui, QtWidgets
    import raw_json_core as core

    class ParentLifetime:
        """Hold the original Blender process handle, safe from PID reuse."""
        def __init__(self, pid):
            self.kernel = ctypes.WinDLL('kernel32', use_last_error=True)
            self.kernel.OpenProcess.argtypes = (ctypes.c_ulong, ctypes.c_int, ctypes.c_ulong)
            self.kernel.OpenProcess.restype = ctypes.c_void_p
            self.kernel.WaitForSingleObject.argtypes = (ctypes.c_void_p, ctypes.c_ulong)
            self.kernel.WaitForSingleObject.restype = ctypes.c_ulong
            self.kernel.CloseHandle.argtypes = (ctypes.c_void_p,)
            self.handle = self.kernel.OpenProcess(0x00100000, False, pid)  # SYNCHRONIZE
            if not self.handle:
                raise RuntimeError(f'Could not monitor Blender process {pid}')
            atexit.register(self.close)

        def alive(self):
            return self.kernel.WaitForSingleObject(self.handle, 0) == 0x00000102

        def close(self):
            if self.handle:
                self.kernel.CloseHandle(self.handle)
                self.handle = None

    class LineNumberArea(QtWidgets.QWidget):
        def __init__(self, editor):
            super().__init__(editor)
            self.editor = editor

        def sizeHint(self):
            return QtCore.QSize(self.editor.line_number_width(), 0)

        def paintEvent(self, event):
            self.editor.paint_line_numbers(event)

    class JsonEditor(QtWidgets.QPlainTextEdit):
        def __init__(self):
            super().__init__()
            self.gutter = LineNumberArea(self)
            self.blockCountChanged.connect(self.update_line_number_width)
            self.updateRequest.connect(self.update_line_numbers)
            self.update_line_number_width()

        def line_number_width(self):
            digits = len(str(max(1, self.blockCount())))
            return 12 + self.fontMetrics().horizontalAdvance('9') * digits

        def update_line_number_width(self, _=None):
            self.setViewportMargins(self.line_number_width(), 0, 0, 0)

        def update_line_numbers(self, rect, dy):
            if dy:
                self.gutter.scroll(0, dy)
            else:
                self.gutter.update(0, rect.y(), self.gutter.width(), rect.height())
            if rect.contains(self.viewport().rect()):
                self.update_line_number_width()

        def resizeEvent(self, event):
            super().resizeEvent(event)
            rect = self.contentsRect()
            self.gutter.setGeometry(rect.left(), rect.top(), self.line_number_width(), rect.height())

        def paint_line_numbers(self, event):
            painter = QtGui.QPainter(self.gutter)
            painter.fillRect(event.rect(), self.palette().alternateBase())
            block = self.firstVisibleBlock()
            number = block.blockNumber()
            top = self.blockBoundingGeometry(block).translated(self.contentOffset()).top()
            height = self.fontMetrics().height()
            while block.isValid() and top <= event.rect().bottom():
                if block.isVisible() and top + height >= event.rect().top():
                    painter.setPen(self.palette().placeholderText().color())
                    painter.drawText(0, int(top), self.gutter.width() - 5, height,
                                     QtCore.Qt.AlignRight, str(number + 1))
                block = block.next()
                number += 1
                top = self.blockBoundingGeometry(block).translated(self.contentOffset()).top()

    class RawWindow(QtWidgets.QMainWindow):
        @staticmethod
        def style_save_button(button):
            button.setCursor(QtCore.Qt.PointingHandCursor)
            button.setStyleSheet(
                'QPushButton:enabled {'
                ' background-color: #238b4a; color: white; border: 1px solid #61d48b;'
                ' border-radius: 4px; padding: 4px 9px; }'
                'QPushButton:enabled:hover, QPushButton:enabled:focus {'
                ' background-color: #2ca759; border: 1px solid #84e5a5; }'
                'QPushButton:enabled:pressed {'
                ' background-color: #176a36; color: white; border: 1px solid #61d48b;'
                ' border-radius: 4px; padding: 4px 9px; }'
                'QPushButton:disabled {'
                ' background-color: #33343a; color: #96989f; border: 1px solid #4b4d54;'
                ' border-radius: 4px; padding: 4px 9px; }')

        def __init__(self):
            super().__init__()
            self.setWindowTitle('BBE · Advanced Raw Save JSON')
            self.resize(1250, 780)
            self.path = Path(args.save).resolve()
            self.backup_root = args.backup_root
            self.root = None
            self.expected = {}
            self.stats = {}
            self.modified = False
            self.stale = False
            self.node_dirty = False
            self.quick_dirty = False
            self.current_path = ()
            self.current_item = None
            self.preview_path = None
            self.quick_current_path = None
            self.quick_preview_path = None
            self.advanced_rendered = False
            self._selecting = False
            self.parent_exited = False
            self.name_cache = {}
            self.folder_icon = self.style().standardIcon(QtWidgets.QStyle.SP_DirIcon)
            self.field_icon = self.style().standardIcon(QtWidgets.QStyle.SP_FileIcon)

            body = QtWidgets.QWidget()
            self.setCentralWidget(body)
            outer = QtWidgets.QVBoxLayout(body)
            header = QtWidgets.QHBoxLayout()
            self.folder_label = QtWidgets.QLabel()
            header.addWidget(self.folder_label, 1)
            browse = QtWidgets.QPushButton('Browse Folder…')
            browse.clicked.connect(self.browse_folder)
            header.addWidget(browse)
            outer.addLayout(header)
            files = QtWidgets.QHBoxLayout()
            files.addWidget(QtWidgets.QLabel('Save point:'))
            self.files = QtWidgets.QComboBox()
            self.files.currentIndexChanged.connect(self.choose_file)
            files.addWidget(self.files, 1)
            self.all_slots = QtWidgets.QCheckBox('Show all account slots')
            self.all_slots.toggled.connect(lambda _: self.populate_files(self.path.parent, self.path))
            files.addWidget(self.all_slots)
            self.refresh_button = QtWidgets.QPushButton('Refresh from Disk')
            self.refresh_button.clicked.connect(self.refresh)
            files.addWidget(self.refresh_button)
            outer.addLayout(files)
            self.slot_summary = QtWidgets.QLabel()
            outer.addWidget(self.slot_summary)

            self.quick_toggle = QtWidgets.QCheckBox('Quick View — grouped bases')
            self.quick_toggle.toggled.connect(self.set_quick_mode)
            outer.addWidget(self.quick_toggle)
            self.stack = QtWidgets.QStackedWidget()
            outer.addWidget(self.stack, 1)
            advanced = QtWidgets.QWidget()
            advanced_layout = QtWidgets.QVBoxLayout(advanced)
            advanced_layout.setContentsMargins(0, 0, 0, 0)

            nav = QtWidgets.QHBoxLayout()
            self.path_search = QtWidgets.QLineEdit()
            self.path_search.setPlaceholderText('Jump to path, e.g. BaseContext.PlayerStateData')
            self.path_search.returnPressed.connect(self.jump_to_path)
            nav.addWidget(self.path_search, 1)
            jump = QtWidgets.QPushButton('Go to Path')
            jump.clicked.connect(self.jump_to_path)
            nav.addWidget(jump)
            self.text_search = QtWidgets.QLineEdit()
            self.text_search.setPlaceholderText('Find text in selected JSON (Ctrl+F)')
            self.text_search.returnPressed.connect(self.find_text)
            nav.addWidget(self.text_search, 1)
            find = QtWidgets.QPushButton('Find')
            find.clicked.connect(self.find_text)
            nav.addWidget(find)
            advanced_layout.addLayout(nav)

            splitter = QtWidgets.QSplitter()
            self.tree = QtWidgets.QTreeWidget()
            self.tree.setHeaderLabels(['JSON folders and keys'])
            self.tree.itemExpanded.connect(self.expand_item)
            self.tree.currentItemChanged.connect(self.select_item)
            splitter.addWidget(self.tree)
            self.editor = JsonEditor()
            self.editor.setLineWrapMode(QtWidgets.QPlainTextEdit.NoWrap)
            self.editor.setFont(QtGui.QFont('Consolas', 10))
            self.editor.textChanged.connect(self.text_changed)
            splitter.addWidget(self.editor)
            splitter.setSizes([350, 900])
            advanced_layout.addWidget(splitter, 1)

            controls = QtWidgets.QHBoxLayout()
            self.status = QtWidgets.QLabel('')
            controls.addWidget(self.status, 1)
            self.load_full_button = QtWidgets.QPushButton('Load Full JSON for This Node')
            self.load_full_button.clicked.connect(self.load_full_node)
            controls.addWidget(self.load_full_button)
            self.save_button = QtWidgets.QPushButton('Back Up and Save to Game')
            self.style_save_button(self.save_button)
            self.save_button.setToolTip('Create a verified backup, then write the selected save point to disk.')
            self.save_button.clicked.connect(self.save_file)
            controls.addWidget(self.save_button)
            advanced_layout.addLayout(controls)
            self.stack.addWidget(advanced)

            quick = QtWidgets.QWidget()
            quick_layout = QtWidgets.QVBoxLayout(quick)
            quick_layout.setContentsMargins(0, 0, 0, 0)
            self.quick_summary = QtWidgets.QLabel()
            quick_layout.addWidget(self.quick_summary)
            self.quick_search = QtWidgets.QLineEdit()
            self.quick_search.setPlaceholderText('Filter by base name, number, type, or context')
            self.quick_search.textChanged.connect(self.filter_quick)
            quick_layout.addWidget(self.quick_search)
            quick_splitter = QtWidgets.QSplitter()
            self.quick_list = QtWidgets.QTreeWidget()
            self.quick_list.setHeaderLabels(['Base name', 'Base #', 'Type', 'Objects'])
            self.quick_list.setAlternatingRowColors(True)
            self.quick_list.setColumnWidth(0, 240)
            self.quick_list.setColumnWidth(1, 65)
            self.quick_list.setColumnWidth(2, 145)
            self.quick_list.setColumnWidth(3, 65)
            self.quick_list.itemDoubleClicked.connect(self.open_quick_base)
            self.quick_list.currentItemChanged.connect(self.update_quick_selection)
            quick_splitter.addWidget(self.quick_list)
            quick_detail = QtWidgets.QWidget()
            quick_detail_layout = QtWidgets.QVBoxLayout(quick_detail)
            quick_detail_layout.setContentsMargins(0, 0, 0, 0)
            self.quick_heading = QtWidgets.QLabel('Select a base to view its JSON.')
            quick_detail_layout.addWidget(self.quick_heading)
            self.quick_editor = JsonEditor()
            self.quick_editor.setLineWrapMode(QtWidgets.QPlainTextEdit.NoWrap)
            self.quick_editor.setFont(QtGui.QFont('Consolas', 10))
            self.quick_editor.setReadOnly(True)
            self.quick_editor.textChanged.connect(self.quick_text_changed)
            quick_detail_layout.addWidget(self.quick_editor, 1)
            quick_splitter.addWidget(quick_detail)
            quick_splitter.setSizes([540, 710])
            quick_layout.addWidget(quick_splitter, 1)
            quick_buttons = QtWidgets.QHBoxLayout()
            self.quick_status = QtWidgets.QLabel('')
            quick_buttons.addWidget(self.quick_status, 1)
            self.quick_full_button = QtWidgets.QPushButton('Load Full Base JSON')
            self.quick_full_button.clicked.connect(self.load_full_quick_node)
            self.quick_full_button.setEnabled(False)
            quick_buttons.addWidget(self.quick_full_button)
            quick_buttons.addStretch(1)
            self.open_base_button = QtWidgets.QPushButton('Open Selected Base in JSON View')
            self.open_base_button.setEnabled(False)
            self.open_base_button.clicked.connect(self.open_quick_base)
            quick_buttons.addWidget(self.open_base_button)
            self.quick_save_button = QtWidgets.QPushButton('Back Up and Save to Game')
            self.style_save_button(self.quick_save_button)
            self.quick_save_button.setToolTip('Create a verified backup, then write the selected save point to disk.')
            self.quick_save_button.clicked.connect(self.save_file)
            quick_buttons.addWidget(self.quick_save_button)
            quick_layout.addLayout(quick_buttons)
            self.stack.addWidget(quick)
            self.quick_toggle.setChecked(True)
            self.populate_files(self.path.parent, self.path)
            self.load_file(self.path)
            self.timer = QtCore.QTimer(self)
            self.timer.timeout.connect(self.check_source)
            self.timer.start(5000)

        def populate_files(self, folder, selected=None):
            folder = Path(folder).resolve()
            all_paths = [p for p in folder.iterdir() if p.is_file() and core.SAVE_NAME.fullmatch(p.name)]
            if not all_paths:
                raise ValueError('This folder contains no Steam save*.hg files')
            selected = Path(selected).resolve() if selected else max(all_paths, key=lambda p: p.stat().st_mtime_ns)
            slot = core.slot_point(selected)[0]
            paths = sorted((all_paths if self.all_slots.isChecked() else
                            [path for path in all_paths if core.slot_point(path)[0] == slot]),
                           key=core.slot_point)
            self.folder_label.setText(str(folder))
            self.slot_summary.setText(
                f'Slot {slot}: {sum(core.slot_point(path)[0] == slot for path in all_paths)} save point(s). '
                f'This account has {len(all_paths)} files across '
                f'{len({core.slot_point(path)[0] for path in all_paths})} slots; each slot has up to two points.')
            self.files.blockSignals(True)
            self.files.clear()
            for path in paths:
                number, point = core.slot_point(path)
                self.files.addItem(f'{self.player_name(path)} — Slot {number} · Point {point} ({path.name})', str(path))
            index = next((index for index, path in enumerate(paths) if path == selected), 0)
            self.files.setCurrentIndex(index)
            self.files.blockSignals(False)
            return paths[index]

        def player_name(self, path):
            try:
                stat = path.stat()
                cache_key = (str(path), stat.st_size, stat.st_mtime_ns)
                if cache_key not in self.name_cache:
                    self.name_cache[cache_key] = core.peek_save_name(path) or 'Unnamed save'
                return self.name_cache[cache_key]
            except Exception:
                return 'Name unavailable'

        def browse_folder(self):
            if not self.leave_current():
                return
            folder = QtWidgets.QFileDialog.getExistingDirectory(self, 'Select NMS account save folder', str(self.path.parent))
            if not folder:
                return
            try:
                chosen = self.populate_files(folder)
                if not self.load_file(chosen):
                    self.populate_files(self.path.parent, self.path)
            except Exception as exc:
                self.populate_files(self.path.parent, self.path)
                QtWidgets.QMessageBox.critical(self, 'Could not open folder', str(exc))

        def choose_file(self, index):
            if index < 0:
                return
            next_path = Path(self.files.itemData(index))
            if next_path == self.path:
                return
            if not self.leave_current():
                self.files.blockSignals(True)
                previous = self.files.findData(str(self.path))
                self.files.setCurrentIndex(previous)
                self.files.blockSignals(False)
                return
            if not self.load_file(next_path):
                self.populate_files(self.path.parent, self.path)

        def leave_current(self, reload_discard=True):
            if not (self.modified or self.node_dirty or self.quick_dirty):
                return True
            dialog = QtWidgets.QMessageBox(self)
            dialog.setWindowTitle('Unsaved save JSON changes')
            dialog.setIcon(QtWidgets.QMessageBox.Warning)
            dialog.setText('Save your JSON changes before leaving?')
            dialog.setInformativeText(
                'Apply and Save Changes creates a verified backup before writing the selected '
                'save point. Discard Changes leaves the game save unchanged.')
            save = dialog.addButton('Apply and Save Changes', QtWidgets.QMessageBox.AcceptRole)
            self.style_save_button(save)
            discard = dialog.addButton('Discard Changes', QtWidgets.QMessageBox.DestructiveRole)
            dialog.addButton('Stay in Editor', QtWidgets.QMessageBox.RejectRole)
            dialog.setDefaultButton(save)
            dialog.exec()
            if dialog.clickedButton() == save:
                return self.save_file(quiet=True)
            if dialog.clickedButton() == discard:
                if reload_discard:
                    self.modified = self.node_dirty = self.quick_dirty = False
                    return self.load_file(self.path)
                return True
            return False

        def load_file(self, path):
            try:
                root, expected, stats = core.read(path)
            except Exception as exc:
                if self.root is None:
                    raise RuntimeError(str(exc)) from exc
                QtWidgets.QMessageBox.critical(self, 'Raw JSON unavailable', str(exc))
                return False
            self.path, self.root = Path(path).resolve(), root
            self.expected, self.stats = expected, stats
            name = core.save_name(root) or 'Unnamed save'
            number, point = core.slot_point(self.path)
            self.setWindowTitle(f'BBE · {name} — Slot {number}, Point {point} · Advanced Save JSON')
            selected_index = self.files.findData(str(self.path))
            if selected_index >= 0:
                self.files.setItemText(selected_index,
                                       f'{name} — Slot {number} · Point {point} ({self.path.name})')
            self.modified = self.stale = self.node_dirty = self.quick_dirty = False
            self.current_path = ()
            self.quick_current_path = None
            self.quick_preview_path = None
            self.advanced_rendered = False
            self.tree.clear()
            top = self.make_item(None, f'{name} — {self.path.name}', (), root)
            self.tree.addTopLevelItem(top)
            top.setExpanded(True)
            self._selecting = True
            self.tree.setCurrentItem(top)
            self._selecting = False
            self.editor.blockSignals(True)
            self.editor.clear()
            self.editor.setReadOnly(True)
            self.editor.blockSignals(False)
            self.quick_editor.blockSignals(True)
            self.quick_editor.clear()
            self.quick_editor.setReadOnly(True)
            self.quick_editor.blockSignals(False)
            self.quick_heading.setText('Select a base to view its JSON.')
            self.populate_quick()
            if not self.quick_toggle.isChecked():
                self.show_node((), top)
            self.update_status()
            return True

        def set_quick_mode(self, enabled):
            if (self.modified or self.node_dirty or self.quick_dirty) and not self.leave_current():
                self.quick_toggle.blockSignals(True)
                self.quick_toggle.setChecked(not enabled)
                self.quick_toggle.blockSignals(False)
                return
            if enabled:
                self.populate_quick()
            self.stack.setCurrentIndex(1 if enabled else 0)
            if not enabled and not self.advanced_rendered:
                if self.quick_current_path:
                    self.path_search.setText('.'.join(str(core.readable_key(part))
                                                      for part in self.quick_current_path))
                    self.jump_to_path()
                else:
                    top = self.tree.topLevelItem(0)
                    self.show_node((), top)

        def populate_quick(self):
            if self.root is None:
                return
            records = core.base_records(self.root)
            self.quick_list.blockSignals(True)
            self.quick_list.clear()
            for context in ('Main', 'Expedition'):
                context_records = [record for record in records if record['context'] == context]
                root_item = QtWidgets.QTreeWidgetItem(
                    self.quick_list, [f'{context} Save ({len(context_records)})'])
                root_item.setIcon(0, self.folder_icon)
                for category in core.BASE_CATEGORIES:
                    members = sorted((record for record in context_records
                                      if record['category'] == category),
                                     key=lambda record: (record['name'].casefold(), record['index']))
                    if not members and category == 'Other':
                        continue
                    group = QtWidgets.QTreeWidgetItem(root_item, [f'{category} ({len(members)})'])
                    group.setIcon(0, self.folder_icon)
                    for record in members:
                        item = QtWidgets.QTreeWidgetItem(group, [
                            record['name'], str(record['index']), record['type'],
                            str(record['object_count'])])
                        item.setIcon(0, self.field_icon)
                        item.setData(0, QtCore.Qt.UserRole, record['path'])
                        item.setToolTip(0, f"Base {record['index']} · {record['raw_type'] or 'Unknown Type'}")
                    group.setExpanded(True)
                root_item.setExpanded(True)
            self.quick_list.blockSignals(False)
            self.update_quick_selection(None, None)
            self.quick_summary.setText(
                f'{len(records)} base records in separate Main and Expedition trees · '
                'Base # is the original zero-based index in its save context.')
            self.filter_quick(self.quick_search.text())

        def filter_quick(self, text):
            query = text.strip().casefold()
            for context_index in range(self.quick_list.topLevelItemCount()):
                context_item = self.quick_list.topLevelItem(context_index)
                context_match = query in context_item.text(0).casefold()
                context_shown = 0
                for group_index in range(context_item.childCount()):
                    group = context_item.child(group_index)
                    category_match = context_match or query in group.text(0).casefold()
                    shown = 0
                    for child_index in range(group.childCount()):
                        child = group.child(child_index)
                        values = ' '.join(child.text(column) for column in range(4))
                        matches = not query or category_match or query in values.casefold()
                        child.setHidden(not matches)
                        shown += bool(matches)
                    group.setHidden(bool(query) and not shown)
                    context_shown += shown
                context_item.setHidden(bool(query) and not context_shown)

        def update_quick_selection(self, item, _old):
            if self.quick_dirty and not self.stage_quick_node():
                self.quick_list.blockSignals(True)
                previous = self.find_quick_item(self.quick_current_path)
                self.quick_list.setCurrentItem(previous)
                self.quick_list.blockSignals(False)
                return
            path = item.data(0, QtCore.Qt.UserRole) if item is not None else None
            self.quick_current_path = path
            self.open_base_button.setEnabled(
                path is not None)
            if path is not None:
                self.show_quick_node(path, item)
            else:
                self.quick_heading.setText('Select a base to view its JSON.')
                self.quick_editor.blockSignals(True)
                self.quick_editor.clear()
                self.quick_editor.setReadOnly(True)
                self.quick_editor.blockSignals(False)

        def find_quick_item(self, path):
            for context_index in range(self.quick_list.topLevelItemCount()):
                context_item = self.quick_list.topLevelItem(context_index)
                for group_index in range(context_item.childCount()):
                    group = context_item.child(group_index)
                    for child_index in range(group.childCount()):
                        candidate = group.child(child_index)
                        if candidate.data(0, QtCore.Qt.UserRole) == path:
                            return candidate
            return None

        def open_quick_base(self, *_):
            item = self.quick_list.currentItem()
            path = item.data(0, QtCore.Qt.UserRole) if item is not None else None
            if path is None:
                return
            self.path_search.setText('.'.join(str(core.readable_key(part)) for part in path))
            self.quick_toggle.setChecked(False)
            if not self.quick_toggle.isChecked():
                self.jump_to_path()

        def value_at(self, path):
            value = self.root
            for key in path:
                value = value[key]
            return value

        def show_quick_node(self, path, item):
            value = self.value_at(path)
            player = self.value_at(path[:-2])
            info = core.base_info(value, path[-1], player)
            context = 'Main' if core.readable_key(path[0]) == 'BaseContext' else 'Expedition'
            self.quick_heading.setText(
                f"{context} · Base {info['index']} · {info['name']} · {info['type']}")
            large = len(json.dumps(value, ensure_ascii=False)) > 1_000_000
            self.quick_preview_path = path if large else None
            self.quick_editor.blockSignals(True)
            self.quick_editor.setPlainText(self.preview_json(value) if large else self.display_json(value))
            self.quick_editor.setReadOnly(large)
            self.quick_editor.blockSignals(False)
            self.quick_dirty = False
            self.quick_full_button.setEnabled(large)
            self.update_status()

        def load_full_quick_node(self):
            if self.quick_current_path != self.quick_preview_path:
                return
            self.quick_editor.blockSignals(True)
            self.quick_editor.setPlainText(self.display_json(self.value_at(self.quick_current_path)))
            self.quick_editor.setReadOnly(False)
            self.quick_editor.blockSignals(False)
            self.quick_preview_path = None
            self.quick_full_button.setEnabled(False)

        def quick_text_changed(self):
            self.quick_dirty = True
            self.update_status()

        def stage_quick_node(self):
            if not self.quick_dirty:
                return True
            if self.quick_preview_path == self.quick_current_path:
                return False
            try:
                before = self.value_at(self.quick_current_path)
                shown = core.strict_json(self.quick_editor.toPlainText())
                value = core.restore_keys(shown, before)
                if value != before:
                    bases = self.value_at(self.quick_current_path[:-1])
                    bases[self.quick_current_path[-1]] = value
                    self.modified = True
                    player = self.value_at(self.quick_current_path[:-2])
                    info = core.base_info(value, self.quick_current_path[-1], player)
                    item = self.find_quick_item(self.quick_current_path)
                    if item is not None:
                        for column, text in enumerate((info['name'], str(info['index']),
                                                       info['type'], str(info['object_count']))):
                            item.setText(column, text)
                    self.quick_heading.setText(
                        f"Base {info['index']} · {info['name']} · {info['type']}")
                self.quick_dirty = False
                self.update_status()
                return True
            except Exception as exc:
                QtWidgets.QMessageBox.warning(self, 'Invalid base JSON', str(exc))
                return False

        def stage_current_node(self):
            if not self.node_dirty:
                return True
            if self.preview_path == self.current_path:
                return False
            try:
                before = self.value_at(self.current_path)
                shown = core.strict_json(self.editor.toPlainText())
                value = core.restore_keys(shown, before)
                if not self.current_path and not isinstance(value, dict):
                    raise ValueError('The save root must remain a JSON object')
                if value != before:
                    if self.current_path:
                        parent = self.value_at(self.current_path[:-1])
                        parent[self.current_path[-1]] = value
                    else:
                        self.root = value
                    self.modified = True
                    if self.current_item is not None:
                        while self.current_item.childCount():
                            self.current_item.takeChild(0)
                        if isinstance(value, (dict, list)) and value:
                            QtWidgets.QTreeWidgetItem(self.current_item, ['…'])
                        if self.current_path:
                            key = self.current_path[-1]
                            self.current_item.setText(
                                0, self.node_label(key, value, self.current_path[:-1]))
                self.node_dirty = False
                self.update_status()
                return True
            except Exception as exc:
                QtWidgets.QMessageBox.warning(self, 'Invalid JSON', str(exc))
                return False

        def make_item(self, parent, label, path, value):
            item = QtWidgets.QTreeWidgetItem(parent, [str(label)]) if parent else QtWidgets.QTreeWidgetItem([str(label)])
            item.setData(0, QtCore.Qt.UserRole, path)
            item.setIcon(0, self.folder_icon if isinstance(value, (dict, list)) else self.field_icon)
            if path and isinstance(path[-1], str) and core.readable_key(path[-1]) != path[-1]:
                item.setToolTip(0, f'Game key: {path[-1]}')
            if isinstance(value, (dict, list)) and value:
                QtWidgets.QTreeWidgetItem(item, ['…'])
            return item

        def expand_item(self, item):
            path = item.data(0, QtCore.Qt.UserRole)
            if path is None or item.childCount() != 1 or item.child(0).data(0, QtCore.Qt.UserRole) is not None:
                return
            item.takeChild(0)
            self.append_children(item, 0)

        def append_children(self, item, start):
            path = item.data(0, QtCore.Qt.UserRole)
            value = self.value_at(path)
            stop = min(len(value), start + 200)
            entries = (itertools.islice(value.items(), start, stop) if isinstance(value, dict)
                       else enumerate(value[start:stop], start))
            for key, child in entries:
                label = self.node_label(key, child, path)
                self.make_item(item, label, path + (key,), child)
            if stop < len(value):
                more = QtWidgets.QTreeWidgetItem(item, [f'Show next 200 of {len(value):,}…'])
                more.setData(0, QtCore.Qt.UserRole + 1, stop)

        def node_label(self, key, value, parent_path=()):
            if (type(key) is int and parent_path and
                    core.readable_key(parent_path[-1]) == 'PersistentPlayerBases'):
                player = self.value_at(parent_path[:-1])
                info = core.base_info(value, key, player)
                return f"{key} · {info['name']} · {info['type']}"
            return str(core.readable_key(key)) if isinstance(key, str) else str(key)

        def show_node(self, path, item):
            self.current_path, self.current_item = path, item
            self.advanced_rendered = True
            value = self.value_at(path)
            compact = json.dumps(value, ensure_ascii=False)
            large = len(compact) > 1_000_000
            self.preview_path = path if large else None
            self.editor.blockSignals(True)
            if large:
                self.editor.setPlainText(self.preview_json(value))
                self.editor.setReadOnly(True)
            else:
                self.editor.setPlainText(self.display_json(value))
                self.editor.setReadOnly(False)
            self.editor.blockSignals(False)
            self.node_dirty = False
            self.path_search.setText('.'.join(str(core.readable_key(part)) for part in path))
            self.update_status()

        @staticmethod
        def display_json(value):
            display = json.dumps(core.readable(value), indent=2, ensure_ascii=False)
            # Render undecodable source bytes as editable \udcXX JSON escapes;
            # Qt cannot display lone surrogate code points directly.
            return display.encode('utf-8', errors='backslashreplace').decode('utf-8')

        @staticmethod
        def preview_json(value, limit=120_000):
            """Show the beginning of large JSON immediately, without loading it into Qt."""
            pieces = []
            length = 0
            truncated = False
            for piece in json.JSONEncoder(indent=2, ensure_ascii=False).iterencode(core.readable(value)):
                remaining = limit - length
                if len(piece) > remaining:
                    pieces.append(piece[:remaining])
                    truncated = True
                    break
                pieces.append(piece)
                length += len(piece)
                if length >= limit:
                    truncated = True
                    break
            display = ''.join(pieces)
            if truncated:
                display += '\n\n… Preview only. Select a folder or click Load Full JSON for This Node to edit the whole section.'
            return display.encode('utf-8', errors='backslashreplace').decode('utf-8')

        def load_full_node(self):
            if self.preview_path != self.current_path:
                return
            self.editor.blockSignals(True)
            self.editor.setPlainText(self.display_json(self.value_at(self.current_path)))
            self.editor.setReadOnly(False)
            self.editor.blockSignals(False)
            self.preview_path = None
            self.update_status()

        def select_item(self, item, old):
            if self._selecting or item is None:
                return
            more = item.data(0, QtCore.Qt.UserRole + 1)
            if more is not None:
                parent = item.parent()
                parent.removeChild(item)
                self.append_children(parent, more)
                self._selecting = True
                self.tree.setCurrentItem(parent)
                self._selecting = False
                return
            path = item.data(0, QtCore.Qt.UserRole)
            if path is None:
                return
            if self.node_dirty and not self.stage_current_node():
                self._selecting = True
                self.tree.setCurrentItem(old)
                self._selecting = False
                return
            self.show_node(path, item)

        def text_changed(self):
            self.node_dirty = True
            self.update_status()

        def apply_node(self):
            return self.stage_current_node()

        def update_status(self):
            message = (f'{self.path.name}  ·  ' +
                       ('Source changed: refresh required' if self.stale else
                        'JSON edit held in window; file unchanged' if (self.node_dirty or self.quick_dirty) else
                        'Unsaved draft; file unchanged' if self.modified else 'Read only until edited'))
            self.status.setText(message)
            self.quick_status.setText(message)
            self.save_button.setEnabled((self.modified or self.node_dirty or self.quick_dirty) and not self.stale)
            self.quick_save_button.setEnabled((self.modified or self.node_dirty or self.quick_dirty) and not self.stale)
            self.load_full_button.setEnabled(
                self.preview_path is not None and self.preview_path == self.current_path)

        def check_source(self):
            if self.stale or not self.expected:
                return
            try:
                if core.game_running():
                    self.stale = True
                    self.update_status()
                    return
                stale = core.changed(self.expected, self.stats)
            except Exception:
                stale = True
            if stale:
                self.stale = True
                self.update_status()
                QtWidgets.QMessageBox.warning(
                    self, 'Save changed on disk',
                    'This save changed since opening. Saving is disabled. Use Refresh from Disk '
                    'after resolving any unsaved changes.')

        def refresh(self):
            if not self.leave_current():
                return
            self.load_file(self.path)

        def save_file(self, _checked=False, quiet=False):
            if (self.node_dirty and not self.stage_current_node()) or (
                    self.quick_dirty and not self.stage_quick_node()):
                return False
            if not self.modified:
                return True
            try:
                backup = core.commit(self.path, self.root, self.expected, self.backup_root)
                self.load_file(self.path)
                if not quiet:
                    QtWidgets.QMessageBox.information(
                        self, 'Raw JSON saved', 'Saved and verified. Backup: ' + backup +
                        '\nRefresh the Save Manager in Blender to update its list.')
                return True
            except Exception as exc:
                self.stale = 'changed' in str(exc).lower()
                self.update_status()
                QtWidgets.QMessageBox.critical(self, 'Save refused', str(exc))
                return False

        def jump_to_path(self):
            raw = self.path_search.text().strip()
            parts = [part for part in re.split(r'\.|\[|\]', raw) if part]
            item = self.tree.topLevelItem(0)
            value = self.root
            try:
                for token in parts:
                    key = int(token) if isinstance(value, list) else token
                    if isinstance(value, dict) and key not in value:
                        key = core.KEY_IDS.get(token, token)
                    value = value[key]
                    item.setExpanded(True)
                    target = item.data(0, QtCore.Qt.UserRole) + (key,)
                    found = next((child for child in (item.child(i) for i in range(item.childCount()))
                                  if child.data(0, QtCore.Qt.UserRole) == target), None)
                    if found is None:
                        label = self.node_label(key, value, item.data(0, QtCore.Qt.UserRole))
                        found = self.make_item(item, label, target, value)
                    item = found
                self.tree.setCurrentItem(item)
            except (KeyError, IndexError, StopIteration, ValueError, TypeError):
                QtWidgets.QMessageBox.information(self, 'Path not found', raw)

        def find_text(self):
            query = self.text_search.text()
            if query and not self.editor.find(query):
                self.editor.moveCursor(QtGui.QTextCursor.Start)
                self.editor.find(query)

        def keyPressEvent(self, event):
            if event.matches(QtGui.QKeySequence.Find):
                self.text_search.setFocus()
                self.text_search.selectAll()
                return
            super().keyPressEvent(event)

        def closeEvent(self, event):
            if self.leave_current(reload_discard=False):
                event.accept()
            else:
                event.ignore()

    app = QtWidgets.QApplication(sys.argv)
    parent = ParentLifetime(args.parent_pid) if args.parent_pid else None
    if parent is not None:
        def check_parent():
            if parent.alive():
                return
            parent_timer.stop()
            for widget in app.topLevelWidgets():
                if isinstance(widget, RawWindow):
                    widget.parent_exited = True
                if isinstance(widget, QtWidgets.QDialog):
                    widget.reject()
                else:
                    widget.close()
            if not any(isinstance(widget, RawWindow) and widget.isVisible()
                       for widget in app.topLevelWidgets()):
                app.quit()
        parent_timer = QtCore.QTimer(app)
        parent_timer.timeout.connect(check_parent)
        parent_timer.start(1000)
    try:
        core.require_game_closed()
    except Exception as exc:
        QtWidgets.QMessageBox.critical(None, 'Raw JSON editor unavailable', str(exc))
        return 1
    warning = QtWidgets.QMessageBox.warning(
        None, 'Advanced users only',
        'This editor changes the selected save’s raw JSON. BBE checks syntax and creates a backup '
        'before saving, but cannot verify every game value. Continue only if you understand the save structure. '
        'Improper use may cause save file to become corrupt.',
        QtWidgets.QMessageBox.Ok | QtWidgets.QMessageBox.Cancel, QtWidgets.QMessageBox.Cancel)
    if warning != QtWidgets.QMessageBox.Ok:
        return 0
    try:
        window = RawWindow()
    except Exception as exc:
        QtWidgets.QMessageBox.critical(None, 'Raw JSON unavailable', str(exc))
        return 1
    window.show()
    return app.exec()


if __name__ == '__main__':
    raise SystemExit(main())
