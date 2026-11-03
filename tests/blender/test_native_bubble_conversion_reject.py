"""The reporter's touching elbows must be rejected without altering the build."""
import sys
from pathlib import Path

import bpy

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_support import addon
from no_mans_sky_base_builder import bubble_preview

qa = Path(r'C:\Users\kengo\OneDrive\Desktop\NMS\kuma_station_builder\qa\bubble_corners_20261018')
bpy.ops.wm.open_mainfile(filepath=str(qa / 'testtttt-inspection.blend'))
corners = [obj for obj in bpy.context.scene.objects
           if obj.get('ObjectID') == 'BASE_BUBPIPE_L']
before = [(obj.name, obj.matrix_world.copy(), obj.data, obj.get('ObjectID'))
          for obj in corners]
assert len(before) == 4
try:
    bubble_preview.convert_legacy_corners(bpy.context.scene)
except ValueError as exc:
    print('EXPECTED_BUBBLE_CONVERSION_REJECTION', str(exc), flush=True)
else:
    raise AssertionError('The touching bends were converted unsafely')
for name, matrix, mesh, object_id in before:
    obj = bpy.context.scene.objects[name]
    assert obj.get('ObjectID') == object_id
    assert obj.data == mesh
    assert all(abs(a - b) < 1e-6 for row_a, row_b in zip(obj.matrix_world, matrix)
               for a, b in zip(row_a, row_b))
print('NATIVE_BUBBLE_CONVERSION_ROLLBACK_PASS', bpy.app.version_string, flush=True)
