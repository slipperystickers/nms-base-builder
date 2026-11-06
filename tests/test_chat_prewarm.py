"""A prewarmed companion stays hidden and opens on the first toolbar command."""
import json
import os
from pathlib import Path
import sys
import tempfile

source = Path(__file__).resolve().parents[1] / 'src/addons/no_mans_sky_base_builder'
site = sys.argv[1]
sys.path.insert(0, str(source))
sys.argv = [str(source / 'bbe_chat_messenger.py'), site, 'identity', 'settings', 'snapshot']
os.environ['QT_QPA_PLATFORM'] = 'offscreen'
import bbe_chat_messenger as messenger

app = messenger.QtWidgets.QApplication([])
messenger.Messenger.sync = lambda self: None
messenger.Messenger.show_account_settings = lambda self: None

with tempfile.TemporaryDirectory() as temporary:
    folder = Path(temporary)
    identity = folder / 'identity.json'
    settings = folder / 'settings.json'
    identity.write_text(json.dumps({'secret': 'test-only', 'id': 'alice',
                                    'names': [{'id': 'alice', 'name': 'Alice'}]}))
    settings.write_text(json.dumps({'enabled': True, 'online_access': True,
                                    'native_chat_toolbar': True}))
    window = messenger.Messenger(identity, settings, folder, prewarm=True)
    assert not window.isVisible(), 'Prewarming opened a visible chat window'
    (folder / 'messenger-command.json').write_text(json.dumps({'action': 'TOOLBAR'}))
    window._consume_blender_command()
    app.processEvents()
    assert window.isVisible() and not window.collapsed and window.dock_mode == 'toolbar'
    window.close()

print('CHAT_PREWARM_PASS')
