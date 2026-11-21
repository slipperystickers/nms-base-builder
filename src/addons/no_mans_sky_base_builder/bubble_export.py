"""Plan native bubble shapes using neighboring sockets and placement frames.

The 2026-10-20 native unit-scale experiments bracket local roll recognition at
8 degrees passing / 10 failing, and socket gap at .075 passing / .100 failing.
These are measured brackets, not exact universal engine thresholds. Borderline
contacts are reported as uncertain. Scaled parts retain the older, narrower
supported envelope. Keep editor snapping tolerance separate from game contacts.

Preserve working native frames, including gradually twisted straight chains.
For independently oriented editor meshes, relabel each local frame using cube
symmetries; do not require one global frame. Only roll straights with unwanted
side contacts, using the measured working roll/gap envelope. Unit-scale
straights use six degrees so a single lateral contact clears the gap bracket.
"""
from collections import defaultdict
from itertools import permutations, product
import math

from mathutils import Matrix, Vector

ARMS = {'Front': Vector((0, 0, 1)), 'Back': Vector((0, 0, -1)),
        'Left': Vector((-1, 0, 0)), 'Right': Vector((1, 0, 0)),
        'Top': Vector((0, 1, 0)), 'Bot': Vector((0, -1, 0))}
OPPOSITE = {'Front': 'Back', 'Back': 'Front', 'Left': 'Right',
            'Right': 'Left', 'Top': 'Bot', 'Bot': 'Top'}
STRAIGHTS = {'X': ('Left', 'Right'), 'Y': ('Bot', 'Top'), 'Z': ('Back', 'Front')}
POSITION_TOLERANCE = .025
SUPPORTED_ROLL = math.radians(8.001)
REJECTED_ROLL = math.radians(9.999)
SUPPORTED_GAP = .07501
REJECTED_GAP = .09999


def _stable_frame(rotation):
    """Choose one encoding of the same orthogonal grid, regardless of root roll."""
    axes = (Vector((1, 0, 0)), Vector((0, 1, 0)), Vector((0, 0, 1)))
    choices = []
    for order in permutations(range(3)):
        for signs in product((-1, 1), repeat=3):
            local = Matrix([axes[order[i]] * signs[i] for i in range(3)]).transposed()
            if local.determinant() > 0:
                candidate = rotation @ local
                choices.append(candidate)
    return max(choices, key=lambda r: sum(r[i][i] for i in range(3)))


def sockets(intent):
    if intent.startswith('STRAIGHT:'):
        return STRAIGHTS.get(intent.split(':', 1)[1], ())
    if intent.startswith(('ELBOW:', 'TEE:', 'CROSS:', 'CORNER3:', 'CORNER4:', 'FIVE:', 'SIX:')):
        names = tuple(sorted(set(intent.split(':', 1)[1].split('+'))))
        return names if all(name in ARMS for name in names) else ()
    return ()


def shape(ports):
    ports = set(ports)
    if not ports:
        return frozenset(STRAIGHTS['Y'])
    for pair in STRAIGHTS.values():
        if ports.issubset(pair):
            return frozenset(pair)
    return frozenset(ports)


def frame(record):
    up, at = Vector(record['Up']), Vector(record['At'])
    scale = up.length
    if scale < 1e-8 or at.length < 1e-8:
        raise ValueError('Bubble duct has a zero scale or direction before export.')
    up, at = up.normalized(), at.normalized()
    if abs(up.dot(at)) > 1e-4:
        raise ValueError('Bubble duct directions are skewed. Remove shear before exporting.')
    rotation = Matrix((up.cross(at), up, at)).transposed()
    return Vector(record['Position']) + up * scale, rotation, scale


def _pairs(points, tolerance=POSITION_TOLERANCE):
    """Spatial candidates; entries are (index, port, point, scale)."""
    cell_size = max((p[3] for p in points), default=1) * tolerance
    cell_size = max(cell_size, 1e-8)
    cells = defaultdict(list)
    for entry in points:
        cell = tuple(math.floor(value / cell_size) for value in entry[2])
        for delta in product((-1, 0, 1), repeat=3):
            near = tuple(cell[i] + delta[i] for i in range(3))
            for other in cells.get(near, ()):
                if entry[0] != other[0] and (entry[2] - other[2]).length <= max(entry[3], other[3]) * tolerance:
                    yield other, entry
        cells[cell].append(entry)


def native_contacts(nodes, links=None):
    """Conservative contacts for frames in the empirically supported envelope."""
    points = [(i, port, c + r @ arm * scale, scale)
              for i, (c, r, scale) in nodes.items() for port, arm in ARMS.items()]
    found = {i: set() for i in nodes}
    uncertain = []
    for a, b in _pairs(points, tolerance=.10001):
        i, port, _, _ = a
        j, other, _, _ = b
        if OPPOSITE[port] != other:
            continue
        rotation = nodes[i][1].transposed() @ nodes[j][1]
        angle = rotation.to_quaternion().angle
        angle = min(angle, 2 * math.pi - angle)
        gap = (a[2] - b[2]).length / max(a[3], b[3])
        if angle >= REJECTED_ROLL or gap >= REJECTED_GAP:
            continue
        unit = abs(a[3] - 1) < 1e-4 and abs(b[3] - 1) < 1e-4
        supported_angle = SUPPORTED_ROLL if unit else math.radians(5.001)
        supported_gap = SUPPORTED_GAP if unit else POSITION_TOLERANCE + 1e-6
        if angle > supported_angle or gap > supported_gap:
            uncertain.append((i, j))
            continue
        found[i].add(port)
        found[j].add(other)
        if links is not None:
            links.setdefault((i, port), set()).add((j, other))
            links.setdefault((j, other), set()).add((i, port))
    return found, uncertain


def _cube_frames(rotation):
    for order in permutations(range(3)):
        for signs in product((-1, 1), repeat=3):
            basis = Matrix.Identity(3)
            for column in range(3):
                basis.col[column] = Vector(tuple(
                    signs[column] if axis == order[column] else 0 for axis in range(3)))
            if basis.determinant() > 0:
                yield rotation @ basis


def _mapped_ports(rotation, directions):
    names = set()
    for direction in directions:
        local = rotation.transposed() @ direction
        name = max(ARMS, key=lambda n: local.dot(ARMS[n]))
        if local.dot(ARMS[name]) < .99999:
            return None
        names.add(name)
    return frozenset(names)


def _spread_straight_twists(compiled, mapped, graph, hints, contacts):
    """Use axial freedom of a straight bridge without moving any opening.

    Only interpolate a collinear, unbranched chain between two fixed bends.
    Each resulting relative rotation must stay inside the measured envelope.
    The native E-series established this construction through 42 degrees total.
    """
    straights = {i for i in hints if hints[i]['shape'].startswith('STRAIGHT:')}
    visited = set()
    for start in sorted(hints.keys() - straights):
        for first in sorted(graph[start] & straights):
            if (start, first) in visited:
                continue
            path = [start, first]
            while path[-1] in straights:
                if len(graph[path[-1]]) != 2:
                    break
                next_node = next(iter(graph[path[-1]] - {path[-2]}))
                if next_node in path:
                    break
                path.append(next_node)
            if path[-1] in straights or len(path) < 3:
                continue
            visited.add((path[-1], path[-2]))
            if all(shape(contacts[i]) == mapped[i] for i in path):
                continue
            end = path[-1]
            delta = compiled[end][0] - compiled[start][0]
            if delta.length < 1e-6:
                continue
            axis = delta.normalized()
            left, right = compiled[start][1], compiled[end][1]
            turn = right @ left.transposed()
            if (turn @ axis - axis).length > 1e-5:
                continue  # This changes the tube axis, not just its axial roll.
            angle = left.to_quaternion().rotation_difference(right.to_quaternion()).angle
            angle = min(angle, 2 * math.pi - angle)
            supported = (SUPPORTED_ROLL if all(abs(compiled[i][2] - 1) < 1e-4 for i in path)
                         else math.radians(5.001))
            if angle / (len(path) - 1) > supported:
                continue
            candidates = {}
            for k, index in enumerate(path[1:-1], 1):
                center, old, scale = compiled[index]
                if ((center - compiled[start][0]).cross(axis).length > 1e-5
                        or any(abs((old @ ARMS[p]).dot(axis)) < .99999 for p in mapped[index])):
                    break
                rotation = left.to_quaternion().slerp(
                    right.to_quaternion(), k / (len(path) - 1)).to_matrix()
                ports = _mapped_ports(rotation, (old @ ARMS[p] for p in mapped[index]))
                if ports is None:
                    break
                candidates[index] = ((center, rotation, scale), ports)
            else:
                for index, (node, ports) in candidates.items():
                    compiled[index], mapped[index] = node, ports


def plan_objects(objects, hints):
    """Return records, per-object issues, and predicted native display nodes.

    Hints map output indices to {shape, name}. Unhinted native ducts remain
    untouched and participate as obstacles. Project JSON bypasses this method.
    Shape warnings are advisory: callers may export the planned records for
    in-game testing. The live preview keeps reporting the same warnings.
    No bpy access, object mutation, metadata injection, or save writes occur.
    """
    hints = {i: hint for i, hint in hints.items()
             if i < len(objects) and objects[i].get('ObjectID') == '^BASE_BUBPIPE'
             and sockets(str(hint.get('shape', '')))}
    nodes = {i: frame(record) for i, record in enumerate(objects)
             if record.get('ObjectID') == '^BASE_BUBPIPE'}
    before_contacts, before_uncertain = native_contacts(nodes)
    desired = {i: {port: nodes[i][1] @ ARMS[port]
                   for port in sockets(hint['shape'])} for i, hint in hints.items()}
    points = [(i, port, nodes[i][0] + direction * nodes[i][2], nodes[i][2])
              for i, ports in desired.items() for port, direction in ports.items()]
    graph = {i: set() for i in hints}
    joined = {i: set() for i in hints}
    for a, b in _pairs(points):
        i, port, _, _ = a
        j, other, _, _ = b
        if desired[i][port].dot(desired[j][other]) > -.9999:
            continue
        graph[i].add(j)
        graph[j].add(i)
        joined[i].add(port)
        joined[j].add(other)
    compiled = dict(nodes)
    mapped = {}
    remaining = set(hints)
    while remaining:
        first = min(remaining)
        component, pending = set(), [first]
        while pending:
            i = pending.pop()
            if i in component:
                continue
            component.add(i)
            pending.extend(graph[i] - component)
        remaining -= component
        # Imported/native routes that already work must retain their frames.
        # This preserves the observed 42-degree gradual bridge.
        if (all(shape(before_contacts[i]) == frozenset(sockets(hints[i]['shape'])) for i in component)
                and not any(i in component or j in component for i, j in before_uncertain)):
            for i in component:
                mapped[i] = frozenset(sockets(hints[i]['shape']))
            continue
        # An elbow fixes a local plane; a straight may have irrelevant axial roll.
        root = min(component, key=lambda i: (not hints[i]['shape'].startswith('ELBOW:'), i))
        common = _stable_frame(nodes[root][1])
        if len(component) == 1 and hints[root]['shape'].startswith('STRAIGHT:'):
            # With no connections the game's fallback is always its local Y tube.
            direction = next(iter(desired[root].values()))
            up = common.col[1]
            if abs(up.dot(direction)) < .9999:
                common = up.rotation_difference(direction).to_matrix() @ common
        pending = [(root, common)]
        visited = set()
        while pending:
            i, reference = pending.pop(0)
            if i in visited:
                continue
            visited.add(i)
            names = _mapped_ports(reference, desired[i].values())
            if names is not None:
                rotation = reference.copy()
            else:
                # Choose the equivalent local labeling nearest this neighbor.
                # Geometry stays fixed; gradual twists remain local.
                rotation = max(_cube_frames(nodes[i][1]), key=lambda r:
                               abs(r.to_quaternion().dot(reference.to_quaternion())))
                names = _mapped_ports(rotation, desired[i].values())
            mapped[i] = names
            compiled[i] = (nodes[i][0], rotation, nodes[i][2])
            pending.extend((j, rotation) for j in sorted(graph[i] - visited))

    contacts, _ = native_contacts(compiled)
    if any(shape(contacts[i]) != mapped[i] for i in hints):
        _spread_straight_twists(compiled, mapped, graph, hints, contacts)
        contacts, _ = native_contacts(compiled)
    # Roll only straights with unwanted side contacts. Both parallel sides roll
    # together, separating nearby routes without adding objects.
    for i in sorted(hints):
        if hints[i]['shape'].startswith('STRAIGHT:') and contacts[i] - mapped[i]:
            axis = next(axis for axis, pair in STRAIGHTS.items() if set(pair) == mapped[i])
            center, rotation, scale = compiled[i]
            # A single 5-degree roll separates a lateral socket by .0872:
            # inside the unmeasured .075-.100 gap bracket. At unit scale,
            # 6 degrees separates it by .1047 while remaining a tested
            # working end connection (native A/B and E cases). Keep the
            # older conservative behavior for scales we did not test.
            roll = 6 if abs(scale - 1) < 1e-4 else 5
            compiled[i] = (center, rotation @ Matrix.Rotation(math.radians(roll), 3, axis), scale)
    contact_links = {}
    after, uncertain = native_contacts(compiled, contact_links)
    # The user-confirmed 30-tube layout exported correctly in 18.1.116 despite
    # seven warnings produced solely by closed-side/closed-side coincidences.
    # These candidate socket pairs do not establish a visible connection.
    # Correct the prediction only: preserve the exact proven export frames.
    closed_pairs = {
        (i, port, j, other)
        for (i, port), neighbors in contact_links.items()
        for j, other in neighbors
        if i in mapped and j in mapped
        and port not in mapped[i] and other not in mapped[j]
    }
    for i, port, j, other in closed_pairs:
        contact_links[i, port].discard((j, other))
        if not contact_links[i, port]:
            after[i].discard(port)
    issues = {}
    for i in sorted(hints):
        if shape(after[i]) != mapped[i]:
            wanted = hints[i]['shape'].split(':')[0].lower()
            if wanted == 'elbow' and len(joined[i]) < 2:
                detail = ("This elbow has an open or misaligned end. Connect both "
                          "openings to other tubes to make a bend in game.")
            elif wanted in ('tee', 'cross', 'corner3', 'corner4', 'five', 'six') and len(joined[i]) < len(mapped[i]):
                detail = ("This junction is unfinished. Connect its free opening "
                          "to a straight, or finish the elbow attached there.")
            elif after[i] - mapped[i]:
                detail = (("This elbow would become a T-junction in game. "
                           "Use T-junction, or move the nearby tube away.")
                          if wanted == 'elbow' and len(after[i]) == 3
                          and any(OPPOSITE[p] in after[i] for p in after[i]) else
                          ("The nearby tube makes this a three-way corner in game. "
                           "Use the corner junction, or move the nearby tube away.")
                          if len(after[i]) == 3 and not any(OPPOSITE[p] in after[i] for p in after[i]) else
                          ("This tube would become a + junction in game. "
                           "Use + junction, or move the extra tube away.")
                          if len(after[i]) == 4 and all(OPPOSITE[p] in after[i] for p in after[i]) else
                          ("A nearby tube adds an unwanted connection. "
                           "Move or turn the extra tube away."))
            else:
                detail = ("The tubes turn too far apart at this joint. "
                          "Use Snap to line up this end, or turn the connected branch.")
            issues[i] = f"{hints[i]['name']}: {detail}"
    for i, j in uncertain:
        for index in (i, j):
            if index in hints:
                issues[index] = (f"{hints[index]['name']}: This joint is between the "
                                 "angles or gaps tested in game. Use Snap to align "
                                 "the tubes before exporting.")
    for i in nodes.keys() - hints.keys():
        if after[i] != before_contacts[i]:
            issues[i] = 'This route changes a nearby grouped tube. Ungroup that tube and check its connections.'

    result = list(objects)
    for i in hints:
        center, rotation, scale = compiled[i]
        record = dict(objects[i])
        record.update(Position=list(center - rotation.col[1] * scale),
                      Up=list(rotation.col[1] * scale), At=list(rotation.col[2]))
        result[i] = record
    return result, issues, {i: (compiled[i], after[i]) for i in nodes}


def compile_objects(objects, hints, *, for_save=False):
    """Export planned native frames even when predicted shapes need checking.

    Save writes require resolved chains. Clipboard and standalone files retain
    the draft so builders can share it or finish editing later.
    """
    if not hints:
        return objects
    records, issues, _ = plan_objects(objects, hints)
    if issues:
        if for_save:
            raise ValueError('Finish your bubble tube chain before exporting to your save. '
                             + next(iter(issues.values()))
                             + ' Connect or remove the unfinished opening, then try again.')
        import logging
        logging.getLogger(__name__).warning(
            'Exporting with %d bubble tube warning(s): %s',
            len(issues), next(iter(issues.values())))
    return records
