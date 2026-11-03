"""A native curved placement has a fixed visual shape and export check."""
import sys
from pathlib import Path
import bpy

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_support import addon
from no_mans_sky_base_builder import bubble_preview

curve = bubble_preview.add_native_bend_point(addon.BUILDER, cursor=(0, 0, 0))
assert len([obj for obj in bpy.context.scene.objects if obj.get('ObjectID')]) == 1
assert curve.object.get('bbe_bubble_shape') == 'ELBOW:Bot+Front'
assert str(curve.object.data.get('bbe_native_bubble_preview')).startswith('ELBOW:')
for expected_count in (2, 3):
    straight = addon.BUILDER.add_part('BASE_BUBPIPE')
    straight.object['bbe_bubble_shape'] = 'STRAIGHT:Y'
    assert bubble_preview.snap_native(straight.object, curve.object)
    assert len([obj for obj in bpy.context.scene.objects if obj.get('ObjectID')]) == expected_count
    assert str(curve.object.data.get('bbe_native_bubble_preview')).startswith('ELBOW:')

assert all(item['ObjectID'] == '^BASE_BUBPIPE' for item in addon.BUILDER.serialise()['Objects'])
print('NATIVE_BUBBLE_BROWSER_PASS', bpy.app.version_string, flush=True)
