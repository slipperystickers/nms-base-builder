import importlib.util
import json
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import Mock

path = Path(__file__).resolve().parents[1] / 'src/addons/no_mans_sky_base_builder/furby_updates.py'
spec = importlib.util.spec_from_file_location('updates', path)
u = importlib.util.module_from_spec(spec)
spec.loader.exec_module(u)

class Lifecycle(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.c = u.ProcessUpdateClient('bbe', '18.1.86', state=self.tmp.name, require_consent=True)
        self.addCleanup(self.c.close)

    def worker(self, running=True):
        self.c.worker=Mock();self.c.worker.poll.return_value=None if running else 0
        self.c.job=Path(self.tmp.name)/'job';self.c.job.mkdir()
        self.c.busy=True;self.c.started=self.c.last_progress=time.monotonic()

    def test_stuck_check_releases_busy_and_can_retry(self):
        self.worker();self.c.started-=46;worker=self.c.worker
        self.c.poll();self.assertFalse(self.c.busy);worker.terminate.assert_called_once()
        self.assertIn('timed out',self.c.message);self.assertIsNone(self.c.job)

    def test_stalled_download_times_out_without_touching_other_files(self):
        self.worker();self.c.action='download';self.c.last_progress-=121
        other=Path(self.tmp.name)/'existing.zip';other.write_text('keep')
        self.c.poll();self.assertFalse(self.c.busy);self.assertEqual(other.read_text(),'keep')

    def test_growing_download_survives_unavailable_progress_file(self):
        self.worker();self.c.action='download';self.c.last_progress-=121
        self.c.staging=Path(self.tmp.name)/'download.part'
        self.c.staging.write_bytes(b'new downloaded bytes')
        self.c.poll()
        self.assertTrue(self.c.busy)
        self.c.worker.terminate.assert_not_called()
        self.c.last_progress-=121  # No further growth still times out.
        self.c.poll()
        self.assertFalse(self.c.busy)

    def test_malformed_result_releases_busy(self):
        self.worker(False);(self.c.job/'result.json').write_text('{"release": null}')
        self.c.poll();self.assertFalse(self.c.busy);self.assertIn('retry',self.c.message)

    def test_latest_result_finishes_and_is_visible(self):
        self.worker(False);(self.c.job/'result.json').write_text(json.dumps({'release':{'message':'You have the latest public version.','available':False}}))
        self.c.poll();self.assertFalse(self.c.busy);self.assertIn('latest public',self.c.message)

    def test_auto_retries_failure_and_does_not_repeat_success(self):
        self.c.set_auto(True);self.c.start=Mock();self.c.settings['last_attempt']=time.time()-901
        self.c.maybe_check();self.c.start.assert_called_once()
        self.c.start.reset_mock();self.c.result={'available':False};self.c.settings['last_checked']=time.time()
        self.c.maybe_check();self.c.start.assert_not_called()

    def test_bad_saved_timestamps_do_not_break_polling(self):
        self.c.set_auto(True);self.c.settings.update(last_attempt='bad',last_checked=None)
        self.c.start=Mock();self.c.maybe_check();self.c.start.assert_called_once()

    def test_new_session_checks_even_after_recent_success(self):
        self.c.set_auto(True);self.c.settings.update(last_attempt=time.time()-3,last_checked=time.time()-2)
        self.c.start=Mock();self.c.maybe_check();self.c.start.assert_called_once()

if __name__=='__main__':unittest.main()
