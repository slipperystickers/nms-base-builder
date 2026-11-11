"""Rotating, independent .blend recovery copies for BBE projects.

Only Blender's main thread runs the timer and save operator. Recovery copies
live under the shared backup folder, never beside or over a project file.
"""
from .furby_errors import report_error
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from uuid import uuid4

import bpy
from . import icons
from bpy.app.handlers import persistent

from . import undo_guard
from .save_editor import backup_policy

_session = uuid4().hex
_last_file = None
_last_count = None
_pending_parts = 0
_last_backup = time.monotonic()
_last_change = 0.0
_busy = False
_last_error = ''
_retry_at = 0.0
_status_popups = set()
_SLOT_NAMES = ('recovery-1.blend', 'recovery-2.blend', 'recovery-3.blend')


def _preferences():
    addon = bpy.context.preferences.addons.get(__package__)
    return addon.preferences if addon else None


def _root():
    return backup_policy.root_directory() / 'Projects'


def _legacy_root():
    """Keep recovery copies from older releases visible without moving them."""
    return Path(bpy.utils.user_resource('CONFIG', path='bbe_recovery', create=False)).resolve()


def _recovery_roots():
    return tuple(dict.fromkeys((_root(), _legacy_root())))


def _project():
    source = bpy.data.filepath
    if source:
        normalized = os.path.normcase(os.path.abspath(source))
        key = hashlib.sha256(normalized.encode('utf-8')).hexdigest()[:20]
        label = Path(source).stem
    else:
        key = 'unsaved-' + _session
        label = 'Untitled'
    return key, label, source


def _folder():
    key, _, _ = _project()
    return _root() / key


def _part_count():
    # Match the builder's logical count so grouped prefabs also count toward
    # the placement trigger, without counting display/helper objects.
    return sum((1 if 'ObjectID' in obj else 0)
               + (max(0, int(obj.get('part_count', 0))) if 'GroupID' in obj else 0)
               for scene in bpy.data.scenes for obj in scene.objects)


def _reset():
    global _last_file, _last_count, _pending_parts, _last_backup, _last_change, _last_error, _retry_at
    _last_file = bpy.data.filepath
    _last_count = _part_count()
    _pending_parts = 0
    _last_backup = time.monotonic()
    _last_change = 0.0
    _last_error = ''
    _retry_at = 0.0


def _wait_reason():
    wm = bpy.context.window_manager
    if _busy:
        return 'Saving recovery copy'
    if not undo_guard.history_ready():
        return 'Waiting for undo/redo'
    if wm is None or wm.is_interface_locked:
        return 'Waiting for Blender'
    if bpy.context.mode != 'OBJECT':
        return 'Waiting for Object Mode'
    if bpy.app.is_job_running('RENDER'):
        return 'Waiting for render'
    for window in wm.windows:
        for operator in window.modal_operators:
            if operator.bl_idname.startswith(('TRANSFORM_OT_', 'SCULPT_OT_', 'PAINT_OT_')):
                return 'Waiting for current edit'
    return ''


def _safe_to_save():
    return not _wait_reason()


def _redraw_controls():
    # Popovers need a UI refresh, not just a viewport/header redraw. Validate
    # temporary regions before touching them, as Blender's extension notifier
    # does: closed popup regions do not invalidate their Python wrappers.
    for window, region in tuple(_status_popups):
        try:
            with bpy.context.temp_override(window=window, region=region):
                region.tag_redraw()
                region.tag_refresh_ui()
        except (TypeError, ReferenceError, RuntimeError):
            _status_popups.discard((window, region))
    wm = bpy.context.window_manager
    if wm:
        for window in wm.windows:
            for area in window.screen.areas:
                if area.type == 'VIEW_3D':
                    for region in area.regions:
                        if region.type in {'UI', 'HEADER', 'TOOL_HEADER', 'TEMPORARY'}:
                            region.tag_redraw()


def _record_failure(exc):
    global _last_error, _retry_at
    _last_error = str(exc) or type(exc).__name__
    _retry_at = time.monotonic() + 60.0
    print('BBE recovery backup failed:', _last_error)


def _status(prefs):
    if _busy:
        return 'Saving recovery copy'
    if prefs is None or prefs.bbe_recovery_mode == 'OFF':
        return 'Automatic recovery is off'
    now = time.monotonic()
    if _last_error:
        return f'Backup failed; retry in {max(0, int(_retry_at - now))}s'
    if prefs.bbe_recovery_mode == 'TIME':
        remaining = max(0, int(prefs.bbe_recovery_minutes * 60 - (now - _last_backup)))
        if remaining:
            return f'Next backup in {remaining // 60}:{remaining % 60:02d}'
    elif _pending_parts < prefs.bbe_recovery_parts:
        return f'Parts placed: {_pending_parts}/{prefs.bbe_recovery_parts}'
    return _wait_reason() or 'Backup due; waiting for idle'


def _backup_files(folder):
    # An interrupted save may leave a partial file. Never offer it for
    # recovery or count it as one of the three completed generations.
    return [p for p in folder.glob('*.blend') if not p.name.startswith('.partial-')]


def _next_slot(folder):
    """Reuse three fixed slots, including backups made before slot rotation."""
    slots = tuple(folder / name for name in _SLOT_NAMES)
    existing = _backup_files(folder)
    if any(path not in slots for path in existing):
        # Earlier releases used timestamp names. Rename the newest three into
        # slots without copying large .blend files. Staged names remain valid
        # recovery files if Blender stops midway through the migration.
        keep = sorted(existing, key=lambda p: p.stat().st_mtime_ns)[-3:]
        staged = []
        for path in keep:
            temporary = folder / ('.rotate-' + uuid4().hex + '.blend')
            os.replace(path, temporary)
            staged.append(temporary)
        for target, temporary in zip(slots, staged):
            os.replace(temporary, target)
        for old in existing:
            if old not in slots and old.exists():
                old.unlink()
    for slot in slots:
        if not slot.exists():
            return slot
    return min(slots, key=lambda p: p.stat().st_mtime_ns)


def _snapshot():
    """Save to a temporary file, then atomically replace the next slot."""
    global _busy, _last_backup, _pending_parts, _last_error, _retry_at
    folder = _folder()
    folder.mkdir(parents=True, exist_ok=True)
    target = _next_slot(folder)
    partial = folder / ('.partial-' + uuid4().hex + '.blend')
    prior_path = bpy.data.filepath
    _busy = True
    try:
        result = bpy.ops.wm.save_as_mainfile(filepath=str(partial), copy=True,
                                             relative_remap=False, check_existing=False)
        if result != {'FINISHED'} or not partial.is_file() or partial.stat().st_size < 100:
            raise RuntimeError('Blender did not produce a recovery copy')
        if bpy.data.filepath != prior_path:
            raise RuntimeError('Recovery copy changed the active project path')
        os.replace(partial, target)
        key, label, source = _project()
        metadata = folder / 'project.json'
        metadata_tmp = folder / '.project.json.tmp'
        metadata_tmp.write_text(json.dumps({'label': label, 'source': source}), encoding='utf-8')
        os.replace(metadata_tmp, metadata)
        _last_backup = time.monotonic()
        _pending_parts = 0
        _last_error = ''
        _retry_at = 0.0
        return target
    finally:
        _busy = False
        if partial.exists():
            partial.unlink()


def tick():
    global _last_file, _last_count, _pending_parts, _last_change, _last_backup
    try:
        if not _safe_to_save():
            return 2.0
        if bpy.data.filepath != _last_file:
            _reset()
            return 2.0
        if _last_count is None:
            # Establish counts after load without postponing the load-time deadline.
            _last_count = _part_count()
        now = time.monotonic()
        count = _part_count()
        if count != _last_count:
            if count > _last_count:
                _pending_parts += count - _last_count
            else:
                _pending_parts = 0
            _last_count = count
            _last_change = now
        prefs = _preferences()
        if prefs is None or prefs.bbe_recovery_mode == 'OFF':
            return 2.0
        due = ((prefs.bbe_recovery_mode == 'TIME'
                and now - _last_backup >= prefs.bbe_recovery_minutes * 60)
               or (prefs.bbe_recovery_mode == 'PARTS'
                   and _pending_parts >= prefs.bbe_recovery_parts))
        if due and now >= _retry_at and now - _last_change >= 3.0:
            _snapshot()
    except Exception as exc:
        _record_failure(exc)
    finally:
        _redraw_controls()
    return 2.0


@persistent
def after_load(_):
    global _last_file, _last_count, _last_backup, _pending_parts, _last_change, _last_error, _retry_at
    # Other load handlers may rebuild display objects. Take the baseline on
    # the first idle tick after all of them have finished.
    _last_count = None
    _last_file = bpy.data.filepath
    _last_backup = time.monotonic()
    _pending_parts = 0
    _last_change = 0.0
    _last_error = ''
    _retry_at = 0.0
    _status_popups.clear()


@persistent
def after_save(_):
    # Save-copy operations (including other autosave add-ons) fire save_post
    # too. Only a changed project path should restart our independent schedule.
    if not _busy and bpy.data.filepath != _last_file:
        _reset()


def _backups():
    current = _folder()
    folders = [current] if current.is_dir() else []
    for root in _recovery_roots():
        if root.is_dir():
            folders.extend(p for p in root.iterdir() if p.is_dir() and p != current)
    entries = []
    for folder in folders:
        meta = folder / 'project.json'
        try:
            label = json.loads(meta.read_text(encoding='utf-8')).get('label', 'Project')
        except (OSError, ValueError):
            label = 'Project'
        for path in _backup_files(folder):
            entries.append((path, label, folder == current))
    entries.sort(key=lambda row: (not row[2], -row[0].stat().st_mtime))
    return entries[:12]


class BBE_MT_recovery(bpy.types.Menu):
    bl_idname = 'BBE_MT_recovery'
    bl_label = 'Open Recovery Copy'

    def draw(self, context):
        from .save_editor.function_help import corner_help
        corner_help(self.layout, 'RECOVERY')
        entries = _backups()
        if not entries:
            self.layout.label(text='No recovery copies yet', **icons.ui_icon('INFO'))
        for path, label, current in entries:
            date = time.strftime('%b %d, %I:%M %p', time.localtime(path.stat().st_mtime))
            text = f'{label} - {date}'
            op = self.layout.operator('bbe.open_recovery', text=text,
                                      **icons.ui_icon('RECOVER_LAST' if current else 'FILE_BLEND'))
            op.filepath = str(path)


class BBE_OT_open_recovery(bpy.types.Operator):
    bl_idname = 'bbe.open_recovery'
    bl_label = 'Open Recovery Copy'
    bl_description = 'Open this recovery copy; save the current project first if needed'

    filepath: bpy.props.StringProperty(subtype='FILE_PATH')

    def invoke(self, context, event):
        return context.window_manager.invoke_confirm(self, event)

    def execute(self, context):
        path = Path(self.filepath).resolve()
        if (path.suffix.lower() != '.blend'
                or not any(root in path.parents for root in _recovery_roots())
                or not path.is_file()):
            report_error(self, {'ERROR'}, 'Recovery copy is missing or outside the backup folder')
            return {'CANCELLED'}
        return bpy.ops.wm.open_mainfile(filepath=str(path))


class BBE_OT_recovery_now(bpy.types.Operator):
    bl_idname = 'bbe.recovery_now'
    bl_label = 'Create Recovery Copy Now'

    def execute(self, context):
        if not _safe_to_save():
            self.report({'WARNING'}, 'Wait for the current edit or undo to finish')
            return {'CANCELLED'}
        try:
            path = _snapshot()
        except Exception as exc:
            _record_failure(exc)
            report_error(self, {'ERROR'}, f'Recovery copy failed: {exc}')
            return {'CANCELLED'}
        self.report({'INFO'}, f'Recovery copy saved: {path}')
        return {'FINISHED'}


class BBE_OT_open_backup_root(bpy.types.Operator):
    bl_idname = 'bbe.open_backup_root'
    bl_label = 'Open Backup Folder'
    bl_description = 'Open the shared folder for project recovery and game-save backups'

    def execute(self, context):
        try:
            root = backup_policy.root_directory()
            root.mkdir(parents=True, exist_ok=True)
            if sys.platform == 'win32':
                os.startfile(str(root))
            elif sys.platform == 'darwin':
                subprocess.Popen(['open', str(root)])
            else:
                subprocess.Popen(['xdg-open', str(root)])
        except (OSError, ValueError) as exc:
            report_error(self, {'ERROR'}, f'Could not open backup folder: {exc}')
            return {'CANCELLED'}
        return {'FINISHED'}


def draw_controls(layout, context, *, boxed=True):
    popup = getattr(context, 'region_popup', None)
    if popup is not None and context.window is not None:
        _status_popups.add((context.window, popup))
    prefs = _preferences()
    box = layout.box() if boxed else layout
    from .save_editor.function_help import corner_help
    header = box.row(align=True)
    if boxed:
        header.label(text='Project Recovery', **icons.ui_icon('RECOVER_LAST'))
    else:
        header.label(text='Keeps the last 3 recovery saves')
    corner_help(header, 'RECOVERY')
    if prefs:
        schedule = box.split(factor=0.60, align=True)
        schedule.prop(prefs, 'bbe_recovery_mode', text='')
        if prefs.bbe_recovery_mode == 'TIME':
            schedule.prop(prefs, 'bbe_recovery_minutes', text='Minutes')
        elif prefs.bbe_recovery_mode == 'PARTS':
            schedule.prop(prefs, 'bbe_recovery_parts', text='Qty')
        else:
            schedule.label(text='Manual only')
    if boxed:
        box.label(text='Keeps the last 3 recovery saves')
    status = box.row()
    status.alert = bool(_last_error)
    status.label(text=_status(prefs))
    if _last_error:
        error = box.row()
        error.alert = True
        error.label(text=_last_error, **icons.ui_icon('ERROR'))
    row = box.row(align=True)
    row.operator('bbe.recovery_now', text='Back Up Now', **icons.ui_icon('FILE_TICK'))
    row.menu('BBE_MT_recovery', text='Open Recovery...', **icons.ui_icon('FILE_FOLDER'))
    row = box.row(align=True)
    row.operator('bbe.open_backup_root', text='Open Backup Folder', **icons.ui_icon('FOLDER_REDIRECT'))
    row.operator_context = 'INVOKE_DEFAULT'
    row.operator('bbe.backup_settings', text='Change Folder...', **icons.ui_icon('PREFERENCES'))


_classes = (BBE_MT_recovery, BBE_OT_open_recovery, BBE_OT_recovery_now,
            BBE_OT_open_backup_root)


def register():
    for cls in _classes:
        bpy.utils.register_class(cls)
    # Registration runs with restricted bpy.data; the first timer establishes
    # the project baseline after Blender restores normal context access.
    if after_load not in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.append(after_load)
    if after_save not in bpy.app.handlers.save_post:
        bpy.app.handlers.save_post.append(after_save)
    if not bpy.app.timers.is_registered(tick):
        bpy.app.timers.register(tick, first_interval=2.0, persistent=True)


def unregister():
    _status_popups.clear()
    if bpy.app.timers.is_registered(tick):
        bpy.app.timers.unregister(tick)
    for handlers, callback in ((bpy.app.handlers.load_post, after_load),
                               (bpy.app.handlers.save_post, after_save)):
        if callback in handlers:
            handlers.remove(callback)
    for cls in reversed(_classes):
        bpy.utils.unregister_class(cls)
