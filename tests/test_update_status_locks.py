"""Progress-file sharing locks must never abort the verified ZIP download."""
import ctypes
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

SOURCE = Path(__file__).resolve().parents[1] / 'src/addons/no_mans_sky_base_builder/furby_updates.py'
spec = importlib.util.spec_from_file_location('status_updates', SOURCE)
u = importlib.util.module_from_spec(spec)
spec.loader.exec_module(u)


class StatusLocks(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)

    def test_transient_result_lock_retries(self):
        replace = u.os.replace
        attempts = []
        def locked_then_free(source, target):
            attempts.append(target)
            if len(attempts) < 3:
                raise PermissionError(13, 'Access denied')
            return replace(source, target)
        with patch.object(u.os, 'replace', side_effect=locked_then_free), patch.object(u.time, 'sleep'):
            self.assertTrue(u._write_worker_status(self.root, 'result.json', {'download': 'verified.zip'}))
        self.assertEqual(len(attempts), 3)
        self.assertEqual(json.loads((self.root/'result.json').read_text()), {'download': 'verified.zip'})

    def test_permanent_result_failure_is_not_reported_as_success(self):
        with patch.object(u.os, 'replace', side_effect=PermissionError('locked')), patch.object(u.time, 'sleep'):
            with self.assertRaises(PermissionError):
                u._write_worker_status(self.root, 'result.json', {'download': 'verified.zip'})

    def worker_download(self, *, corrupt=False):
        payload = b'actual download bytes' * 100000
        asset = dict(name='no_mans_sky_base_builder-18.2.45.zip', size=len(payload),
                     digest='sha256:' + hashlib.sha256(payload).hexdigest(),
                     browser_download_url='https://github.com/slipperystickers/nms-base-builder/releases/download/v18.2.45/test.zip')
        release = dict(available=True, version='18.2.45', asset=asset)
        request = dict(product='bbe', installed='18.2.43', action='download',
                       destination=str(self.root/'downloads'), token='123456abcdef', asset=asset)
        (self.root/'request.json').write_text(json.dumps(request))
        class Response(io.BytesIO):
            def geturl(self):
                return asset['browser_download_url']
        original = u.download_release
        def download(result, destination, **kwargs):
            return original(result, destination, opener=lambda *a, **k: Response(
                b'x' * len(payload) if corrupt else payload), **kwargs)
        with patch.object(u, 'check_release', return_value=release), patch.object(u, 'download_release', side_effect=download):
            u.worker(self.root)
        outcome = json.loads((self.root/'result.json').read_text())
        if corrupt:
            self.assertIn('verification failed', outcome['error'])
            self.assertFalse((self.root/'downloads'/asset['name']).exists())
        else:
            self.assertEqual(Path(outcome['download']).read_bytes(), payload)
        return outcome

    def test_progress_access_denied_does_not_abort_download(self):
        original = u.os.replace
        def deny_progress(source, target):
            if Path(target).name == 'progress.json':
                raise PermissionError(13, 'Access denied')
            return original(source, target)
        with patch.object(u.os, 'replace', side_effect=deny_progress), patch.object(u.time, 'sleep'):
            self.worker_download()

    def test_locked_progress_does_not_bypass_archive_verification(self):
        original = u.os.replace
        def deny_progress(source, target):
            if Path(target).name == 'progress.json':
                raise PermissionError('locked')
            return original(source, target)
        with patch.object(u.os, 'replace', side_effect=deny_progress), patch.object(u.time, 'sleep'):
            self.worker_download(corrupt=True)

    @unittest.skipUnless(os.name == 'nt', 'Windows file sharing semantics')
    def test_real_windows_reader_lock_preserves_download(self):
        from ctypes import wintypes
        kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        kernel.CreateFileW.argtypes = (wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD,
                                      wintypes.LPVOID, wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE)
        kernel.CreateFileW.restype = wintypes.HANDLE
        kernel.CloseHandle.argtypes = (wintypes.HANDLE,)
        path = self.root/'progress.json'
        path.write_text('{}')
        # Permit reads/writes, but hold off replacement exactly as in WinError 5.
        handle = kernel.CreateFileW(str(path), 0x80000000, 3, None, 3, 0x80, None)
        self.assertNotEqual(handle, wintypes.HANDLE(-1).value)
        try:
            temporary = self.root/'probe.tmp'
            temporary.write_text('{}')
            with self.assertRaises(PermissionError):
                os.replace(temporary, path)
            self.worker_download()
        finally:
            kernel.CloseHandle(handle)


if __name__ == '__main__':
    unittest.main()
