"""Real Messenger selection, incoming-only previews, and DM-only highlights."""
import json
import os
from pathlib import Path
import sys
import tempfile
from unittest.mock import patch

root = Path(__file__).resolve().parents[1]
source = root / 'src/addons/no_mans_sky_base_builder'
site = sys.argv[1]
sys.path.insert(0, str(source))
sys.argv = [str(source/'bbe_chat_messenger.py'), site, 'identity', 'settings', 'snapshot']
os.environ['QT_QPA_PLATFORM'] = 'offscreen'
import bbe_chat_messenger as m
import bbe_chat_state as state

app = m.QtWidgets.QApplication([])
for font in ('segoeui.ttf', 'seguiemj.ttf', 'seguisym.ttf'):
    m.QtGui.QFontDatabase.addApplicationFont('C:/Windows/Fonts/' + font)
app.setFont(m.QtGui.QFont('Segoe UI', 10))
m.Messenger.sync = lambda self: None
m.Messenger.show_account_settings = lambda self: None

def message(id, sender, target, time, text):
    return dict(id=id, **{'from':sender}, to=target, name=sender.title(), time=time, text=text)

with tempfile.TemporaryDirectory() as tmp:
    folder = Path(tmp)
    identity = folder / 'identity.json'; settings = folder / 'settings.json'
    identity.write_text(json.dumps(dict(secret='test-only', id='alice', names=[
        dict(id='alice',name='Alice'), dict(id='alias',name='Alias')])) )
    settings.write_text(json.dumps(dict(enabled=True, native_chat_toolbar=True)))
    w = m.Messenger(identity, settings, folder)
    w.timer.stop(); w.snapshot_timer.stop(); w.compact_timer.stop()
    w._job = lambda *a, **k: None
    w._notify_inbox([])
    main = message('main', 'bob', None, 1000, 'Hello Main Room')
    dm = message('dm', 'zapper', 'alice', 2000, 'Latest Zapper response')
    other = message('other', 'doom', 'alice', 3000, 'Separate DM')
    mine = message('mine', 'alice', 'zapper', 4000, 'My outgoing response')
    alias = message('alias', 'alias', None, 5000, 'My other name')
    inbox = [main, dm, other]

    def sync(messages):
        w._synced(dict(messages=messages, inbox=inbox, online=[]), None,
                  w.target, w.persona, w.message_generation)
        w._publish_toolbar_status()

    def toolbar():
        w._publish_toolbar_status()
        return json.loads((folder/'toolbar-status.json').read_text())

    sync([main, alias])
    assert toolbar()['preview'] == 'Doom: Separate DM'
    assert toolbar()['directed'] == 2
    w._open_conversation('zapper', 'Zapper')
    assert toolbar()['preview'] == 'Doom: Separate DM'
    assert toolbar()['directed'] == 2  # Reading is not replying.
    sync([dm, mine])
    assert toolbar()['preview'] == 'Doom: Separate DM'
    w._open_conversation('doom', 'Doom')
    assert toolbar()['preview'] == 'Doom: Separate DM'
    assert toolbar()['directed'] == 2
    w._sent(None,'Simulated failure','',None,'doom','alice',other)
    assert toolbar()['directed'] == 2
    w._sent({},None,'',None,'doom','alice',other)
    assert toolbar()['preview'] == 'Zapper: Latest Zapper response' and toolbar()['directed']==1
    assert toolbar()['target']=='zapper'  # Next unanswered DM, still highlighted.
    w._open_conversation('zapper','Zapper')
    w._sent({'message':mine},None,'',None,'zapper','alice',dm)
    assert toolbar()['preview'] == 'Bob: Hello Main Room' and toolbar()['directed']==0
    w._open_conversation('nobody', 'Nobody')
    assert toolbar()['preview'] == 'Bob: Hello Main Room'
    w.close_conversation('nobody')
    assert w.target is None and toolbar()['preview'] == 'Bob: Hello Main Room'

    # Even a quoted reply in Main must not highlight the bar.
    public_reply = message('public', 'bob', None, 6000, state.make_reply('Alice', 'Question', 'Main response'))
    inbox.append(public_reply)
    sync([main, public_reply, alias])
    assert toolbar()['directed'] == toolbar()['unread'] == 0
    assert toolbar()['preview'] == 'Bob: Main response'
    assert not w.mini_title.styleSheet()

    # Incoming content is consumed during this poll, including sparse inboxes.
    w._open_conversation('zapper', 'Zapper')
    newest = message('newest', 'zapper', 'alice', 7000, 'New response in this poll')
    inbox.append({k:v for k,v in newest.items() if k != 'text'})
    sync([dm, mine, newest])
    assert toolbar()['preview'] == 'Zapper: New response in this poll'
    # Reading clears the pulse without removing the unanswered response.
    state.update(w._notifications,dict(inbox=inbox,messages=[newest]),w.persona,w.names,viewed='zapper')
    assert not w._notifications['unread'].get('zapper') and toolbar()['directed']==0
    assert toolbar()['preview'] == 'Bob: Main response' and toolbar()['target'] is None
    w.dock_mode = 'floating'; w._collapse(False); w.show()
    with patch.object(m.time,'monotonic',return_value=100):
        w._update_badge()
        assert not w.mini_title.styleSheet()
    for _ in range(6): app.processEvents()
    w.grab().save(str(root/'tests/.artifacts/chat25-awaiting-reply.png'))
    with patch.object(m.time,'monotonic',return_value=101):
        w._update_badge()
        assert not w.mini_title.styleSheet()

    # Pending replies survive restart and background/Messenger handoff.
    state.save(folder/'saved.json', w._notifications)
    saved = state.load(folder/'saved.json')
    assert state.toolbar(saved, 0)['preview'] == 'Bob: Main response'
    assert state.toolbar(saved,0)['directed']==0
    assert state.toolbar(saved, 0, 'zapper')['preview'] == 'Bob: Main response'
    old = dict(persona='alice', content=saved['content'], latest=newest, unread={}, directed={})
    state.update(old, dict(inbox=[], messages=[]), 'alice', w.names)
    assert 'Main response' in state.toolbar(old, 0)['preview']
    assert 'Main response' in state.toolbar(old, 0, 'zapper')['preview']
    # A response arriving while a send is in flight must keep its alert.
    w.hide()
    app.processEvents()
    newer = message('newer','zapper','alice',8000,'Arrived during send')
    inbox.append(newer);sync([dm,mine,newest,newer])
    w._sent({},None,'',None,'zapper','alice',newest)
    assert toolbar()['preview']=='Zapper: Arrived during send' and toolbar()['directed']==1
    # Exercise the real Send callback, with only the transport replaced.
    m.helper.run=lambda action,detail: {'message':message('sent','alice','zapper',9000,detail['text'])}
    w._job=lambda fn,done,**kw:done(fn(),None)
    w.composer.setPlainText('Reply sent successfully');w.send()
    assert toolbar()['preview']=='Bob: Main response' and toolbar()['directed']==0
    sync([dm,mine,newest,newer])
    assert toolbar()['preview']=='Bob: Main response' and toolbar()['directed']==0
    # A new event takes over again without changing the composer destination.
    newest_other=message('next-other','doom','alice',10000,'Another DM')
    inbox.append(newest_other);sync([dm,newest,newer])
    assert toolbar()['target']=='doom' and w.target=='zapper'
    (folder/'messenger-command.json').write_text(json.dumps({'action':'TOOLBAR','target':'doom'}))
    w._consume_blender_command()
    assert w.target=='doom' and toolbar()['directed']==1
    w.close()

print('CHAT25_DYNAMIC_REPLY_PREVIEW_PASS')
