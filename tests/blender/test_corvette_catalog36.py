"""Navigation changes preserve every native ID and all placement definitions."""
from pathlib import Path
import csv
import io
import sys
import zipfile

sys.path.insert(0, str(Path(__file__).parent))
from test_support import module, D, R, report

dictionary = module('utils.dictionary')
names = dictionary.get_nice_names_diictionary()
rows = dictionary.get_parts_definition()
tree = module('utils.asset_browser_utils').build_category_tree(favourite_ids=[])
corvette = tree['Corvette']
assert 'B_WNG_B' in corvette['Access and Docking']
assert 'B_WNG_B_R' in corvette['Access and Docking']['B_WNG_B']['variants']
assert 'B_WNG_B' not in corvette['Wings']
for identity in ('B_WNG_A', 'B_WNG_P', 'B_WNG_S', 'B_WNG_W', 'B_WNG_X', 'B_WNG_Y'):
    assert identity in corvette['Thrusters'], identity
    assert identity not in corvette['Wings'], identity
assert 'B_WNG_T' in corvette['Wings']
assert 'B_DECO_I' in corvette['Defensive Systems']
for identity, expected in {
    'B_GEN_4': 'Limos-Class Generator',
    'B_GEN_5': 'Vile Proboscis Generator',
    'B_TUR_F': 'Venom Spitter',
    'B_MAG_1X1': 'Tractor Beam',
}.items():
    assert names[identity] == expected, (identity, names[identity])
    assert rows['^' + identity][7] == expected.upper()
assert 'B_STR_AA_NE' not in corvette['Hull Plating']
assert 'B_STR_AA_NE' in corvette['Hull Plating']['B_STR_A_NE']['variants']
assert 'B_STR_AA_N' in corvette['Hull Plating']  # Distinct Aeron Winglet.
assert 'B_STR_AB_N' in corvette['Hull Plating']
assert len(corvette['Hull Plating']['B_STR_AB_N']['variants']) == 7
assert len(corvette['Hull Plating']['B_STR_AB_NE']['variants']) == 15
for identity in ('B_LAN_B', 'B_STR_AM_NE', 'B_STR_AN_NE', 'B_STR_AB_NE'):
    assert any(identity in category for category in corvette.values()), identity
    assert 'hidden' in dictionary.PLACEMENT_HELP[identity].lower(), identity

with zipfile.ZipFile(R / 'dist/no_mans_sky_base_builder-18.2.35.zip') as old:
    old_rows = {row[0]: row for row in csv.reader(io.StringIO(
        old.read('resources/DT_PartDefinition.csv').decode('utf-16'))) if row}
assert set(rows) == set(old_rows) - {'---'}
changed = 0
for identity, row in rows.items():
    previous = old_rows[identity]
    if row != previous:
        changed += 1
        assert row[2] == 'Corvette', identity
        for index, (before, after) in enumerate(zip(previous, row)):
            if index not in (4, 7, 8, 9):
                assert before == after, (identity, index)
report('corvette_catalog36', {
    'preservedPartIds': len(rows),
    'changedNavigationRows': changed,
    'nativeNamesCorrected': 4,
    'thunderbirdLandingThrustersVisibleWithVariant': True,
    'distinctAeronWingletAndHiddenPartsPreserved': True,
    'duplicateArgonautTileFoldedIntoVariants': True,
})
