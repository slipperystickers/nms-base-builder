"""Verified, backed-up write of an optimized Corvette to its selected save slot."""
import copy
from pathlib import Path
import time

from .save_editor_utils import BaseData, BaseType, get_lastes_save_file_location
from .save_translation import SaveTranslation as K, translate_to_obf_data


def replace_file(source, target):
    # Antivirus/sync clients can briefly hold a newly written Windows file.
    for delay in (.05, .15, .35):
        try:
            source.replace(target)
            return
        except PermissionError:
            time.sleep(delay)
    source.replace(target)


def export(objects, identifier, links, base_name=None, progress=None, owner_override=None, selected_source=None):
    from .save_file import SaveFile
    from . import ship_files, ship_repair, ship_core
    if identifier.base_type != BaseType.CORVETTE:
        raise ValueError('Optimize & Export is only available for Corvettes')
    paths = list(dict.fromkeys(Path(p).resolve() for p in links if p))
    if not paths:
        raise ValueError('No save files selected')
    if progress:
        progress.update(.18, 'Preparing save files')
    expected = ship_files.export_hashes(paths)
    if selected_source is not None:
        latest = str(get_lastes_save_file_location(paths))
        if latest != selected_source.get('source_path') or expected[latest] != selected_source.get('source_hash'):
            raise ValueError('The save changed. Refresh the save list before exporting.')
    roots = {}
    # Resolve every destination before touching any save file. Keep each save
    # point's own unrelated progress rather than cloning the newest root.
    for index, path in enumerate(paths):
        if progress:
            progress.update(.20 + .34 * index / len(paths), f'Loading {path.name}')
        save = SaveFile(path)
        save.load()
        save.context = getattr(identifier, 'save_context', None) or ship_core.get(save.json_data, 'ActiveContext')
        index = identifier.user_data
        if type(index) is not int or not 0 <= index < 12:
            raise ValueError('Select a linked Corvette before exporting.')
        records = ship_repair.linked_builds(save.json_data, save.context, index)
        if len(records) != 1:
            raise ValueError(f'Could not identify a single Corvette in ship slot {index + 1} in {path.name}. Review the destination in Export to Save.')
        position = records[0]
        base = save.get_bases_list_pointer()[position]
        ship_repair.require_objects_destination(save.json_data, save.context, base)
        matched = BaseData(position, base, save.get_ship_ownership_pointer())
        if matched.base_name != identifier.base_name:
            raise ValueError(f'The Corvette in {path.name} has a different name. Review the destination in Export to Save.')
        base[K.objects] = translate_to_obf_data(copy.deepcopy(objects))
        from ..build_metadata import apply_save_owner
        apply_save_owner(base, owner_override)
        if base_name:
            ownership = save.get_ship_ownsership_element(int(identifier.user_data))
            if ownership is None:
                raise ValueError(f'Corvette ownership not found in {path.name}')
            base[K.base_name] = base_name
            ownership[K.base_name] = base_name
        roots[path] = save.json_data
    return ship_files.commit_roots(roots, expected, progress=progress)
