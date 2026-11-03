"""Compile independently rotated editor elbows to the in-game-proven loop.

Includes the actual successful fixture when available and its rejected 180-
degree diagnostic counterparts, rather than testing only the predictor itself.
"""
import copy
import json
import math
import sys
from pathlib import Path

import bpy
from mathutils import Matrix, Vector

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_support import addon, module

export = module('bubble_export')
preview = module('bubble_preview')
qa = Path(r'C:\Users\kengo\OneDrive\Desktop\NMS\kuma_station_builder\qa\bubble_corners_20261018')
proof = json.loads((qa / 'Bubble-Open-Loop-5deg/Bubble-Open-Loop-5deg.nmsbase').read_text())['Objects']
directions = [('Top', 'Right'), ('Bot', 'Top'), ('Bot', 'Right'),
              ('Bot', 'Left'), ('Bot', 'Top'), ('Top', 'Left')]
objects, hints = [], {}
for i, p in enumerate(proof):
    center = export.frame(p)[0]
    ports = ('Bot', 'Top') if i in (1, 4) else ('Bot', 'Front')
    # Independently orient the same asset-browser elbow in each corner.
    rotation = next(r.to_3x3() for r in preview._ROTATIONS
                    if {tuple(round(v) for v in r.to_3x3() @ export.ARMS[n]) for n in ports}
                    == {tuple(export.ARMS[n]) for n in directions[i]})
    record = dict(p, Position=list(center - rotation.col[1]),
                  Up=list(rotation.col[1]), At=list(rotation.col[2]),
                  UserData=i * 16, Message='preserve me')
    objects.append(record)
    hints[i] = {'shape': ('STRAIGHT:' + 'Y') if i in (1, 4) else 'ELBOW:Bot+Front', 'name': 'duct ' + str(i)}
before = copy.deepcopy(objects)
actual = export.compile_objects(objects, hints)
assert objects == before
assert len(actual) == len(proof) == 6
for i, (a, p) in enumerate(zip(actual, proof)):
    assert a['ObjectID'] == p['ObjectID']
    assert a['UserData'] == i * 16 and a['Message'] == 'preserve me'
    assert max(abs(x-y) for key in ('Position', 'Up', 'At') for x, y in zip(a[key], p[key])) < 1e-5, (i, a, p)

# The same construction must survive whole-route rotation, translation and scale.
from mathutils import Euler
whole = Euler((.31, .38, .19)).to_matrix()
offset = Vector((11, 23, 5))
for scale in (.5, 3):
    def transformed(record):
        return dict(record, Position=list(whole @ Vector(record['Position']) * scale + offset),
                    Up=list(whole @ Vector(record['Up']) * scale), At=list(whole @ Vector(record['At'])))
    rotated = export.compile_objects([transformed(p) for p in objects], hints)
    for p, expected in zip(rotated, map(transformed, proof)):
        assert max(abs(a-b) for key in ('Position', 'Up', 'At') for a,b in zip(p[key], expected[key])) < 2e-5

# Every control/failure in the recent diagnostic has the same visible geometry
# as A or the known-good loop. It must encode to those already tested frames.
cases = json.loads((qa / 'flow-20261019/socket-diagnostic-cases.json').read_text())['cases']
for case in cases:
    records = case['objects']
    case_hints = {}
    centers = [export.frame(p)[0] for p in records]
    for i, p in enumerate(records):
        c, rotation, _ = export.frame(p)
        arms = [(other-c).normalized() for j, other in enumerate(centers) if j != i and abs((other-c).length-2) < 1e-4]
        # The six-piece loop's middle crossbar is deliberately absent.
        if len(records) == 6:
            arms = [(centers[j]-c).normalized() for j in ((i-1)%6, (i+1)%6)]
        names = {max(export.ARMS, key=lambda n: (rotation.transposed() @ arm).dot(export.ARMS[n])) for arm in arms}
        port_shape = export.shape(names)
        axis = next((axis for axis, pair in export.STRAIGHTS.items() if set(pair) == port_shape), None)
        intent = 'STRAIGHT:' + axis if axis else 'ELBOW:' + '+'.join(sorted(port_shape))
        case_hints[i] = {'shape': intent, 'name': case['label'] + str(i)}
    encoded = export.compile_objects(records, case_hints)
    for i, p in enumerate(encoded):
        expected = proof[i] if len(records) == 6 else cases[0]['objects'][i]
        assert max(abs(x-y) for key in ('Up', 'At') for x, y in zip(p[key], expected[key])) < 1e-5, case['label']

# The uncorrected imports must no longer claim all seven diagnostic elbows work.
for case, expected_elbows in zip(cases, (1, 0, 0, 0)):
    native, _ = export.native_contacts({i: export.frame(p) for i,p in enumerate(case['objects'])})
    elbows = 0
    for ports in native.values():
        if len(ports) == 2:
            a, b = sorted(ports)
            elbows += export.ARMS[a].dot(export.ARMS[b]) == 0
    assert elbows == expected_elbows, (case['label'], native)

# An unfinished elbow remains a visible warning, but users can export to test it.
assert export.plan_objects(objects[:1], {0: hints[0]})[1]
assert len(export.compile_objects(objects[:1], {0: hints[0]})) == 1

# Exercise the real Builder export, project JSON, and grouped cache paths.
bpy.context.scene.nms_main.new_file()
bpy.context.scene.bbe_detailed_proxies = False
parts = []
for i, record in enumerate(objects):
    part = module('part').Part.deserialise_from_data(record, addon.BUILDER, build_rigs=False)
    part.object['bbe_bubble_shape'] = hints[i]['shape']
    parts.append(part.object)
bpy.context.view_layer.update()
preview.refresh(bpy.context.scene)
transforms = [obj.matrix_world.copy() for obj in parts]
intents = [obj['bbe_bubble_shape'] for obj in parts]
payload = addon.BUILDER.serialise()['Objects']
assert len(payload) == 6
for p, expected in zip(payload, actual):
    assert max(abs(a-b) for key in ('Position', 'Up', 'At') for a,b in zip(p[key], expected[key])) < 1e-5
assert all(obj.matrix_world == matrix for obj, matrix in zip(parts, transforms))
assert [obj['bbe_bubble_shape'] for obj in parts] == intents
project = addon.BUILDER.serialise(get_presets=True)['Objects']
assert [p['bbe_bubble_shape'] for p in project] == intents
assert all('bbe_bubble_shape' not in p for p in payload)
grouped = module('group').Group.group_objects(parts)
assert grouped is not None
group_payload = addon.BUILDER.serialise()['Objects']
assert len(group_payload) == 6
for p, expected in zip(group_payload, payload):
    assert max(abs(a-b) for key in ('Position', 'Up', 'At') for a,b in zip(p[key], expected[key])) < 1e-5
restored = module('group').Group.ungroup_objects(addon.BUILDER, grouped)
assert [obj['bbe_bubble_shape'] for obj in restored] == intents
print('BUBBLE_EXPORT_FRAMES_PASS', bpy.app.version_string, flush=True)
