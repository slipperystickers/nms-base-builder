"""HD distribution must retain the pilot's skinning data beside its blend."""
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
import zipfile
from unittest.mock import patch

REPO = Path(__file__).resolve().parents[1]


class HDSkinningPackageTests(unittest.TestCase):
    def test_skinning_data_is_archived_and_manifested(self):
        spec = importlib.util.spec_from_file_location('hd_pack_builder_test', REPO / 'tools/build_hd_characters.py')
        builder = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(builder)
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            addon = root / 'addon'
            source = addon / 'resources/hd_additions/pilot_references'
            source.mkdir(parents=True)
            (root / 'dist').mkdir()
            (addon / 'blender_manifest.toml').write_text('version = "1.2.3"\n')
            expected = {}
            for race in ('ASTRO_DEFAULT','ASTRO_ARMOURED','GEK_DEFAULT','VYKEEN_DEFAULT',
                         'KORVAX_DEFAULT','FOURTH_DEFAULT','BUI_DEFAULT'):
                expected[f'pilot_references/{race}.blend'] = b'unchanged blend bytes'
                expected[f'pilot_references/{race}.skin.npz'] = b'native joint weights and points'
                for pose in ('STANDING','SEATED'):
                    expected[f'character_references/{pose}_{race}.blend'] = b'free reference mesh'
            for name, data in expected.items():
                path = addon / 'resources/hd_additions' / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(data)
            (source / 'ASTRO_ARMOURED.blend1').write_bytes(b'backup stays out')
            builder.ROOT, builder.ADDON = root, addon
            with patch('sys.argv', ['build_hd_characters.py', '--release-tag', 'v1.2.3']):
                builder.main()
            manifest = json.loads((addon / 'resources/hd_characters.json').read_text())
            self.assertEqual(set(manifest['files']), set(expected))
            with zipfile.ZipFile(root / 'dist/bbe-hd-characters-1.zip') as archive:
                self.assertEqual(set(archive.namelist()), set(expected))
                for name, data in expected.items():
                    self.assertEqual(archive.read(name), data)
                    self.assertEqual(manifest['files'][name], {
                        'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest(),
                    })
            generic_spec = importlib.util.spec_from_file_location('generic_hd_test', REPO / 'tools/build_hd_additions.py')
            generic = importlib.util.module_from_spec(generic_spec)
            generic_spec.loader.exec_module(generic)
            generic.ROOT, generic.ADDON = root, addon
            generic.main([])
            with zipfile.ZipFile(root / 'dist/bbe-hd-additions-1.zip') as archive:
                self.assertEqual(archive.namelist(), [], 'Character payload must not be duplicated in other packs')


if __name__ == '__main__':
    unittest.main()
