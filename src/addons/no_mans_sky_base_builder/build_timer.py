"""Local active building time. Game saves contain no timer fields."""
from . import i18n
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import time
from uuid import uuid4

import bpy
from bpy.app.handlers import persistent
from . import undo_guard
from .utils.asset_browser_utils import get_user_data_directory

SCENE_KEY = "bbe_build_timer_key"
CHECKPOINT = 10
_active = None
_last_edit = _accounted = _last_flush = 0.0
_pending = {}
_totals = {}
_clock_error = False
_scene_id = None
_parts = {}
_dirty = set()
_structure = True
_last_display = None
_status_popups = set()


def _key(links, context, kind, anchor):
    slot = sorted(os.path.normcase(os.path.abspath(p)) for p in links if p)
    if not slot:
        return None
    identity = json.dumps([slot, context or 'Main', kind, anchor], separators=(',', ':'))
    return hashlib.sha256(identity.encode()).hexdigest()


def ship_key(links, context, index):
    return _key(links, context, 'PlayerShipBase', index)


def base_key(base, links):
    if base is None:
        return None
    if base.base_type == 'PlayerShipBase':
        return ship_key(links, base.save_context, base.user_data)
    position = getattr(base, 'base_position', None)
    anchor = [str(base.galactic_address), position if position is not None else base.base_name]
    return _key(links, base.save_context, base.base_type, anchor)


def selected_key(data):
    if not data or not data.check_plugin_enabled:
        return None
    base = data.get_current_base_identifiers()
    return base_key(base, base.save_slot) if base else None


# Save guidance uses the imported destination separately from the activity timer.
# Navigating to another slot must never associate the current scene with that slot.
_BASELINE = 'bbe_save_baseline'
_DESTINATION = 'bbe_save_destination'
_parts_digest = {}


def parts_digest(scene):
    if scene.session_uid not in _parts_digest:
        try:
            # This comparison also runs in Blender's read-only panel draw context.
            from . import BUILDER
            with bpy.context.temp_override(scene=scene):
                records = BUILDER.object_records(read_only=True)
        except (RuntimeError, ValueError, KeyError):
            return None  # An unexportable edit still needs attention.
        payload = json.dumps(records, sort_keys=True, separators=(',', ':'))
        _parts_digest[scene.session_uid] = hashlib.sha256(payload.encode()).hexdigest()
    return _parts_digest[scene.session_uid]


def save_signature(scene):
    from .build_metadata import save_owner
    properties = scene.nms_base_tool
    fields = [parts_digest(scene), properties.string_base, save_owner(properties)]
    if scene.get('bbe_optimizer_order_revision'):
        fields.append(scene['bbe_optimizer_order_revision'])
    return json.dumps(fields, sort_keys=True)


def mark_saved(scene, key):
    if key:
        _parts_digest.pop(scene.session_uid, None)
        scene[_DESTINATION] = key
        scene[_BASELINE] = save_signature(scene)


def next_save_action(scene):
    data = scene.nms_save_data
    key = selected_key(data)
    if not key:
        return ''
    if scene.get(_DESTINATION) != key:
        return 'object.nms_import_base_from_save'
    if save_signature(scene) == scene.get(_BASELINE):
        return ''
    return 'bbe.optimizer_export' if data.nms_base_type == 'PlayerShipBase' else 'object.nms_export_base_to_save'


def _open_db():
    folder = Path(get_user_data_directory())
    folder.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(folder / 'build-time.sqlite3', timeout=.1)
    db.execute('CREATE TABLE IF NOT EXISTS builds (id TEXT PRIMARY KEY, seconds REAL NOT NULL, updated INTEGER NOT NULL)')
    return db


def _flush(merge=None):
    global _clock_error
    if not _pending and not merge:
        return True
    db = None
    try:
        db = _open_db()
        with db:
            db.executemany("INSERT INTO builds VALUES (?, ?, strftime('%s','now')) ON CONFLICT(id) DO UPDATE "
                           'SET seconds = seconds + excluded.seconds, updated = excluded.updated', _pending.items())
            if merge:
                draft, target = merge
                db.execute('INSERT INTO builds SELECT ?, seconds, updated FROM builds WHERE id = ? '
                           'ON CONFLICT(id) DO UPDATE SET seconds = seconds + excluded.seconds',
                           (target, draft))
                db.execute('DELETE FROM builds WHERE id = ?', (draft,))
        for key in _pending:
            _totals.pop(key, None)
        if merge:
            for key in merge:
                _totals.pop(key, None)
        _pending.clear()
        _clock_error = False
        return True
    except (OSError, sqlite3.Error) as exc:
        if not _clock_error:
            print(f'BBE build timer: {exc}')
        _clock_error = True
        return False
    finally:
        if db is not None:
            db.close()


def _advance(now, timeout):
    global _accounted, _active
    if _active is None:
        return
    end = min(now, _last_edit + timeout)
    if end > _accounted:
        _pending[_active] = _pending.get(_active, 0.) + end - _accounted
        _accounted = end
    if now >= _last_edit + timeout:
        _active = None


def _timeout():
    addon = bpy.context.preferences.addons.get(__package__)
    return 60 * getattr(addon.preferences, 'build_idle_minutes', 2) if addon else 120


def _stop():
    global _active
    _advance(time.monotonic(), _timeout())
    _active = None
    _flush()


def tracking_changed(prefs, context):
    if not prefs.build_timer_enabled:
        _stop()
    elif context.scene is not None and undo_guard.history_ready():
        # Edits made while paused belong to the baseline, including changes since the last tick.
        _scan(context.scene, baseline=True)


def bind(scene, key):
    """Attach draft time on first association. Copies start their own destination clock."""
    if not key or scene.get(SCENE_KEY) == key:
        return
    old = scene.get(SCENE_KEY, '')
    _stop()
    if old.startswith('draft:') and not _flush((old, key)):
        return
    scene[SCENE_KEY] = key


def _activity(scene, now):
    global _active, _last_edit, _accounted
    key = scene.get(SCENE_KEY)
    if not key or key.startswith('draft:'):
        target = selected_key(getattr(scene, 'nms_save_data', None))
        if target:
            bind(scene, target)
            key = scene.get(SCENE_KEY)
        if not key:
            key = 'draft:' + uuid4().hex
            scene[SCENE_KEY] = key
    _advance(now, _timeout())
    _active, _last_edit, _accounted = key, now, now


def _state(obj):
    if obj is None or ('ObjectID' not in obj and 'GroupID' not in obj):
        return None
    return (obj.get('ObjectID'), obj.get('GroupID'), str(obj.get('UserData', '')),
            tuple(value for row in obj.matrix_world for value in row))


def _scan(scene, baseline=False):
    global _structure
    changed = False
    if _structure or baseline:
        names = {o.name for o in scene.objects if 'ObjectID' in o or 'GroupID' in o}
        gone = _parts.keys() - names
        changed = bool(gone)
        for name in gone:
            del _parts[name]
        _dirty.update(names - _parts.keys())
        _structure = False
    for name in _dirty:
        state = _state(scene.objects.get(name))
        if state != _parts.get(name):
            changed = True
            if state is None:
                _parts.pop(name, None)
            else:
                _parts[name] = state
    _dirty.clear()
    return changed and not baseline


@persistent
def changed(scene, graph):
    global _structure
    if scene != bpy.context.scene or not undo_guard.history_ready():
        return
    if not (graph.id_type_updated('OBJECT') or graph.id_type_updated('COLLECTION')):
        return
    _parts_digest.pop(scene.session_uid, None)
    screen = bpy.context.screen
    if screen and screen.is_animation_playing:
        return
    for update in graph.updates:
        obj = update.id
        if isinstance(obj, bpy.types.Object):
            if 'ObjectID' in obj or 'GroupID' in obj or obj.name in _parts:
                _dirty.add(obj.name)
        elif isinstance(obj, bpy.types.Collection):
            _structure = True


def tick():
    global _scene_id, _last_flush, _last_display
    scene = bpy.context.scene
    if scene is None or not undo_guard.history_ready():
        return 1
    now = time.monotonic()
    if scene.as_pointer() != _scene_id:
        reset()
        _scene_id = scene.as_pointer()
        _scan(scene, baseline=True)
    elif _scan(scene):
        addon = bpy.context.preferences.addons.get(__package__)
        if addon is None or addon.preferences.build_timer_enabled:
            _activity(scene, now)
    _advance(now, _timeout())
    if now - _last_flush >= CHECKPOINT:
        _flush()
        _last_flush = now
    display = (_active, int(_accounted), _clock_error)
    if display != _last_display:
        _last_display = display
        for window, region in tuple(_status_popups):
            # Blender caches open header popovers separately from the header.
            # Validate the temporary region before using it after a menu closes.
            try:
                with bpy.context.temp_override(window=window, region=region):
                    region.tag_redraw()
                    region.tag_refresh_ui()
            except (TypeError, ReferenceError, RuntimeError):
                _status_popups.discard((window, region))
        for window in bpy.context.window_manager.windows:
            for area in window.screen.areas:
                if area.type == 'VIEW_3D' and area.spaces.active.show_region_ui:
                    for region in area.regions:
                        if region.type == 'UI':
                            region.tag_redraw()
    return 1


def label(scene, key=None):
    global _clock_error
    key = key or scene.get(SCENE_KEY)
    seconds = 0
    if key:
        if key not in _totals:
            db = None
            try:
                db = _open_db()
                row = db.execute('SELECT seconds FROM builds WHERE id=?', (key,)).fetchone()
                _totals[key] = row[0] if row else 0
            except (OSError, sqlite3.Error):
                _clock_error = True
            finally:
                if db is not None:
                    db.close()
        seconds = int(_totals.get(key, 0) + _pending.get(key, 0))
    if _clock_error:
        return 'Build time unavailable'
    hours, remainder = divmod(seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    return f'Build {hours:d}:{minutes:02d}:{seconds:02d}'


def draw_status(layout, scene, key=None, prefix=''):
    context = bpy.context
    popup = getattr(context, 'region_popup', None)
    if popup is not None and context.window is not None:
        _status_popups.add((context.window, popup))
    key = key or scene.get(SCENE_KEY)
    elapsed = label(scene, key)
    running = key is not None and key == _active
    from . import i18n
    status = i18n.interface('Building {time}' if running else 'Paused {time}').format(time=elapsed.removeprefix('Build '))
    layout.label(text=prefix + (elapsed if _clock_error else status), icon='TIME')


def draw_labeled(layout, scene, key=None, prefix=''):
    key = key or scene.get(SCENE_KEY)
    if not key:
        return
    label(scene, key)  # Populate persisted time before deciding visibility.
    if _totals.get(key, 0) + _pending.get(key, 0) <= 0 and key != _active:
        return
    from . import i18n
    row = layout.row(align=True)
    row.alignment = 'RIGHT'
    draw_status(row, scene, key, i18n.interface('Build timer') + '  ' + prefix)


_drafts = []


class BBE_OT_recover_draft_time(bpy.types.Operator):
    bl_idname = 'bbe.recover_draft_time'
    bl_translation_context = "BBEExtendedInterface"
    bl_label = 'Recover Draft Time'
    bl_description = 'Add time from an unsaved, unassigned draft to the current build'

    draft: bpy.props.EnumProperty(translation_context="BBEExtendedInterface", name='Draft', items=lambda self, context: _drafts)

    def invoke(self, context, event):
        _advance(time.monotonic(), _timeout())
        _flush()
        _drafts.clear()
        db = None
        try:
            db = _open_db()
            for key, seconds, stamp in db.execute(
                    "SELECT id, seconds, updated FROM builds WHERE id LIKE 'draft:%' "
                    "AND id != ? ORDER BY updated DESC", (context.scene.get(SCENE_KEY, ''),)):
                when = time.strftime('%b %d %Y, %I:%M %p', time.localtime(stamp))
                minutes, sec = divmod(int(seconds), 60)
                _drafts.append((key, f'{when}  ({minutes}m {sec}s)', 'Last active on this computer'))
        except (OSError, sqlite3.Error) as exc:
            self.report({'ERROR'}, str(exc))
            return {'CANCELLED'}
        finally:
            if db is not None:
                db.close()
        if not _drafts:
            self.report({'INFO'}, 'No other draft time to recover on this computer')
            return {'CANCELLED'}
        self.draft = _drafts[0][0]
        return context.window_manager.invoke_props_dialog(self, width=380)

    def draw(self, context):
        i18n.localized_layout(self.layout).prop(self, 'draft')
        i18n.localized_layout(self.layout).label(text='Add this time to the current build timer.')

    def execute(self, context):
        scene = context.scene
        key = scene.get(SCENE_KEY) or selected_key(scene.nms_save_data) or 'draft:' + uuid4().hex
        if not self.draft.startswith('draft:') or self.draft == key:
            return {'CANCELLED'}
        _stop()
        if not _flush((self.draft, key)):
            self.report({'ERROR'}, 'Could not save the recovered time')
            return {'CANCELLED'}
        scene[SCENE_KEY] = key
        self.report({'INFO'}, label(scene))
        return {'FINISHED'}


@persistent
def reset(*_):
    _parts_digest.clear()
    global _structure, _scene_id
    _stop()
    _scene_id = None
    _parts.clear()
    _dirty.clear()
    _structure = True
    _status_popups.clear()


@persistent
def baseline(*_):
    global _scene_id
    scene = bpy.context.scene
    if scene is not None:
        _scene_id = scene.as_pointer()
        _scan(scene, baseline=True)


def clear_build(scene):
    reset()
    for key in (_DESTINATION, _BASELINE):
        if key in scene:
            del scene[key]
    if SCENE_KEY in scene:
        del scene[SCENE_KEY]


@persistent
def history_changed(*_):
    _parts_digest.clear()
    global _structure
    _structure = True
    _dirty.update(_parts)


_HANDLERS = ((bpy.app.handlers.depsgraph_update_post, changed),
             (bpy.app.handlers.undo_post, history_changed), (bpy.app.handlers.redo_post, history_changed),
             (bpy.app.handlers.load_pre, reset), (bpy.app.handlers.load_post, baseline),
             (bpy.app.handlers.exit_pre, reset))


def register():
    bpy.utils.register_class(BBE_OT_recover_draft_time)
    for handlers, callback in _HANDLERS:
        if callback not in handlers:
            handlers.append(callback)
    if not bpy.app.timers.is_registered(tick):
        bpy.app.timers.register(tick, first_interval=.5, persistent=True)


def unregister():
    bpy.utils.unregister_class(BBE_OT_recover_draft_time)
    if bpy.app.timers.is_registered(tick):
        bpy.app.timers.unregister(tick)
    for handlers, callback in _HANDLERS:
        if callback in handlers:
            handlers.remove(callback)
    reset()
    _totals.clear()
