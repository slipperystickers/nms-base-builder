"""Exercise startup/reinstall HD updates without touching the user's library."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from test_support import module, report
import bpy
import contextlib
import hashlib
import json
import os
import tempfile
import time
import unittest
import zipfile
from types import SimpleNamespace
from unittest.mock import patch

hd = module('hd_library')
ui = module('hd_library_ui')
update = module('update_install')


class AutoUpdateTests(unittest.TestCase):
    def setUp(self):
        self.stack = contextlib.ExitStack()
        self.addCleanup(self.stack.close)
        self.root = Path(self.stack.enter_context(tempfile.TemporaryDirectory()))
        self.stack.enter_context(patch.dict(os.environ, BBE_ASSET_LIBRARY_ROOT=str(self.root / 'packs')))
        self.stack.enter_context(patch.object(hd, 'ADDON', self.root / 'reinstalled-addon'))
        self.stack.enter_context(patch.object(hd, 'STATE', dict(busy=False, result=None, error='', message='')))
        self.stack.enter_context(patch.object(ui, '_auto_update_attempts', set()))
        self.stack.enter_context(patch.object(ui, '_auto_update_active', False))
        self.stack.enter_context(patch.object(ui, '_pending_scene', None))
        self.app = SimpleNamespace(background=False, online_access=True)
        self.stack.enter_context(patch.object(ui, 'bpy', SimpleNamespace(
            app=self.app, data=bpy.data, context=bpy.context, ops=bpy.ops)))
        ui.reset_update_check()
        hd.CANCEL.clear()
        self.addCleanup(hd.CANCEL.clear)
        self.specs = [self.pack('hd-' + name) for name in ['base', 'scenes', 'additions-new', 'characters']]
        for function, spec in zip(['specification', 'scenes_specification', 'additions_specification',
                                   'characters_specification'], self.specs):
            self.stack.enter_context(patch.object(hd, function, return_value=spec))
        self.old = self.pack('hd-additions-old')
        self.specs[2]['compatible_previous'] = [self.old]
        self.downloads = self.stack.enter_context(patch.object(hd, 'download_and_install', wraps=hd.download_and_install))

    def pack(self, name):
        files = {'assets/' + name + '.blend': name.encode(), 'textures/' + name + '.webp': b'texture'}
        archive = self.root / (name + '.zip')
        with zipfile.ZipFile(archive, 'w') as z:
            for filename, value in files.items():
                z.writestr(filename, value)
        return dict(id=name, content_sha256=hashlib.sha256(name.encode()).hexdigest(),
                    archives={hd._hash(archive): {'prefix': ''}}, url=archive.as_uri(),
                    download_bytes=archive.stat().st_size,
                    files={k: dict(bytes=len(v), sha256=hashlib.sha256(v).hexdigest()) for k, v in files.items()})

    def install(self, spec):
        return hd.install_archive(self.root / (spec['id'] + '.zip'), spec)

    def owner(self):
        for spec in [self.specs[0], self.specs[1], self.old, self.specs[3]]:
            self.install(spec)

    def wait(self):
        deadline = time.monotonic() + 15
        while hd.STATE['busy'] and time.monotonic() < deadline:
            time.sleep(.01)
        self.assertFalse(hd.STATE['busy'], 'Worker did not finish')

    def test_reinstall_with_old_pack_downloads_only_updated_content(self):
        self.owner()
        bpy.context.scene.bbe_detailed_proxies = False
        self.assertFalse(hd.ready())
        self.assertTrue(ui.check_installed_updates())
        self.wait()
        self.assertEqual(hd.STATE['result'], 'installed', hd.STATE)
        self.assertTrue(hd.ready())
        self.assertEqual([c.args[0]['id'] for c in self.downloads.call_args_list], ['hd-additions-new'])
        self.assertTrue((hd.storage() / self.old['id'] / 'installed.json').is_file())
        self.assertFalse(bpy.context.scene.bbe_detailed_proxies)
        self.assertFalse(ui.check_installed_updates())

    def test_historical_core_owner_gets_all_missing_components(self):
        self.install(self.pack('hd-retired-base'))
        self.assertFalse(hd.available())
        self.assertTrue(ui.check_installed_updates())
        self.wait()
        self.assertTrue(hd.ready())
        self.assertEqual(self.downloads.call_count, 4)

    def test_never_hd_user_does_not_download(self):
        self.assertFalse(ui.check_installed_updates())
        self.downloads.assert_not_called()

    def test_reenable_resets_a_previous_failed_check(self):
        self.owner()
        ui._auto_update_attempts.add(hd.content_version())
        ui._auto_update_checked = True
        ui._auto_update_version = hd.content_version()
        with patch.object(ui, 'bpy', bpy):
            ui.unregister()
            ui.register()
        self.assertTrue(ui.check_installed_updates())
        self.wait()
        self.assertTrue(hd.ready())

    def test_offline_then_online_does_not_consume_check(self):
        self.owner()
        self.app.online_access = False
        self.assertFalse(ui.check_installed_updates())
        self.app.online_access = True
        self.assertTrue(ui.check_installed_updates())
        self.wait()
        self.assertTrue(hd.ready())

    def test_failure_preserves_old_pack_without_retry_loop(self):
        self.owner()
        self.specs[2]['url'] = (self.root / 'missing.zip').as_uri()
        self.assertTrue(ui.check_installed_updates())
        self.wait()
        self.assertEqual(hd.STATE['result'], 'partial')
        self.assertTrue(hd.STATE['error'])
        self.assertFalse(hd.ready())
        self.assertEqual(hd.additions_root().name, self.old['id'])
        ui.reset_update_check()  # Loading another blend must not retry indefinitely.
        self.assertFalse(ui.check_installed_updates())

    def test_manifest_change_is_checked_again(self):
        self.owner()
        self.install(self.specs[2])
        self.assertFalse(ui.check_installed_updates())
        newer = self.pack('hd-additions-newer')
        with patch.object(hd, 'additions_specification', return_value=newer):
            self.assertTrue(ui.check_installed_updates())
            self.wait()
            self.assertTrue(hd.ready())

    def test_cancel_manual_download_does_not_restart_automatically(self):
        self.owner()
        with patch.object(hd, 'start', return_value=True):
            self.assertEqual(ui.request_download(bpy.context), {'FINISHED'})
        hd.STATE.update(result='cancelled', busy=False)
        hd.CANCEL.set()
        ui.cancel_activation()
        self.assertFalse(ui.check_installed_updates())
        self.downloads.assert_not_called()

    def test_finish_refreshes_all_hd_scenes_but_preserves_simple(self):
        simple = bpy.context.scene
        simple.bbe_detailed_proxies = False
        detail = bpy.data.scenes.new('Auto update HD scene')
        detail.bbe_detailed_proxies = True
        detail2 = bpy.data.scenes.new('Second HD scene')
        detail2.bbe_detailed_proxies = True
        try:
            ui._auto_update_active = True
            hd.STATE['result'] = 'installed'
            with patch.object(hd, 'ready', return_value=True), \
                    patch.object(update, 'wait_reason', return_value='Editing') as idle, \
                    patch.object(ui, 'relink_legacy_textures'), \
                    patch.object(ui.bpy, 'ops', SimpleNamespace(object=SimpleNamespace(
                        nms_switch_proxies_to_high=lambda: calls.append(bpy.context.scene.name) or {'FINISHED'}))):
                calls = []
                ui.finish_download()
                self.assertEqual(calls, [])
                self.assertTrue(ui._auto_update_active)
                idle.return_value = ''
                ui.finish_download()
                self.assertEqual(set(calls), {detail.name, detail2.name})
                self.assertFalse(simple.bbe_detailed_proxies)
                self.assertFalse(ui._auto_update_active)
        finally:
            bpy.data.scenes.remove(detail)
            bpy.data.scenes.remove(detail2)

    def test_corrupt_update_is_not_activated(self):
        self.owner()
        self.specs[2]['files']['assets/hd-additions-new.blend']['sha256'] = 'bad'
        self.assertTrue(ui.check_installed_updates())
        self.wait()
        with patch.object(update, 'wait_reason', return_value=''), patch.object(ui, 'relink_legacy_textures') as relink:
            ui.finish_download()
            relink.assert_not_called()
        self.assertFalse(hd.ready())
        self.assertFalse((hd.storage() / self.specs[2]['id']).exists())


result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(AutoUpdateTests))
report('hd_auto_update', dict(tests=result.testsRun, failures=len(result.failures), errors=len(result.errors)))
assert result.wasSuccessful()
