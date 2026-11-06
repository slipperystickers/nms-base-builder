"""Native Corvette connections: coverage, compatibility, transforms and click UI.

Run in a factory-startup Blender process, with --python-exit-code 1.
No game save or user's open Blender project is loaded or changed.
"""
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

cs = module('corvette_snapping')
markers = module('snap_markers')
pivot = module('utils.mirror_pivot')
v2 = module('builder_v2')
habitat = module('habitat_preview')


def near(a, b, tolerance=1e-4):
    assert max(abs(v) for row in a-b for v in row) < tolerance, (a, b)


def obj(pid):
    o = bpy.data.objects.new(pid, None)
    bpy.context.scene.collection.objects.link(o)
    o['ObjectID'] = o['SnapID'] = pid
    o.matrix_world = v2.X_ROT_90
    return o


source, target = obj('B_WNG_A'), obj('B_HAB_D')
catalog = {r['---'].lstrip('^'): r for r in csv.DictReader(
    (D/'resources/DT_PartDefinition.csv').open(encoding='utf-16'))}
available = defaultdict(list)
for pid in cs.DATA:
    for key, channel, kind, role, frame in cs._sockets(pid):
        available[kind, role].append((pid, key, channel, frame))

covered, orphan = {}, []
for pid in cs.DATA:
    source['ObjectID'] = source['SnapID'] = pid
    partners = set()
    for key, channel, kind, role, frame in cs._sockets(pid):
        peers = available[kind, 'In' if role == 'Out' else 'Out']
        if peers:
            partners.add(peers[0][0])
        else:
            orphan.append((pid, key, channel, kind, role))
    count = 0
    for partner in partners:
        target['ObjectID'] = target['SnapID'] = partner
        pairs = cs.options(source, target)
        assert pairs, (pid, partner)
        source_channels = {p[1]: p[4] for p in cs._sockets(pid)}
        target_channels = {p[1]: p[4] for p in cs._sockets(partner)}
        for tk, sk, location, result in pairs:
            sc, tc = sk.split('>')
            # Independently check both transformed socket frames coincide.
            near(result @ source_channels[sc], target.matrix_world @ target_channels[tc])
            assert (location - (target.matrix_world @ target_channels[tc].translation)).length < 1e-4
            assert result.to_3x3().determinant() > .99
        count += len(pairs)
    if count:
        covered[pid] = count
# The portal has only Pylon_Out9_ (no complementary native Corvette socket).
# It is surface placed in-game; don't invent a marker to reach 100% coverage.
assert set(cs.DATA)-covered.keys() == {'U_MINIPORTAL_CV'}

# Authored placements, rather than only comparing two implementations of math.
source['ObjectID'] = 'B_WNG_A'; target['ObjectID'] = 'B_HAB_D'
source.matrix_world = target.matrix_world = v2.X_ROT_90
wing_choices = cs.options(source, target)
assert any(max(abs(v) for row in (target.matrix_world.inverted() @ p[3])-
               Matrix.Translation((3, 1.5, 0)) for v in row) < 1e-4 for p in wing_choices)
source['ObjectID'] = 'B_LND_A'
landing_choices = cs.options(source, target)
assert any(max(abs(v) for row in (target.matrix_world.inverted() @ p[3])-
               Matrix.Translation((0, -3, -3)) for v in row) < 1e-4 for p in landing_choices)

# Individually translated and rotated sockets must survive extraction.
hopper = next(p for p in cs._sockets('B_HOP_A') if p[1].endswith(':0') and
               cs.DATA['B_HOP_A'][int(p[0])]['name'] == 'SnapPoint_E3')
raw = cs.DATA['B_HOP_A'][int(hopper[0])]
expected = Matrix(raw['matrix']) @ Matrix(raw['socket_matrices']['RoomW_Out_'])
assert (hopper[4].translation-expected.translation).length < 1e-5
assert (hopper[4].translation-Matrix(raw['matrix']).translation).length > .01
stairs = [p for p in cs._sockets('B_HAB_A') if p[2] == 'StairsTA']
assert any(abs(p[4].to_quaternion().angle-math.pi) < 1e-4 for p in stairs)

# No door-to-wing fallback, diagonal-face substitution, or self snapping.
source['ObjectID'] = 'B_DOOR0'; target['ObjectID'] = 'B_WNG_A'
before = source.matrix_world.copy(); cache = dict(cs.CACHE)
assert cs.snap(source, target) is False
assert not markers.options(source, target)
near(source.matrix_world, before); assert cs.CACHE == cache
assert cs.snap(source, source) is False
target['ObjectID'] = 'B_HAB_D'; source['ObjectID'] = 'B_HAB_D'
corner_keys = {str(i) for i, p in enumerate(cs.DATA['B_HAB_D'])
               if p['name'] in ('SnapPoint_NE1', 'SnapPoint_NW1', 'SnapPoint_SE3', 'SnapPoint_SW3')}
assert not corner_keys & {p[0] for p in cs.options(source, target)}

# Rotation/scale covariance and display-pivot migration independence.
for sid, tid in [('B_WNG_A', 'B_HAB_D'), ('B_CON_7', 'B_COK_D'),
                 ('B_STAIRS0', 'B_HAB_A'), ('B_MAG_1X1', 'B_HAB_D')]:
    source['ObjectID'], target['ObjectID'] = sid, tid
    for normalized in (False, True):
        for ob in (source, target):
            ob.pop(pivot.OBJECT_TAG, None)
            if normalized:
                ob[pivot.OBJECT_TAG] = ob['ObjectID']
        for scale in (.05, .25, 1, 3):
            native = (Matrix.Translation((23, -17, 8)) @ Matrix.Rotation(.7, 4, 'Z') @
                      Matrix.Rotation(.4, 4, 'Y') @ v2.X_ROT_90 @ Matrix.Scale(scale, 4))
            target.matrix_world = pivot.display_matrix(native, tid) if normalized else native
            for tk, sk, pos, result in cs.options(source, target):
                relative = next(p[3] for p in cs._local_options(sid, tid) if p[:2] == (tk, sk))
                near(pivot.native_matrix(result, sid, normalized=normalized), native @ relative)
                assert abs(result.to_scale().x-scale) < 1e-4
    for ob in (source, target): ob.pop(pivot.OBJECT_TAG, None)

# Click operators keep the target/selection, cycle alternatives and reject bad keys.
source['ObjectID'] = source['SnapID'] = 'B_WNG_A'
target['ObjectID'] = target['SnapID'] = 'B_HAB_D'
source.matrix_world = target.matrix_world = v2.X_ROT_90
for ob in bpy.context.selected_objects: ob.select_set(False)
source.select_set(True); target.select_set(True); bpy.context.view_layer.objects.active = target
assert markers.start(bpy.context, source, target)
key = markers.options(source, target)[0][0]
before_target = target.matrix_world.copy()
assert bpy.ops.bbe.click_snap_point(target_key=key) == {'FINISHED'}
first = cs.CACHE[source.name, target.name]
assert bpy.ops.bbe.click_snap_point(target_key=key) == {'FINISHED'}
assert cs.CACHE[source.name, target.name] != first
near(target.matrix_world, before_target)
assert set(bpy.context.selected_objects) == {source, target}
before = source.matrix_world.copy()
assert bpy.ops.bbe.click_snap_point(target_key='invalid') == {'CANCELLED'}
near(source.matrix_world, before)
cs.snap(source, target); pair = cs.CACHE[source.name, target.name]
cs.snap(source, target, next_source=True); cs.snap(source, target, prev_source=True)
assert cs.CACHE[source.name, target.name] == pair
target.select_set(False); assert markers.objects(bpy.context) is None

# Vantage's three rear openings still track only actual attached habs/doors.
source['ObjectID'] = 'B_HAB_D'; target['ObjectID'] = 'B_COK_E'
target.matrix_world = source.matrix_world = v2.X_ROT_90
rear = [str(i) for i,p in enumerate(cs.DATA['B_COK_E'])
        if p['name'] in ('SnapPoint_N0', 'SnapPoint_N1', 'SnapPoint_N2')]
assert len(rear) == 3
for key in rear:
    cs.apply(source, target, cs.choose(source, target, key))
    assert habitat.opening_mask(target, [source]) in (1, 2, 4)

# Marker redraws reuse cached local geometry instead of rebuilding every option.
source['ObjectID'] = 'B_WNG_A'; target['ObjectID'] = 'B_HAB_D'
cs.target_points(source, target)
start = time.perf_counter()
for i in range(1000): cs.target_points(source, target)
marker_ms = (time.perf_counter()-start)
assert marker_ms < 1.0, marker_ms
report('corvette_native_snapping', dict(parts=len(cs.DATA), points=sum(map(len, cs.DATA.values())),
       catalog_parts=len(cs.DATA.keys() & catalog.keys()), parts_with_compatible_connections=len(covered),
       checked_transforms=sum(covered.values()), unmatched_channels=len(orphan),
       surface_placed_only=sorted(set(cs.DATA)-covered.keys()),
       marker_ms_per_redraw=marker_ms, all_checks_passed=True))
