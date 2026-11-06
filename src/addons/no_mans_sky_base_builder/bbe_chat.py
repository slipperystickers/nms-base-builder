"""Optional BBE community chat. No network access occurs before joining.

Short-lived helper processes handle network requests. Blender state is read
and changed on the main thread by a timer. Identity stays in the profile, not a
.blend file. The service also enforces all message and file rules.
"""

import json
import os
from pathlib import Path
import re
import secrets
import subprocess
import tempfile
import time
import sys

import bpy
from . import bbe_chat_state as chat_state


_MAX_DOWNLOAD = 20 * 1024 * 1024
_MIMES = {'.png', '.jpg', '.jpeg', '.gif', '.webp', '.mp4', '.webm'}
_identity = None
_messages = []
_online = []
_contacts = []
_target = ''
_online_page = 0
_message_page = 0
_pending = ''
_pending_snapshot = False
_status = ''
_busy = None
_next_sync = 0.0
_enabled = False
_chat_enabled = False
_messenger_process = None
_prewarm_attempted = False
_last_theme = None
_toolbar_status = {}
_toolbar_status_stamp = None
_badge_previews = None
_notification_state = {}
_was_messenger_alive = False
_background_synced_at = 0.0


def _online_count():
    count = _toolbar_status.get('online') if _chat_enabled else None
    return count if type(count) is int and count >= 0 else None


def _chat_icon():
    """Load each tiny badge once; no rasterization or network work during draw."""
    global _badge_previews
    import bpy.utils.previews
    if _badge_previews is None:
        _badge_previews = bpy.utils.previews.new()
    count = _online_count()
    key = 'person' if count is None else '99plus' if count > 99 else str(count)
    if _chat_enabled and _toolbar_status.get('directed'):
        key = 'reply_' + key
    elif _chat_enabled and _toolbar_status.get('unread'):
        key = 'unread_' + key
    if key not in _badge_previews:
        _badge_previews.load(key, str(Path(__file__).parent/'resources/chat_badges'/f'{key}.png'), 'IMAGE')
    return _badge_previews[key].icon_id


def _identity_path():
    return Path(bpy.utils.user_resource('CONFIG')) / 'bbe_chat_identity.json'


def _settings_path():
    return Path(bpy.utils.user_resource('CONFIG')) / 'bbe_chat_settings.json'


def _load_chat_enabled():
    try:
        return json.loads(_settings_path().read_text(encoding='utf-8')).get('enabled') is True
    except (OSError, ValueError, AttributeError):
        return False


def _save_chat_enabled():
    target = _settings_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix('.new')
    try:
        current = json.loads(target.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        current = {}
    current['enabled'] = _chat_enabled
    temporary.write_text(json.dumps(current), encoding='utf-8')
    os.replace(temporary, target)


def _hex_color(color):
    return '#' + ''.join(f'{round(max(0, min(1, value)) * 255):02x}' for value in color[:3])


def _viewport_geometry(region_type="WINDOW"):
    # Match the largest Blender client window used by Messenger. Ignore the
    # asset-browser-only windows when choosing a modeling viewport.
    windows = list(bpy.context.window_manager.windows)
    if not windows:
        return None
    window = max(windows, key=lambda w: w.width * w.height)
    areas = [a for a in window.screen.areas if a.type == 'VIEW_3D'
             and a.spaces.active.region_3d is not None]
    if not areas or not window.width or not window.height:
        return None
    area = max(areas, key=lambda a: a.width * a.height)
    region = next((r for r in area.regions if r.type == region_type and r.height > 1), None)
    if region is None:
        return None
    return [round(region.x/window.width, 6),
            round((window.height-region.y-region.height)/window.height, 6),
            round(region.width/window.width, 6), round(region.height/window.height, 6)]


def sync_theme():
    """Share only public theme colors with the separate messenger process."""
    global _last_theme
    ui = bpy.context.preferences.themes[0].user_interface
    palette = {
        'background': _hex_color(ui.wcol_menu.inner),
        'surface': _hex_color(ui.wcol_box.inner),
        'raised': _hex_color(ui.wcol_tool.inner),
        'text': _hex_color(ui.wcol_regular.text),
        'accent': _hex_color(ui.wcol_regular.inner_sel),
        'outline': _hex_color(ui.wcol_regular.outline),
    }
    viewport = _viewport_geometry()
    toolbar = _viewport_geometry("TOOL_HEADER")
    signature = (*palette.values(), bool(getattr(bpy.app, 'online_access', False)), os.getpid(), tuple(viewport or ()), tuple(toolbar or ()))
    if signature == _last_theme:
        return
    _last_theme = signature
    target = _settings_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    try:
        current = json.loads(target.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        current = {}
    current['theme'] = palette
    current['blender_pid'] = os.getpid()
    current['chat_viewport'] = viewport
    current['chat_toolbar'] = toolbar
    current['native_chat_toolbar'] = True
    current.setdefault('enabled', _chat_enabled)
    current['online_access'] = bool(getattr(bpy.app, 'online_access', False))
    temporary = target.with_suffix('.new')
    temporary.write_text(json.dumps(current), encoding='utf-8')
    os.replace(temporary, target)


def _load_identity():
    try:
        data = json.loads(_identity_path().read_text(encoding='utf-8'))
        if isinstance(data, dict) and isinstance(data.get('secret'), str):
            if 'names' not in data:
                data['names'] = ([{'id': data['id'], 'name': data['name']}]
                                 if data.get('id') and data.get('name') else [])
            return data
    except (OSError, ValueError):
        pass
    return None


def _save_identity(data):
    target = _identity_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix('.new')
    with open(temporary, 'w', encoding='utf-8') as stream:
        json.dump(data, stream)
    try:
        os.chmod(temporary, 0o600)
    except OSError:
        pass
    os.replace(temporary, target)


def _python_executable():
    folder = f'{bpy.app.version[0]}.{bpy.app.version[1]}'
    executable = Path(bpy.app.binary_path).parent / folder / 'python' / 'bin' / 'python.exe'
    if not executable.is_file():
        raise RuntimeError('Blender Python is unavailable for chat')
    return str(executable)


def _qt_site_packages():
    for folder in map(Path, sys.path):
        if (folder / 'PySide6').is_dir():
            return str(folder)
    profile = _identity_path().parent.parent
    folder = profile / 'extensions' / '.local' / 'lib' / f'python{sys.version_info.major}.{sys.version_info.minor}' / 'site-packages'
    if not (folder / 'PySide6').is_dir():
        raise RuntimeError('The bundled chat window is unavailable; reinstall the BBE extension')
    return str(folder)


def _launch_messenger(*, prewarm=False):
    """Start the companion once; a prewarmed instance stays hidden until clicked."""
    global _messenger_process, _prewarm_attempted
    if _messenger_process is not None and _messenger_process.poll() is None:
        return
    sync_theme()
    folder = _identity_path().parent / 'bbe-chat-temp'
    folder.mkdir(parents=True, exist_ok=True, mode=0o700)
    log = folder / 'messenger-startup.log'
    args = [_python_executable(), '-I', '-u', str(Path(__file__).with_name('bbe_chat_messenger.py')),
            _qt_site_packages(), str(_identity_path()), str(_settings_path()), str(folder),
            '--blender-pid', str(os.getpid())]
    if prewarm:
        args.append('--prewarm')
    with open(log, 'a', encoding='utf-8') as stream:
        _messenger_process = subprocess.Popen(
            args, stdin=subprocess.DEVNULL, stdout=stream, stderr=stream,
            creationflags=subprocess.CREATE_NO_WINDOW)
    _prewarm_attempted = True


def _handle_messenger_snapshot():
    folder = _identity_path().parent / 'bbe-chat-temp'
    request = folder / 'snapshot-request.json'
    if not request.is_file():
        return
    try:
        data = json.loads(request.read_text(encoding='utf-8'))
        token = data['id']
        if not re.fullmatch(r'[a-f0-9]{24}', token):
            return
        result = folder / ('snapshot-' + token + '.json')
        image = folder / ('snapshot-' + token + '.png')
        try:
            window, area = next((window, area) for window in bpy.context.window_manager.windows
                                for area in window.screen.areas if area.type == 'VIEW_3D')
            with bpy.context.temp_override(window=window, area=area):
                finished = bpy.ops.screen.screenshot(filepath=str(image))
            payload = {'path': str(image)} if 'FINISHED' in finished and image.is_file() else {'error': 'Could not capture Blender'}
        except Exception:
            payload = {'error': 'Could not capture Blender'}
        temporary = result.with_suffix('.new')
        temporary.write_text(json.dumps(payload), encoding='utf-8')
        os.replace(temporary, result)
    except (OSError, ValueError, KeyError, TypeError):
        pass
    finally:
        request.unlink(missing_ok=True)


def _start(action, **detail):
    global _busy, _status
    if not _chat_enabled:
        _status = 'Enable chat first'
        return False
    if _busy is not None:
        _status = 'Please wait for the current chat action'
        return False
    if not getattr(bpy.app, 'online_access', False):
        _status = 'Enable online access in Blender Preferences to use chat'
        return False
    detail.setdefault('secret', _identity['secret'] if _identity else None)
    if action != 'claim':
        detail.setdefault('as', _identity.get('id') if _identity else None)
    process = None
    try:
        folder = _identity_path().parent / 'bbe-chat-temp'
        folder.mkdir(parents=True, exist_ok=True, mode=0o700)
        result_path = folder / ('response-' + secrets.token_hex(12) + '.json')
        startup = subprocess.STARTUPINFO()
        startup.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startup.wShowWindow = subprocess.SW_HIDE
        process = subprocess.Popen(
            [_python_executable(), '-I', '-u', str(Path(__file__).with_name('bbe_chat_helper.py')), str(result_path)],
            stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            startupinfo=startup, creationflags=subprocess.CREATE_NO_WINDOW,
        )
        process.stdin.write(json.dumps({'action': action, 'detail': detail}).encode('utf-8'))
        process.stdin.close()
    except (OSError, RuntimeError) as error:
        if process is not None:
            process.kill()
        _status = str(error)
        return False
    _busy = (process, action, detail, result_path, time.monotonic())
    _status = 'Connecting...' if action == 'claim' else 'Working...'
    return True


def _tick():
    global _busy, _identity, _status, _messages, _online, _contacts, _chat_enabled
    global _pending, _pending_snapshot, _next_sync, _online_page, _message_page, _target
    global _notification_state, _was_messenger_alive, _toolbar_status, _prewarm_attempted
    if not _enabled:
        return None
    if _chat_enabled and _toolbar_status.get('directed'):
        _redraw(toolbar_only=True)
    was_enabled = _chat_enabled
    _chat_enabled = _load_chat_enabled()
    if was_enabled != _chat_enabled:
        _redraw()
    messenger_alive = _messenger_process is not None and _messenger_process.poll() is None
    if messenger_alive:
        _read_toolbar_status()
    elif _was_messenger_alive:
        _notification_state = chat_state.load(_identity_path().parent/'bbe-chat-temp'/'notifications.json')
        _next_sync = 0
    _was_messenger_alive = messenger_alive
    if (not _chat_enabled or not getattr(bpy.app, 'online_access', False)
            or (not messenger_alive and time.monotonic()-_background_synced_at > 30)):
        if _toolbar_status.get('online') is not None:
            _toolbar_status = {**_toolbar_status, 'online': None}
            _redraw()
    if messenger_alive:
        if _chat_enabled and getattr(bpy.app, 'online_access', False):
            _handle_messenger_snapshot()
        sync_theme()
    if _busy is not None:
        process, action, detail, result_path, started = _busy
        timeout = 55 if action == 'send' and detail.get('file') else 25
        if process.poll() is None and time.monotonic() - started > timeout:
            process.kill()
            _status = 'Chat request timed out'
        if process.poll() is not None:
            _busy = None
            try:
                response = json.loads(result_path.read_text(encoding='utf-8'))
            except (OSError, ValueError):
                response = {'error': _status if _status == 'Chat request timed out' else 'Chat helper could not complete the request'}
            try:
                result_path.unlink(missing_ok=True)
            except OSError:
                pass
            output, error = response.get('output'), response.get('error')
            if error:
                _status = error
                if action == 'sync':
                    _next_sync = time.monotonic() + 30
            elif not isinstance(output, (dict, str)):
                _status = 'Chat server returned an invalid response'
            elif action == 'claim':
                if detail.get('restore'):
                    _identity = {'secret': detail['secret'], 'name': output['name'], 'active': False}
                    wm = getattr(bpy.context, 'window_manager', None)
                    if wm:
                        wm.bbe_chat_recovery = ''
                _identity['id'], _identity['name'] = output['id'], output['name']
                _identity['names'] = output.get('names', [{'id': output['id'], 'name': output['name']}])
                _identity['active'] = True
                _save_identity(_identity)
                _messages, _contacts, _target = [], [], ''
                _status = 'Connected as ' + output['name']
                _next_sync = 0
            elif action == 'sync':
                if not messenger_alive and _chat_enabled and getattr(bpy.app, 'online_access', False):
                    _update_background_status(output)
                if detail['to'] == _target:
                    _messages = output.get('messages', [])
                _online = output.get('online', [])
                _contacts = output.get('contacts', [])
                if _identity and output.get('names') and _identity.get('names') != output['names']:
                    _identity['names'] = output['names']
                    _save_identity(_identity)
                _online_page = min(_online_page, max(0, (len(_online) - 1) // 8))
                _message_page = min(_message_page, max(0, (len(_messages) - 1) // 8))
                _status = ''
                _next_sync = time.monotonic() + 10
            elif action == 'send':
                wm = getattr(bpy.context, 'window_manager', None)
                if wm and wm.bbe_chat_draft.strip() == detail['text']:
                    wm.bbe_chat_draft = ''
                if detail['file'] == _pending:
                    if _pending_snapshot:
                        try:
                            Path(_pending).unlink(missing_ok=True)
                        except OSError:
                            pass
                    _pending, _pending_snapshot = '', False
                _status = 'Sent'
                _next_sync = 0
            elif action == 'download':
                _status = 'Saved to ' + output
    if messenger_alive:
        latest = _load_identity()
        if latest and latest != _identity:
            _identity = latest
        return 1.0
    if (not _prewarm_attempted and _chat_enabled and getattr(bpy.app, 'online_access', False)
            and _identity and _identity.get('id') and _busy is None):
        _prewarm_attempted = True
        try:
            _launch_messenger(prewarm=True)
            return 1.0
        except (OSError, RuntimeError) as exc:
            _status = str(exc)
    if _chat_enabled and _identity and _identity.get('id') and _busy is None and time.monotonic() >= _next_sync and getattr(bpy.app, 'online_access', False):
        _start('sync', to=_target, known_content=[k for k,v in _notification_state.get('content',{}).items() if 'text' in v])
        _next_sync = time.monotonic() + 10
    return 1.0


def _update_background_status(output):
    global _toolbar_status, _background_synced_at
    _background_synced_at = time.monotonic()
    chat_state.update(_notification_state, output, _identity.get('id'), _identity.get('names', []))
    chat_state.save(_identity_path().parent/'bbe-chat-temp'/'notifications.json', _notification_state)
    online = len({p['id'] for p in output.get('online',[]) if p.get('id') and p['id'] != _identity.get('id')})
    _toolbar_status = chat_state.toolbar(_notification_state, online)
    _redraw()


def _redraw(toolbar_only=False):
    for window in bpy.context.window_manager.windows:
        for area in window.screen.areas:
            if area.type == 'VIEW_3D':
                if toolbar_only:
                    for region in area.regions:
                        if region.type == 'TOOL_HEADER':
                            region.tag_redraw()
                else:
                    area.tag_redraw()


def _read_toolbar_status():
    global _toolbar_status, _toolbar_status_stamp
    path = _identity_path().parent / 'bbe-chat-temp' / 'toolbar-status.json'
    try:
        stat = path.stat()
        stamp = stat.st_mtime_ns if time.time()-stat.st_mtime < 15 and stat.st_size < 16384 else None
        if stamp == _toolbar_status_stamp:
            return
        data = json.loads(path.read_text(encoding='utf-8')) if stamp else {}
        if not isinstance(data, dict):
            data = {}
    except (OSError, ValueError):
        stamp, data = None, {}
    _toolbar_status_stamp = stamp
    if data != _toolbar_status:
        _toolbar_status = data
        _redraw()


def draw_native_toolbar(layout, context):
    """One reorderable chat control; toolbar settings are drawn after it."""
    if not _chat_enabled:
        layout.popover(panel='VIEW3D_PT_bbe_chat', text='Chat', icon_value=_chat_icon())
        return
    text = ' '.join(str(_toolbar_status.get('preview', 'Waiting for messages')).split())
    text = text[:43]+'…' if len(text) > 44 else text
    unread = _toolbar_status.get('unread', 0)
    if isinstance(unread, int) and unread > 0:
        text = f'({unread}) {text}'
    row = layout.row(align=True)
    row.alert = bool(_toolbar_status.get('directed')) and chat_state.pulse_on(time.monotonic())
    if _toolbar_status.get('directed'):
        text = '↪ ' + text
    elif unread:
        text = '● ' + text
    row.operator('bbe.chat_open', text=text+' ▾', icon_value=_chat_icon()).view = 'TOOLBAR'


def _dropdown_anchor(context, event):
    """Capture the clicked toolbar in its own Blender client coordinates."""
    window, area = context.window, context.area
    if not window or not area or not window.width or not window.height:
        return None
    region = next((r for r in area.regions if r.type == 'TOOL_HEADER' and r.height > 1), None)
    if region is None:
        return None
    anchor = {'x': max(0., min(1., event.mouse_x/window.width)),
              'bottom': (window.height-region.y)/window.height}
    if sys.platform == 'win32':
        import ctypes
        from ctypes import wintypes
        api = ctypes.WinDLL('user32')
        api.GetForegroundWindow.restype = wintypes.HWND
        api.GetWindowThreadProcessId.argtypes = (wintypes.HWND, ctypes.POINTER(wintypes.DWORD))
        handle = api.GetForegroundWindow()
        pid = wintypes.DWORD()
        api.GetWindowThreadProcessId(handle, ctypes.byref(pid))
        if pid.value == os.getpid():
            anchor['hwnd'] = int(handle)
    return anchor


class BBE_OT_chat_open(bpy.types.Operator):
    bl_idname = 'bbe.chat_open'
    bl_label = 'Open BBE Messenger'
    bl_description = 'Open messages, attachments and chat settings'
    bl_options = {'INTERNAL'}
    view: bpy.props.EnumProperty(items=(('CHAT', 'Messages', ''), ('PEOPLE', 'Users and direct messages', ''),
                                      ('TOOLBAR', 'Chat dropdown', 'Open mini chat below this toolbar')), default='CHAT')

    def invoke(self, context, event):
        self._dropdown_anchor = _dropdown_anchor(context, event) if self.view == 'TOOLBAR' else None
        return self.execute(context)

    @classmethod
    def description(cls, context, properties):
        if properties.view == 'TOOLBAR':
            count = _online_count()
            presence = f'{count} other builders online. ' if count is not None else 'Online count unavailable. '
            if _toolbar_status.get('directed'):
                presence += 'A direct message is waiting for your reply. '
            return presence + 'Open chat below this toolbar: messages, attachments, online users and chat toggle'
        return ('Show online users and choose someone to direct message'
                if properties.view == 'PEOPLE' else cls.bl_description)

    def execute(self, context):
        global _messenger_process, _status, _busy, _identity
        if not _identity:
            _identity = {'secret': secrets.token_urlsafe(32), 'names': [], 'active': False}
            _save_identity(_identity)
        if _busy is not None:
            process, _, _, result_path, _ = _busy
            if process.poll() is None:
                process.kill()
            result_path.unlink(missing_ok=True)
            _busy = None
        previous = _messenger_process if _messenger_process is not None and _messenger_process.poll() is None else None
        try:
            sync_theme()
            folder = _identity_path().parent / 'bbe-chat-temp'
            folder.mkdir(parents=True, exist_ok=True, mode=0o700)
            command = folder / 'messenger-command.json'
            temporary = command.with_suffix('.new')
            temporary.write_text(json.dumps({'action': self.view, 'anchor': getattr(self, '_dropdown_anchor', None),
                                              'target': _toolbar_status.get('target')}), encoding='utf-8')
            os.replace(temporary, command)
            if previous is not None:
                if sys.platform == 'win32':
                    import ctypes
                    ctypes.WinDLL('user32').AllowSetForegroundWindow(previous.pid)
                return {'FINISHED'}
            _launch_messenger()
            _status = 'Messenger opened'
        except (OSError, RuntimeError) as exc:
            self.report({'ERROR'}, str(exc))
            return {'CANCELLED'}
        return {'FINISHED'}


class BBE_OT_chat_toggle(bpy.types.Operator):
    bl_idname = 'bbe.chat_toggle'
    bl_label = 'Enable or Disable BBE Chat'
    bl_description = 'Chat is optional and starts off; disable it to stop chat requests'
    bl_options = {'INTERNAL'}

    def execute(self, context):
        global _chat_enabled, _busy, _online, _messages, _status, _next_sync, _messenger_process
        _chat_enabled = not _chat_enabled
        _save_chat_enabled()
        if _chat_enabled:
            if _identity and _identity.get('id'):
                _identity['active'] = True
                _next_sync = 0
            _status = 'Chat enabled.'
            bpy.ops.bbe.chat_open('INVOKE_DEFAULT', view='TOOLBAR')
        else:
            if _messenger_process is not None and _messenger_process.poll() is None:
                _messenger_process.terminate()
                _messenger_process = None
            if _busy is not None:
                process, _, _, result_path, _ = _busy
                if process.poll() is None:
                    process.kill()
                try:
                    result_path.unlink(missing_ok=True)
                except OSError:
                    pass
                _busy = None
            _online, _messages = [], []
            _status = 'Chat is off.'
        _redraw()
        return {'FINISHED'}


class BBE_OT_chat_join(bpy.types.Operator):
    bl_idname = 'bbe.chat_join'
    bl_label = 'Join BBE Chat'
    bl_options = {'INTERNAL'}

    def execute(self, context):
        global _identity
        name = context.window_manager.bbe_chat_name.strip()
        if len(name) < 2:
            self.report({'WARNING'}, 'Enter a name of at least 2 characters')
            return {'CANCELLED'}
        if _identity is None:
            _identity = {'name': name, 'secret': secrets.token_urlsafe(32), 'active': False, 'names': []}
            _save_identity(_identity)  # Save before the request, so a retry keeps the claim.
        elif len(_identity.get('names', [])) >= 3 and name.lower() not in {item['name'].lower() for item in _identity['names']}:
            self.report({'WARNING'}, 'This recovery key already owns three names')
            return {'CANCELLED'}
        if not _start('claim', name=name):
            return {'CANCELLED'}
        return {'FINISHED'}


class BBE_OT_chat_copy_key(bpy.types.Operator):
    bl_idname = 'bbe.chat_copy_key'
    bl_label = 'Copy Chat Recovery Key'
    bl_description = 'Copy your private name key; save it somewhere safe to restore your name on another Blender profile'
    bl_options = {'INTERNAL'}

    def execute(self, context):
        if not _identity or not _identity.get('id'):
            return {'CANCELLED'}
        context.window_manager.clipboard = _identity['secret']
        self.report({'INFO'}, 'Private chat name key copied. Do not share it.')
        return {'FINISHED'}


class BBE_OT_chat_restore_key(bpy.types.Operator):
    bl_idname = 'bbe.chat_restore_key'
    bl_label = 'Restore Chat Name'
    bl_description = 'Restore a claimed chat name using its private recovery key'
    bl_options = {'INTERNAL'}

    def execute(self, context):
        global _identity
        secret = context.window_manager.bbe_chat_recovery.strip()
        if not re.fullmatch(r'[A-Za-z0-9_-]{40,128}', secret):
            self.report({'WARNING'}, 'Paste a valid chat recovery key')
            return {'CANCELLED'}
        if _identity and _identity.get('id') and _identity['secret'] != secret:
            self.report({'WARNING'}, 'This profile already owns a name. Back up its key before changing profiles.')
            return {'CANCELLED'}
        name = context.window_manager.bbe_chat_name.strip()
        return {'FINISHED'} if _start('claim', name=name, secret=secret, restore=True) else {'CANCELLED'}


class BBE_OT_chat_leave(bpy.types.Operator):
    bl_idname = 'bbe.chat_leave'
    bl_label = 'Disconnect Chat'
    bl_description = 'Stop appearing online; your name remains yours on this Blender profile'
    bl_options = {'INTERNAL'}

    def execute(self, context):
        global _identity, _online, _messages, _status
        if _chat_enabled:
            return bpy.ops.bbe.chat_toggle()
        if _identity:
            _identity['active'] = False
            _save_identity(_identity)
        _online, _messages = [], []
        _status = 'Disconnected'
        _redraw()
        return {'FINISHED'}


class BBE_OT_chat_switch(bpy.types.Operator):
    bl_idname = 'bbe.chat_switch'
    bl_label = 'Switch Chat Name'
    bl_description = 'Use another name owned by this recovery key'
    bl_options = {'INTERNAL'}
    identity_id: bpy.props.StringProperty()

    def execute(self, context):
        global _messages, _contacts, _target, _next_sync, _status
        if not _identity or _busy is not None:
            return {'CANCELLED'}
        name = next((item for item in _identity.get('names', []) if item['id'] == self.identity_id), None)
        if not name:
            return {'CANCELLED'}
        _identity['id'], _identity['name'], _identity['active'] = name['id'], name['name'], True
        _save_identity(_identity)
        _messages, _contacts, _target, _next_sync = [], [], '', 0
        _status = 'Using ' + name['name']
        _redraw()
        return {'FINISHED'}


class BBE_OT_chat_room(bpy.types.Operator):
    bl_idname = 'bbe.chat_room'
    bl_label = 'Open Chat Room'
    bl_options = {'INTERNAL'}
    target: bpy.props.StringProperty(default='')

    def execute(self, context):
        global _target, _messages, _next_sync, _message_page
        _target, _messages, _next_sync, _message_page = self.target, [], 0, 0
        _redraw()
        return {'FINISHED'}


class BBE_OT_chat_page(bpy.types.Operator):
    bl_idname = 'bbe.chat_page'
    bl_label = 'Chat Page'
    bl_options = {'INTERNAL'}
    kind: bpy.props.EnumProperty(items=[('MESSAGES', 'Messages', ''), ('ONLINE', 'Online', '')])
    step: bpy.props.IntProperty(default=0)

    def execute(self, context):
        global _online_page, _message_page
        if self.kind == 'ONLINE':
            _online_page = max(0, min((len(_online) - 1) // 8, _online_page + self.step))
        else:
            _message_page = max(0, min((len(_messages) - 1) // 8, _message_page + self.step))
        _redraw()
        return {'FINISHED'}


class BBE_OT_chat_read(bpy.types.Operator):
    bl_idname = 'bbe.chat_read'
    bl_label = 'Read Chat Message'
    bl_options = {'INTERNAL'}
    message_id: bpy.props.StringProperty()

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self, width=480, confirm_text='Close')

    def draw(self, context):
        item = next((item for item in _messages if item.get('id') == self.message_id), None)
        if not item:
            self.layout.label(text='Message is no longer in the current view')
            return
        self.layout.label(text=item.get('name', 'User'))
        text = item.get('text', '')
        for index in range(0, len(text), 70):
            self.layout.label(text=text[index:index + 70])

    def execute(self, context):
        return {'FINISHED'}


class BBE_OT_chat_attach(bpy.types.Operator):
    bl_idname = 'bbe.chat_attach'
    bl_label = 'Attach File'
    bl_description = 'Choose an image or short video; nothing uploads until Send'
    bl_options = {'INTERNAL'}
    filepath: bpy.props.StringProperty(subtype='FILE_PATH')
    filter_glob: bpy.props.StringProperty(default='*.png;*.jpg;*.jpeg;*.gif;*.webp;*.mp4;*.webm', options={'HIDDEN'})

    def invoke(self, context, event):
        context.window_manager.fileselect_add(self)
        return {'RUNNING_MODAL'}

    def execute(self, context):
        global _pending, _pending_snapshot, _status
        file = Path(self.filepath)
        if not file.is_file() or file.suffix.lower() not in _MIMES or file.stat().st_size > _MAX_DOWNLOAD:
            self.report({'WARNING'}, 'Choose a PNG, JPEG, GIF, WebP, MP4 or WebM up to 20 MB')
            return {'CANCELLED'}
        _pending, _pending_snapshot = str(file), False
        _status = 'File ready. Press Send to upload.'
        _redraw()
        return {'FINISHED'}


class BBE_OT_chat_snapshot(bpy.types.Operator):
    bl_idname = 'bbe.chat_snapshot'
    bl_label = 'Snapshot'
    bl_description = 'Capture this Blender window and queue it; press Send to share'
    bl_options = {'INTERNAL'}

    def execute(self, context):
        file = Path(tempfile.gettempdir()) / ('bbe-chat-' + secrets.token_hex(12) + '.png')
        window = context.window

        def capture_after_menu_closes():
            global _pending, _pending_snapshot, _status
            try:
                area = next(area for area in window.screen.areas if area.type == 'VIEW_3D')
                with bpy.context.temp_override(window=window, area=area):
                    result = bpy.ops.screen.screenshot(filepath=str(file))
                if 'FINISHED' not in result or not file.is_file():
                    raise RuntimeError('Screenshot was not saved')
                if _pending_snapshot:
                    Path(_pending).unlink(missing_ok=True)
                _pending, _pending_snapshot = str(file), True
                _status = 'Snapshot ready. Press Send or use Send with Enter.'
                _redraw()
                try:
                    with bpy.context.temp_override(window=window, area=area):
                        bpy.ops.bbe.chat_compose('INVOKE_DEFAULT')
                except RuntimeError:
                    pass  # The staged image remains available in the menu.
            except Exception:
                _status = 'Could not capture the Blender window'
                _redraw()
            return None

        # Let this popover disappear before taking the screenshot.
        bpy.app.timers.register(capture_after_menu_closes, first_interval=0.3)
        return {'FINISHED'}


class BBE_OT_chat_clear_file(bpy.types.Operator):
    bl_idname = 'bbe.chat_clear_file'
    bl_label = 'Remove Attachment'
    bl_options = {'INTERNAL'}

    def execute(self, context):
        global _pending, _pending_snapshot, _status
        if _pending_snapshot:
            try:
                Path(_pending).unlink(missing_ok=True)
            except OSError:
                pass
        _pending, _pending_snapshot, _status = '', False, ''
        return {'FINISHED'}


class BBE_OT_chat_send(bpy.types.Operator):
    bl_idname = 'bbe.chat_send'
    bl_label = 'Send Chat Message'
    bl_options = {'INTERNAL'}

    def execute(self, context):
        global _status
        text = context.window_manager.bbe_chat_draft.strip()
        if not text and not _pending:
            return {'CANCELLED'}
        if len(text) > 1000:
            self.report({'WARNING'}, 'Message is too long (1000 characters maximum)')
            return {'CANCELLED'}
        if _start('send', to=_target, text=text, file=_pending):
            return {'FINISHED'}
        return {'CANCELLED'}


class BBE_OT_chat_compose(bpy.types.Operator):
    bl_idname = 'bbe.chat_compose'
    bl_label = 'Send Chat Message'
    bl_description = 'Review your message and staged file; press Enter to send'
    bl_options = {'INTERNAL'}
    text: bpy.props.StringProperty(name='Message', maxlen=1000)

    def invoke(self, context, event):
        self.text = context.window_manager.bbe_chat_draft
        return context.window_manager.invoke_props_dialog(self, width=420, confirm_text='Send')

    def draw(self, context):
        self.layout.label(text='Main Room' if not _target else 'Direct Message')
        self.layout.prop(self, 'text')
        if _pending:
            self.layout.label(text='Ready: ' + Path(_pending).name[:48], icon='IMAGE_DATA' if _pending_snapshot else 'FILE')

    def execute(self, context):
        text = self.text.strip()
        if not text and not _pending:
            return {'CANCELLED'}
        context.window_manager.bbe_chat_draft = text
        return {'FINISHED'} if _start('send', to=_target, text=text, file=_pending) else {'CANCELLED'}


class BBE_OT_chat_download(bpy.types.Operator):
    bl_idname = 'bbe.chat_download'
    bl_label = 'Save Chat File'
    bl_description = 'Save this chat attachment to a location you choose'
    bl_options = {'INTERNAL'}
    media_id: bpy.props.StringProperty()
    filepath: bpy.props.StringProperty(subtype='FILE_PATH')

    def invoke(self, context, event):
        context.window_manager.fileselect_add(self)
        return {'RUNNING_MODAL'}

    def execute(self, context):
        if not any(item.get('attachment', {}).get('id') == self.media_id for item in _messages):
            return {'CANCELLED'}
        if Path(self.filepath).exists():
            self.report({'WARNING'}, 'Choose a new filename; chat will not overwrite a file')
            return {'CANCELLED'}
        return {'FINISHED'} if _start('download', id=self.media_id, path=self.filepath) else {'CANCELLED'}


class VIEW3D_PT_bbe_chat(bpy.types.Panel):
    bl_idname = 'VIEW3D_PT_bbe_chat'
    bl_label = 'BBE Chat'
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'HEADER'
    bl_ui_units_x = 18

    def draw(self, context):
        row = self.layout.row()
        row.enabled = bool(getattr(bpy.app, 'online_access', False))
        row.operator('bbe.chat_toggle', text='Enable chat',
                     icon='CHECKBOX_HLT' if _chat_enabled else 'CHECKBOX_DEHLT', depress=_chat_enabled)
        self.layout.label(text='Your names stay reserved when chat is off.')
        if not row.enabled:
            self.layout.label(text='Enable Online Access in Blender Preferences.', icon='INFO')


classes = (BBE_OT_chat_open, BBE_OT_chat_toggle, BBE_OT_chat_join, BBE_OT_chat_copy_key, BBE_OT_chat_restore_key,
           BBE_OT_chat_leave, BBE_OT_chat_switch, BBE_OT_chat_room, BBE_OT_chat_page, BBE_OT_chat_read,
           BBE_OT_chat_attach, BBE_OT_chat_snapshot, BBE_OT_chat_clear_file,
           BBE_OT_chat_send, BBE_OT_chat_compose, BBE_OT_chat_download,
           VIEW3D_PT_bbe_chat)


def register():
    global _identity, _enabled, _chat_enabled, _notification_state, _toolbar_status, _prewarm_attempted
    _prewarm_attempted = False
    _identity = _load_identity()
    _chat_enabled = _load_chat_enabled()
    _notification_state = chat_state.load(_identity_path().parent/'bbe-chat-temp'/'notifications.json')
    if _chat_enabled and _identity and _notification_state.get('persona') == _identity.get('id'):
        _toolbar_status = chat_state.toolbar(_notification_state, None)
    _enabled = True
    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.types.WindowManager.bbe_chat_name = bpy.props.StringProperty(
        name='Chat Name', default=_identity.get('name', '') if _identity else '', options={'SKIP_SAVE'})
    bpy.types.WindowManager.bbe_chat_draft = bpy.props.StringProperty(
        name='Message', default='', options={'SKIP_SAVE'})
    bpy.types.WindowManager.bbe_chat_recovery = bpy.props.StringProperty(
        name='Recovery Key', default='', subtype='PASSWORD', options={'SKIP_SAVE'})
    if not bpy.app.timers.is_registered(_tick):
        bpy.app.timers.register(_tick, first_interval=1.0, persistent=True)


def unregister():
    global _enabled, _busy, _messenger_process, _badge_previews
    _enabled = False
    if _badge_previews is not None:
        from bpy.utils import previews
        previews.remove(_badge_previews)
        _badge_previews = None
    if bpy.app.timers.is_registered(_tick):
        bpy.app.timers.unregister(_tick)
    if _busy is not None:
        process, _, _, result_path, _ = _busy
        if process.poll() is None:
            process.kill()
        process.wait(timeout=3)
        try:
            result_path.unlink(missing_ok=True)
        except OSError:
            pass
        _busy = None
    if _messenger_process is not None and _messenger_process.poll() is None:
        _messenger_process.terminate()
        _messenger_process = None
    for name in ('bbe_chat_name', 'bbe_chat_draft', 'bbe_chat_recovery'):
        if hasattr(bpy.types.WindowManager, name):
            delattr(bpy.types.WindowManager, name)
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
