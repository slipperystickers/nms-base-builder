"""Only synthetic Steam save fixtures; never the user's live game files."""
import importlib.util
import json
import lz4.block
from pathlib import Path
import struct
import sys
import tempfile
import unittest
from unittest import mock


SOURCE = Path(__file__).resolve().parents[1] / 'src/addons/no_mans_sky_base_builder/save_editor'
sys.path.insert(0, str(SOURCE))
spec = importlib.util.spec_from_file_location('raw_json_core', SOURCE / 'raw_json_core.py')
core = importlib.util.module_from_spec(spec)
spec.loader.exec_module(core)
import steam_metadata


class RawJsonTests(unittest.TestCase):
    def test_base_labels_categories_and_original_paths(self):
        compact = core.KEY_IDS
        player = {
            compact['PlayerFreighterName']: 'My Freighter',
            compact['ShipOwnership']: [{compact['Name']: 'My Corvette'}],
            compact['PersistentPlayerBases']: [
                {compact['Name']: '', compact['BaseType']: {
                    compact['PersistentBaseTypes']: 'FreighterBase'}},
                {compact['Name']: 'Default', compact['UserData']: 0,
                 compact['BaseType']: {compact['PersistentBaseTypes']: 'PlayerShipBase'}},
                {compact['Name']: 'Garden', compact['BaseType']: {
                    compact['PersistentBaseTypes']: 'HomePlanetBase'}},
                {compact['Name']: 'Unknown record', compact['BaseType']: {
                    compact['PersistentBaseTypes']: 'UITempShipBase'}},
            ],
        }
        root = {compact['BaseContext']: {compact['PlayerStateData']: player}}
        records = core.base_records(root)
        self.assertEqual([(r['index'], r['name'], r['category']) for r in records], [
            (0, 'My Freighter', 'Freighters'),
            (1, 'My Corvette', 'Corvettes'),
            (2, 'Garden', 'Planet Bases'),
            (3, 'Unknown record', 'Other'),
        ])
        self.assertEqual(records[1]['path'], (compact['BaseContext'],
                         compact['PlayerStateData'], compact['PersistentPlayerBases'], 1))

    def test_readable_keys_round_trip_without_changing_game_ids(self):
        original = {
            'F2P': 4745,
            '<h0': {'Pk4': 'My ship', 'UnknownKey': [{'vLc': {'F2P': 1}}]},
            'Version': 'separate literal field',
        }
        shown = core.readable(original)
        self.assertEqual(shown['CommonStateData']['SaveName'], 'My ship')
        self.assertIn('Version [raw:Version]', shown)
        self.assertEqual(core.restore_keys(shown, original), original)
        shown['CommonStateData']['SaveName'] = 'Changed name'
        restored = core.restore_keys(shown, original)
        self.assertEqual(restored['<h0']['Pk4'], 'Changed name')
        self.assertEqual(restored['F2P'], 4745)
        self.assertEqual(restored['Version'], 'separate literal field')

    def test_strict_json_and_codec(self):
        root = {'Hello': '世界', 'List': [1, {'x': True}], 'Large': 'A' * 600000}
        encoded, length = core.encode(root)
        self.assertGreater(length, 600000)
        self.assertEqual(core.decode(encoded), root)
        with self.assertRaisesRegex(ValueError, 'Duplicate'):
            core.strict_json('{"a":1,"a":2}')
        with self.assertRaises(ValueError):
            core.strict_json('{"a":NaN}')
        # Real HG saves can contain isolated non-UTF-8 bytes in JSON strings.
        # Display them as escapes while retaining the original bytes on write.
        payload = b'{"Text":"before\xbfafter","A":1}\x00'
        packed = lz4.block.compress(payload, store_size=False)
        raw = struct.pack('<IIII', core.MAGIC, len(packed), len(payload), 0) + packed
        decoded = core.decode(raw)
        self.assertEqual(decoded['Text'], 'before\udcbfafter')
        self.assertEqual(core.decode(core.encode(decoded)[0]), decoded)

    def test_commit_backup_metadata_and_stale_refusal(self):
        with tempfile.TemporaryDirectory() as directory, mock.patch.object(core, 'game_running', return_value=False):
            folder = Path(directory)
            path = folder / 'save.hg'
            original = {'BaseContext': {'PlayerStateData': {'Units': 12}}, 'Other': [1, 2]}
            path.write_bytes(core.encode(original)[0])
            plain = bytearray(384)
            struct.pack_into('<I', plain, 0, 0xeeeeeebe)
            metadata = folder / 'mf_save.hg'
            metadata.write_bytes(steam_metadata.crypt(plain, steam_metadata.storage_number(metadata.name)))
            before = {p.name: p.read_bytes() for p in (path, metadata)}
            root, hashes, stats = core.read(path)
            self.assertFalse(core.changed(hashes, stats))
            root['BaseContext']['PlayerStateData']['Units'] = 99
            backup = Path(core.commit(path, root, hashes, folder / 'backups'))
            self.assertEqual(core.decode(path.read_bytes()), root)
            self.assertEqual({p.name: (backup / p.name).read_bytes() for p in (path, metadata)}, before)
            self.assertEqual(json.loads((backup / '.bbe-backup.json').read_text())['reason'], 'raw-json')
            updated, expected, _ = core.read(path)
            self.assertEqual(updated, root)
            old_stat = path.stat()
            alternate = {'BaseContext': {'PlayerStateData': {'Units': 98}}, 'Other': [1, 2]}
            path.write_bytes(core.encode(alternate)[0])
            # Matching timestamps and size are not proof of unchanged content.
            import os
            os.utime(path, ns=(old_stat.st_atime_ns, old_stat.st_mtime_ns))
            self.assertEqual(path.stat().st_size, old_stat.st_size)
            self.assertTrue(core.changed(expected))
            with self.assertRaisesRegex(ValueError, 'changed'):
                core.commit(path, root, expected, folder / 'backups')
            self.assertEqual(core.decode(path.read_bytes()), alternate)

    def test_running_game_blocks_open_and_save(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'save.hg'
            path.write_bytes(core.encode({'A': 1})[0])
            with mock.patch.object(core, 'game_running', return_value=True):
                with self.assertRaisesRegex(RuntimeError, 'running'):
                    core.read(path)
                with self.assertRaisesRegex(RuntimeError, 'running'):
                    core.commit(path, {'A': 2}, {}, Path(directory) / 'backups')


if __name__ == '__main__':
    unittest.main()
