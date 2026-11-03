"""Connection frames read from the installed game's Corvette placement scenes."""
import json
import math
import re
from pathlib import Path
from functools import lru_cache
from mathutils import Matrix, Vector
from .utils import mirror_pivot

DATA = json.loads((Path(__file__).parent / 'resources/corvette_snapping.json').read_text())['parts']
DIRECTIONS = {'N': (0,0,-1), 'S': (0,0,1), 'E': (1,0,0),
              'W': (-1,0,0), 'T': (0,1,0), 'B': (0,-1,0)}
CACHE = {}


@lru_cache(maxsize=64)
def room_points(pid):
    result = {}
    for index, point in enumerate(DATA.get(pid, ())):
        sockets = point['sockets']
        inward = next((re.fullmatch(r'Room([NSEWTB])_In_', s) for s in sockets
                       if re.fullmatch(r'Room([NSEWTB])_In_', s)), None)
        outward = next((re.fullmatch(r'Room([NSEWTB])_Out_', s) for s in sockets
                        if re.fullmatch(r'Room([NSEWTB])_Out_', s)), None)
        if not inward and not outward:
            continue
        raw = Matrix(point['matrix'])
        normal = Vector(DIRECTIONS[(inward or outward).group(1)]) * (1 if inward else -1)
        normal = (raw.to_3x3() @ normal).normalized()
        up = Vector((0,1,0)) if abs(normal.y) < .9 else Vector((0,0,-1))
        side = normal.cross(up).normalized()
        up = side.cross(normal).normalized()
        frame = Matrix((normal, up, side)).transposed().to_4x4()
        frame.translation = raw.translation
        result[str(index)] = frame
    return result


def options(source, target):
    sid, tid = source.get('ObjectID'), target.get('ObjectID')
    if sid not in DATA or tid not in DATA:
        return []
    native_target = mirror_pivot.native_matrix(target.matrix_world, tid,
                                               normalized=mirror_pivot.is_normalized(target))
    pairs = []
    if sid == 'B_DOOR0':
        for ti, tp in enumerate(DATA[tid]):
            accepted = {s.replace('_In_', '') for s in tp['sockets']
                        if re.fullmatch(r'Int(?:NS|EW)[ABCD]_In_', s)}
            if not accepted:
                continue
            for si, sp in enumerate(DATA[sid]):
                offered = {s.replace('_Out_', '') for s in sp['sockets'] if '_Out_' in s}
                if not accepted & offered:
                    continue
                tm, sm = Matrix(tp['matrix']), Matrix(sp['matrix'])
                matrix = native_target @ tm @ sm.inverted()
                pairs.append((str(ti), str(si), native_target @ tm.translation,
                              mirror_pivot.display_matrix(matrix, sid)))
    else:
        for ti, tm in room_points(tid).items():
            for si, sm in room_points(sid).items():
                matrix = native_target @ tm @ Matrix.Rotation(math.pi, 4, 'Y') @ sm.inverted()
                pairs.append((ti, si, native_target @ tm.translation,
                              mirror_pivot.display_matrix(matrix, sid)))
    return pairs


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
    pairs.sort(key=lambda p: (round(1-abs(p[3].to_quaternion().dot(reference)), 5),
                              (p[3].translation-source.matrix_world.translation).length))
    return pairs[0]


def apply(source, target, choice):
    if choice is None:
        return False
    source.matrix_world = choice[3]
    source['snapped_to'] = target.name
    CACHE[source.name, target.name] = choice[:2]
    return True


def snap(source, target, next_target=False, prev_target=False, next_source=False, prev_source=False):
    pairs = options(source, target)
    if not pairs:
        return None
    previous = CACHE.get((source.name, target.name))
    keys = list(dict.fromkeys(p[0] for p in pairs))
    key = previous[0] if previous and previous[0] in keys else None
    if next_target or prev_target:
        key = key or choose(source, target)[0]
        key = keys[(keys.index(key) + (1 if next_target else -1)) % len(keys)]
    choice = choose(source, target, key, cycle_source=1 if next_source else -1 if prev_source else 0)
    return apply(source, target, choice)
