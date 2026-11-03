"""Offline account UI checks: no real name claims or chat traffic."""
import json, os, sys, tempfile
from pathlib import Path
source = Path(__file__).resolve().parents[1] / 'src/addons/no_mans_sky_base_builder'
sys.path.insert(0, str(source))
os.environ['QT_QPA_PLATFORM'] = 'offscreen'
import bbe_chat_messenger as m
app = m.QtWidgets.QApplication([])
calls = []
def request(action, data=None, **kwargs):
    calls.append(action)
    return {'online': [], 'contacts': [], 'messages': []}
def run(action, detail):
    calls.append(action)
    assert action == 'claim'
    return {'id': 'a'*32, 'name': detail['name'], 'names': [{'id': 'a'*32, 'name': detail['name']}]}
m.helper.request = request
m.helper.run = run
with tempfile.TemporaryDirectory() as directory:
    folder = Path(directory)
    identity, settings = folder/'identity.json', folder/'settings.json'
    identity.write_text(json.dumps({'secret': 's'*43, 'names': [], 'active': False}))
    settings.write_text('{"enabled":false,"online_access":true}')
    w = m.Messenger(identity, settings, folder)
    w.show(); app.processEvents(); w.timer.stop(); w.snapshot_timer.stop()
    assert w.account_dialog.isVisible()
    w.sync(); w._claim_name('FF'); app.processEvents()
    assert calls == []
    w._set_enabled(True)
    assert json.loads(settings.read_text())['enabled']
    w._claim_name('FF')
    for _ in range(100):
        app.processEvents(); m.QtCore.QThread.msleep(10)
        if not w.claiming and not w.syncing: break
    assert w.persona == 'a'*32 and w.names[0]['name'] == 'FF'
    assert json.loads(identity.read_text())['name'] == 'FF'
    w.names = [{'id': str(i)*32, 'name': n} for i,n in enumerate(['FF','FuriousFurby','Third'])]
    before = len(calls)
    w._claim_name('Fourth')
    assert len(calls) == before and 'three names' in w.status.text()
    w._claim_name('FF', 'other_key_'+'a'*40)
    assert 'another Blender profile' in w.status.text()
    w.composer.setPlainText('Keep my draft')
    w._set_enabled(False); w._periodic(); w.sync(); app.processEvents()
    assert w.isVisible() and w.composer.toPlainText() == 'Keep my draft'
    assert len(calls) == before
    settings.write_text('{"enabled":false,"online_access":false}')
    w._set_enabled(True)
    assert not w._enabled() and not json.loads(settings.read_text())['enabled']
    if w.account_dialog: w.account_dialog.close()
    w.show_account_settings(); app.processEvents()
    checkbox = w.account_dialog.findChild(m.QtWidgets.QCheckBox)
    assert not checkbox.isEnabled()
    w.account_dialog.close(); w.close()
    # Recover a name on a new profile without sending any real network request.
    identity.write_text(json.dumps({'secret': 's'*43, 'names': []}))
    settings.write_text('{"enabled":true,"online_access":true}')
    w = m.Messenger(identity, settings, folder); w.timer.stop(); w.snapshot_timer.stop()
    w._claim_name('Recovered', 'r'*43)
    for _ in range(100):
        app.processEvents(); m.QtCore.QThread.msleep(10)
        if not w.claiming and not w.syncing: break
    assert w.secret == 'r'*43 and json.loads(identity.read_text())['secret'] == 'r'*43
    if w.account_dialog: w.account_dialog.close()
    w.close()
print('BBE_CHAT_ACCOUNTS_OK')
