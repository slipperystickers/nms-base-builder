"""Exercise actual export writers on disposable Steam saves, never live saves."""
import copy
import json
import os
from pathlib import Path
import struct
import sys
import tempfile
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_support import module, QA, report

files = module('save_editor.ship_files')
optimizer = module('save_editor.optimizer_export')
utils = module('save_editor.save_editor_utils')
core = module('save_editor.ship_core')
meta = module('save_editor.steam_metadata')
T = json.loads((core.RES / 'minimal_corvette.json').read_text())
OLD_TIME = 1700000000


def fixture(path, marker):
    ship = copy.deepcopy(T['ship']); ship['Name'] = 'Metadata QA'
    base = copy.deepcopy(T['base']); base.update(UserData=0, Name='Metadata QA')
    root = core.translate(dict(
        ActiveContext='Main', CommonStateData={'SaveName': marker},
        BaseContext={'PlayerStateData': {
            'ShipOwnership': [ship] + [copy.deepcopy(T['empty']) for _ in range(11)],
            'PersistentPlayerBases': [base], 'PrimaryShip': 0,
            'CharacterCustomisationData': [copy.deepcopy(T['custom']) for _ in range(23)],
        }}), False)
    save = files.SaveFile(path); save.json_data = root; save.save()
    plain = bytearray(432)
    struct.pack_into('<I', plain, 0, 0xeeeeeebe)
    struct.pack_into('<I', plain, 56, len(json.dumps(root, separators=(',', ':'), ensure_ascii=False).encode()) + 1)
    struct.pack_into('<I', plain, 60, path.stat().st_size)
    struct.pack_into('<Q', plain, 348, 0x0123456789ABCDEF)
    struct.pack_into('<I', plain, 356, OLD_TIME)
    plain[400:417] = b'preserve-unknown!'
    companion = path.with_name('mf_' + path.name)
    companion.write_bytes(meta.crypt(plain, meta.storage_number(path.name)))
    for p in (path, companion): os.utime(p, (OLD_TIME, OLD_TIME))
    identifier = utils.BaseData(0, save.get_bases_list_pointer()[0], save.get_ship_ownership_pointer())
    identifier.save_context = 'Main'
    return root, identifier


def inspect(path):
    companion = path.with_name('mf_' + path.name)
    plain = meta.decode(companion.read_bytes(), path.name)
    root = files.SaveFile(path).load()
    assert struct.unpack_from('<Q', plain, 348)[0] == 0x0123456789ABCDEF
    assert plain[400:417] == b'preserve-unknown!'
    stamp = struct.unpack_from('<I', plain, 356)[0]
    size = struct.unpack_from('<I', plain, 60)[0]
    raw_size = struct.unpack_from('<I', plain, 56)[0]
    return dict(file=path.name, size_matches=size == path.stat().st_size,
                raw_size_matches=raw_size == len(json.dumps(root, separators=(',', ':'), ensure_ascii=False).encode()) + 1,
                timestamp_updated=stamp > OLD_TIME,
                timestamps_equal=stamp == path.stat().st_mtime == companion.stat().st_mtime,
                metadata_timestamp=stamp, data_mtime=path.stat().st_mtime,
                metadata_mtime=companion.stat().st_mtime)


results = []
with tempfile.TemporaryDirectory(prefix='metadata-qa-', dir=QA / 'tmp') as folder:
    folder = Path(folder)
    with patch.object(files.backup_policy, 'settings', return_value=(str(folder / 'backups'), 100)):
        for route in ('corvette', 'pinned_optimizer', 'base_export', 'planet_base_export'):
            paths = [folder / 'save9.hg', folder / 'save10.hg']
            root, ident = fixture(paths[0], 'first')
            fixture(paths[1], 'second')
            if route == 'planet_base_export':
                for path in paths:
                    save = files.SaveFile(path); save.load()
                    base = save.get_bases_list_pointer()[0]
                    base[utils.SaveTranslation.base_type][utils.SaveTranslation.persistent_base_types] = utils.BaseType.BASE
                    save.save()
                    ident = utils.BaseData(0, base); ident.save_context = 'Main'
            objects = copy.deepcopy(T['base']['Objects']) * 7
            if route == 'corvette':
                watched = paths + [p.with_name('mf_' + p.name) for p in paths]
                core.get(core.player(root, 'Main'), 'PersistentPlayerBases')[0][utils.SaveTranslation.objects] = core.translate(objects, False)
                files.commit(root, paths, files.hashes(watched))
            elif route == 'pinned_optimizer':
                optimizer.export(objects, ident, paths)
            else:
                utils.save_base_to_save_file(objects, ident, paths)
            results.append(dict(route=route, checks=[inspect(p) for p in paths]))
            if route != 'corvette':
                # Updating both save points must not copy unrelated progress between them.
                for p, marker in zip(paths, ('first', 'second')):
                    assert core.get(core.get(files.SaveFile(p).load(), 'CommonStateData'), 'SaveName') == marker

        # A late failure must restore BOTH save points and their metadata,
        # including the original timestamps used in cross-save comparison.
        roots = {p: fixture(p, p.name)[0] for p in paths}
        watched = paths + [p.with_name('mf_' + p.name) for p in paths]
        before = {p: (p.read_bytes(), p.stat().st_mtime_ns) for p in watched}
        real_replace = files.replace_file
        calls = []
        def fail_fourth(src, dst):
            calls.append(dst)
            if len(calls) == 4:
                raise OSError('Injected metadata publication failure')
            return real_replace(src, dst)
        with patch.object(files, 'replace_file', side_effect=fail_fourth):
            try: files.commit_roots(roots, files.export_hashes(paths))
            except OSError: pass
            else: raise AssertionError('Write failure was not injected')
        assert before == {p: (p.read_bytes(), p.stat().st_mtime_ns) for p in watched}

        # An external metadata edit during preparation aborts publication.
        expected = files.export_hashes(paths)
        snapshot = files.backup_policy.snapshot
        companion = watched[-1]
        def change_after_backup(*args, **kwargs):
            result = snapshot(*args, **kwargs)
            companion.write_bytes(companion.read_bytes() + b'external-change')
            return result
        with patch.object(files.backup_policy, 'snapshot', side_effect=change_after_backup):
            try: files.commit_roots(roots, expected)
            except ValueError as exc: assert 'changed during preparation' in str(exc)
            else: raise AssertionError('Concurrent metadata change accepted')
        for p in paths:
            assert (p.read_bytes(), p.stat().st_mtime_ns) == before[p]
        assert companion.read_bytes().endswith(b'external-change')
        assert not list(folder.glob('.bbe-*')), 'Staging files left behind'

report('export_metadata', results)
report('export_metadata_guards', dict(rollback_bytes_and_timestamps=True, concurrent_metadata_rejected=True))
if '--audit' not in sys.argv:
    assert all(all(c[key] for key in ('size_matches', 'raw_size_matches', 'timestamp_updated', 'timestamps_equal'))
               for r in results for c in r['checks']), results

