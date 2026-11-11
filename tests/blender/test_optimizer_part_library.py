"""The optimizer searches the full catalogue and uses exact variant IDs on export."""
import json
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_support import bpy, D, module

opt = module('save_editor.corvette_optimizer')
library = {pid:label for pid,label,_ in opt.part_library()}
catalog = module('utils.dictionary').get_parts_definition()
forsaken = json.loads((D / 'resources/forsaken_assets.json').read_text())['assets']
assert set(library) == {row[0].lstrip('^') for row in catalog.values()}
assert {part['id'] for part in forsaken} <= set(library)
assert {pid for pid,label in library.items() if 'chelone' in label.casefold()} == {'B_GEN_6','B_GEN_6_1'}
assert library['B_GEN_5'] == 'Vile Proboscis Generator (B_GEN_5)'

defaults = opt.core.validate(opt.core.defaults())
groups = {g['name']:g['parts'] for g in defaults['groups']}
assert {'B_GEN_5', 'B_GEN_6_1'} <= set(groups['Generators'])
assert {'B_TUR_F', 'B_TUR_G'} <= set(groups['Weapon Turrets'])
assert {f'B_COK_C{i}' for i in range(1,10)} <= set(groups['Cockpit'])

state = bpy.context.window_manager.bbe_optimizer
opt.populate(state, defaults)
assert bpy.ops.bbe.optimizer_choose_part(part_id='B_TUR_F') == {'FINISHED'}
selected = state.groups[state.active_group]
assert selected.name == 'Weapon Turrets' and selected.parts[selected.active_part].part_id == 'B_TUR_F'
assert opt.read_state(state) == defaults

custom = dict(version=1, delete_identical=True, groups=[dict(name='My order', parts=['MOD_PART'])])
with TemporaryDirectory() as tmp, patch.object(opt,'settings_file',return_value=Path(tmp)/'settings.json'):
    opt.save_settings(custom)
    assert opt.load_settings() == custom
    opt.populate(state, opt.load_settings())
    for pid in ('B_HAB_D','S_WALL','B_TUR_G','B_GEN_6_1','B_TUR_F'):
        assert bpy.ops.bbe.optimizer_choose_part(part_id=pid) == {'FINISHED'}
        assert state.groups[0].parts[-1].part_id == pid
    assert bpy.ops.bbe.optimizer_edit(action='ADD_PART',value='^FUTURE_PART') == {'FINISHED'}
    opt.save_settings(opt.read_state(state))
    order = opt.load_settings()['groups'][0]['parts']
    records = [{'ObjectID':'^'+pid,'UserData':13} for pid in reversed(order)]
    ordered, counts = opt.core.optimize(records,opt.load_settings())
    assert [r['ObjectID'][1:] for r in ordered] == order
    assert counts['removed'] == 0 and all(r['UserData']==13 for r in ordered)
print('OPTIMIZER LIBRARY PASS',bpy.app.version_string,len(library),len(forsaken), flush=True)
