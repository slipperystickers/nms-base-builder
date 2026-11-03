"""Isolated, guarded Steam save codec for the advanced JSON window.

This module has no Blender/UI dependency so it can run in a separate process.
Only one explicitly selected save point is ever written.
"""
import csv
from datetime import datetime
import hashlib
import json
import os
from pathlib import Path
import re
import struct
import subprocess
import tempfile
import time

import lz4.block

try:
    from . import steam_metadata
except ImportError:  # Standalone Qt process runs this module outside the add-on package.
    import steam_metadata

MAGIC = 0xFEEDA1E5
CHUNK_SIZE = 0x80000
SAVE_NAME = re.compile(r'save\d*\.hg\Z', re.IGNORECASE)
SAVE_NAME_KEYS = (b'"Pk4":', b'"SaveName":')
KEY_IDS = json.loads((Path(__file__).parents[1] / 'resources/ship_management_keys.json').read_text(encoding='utf-8'))
KEY_NAMES = {identifier: name for name, identifier in KEY_IDS.items()}
BASE_CATEGORIES = (
    'Corvettes', 'Planet Bases', 'Space Bases', 'Freighters', 'Stations', 'Other',
)
BASE_TYPES = {
    'PlayerShipBase': ('Corvettes', 'Corvette'),
    'FriendsShipBase': ('Corvettes', 'Friend Corvette'),
    'HomePlanetBase': ('Planet Bases', 'Planet Base'),
    'ExternalPlanetBase': ('Planet Bases', 'Cached Planet Base'),
    'PlayerSpaceBase': ('Space Bases', 'Space Base'),
    'ExternalSpaceBase': ('Space Bases', 'Cached Space Base'),
    'FreighterBase': ('Freighters', 'Freighter'),
    'PlayerSpaceStationBase': ('Stations', 'Station'),
}


def field_key(obj, name):
    """Find the key actually used in this save, whether readable or compact."""
    if not isinstance(obj, dict):
        return None
    if name in obj:
        return name
    compact = KEY_IDS.get(name)
    return compact if compact in obj else None


def field(obj, name, default=None):
    key = field_key(obj, name)
    return obj[key] if key is not None else default


def base_info(base, index, player):
    """Describe a saved base without changing its original array position."""
    raw_type = field(field(base, 'BaseType', {}), 'PersistentBaseTypes', '')
    raw_type = raw_type if isinstance(raw_type, str) else str(raw_type)
    category, type_label = BASE_TYPES.get(raw_type, ('Other', raw_type or 'Unknown Type'))
    name = field(base, 'Name', '')
    name = name.strip() if isinstance(name, str) else ''
    if raw_type == 'FreighterBase':
        freighter = field(player, 'PlayerFreighterName', '')
        if isinstance(freighter, str) and freighter.strip():
            name = freighter.strip()
    if raw_type in ('PlayerShipBase', 'FriendsShipBase') and (not name or name == 'Default'):
        ownership = field(player, 'ShipOwnership', [])
        ship_index = field(base, 'UserData')
        if type(ship_index) is int and isinstance(ownership, list) and 0 <= ship_index < len(ownership):
            ship_name = field(ownership[ship_index], 'Name', '')
            if isinstance(ship_name, str) and ship_name.strip():
                name = ship_name.strip()
    if not name or name == 'Default':
        name = 'Unnamed base'
    objects = field(base, 'Objects', [])
    return {
        'index': index,
        'name': name,
        'category': category,
        'type': type_label,
        'raw_type': raw_type,
        'object_count': len(objects) if isinstance(objects, list) else 0,
    }


def base_records(root):
    """Return Main and Expedition bases with exact paths into the original JSON."""
    records = []
    for context_name, context_label in (('BaseContext', 'Main'),
                                        ('ExpeditionContext', 'Expedition')):
        context_key = field_key(root, context_name)
        if context_key is None:
            continue
        context = root[context_key]
        player_key = field_key(context, 'PlayerStateData')
        if player_key is None:
            continue
        player = context[player_key]
        bases_key = field_key(player, 'PersistentPlayerBases')
        if bases_key is None or not isinstance(player[bases_key], list):
            continue
        for index, base in enumerate(player[bases_key]):
            info = base_info(base, index, player)
            info['context'] = context_label
            info['path'] = (context_key, player_key, bases_key, index)
            records.append(info)
    return records


def readable_key(key):
    return KEY_NAMES.get(key, key)


def _unique_label(raw_key, used):
    label = readable_key(raw_key)
    if label not in used:
        return label
    alternate = f'{label} [raw:{raw_key}]'
    while alternate in used:
        alternate += '#'
    return alternate


def readable(value):
    """Translate known property IDs for display, retaining unknown keys."""
    if isinstance(value, dict):
        shown = {}
        for raw_key, child in value.items():
            label = _unique_label(raw_key, shown)
            shown[label] = readable(child)
        return shown
    if isinstance(value, list):
        return [readable(child) for child in value]
    return value


def restore_keys(edited, before):
    """Return edited readable JSON to its original key scheme where possible."""
    if isinstance(edited, dict):
        previous = before if isinstance(before, dict) else {}
        original_names = {}
        for raw_key in previous:
            label = _unique_label(raw_key, original_names)
            original_names[label] = raw_key
        restored = {}
        for label, child in edited.items():
            raw_key = original_names.get(label, KEY_IDS.get(label, label))
            if raw_key in restored:
                raise ValueError(f'JSON keys resolve to the same game field: {label}')
            restored[raw_key] = restore_keys(child, previous.get(raw_key))
        return restored
    if isinstance(edited, list):
        previous = before if isinstance(before, list) else []
        return [restore_keys(child, previous[index] if index < len(previous) else None)
                for index, child in enumerate(edited)]
    return edited


def slot_point(path):
    """NMS stores two numbered save points per slot."""
    number = int(Path(path).stem[4:] or '1')
    return (number + 1) // 2, 1 if number % 2 else 2


def save_name(root):
    common = root.get('<h0', root.get('CommonStateData', {}))
    if not isinstance(common, dict):
        return None
    name = common.get('Pk4', common.get('SaveName'))
    return name.strip() if isinstance(name, str) and name.strip() else None


def peek_save_name(path):
    """Read just enough HG blocks to show a player's save name in the picker."""
    buffer = bytearray()
    with Path(path).open('rb') as stream:
        while True:
            header = stream.read(16)
            if not header:
                break
            if len(header) != 16:
                raise ValueError('Incomplete HG block header')
            magic, packed, unpacked, _ = struct.unpack('<IIII', header)
            if magic != MAGIC or not 0 < unpacked <= CHUNK_SIZE:
                raise ValueError('Invalid HG save block')
            chunk = stream.read(packed)
            if len(chunk) != packed:
                raise ValueError('Incomplete HG save block')
            buffer.extend(lz4.block.decompress(chunk, uncompressed_size=unpacked))
            for key in SAVE_NAME_KEYS:
                start = buffer.find(key)
                if start >= 0:
                    value = bytes(buffer[start + len(key):]).decode('utf-8', errors='surrogateescape')
                    try:
                        name, _ = json.JSONDecoder().raw_decode(value.lstrip())
                    except ValueError:
                        continue  # A string can span two compressed blocks.
                    if isinstance(name, str) and name.strip():
                        return name.strip()
            if len(buffer) > 2 * CHUNK_SIZE:
                del buffer[:-CHUNK_SIZE]
    return None


def game_running():
    """Fail closed when the Windows process list cannot be checked."""
    if os.name != 'nt':
        raise RuntimeError('The raw save editor currently supports Windows Steam saves only')
    result = subprocess.run(['tasklist', '/FI', 'IMAGENAME eq NMS.exe', '/FO', 'CSV', '/NH'],
                            capture_output=True, text=True, timeout=10, check=True)
    return any(row and row[0].casefold() == 'nms.exe'
               for row in csv.reader(result.stdout.splitlines()))


def require_game_closed():
    if game_running():
        raise RuntimeError('No Man’s Sky is running. Close the game before opening the raw save editor.')


def strict_json(text):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError(f'Duplicate JSON key: {key}')
            result[key] = value
        return result
    def constant(value):
        raise ValueError(f'Invalid JSON value: {value}')
    return json.loads(text, object_pairs_hook=pairs, parse_constant=constant)


def decode(raw):
    offset = 0
    decoded = bytearray()
    while offset < len(raw):
        if len(raw) - offset < 16:
            raise ValueError('Incomplete HG block header')
        magic, packed, unpacked, _ = struct.unpack_from('<IIII', raw, offset)
        offset += 16
        if magic != MAGIC or packed > len(raw) - offset or not 0 < unpacked <= CHUNK_SIZE:
            raise ValueError('Invalid HG save block')
        chunk = lz4.block.decompress(raw[offset:offset + packed], uncompressed_size=unpacked)
        if len(chunk) != unpacked:
            raise ValueError('HG block size mismatch')
        decoded.extend(chunk)
        offset += packed
    data = bytes(decoded).rstrip(b'\x00')
    # Some game saves contain isolated non-UTF-8 bytes inside JSON strings.
    # Surrogate escape keeps each original byte reversible instead of silently
    # replacing it, which would alter unrelated save content on write.
    root = strict_json(data.decode('utf-8', errors='surrogateescape'))
    if not isinstance(root, dict):
        raise ValueError('Save JSON root must be an object')
    return root


def encode(root):
    if not isinstance(root, dict):
        raise ValueError('Save JSON root must be an object')
    data = json.dumps(root, separators=(',', ':'), ensure_ascii=False,
                      allow_nan=False).encode('utf-8', errors='surrogateescape') + b'\x00'
    encoded = bytearray()
    for offset in range(0, len(data), CHUNK_SIZE):
        chunk = data[offset:offset + CHUNK_SIZE]
        packed = lz4.block.compress(chunk, store_size=False)
        encoded.extend(struct.pack('<IIII', MAGIC, len(packed), len(chunk), 0))
        encoded.extend(packed)
    if decode(bytes(encoded)) != root:
        raise ValueError('Save JSON did not round-trip')
    return bytes(encoded), len(data)


def _watched(path):
    path = Path(path).resolve()
    if not SAVE_NAME.fullmatch(path.name) or not path.is_file():
        raise ValueError('Choose an existing Steam save*.hg file')
    meta = path.with_name('mf_' + path.name)
    return [path] + ([meta] if meta.is_file() else [])


def fingerprints(paths):
    return {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}


def read(path):
    require_game_closed()
    paths = _watched(path)
    raw = paths[0].read_bytes()
    root = decode(raw)
    hashes = fingerprints(paths)
    if hashes[str(paths[0])] != hashlib.sha256(raw).hexdigest():
        raise ValueError('Save changed during load; refresh it')
    stats = {str(p): (p.stat().st_size, p.stat().st_mtime_ns) for p in paths}
    return root, hashes, stats


def changed(expected, stats=None):
    paths = [Path(p) for p in expected]
    if _watched(paths[0]) != paths:
        return True
    # Hash even when timestamp and size match: sync tools can replace a save
    # while preserving both. The UI checks periodically and again at commit.
    return fingerprints(paths) != expected


def _backup(originals, path, backup_root):
    account = path.parent
    identity = hashlib.sha256(str(account).casefold().encode('utf-8')).hexdigest()[:10]
    number = int(path.stem.removeprefix('save') or '1')
    slot = (number + 1) // 2
    parent = Path(backup_root).resolve() / 'Game Saves' / f'{account.name}-{identity}' / f'slot-{slot:02}'
    parent.mkdir(parents=True, exist_ok=True)
    generation = parent / (datetime.now().strftime('%Y%m%d-%H%M%S-%f') + '_raw-json')
    generation.mkdir()
    records = {}
    for source, data in originals.items():
        target = generation / source.name
        with target.open('xb') as stream:
            stream.write(data)
        digest = hashlib.sha256(data).hexdigest()
        if hashlib.sha256(target.read_bytes()).hexdigest() != digest:
            raise ValueError('Raw JSON backup verification failed')
        records[source.name] = {'source': str(source), 'sha256': digest}
    marker = {'schema': 1, 'files': records, 'reason': 'raw-json'}
    (generation / '.bbe-backup.json').write_text(json.dumps(marker, indent=2), encoding='utf-8')
    return generation


def _stage(path, data, stamp):
    descriptor, name = tempfile.mkstemp(prefix='.bbe-raw-json-', dir=path.parent)
    target = Path(name)
    with os.fdopen(descriptor, 'wb') as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())
    if target.read_bytes() != data:
        raise ValueError('Staged raw save failed verification')
    os.utime(target, (stamp, stamp))
    return target


def commit(path, root, expected, backup_root):
    """Encode, back up, recheck, atomically publish, and roll back on failure."""
    require_game_closed()
    path = Path(path).resolve()
    watched = _watched(path)
    if set(expected) != {str(p) for p in watched} or changed(expected):
        raise ValueError('Save changed since opening. Refresh before editing or saving.')
    encoded, decoded_size = encode(root)
    originals = {p: p.read_bytes() for p in watched}
    stats = {p: p.stat() for p in watched}
    if fingerprints(watched) != expected:
        raise ValueError('Save changed during preparation. Refresh it.')
    stamp = int(time.time())
    output = {path: encoded}
    if len(watched) == 2:
        output[watched[1]] = steam_metadata.rebuild(
            originals[watched[1]], path.name, path.name, len(encoded), decoded_size, timestamp=stamp)
    staged = {}
    replaced = []
    try:
        for target, data in output.items():
            staged[target] = _stage(target, data, stamp)
        generation = _backup(originals, path, backup_root)
        require_game_closed()
        if changed(expected):
            raise ValueError('Save changed before publication. Refresh it; nothing was written.')
        for target, temporary in staged.items():
            os.replace(temporary, target)
            replaced.append(target)
        if decode(path.read_bytes()) != root:
            raise ValueError('Published raw save verification failed')
        return str(generation)
    except Exception:
        for target in reversed(replaced):
            temporary = _stage(target, originals[target], int(stats[target].st_mtime))
            os.utime(temporary, ns=(stats[target].st_atime_ns, stats[target].st_mtime_ns))
            os.replace(temporary, target)
        raise
    finally:
        for temporary in staged.values():
            temporary.unlink(missing_ok=True)
