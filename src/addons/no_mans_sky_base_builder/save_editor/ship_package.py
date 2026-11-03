"""Capture a selected save Corvette as a standalone, self-contained package."""
import io
import json
import zipfile
from . import ship_core as core, ship_repair
from ..interchange import BuildFile, _encode
from .. import build_metadata


def new_corvette_source():
    """Supply ship records for a new design; template build parts never enter it."""
    template = json.loads((core.RES / 'minimal_corvette.json').read_text(encoding='utf8'))
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
        for name, value in (('objects.json', []), ('so.json', template['ship']),
                            ('ccd.json', template['custom'])):
            archive.writestr(name, _encode(value))
    return BuildFile.from_bytes(stream.getvalue(), '.nmsship')


def from_save(root, context, base_index):
    bases = core.get(core.player(root, context), 'PersistentPlayerBases', [])
    if type(base_index) is not int or not 0 <= base_index < len(bases):
        raise ValueError('The selected build no longer exists. Refresh the save list.')
    base = bases[base_index]
    if core.kind(base) != 'PlayerShipBase':
        raise ValueError('The selected build is not a Corvette.')
    index = core.get(base, 'UserData')
    if type(index) is not int or not 0 <= index < 12:
        raise ValueError('This build has no valid ship slot. Review its link in Ship Management.')
    issues = ship_repair.inspect_slots(root, context, include_warnings=False)[0][index]
    if issues:
        raise ValueError(' '.join(issues) + ' Use Repair Corvette in I/O.')
    if ship_repair.linked_builds(root, context, index) != [base_index]:
        raise ValueError('The selected build does not have one unambiguous ship link.')
    ship = core.translate(core.ships(root, context)[index])
    objects = core.translate(core.get(base, 'Objects', []))
    custom = core.get(core.player(root, context), 'CharacterCustomisationData', [])
    slot = core.CUSTOM_SLOTS[index]
    if not isinstance(custom, list) or len(custom) <= slot or not isinstance(custom[slot], dict):
        raise ValueError('The saved ship appearance is unavailable; choose a complete .nmsship template.')
    appearance = core.translate(custom[slot])
    legacy = core.get(core.player(root, context), 'ShipUsesLegacyColours', [])
    state = {}
    if isinstance(legacy, list) and len(legacy) > index and type(legacy[index]) is bool:
        state['ShipUsesLegacyColours'] = legacy[index]
    ship_repair.validate_payload(dict(ship=ship, objects=objects, custom=appearance), 'FULL')
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
        for name, value in (('objects.json', objects), ('so.json', ship), ('ccd.json', appearance),
                            (build_metadata.PACKAGE_ENTRY, build_metadata.package_metadata(core.translate(base)))):
            archive.writestr(name, _encode(value))
        if state:
            archive.writestr(build_metadata.SHIP_STATE_ENTRY, _encode(
                {'format': 'bbe-ship-state', 'version': 1, 'state': state}))
    return BuildFile.from_bytes(stream.getvalue(), '.nmsship')


def selected_save_source(context):
    """An explicit exporter choice; never silently borrow another selected ship."""
    from pathlib import Path
    from . import ship_files
    data = context.scene.nms_save_data
    selected = data.get_current_base_identifiers()
    if selected is None or selected.base_type != 'PlayerShipBase':
        raise ValueError('Select the original Corvette in I/O before using its ship metadata.')
    links = list(dict.fromkeys(str(Path(p)) for p in data.get_current_slot_data()['saves'] if p and Path(p).exists()))
    root, hashes, source = ship_files.read(links)
    cache = data.extracted_base_data
    if str(source) != cache.get('source_path') or hashes[str(source)] != cache.get('source_hash'):
        raise ValueError('The save changed. Refresh the save list and select the original Corvette again.')
    return from_save(root, selected.save_context, selected.base_index)
