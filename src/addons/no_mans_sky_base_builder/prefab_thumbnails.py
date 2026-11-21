"""Shared on-demand local prefab previews. Blender only loads finished PNGs."""
from collections import OrderedDict
import hashlib
import os
from pathlib import Path
import subprocess
import sys

import bpy
import bpy.utils.previews

_paths = {}
_keys = {}
_pending = OrderedDict()
_running = {}
_failed = set()
_resident = OrderedDict()
_collection = None
_worker = None
_cache = None
# Change when the mesh catalogue or renderer changes.
_FORMAT = 'shell-1'


def set_library(paths):
    global _paths
    _paths = dict(paths)
    _keys.clear()
    _failed.clear()
    _pending.clear()


def enabled():
    addon = bpy.context.preferences.addons.get(__package__)
    return bool(addon and addon.preferences.bbe_prefab_previews)


def get(name, path=None):
    if not enabled():
        return None
    path = path or _paths.get(name)
    if not path:
        return None
    key = _keys.get(path)
    if key in _resident:
        _resident.move_to_end(key)
        return _collection[key]
    if path not in _failed and path not in _running:
        _pending[path] = None
        if not bpy.app.timers.is_registered(_tick):
            bpy.app.timers.register(_tick, first_interval=.04, persistent=True)
    return None


def _load(key, output):
    global _collection
    if key in _resident:
        return
    if _collection is None:
        _collection = bpy.utils.previews.new()
    _collection.load(key, str(output), 'IMAGE')
    _resident[key] = None
    if len(_resident) > 160:
        old, _ = _resident.popitem(last=False)
        del _collection[old]


def redraw():
    wm = bpy.context.window_manager
    if wm:
        for window in wm.windows:
            for area in window.screen.areas:
                if area.type in {'VIEW_3D', 'INFO'}:
                    area.tag_redraw()


def _tick():
    global _worker, _cache
    if not enabled():
        return None
    changed = False
    if _worker is not None:
        finished = _worker.poll() is not None
        for path, (key, output) in list(_running.items()):
            if output.is_file():
                if _keys.get(path) == key:
                    try:
                        _load(key, output)
                        changed = True
                    except (OSError, RuntimeError):
                        _failed.add(path)
                del _running[path]
            elif finished:
                if _keys.get(path) == key:
                    _failed.add(path)
                del _running[path]
        if finished:
            _worker = None
    if _worker is None and _pending:
        if _cache is None:
            _cache = Path(bpy.utils.user_resource('CONFIG'))/'bbe-prefab-thumbnails'
        for _ in range(min(8, len(_pending))):
            path, _unused = _pending.popitem(last=False)
            try:
                info = os.stat(path)
                stamp = f'{_FORMAT}|{os.path.normcase(path)}|{info.st_size}|{info.st_mtime_ns}'
                key = hashlib.sha256(os.fsencode(stamp)).hexdigest()
                _keys[path] = key
                output = _cache/(key+'.png')
                if output.is_file():
                    _load(key, output)
                    changed = True
                else:
                    _running[path] = (key, output)
            except (OSError, RuntimeError):
                _failed.add(path)
        if _running:
            try:
                _cache.mkdir(parents=True, exist_ok=True)
                args = [str(Path(sys.prefix)/'bin/python.exe'), '-I',
                        str(Path(__file__).with_name('prefab_thumbnail_worker.py'))]
                for path, (_, output) in _running.items():
                    args.extend((path, str(output)))
                _worker = subprocess.Popen(args, creationflags=subprocess.CREATE_NO_WINDOW |
                                           subprocess.BELOW_NORMAL_PRIORITY_CLASS)
            except OSError as error:
                print('BBE prefab previews:', error)
                _failed.update(_running)
                _running.clear()
    if changed:
        redraw()
    return .08 if _worker is not None or _pending else None


def stop_work():
    global _worker
    _pending.clear()
    if bpy.app.timers.is_registered(_tick):
        bpy.app.timers.unregister(_tick)
    if _worker is not None:
        _worker.terminate()
        _worker.wait()
        _worker = None
    _running.clear()


def close():
    global _collection, _cache
    stop_work()
    set_library({})
    _resident.clear()
    if _collection is not None:
        bpy.utils.previews.remove(_collection)
        _collection = None
    _cache = None

