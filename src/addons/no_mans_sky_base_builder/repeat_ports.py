"""Connector-aware runs for habs, freighter passageways and rigid pipework.

All port geometry and plan matrices in this module are in native part coordinates.
A turned run consists of one compatible corner followed by straight spans.
"""

from dataclasses import dataclass
from functools import lru_cache
from math import pi

from mathutils import Matrix, Vector, kdtree

from . import base_snapping, corvette_snapping

HABS = {key for key in corvette_snapping.DATA if key.startswith(("B_HAB_", "B_HAB1_"))}
CORRIDORS = {}
for family in (
    ("FRE_CORR_A", "FRE_CORR_A_STR", "FRE_CORR_A_L", "FRE_CORR_A_T"),
    ("FRE_CORR_B", "FRE_CORR_B_STR", "FRE_CORR_B_L", "FRE_CORR_B_T"),
    ("FRE_CORR_A_GLAS", "FRE_CORR_GLA_ST", "FRE_CORR_GLA_L", "FRE_CORR_GLA_T"),
    ("CORRIDORX_SPACE", "CORRIDOR_SPACE", "CORRIDORL_SPACE", "CORRIDORT_SPACE"),
):
    for member in family:
        CORRIDORS[member] = family
WALKWAY = "FRE_EXT_WALKWAY"
BUBBLE = "BASE_BUBPIPE"
PIPES = {BUBBLE, "PIPESHAPE", "PIPE"}
SUPPORTED = HABS | CORRIDORS.keys() | PIPES | {WALKWAY}
AXES = tuple(
    Vector(axis) for axis in ((1, 0, 0), (-1, 0, 0), (0, 1, 0), (0, -1, 0), (0, 0, 1), (0, 0, -1))
)


def intent(obj):
    if obj.get("ObjectID") == BUBBLE:
        return obj.get("bbe_bubble_shape", "STRAIGHT:Y")
    return ""


@lru_cache(maxsize=128)
def ports(pid, shape=""):
    if pid in HABS:
        return tuple(
            (frame.translation, frame.col[0].xyz.normalized())
            for frame in corvette_snapping.room_points(pid).values()
        )
    if pid in CORRIDORS or pid == WALKWAY:
        kind = "Ext" if pid == WALKWAY else "FaceCorridor"
        return tuple(
            (m.translation, m.translation.normalized())
            for _, _, k, role, m in base_snapping._sockets(pid)
            if k == kind and role == "In"
        )
    if pid == BUBBLE:
        from . import bubble_preview, bubble_export

        return tuple(
            (Vector(bubble_preview._OFFSETS[k]), bubble_preview._ARMS[k])
            for k in bubble_export.sockets(shape)
        )
    if pid in {"PIPESHAPE", "PIPE", "CURVEPIPESHAPE"}:
        from .part import Part

        curved = pid == "CURVEPIPESHAPE"
        data = Part.SNAP_MATRIX_DICTIONARY["CURVED_PIPES" if curved else "PIPES"]["snap_points"]
        keys = ("BOTTOM0", "TOP0") if curved else ("BOTTOM", "TOP")
        normals = ((0, -1, 0), (-1, 0, 0) if curved else (0, 1, 0))
        return tuple(
            (Matrix(data[k]["matrix"]).translation, Vector(axis)) for k, axis in zip(keys, normals)
        )
    return ()


def eligible(obj):
    pid = obj.get("ObjectID")
    return pid in SUPPORTED and (
        pid != BUBBLE or intent(obj) in {"STRAIGHT:X", "STRAIGHT:Y", "STRAIGHT:Z"}
    )


@lru_cache(maxsize=128)
def steps(pid, shape):
    family = "Corvette room" if pid in HABS else "Pipe" if pid in PIPES else "Freighter passage"
    found = []
    for point, normal in ports(pid, shape):
        for entry, inward in ports(pid, shape):
            pitch = point - entry
            if inward.dot(normal) < -0.999 and pitch.normalized().dot(normal) > 0.9999:
                found.append((point, pitch, family))
    return tuple(found)


@dataclass
class Piece:
    pid: str
    matrix: Matrix


@dataclass
class Route:
    run: Piece
    pitch: Vector
    corner: Piece | None = None


def align_ports(pid, joint, incoming, outgoing, fitting):
    """Find an entry/exit pair, keeping existing facing and lateral lane when possible."""
    best = None
    for quarter in (0, 1, -1, 2):
        rotation = Matrix.Rotation(quarter * pi / 2, 4, "Y")
        axes = rotation.to_3x3()
        for entry, normal in ports(pid):
            if (axes @ normal).dot(-incoming) < 0.9999:
                continue
            translation = joint - axes @ entry
            for exit_point, exit_normal in ports(pid):
                if (axes @ exit_normal).dot(outgoing) < 0.9999:
                    continue
                pitch = axes @ (exit_point - entry)
                if not fitting and pitch.normalized().dot(outgoing) < 0.9999:
                    continue
                # Prefer the existing facing when several orientations mate.
                score = (
                    round(rotation.to_quaternion().angle, 4),
                    round(translation.length_squared, 4),
                    round(pitch.length_squared, 4),
                )
                if best is None or score < best[0]:
                    pose = rotation.copy()
                    pose.translation = translation
                    best = score, Piece(pid, pose), joint + pitch, pitch
    return best[1:] if best else None


@lru_cache(maxsize=4096)
def plan(pid, position, entry_axis, exit_axis):
    joint, incoming, outgoing = map(Vector, (position, entry_axis, exit_axis))
    run_id = pid
    if pid in CORRIDORS and not steps(pid, ""):
        run_id = CORRIDORS[pid][1]  # A locked L has no through-span.
    corner = None
    if incoming.dot(outgoing) < 0.999:
        bend = align_ports(pid, joint, incoming, outgoing, True)
        if bend is None and pid in CORRIDORS:
            bend = align_ports(CORRIDORS[pid][2], joint, incoming, outgoing, True)
        if bend is None:
            return None
        corner, joint, _ = bend
    span = align_ports(run_id, joint, outgoing, outgoing, False)
    if span is None:
        return None
    piece, _, pitch = span
    return Route(piece, pitch, corner)


def world_piece(native, piece):
    return Piece(piece.pid, native @ piece.matrix) if piece else None


def connections(objects, scene_objects):
    """Index openings once on invocation. Shared ports can branch through a real side opening."""
    selected = set(objects)

    def family(pid):
        if pid in CORRIDORS or pid == WALKWAY:
            return "freighter"
        if pid in HABS:
            return "corvette"
        if pid == BUBBLE:
            return "bubble"
        if pid in {"PIPE", "PIPESHAPE", "CURVEPIPESHAPE"}:
            return "pipe"
        return None

    families = {family(obj["ObjectID"]) for obj in selected}
    entries = []
    for obj in scene_objects:
        pid = obj.get("ObjectID")
        if family(pid) not in families:
            continue
        frame = base_snapping._native_target(obj)
        for point, axis in ports(pid, intent(obj)):
            entries.append((obj, point, axis, frame @ point, (frame.to_3x3() @ axis).normalized()))
    tree = kdtree.KDTree(len(entries))
    for i, (_, _, _, point, _) in enumerate(entries):
        tree.insert(point, i)
    if entries:
        tree.balance()
    occupied = set()
    for i, (obj, _, _, point, axis) in enumerate(entries):
        if obj not in selected:
            continue
        if any(
            entries[j][0] != obj
            and family(entries[j][0].get("ObjectID")) == family(obj.get("ObjectID"))
            and entries[j][4].dot(axis) < -0.999
            for _, j, _ in tree.find_range(point, 0.0002)
        ):
            occupied.add(i)
    return [
        (obj, p, n, w, i in occupied) for i, (obj, p, n, w, _) in enumerate(entries) if obj in selected
    ]


def routes(obj, point, normal, occupied, available):
    """At a shared doorway use an open side of its owner, keeping existing parts intact."""
    pid = obj["ObjectID"]
    if pid not in CORRIDORS and pid != WALKWAY:
        return
    if occupied:
        sides = sorted(
            ((p, n) for p, n in available if abs(n.dot(normal)) < 0.001),
            key=lambda port: (port[0] - point).length_squared,
        )
        seen = set()
        for p, n in sides:
            key = tuple(n)
            if key in seen:
                continue
            seen.add(key)
            choice = plan(pid, tuple(p), key, key)
            if choice:
                yield choice
        return
    for axis in (normal, *AXES):
        if axis is not normal:
            if abs(axis.dot(normal)) > 0.001:
                continue
            if abs(axis.y) > 0.5 or abs(normal.y) > 0.5:
                continue
        choice = plan(pid, tuple(point), tuple(normal), tuple(axis))
        if choice:
            yield choice
