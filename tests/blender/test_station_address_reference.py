"""Station imports resolve a galactic address or retain the manual reference."""
import itertools
import json
from pathlib import Path
import sys

import bpy

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_support import QA, module, ref

address = module('save_editor.station_address')
ctx = bpy.context
seed = 290271126228013
assert all(address.read_address(value) == seed for value in (seed, str(seed), hex(seed), seed + (3 << 52)))
assert all(address.read_address(value) is None for value in (None, '', 0, '0x0', 'unknown', True, -1))
choices = address.descriptors(seed)
assert {'_TYPE_TET', '_TUBE_SQUARE'} <= choices
for actual, expected in zip(address.hull_colours(seed), ((.084608, .079322, .067437), (.677479,) * 3)):
    assert max(abs(x-y) for x, y in zip(actual, expected)) < 1e-5

fixture = {'BaseType': {'PersistentBaseTypes': 'PlayerSpaceStationBase'}, 'GalacticAddress': str(seed),
           'Objects': [{'ObjectID': '^BUILDFLATPANEL', 'UserData': 0, 'Timestamp': 0, 'Position': [1, 2, 3], 'Up': [0, 1, 0], 'At': [0, 0, 1]}]}


def reference():
    roots = [c for c in ctx.scene.collection.children if c.get(ref.TAG)]
    assert len(roots) == 1
    return roots[0]


def check_surfaces(meshes):
    materials = set()
    for mesh in meshes:
        assert mesh.uv_layers.active and mesh.materials, mesh.name
        materials.update(mesh.materials)
    assert all(m and m.get('bbe_station_surface') for m in materials)
    textures = [node.image for m in materials for node in m.node_tree.nodes if node.type == 'TEX_IMAGE']
    assert textures and all(im and im.packed_file for im in textures)


def check_address():
    root = reference()
    assert root['appearance_source'] == 'GalacticAddress'
    assert all(o.hide_select and o.get('station_reference_only') and 'ObjectID' not in o for o in root.all_objects)
    outside = next(c for c in root.children if c.name == 'Outside')
    assert len(outside.objects) > 0
    check_surfaces({o.data for o in outside.objects})
    check_surfaces({o.data for o in root.all_objects if o.name not in outside.objects})


# Include each native hull and corridor at least once.
seen = set()
for candidate in range(1, 1025):
    selected = address.descriptors(candidate)
    labels = selected & {entry[0].upper() for entry in itertools.chain(ref.FAMILIES, ref.CORRIDORS)}
    if labels - seen:
        ref.imported_station(ctx, dict(fixture, GalacticAddress=candidate), [])
        check_address()
        seen.update(labels)
    if len(seen) == 9:
        break
assert len(seen) == 9, seen

path = QA / 'station-address.nmsbase'
path.write_text(json.dumps(fixture))
main = ctx.scene.nms_main
main.import_build_file(str(path))
check_address()
assert ctx.scene.nms_save_data.station_status == 'Tet hull · Square launch tube'
assert bpy.ops.object.nms_switch_station_reference(manual=True) == {'FINISHED'}
assert len(reference().all_objects) == 86
manual = reference()
check_surfaces({o.data for o in manual.all_objects if o.type == 'MESH'})
check_surfaces({child.data for o in manual.all_objects if o.instance_collection
                for child in o.instance_collection.objects if child.type == 'MESH'})
assert bpy.ops.object.nms_switch_station_reference() == {'FINISHED'}
check_address()
output = QA / 'station-address-roundtrip.nmsbase'
main.export_base_file(str(output))
saved = json.loads(output.read_bytes())
assert str(saved['GalacticAddress']) == str(seed)
assert [o['ObjectID'] for o in saved['Objects']] == ['^BUILDFLATPANEL']
for key in ('Position', 'Up', 'At'):
    assert max(abs(x-y) for x, y in zip(saved['Objects'][0][key], fixture['Objects'][0][key])) < .00001
main.import_nms_data(json.dumps(dict(fixture, GalacticAddress='')))
assert len(reference().all_objects) == 86
assert all(not m.get('station_reference_palette') for m in bpy.data.materials)
main.import_nms_data(json.dumps(dict(fixture, BaseType={'PersistentBaseTypes': 'HomePlanetBase'})))
assert not any(c.get(ref.TAG) for c in ctx.scene.collection.children)
assert not any(m.get('bbe_station_surface') or m.get('bbe_station_slot') for m in bpy.data.materials)
assert not any(image.get('bbe_station_image') for image in bpy.data.images)
print('STATION ADDRESS PASS')
