"""Check that a staged screenshot and caption use one upload request."""
import base64
import importlib.util
from pathlib import Path
import tempfile

source = Path(__file__).resolve().parents[1] / 'src/addons/no_mans_sky_base_builder/bbe_chat_helper.py'
spec = importlib.util.spec_from_file_location('bbe_chat_helper_test', source)
helper = importlib.util.module_from_spec(spec)
spec.loader.exec_module(helper)

calls = []
original_request = helper.request
helper.request = lambda *args, **kwargs: calls.append((args, kwargs)) or {'ok': True}
with tempfile.TemporaryDirectory() as directory:
    snapshot = Path(directory) / 'screen.png'
    snapshot.write_bytes(b'example image bytes')
    assert helper.run('send', {
        'secret': 'a' * 43, 'to': '', 'file': str(snapshot), 'text': 'Please check this screenshot'
    }) == {'ok': True}
assert len(calls) == 1
assert calls[0][0] == ('upload',)
assert calls[0][1]['timeout'] == 40
assert base64.urlsafe_b64decode(calls[0][1]['headers']['X-BBE-Text'] + '===') == b'Please check this screenshot'
assert helper.run('sync', {'secret': 'a' * 43, 'as': 'b' * 32, 'to': ''}) == {'ok': True, 'inbox': []}
assert calls[1][0] == ('sync', {'secret': 'a' * 43, 'as': 'b' * 32, 'to': None})
helper.request = original_request

class FakeResponse:
    def __enter__(self): return self
    def __exit__(self, *args): return False
    def read(self, limit): return b'{"ok":true}'

class FakeOpener:
    def open(self, query, timeout):
        assert query.get_header('User-agent').startswith('BBE-Chat/')
        return FakeResponse()

helper.OPENER = FakeOpener()
assert helper.request('health') == {'ok': True}
print('BBE_CHAT_HELPER_OK')
