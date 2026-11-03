"""A completed fixed elbow must not offer hidden native sockets as snap targets."""
import json
import sys
from pathlib import Path

import bpy
from mathutils import Matrix, Vector

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_support import addon, module

payload = Path(r'C:\Users\kengo\OneDrive\Desktop\NMS\kuma_station_builder\qa\bubble_corners_20261018\Native-Bubble-Elbow-Test.nmsbase')
module('builder_v2').deserialise_from_data(json.loads(payload.read_text()))
parts = [o for o in bpy.context.scene.objects if o.get('ObjectID') == 'BASE_BUBPIPE']
target = next(o for o in parts if str(o.data.get('bbe_native_bubble_preview')).startswith('ELBOW:'))
source = module('builder_v2').add_part('BASE_BUBPIPE', builder_object=addon.BUILDER)
source.matrix_world = target.matrix_world @ Matrix.Translation((2.2, 0, 0))
before = source.object.matrix_world.copy()
assert not source.snap_to(addon.BUILDER.get_builder_object_from_bpy_object(target))
assert all(abs(source.object.matrix_world[i][j] - before[i][j]) < 1e-5
           for i in range(4) for j in range(4))
assert source.object.get('ObjectID') == 'BASE_BUBPIPE'
assert len(addon.BUILDER.serialise()['Objects']) == 4
print('NATIVE_BUBBLE_SNAP_PASS', bpy.app.version_string, flush=True)
