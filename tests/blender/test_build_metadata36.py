"""Owner editor and every export writer on disposable builds/saves only."""
from pathlib import Path
from types import SimpleNamespace as NS
from unittest.mock import patch
import copy
import json
import sys
import tempfile
import bpy

sys.path.insert(0, str(Path(__file__).parent))
from test_support import module, addon, QA, report
sys.path.insert(0, str(Path(__file__).parents[1]))
from test_ship_link_resilience import fixture, TEMPLATE

metadata = module('build_metadata')
ui = module('build_metadata_ui')
interchange = module('interchange')
core = module('save_editor.ship_core')
repair = module('save_editor.ship_repair')
files = module('save_editor.ship_files')
utils = module('save_editor.save_editor_utils')
optimizer = module('save_editor.optimizer_export')
actions = module('save_editor.corvette_actions')
props = bpy.context.scene.nms_base_tool
source = copy.deepcopy(TEMPLATE['base'])
source.update(Name='Authored build', LastEditedById=678, Owner={'UID': 123456, 'USN': 'Old author', 'LID': '',
    'PTK': 'ST', 'TS': '001234', 'Future': {'nested': [1, None]}}, Extra={'untouched': True})
source['BaseType']['FutureTypeInfo'] = {'keep': 42}
props.new_file()
props.deserialise_from_data(source)
assert props.serialise()['Owner'] == source['Owner']
assert props.serialise()['Extra'] == source['Extra']
assert props.serialise()['LastEditedById'] == 678
assert metadata.save_owner(props) is None

# Invoke only loads operator-local fields. Closing/cancelling cannot change the scene.
op = NS(report=lambda *args: None)
context = NS(scene=bpy.context.scene, window_manager=NS(invoke_props_dialog=lambda *a, **kw: {'RUNNING_MODAL'}))
before = props.serialise()
assert ui.BBE_OT_build_metadata.invoke(op, context, None) == {'RUNNING_MODAL'}
op.owner_usn = 'New author'
assert props.serialise() == before
assert ui.BBE_OT_build_metadata.execute(op, context) == {'FINISHED'}
expected_owner = dict(source['Owner'], USN='New author')
assert props.serialise()['Owner'] == expected_owner
assert metadata.save_owner(props) is None
assert props.serialise()['Extra'] == source['Extra']
assert props.serialise()['LastEditedById'] == 678

# Deliberate save opt-in is separate; stale dialogs and unreviewed owner edits fail.
op = NS(report=lambda *args: None)
ui.BBE_OT_build_metadata.invoke(op, context, None)
op.owner_to_save = True
assert ui.BBE_OT_build_metadata.execute(op, context) == {'FINISHED'}
assert metadata.save_owner(props) == expected_owner
props.string_usn = 'Changed later'
try:
    metadata.save_owner(props)
except ValueError:
    pass
else:
    raise AssertionError('Unreviewed ownership was exported')
props.string_usn = 'New author'
ui.BBE_OT_build_metadata.invoke(op, context, None)
props.string_base = 'Another build'
assert ui.BBE_OT_build_metadata.execute(op, context) == {'CANCELLED'}
props.deserialise_from_data(source)
assert not props.metadata_owner_to_save
assert props.bl_rna.properties['metadata_owner_to_save'].is_skip_save

# Native .nmsship entries stay byte-identical; BBE-only metadata uses a versioned sidecar.
package = module('save_editor.ship_package').new_corvette_source()
packed = interchange.BuildFile.from_bytes(package.ship_bytes(package.objects, metadata=props.serialise()), '.nmsship')
for name in package.entries:
    assert packed.entries[name] == package.entries[name]
assert packed.document['Owner'] == source['Owner']
assert packed.document['Extra'] == source['Extra']
assert packed.document['BaseType'] == source['BaseType']
for suffix in ('.json', '.nmsbase', '.txt'):
    payload = props.serialise(); payload['Objects'] = source['Objects']
    assert interchange.BuildFile.from_bytes(interchange._encode(payload), suffix).document['Owner'] == source['Owner']
assert metadata.PACKAGE_ENTRY not in package.entries

# Native/obfuscated key paths preserve unknown destination fields and fleet records.
owner = {'USN': 'Test author', 'UID': 'test-id', 'TS': 123, 'Future': {'retained': 1}}
routes = []
with tempfile.TemporaryDirectory(dir=QA / 'tmp') as temp:
    temp = Path(temp)
    with patch.object(files.backup_policy, 'settings', return_value=(str(temp / 'backups'), 100)):
        for route in ('standard', 'optimized', 'reviewed', 'reviewed_optimized'):
            for enabled in (False, True):
                root = fixture()
                root['ActiveContext'] = 'Main'
                player = core.player(root, 'Main')
                player['CharacterCustomisationData'] = [copy.deepcopy(TEMPLATE['custom']) for _ in range(23)]
                base = player['PersistentPlayerBases'][0]
                base['Owner'] = {'UID': 'destination', 'USN': 'Keep me', 'DestinationOnly': 9}
                base['Extra'] = {'keep': True}
                player['ShipOwnership'][0]['Name'] = base['Name']
                baseline = copy.deepcopy(root)
                root = core.translate(root, False)
                paths = [temp / 'save9.hg', temp / 'save10.hg']
                for path in paths:
                    save = files.SaveFile(path); save.json_data = copy.deepcopy(root); save.save()
                save = files.SaveFile(paths[0]); save.load()
                ident = utils.BaseData(0, save.get_bases_list_pointer()[0], save.get_ship_ownership_pointer())
                ident.save_context = 'Main'
                overrides = owner if enabled else None
                objects = copy.deepcopy(source['Objects'])
                objects[0]['Position'] = [9, 8, 7]
                if route == 'standard':
                    utils.save_base_to_save_file(objects, ident, paths, owner_override=overrides)
                elif route == 'optimized':
                    optimizer.export(objects, ident, paths, owner_override=overrides)
                else:
                    payload, _ = repair.rebuild_payload(root, 'Main', 0, 0, objects=objects)
                    # Exercise the actual reviewed operator's payload wiring
                    # for regular and optimized exports, then its real plan.
                    submitted = []
                    op = NS(check=lambda ctx: None, _error='', confirm=True, _resets=[],
                        confirm_resets=False, _s={'root': root}, context_name='Main', _index=0,
                        _payload=payload, _anchor=0, confirm_duplicates=False, _signature='reviewed',
                        optimized=route == 'reviewed_optimized', cancel=lambda ctx: None,
                        report=lambda *args: None)
                    with patch.object(actions, 'check_snapshot'), patch.object(metadata, 'save_owner', return_value=overrides), \
                            patch.object(actions, 'submit', side_effect=lambda s, *args: submitted.append(s['plan'])):
                        assert actions.BBE_OT_corvette_export.execute(op, bpy.context) == {'FINISHED'}
                    plan, = submitted
                    assert plan['payload']['owner_override'] == overrides
                    draft = repair.apply_plan(root, plan)
                    repair.validate_reviewed_draft(root, draft, [plan])
                    files.commit(draft, paths, files.export_hashes(paths))
                for path in paths:
                    after = core.translate(files.SaveFile(path).load())
                    p = core.player(after, 'Main')
                    actual = p['PersistentPlayerBases'][0]
                    expected = dict(base['Owner'], **owner) if enabled else base['Owner']
                    assert actual['Owner'] == expected, (route, enabled, actual['Owner'])
                    assert actual['Extra'] == base['Extra']
                    assert actual['Objects'] == objects
                    assert p['ShipOwnership'] == baseline['BaseContext']['PlayerStateData']['ShipOwnership']
                routes.append((route, enabled))

# The actual dialog and name helper include every control and the adjacent icon.
class Layout:
    def __init__(self): self.fields = []; self.operators = []; self.labels = []
    def row(self, **kw): return self
    def column(self, **kw): return self
    def box(self): return self
    def label(self, **kw): self.labels.append(kw.get('text'))
    def prop(self, _owner, field, **kw): self.fields.append(field)
    def operator(self, name, **kw): self.operators.append((name, kw)); return NS()
    def separator(self): pass
layout = Layout()
ui.BBE_OT_build_metadata.draw(NS(layout=layout), context)
metadata.draw_name(layout, props, text='Ship Name')
assert set(['owner_'+key.lower() for key in metadata.OWNER_FIELDS] + ['owner_to_save', 'string_base']) <= set(layout.fields)
assert layout.operators[0][0] == 'bbe.build_metadata'
assert layout.operators[0][1]['icon'] == 'PREFERENCES'
assert bpy.ops.bbe.build_metadata.get_rna_type()

# Saved RNA values can survive SKIP_SAVE in PropertyGroups. A real load must
# revoke approval while retaining the build metadata in both scene records.
with tempfile.TemporaryDirectory(dir=QA / 'tmp') as temp:
    props.metadata_owner_to_save = True
    props.metadata_owner_reviewed = metadata.encode(props.serialise()['Owner'])
    second = bpy.data.scenes.new('Another authors build')
    second.nms_base_tool.deserialise_from_data(source)
    second.nms_base_tool.metadata_owner_to_save = True
    second.nms_base_tool.metadata_owner_reviewed = metadata.encode(source['Owner'])
    path = str(Path(temp) / 'owner-approval.blend')
    bpy.ops.wm.save_as_mainfile(filepath=path)
    bpy.ops.wm.open_mainfile(filepath=path)
    for scene in bpy.data.scenes:
        assert not scene.nms_base_tool.metadata_owner_to_save
        assert scene.nms_base_tool.metadata_owner_reviewed == ''
        assert metadata.save_owner(scene.nms_base_tool) is None
        assert scene.nms_base_tool.serialise()['Owner'] == source['Owner']
report('build_metadata36', dict(unknown_fields_and_types_preserved=True, cancel_no_changes=True,
    stale_review_rejected=True, file_and_package_roundtrip=True, save_routes=routes,
    default_owner_preserved=True, fleet_ownership_unchanged=True, dialog_controls=True,
    actual_blend_reload_revokes_all_scene_approvals=True))
