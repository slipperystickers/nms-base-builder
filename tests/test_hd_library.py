"""Network/file failure tests independent of Blender and user's actual library."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest
import zipfile
from unittest.mock import patch

p=Path(__file__).resolve().parents[1]/'src/addons/no_mans_sky_base_builder/hd_library.py'
spec=importlib.util.spec_from_file_location('hd_library',p)
hd=importlib.util.module_from_spec(spec);spec.loader.exec_module(hd)


class LibraryTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.root=Path(self.temp.name)
        self.env=patch.dict(os.environ,BBE_ASSET_LIBRARY_ROOT=str(self.root/'persistent'))
        self.env.start();hd.CANCEL.clear()
        self.files={'assets/PIPE.blend':b'mesh','textures/shared.webp':b'texture'}
        self.zip=self.root/'hd.zip'
        self.make_zip(self.files)

    def tearDown(self):
        hd.CANCEL.clear();self.env.stop();self.temp.cleanup()

    def make_zip(self, files):
        with zipfile.ZipFile(self.zip,'w') as z:
            for name,value in files.items():z.writestr(name,value)
        self.spec={'id':'test-hd-1','content_sha256':'test-content','archives':{hd._hash(self.zip):{'prefix':''}},'files':{k:{'bytes':len(v),'sha256':hashlib.sha256(v).hexdigest()} for k,v in self.files.items()},'url':self.zip.as_uri(),'download_bytes':self.zip.stat().st_size}

    def test_install_and_addon_update_reuse(self):
        dest=hd.install_archive(self.zip,self.spec)
        self.assertEqual((dest/'assets/PIPE.blend').read_bytes(),b'mesh')
        with patch.object(hd,'specification',return_value=self.spec):
            self.assertEqual(hd.installed_root(),dest)
            with patch.object(hd,'ADDON',self.root/'new-addon-version'):
                self.assertEqual(hd.library_root(),dest)
        self.assertEqual(hd.install_archive(self.zip,self.spec),dest)

    def test_manifest_refresh_after_addon_update(self):
        addon = self.root / 'addon'
        resource = addon / 'resources/hd_library.json'
        resource.parent.mkdir(parents=True)
        resource.write_text(json.dumps({'id': 'previous'}))
        with patch.object(hd, 'ADDON', addon):
            self.assertEqual(hd.specification()['id'], 'previous')
            resource.write_text(json.dumps({'id': 'updated-manifest'}))
            self.assertEqual(hd.specification()['id'], 'updated-manifest')

    def test_compatible_additions_remain_visible_until_update_installed(self):
        old_root = hd.install_archive(self.zip, self.spec)
        new_spec = dict(self.spec, id='updated-additions', content_sha256='updated-content',
                        compatible_previous=[self.spec])
        with patch.object(hd, 'additions_specification', return_value=new_spec), \
                patch.object(hd, 'ADDON', self.root / 'empty-addon'):
            self.assertEqual(hd.additions_root(), old_root)
            self.assertIsNone(hd.additions_root(allow_previous=False))
            with patch.object(hd, 'available', return_value=True), \
                    patch.object(hd, 'scenes_root', return_value=old_root), \
                    patch.object(hd, 'characters_root', return_value=old_root):
                self.assertEqual(hd.pending_specs(), [new_spec])
                self.assertFalse(hd.ready())
            new_root = hd.install_archive(self.zip, new_spec)
            self.assertEqual(hd.additions_root(), new_root)
            self.assertEqual(hd.additions_root(allow_previous=False), new_root)

    def test_unverified_or_removing_previous_additions_are_rejected(self):
        old_root = hd.install_archive(self.zip, self.spec)
        new_spec = dict(self.spec, id='updated-additions', content_sha256='updated-content',
                        compatible_previous=[self.spec])
        with patch.object(hd, 'additions_specification', return_value=new_spec), \
                patch.object(hd, 'ADDON', self.root / 'empty-addon'):
            for receipt in ({'id': self.spec['id'], 'content_sha256': 'wrong'},
                            dict(self.spec, removing=True)):
                (old_root / 'installed.json').write_text(json.dumps(receipt))
                self.assertIsNone(hd.additions_root())

    def test_remove_hd_also_removes_compatible_fallback(self):
        old_root = hd.install_archive(self.zip, self.spec)
        main_spec = dict(self.spec, id='main-library', content_sha256='main-content')
        main_root = hd.install_archive(self.zip, main_spec)
        new_spec = dict(self.spec, id='updated-additions', content_sha256='updated-content',
                        compatible_previous=[self.spec])
        unrelated = hd.storage() / 'unrelated'
        unrelated.mkdir()
        with patch.object(hd, 'specification', return_value=main_spec), \
                patch.object(hd, 'additions_specification', return_value=new_spec):
            hd.remove_installed(main_root)
        self.assertFalse(old_root.exists())
        self.assertFalse(main_root.exists())
        self.assertTrue(unrelated.exists())


    def test_bad_archive_hash(self):
        self.zip.write_bytes(b'wrong download')
        with self.assertRaisesRegex(ValueError,'verified HD'):hd.install_archive(self.zip,self.spec)
        self.assertFalse((hd.storage()/self.spec['id']).exists())

    def test_per_file_corruption_never_publishes(self):
        self.spec['files']['assets/PIPE.blend']['sha256']='bad'
        with self.assertRaisesRegex(ValueError,'Checksum mismatch'):hd.install_archive(self.zip,self.spec)
        self.assertEqual(list(hd.storage().iterdir()),[])

    def test_cancel_keeps_previous_library(self):
        dest=hd.install_archive(self.zip,self.spec)
        hd.CANCEL.set()
        with self.assertRaises(InterruptedError):hd.install_archive(self.zip,self.spec)
        self.assertEqual((dest/'assets/PIPE.blend').read_bytes(),b'mesh')
        self.assertEqual([p.name for p in hd.storage().iterdir()],['test-hd-1'])

    def test_unsafe_zip_path(self):
        self.make_zip(dict(self.files,**{'../escape':b'unsafe'}))
        with self.assertRaisesRegex(ValueError,'Unsafe path'):hd.install_archive(self.zip,self.spec)
        self.assertFalse((self.root/'escape').exists())

    def test_download_verify_install_cleanup(self):
        dest=hd.download_and_install(self.spec)
        self.assertTrue((dest/'installed.json').exists())
        self.assertEqual([p.name for p in hd.storage().iterdir()],['test-hd-1'])

    def test_progress_moves_forward_through_all_phases(self):
        class RecordedState(dict):
            def update(state, **values):
                super().update(values)
                samples.append(dict(state))
        samples = []
        with patch.object(hd, 'STATE', RecordedState(hd.STATE)):
            hd.download_and_install(self.spec)
        values = [s['progress'] for s in samples]
        self.assertEqual(values, sorted(values))
        self.assertEqual(values[-1], 1.0)
        for phase in ['Downloading:', 'Checking download:', 'Installing models:']:
            self.assertTrue(any(s['message'].startswith(phase) for s in samples), phase)

    def test_cancellation_interrupts_checksum_verification(self):
        hd.CANCEL.set()
        with self.assertRaises(InterruptedError):
            hd.install_archive(self.zip, self.spec)
        self.assertFalse((hd.storage() / self.spec['id']).exists())

    def test_truncated_download_preserves_previous(self):
        dest=hd.install_archive(self.zip,self.spec)
        self.zip.write_bytes(b'truncated')
        with self.assertRaises(ValueError):hd.download_and_install(self.spec)
        self.assertTrue((dest/'installed.json').exists())

    def test_wrong_library_rejected(self):
        dest=hd.install_archive(self.zip,self.spec)
        other=dict(self.spec,content_sha256='another-library')
        with patch.object(hd,'specification',return_value=other):self.assertIsNone(hd.installed_root())

    def test_remove_only_downloaded_pack_then_reinstall(self):
        root = hd.install_archive(self.zip, self.spec)
        sibling = hd.storage() / 'other-pack'
        sibling.mkdir()
        (sibling / 'keep.txt').write_text('keep')
        with patch.object(hd, 'specification', return_value=self.spec):
            self.assertEqual(hd.removable_root(), root)
            with self.assertRaises(ValueError): hd.remove_installed(sibling)
            hd.remove_installed(root)
            self.assertIsNone(hd.installed_root())
            self.assertIsNone(hd.removable_root())
            self.assertTrue((sibling / 'keep.txt').exists())
            self.assertEqual(hd.install_archive(self.zip, self.spec), root)

    def test_extra_files_prevent_removal(self):
        root = hd.install_archive(self.zip, self.spec)
        (root / 'my-work.blend').write_bytes(b'keep')
        with patch.object(hd, 'specification', return_value=self.spec):
            with self.assertRaisesRegex(ValueError, 'extra files'): hd.remove_installed(root)
            self.assertEqual(hd.installed_root(), root)
        self.assertTrue((root / 'my-work.blend').exists())

    def test_busy_and_partial_removal_are_safe_and_retryable(self):
        root = hd.install_archive(self.zip, self.spec)
        with patch.object(hd, 'specification', return_value=self.spec):
            with patch.dict(hd.STATE, busy=True):
                self.assertIsNone(hd.removable_root())
                with self.assertRaises(ValueError): hd.remove_installed(root)
            def locked(path):
                (path / 'assets/PIPE.blend').unlink()
                raise PermissionError('locked texture')
            with patch.object(hd.shutil, 'rmtree', side_effect=locked):
                with self.assertRaises(PermissionError): hd.remove_installed(root)
            self.assertIsNone(hd.installed_root())
            self.assertEqual(hd.removable_root(), root)
            hd.remove_installed(root)
            self.assertFalse(root.exists())


if __name__=='__main__':unittest.main(verbosity=2)
