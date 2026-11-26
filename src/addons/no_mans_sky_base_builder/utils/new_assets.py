"""Per-user discovery markers for newly released parts, never stored in a build."""
import json
from pathlib import Path
from time import monotonic
from urllib.parse import quote, unquote

YELLOW = (1.0, 0.78, 0.06, 1.0)
_catalog = None
_seen = None
_last_check = 0.0
_directory_stamp = None


def _new_ids():
    global _catalog
    if _catalog is None:
        from .dictionary import get_parts_definition
        # This is a fixed historical snapshot. New catalogue rows opt in
        # automatically, even when someone skips a release or installs fresh.
        path = Path(__file__).resolve().parents[1] / 'resources/discovery_baseline.txt'
        established = set(path.read_text(encoding='utf-8').splitlines())
        _catalog = {key[1:] for key in get_parts_definition() if key.startswith('^')} - established
    return _catalog


def _path():
    from .asset_browser_utils import get_user_data_directory
    return Path(get_user_data_directory()) / 'asset_browser' / 'viewed_new_parts.json'


def _viewed():
    global _seen, _last_check, _directory_stamp
    now = monotonic()
    if _seen is not None and now - _last_check < 1:
        return _seen
    _last_check = now
    path = _path()
    if _seen is None:
        try:
            data = json.loads(path.read_text(encoding='utf-8'))
            _seen = {entry for entry in data if isinstance(entry, str)} if isinstance(data, list) else set()
        except (OSError, ValueError):
            _seen = set()
    directory = path.with_suffix('')
    try:
        stamp = directory.stat().st_mtime_ns
        if stamp != _directory_stamp:
            _seen.update(unquote(p.name[5:]) for p in directory.glob('part-*'))
            _directory_stamp = stamp
    except OSError:
        pass
    return _seen


def is_new(object_id):
    object_id = object_id.lstrip('^')
    return object_id in _new_ids() and object_id not in _viewed()


def mark_viewed(object_id):
    object_id = object_id.lstrip('^')
    if not is_new(object_id):
        return False
    _viewed().add(object_id)
    try:
        # Independent receipts keep two open Blender instances from
        # overwriting each other's discoveries.
        directory = _path().with_suffix('')
        directory.mkdir(parents=True, exist_ok=True)
        (directory / ('part-' + quote(object_id, safe=''))).touch(exist_ok=True)
    except OSError as exc:
        # A read-only profile must not stop placement; keep session state.
        print(f'BBE: Could not remember viewed part: {exc}')
    return True


def record_click(context, object_id):
    if mark_viewed(object_id):
        for window in context.window_manager.windows:
            for area in window.screen.areas:
                area.tag_redraw()
