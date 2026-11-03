"""Ownership copying and complete package round trips; disposable saves only."""
import copy
import io
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace as NS
from unittest.mock import patch
import zipfile
import bpy
sys.path.insert(0, str(Path(__file__).parent))
from test_support import module, addon, QA, report
sys.path.insert(0, str(Path(__file__).parents[1]))
from test_ship_link_resilience import fixture, TEMPLATE

meta = module('build_metadata')
ui = module('build_metadata_ui')
core = module('save_editor.ship_core')
files = module('save_editor.ship_files')
packages = module('save_editor.ship_package')
repair = module('save_editor.ship_repair')
interchange = module('interchange')
props = bpy.context.scene.nms_base_tool
root = fixture()
root['ActiveContext'] = 'Main'
p = core.player(root, 'Main')
p['CharacterCustomisationData'] = [copy.deepcopy(TEMPLATE['custom']) for _ in range(23)]
p['ShipUsesLegacyColours'] = [True] + [False] * 11
owner = dict(USN='Example builder', UID='123456789', LID='local', PTK='ST', TS=12345, Extra={'keep': [1, None]})
base = p['PersistentPlayerBases'][0]
base.update(Owner=copy.deepcopy(owner), Position=[123.125, 456.5, -789.75], Forward=[.5, .25, .75],
            FutureBase={'huge': 18446744073709551615})
ship = p['ShipOwnership'][0]
ship.update(Position=[100.5, -20.25, 99.75, -1], Direction=[.25, .75, .5, -1], Location=7,
            FutureShip={'keep': [True, 18446744073709551615]})
ship['Inventory']['Slots'] = [dict(Index={'X': 3, 'Y': 2}, Id='^FUEL1', Amount=450,
    MaxAmount=9999, Type={'InventoryType': 'Product'}, Future='cargo')]
ship['Inventory_TechOnly']['Slots'][0]['Index'] = {'X': 4, 'Y': 2}
ship['Inventory']['ValidSlotIndices'].append({'X': 3, 'Y': 2})
ship['Inventory_TechOnly']['ValidSlotIndices'].append({'X': 4, 'Y': 2})
ship['Inventory_TechOnly']['SpecialSlots'] = [dict(Index={'X': 4, 'Y': 2}, Type={'InventorySpecialSlotType': 'TechBonus'})]
ship['Inventory_Cargo']['FutureCargo'] = [9, 8, 7]
before = copy.deepcopy(root)

with tempfile.TemporaryDirectory(dir=QA / 'tmp') as temp:
    temp = Path(temp)
    for raw in (False, True):
        source = packages.from_save(core.translate(root, False) if raw else root, 'Main', 0)
        assert json.loads(source.entries['so.json']) == ship
        assert source.document['Owner'] == owner
        assert source.document['Position'] == base['Position']
        assert source.document['Forward'] == base['Forward']
        props.new_file()
        props.deserialise_from_data(source.import_document())
        addon._store_build_source(bpy.context.scene, source, '.nmsship')
        # Actual .blend persistence then actual package exporter, with geometry
        # serialisation isolated so the test focuses on all non-object fields.
        blend = temp / 'retained.blend'
        bpy.ops.wm.save_as_mainfile(filepath=str(blend))
        bpy.ops.wm.open_mainfile(filepath=str(blend))
        props = bpy.context.scene.nms_base_tool
        restored = addon._restore_build_source(bpy.context.scene)
        assert restored.entries == source.entries
        out = temp / 'roundtrip.nmsship'
        fake = NS(serialise=lambda **kw: source.objects)
        addon.NMSMain._export_ship_file(fake, str(out), '', NS(update=lambda *a: None))
        result = interchange.BuildFile.read(out)
        for name in ('so.json', 'ccd.json', 'objects.json', meta.SHIP_STATE_ENTRY):
            assert result.entries[name] == source.entries[name], name
        assert meta.wrapper(result.document) == meta.wrapper(source.document)
        payload = repair.read_replacement(out, 'FULL')
        assert payload['legacy_colours'] is True
        assert payload['ship'] == ship
    assert root == before

    # Wrapped third-party objects.json with no BBE sidecar retains USN and pose.
    for key in ('Objects', 'objects', 'Prefab'):
        wrapped = dict(meta.wrapper(base), **{key: base['Objects']})
        stream = io.BytesIO()
        with zipfile.ZipFile(stream, 'w') as z:
            z.writestr('objects.json', interchange._encode(wrapped))
            z.writestr('so.json', interchange._encode(ship))
            z.writestr('ccd.json', source.entries['ccd.json'])
            z.writestr('extra/data.bin', b'preserve unknown bytes')
        wrapped_source = interchange.BuildFile.from_bytes(stream.getvalue(), '.nmsship')
        assert wrapped_source.document['Owner'] == owner
        changed = copy.deepcopy(wrapped_source.objects)
        changed[0]['Position'] = [11, 22, 33]
        result = interchange.BuildFile.from_bytes(wrapped_source.ship_bytes(changed), '.nmsship')
        assert result.objects == changed
        assert result.document['Position'] == base['Position']
        assert result.entries['extra/data.bin'] == b'preserve unknown bytes'
        edited = interchange.BuildFile.from_bytes(wrapped_source.ship_bytes(changed,
            metadata={'Owner': dict(owner, USN='Updated')}), '.nmsship')
        assert edited.document['Owner']['USN'] == 'Updated'
        assert json.loads(edited.entries['objects.json'])['Owner']['USN'] == 'Updated'

    # A JSON-only design with no owner must not replace selected-save metadata
    # with empty UI defaults. Explicit metadata edits still win.
    props.new_file()
    props.deserialise_from_data(dict(Name='Edited build', Objects=base['Objects']))
    merged = meta.export_package_metadata(props, source)
    assert merged['Owner'] == owner
    assert merged['Position'] == base['Position']
    assert merged['Name'] == 'Edited build'

    save_path = temp / 'save9.hg'
    sf = files.SaveFile(save_path); sf.json_data = core.translate(root, False); sf.save()
    snapshots = {str(save_path): save_path.read_bytes()}
    context = NS(scene=bpy.context.scene, window_manager=NS(invoke_props_dialog=lambda *a, **kw: {'RUNNING_MODAL'}))
    original = copy.deepcopy(TEMPLATE['base'])
    original['Owner'] = dict(owner, USN='Original', UID='original')
    props.deserialise_from_data(original)
    op = NS(report=lambda *a: None)
    ui.BBE_OT_build_metadata.invoke(op, context, None)
    op.copy_owner = True
    with patch.object(ui, 'selected_save_paths', return_value=[str(save_path)]):
        ui.toggle_copy(op, context)
        assert not op._donor_error
        assert props.serialise()['Owner'] == original['Owner']  # Cancel is harmless
        op.owner_donor = 'Main:0'
        ui.select_donor(op, context)
        assert op.owner_usn == owner['USN']
        assert ui.BBE_OT_build_metadata.execute(op, context) == {'FINISHED'}
    assert props.serialise()['Owner'] == owner
    assert not props.metadata_owner_to_save
    assert snapshots == {str(save_path): save_path.read_bytes()}
    # Source modification invalidates pending copy; no partial project changes.
    ui.BBE_OT_build_metadata.invoke(op, context, None)
    op.copy_owner = True
    with patch.object(ui, 'selected_save_paths', return_value=[str(save_path)]):
        ui.toggle_copy(op, context)
        op.owner_donor = 'Main:0'; ui.select_donor(op, context)
        staged = props.serialise()
        save_path.write_bytes(save_path.read_bytes() + b'changed')
        assert ui.BBE_OT_build_metadata.execute(op, context) == {'CANCELLED'}
        assert props.serialise() == staged

    duplicates = copy.deepcopy(root)
    core.player(duplicates, 'Main')['PersistentPlayerBases'].append(copy.deepcopy(base))
    assert not meta.ownership_sources(duplicates)
    blank = copy.deepcopy(root)
    core.player(blank, 'Main')['PersistentPlayerBases'][0]['Owner']['USN'] = ''
    assert meta.ownership_sources(blank)['Main:0'][1]['USN'] == ''
    assert meta.ownership_sources(core.translate(root, False)) == meta.ownership_sources(root)

report('ownership38', dict(full_ship_record=True, inventory_and_tech_positions=True,
    world_and_part_placement=True, legacy_colours=True, unknown_fields_and_entries=True,
    actual_blend_reload=True, wrapped_package_owner=True, source_owner_not_blank_overwritten=True,
    donor_cancel_safe=True, donor_copy=True, stale_donor_rejected=True,
    ambiguous_donors_excluded=True, live_save_writes=False))
