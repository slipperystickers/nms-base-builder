"""Build the offline unlock catalogue from unmodified game MXML and English text.

Usage: python tools/build_buildable_unlock_catalog.py <extracted-native-folder>
The input folder must include manifest.json with source MBIN hashes/build ID.
No game saves, inventories or account files are read or written.
"""
import argparse
import collections
import json
from pathlib import Path
import re
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / 'src/addons/no_mans_sky_base_builder/resources/buildable_unlocks.json'
# Native tables include unfinished/internal objects without English labels.
# These are descriptive reference labels, not claimed game translations.
UNTRANSLATED_NAMES = {
    'BLD_SET_MONUMENT_NAME_L': 'Settlement Monument',
    'BLD_SET_CONSTRUCT_NAME_L': 'Settlement Construction Site',
    'BLD_SET_MAYORTERM_NAME_L': "Overseer's Terminal",
    'BLD_SET_INT_SUMMARY_NAME_L': 'Settlement Status Terminal',
    'BLD_SET_INT_SHIPSAL_NAME_L': 'Starship Salvage Terminal',
    'BLD_SET_STAFFBUILD_NAME_L': 'Staff Assembly Terminal',
    'BLD_SET_GROUNDDECAL_NAME_L': 'Settlement Ground Decal',
    'BLD_GAMETABLE_NAME_L': 'Game Table',
    'BLD_B_CANOPY_WALL1_NAME_L': 'Canopy Wall 1',
    'BLD_B_CANOPY_WALL2_NAME_L': 'Canopy Wall 2',
    'BLD_B_WALL_SUPPORTS_NAME_L': 'Wall Supports',
    'UI_BRIDGECONNECT_NAME_L': 'Bridge Connector',
    'BLD_BIG_STR_AA_COR_NAME_L': 'Hull Corner AA',
    'BLD_BIG_STR_AB_COR_NAME_L': 'Hull Corner AB',
    'BLD_BIG_STR_AB_STR_NAME_L': 'Hull Structure AB',
    'BLD_BIG_STR_STR_E_NAME_L': 'Hull Structure E',
}


def field(node, name):
    return node.find(f"Property[@name='{name}']") if node is not None else None


def value(node, name, default=''):
    item = field(node, name)
    return item.get('value', default) if item is not None else default


def children(node, name):
    item = field(node, name)
    return list(item) if item is not None else []


def nested(node, name, key):
    return value(field(node, name), key)


def build(native):
    tables = native / 'metadata/reality/tables'
    provenance = json.loads((native / 'manifest.json').read_text(encoding='utf-8'))
    if provenance.get('decode_errors'):
        raise ValueError('Resolve native decoding errors before publishing a catalogue')

    def table(name):
        return ET.parse(tables / (name + '.MXML')).getroot()

    translations = {}
    for path in sorted((native / 'language').glob('*.MXML')):
        for row in ET.parse(path).getroot()[0]:
            text = value(row, 'English')
            if text:
                translations[value(row, 'Id')] = re.sub(r'<[^>]+>', '', text).strip()

    def name(row, fallback):
        return translations.get(value(row, 'NameLower')) or translations.get(value(row, 'Name')) or fallback

    products = {}
    for source in ('nms_reality_gcproducttable', 'nms_basepartproducts', 'nms_modularcustomisationproducts'):
        for row in table(source)[0]:
            products[value(row, 'ID')] = row
    product_icons = collections.defaultdict(list)
    for identifier, row in products.items():
        product_icons[Path(value(field(row, 'Icon'), 'Filename')).stem].append(identifier)
    base = table('basebuildingobjectstable')
    objects = {value(row, 'ID'): row for row in children(base, 'Objects')}
    groups = {value(row, 'ID'): name(row, value(row, 'ID')).title() for row in children(base, 'Groups')}
    season = {
        value(row, 'ID'): [entry.get('value', '') for entry in children(row, 'SeasonIds')]
        for row in table('unlockableseasonrewards')[0]
    }
    twitch = [(value(row, 'TwitchId'), value(row, 'ProductId'))
              for row in table('unlockabletwitchrewards')[0]]
    platform = [(value(row, 'RewardId'), value(row, 'ProductId'))
                for row in table('unlockableplatformrewards')[0]]
    unlock_tree_ids = {p.get('value') for p in table('unlockableitemtrees').iter('Property') if p.get('name') == 'Unlockable'}

    product_types = {'BuildingPart': 'Base Parts', 'CustomisationPart': 'Appearance',
                     'Curiosity': 'Collectibles', 'Emote': 'Emotes',
                     'Consumable': 'Consumables', 'Tradeable': 'Items',
                     'Component': 'Components', 'SpaceSalvage': 'Salvage',
                     'Fish': 'Fish'}

    def product_type(product):
        native_type = nested(product, 'Type', 'ProductCategory')
        return product_types.get(native_type, native_type or 'Other Items')

    def category(obj, product, identifier):
        if identifier in season:
            number = next((int(x) for x in season[identifier] if x.isdecimal()), None)
            return f'Expedition / Season {number:02d}' if number is not None else 'Expedition / Other Rewards'
        if nested(product, 'TradeCategory', 'TradeCategory') == 'SpecialShop':
            return 'Quicksilver / ' + product_type(product)
        if obj is None:
            return 'Recipes / ' + product_type(product)
        native_groups = children(obj, 'Groups')
        group = value(native_groups[0], 'Group') if native_groups else ''
        label = groups.get(group, 'Other Buildable Items')
        if group.startswith('BIGGS'):
            return 'Corvette / ' + label
        if group.startswith('FREIGHT'):
            return 'Freighter / ' + label
        if group.startswith('STATION') or group == 'SPACE':
            return 'Space Station / ' + label
        return 'Construction / ' + label

    selected = set(objects)
    selected.update(identifier for identifier, row in products.items()
                    if nested(row, 'Type', 'ProductCategory') == 'BuildingPart')
    selected.update(identifier for identifier, row in products.items()
                    if value(row, 'IsCraftable') == 'true' or identifier in unlock_tree_ids
                    or nested(row, 'TradeCategory', 'TradeCategory') == 'SpecialShop'
                    or identifier in season)
    items = []
    for identifier in sorted(selected):
        obj, product = objects.get(identifier), products.get(identifier)
        # Object overrides are explicit native mappings, never a guessed ID prefix.
        target = identifier
        if product is None and value(obj, 'UseProductIDOverride') == 'true':
            target = value(obj, 'OverrideProductID')
            product = products.get(target)
        title = name(product, '')
        translated = bool(title)
        if not title:
            icon_product = products.get(value(obj, 'IconOverrideProductID'))
            title = name(icon_product, '')
        if not title:
            title = UNTRANSLATED_NAMES.get(value(product, 'NameLower'), identifier.replace('_', ' ').title())
        learnable = product is not None and (value(product, 'IsCraftable') == 'true' or target in unlock_tree_ids)
        row = dict(id=target, name=title, kind='Product', category=category(obj, product, target),
                   object_ids=[identifier] if obj is not None else [],
                   unlock_field='KnownProducts' if learnable else None, tags=[])
        if not translated:
            row['name_source'] = 'Descriptive label; the native English name is absent'
        if not learnable:
            row['scope_note'] = ('This is an inventory or internal part, not a learnable blueprint. '
                                 'Unlocking knowledge does not acquire it.') if product is not None else 'Internal object: no native product blueprint exists.'
        else:
            row['scope_note'] = 'Learn this blueprint in the selected save context.'
        if target in season:
            row['tags'].append('Expedition')
            row.update(account_field='UnlockedSeasonRewards', account_id=target,
                       unlock_field='KnownProducts' if learnable else 'AccountWideSpecials',
                       scope_note=('Learn the blueprint and unlock its expedition reward for this account.'
                                   if learnable else 'Unlock this expedition reward for this account.'))
        elif nested(product, 'TradeCategory', 'TradeCategory') == 'SpecialShop':
            row['tags'].append('Quicksilver')
            row.update(account_field='UnlockedSpecials', account_id=target,
                       unlock_field='KnownProducts' if learnable else 'AccountWideSpecials',
                       scope_note=('Learn the blueprint and unlock its Quicksilver item for this account.'
                                   if learnable else 'Unlock this Quicksilver item for this account.'))
        if learnable and nested(product, 'TradeCategory', 'TradeCategory') == 'SpecialShop':
            row['extra_save_fields'] = ['KnownSpecials']
        items.append(row)

    # The native Corvette research tree contains module unlock IDs that are
    # absent from the product table. Keep their exact IDs instead of guessing
    # a related build-object ID.
    technologies = {value(row, 'ID') for row in table('nms_reality_gctechnologytable')[0]}
    for identifier in sorted(unlock_tree_ids - products.keys() - technologies):
        matching_products = product_icons.get(identifier, [])
        matching_names = {name(products[product_id], '') for product_id in matching_products}
        matching_names.discard('')
        title = next(iter(matching_names)) if len(matching_names) == 1 else identifier.replace('_', ' ').title()
        items.append(dict(id=identifier, name=title,
                          kind='Product', category='Corvette / Research Tree',
                          object_ids=[], unlock_field='KnownProducts', tags=[],
                          name_source=('Native product name from the exact research icon' if len(matching_names) == 1
                                       else 'Descriptive label for a native research-tree ID'),
                          scope_note='Learn this native Corvette research-tree entry in the selected save context.'))

    # Twitch and platform entitlements have reward IDs separate from product
    # IDs. Their checkboxes change the local account reward list, not a recipe.
    for reward_id, product_id in twitch:
        product = products.get(product_id)
        items.append(dict(id=reward_id, name=name(product, product_id), kind='Twitch Reward',
                          category='Twitch Drops / ' + product_type(product),
                          object_ids=[], related_id=product_id,
                          unlock_field='AccountWideSpecials', account_field='UnlockedTwitchRewards',
                          account_id=reward_id, tags=['Twitch reward'],
                          scope_note='Add the local Twitch reward flag; online entitlement sync may still apply.'))
    for reward_id, product_id in platform:
        product = products.get(product_id)
        items.append(dict(id=reward_id, name=name(product, product_id), kind='Platform Reward',
                          category='Platform Rewards / ' + product_type(product),
                          object_ids=[], related_id=product_id,
                          unlock_field='AccountWideSpecials', account_field='UnlockedPlatformRewards',
                          account_id=reward_id, tags=['Platform reward'],
                          scope_note='Add the local platform reward flag; platform ownership is not changed.'))

    title_rows = list(ET.parse(native / 'metadata/gamestate/playerdata/playertitledata.MXML').getroot()[0])
    for title in title_rows:
        identifier = value(title, 'ID')
        if identifier == 'T_DEFAULT':
            continue
        title_text = translations.get(value(title, 'Title'), identifier)
        title_text = re.sub(r'\s*%NAME%\s*', ' ', title_text).strip(' ,') or identifier
        recipe = value(title, 'UnlockedByProductRecipe')
        if recipe.startswith('EXPD_'):
            category_name, tags = 'Titles / Expedition', ['Expedition']
        elif recipe.startswith('SPEC_'):
            category_name, tags = 'Titles / Quicksilver', ['Quicksilver']
        elif value(title, 'UnlockedByMission'):
            category_name, tags = 'Titles / Missions', []
        elif value(title, 'UnlockedByTrophy'):
            category_name, tags = 'Titles / Achievements', []
        elif value(title, 'UnlockedByStat'):
            category_name, tags = 'Titles / Milestones', []
        else:
            category_name, tags = 'Titles / Other', []
        items.append(dict(id=identifier, name=title_text, kind='Title', category=category_name,
                          object_ids=[], related_id=recipe, unlock_field='AccountWideSpecials',
                          account_field='UnlockedTitles', account_id=identifier, tags=tags,
                          scope_note='Unlock this title for this account; mission and milestone progress is unchanged.'))

    tech_categories = {'Suit': 'Exosuit', 'Weapon': 'Multi-Tool', 'Ship': 'Starship',
                       'AllShips': 'Starship', 'AllShipsExceptAlien': 'Starship',
                       'AlienShip': 'Living Ship', 'RobotShip': 'Sentinel Ship',
                       'AllVehicles': 'Exocraft', 'Mech': 'Minotaur', 'Submarine': 'Nautilon'}
    for product in table('nms_reality_gctechnologytable')[0]:
        identifier = value(product, 'ID')
        # Broken slots, procedural upgrades and repair placeholders are not blueprints.
        if value(product, 'Teach') != 'true' and identifier not in unlock_tree_ids:
            continue
        group = nested(product, 'Category', 'TechnologyCategory')
        items.append(dict(id=identifier, name=name(product, identifier), kind='Technology',
                          category='Technology / ' + tech_categories.get(group, group),
                          object_ids=[], unlock_field='KnownTech', tags=[],
                          scope_note='Learn this installable technology in the selected save context.'))

    # An explicit override can give several objects the same learned product.
    merged = {}
    for row in items:
        key = row['kind'], row['id']
        if key in merged:
            merged[key]['object_ids'] = sorted(set(merged[key]['object_ids'] + row['object_ids']))
        else:
            merged[key] = row
    items = sorted(merged.values(), key=lambda r: (r['category'], r['name'].casefold(), r['id']))
    coverage = {identifier for row in items for identifier in row['object_ids']}
    assert coverage == set(objects), sorted(set(objects) - coverage)
    assert all(row['name'] and row['id'] for row in items)
    return dict(schema_version=1, items=items, provenance=provenance,
                coverage=dict(native_object_count=len(objects), covered_object_count=len(coverage),
                              native_season_rewards=len(season), covered_season_rewards=sum(
                                  any(r['id'] == identifier and r.get('account_field') == 'UnlockedSeasonRewards'
                                      for r in items) for identifier in season),
                              native_twitch_rewards=len(twitch), covered_twitch_rewards=sum(
                                  r['kind'] == 'Twitch Reward' for r in items),
                              native_platform_rewards=len(platform), covered_platform_rewards=sum(
                                  r['kind'] == 'Platform Reward' for r in items),
                              native_titles=len(title_rows) - 1, covered_titles=sum(
                                  r['kind'] == 'Title' for r in items),
                              item_count=len(items), learnable_count=sum(bool(r['unlock_field']) for r in items)),
                limitations=['Inventory-only Corvette parts and internal objects cannot be acquired by learning a blueprint.',
                             'Twitch and platform checkboxes update local account flags; external account eligibility is not changed.',
                             'No procedural upgrades, broken technology slots or ordinary inventory items are added.'])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('native', type=Path)
    parser.add_argument('--output', type=Path, default=OUTPUT)
    args = parser.parse_args()
    result = build(args.native)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(result['coverage']))
    print(json.dumps(collections.Counter(row['category'] for row in result['items']), indent=2))


if __name__ == '__main__':
    main()
