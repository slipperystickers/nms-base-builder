"""Deleting a placed prefab removes its locked members and preserves other instances."""
import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
from unittest.mock import patch

import bpy

sys.path.insert(0, str(Path(__file__).parent))
from test_support import addon, module

ctx = bpy.context
preset = module('preset').Preset
cables = module('cable_connections')
deletion = module('cable_delete')
area = next(a for a in ctx.screen.areas if a.type == 'VIEW_3D')
outliner = next(a for a in ctx.screen.areas if a.type == 'OUTLINER')


def place():
    assert bpy.ops.object.nms_asset_browser_object_selected(object_id='Tile Pair', is_preset=True) == {'FINISHED'}
    root = ctx.active_object
    assert root.get('PresetID') == 'Tile Pair'
    assert len(root.children) == 2 and all(o.hide_select for o in root.children)
    return root


def select(obj):
    for other in ctx.selected_objects:
        other.select_set(False)
    obj.select_set(True)
    ctx.view_layer.objects.active = obj


fixture = {'BaseVersion': 5, 'Prefab': [
    {'ObjectID': '^L_FLOOR_Q', 'Position': [x, 0, 0], 'Up': [0, 1, 0], 'At': [0, 0, 1],
     'UserData': 0, 'Timestamp': 1} for x in (0, 4)]}
with TemporaryDirectory() as folder, patch.object(preset, 'PRESET_PATH', folder):
    path = Path(folder) / 'Tile Pair.nmsprefab'
    path.write_text(json.dumps(fixture))
    ctx.scene.nms_main.new_file()
    other = place()
    keep = {other.name, *(o.name for o in other.children)}
    for source in ('BUILDER', 'VIEWPORT', 'OUTLINER'):
        root = place()
        doomed = {root.name, *(o.name for o in root.children)}
        if source == 'OUTLINER':
            select(other)  # The Outliner can target a different instance.
            with ctx.temp_override(area=outliner, selected_ids=[root]):
                assert bpy.ops.bbe.delete_with_cables('EXEC_DEFAULT') == {'FINISHED'}
        elif source == 'VIEWPORT':
            with ctx.temp_override(area=area):
                assert bpy.ops.bbe.delete_with_cables('INVOKE_DEFAULT') == {'FINISHED'}
        else:
            assert bpy.ops.object.nms_delete() == {'FINISHED'}
        assert not doomed.intersection(ctx.scene.objects.keys()), (source, doomed.intersection(ctx.scene.objects.keys()))
        assert keep <= set(ctx.scene.objects.keys())
        assert json.loads(path.read_text()) == fixture

    for clean in (False, True):
        root = place()
        tile = root.children[0]
        socket = next(iter(cables.local_sockets(tile, cables.POWER)))
        wire = cables.connect(tile, socket, None, '', cables.POWER, addon.BUILDER, free_end=(12, 3, 0))
        network = {wire.name, *(obj.name for obj in cables.endpoints(wire))}
        select(root)
        assert deletion.make_plan(ctx, 'BUILDER').attached == {wire}
        assert bpy.ops.object.nms_delete(remove_cabling=clean) == {'FINISHED'}
        if clean:
            assert not network.intersection(ctx.scene.objects.keys())
        else:
            assert network <= set(ctx.scene.objects.keys())
            assert cables.free_control(cables.endpoints(wire)[0])
    assert keep <= set(ctx.scene.objects.keys())
print('PREFAB INSTANCE DELETE PASS', flush=True)
