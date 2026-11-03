"""Loaded native elbow keeps its visible shape when moved."""
import json
import os
import sys
from pathlib import Path

import bpy

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_support import addon, module

payload = Path(r'C:\Users\kengo\OneDrive\Desktop\NMS\kuma_station_builder\qa\bubble_corners_20261018\Native-Bubble-Elbow-Test.nmsbase')
data = json.loads(payload.read_text())
if os.environ.get('NMS_BUBBLE_LOW_RES') == '1':
    bpy.context.scene.bbe_detailed_proxies = False
module('builder_v2').deserialise_from_data(data)
parts = sorted((obj for obj in bpy.context.scene.objects
                if obj.get('ObjectID') == 'BASE_BUBPIPE'),
               key=lambda obj: obj.get('Order', 0))
assert len(parts) == 3, len(parts)
from no_mans_sky_base_builder import bubble_preview

keys = [obj.data.get('bbe_native_bubble_preview') for obj in parts]
print('NATIVE_PREVIEW_KEYS', keys, flush=True)
assert any(str(key).startswith('ELBOW:Back+Bot') for key in keys), keys
assert any(str(key).startswith('STRAIGHT:Z') for key in keys), keys
assert all(obj.get('ObjectID') == 'BASE_BUBPIPE' for obj in parts)
assert [item['ObjectID'] for item in addon.BUILDER.serialise()['Objects']] == [
    '^BASE_BUBPIPE', '^BASE_BUBPIPE', '^BASE_BUBPIPE']
before = [obj.data.as_pointer() for obj in parts]
assert bubble_preview.refresh(bpy.context.scene) == 0
assert [obj.data.as_pointer() for obj in parts] == before
elbow = next(obj for obj in parts if str(obj.data.get('bbe_native_bubble_preview')).startswith('ELBOW:Back+Bot'))
elbow.location.x += 4
bpy.context.view_layer.update()
bubble_preview.refresh(bpy.context.scene)
assert str(elbow.data.get('bbe_native_bubble_preview')).startswith('ELBOW:Back+Bot')
try:
    addon.BUILDER.serialise()
except ValueError as error:
    assert 'both visible ends' in str(error)
else:
    raise AssertionError('Moved elbow must not export as a different game shape')
elbow.location.x -= 4
bpy.context.view_layer.update()
bubble_preview.refresh(bpy.context.scene)
assert str(elbow.data.get('bbe_native_bubble_preview')).startswith('ELBOW:Back+Bot')
assert len(addon.BUILDER.serialise()['Objects']) == 3
print('NATIVE_BUBBLE_PREVIEW_PASS', bpy.app.version_string, flush=True)
