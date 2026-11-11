"""Native base/freighter snap frames; only the selected pair is evaluated.

Locator suffixes identify instances, not connection types. For example
CubeRoom_Out_Front mates with CubeRoom_In, using both authored child frames.
Coincident locators share a marker; clicking cycles all compatible placements.
"""
from collections import defaultdict
from functools import lru_cache
import json
from pathlib import Path
import re
from mathutils import Matrix
from .utils import mirror_pivot

CACHE = {}
# These use a shape-aware assembly/cable system with different display meshes.
PIPE_PARTS = frozenset({'PIPE', 'PIPESHAPE', 'CURVEPIPESHAPE', 'BASE_BUBPIPE', 'BASE_BUBPIPE_L'})
SPECIAL = {'BASE_BUBPIPE', 'U_POWERLINE', 'U_PIPELINE', 'U_PORTALLINE', 'U_BYTEBEATLINE'}


@lru_cache(maxsize=1)
def catalog():
    return json.loads((Path(__file__).parent / 'resources/base_snapping.json').read_text())


def supports(source, target):
    ids = (source.get('ObjectID'), target.get('ObjectID'))
    return (not all(pid in PIPE_PARTS for pid in ids) and not any(pid in SPECIAL for pid in ids)
            and all(pid in catalog()['parts'] for pid in ids))


@lru_cache(maxsize=512)
def _scene_sockets(scene):
    result, positions = [], {}
    for pi, point in enumerate(catalog()['scenes'][scene]):
        raw = Matrix(point['matrix'])
        for ci, socket in enumerate(point['sockets']):
            match = re.fullmatch(r'(.+)_(In|Out)(?:_.*)?', socket)
            if not match:
                continue
            kind, role = match.groups()
            frame = raw @ Matrix(point.get('socket_matrices', {}).get(socket, Matrix.Identity(4)))
            position = tuple(round(v, 5) for v in frame.translation)
            key = positions.setdefault(position, str(len(positions)))
            result.append((key, f'{pi}:{ci}', kind, role, frame))
    return tuple(result)


def _sockets(pid):
    row = catalog()['parts'].get(pid)
    return _scene_sockets(row['scene']) if row else ()


@lru_cache(maxsize=512)
def _scene_options(source_scene, target_scene):
    sources = defaultdict(list)
    for sk, sc, kind, role, frame in _scene_sockets(source_scene):
        sources[kind, role].append((sc, frame.inverted()))
    result, seen = [], set()
    for tk, tc, kind, role, frame in _scene_sockets(target_scene):
        for sc, inverse in sources[kind, 'Out' if role == 'In' else 'In']:
            relative = frame @ inverse
            signature = (tk, tuple(round(v, 5) for row in relative for v in row))
            if signature not in seen:
                seen.add(signature)
                result.append((tk, sc+'>'+tc, frame.translation.copy(), relative))
    return tuple(result)


def _local_options(sid, tid):
    parts = catalog()['parts']
    if sid not in parts or tid not in parts:
        return ()
    return _scene_options(parts[sid]['scene'], parts[tid]['scene'])


def _native_target(target):
    return mirror_pivot.native_matrix(target.matrix_world, target.get('ObjectID'),
                                     normalized=mirror_pivot.is_normalized(target))


def options(source, target):
    if source == target or not supports(source, target):
        return []
    sid, tid = source.get('ObjectID'), target.get('ObjectID')
    native_target = _native_target(target)
    normalized = mirror_pivot.is_normalized(source)
    result = []
    for tk, sk, position, relative in _local_options(sid, tid):
        matrix = native_target @ relative
        if normalized:
            matrix = mirror_pivot.display_matrix(matrix, sid)
        result.append((tk, sk, native_target @ position, matrix))
    return result


@lru_cache(maxsize=512)
def _scene_points(source_scene, target_scene):
    return tuple({p[0]: p[2] for p in _scene_options(source_scene, target_scene)}.items())


def target_points(source, target):
    if source == target or not supports(source, target):
        return []
    parts = catalog()['parts']
    points = _scene_points(*(parts[o['ObjectID']]['scene'] for o in (source, target)))
    native_target = _native_target(target)
    return [(key, native_target @ position) for key, position in points]


def choose(source, target, target_key=None, cycle_source=False):
    pairs = options(source, target)
    if target_key is not None:
        pairs = [p for p in pairs if p[0] == target_key]
    if not pairs:
        return None
    previous = CACHE.get((source.name, target.name))
    if cycle_source and previous and any(p[:2] == previous for p in pairs):
        current = next(i for i, p in enumerate(pairs) if p[:2] == previous)
        return pairs[(current + int(cycle_source)) % len(pairs)]
    reference = source.matrix_world.to_quaternion()
    return min(pairs, key=lambda p: (round(1-abs(p[3].to_quaternion().dot(reference)), 5),
                                    (p[3].translation-source.matrix_world.translation).length))


def apply(source, target, choice):
    if choice is None:
        return False
    source.matrix_world = choice[3]
    source['snapped_to'] = target.name
    CACHE[source.name, target.name] = choice[:2]
    return True


def snap(source, target, next_target=False, prev_target=False, next_source=False, prev_source=False):
    if not supports(source, target):
        return None
    pairs = options(source, target)
    if not pairs:
        return False
    previous = CACHE.get((source.name, target.name))
    keys = list(dict.fromkeys(p[0] for p in pairs))
    key = previous[0] if previous and previous[0] in keys else None
    if next_target or prev_target:
        key = key or choose(source, target)[0]
        key = keys[(keys.index(key) + (1 if next_target else -1)) % len(keys)]
    choice = choose(source, target, key, cycle_source=1 if next_source else -1 if prev_source else 0)
    return apply(source, target, choice)
