"""Build wrapper metadata. Owner belongs to the build, not the fleet ShipOwnership list."""
import copy
import json

PART_KEYS = {'Objects', 'objects', 'Prefab', 'Presets'}
OWNER_FIELDS = {'USN': 'string_usn', 'UID': 'string_uid', 'LID': 'string_lid',
                'PTK': 'string_ptk', 'TS': 'string_ts'}
PACKAGE_ENTRY = 'bbe-build-metadata.json'
SHIP_STATE_ENTRY = 'bbe-ship-state.json'
_approved_owners = {}


def encode(value):
    return json.dumps(value, ensure_ascii=False, allow_nan=False, sort_keys=True)


def wrapper(document):
    return copy.deepcopy({k: v for k, v in document.items() if k not in PART_KEYS})


def merge_preserved(source, baseline, current):
    """Retain imported types/unknown fields when a visible field was not edited."""
    result = copy.deepcopy(source)
    for key, value in current.items():
        if key in source and value == baseline.get(key):
            continue
        if isinstance(value, dict) and isinstance(source.get(key), dict):
            result[key] = merge_preserved(source[key], baseline.get(key, {}), value)
        else:
            result[key] = copy.deepcopy(value)
    return result


def field_text(value):
    return '' if value is None else str(value)


def edited_owner(owner, fields):
    if not isinstance(owner, dict):
        raise ValueError('The imported Owner record is not an object. Import a valid build first.')
    result = copy.deepcopy(owner)
    for key, text in fields.items():
        old = owner.get(key, '')
        if text == field_text(old):
            continue
        if type(old) is int:
            try:
                value = int(text)
            except ValueError as exc:
                raise ValueError(f'{key} is an integer in this build; enter a whole number.') from exc
        elif isinstance(old, (dict, list, bool, float)):
            raise ValueError(f'{key} has an unsupported type; its original value has been preserved.')
        else:
            value = text
        if key == 'TS' and key not in owner and text:
            try:
                value = int(text)
            except ValueError as exc:
                raise ValueError('TS must be a whole-number timestamp.') from exc
        result[key] = value
    return result


def save_owner(props):
    """Only a deliberate scene edit can authorize a later reviewed Owner write."""
    if not props.metadata_owner_to_save:
        return None
    owner = props.serialise().get('Owner')
    if not isinstance(owner, dict) or not owner:
        raise ValueError('Advanced metadata: provide an Owner record before exporting ownership.')
    if (encode(owner) != props.metadata_owner_reviewed or
            _approved_owners.get(props.id_data.as_pointer()) != props.metadata_owner_reviewed):
        raise ValueError('Ownership changed after review. Reopen Advanced Build Metadata and Apply again.')
    return copy.deepcopy(owner)


def approve_save_owner(props, enabled):
    props.metadata_owner_reviewed = encode(props.serialise()['Owner'])
    props.metadata_owner_to_save = enabled
    if enabled:
        _approved_owners[props.id_data.as_pointer()] = props.metadata_owner_reviewed
    else:
        _approved_owners.pop(props.id_data.as_pointer(), None)


def clear_save_approvals():
    _approved_owners.clear()


def apply_save_owner(base, owner):
    """Patch only the destination build Owner; preserve its unedited extra keys."""
    if owner is None:
        return
    if not isinstance(owner, dict) or any(key in PART_KEYS for key in owner):
        raise ValueError('Advanced ownership must be an Owner object.')
    from .save_editor import ship_core as core
    old = core.translate(core.get(base, 'Owner', {}))
    if not isinstance(old, dict):
        raise ValueError('The destination Owner record is not an object; nothing was written.')
    old.update(copy.deepcopy(owner))
    raw = 'BaseType' not in base
    base[core.KEYS['Owner'] if raw else 'Owner'] = core.translate(old, False) if raw else old


def draw_save_warning(layout, props):
    owner = save_owner(props)
    if owner is not None:
        box = layout.box()
        box.alert = True
        box.label(text='Advanced: destination build ownership will be updated.', icon='ERROR')
        box.label(text='Owner: ' + str(owner.get('USN') or owner.get('UID') or '(unnamed)'))


def save_target_signature(context, pinned=False):
    """Invalidate an ownership export review when the chosen base changes."""
    manager = context.scene.nms_save_data
    identifier = (manager.get_pinned_base_identifiers() if pinned
                  else manager.get_current_base_identifiers())
    if identifier is None:
        raise ValueError('Choose an export destination before reviewing ownership.')
    values = [getattr(identifier, key, None) for key in
              ('base_index', 'base_name', 'base_type', 'user_data', 'galactic_address', 'save_context')]
    links = (getattr(identifier, 'save_slot', []) if pinned
             else (manager.get_current_slot_data() or {}).get('saves', []))
    props = context.scene.nms_base_tool
    return encode([context.scene.as_pointer(), props.string_base, save_owner(props),
                   values, [str(link) for link in links]])


def draw_name(layout, props, text='', **kwargs):
    row = layout.row(align=True)
    row.prop(props, 'string_base', text=text, **kwargs)
    row.operator('bbe.build_metadata', text='', icon='PREFERENCES')
    return row


def package_metadata(data):
    return {'format': 'bbe-build-metadata', 'version': 1, 'metadata': wrapper(data)}


def read_package_metadata(value):
    if (not isinstance(value, dict) or value.get('format') != 'bbe-build-metadata'
            or value.get('version') != 1 or not isinstance(value.get('metadata'), dict)):
        raise ValueError('Unsupported BBE build metadata in ship package')
    return wrapper(value['metadata'])


def export_package_metadata(props, source):
    """Keep template/save metadata unless the project supplied or edited it."""
    result = wrapper(source.document)
    current = props.serialise()
    authored = json.loads(props.metadata_source_json) if props.metadata_source_json else {}
    baseline = json.loads(props.metadata_baseline_json) if props.metadata_baseline_json else {}
    for key, value in current.items():
        if key in authored or key not in result or value != baseline.get(key, value):
            result[key] = copy.deepcopy(value)
    return result


def ownership_sources(root):
    """Read unambiguous Corvette owners, including blank names, without mutations."""
    from .save_editor import ship_core as core
    result = {}
    for context in core.contexts(root):
        ships = core.ships(root, context)
        bases = core.get(core.player(root, context), 'PersistentPlayerBases', [])
        counts = {}
        for base in bases:
            if core.kind(base) == 'PlayerShipBase':
                index = core.get(base, 'UserData')
                if type(index) is int:
                    counts[index] = counts.get(index, 0) + 1
        for number, base in enumerate(bases):
            index = core.get(base, 'UserData')
            if (core.kind(base) != 'PlayerShipBase' or type(index) is not int
                    or not 0 <= index < len(ships) or counts.get(index) != 1
                    or not core.corvette(ships[index])):
                continue
            owner = core.translate(core.get(base, 'Owner'))
            if not isinstance(owner, dict) or not owner:
                continue
            name = core.get(base, 'Name') or core.get(ships[index], 'Name') or 'Unnamed Corvette'
            label = f'{context} / Ship {index + 1}: {name}'
            result[f'{context}:{number}'] = (label, copy.deepcopy(owner))
    return result


def read_ship_state(value):
    if (not isinstance(value, dict) or value.get('format') != 'bbe-ship-state'
            or value.get('version') != 1 or not isinstance(value.get('state'), dict)):
        raise ValueError('Unsupported BBE ship state in ship package')
    state = value['state']
    if 'ShipUsesLegacyColours' in state and type(state['ShipUsesLegacyColours']) is not bool:
        raise ValueError('Ship legacy-colour flag must be true or false')
    return copy.deepcopy(state)


