"""Independent, non-mutating Corvette export ordering and exact deduplication.

Priority data follows the user's supplied category/part ordering. This module
has no Blender or save-file dependencies and never edits its input objects.
"""
import copy
import json
from pathlib import Path


# IDs observed in the optimizer's warning groups. They affect order only;
# classification here never deletes or changes a placed object.
ORANGE_IDS = frozenset({
    'BUILDBEACON', 'MESSAGEMODULE', 'NPCBUILDERTERM', 'NPCFARMTERM',
    'NPCSCIENCETERM', 'NPCVEHICLETERM', 'NPCWEAPONTERM', 'SUMMON_GARAGE',
    'GARAGE_B', 'GARAGE_FLOAT', 'GARAGE_FREIGHT', 'GARAGE_L', 'GARAGE_M',
    'GARAGE_MECH', 'GARAGE_S', 'GARAGE_SUB',
})
RED_IDS = frozenset({
    'BUILD_REFINER1', 'BUILD_REFINER2', 'BUILD_REFINER3', 'FRE_ROOM_REFINE',
    'BASE_FLAG', 'SET_B_MONU', 'SET_MONUMENT', 'SET_T_MONU', 'SET_F_MONU',
    'SET_INT_SHIPSAL', 'SET_CONSTRUCT', 'SET_INT_SUMMARY', 'SET_MAYORTERM',
})


def defaults():
    return json.loads((Path(__file__).parents[1] / 'resources/corvette_priorities.json').read_text(encoding='utf-8'))


def validate(config):
    if not isinstance(config, dict) or type(config.get('delete_identical')) is not bool:
        raise ValueError('Invalid optimizer settings')
    groups = config.get('groups')
    if not isinstance(groups, list) or len(groups) > 128:
        raise ValueError('Expected up to 128 priority categories')
    names, ids, cleaned = set(), set(), []
    import re
    for group in groups:
        if not isinstance(group, dict):
            raise ValueError('Invalid priority category')
        name = str(group.get('name', '')).strip()
        parts = group.get('parts')
        if not name or len(name) > 80 or name.casefold() in names or not isinstance(parts, list):
            raise ValueError('Categories need unique names (up to 80 characters)')
        names.add(name.casefold())
        normalized = []
        for part in parts:
            if not isinstance(part, str):
                raise ValueError('Part IDs must be text')
            pid = part.strip().lstrip('^').upper()
            if not re.fullmatch(r'[A-Z0-9_]{1,64}', pid) or pid in ids:
                raise ValueError('Part IDs must be valid and appear only once in the priority list')
            ids.add(pid)
            normalized.append(pid)
        cleaned.append({'name': name, 'parts': normalized})
    return {'version': 1, 'delete_identical': config['delete_identical'], 'groups': cleaned}


def fingerprint(value):
    # No coordinate rounding, ignored timestamps or removed fields. JSON key
    # order is irrelevant; values, nested data and array order are retained.
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False)


def role_family(obj):
    """Return the game role whose placement order must survive optimization."""
    part_id = str(obj.get('ObjectID', '')).lstrip('^').upper()
    if part_id.startswith('B_COK_'):
        return 'cockpit'
    if part_id.startswith('B_ALK_'):
        return 'landing_bay'
    return None


def priority_order(objects, config, name_for_part=None):
    rank = {pid: (group_index, part_index)
            for group_index, group in enumerate(config['groups'])
            for part_index, pid in enumerate(group['parts'])}
    buckets = {}
    remainder = []
    paragon = []
    for index, obj in enumerate(objects):
        part_id = str(obj.get('ObjectID', '')).lstrip('^').upper()
        priority = rank.get(part_id)
        if part_id == 'U_PARAGON':
            paragon.append(index)
        elif priority is None:
            tier = 100 if part_id in ORANGE_IDS else 101 if part_id in RED_IDS else 102
            display_name = name_for_part(part_id) if name_for_part else part_id
            remainder.append((tier, str(display_name or part_id).casefold(), index))
        else:
            buckets.setdefault(priority, []).append(index)
    order = ([i for priority in sorted(buckets) for i in buckets[priority]]
             + [index for _, _, index in sorted(remainder)] + paragon)
    # A cockpit's camera/boarding role, and a bay's beam-up role, depend on
    # encounter order. Priority categories choose their location in the export,
    # but never silently exchange two placed members of either role family.
    for family in ('cockpit', 'landing_bay'):
        originals = [i for i in order if role_family(objects[i]) == family]
        originals.sort()
        positions = [pos for pos, i in enumerate(order) if role_family(objects[i]) == family]
        for pos, original in zip(positions, originals):
            order[pos] = original
    return order


def export_order(objects, config, name_for_part=None, manual_first=()):
    automatic = priority_order(objects, config, name_for_part)
    placed = set(manual_first)
    return [*manual_first, *(i for i in automatic if i not in placed)]


def optimize(objects, config, name_for_part=None, manual_first=()):
    config = validate(config)
    if not isinstance(objects, list) or any(not isinstance(o, dict) for o in objects):
        raise ValueError('Expected a list of saved objects')
    removed = []
    if config['delete_identical']:
        seen = set()
        # For identical records the first manually ranked instance wins.
        for i in dict.fromkeys((*manual_first, *range(len(objects)))):
            key = fingerprint(objects[i])
            if key in seen:
                removed.append(i)
            seen.add(key)
    excluded = set(removed)
    indices = [i for i in range(len(objects)) if i not in excluded]
    # Deduplicate before assigning cockpit and landing-bay roles.
    compact = {original: i for i, original in enumerate(indices)}
    order = export_order([objects[i] for i in indices], config, name_for_part,
                         [compact[i] for i in manual_first if i in compact])
    order = [indices[i] for i in order]
    return copy.deepcopy([objects[i] for i in order]), {
        'before': len(objects), 'after': len(order), 'removed': len(removed),
        'removed_indices': removed, 'moved': sum(i != original for i, original in enumerate(order)),
    }
