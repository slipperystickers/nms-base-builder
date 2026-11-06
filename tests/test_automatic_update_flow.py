"""Update decisions, archive rejection, and idle-browser suspension."""
import hashlib
import importlib.util
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace as NS
import unittest
from unittest.mock import Mock, patch
import zipfile

SOURCE = Path(__file__).resolve().parents[1]/'src/addons/no_mans_sky_base_builder/update_install.py'


class UpdateFlow(unittest.TestCase):
    def setUp(self):
        spec = importlib.util.spec_from_file_location('update_flow_test', SOURCE)
        self.u = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.u)
        self.session = tempfile.TemporaryDirectory()
        self.addCleanup(self.session.cleanup)
        self.window = NS(modal_operators=[])
        self.bpy = NS(app=NS(background=False, online_access=True, version=(5,1,2), tempdir=self.session.name,
                            is_job_running=Mock(return_value=False),
                            timers=NS(register=Mock(), is_registered=Mock(return_value=False), unregister=Mock())),
                      context=NS(mode='OBJECT', window_manager=NS(is_interface_locked=False, windows=[self.window],
                                                                 event_timer_add=Mock(), event_timer_remove=Mock())))
        p = patch.dict(sys.modules, bpy=self.bpy)
        p.start(); self.addCleanup(p.stop)
        self.client = NS(busy=False, downloaded=None, settings={'auto_check':True},
                         result={'available':True, 'version':'18.2.39'}, product='bbe', start=Mock())

    def test_checked_downloads_once(self):
        self.u.advance(self.client, 'bbe')
        self.u.advance(self.client, 'bbe')
        self.client.start.assert_called_once_with('download')

    def test_unchecked_or_offline_does_not_download(self):
        self.client.settings['auto_check'] = False
        self.u.advance(self.client, 'bbe')
        self.client.settings['auto_check'] = True
        self.bpy.app.online_access = False
        self.u.advance(self.client, 'bbe')
        self.client.start.assert_not_called()

    def test_manual_download_installs_without_auto_checked(self):
        self.client.settings['auto_check'] = False
        self.client.downloaded = 'verified.zip'
        with patch.object(self.u, 'validate_archive', return_value='verified.zip'), patch.object(self.u, 'install') as install:
            self.u.advance(self.client, 'bbe')
            callback = self.bpy.app.timers.register.call_args.args[0]
            self.assertIsNone(callback())
            install.assert_called_once_with('verified.zip', 'bbe')

    def test_transform_and_edit_mode_defer(self):
        self.client.downloaded = 'verified.zip'
        self.window.modal_operators = [NS(bl_idname='TRANSFORM_OT_translate')]
        self.u.advance(self.client, 'bbe')
        self.bpy.app.timers.register.assert_not_called()
        self.window.modal_operators = []
        self.bpy.context.mode = 'EDIT_MESH'
        self.u.advance(self.client, 'bbe')
        self.bpy.app.timers.register.assert_not_called()

    def test_pauses_background_browser_but_waits_for_its_handler_to_exit(self):
        self.client.downloaded = 'verified.zip'
        self.window.modal_operators = [NS(bl_idname='BBE_OT_sidebar_asset_grid')]
        browser = NS(_sessions={1:NS(_drag=False, _pressed=None)}, _enabled=True,
                     BBE_OT_sidebar_asset_grid=NS(is_registered=True), _close_all=Mock(), _restore=Mock())
        with patch.object(self.u, '_browser_modules', return_value=[browser]), \
             patch.object(self.u, 'validate_archive', return_value='verified.zip'), patch.object(self.u, 'install') as install:
            self.u.advance(self.client, 'bbe')
            self.assertFalse(browser._enabled)
            callback = self.bpy.app.timers.register.call_args.args[0]
            self.assertEqual(callback(), .25)
            install.assert_not_called()
            self.window.modal_operators = []
            callback()
            install.assert_called_once()
            self.assertTrue(browser._enabled)
            self.assertEqual(browser._close_all.call_count, 2)

    def test_browser_drag_is_not_interrupted(self):
        self.client.downloaded = 'verified.zip'
        browser = NS(_sessions={1:NS(_drag=True, _pressed=None)}, _enabled=True)
        with patch.object(self.u, '_browser_modules', return_value=[browser]):
            self.u.advance(self.client, 'bbe')
        self.bpy.app.timers.register.assert_not_called()

    def test_install_failure_is_visible_and_not_repeated(self):
        self.client.downloaded = 'verified.zip'
        with patch.object(self.u, 'validate_archive', return_value='verified.zip'), \
             patch.object(self.u, 'install', side_effect=RuntimeError('test failure')) as install:
            self.u.advance(self.client, 'bbe')
            self.bpy.app.timers.register.call_args.args[0]()
            self.u.advance(self.client, 'bbe')
            self.assertIn('test failure', self.client.message)
            install.assert_called_once()

    def test_cancel_unregisters_pending_install(self):
        self.client.downloaded = 'verified.zip'
        with patch.object(self.u, 'validate_archive', return_value='verified.zip'):
            self.u.advance(self.client, 'bbe')
        callback = self.u._pending
        self.bpy.app.timers.is_registered.return_value = True
        self.u.cancel_pending()
        self.bpy.app.timers.unregister.assert_called_once_with(callback)
        self.assertIsNone(self.u._pending)

    def archive(self, root, extra=None):
        path = Path(root)/'test.zip'
        with zipfile.ZipFile(path, 'w') as z:
            z.writestr('blender_manifest.toml', 'id="no_mans_sky_base_builder"\nversion="18.2.39"\nblender_version_min="4.2.0"\n')
            if extra: z.writestr(extra, 'bad')
        result = {'version':'18.2.39', 'asset':{'size':path.stat().st_size,
                  'digest':'sha256:'+hashlib.sha256(path.read_bytes()).hexdigest()}}
        return path, result

    def test_rejects_changed_bytes_and_wrong_version(self):
        with tempfile.TemporaryDirectory() as root:
            path, result = self.archive(root)
            self.u.validate_archive(path, result, 'bbe', (5,1,2))
            result['version'] = '18.2.40'
            with self.assertRaisesRegex(ValueError, 'identity'):
                self.u.validate_archive(path, result, 'bbe', (5,1,2))
            result['version'] = '18.2.39'
            data = bytearray(path.read_bytes()); data[30] ^= 1; path.write_bytes(data)
            with self.assertRaisesRegex(ValueError, 'checksum'):
                self.u.validate_archive(path, result, 'bbe', (5,1,2))

    def test_rejects_path_traversal_and_incompatible_blender(self):
        with tempfile.TemporaryDirectory() as root:
            path, result = self.archive(root, '../outside.py')
            with self.assertRaisesRegex(ValueError, 'Unsafe'):
                self.u.validate_archive(path, result, 'bbe', (5,1,2))
            path, result = self.archive(root)
            with self.assertRaisesRegex(ValueError, 'requires Blender'):
                self.u.validate_archive(path, result, 'bbe', (3,6,0))

    def test_blender_finished_does_not_mask_failed_file_replacement(self):
        with tempfile.TemporaryDirectory() as root:
            path, _ = self.archive(root)
            installed = Path(root)/'installed'; installed.mkdir()
            package = 'bl_ext.test.no_mans_sky_base_builder'
            module = NS(__file__=str(installed/'__init__.py'), _core_registered=True)
            self.bpy.ops = NS(extensions=NS(package_install_files=Mock(return_value={'FINISHED'})),
                              wm=NS(save_userpref=Mock()))
            with patch.dict(sys.modules, {package:module}):
                with self.assertRaisesRegex(RuntimeError, 'did not replace'):
                    self.u.install(str(path), package)
                self.bpy.ops.wm.save_userpref.assert_not_called()
                with zipfile.ZipFile(path) as z:
                    (installed/'blender_manifest.toml').write_bytes(z.read('blender_manifest.toml'))
                self.u.install(str(path), package)
                self.bpy.ops.wm.save_userpref.assert_called_once()

    def test_missing_cookie_stops_before_blender_disables_addon(self):
        self.bpy.app.tempdir = str(Path(self.session.name)/'missing-session')
        installer = Mock()
        self.bpy.ops = NS(extensions=NS(package_install_files=installer))
        with self.assertRaisesRegex(RuntimeError, 'temporary session folder is missing'):
            self.u.install('verified.zip', 'bl_ext.test.no_mans_sky_base_builder')
        installer.assert_not_called()

    def test_unwritable_cookie_stops_before_blender_disables_addon(self):
        installer = Mock()
        self.bpy.ops = NS(extensions=NS(package_install_files=installer))
        with patch('tempfile.TemporaryFile', side_effect=PermissionError('Access denied')):
            with self.assertRaisesRegex(RuntimeError, 'cannot write'):
                self.u.install('verified.zip', 'bl_ext.test.no_mans_sky_base_builder')
        installer.assert_not_called()

if __name__ == '__main__':
    unittest.main()
