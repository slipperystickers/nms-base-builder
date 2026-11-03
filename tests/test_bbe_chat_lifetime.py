"""Exercise actual companion processes against disposable Blender-owner processes.

Uses offline temporary profiles, real Windows process handles and Qt's event loop.
No user profile or chat server is accessed.
"""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time

root = Path(__file__).resolve().parents[1]
source = Path(os.environ.get('NMS_KUMA_TEST_ADDON', str(root / 'src/addons/no_mans_sky_base_builder')))
site = Path(sys.argv[1])
children = []
streams = []
results = []
env = dict(os.environ, QT_QPA_PLATFORM='offscreen')
flags = subprocess.CREATE_NO_WINDOW if sys.platform == 'win32' else 0


def owner():
    proc = subprocess.Popen([sys.executable, '-I', '-c', 'import sys; sys.stdin.buffer.read()'],
                            stdin=subprocess.PIPE, creationflags=flags)
    children.append(proc)
    return proc


def start(folder, parent, *, stalled=False):
    script = source / 'bbe_chat_messenger.py'
    if stalled:
        script = folder / 'stalled_worker.py'
        script.write_text(
            'import sys, time\n'
            f'sys.path.insert(0, {str(source)!r})\n'
            'import bbe_chat_messenger as m\n'
            'original = m.Messenger.__init__\n'
            'def init(self, *args):\n'
            '    original(self, *args)\n'
            '    self._begin_transfer("Offline test")\n'
            '    self._job(lambda: time.sleep(60), lambda *_: None)\n'
            'm.Messenger.__init__ = init\n'
            'sys.exit(m.main() or 0)\n', encoding='utf8')
    stream = (folder / ('child-' + str(len(children)) + '.log')).open('w', encoding='utf8')
    streams.append(stream)
    proc = subprocess.Popen([sys.executable, '-I', '-u', str(script), str(site),
                             str(folder / 'identity.json'), str(folder / 'settings.json'),
                             str(folder), '--blender-pid', str(parent.pid)],
                            env=env, stdout=stream, stderr=subprocess.STDOUT, creationflags=flags)
    children.append(proc)
    return proc


def ready(proc, folder):
    until = time.monotonic() + 8
    while time.monotonic() < until:
        assert proc.poll() is None, f'Messenger exited during startup: {proc.returncode}'
        if (folder / 'toolbar-status.json').exists():
            return
        time.sleep(.05)
    raise AssertionError('Messenger did not become ready')


def closed(proc, folder, timeout=5):
    assert proc.wait(timeout=timeout) == 0
    assert (folder / 'bbe_messenger_window.json').exists(), 'Graceful close did not run'


with tempfile.TemporaryDirectory(prefix='bbe-lifetime-') as directory:
    base = Path(directory)

    def profile(name):
        folder = base / name
        folder.mkdir()
        (folder / 'identity.json').write_text(json.dumps({'secret': 's'*43, 'names': []}))
        (folder / 'settings.json').write_text(json.dumps({
            'enabled': False, 'online_access': False, 'native_chat_toolbar': True}))
        return folder

    try:
        for crash in (False, True):
            folder = profile('crash' if crash else 'normal')
            parent = owner()
            child = start(folder, parent)
            ready(child, folder)
            time.sleep(1.2)
            assert child.poll() is None, 'Live Blender lost its companion'
            if crash:
                parent.kill()
            else:
                parent.stdin.close()
            parent.wait(timeout=3)
            closed(child, folder)
            results.append(folder.name)

        folder = profile('already-exited')
        parent = owner()
        parent.kill()
        parent.wait(timeout=3)
        child = start(folder, parent)
        assert child.wait(timeout=5) == 0
        assert not (folder / 'toolbar-status.json').exists()
        results.append(folder.name)

        folder = profile('shared')
        first, second = owner(), owner()
        child = start(folder, first)
        ready(child, folder)
        reuse = start(folder, second)
        assert reuse.wait(timeout=5) == 0, 'Second launch should reuse the companion'
        first.kill()
        first.wait(timeout=3)
        time.sleep(2.2)
        assert child.poll() is None, 'Closing one Blender closed another session chat'
        second.kill()
        second.wait(timeout=3)
        closed(child, folder)
        results.append(folder.name)

        folder = profile('stalled-worker')
        parent = owner()
        child = start(folder, parent, stalled=True)
        ready(child, folder)
        parent.kill()
        parent.wait(timeout=3)
        closed(child, folder, timeout=12)
        results.append(folder.name)
        print('BBE_CHAT_LIFETIME_PASS', ', '.join(results), flush=True)
    finally:
        for child in children:
            if child.poll() is None:
                child.kill()
            child.wait(timeout=3)
            if child.stdin and not child.stdin.closed:
                child.stdin.close()
        for stream in streams:
            stream.close()
        if len(results) != 5:
            for log in base.rglob('child-*.log'):
                print(log.parent.name, log.read_text(encoding='utf8', errors='replace')[-4000:])
