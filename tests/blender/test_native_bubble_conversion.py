"""Safe legacy elbow conversion succeeds only for matching native topology."""
import json
import sys
from pathlib import Path

import bpy
from mathutils import Matrix

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_support import addon, module
from no_mans_sky_base_builder import bubble_preview

payload = Path(r'C:\Users\kengo\OneDrive\Desktop\NMS\kuma_station_builder\qa\bubble_corners_20261018\Native-Bubble-Elbow-Test.nmsbase')
module('builder_v2').deserialise_from_data(json.loads(payload.read_text()))
native = next(obj for obj in bpy.context.scene.objects
              if str(obj.data.get('bbe_native_bubble_preview')).startswith('ELBOW:'))
old_matrix = native.matrix_world.copy()
_, _, visual_transform = bubble_preview._display_spec({'Back', 'Bot'}, True)
legacy = module('builder_v2').add_part('BASE_BUBPIPE_L', builder_object=addon.BUILDER).object
legacy.matrix_world = old_matrix @ visual_transform
legacy_visual_matrix = legacy.matrix_world.copy()
bpy.data.objects.remove(native, do_unlink=True)
count = bubble_preview.convert_legacy_corners(bpy.context.scene)
assert count == 1
assert legacy.get('ObjectID') == 'BASE_BUBPIPE'
assert str(legacy.data.get('bbe_native_bubble_preview')) == 'ELBOW:Bot+Front'
for after, before in zip(legacy.matrix_world @ Matrix.Translation((0, 1, 0)),
                         legacy_visual_matrix):
    assert all(abs(a - b) < 1e-4 for a, b in zip(after, before))
assert str(legacy.data.get('bbe_native_bubble_preview')).startswith('ELBOW:')
assert all(item['ObjectID'] == '^BASE_BUBPIPE' for item in addon.BUILDER.serialise()['Objects'])
print('NATIVE_BUBBLE_CONVERSION_PASS', bpy.app.version_string, flush=True)
