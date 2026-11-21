"""Remember the fold state of regular BBE's native sidebar panels."""
import json
import os

import bpy
from bpy.app.handlers import persistent

from . import settings_memory

_CLOSED = 1 << 2  # Blender 5.1 DNA_screen_types.h, PNL_CLOSED
_saved = {}
_pending = {}
_observed = {}
_originals = {}
_first_install = False


def path():
    return settings_memory.path().with_name('bbe-sidebar.json')


def read():
    try:
        value = json.loads(path().read_text(encoding='utf8'))
        return {k: v for k, v in value.items() if type(v) is bool}
    except (FileNotFoundError, ValueError, AttributeError):
        return {}
    except OSError as error:
        settings_memory.report('sidebar', error)
        return {}


def flush():
    if not _pending:
        return
    try:
        state = read()
        state.update(_pending)
        temp = path().with_suffix(f'.{os.getpid()}.tmp')
        temp.write_text(json.dumps(state, indent=2), encoding='utf8')
        temp.replace(path())
        _pending.clear()
    except OSError as error:
        settings_memory.report('sidebar', error)
        return 1.0


def remember(key, expanded):
    _saved[key] = _pending[key] = expanded
    if not bpy.app.timers.is_registered(flush):
        bpy.app.timers.register(flush, first_interval=0)


@persistent
def reset_regions(*_):
    _observed.clear()


def register():
    global _saved, _first_install
    _saved = read()
    _first_install = not _saved and not settings_memory.path().is_file()
    if not bpy.app.background and not _saved:
        remember('installed', True)
    bpy.app.handlers.load_pre.append(reset_regions)


def observe(owner, context, key):
    from .sidebar_builder import native_panel
    if not context.region or context.region.type != 'UI':
        return
    panel = native_panel(owner)
    if panel is None:
        return
    local = (context.region.as_pointer(), owner.bl_idname)
    expanded = not bool(panel.flags & _CLOSED)
    if local not in _observed:
        desired = _saved.get(key, _first_install if key == 'proxies' else expanded)
        if expanded != desired:
            # Restore only the closed bit on this live, version-checked Panel.
            # Pinned status, order, and the active sidebar category stay native.
            panel.flags ^= _CLOSED
            expanded = desired
            context.region.tag_redraw()
        _observed[local] = expanded
        if key not in _saved:
            remember(key, expanded)
    elif expanded != _observed[local]:
        _observed[local] = expanded
        remember(key, expanded)


def bind(cls, key):
    original = cls.__dict__.get('draw_header')
    options = cls.__dict__.get('bl_options')
    _originals[cls] = original, options
    flags = set(options or ())
    default_open = _saved.get(key, _first_install if key == 'proxies' else 'DEFAULT_CLOSED' not in flags)
    if default_open:
        flags.discard('DEFAULT_CLOSED')
    else:
        flags.add('DEFAULT_CLOSED')
    cls.bl_options = flags

    def draw_header(owner, context):
        observe(owner, context, key)
        if original:
            original(owner, context)
    cls.draw_header = draw_header


def unregister():
    if bpy.app.timers.is_registered(flush):
        bpy.app.timers.unregister(flush)
    flush()
    bpy.app.handlers.load_pre.remove(reset_regions)
    reset_regions()
    for cls, (header, options) in _originals.items():
        for name, value in [('draw_header', header), ('bl_options', options)]:
            if value is None:
                delattr(cls, name)
            else:
                setattr(cls, name, value)
    _originals.clear()
    _pending.clear()
