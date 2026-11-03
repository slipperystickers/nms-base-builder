"""Run with --factory-startup --disable-autoexec -b CreepyCrawly.blend."""
import hashlib
import json
import math
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

import bpy
import numpy as np
from mathutils import Matrix

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_support import addon, module, QA, report

compat = module('forge_compat')
group = module('group').Group
repair = module('save_editor.ship_repair')
scene = bpy.context.scene
source = Path(bpy.data.filepath)
before_hash = hashlib.sha256(source.read_bytes()).hexdigest()
obj = bpy.data.objects['Abdomen']
original_cache = obj['child_cache']
original_objects = set(bpy.data.objects.keys())
assert original_cache == '{}'
assert len(obj.data.vertices) == 290
assert not hasattr(obj, 'charon_forged'), 'Test requires Forge disabled'

with patch.object(compat, 'export_cache', return_value=None):
    baseline = scene.nms_main.serialise(objects_only=True)
records = group.serialise(obj)
assert len(records) == 290
assert {r['ObjectID'] for r in records} == {'^C_WALL'}
assert {r['UserData'] for r in records} == {1}

# Independent quaternion rotation formula verifies every exported world frame.
def verify_world(records):
    convert = np.array(((1, 0, 0, 0), (0, 0, 1, 0), (0, -1, 0, 0), (0, 0, 0, 1)))
    for index, record in enumerate(records):
        q = np.array(obj.data.attributes['charon_rotation'].data[index].value)
        w, x, y, z = q / np.linalg.norm(q)
        rotation = np.array(((1-2*(y*y+z*z), 2*(x*y-z*w), 2*(x*z+y*w)),
                             (2*(x*y+z*w), 1-2*(x*x+z*z), 2*(y*z-x*w)),
                             (2*(x*z-y*w), 2*(y*z+x*w), 1-2*(x*x+y*y))))
        local = np.eye(4)
        local[:3, :3] = rotation * obj.data.attributes['charon_scale'].data[index].value
        local[:3, 3] = obj.data.vertices[index].co
        expected = convert @ np.array(obj.matrix_world) @ local
        for key, column in (('Position', 3), ('Up', 1), ('At', 2)):
            assert np.allclose(record[key], expected[:3, column], atol=2e-5), (index, key)
verify_world(records)

all_records = scene.nms_main.serialise(objects_only=True)
assert len(all_records) == len(baseline) + 290
repair.validate_parts(all_records)
# Existing individual parts and cached groups must retain their exact records.
def stable(records):
    return sorted(json.dumps({k: v for k, v in r.items() if k != 'Timestamp'}, sort_keys=True)
                  for r in records)
remaining = stable(all_records)
for record in stable(records):
    remaining.remove(record)
assert remaining == stable(baseline)

# Pose changes use current parenting, never the original saved origin/cache.
parent = obj.parent
old = parent.matrix_world.copy()
parent.matrix_world = Matrix.Translation((7, -3, 2)) @ Matrix.Rotation(.37, 4, 'Z') @ old
bpy.context.view_layer.update()
verify_world(group.serialise(obj))
parent.matrix_world = old
bpy.context.view_layer.update()

# Even a stale nonempty cache cannot override the live generated placements.
obj['child_cache'] = json.dumps({'stale': {'ObjectID': 'BUILDWALL', 'matrix_local': [list(r) for r in Matrix.Identity(4)]}})
assert len(group.serialise(obj)) == 290
obj['child_cache'] = original_cache

# An incompatible procedural layout must not quietly lose the entire shape.
attribute = obj.data.attributes['charon_scale']
attribute.name = 'test_missing_scale'
try:
    group.serialise(obj)
except ValueError as exc:
    assert 'Abdomen' in str(exc) and 'placement attributes' in str(exc)
else:
    raise AssertionError('Unsupported procedural shape was silently skipped')
finally:
    attribute.name = 'charon_scale'

with tempfile.TemporaryDirectory(dir=QA) as temporary:
    target = Path(temporary) / 'CreepyCrawly.nmsship'
    assert bpy.ops.bbe.export_ship_file(filepath=str(target), use_selected_save=False) == {'FINISHED'}
    exported = module('interchange').BuildFile.read(target)
    assert stable(exported.objects) == stable(all_records)
    repair.validate_parts(exported.objects)

assert obj['child_cache'] == original_cache
assert obj.modifiers.get('Charon Forge Sphere')
assert set(bpy.data.objects.keys()) == original_objects
assert hashlib.sha256(source.read_bytes()).hexdigest() == before_hash
report('forge_shape_export', dict(blender=bpy.app.version_string, baseline=len(baseline),
       generated=len(records), total=len(all_records), source_unchanged=True))
print('FORGE_SHAPE_EXPORT_PASS', flush=True)
