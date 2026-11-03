"""Native checklist registration and controls on in-memory fixtures only."""
import importlib
import copy
import os
import sys
import types
from pathlib import Path
import bpy

ADDON = Path(os.environ.get('NMS_KUMA_TEST_ADDON') or Path(__file__).resolve().parents[2] / 'src/addons/no_mans_sky_base_builder')
package = types.ModuleType('bbe_unlock_ui_test'); package.__path__ = [str(ADDON)]
sys.modules[package.__name__] = package
editor = types.ModuleType(package.__name__ + '.save_editor'); editor.__path__ = [str(ADDON / 'save_editor')]
sys.modules[editor.__name__] = editor
ui = importlib.import_module(editor.__name__ + '.buildable_unlocks_ui')
ui.register()
try:
    assert hasattr(bpy.types.WindowManager, 'bbe_buildable_unlocks')
    catalogue = dict(schema_version=1, items=[
        dict(id='WALL', name='Metal Wall', kind='Product', category='Construction', object_ids=['BUILDWALL'], unlock_field='KnownProducts'),
        dict(id='KNOWN', name='Already Learned', kind='Product', category='Construction', object_ids=['KNOWN'], unlock_field='KnownProducts'),
        dict(id='TECH', name='Warp Drive', kind='Technology', category='Technology', unlock_field='KnownTech'),
        dict(id='SPECIAL', name='Reward Statue', kind='AccountReward', category='Expedition', unlock_field='AccountWideSpecials', account_field='UnlockedSeasonRewards', account_id='SPECIAL'),
        dict(id='UNSUPPORTED', name='Inventory Part', kind='Product', category='Construction', unlock_field=None, scope_note='Requires inventory acquisition'),
    ])
    ui.SESSION = dict(roots={'save9.hg': {'BaseContext': {'PlayerStateData': {'KnownProducts': ['^KNOWN'], 'KnownTech': [],
                                'Units': 123456, 'Nanites': 42, 'Specials': 99}},
                                'ExpeditionContext': {'PlayerStateData': {'KnownProducts': [], 'KnownTech': [],
                                'Units': 11, 'Nanites': 22, 'Specials': 33}}}},
                      contexts=['Main', 'Season'], catalogue=catalogue,
                      account={'root': {'UserSettingsData': {'UnlockedSeasonRewards': []}}})
    ui.SESSION['roots']['save10.hg'] = copy.deepcopy(ui.SESSION['roots']['save9.hg'])
    ui.SESSION['roots']['save10.hg']['BaseContext']['PlayerStateData']['Units'] = -1
    ui.SESSION['latest_path'] = 'save10.hg'
    ui._CATEGORIES = [('ALL', 'All Categories', ''), ('Construction', 'Construction', ''), ('Technology', 'Technology', ''), ('Expedition', 'Expedition', '')]
    state = bpy.context.window_manager.bbe_buildable_unlocks
    state.save_context = 'Main'; state.category = 'ALL'
    ui._populate(bpy.context)
    balances = {row.name: row for row in state.currencies}
    assert set(balances) == {'Units', 'Nanites', 'Quicksilver'}
    assert all(row.supported and not row.selected for row in state.currencies)
    assert balances['Units'].mixed and balances['Units'].amount == '4,294,967,295'
    assert balances['Nanites'].amount == '42' and balances['Quicksilver'].amount == '99'
    assert ui._currency_selection(state) == {}, 'Opening must not select any balance changes'
    balances['Units'].selected = True
    assert ui._currency_selection(state) == {'Units': 4294967295}
    for invalid in ('-1', '1.5', '1e4', '1,23', '4,294,967,296'):
        balances['Units'].amount = invalid
        try: ui._currency_selection(state)
        except ValueError: pass
        else: raise AssertionError('Invalid UI amount accepted: '+invalid)
    balances['Units'].amount = '0'
    assert ui._currency_selection(state) == {'Units': 0}
    balances['Units'].selected = False
    balances['Nanites'].amount = 'unused draft text'
    assert ui._currency_selection(state) == {}, 'Unchecked draft fields must not be parsed or written'
    state.save_context = 'Season'
    assert {row.name:row.amount for row in state.currencies} == {'Units':'11','Nanites':'22','Quicksilver':'33'}
    assert not any(row.selected for row in state.currencies)
    state.save_context = 'Main'
    class Progress:
        def __init__(self): self.samples=[]
        def update(self,fraction,detail=None): self.samples.append((fraction,detail))
    progress=Progress()
    ui._populate(bpy.context,progress)
    fractions=[value for value,_ in progress.samples]
    assert fractions[0] == 0 and fractions[-1] == 1 and fractions == sorted(fractions)
    assert any('Preparing items' in detail for _,detail in progress.samples)
    del ui.SESSION['roots']['save10.hg']['BaseContext']['PlayerStateData']['Specials']
    ui._populate(bpy.context)
    quicksilver=next(row for row in state.currencies if row.name=='Quicksilver')
    assert not quicksilver.supported and quicksilver.reason
    quicksilver.selected=True
    try: ui._currency_selection(state)
    except ValueError: pass
    else: raise AssertionError('Unavailable currency was accepted')
    ui.SESSION['roots']['save10.hg']['BaseContext']['PlayerStateData']['Specials']=99
    ui._populate(bpy.context)
    assert len(state.items) == 5
    assert state.items[1].already_known and not state.items[4].supported
    assert state.items[3].scope == 'Account reward'
    assert bpy.ops.bbe.buildable_unlock_select(select=True) == {'FINISHED'}
    assert [r.selected for r in state.items] == [True, False, True, True, False]
    bpy.ops.bbe.buildable_unlock_select(select=False)
    assert not any(r.selected for r in state.items)
    state.search = 'buildwall'
    assert ui._matches(state.items[0], state)
    assert not ui._matches(state.items[2], state)
    bpy.ops.bbe.buildable_unlock_select(select=True, visible_only=True)
    assert [r.selected for r in state.items] == [True, False, False, False, False]
    state.search = 'Warp Drive'
    assert ui._matches(state.items[2], state)
    state.search = ''; state.category = 'Expedition'
    assert ui._matches(state.items[3], state) and not ui._matches(state.items[0], state)
    # Exercise all native catalogue rows in RNA, including independent origin
    # filtering and Select Filtered. This does not open or write save files.
    catalogue = ui.core.load_catalogue()
    ui.SESSION['catalogue'] = catalogue
    for root in ui.SESSION['roots'].values():
        root['BaseContext']['PlayerStateData']['KnownSpecials'] = []
    ui.SESSION['account']['root']['UserSettingsData'] = {field: [] for field in ui.core.ACCOUNT_FIELDS}
    ui._CATEGORIES = [('ALL', 'All Categories', '')] + [(v, v, '') for v in sorted({i['category'] for i in catalogue['items']})]
    ui._GROUPS = [('ALL', 'All Item Groups', '')] + [(v, v, '') for v in sorted({i['category'].split(' / ', 1)[0] for i in catalogue['items']})]
    ui._ORIGINS = [('ALL', 'All Origins', ''), ('Expedition', 'Expedition', ''), ('Quicksilver', 'Quicksilver', ''), ('Twitch reward', 'Twitch reward', '')]
    state.category = 'ALL'; state.origin = 'ALL'; ui._populate(bpy.context)
    assert len(state.items) == catalogue['coverage']['item_count']
    bpy.ops.bbe.buildable_unlock_select(select=True)
    assert sum(r.selected for r in state.items) == catalogue['coverage']['learnable_count']
    bpy.ops.bbe.buildable_unlock_select(select=False)
    state.origin = 'Expedition'
    bpy.ops.bbe.buildable_unlock_select(select=True, visible_only=True)
    assert all('Expedition' in r.tags for r in state.items if r.selected)
    assert any(r.selected for r in state.items)
    state.origin = 'ALL'; state.group = 'Expedition'; state.category = 'Expedition / Season 23'
    assert ui._matches(next(r for r in state.items if r.item_id == 'EXPD_EGG_23'), state)
    assert not ui._matches(next(r for r in state.items if r.item_id == 'NPCBUILDERTERM'), state)
    assert all(c[0] == 'ALL' or c[0].startswith('Expedition / ') for c in ui._categories(state, bpy.context))
    state.group = 'Twitch Drops'
    assert state.category == 'ALL', 'Changing the group must clear a stale subcategory'
    twitch = next(r for r in state.items if r.related_id and r.tags == 'Twitch reward')
    state.search = twitch.related_id
    assert ui._matches(twitch, state), 'Reward product ID must be searchable'
    state.search = ''; state.group = 'Titles'; state.category = 'Titles / Expedition'
    title = next(r for r in state.items if r.item_id == 'T_EXPD14')
    assert title.related_id == 'EXPD_TITLE14' and ui._matches(title, state)
    state.group = 'ALL'
    ui._on_load(None)
    assert ui.SESSION is None
    print('BUILDABLE_UNLOCK_UI_OK: registration, names/IDs, filtering, select/deselect, unavailable rows, account scope, currencies, uint32, mixed balances, context isolation, progress, load cleanup')
finally:
    ui.unregister()
    assert not hasattr(bpy.types.WindowManager, 'bbe_buildable_unlocks')
