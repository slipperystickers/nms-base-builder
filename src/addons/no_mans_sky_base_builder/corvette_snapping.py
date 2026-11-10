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
              'W': (-1,0,0), 'T': (0,1,0), 'B': (0,-1,0),
              'NE': (1,0,-1), 'NW': (-1,0,-1),
              'SE': (1,0,1), 'SW': (-1,0,1)}
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


def supports(source, target):
    return source.get('ObjectID') in DATA and target.get('ObjectID') in DATA


def _direction_frame(direction):
    normal = Vector(DIRECTIONS[direction]).normalized()
    up = Vector((0, 1, 0)) if abs(normal.y) < .9 else Vector((0, 0, -1))
    side = normal.cross(up).normalized()
    return Matrix((normal, side.cross(normal).normalized(), side)).transposed().to_4x4()


@lru_cache(maxsize=1024)
def _sockets(pid):
    """Typed connection frames, in the part's native save coordinates.

    Room/Block compass suffixes specify the mating direction, rather than
    unrelated socket types. Interior variants (A/B/C/D), stairs, magnets and
    landing-gear cores retain their exact authored type and orientation.
    Numeric suffixes after In/Out only distinguish repeated locator names.
    """
    result = []
    for pi, point in enumerate(DATA.get(pid, ())):
        raw = Matrix(point['matrix'])
        positions = {}
        for ci, socket in enumerate(point['sockets']):
            match = re.fullmatch(r'(.+)_(In|Out)_\d*', socket)
            if not match:
                continue
            kind, role = match.groups()
            frame = raw @ Matrix(point.get('socket_matrices', {}).get(socket, Matrix.Identity(4)))
            # Use the child socket position, which can differ from its parent.
            position = tuple(round(v, 5) for v in frame.translation)
            slot = positions.setdefault(position, len(positions))
            key = str(pi) if slot == 0 else f'{pi}:{slot}'
            direction = re.fullmatch(r'(Room|Block)(NE|NW|SE|SW|N|E|S|W|T|B)', kind)
            if direction:
                kind, axis = direction.groups()
                # Corner-only channels are not ordinary face connections.
                # A diagonal Room input must not accept a cardinal Room output.
                if len(axis) == 2:
                    kind += 'Diagonal'
                frame = frame @ _direction_frame(axis)
            result.append((key, str(pi)+':'+str(ci), kind, role, frame))
    return tuple(result)


@lru_cache(maxsize=512)
def _local_options(sid, tid):
    """Cache geometry by part IDs, never by scene-object transforms."""
    result, seen = [], set()
    for tk, tc, tkind, trole, tm in _sockets(tid):
        for sk, sc, skind, srole, sm in _sockets(sid):
            if tkind != skind or trole == srole:
                continue
            relative = tm @ sm.inverted()
            signature = (tk, tuple(round(v, 5) for row in relative for v in row))
            if signature in seen:
                continue
            seen.add(signature)
            result.append((tk, sc+'>'+tc, tm.translation.copy(), relative))
    return tuple(result)


@lru_cache(maxsize=1)
def _vantage_beam_placements():
    """One marker per location, with native mates and a flush editor placement."""
    choices = []
    locations = {}
    seen = set()
    for key, channel, position, relative in _local_options('B_MAG_1X1', 'B_COK_E'):
        center = tuple(round(v, 5) for v in position)
        key = locations.setdefault(center, key)
        pose = (key, tuple(round(v, 5) for row in relative for v in row))
        if pose not in seen:
            seen.add(pose)
            choices.append((key, channel, position, relative))
    for center, key in locations.items():
        point = DATA['B_COK_E'][int(key.split(':')[0])]
        face = re.fullmatch(r'SnapPoint_(?:SPIGN_)?([NSEWTB])\d*', point['name'])
        if face is None:
            continue
        normal = (Matrix(point['matrix']).to_3x3() @ Vector(DIRECTIONS[face[1]])).normalized()
        # The loose projector sits at its model origin. Its Room/Block snaps
        # can turn the ring edge-on. Offer its base flat on the same hull spot.
        frame = Vector((0, 1, 0)).rotation_difference(normal).to_matrix().to_4x4()
        frame.translation = Vector(center)
        choices.append((key, 'face-parallel', frame.translation.copy(), frame))
    return tuple(choices)


def _placement_choices(sid, tid):
    if (sid, tid) == ('B_MAG_1X1', 'B_COK_E'):
        return _vantage_beam_placements()
    return _local_options(sid, tid)


def _native_target(target):
    return mirror_pivot.native_matrix(target.matrix_world, target.get('ObjectID'),
                                     normalized=mirror_pivot.is_normalized(target))


def options(source, target, *, placement=False):
    if source == target or not supports(source, target):
        return []
    sid, tid = source.get('ObjectID'), target.get('ObjectID')
    native_target = _native_target(target)
    normalized = mirror_pivot.is_normalized(source)
    result = []
    choices = _placement_choices(sid, tid) if placement else _local_options(sid, tid)
    for tk, sk, position, relative in choices:
        matrix = native_target @ relative
        # Legacy .blend objects still use native mesh coordinates. Do not
        # silently give them a display-pivot offset without shifting the mesh.
        if normalized:
            matrix = mirror_pivot.display_matrix(matrix, sid)
        result.append((tk, sk, native_target @ position, matrix))
    return result


def target_points(source, target):
    """Only transform the visible target locations on viewport redraw."""
    if source == target or not supports(source, target):
        return []
    points = {p[0]: p[2] for p in _placement_choices(source.get('ObjectID'), target.get('ObjectID'))}
    native_target = _native_target(target)
    return [(key, native_target @ position) for key, position in points.items()]


def choose(source, target, target_key=None, cycle_source=False):
    pairs = options(source, target, placement=True)
    if target_key is not None:
        pairs = [p for p in pairs if p[0] == target_key]
    if not pairs:
        return None
    previous = CACHE.get((source.name, target.name))
    if cycle_source and previous and any(p[:2] == previous for p in pairs):
        current = next(i for i, p in enumerate(pairs) if p[:2] == previous)
        return pairs[(current + int(cycle_source)) % len(pairs)]
    reference = source.matrix_world.to_quaternion()
    pairs.sort(key=lambda p: (p[1] == 'face-parallel', round(1-abs(p[3].to_quaternion().dot(reference)), 5),
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
    if not supports(source, target):
        return None
    pairs = options(source, target, placement=True)
    if not pairs:
        # Covered native parts with incompatible socket types must not fall
        # through to a generic legacy pairing and produce an invented snap.
        return False
    previous = CACHE.get((source.name, target.name))
    if (not previous and (next_source or prev_source)
            and (source.get('ObjectID'), target.get('ObjectID')) == ('B_MAG_1X1', 'B_COK_E')):
        # Reopening a project clears the transient snap cache. Recover an
        # already placed beam's current marker before advancing its rotation.
        for candidate in pairs:
            delta = candidate[3].inverted_safe() @ source.matrix_world
            if delta.translation.length < .05 and max(abs(delta[r][c] - (r == c))
                                                       for r in range(3) for c in range(3)) < .025:
                previous = CACHE[source.name, target.name] = candidate[:2]
                break
    keys = list(dict.fromkeys(p[0] for p in pairs))
    key = previous[0] if previous and previous[0] in keys else None
    if next_target or prev_target:
        key = key or choose(source, target)[0]
        key = keys[(keys.index(key) + (1 if next_target else -1)) % len(keys)]
    choice = choose(source, target, key, cycle_source=1 if next_source else -1 if prev_source else 0)
    return apply(source, target, choice)
