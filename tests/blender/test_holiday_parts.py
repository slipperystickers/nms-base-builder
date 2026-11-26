"""Exercise catalogue placement, paint, saved IDs and native Corvette snaps."""
import json
from collections import Counter
from pathlib import Path
import sys

import bpy

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_support import D, addon, module

builder = module('builder_v2')
materials = module('utils.materials_v2')
paint = module('utils.material')
snaps = module('corvette_snapping')
parts = json.loads((D / 'resources/holiday_assets.json').read_text())['assets']
definitions = module('asset_browser.utils.parts_definition').ROWS
catalogue = module('asset_strip').catalogue(bpy.context)
scene = bpy.context.scene
bpy.data.batch_remove(list(scene.objects))
addon.BUILDER.clear_caches()
placed = {}

for detailed in (False, True):
    scene.bbe_detailed_proxies = detailed
    for pid, entry in parts.items():
        row = definitions['^' + pid]
        group = catalogue[row[2]][row[4]]
        assert pid in group or any(pid in part.get('variants', {}) for part in group.values()), pid
        obj = builder.add_part(pid, user_data=0).object
        placed[pid] = obj
        assert obj['ObjectID'] == pid and obj.data.uv_layers.active, pid
        assert materials.is_high_res(obj) == detailed, (pid, obj.data.name)
        assert bool(obj.data.get('bbe_textured_simple')) != detailed, pid
        images = builder._mesh_texture_images(obj.data)
        assert images and all(image.packed_file for image in images), pid
        if pid.startswith('SWARM_TROPHY'):
            red, green = obj.color[:2]
            assert (red > green) == pid.endswith('_R'), pid
        paint.restore_material(obj, 1)
        assert set(builder._mesh_texture_images(obj.data)) == set(images), pid
        if entry['nativeSnapPoints']:
            assert len(snaps.DATA[pid]) == entry['nativeSnapPoints'], pid

records = addon.BUILDER.serialise()['Objects']
assert Counter(r['ObjectID'] for r in records) == Counter({'^' + pid: 2 for pid in parts})
hab = builder.add_part('B_HAB_A').object
for pid in ('B_LND_D', 'B_TRU_I', 'B_WNG_O_0', 'B_WNG_O_0_R'):
    obj = placed[pid]
    assert snaps.snap(obj, hab) and obj['snapped_to'] == hab.name, pid
print('Holiday placement, paint, export and snapping passed:', len(parts), 'parts')
