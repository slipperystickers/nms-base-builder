"""Explicit, replayable ship replacements. Pure draft operations; no save writes."""
import copy
import hashlib
import json
import math
from . import ship_core as core

# Cable At vectors encode endpoint displacement, including coincident ends.
# They are not the unit facing direction used by ordinary build parts.
CABLE_IDS = frozenset({'U_POWERLINE', 'U_PIPELINE', 'U_PORTALLINE', 'U_BYTEBEATLINE'})


def fingerprint(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'),
                                     allow_nan=False).encode('utf8')).hexdigest()


def cockpit_warning(objects):
    if not any(str(core.get(p, 'ObjectID', '')).lstrip('^').startswith('B_COK_') for p in objects):
        return 'No Corvette cockpit: this build will be unflyable. Export is allowed; no cockpit will be added.'
    return ''


def inspect_slots(root, context, include_warnings=True):
    """Return per-slot explanations plus records which cannot identify a slot."""
    owned = core.ships(root, context)
    slots = {i: [] for i in range(12)}
    linked = {i: [] for i in range(12)}
    unassigned = []
    bases = core.get(core.player(root, context), 'PersistentPlayerBases', [])
    if not isinstance(bases, list):
        return slots, ['Build list has an unsupported format.']
    for number, base in enumerate(bases):
        if not isinstance(base, dict):
            unassigned.append(f'Build record {number + 1} has an unsupported format.')
            continue
        if core.kind(base) != 'PlayerShipBase':
            continue
        index = core.get(base, 'UserData')
        if type(index) is not int or not 0 <= index < 12:
            unassigned.append(f'Build {number + 1}: no valid ship slot; inspect Link Status.')
            continue
        linked[index].append(number)
    for index, ship in enumerate(owned):
        records = linked[index]
        if records and not core.corvette(ship):
            slots[index].append('Corvette build linked to a non-Corvette ship.' if core.occupied(ship)
                                else 'Corvette build linked to an empty ship slot.')
        if len(records) > 1:
            slots[index].append(f'{len(records)} Corvette builds share this slot.')
        if core.corvette(ship) and not records:
            slots[index].append('Corvette ship has no linked build.')
        for number in records:
            objects = core.get(bases[number], 'Objects', [])
            if not isinstance(objects, list) or not objects:
                slots[index].append(f'Build {number + 1} has no parts.')
            elif include_warnings and cockpit_warning(objects):
                slots[index].append(f'Build {number + 1}: {cockpit_warning(objects)}')
        if core.occupied(ship):
            for field, label in (('Inventory', 'Cargo'), ('Inventory_TechOnly', 'Technology')):
                try:
                    core.validate_inventory(core.inventory(root, context, index, field))
                except (ValueError, TypeError, KeyError, AttributeError) as exc:
                    slots[index].append(f'{label}: {exc}')
    return slots, unassigned


def linked_builds(root, context, index):
    bases = core.get(core.player(root, context), 'PersistentPlayerBases', [])
    if not isinstance(bases, list):
        raise ValueError('The build list must be readable before replacing a ship.')
    return [n for n, base in enumerate(bases) if core.kind(base) == 'PlayerShipBase'
            and type(core.get(base, 'UserData')) is int and core.get(base, 'UserData') == index]


def require_objects_destination(root, context, base):
    """Objects-only export cannot repair or relabel a non-Corvette ownership slot."""
    index = core.get(base, 'UserData')
    if (type(index) is not int or not 0 <= index < 12
            or not core.corvette(core.ships(root, context)[index])
            or len(linked_builds(root, context, index)) != 1):
        raise ValueError('This build has an uncertain Corvette link. Review Repair — Keep My Build in I/O, or choose a destination through Export to Save.')


def validate_parts(objects):
    if not isinstance(objects, list) or not objects:
        raise ValueError('The replacement contains no build objects.')
    for number, part in enumerate(objects, 1):
        if not isinstance(part, dict) or not isinstance(part.get('ObjectID'), str) or not part['ObjectID'].strip('^'):
            raise ValueError('Every replacement part needs an ObjectID.')
        for field in ('Position', 'Up', 'At'):
            vector = part.get(field)
            if (not isinstance(vector, list) or len(vector) != 3
                    or any(type(v) not in (int, float) or not math.isfinite(v) for v in vector)):
                raise ValueError(f'A replacement part has an invalid {field} vector.')
        for field in ('Up', 'At'):
            if not any(part[field]):
                if field == 'At' and part['ObjectID'].lstrip('^') in CABLE_IDS:
                    continue
                axis = 'Y' if field == 'Up' else 'Z'
                raise ValueError(
                    f"Part {number} ({part['ObjectID'].lstrip('^')}) has a zero {field} direction. "
                    f"In Blender, find that part and check Scale {axis} on it and its parent/group before exporting."
                )


def read_replacement(path, mode):
    from ..interchange import BuildFile, _decode
    build = BuildFile.read(path)
    objects = core.translate(build.objects)
    payload = {'objects': objects}
    validate_parts(objects)
    if mode == 'FULL':
        if build.kind != 'ship':
            raise ValueError('Replace Entire Ship requires a complete .nmsship package, not objects-only data.')
        payload['ship'] = core.translate(_decode(build.entries['so.json'], 'so.json'))
        payload['custom'] = (core.translate(_decode(build.entries['ccd.json'], 'ccd.json'))
                             if 'ccd.json' in build.entries else None)
        from .. import build_metadata
        if build_metadata.SHIP_STATE_ENTRY in build.entries:
            state = build_metadata.read_ship_state(_decode(
                build.entries[build_metadata.SHIP_STATE_ENTRY], build_metadata.SHIP_STATE_ENTRY))
            if 'ShipUsesLegacyColours' in state:
                payload['legacy_colours'] = state['ShipUsesLegacyColours']
        validate_payload(payload, mode)
    elif mode != 'OBJECTS':
        raise ValueError('Choose a supported replacement mode.')
    return payload


def validate_payload(payload, mode):
    validate_parts(payload.get('objects'))
    if mode == 'FULL':
        ship = payload.get('ship')
        if not isinstance(ship, dict) or not core.corvette(ship):
            raise ValueError('The package ship record is not a Corvette. Its model must be a BIGGS/Corvette model.')
        if not isinstance(core.get(ship, 'Name'), str):
            raise ValueError('The replacement ship needs a valid name field.')
        for field in ('Resource', 'Inventory', 'Inventory_TechOnly', 'InventoryLayout'):
            if not isinstance(core.get(ship, field), dict):
                raise ValueError(f'The package is missing a valid {field} record.')
        for field in ('Inventory', 'Inventory_TechOnly'):
            core.validate_inventory(core.translate(core.get(ship, field)))
        custom = payload.get('custom')
        if custom is not None and (not isinstance(custom, dict) or not isinstance(custom.get('CustomData'), dict)):
            raise ValueError('The package appearance record is incomplete.')
    elif mode != 'OBJECTS':
        raise ValueError('Choose a supported replacement mode.')


def empty_ship_slots(root, context):
    """An orphan build still reserves its slot; never overwrite it as empty."""
    return [i for i, ship in enumerate(core.ships(root, context))
            if not core.occupied(ship) and not linked_builds(root, context, i)]


def rebuild_payload(root, context, index, anchor=None, objects=None, name=None, new=False):
    """Use a Corvette chassis while preserving readable ship data and exact parts.

    Returns a payload plus explicit reset notices for the review. No file writes
    or inserted template parts. Invalid inventories are never silently discarded.
    """
    if type(index) is not int or not 0 <= index < 12:
        raise ValueError('Choose a ship slot from 1 to 12.')
    old = core.translate(core.ships(root, context)[index])
    records = linked_builds(root, context, index)
    if new and index not in empty_ship_slots(root, context):
        raise ValueError('This ship slot is no longer empty. Choose another destination.')
    if anchor is not None and anchor not in records:
        raise ValueError('Choose one of this slot’s linked builds to keep.')
    if objects is None:
        if anchor is None:
            if len(records) != 1:
                raise ValueError('Choose exactly which saved build to preserve.')
            anchor = records[0]
        base = core.get(core.player(root, context), 'PersistentPlayerBases')[anchor]
        objects = core.translate(core.get(base, 'Objects', []))
        if name is None:
            name = core.get(old, 'Name') or core.get(base, 'Name')
    validate_parts(objects)
    template = json.loads((core.RES / 'minimal_corvette.json').read_text())
    ship = copy.deepcopy(template['ship'] if new else old)
    resets = []
    if not core.corvette(ship):
        ship['Resource'] = copy.deepcopy(template['ship']['Resource'])
    for field in ('Inventory', 'Inventory_TechOnly', 'Inventory_Cargo'):
        try:
            core.validate_inventory(ship.get(field, {}))
        except (ValueError, TypeError, KeyError, AttributeError):
            ship[field] = copy.deepcopy(template['ship'][field])
            resets.append(field + ': unreadable inventory; template items, class, stats and hyperslots will replace it.')
    if not isinstance(ship.get('InventoryLayout'), dict):
        ship['InventoryLayout'] = copy.deepcopy(template['ship']['InventoryLayout'])
        resets.append('InventoryLayout: unreadable layout will use the template.')
    ship['Name'] = str(name or ship.get('Name') or 'Corvette')
    p = core.player(root, context)
    appearances = core.get(p, 'CharacterCustomisationData', [])
    custom = None
    if isinstance(appearances, list) and len(appearances) > core.CUSTOM_SLOTS[index]:
        old_custom = core.translate(appearances[core.CUSTOM_SLOTS[index]])
        if not new and isinstance(old_custom, dict) and isinstance(old_custom.get('CustomData'), dict):
            custom = old_custom
        else:
            custom = copy.deepcopy(template['custom'])
            if not new:
                resets.append('Appearance: unreadable appearance will use Corvette defaults. Part colors are retained.')
    elif appearances:
        raise ValueError('Unknown appearance-slot layout. Nothing can be repaired safely.')
    payload = dict(ship=ship, objects=copy.deepcopy(objects), custom=custom)
    legacy = core.get(p, 'ShipUsesLegacyColours', [])
    if not new and isinstance(legacy, list) and len(legacy) == 12:
        payload['legacy_colours'] = legacy[index]
    validate_payload(payload, 'FULL')
    return payload, resets


def make_plan(root, context, index, payload, mode, anchor=None, replace_duplicates=False):
    """Only linked records explicitly listed in this review may be replaced."""
    if type(index) is not int or not 0 <= index < 12:
        raise ValueError('Choose a ship slot from 1 to 12.')
    core.ships(root, context)
    validate_payload(payload, mode)
    records = linked_builds(root, context, index)
    if mode == 'OBJECTS':
        if not core.corvette(core.ships(root, context)[index]) or len(records) != 1:
            raise ValueError('Objects-only replacement requires one correctly linked Corvette. Use Replace Entire Ship to repair this slot.')
    if len(records) > 1 and not replace_duplicates:
        raise ValueError('Confirm replacement of every duplicate build listed for this slot.')
    if records:
        anchor = records[0] if anchor is None and len(records) == 1 else anchor
        if type(anchor) is not int or anchor not in records:
            raise ValueError('Select which linked build supplies the destination metadata.')
    elif anchor is not None:
        raise ValueError('This slot has no linked build to retain.')
    return {'context': context, 'index': index, 'payload': copy.deepcopy(payload),
            'mode': mode, 'records': records, 'anchor': anchor,
            'replace_duplicates': replace_duplicates}


def apply_plan(root, plan):
    """Returns a new root; invalid input never partly mutates the existing draft."""
    context, index = plan['context'], plan['index']
    checked = make_plan(root, context, index, plan['payload'], plan['mode'],
                        plan['anchor'], plan['replace_duplicates'])
    if checked != plan:
        raise ValueError('The reviewed build records changed; review the replacement again.')
    out = copy.deepcopy(root)
    p = core.player(out, context)
    owned = core.ships(out, context)
    bases = core.get(p, 'PersistentPlayerBases', [])
    payload = plan['payload']
    raw = 'ShipOwnership' not in p
    def encoded(value):
        return core.translate(copy.deepcopy(value), False) if raw else copy.deepcopy(value)
    if plan['anchor'] is None:
        base = encoded(json.loads((core.RES/'minimal_corvette.json').read_text())['base'])
    else:
        base = copy.deepcopy(bases[plan['anchor']])
    core.put(base, 'Objects', encoded(payload['objects']))
    if payload.get('owner_override') is not None:
        from ..build_metadata import apply_save_owner
        apply_save_owner(base, payload['owner_override'])
    core.put(base, 'UserData', index)
    core.put(base, 'BaseType', encoded({'PersistentBaseTypes': 'PlayerShipBase'}))
    if plan['mode'] == 'FULL':
        ship = encoded(payload['ship'])
        # Keep the destination's world placement; never import another save's position.
        for field in ('Location', 'Position', 'Direction'):
            if core.key(owned[index], field) in owned[index]:
                core.put(ship, field, copy.deepcopy(core.get(owned[index], field)))
        owned[index] = ship
        core.put(base, 'Name', core.get(ship, 'Name'))
        custom = core.get(p, 'CharacterCustomisationData', [])
        if custom:
            if not isinstance(custom, list) or len(custom) <= core.CUSTOM_SLOTS[index]:
                raise ValueError('Unknown appearance-slot layout; nothing was replaced.')
            appearance = payload.get('custom')
            if appearance is None:
                appearance = json.loads((core.RES/'minimal_corvette.json').read_text())['custom']
            custom[core.CUSTOM_SLOTS[index]] = encoded(appearance)
        elif payload.get('custom') is not None:
            raise ValueError('This save has no appearance slots for the imported appearance.')
        legacy = core.get(p, 'ShipUsesLegacyColours', [])
        if legacy:
            if not isinstance(legacy, list) or len(legacy) != 12:
                raise ValueError('Unknown colour-slot layout; nothing was replaced.')
            legacy[index] = payload.get('legacy_colours', False)
        if core.get(p, 'PrimaryShip') == index:
            for target, source in (('CurrentShip', 'Resource'), ('ShipInventory', 'Inventory'), ('ShipLayout', 'InventoryLayout')):
                if core.key(p, target) in p:
                    core.put(p, target, copy.deepcopy(core.get(ship, source)))
    if plan['records']:
        core.put(p, 'PersistentPlayerBases', [base if n == plan['anchor'] else b
                 for n, b in enumerate(bases) if n == plan['anchor'] or n not in plan['records']])
    else:
        core.put(p, 'PersistentPlayerBases', bases + [base])
    if plan['mode'] == 'FULL' and inspect_slots(out, context, include_warnings=False)[0][index]:
        raise ValueError('The replacement still has a slot mismatch; nothing was staged.')
    return out


def validate_reviewed_draft(original, draft, plans):
    """Replay explicit repairs, then use the existing strict draft validator.

    Repair authorization is a session-only ledger, never a flag loaded from a
    save. Unrelated broken records and contexts remain protected.
    """
    baseline = original
    for plan in plans:
        baseline = apply_plan(baseline, plan)
    core.validate_draft(baseline, draft)
    # Until these replacements are saved, only inventory edits may follow in
    # their contexts. Becoming healthy must not authorize unrelated topology.
    for context in {plan['context'] for plan in plans}:
        context_key = core.key(baseline, 'BaseContext' if context == 'Main' else 'ExpeditionContext')
        expected_context = core.inventory_edit_context(baseline, draft, context)
        if expected_context != draft[context_key]:
            raise ValueError('Unreviewed ship or build changes accompanied the replacement; review again.')
