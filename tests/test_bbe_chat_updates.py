"""Two-user first snapshot, sparse inbox, reply notification and scrolling regression."""
import json,os,sys,tempfile,copy
from pathlib import Path
root=Path(__file__).resolve().parents[1];source=root/'src/addons/no_mans_sky_base_builder'
site=sys.argv[1];sys.path.insert(0,str(source));sys.argv=[str(source/'bbe_chat_messenger.py'),site,'identity','settings','snapshot']
os.environ['QT_QPA_PLATFORM']='offscreen'
import bbe_chat_messenger as m
import bbe_chat_state as state
app=m.QtWidgets.QApplication([])
for font in ('segoeui.ttf','seguiemj.ttf','seguisym.ttf'):m.QtGui.QFontDatabase.addApplicationFont('C:/Windows/Fonts/'+font)
app.setFont(m.QtGui.QFont('Segoe UI',10))
m.Messenger.sync=lambda self:None
m.Messenger.show_account_settings=lambda self:None
with tempfile.TemporaryDirectory() as tmp:
 p=Path(tmp);identity=p/'identity.json';settings=p/'settings.json'
 identity.write_text(json.dumps({'secret':'test-only','id':'alice','names':[{'id':'alice','name':'Alice'}]}))
 settings.write_text(json.dumps({'enabled':True,'native_chat_toolbar':True}))
 w=m.Messenger(identity,settings,p);w.timer.stop();w.snapshot_timer.stop();w.compact_timer.stop()
 w._job=lambda *a,**k:None
 w._notify_inbox([])
 picture={'id':'first','from':'bob','name':'Bob','to':None,'text':'','time':1000,'attachment':{'id':'pic','mime':'image/png','name':'snapshot.png'}}
 def sync(messages):
  value={'messages':messages,'inbox':messages,'online':[{'id':'bob','name':'Bob'}]}
  w._synced(value,None,w.target,w.persona,w.message_generation)
 sync([picture]); assert w._last_received['attachment']['id']=='pic'
 w._collapse(False);w.show();app.processEvents()
 assert any('View image' in b.text() for b in w.findChildren(m.QtWidgets.QPushButton)), [b.text() for b in w.findChildren(m.QtWidgets.QPushButton)]
 w._toggle_image('pic')
 image=m.QtGui.QImage(1600,900,m.QtGui.QImage.Format_RGB32);image.fill(m.QtGui.QColor('#348dcc'))
 data=m.QtCore.QByteArray();buf=m.QtCore.QBuffer(data);buf.open(m.QtCore.QIODevice.WriteOnly);image.save(buf,'PNG')
 w._media_loaded('pic',bytes(data),None);app.processEvents()
 assert w.media_labels['pic'][0].pixmap() and w.media_labels['pic'][0].pixmap().height()<=100
 text={'id':'second','from':'bob','name':'Bob','to':None,'time':2000,'text':'Newest text, not attachment','attachment':None}
 sync([picture,text])
 sparse=[{k:v for k,v in item.items() if k not in ('text','attachment')} for item in (picture,text)]
 w._notify_inbox(sparse)
 w._publish_toolbar_status()
 payload=json.loads((p/'toolbar-status.json').read_text())
 assert payload['preview']=='Bob: Newest text, not attachment',payload
 w.begin_reply(text);w.composer.setPlainText('Yes, fixed!')
 assert w.reply_banner.isVisible()
 sent=[]
 m.helper.run=lambda action,detail:sent.append(detail) or {'message':{'id':'reply','from':'alice','name':'Alice','to':None,'text':detail['text'],'time':3000,'attachment':None}}
 w._job=lambda fn,done,**kw:done(fn(),None)
 w.send(); assert state.reply_parts(sent[0]['text'])==('Bob','Newest text, not attachment','Yes, fixed!')
 assert not w.reply_banner.isVisible()
 # Bob receives the reply through the same server-compatible plain text protocol.
 bob={};names=[{'id':'bob','name':'Bob'}]
 state.update(bob,{'inbox':[]},'bob',names)
 reply={'id':'reply','from':'alice','name':'Alice','to':None,'text':sent[0]['text'],'time':3000}
 state.update(bob,{'inbox':[reply]},'bob',names)
 assert bob['directed']=={'main':1}
 state.update(bob,{'inbox':[reply]},'bob',names)
 assert bob['directed']=={'main':1}
 state.update(bob,{'inbox':[reply]},'bob',names,viewed='main');assert not bob['directed']
 state.save(p/'bob.json',bob);assert state.load(p/'bob.json')['seen']==['reply']
 messages=[dict(text,id=str(i),time=4000+i,text='Long test message '*20) for i in range(35)]
 sync(messages)
 for _ in range(8):app.processEvents()
 bar=w.scroll.verticalScrollBar();assert bar.maximum()>0 and bar.value()==bar.maximum(),(bar.value(),bar.maximum())
 bar.setValue(0);w._user_scrolled();assert not w._follow_latest
 sync(messages+[dict(text,id='last',time=9999)])
 for _ in range(8):app.processEvents()
 assert bar.value()==bar.maximum(),(bar.value(),bar.maximum())
 sync([picture,text,dict(text,id='reply-to-me',time=99999,text=state.make_reply('Alice','Can you see the snapshot?','Yes, it opens now!'))])
 w.begin_reply(text)
 m.QtCore.QCoreApplication.sendPostedEvents(None,m.QtCore.QEvent.DeferredDelete)
 for _ in range(8):app.processEvents()
 w.grab().save(str(root/'tests/.artifacts/chat22-reply-ui.png'))
 w.close()
print('CHAT22_TWO_USER_SNAPSHOT_REPLY_SCROLL_PASS')

