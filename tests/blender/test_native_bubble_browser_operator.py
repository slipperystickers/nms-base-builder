"""A curved browser choice stays curved; each click adds one native part."""
import sys
from pathlib import Path
import bpy

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_support import addon

result = bpy.ops.object.nms_asset_browser_object_selected(object_id='BASE_BUBPIPE_L')
assert result == {'FINISHED'}, result
curve = bpy.context.active_object
assert curve.get('ObjectID') == 'BASE_BUBPIPE'
assert str(curve.data.get('bbe_native_bubble_preview')).startswith('ELBOW:')
assert len([obj for obj in bpy.context.scene.objects if obj.get('ObjectID')]) == 1
try:
    addon.BUILDER.serialise()
except ValueError as error:
    assert 'both visible ends' in str(error)
else:
    raise AssertionError('An isolated curved preview must not export as a straight')

for expected_count in (2, 3):
    bpy.ops.object.select_all(action='DESELECT')
    curve.select_set(True)
    bpy.context.view_layer.objects.active = curve
    result = bpy.ops.object.nms_asset_browser_object_selected(object_id='BASE_BUBPIPE')
    assert result == {'FINISHED'}, result
    parts = [obj for obj in bpy.context.scene.objects if obj.get('ObjectID')]
    assert len(parts) == expected_count
    assert str(curve.data.get('bbe_native_bubble_preview')).startswith('ELBOW:')
    assert all(obj.get('ObjectID') == 'BASE_BUBPIPE' for obj in parts)
    assert all(str(obj.get('bbe_bubble_shape')).startswith('STRAIGHT:')
               for obj in parts if obj != curve)

assert len(addon.BUILDER.serialise()['Objects']) == 3
print('NATIVE_BUBBLE_BROWSER_OPERATOR_PASS', bpy.app.version_string, flush=True)
