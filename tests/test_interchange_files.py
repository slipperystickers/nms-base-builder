"""Standalone file interchange checks; never writes game saves."""
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest
import zipfile
import sys
import types

MODULE = Path(__file__).parents[1] / 'src/addons/no_mans_sky_base_builder/interchange.py'
package = types.ModuleType('bbe_interchange_test')
package.__path__ = [str(MODULE.parent)]
sys.modules[package.__name__] = package
spec = importlib.util.spec_from_file_location('bbe_interchange_test.interchange', MODULE)
interchange = importlib.util.module_from_spec(spec)
spec.loader.exec_module(interchange)


class FileInterchangeTests(unittest.TestCase):
    def test_missing_or_invalid_base_type_uses_selected_fallback(self):
        for metadata in (None, '', {}, {'PersistentBaseTypes': ''},
                         {'PersistentBaseTypes': None}, {'PersistentBaseTypes': []},
                         {'PersistentBaseTypes': 'UnknownType'}, []):
            original = {'BaseType': metadata, 'Name': '',
                        'Objects': [{'ObjectID': '^A'}], 'Extra': {'keep': 42}}
            for extension in ('.txt', '.json', '.nmsbase', '.nmsprefab'):
                source = interchange.BuildFile.from_bytes(json.dumps(original).encode(), extension)
                result = source.import_document('FreighterBase', 'Shared Build')
                self.assertEqual(result['BaseType']['PersistentBaseTypes'], 'FreighterBase')
                self.assertEqual(result['Name'], 'Shared Build')
                self.assertEqual(result['Objects'], original['Objects'])
                self.assertEqual(result['Extra'], original['Extra'])
                self.assertEqual(source.document, original)

    def test_valid_base_type_wins_over_fallback(self):
        for base_type in interchange.BASE_TYPES:
            for metadata in (base_type, {'PersistentBaseTypes': base_type, 'Future': 1}):
                source = interchange.BuildFile.from_bytes(json.dumps({
                    'BaseType': metadata, 'Objects': []}).encode(), '.txt')
                result = source.import_document('HomePlanetBase')
                self.assertEqual(result['BaseType']['PersistentBaseTypes'], base_type)
                if isinstance(metadata, dict):
                    self.assertEqual(result['BaseType']['Future'], 1)

    def test_unassigned_design_and_raw_part_list(self):
        parts = [{'ObjectID': '^A'}]
        for document in (parts, {'Objects': parts}, {'Prefab': parts}):
            source = interchange.BuildFile.from_bytes(json.dumps(document).encode(), '.txt')
            self.assertEqual(source.kind, 'parts')
            self.assertEqual(source.import_document()['Objects'], parts)
            self.assertEqual(source.document, document)

    def test_full_base_and_station_preserve_type_and_extra_fields(self):
        for base_type in ('HomePlanetBase', 'PlayerSpaceBase', 'PlayerSpaceStationBase'):
            original = {'BaseType': {'PersistentBaseTypes': base_type},
                        'Name': 'Test', 'Owner': {'UID': 'owner'},
                        'UnknownField': {'future': 1}, 'Objects': [{'ObjectID': '^A'}]}
            source = interchange.BuildFile.from_bytes(json.dumps(original).encode(), '.nmsbase')
            scene = dict(original)
            scene['Objects'] = [{'ObjectID': '^B'}]
            merged = source.with_scene(scene)
            self.assertEqual(merged['BaseType']['PersistentBaseTypes'], base_type)
            self.assertEqual(merged['UnknownField'], {'future': 1})
            self.assertEqual(merged['Objects'][0]['ObjectID'], '^B')

    def test_fragment_and_nomnom_json(self):
        fragment = b',{"ObjectID":"^A"},{"ObjectID":"^B"}'
        self.assertEqual(len(interchange.BuildFile.from_bytes(fragment, '.nmsbase').objects), 2)
        self.assertEqual(interchange.BuildFile.from_bytes(b'{"Objects":[{"ObjectID":"^A"}]}', '.json').kind, 'parts')
        self.assertEqual(interchange.BuildFile.from_bytes(b'{"Prefab":[{"ObjectID":"^A"}]}', '.nmsprefab').objects[0]['ObjectID'], '^A')

    def test_ship_package_preserves_metadata_and_unknown_entries(self):
        path = Path(r'C:/Users/kengo/Downloads/Arcadia Jumpship.nmsship')
        if not path.is_file():
            self.skipTest('Reference package unavailable')
        source = interchange.BuildFile.read(path)
        self.assertEqual(source.kind, 'ship')
        objects = list(source.objects)
        objects.append(dict(objects[0]))
        rebuilt = interchange.BuildFile.from_bytes(source.ship_bytes(objects), '.nmsship')
        self.assertEqual(len(rebuilt.objects), len(source.objects) + 1)
        for name in source.entries:
            if name != 'objects.json':
                self.assertEqual(rebuilt.entries[name], source.entries[name])

    def test_bad_ship_rejected_before_import(self):
        stream = io.BytesIO()
        with zipfile.ZipFile(stream, 'w') as archive:
            archive.writestr('../escape', 'bad')
        with self.assertRaises(ValueError):
            interchange.BuildFile.from_bytes(stream.getvalue(), '.nmsship')

    def test_atomic_write(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'test.nmsbase'
            interchange.atomic_write(path, b'{"Objects":[]}')
            self.assertEqual(interchange.BuildFile.read(path).objects, [])


if __name__ == '__main__':
    unittest.main()
