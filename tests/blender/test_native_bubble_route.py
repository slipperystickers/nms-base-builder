import json
import os
import sys
from collections import Counter
from pathlib import Path

import bpy

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_support import addon, module

qa = Path(r'C:\Users\kengo\OneDrive\Desktop\NMS\kuma_station_builder\qa\bubble_corners_20261018')
data = json.loads((qa / 'Native-Bubble-Route-Diagnostic.nmsbase').read_text())
if os.environ.get('NMS_BUBBLE_LOW_RES') == '1':
    bpy.context.scene.bbe_detailed_proxies = False
module('builder_v2').deserialise_from_data(data)
parts = [obj for obj in bpy.context.scene.objects if obj.get('ObjectID') == 'BASE_BUBPIPE']
keys = Counter(str(obj.data.get('bbe_native_bubble_preview', 'STRAIGHT:Y')).split(':')[0]
               for obj in parts)
print('NATIVE_ROUTE_PREVIEW', dict(keys), flush=True)
assert len(parts) == 9
assert keys['TEE'] == 1
assert keys['ELBOW'] == 3
assert keys['STRAIGHT'] == 5
assert len(addon.BUILDER.serialise()['Objects']) == 9
print('NATIVE_BUBBLE_ROUTE_PASS', bpy.app.version_string, flush=True)
