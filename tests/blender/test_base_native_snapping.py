"""Base then freighter socket coverage, geometry, click behavior and redraw cost."""
from collections import defaultdict
import csv
import math
from pathlib import Path
import sys
import time
import bpy
from mathutils import Matrix, Vector
sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_support import addon, module, report, D

ns = module('base_snapping')
markers = module('snap_markers')
v2 = module('builder_v2')


def obj(pid):
    o = bpy.data.objects.new(pid, None)
    bpy.context.scene.collection.objects.link(o)
    o['ObjectID'] = o['SnapID'] = pid
    o.matrix_world = v2.X_ROT_90
    return o


def near(a, b):
    assert max(abs(v) for row in a-b for v in row) < 2e-4, (a, b)


start = time.perf_counter()
catalog = ns.catalog()
load_ms = (time.perf_counter()-start)*1000
source, target = obj('W_FLOOR'), obj('W_FLOOR')
parts = catalog['parts']
available = defaultdict(list)
for pid in parts:
    for key, channel, kind, role, frame in ns._sockets(pid):
        available[kind, role].append(pid)
covered, orphan, checked = {}, set(), set()
for stage in ('base', 'freighter'):
    for pid, row in parts.items():
        if not row[stage] or pid in ns.SPECIAL:
            continue
        partners = set()
        for key, channel, kind, role, frame in ns._sockets(pid):
            peers = available[kind, 'Out' if role == 'In' else 'In']
            if peers:
                partners.add(next((p for p in peers if p not in ns.SPECIAL), peers[0]))
            else:
                orphan.add((kind, role))
        covered[pid] = bool(partners)
        for partner in partners:
            signature = (row['scene'], parts[partner]['scene'])
            if signature in checked:
                continue
            checked.add(signature)
            source['ObjectID'] = pid; target['ObjectID'] = partner
            pairs = ns.options(source, target)
            assert pairs, (pid, partner)
            ss = {s[1]: s[4] for s in ns._sockets(pid)}
            ts = {s[1]: s[4] for s in ns._sockets(partner)}
            for tk, connection, position, result in pairs:
                sc, tc = connection.split('>')
                near(result @ ss[sc], target.matrix_world @ ts[tc])
                assert (position-target.matrix_world @ ts[tc].translation).length < 2e-4
                assert abs(result.to_3x3().determinant()-1) < 2e-4

# Independently specified native grid dimensions, with unrotated matching pieces.
for pid, distance in [('W_FLOOR', 16/3), ('CUBEROOM', 4), ('FRE_ROOM_B', 8)]:
    source['ObjectID'] = target['ObjectID'] = pid
    source.matrix_world = target.matrix_world = v2.X_ROT_90
    choices = ns.options(source, target)
    translations = [p[3].translation.length for p in choices
                    if abs(p[3].to_quaternion().dot(v2.X_ROT_90.to_quaternion())) > .99999]
    assert any(abs(d-distance) < 2e-4 for d in translations), (pid, translations)

# Physical building parts exercise Part.snap_to and the registered click operator.
bpy.ops.object.select_all(action='DESELECT')
floor = v2.add_part('W_FLOOR', builder_object=addon.BUILDER)
wall = v2.add_part('W_WALL', builder_object=addon.BUILDER)
floor.matrix_world = v2.X_ROT_90
wall.matrix_world = Matrix.Translation((0,-8,0)) @ v2.X_ROT_90
assert wall.snap_to(floor)
for o in bpy.context.selected_objects: o.select_set(False)
for o in (wall.object, floor.object): o.select_set(True)
bpy.context.view_layer.objects.active = floor.object
assert markers.start(bpy.context, wall.object, floor.object)
points = markers.options(wall.object, floor.object)
assert points
assert len({tuple(round(v,5) for v in p) for _,p in points}) == len(points)
key = points[0][0]
assert bpy.ops.bbe.click_snap_point(target_key=key) == {'FINISHED'}
before = wall.matrix_world.copy()
assert bpy.ops.bbe.click_snap_point(target_key=key) == {'FINISHED'}
assert bpy.context.view_layer.objects.active == floor.object
assert set(bpy.context.selected_objects) == {wall.object, floor.object}
stable = wall.matrix_world.copy()
assert bpy.ops.bbe.click_snap_point(target_key='invalid') == {'CANCELLED'}
near(stable, wall.matrix_world)
markers._reset_history()
assert not ns.CACHE

# Nontrivial target world transform and native/display pivots.
source['ObjectID'] = 'W_WALL'; target['ObjectID'] = 'W_FLOOR'
target.matrix_world = Matrix.Translation((31,-20,6)) @ Matrix.Rotation(.73,4,'Z') @ v2.X_ROT_90 @ Matrix.Scale(2,4)
for tk, connection, position, result in ns.options(source, target):
    sc, tc = connection.split('>')
    ss = next(s[4] for s in ns._sockets('W_WALL') if s[1] == sc)
    ts = next(s[4] for s in ns._sockets('W_FLOOR') if s[1] == tc)
    near(result @ ss, target.matrix_world @ ts)

source['ObjectID'] = 'W_FLOOR'; target['ObjectID'] = 'FRE_ROOM_B'
assert ns.supports(source, target) and not ns.options(source, target)
near_source = source.matrix_world.copy()
assert ns.snap(source, target) is False
near(near_source, source.matrix_world)
source['ObjectID'] = 'U_POWERLINE'
assert ns.snap(source, target) is None
source['ObjectID'] = 'BASE_BUBPIPE'
assert ns.snap(source, target) is None

source['ObjectID'] = 'W_WALL'; target['ObjectID'] = 'W_FLOOR'
ns.target_points(source, target)
start = time.perf_counter()
for _ in range(2000): ns.target_points(source, target)
redraw_ms = (time.perf_counter()-start)/2
assert redraw_ms < 2, redraw_ms
catalog_ids = {r['---'].lstrip('^') for r in csv.DictReader((D/'resources/DT_PartDefinition.csv').open(encoding='utf-16'))}
report('base-native-snapping', dict(parts=len(parts), base=sum(r['base'] for r in parts.values()),
    freighter=sum(r['freighter'] for r in parts.values()), compatible_parts=sum(covered.values()),
    no_partner=[p for p, ok in covered.items() if not ok], orphan_channels=sorted(orphan),
    missing_catalog=sorted(set(parts)-catalog_ids), checked_scene_pairs=len(checked),
    catalog_load_ms=load_ms, warm_marker_ms=redraw_ms))
