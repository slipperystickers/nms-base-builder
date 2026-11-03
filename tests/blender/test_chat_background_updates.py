import sys,tempfile,time
from pathlib import Path
from unittest.mock import patch
from types import SimpleNamespace as NS
import bpy
sys.path.insert(0,str(Path(__file__).resolve().parent))
from test_support import module,QA
c=module('bbe_chat')
with tempfile.TemporaryDirectory() as tmp:
 with patch.object(c,'_identity_path',return_value=Path(tmp)/'identity.json'), patch.object(c,'_load_chat_enabled',return_value=True), patch.object(c,'_start',return_value=True) as start:
  real=c.bpy;c.bpy=NS(app=NS(online_access=True),context=bpy.context)
  c._identity={'id':'alice','names':[{'id':'alice','name':'Alice'}],'active':False}
  c._notification_state={};c._enabled=True;c._busy=None;c._next_sync=0;c._messenger_process=None
  c._tick();assert start.call_count==1 and start.call_args.args==('sync',)
  assert c._messenger_process is None
  message=dict(id='1',name='Bob',text='Startup message',time=1,to=None,**{'from':'bob'})
  c._update_background_status(dict(messages=[message],inbox=[message],online=[{'id':'bob'}]))
  assert c._online_count()==1 and c._toolbar_status['preview']=='Bob: Startup message'
  newer=dict(message,id='2',time=2,text='Next message')
  c._update_background_status(dict(messages=[message,newer],inbox=[message,newer],online=[{'id':'bob'}]))
  assert c._toolbar_status['unread']==0 and c._toolbar_status['directed']==0
  c._update_background_status(dict(messages=[message,newer],inbox=[{k:v for k,v in newer.items() if k!='text'}],online=[{'id':'bob'}]))
  assert c._toolbar_status['preview']=='Bob: Next message'
  dm=dict(message,id='dm',time=3,text='Private response',to='alice')
  c._update_background_status(dict(messages=[message,newer],inbox=[newer,dm],online=[{'id':'bob'}]))
  assert c._toolbar_status['preview']=='Bob: Private response'
  assert c._toolbar_status['directed']==1
  c._update_background_status(dict(messages=[message,newer],inbox=[newer,dm],online=[{'id':'bob'}]))
  assert c._toolbar_status['directed']==1  # Repeated polls cannot dismiss it.
  c.chat_state.answered(c._notification_state,'bob',dm)
  c._update_background_status(dict(messages=[message,newer],inbox=[newer,dm],online=[{'id':'bob'}]))
  assert c._toolbar_status['preview']=='Bob: Next message' and not c._toolbar_status['directed']
  c._next_sync=0;c.bpy.app.online_access=False;start.reset_mock();c._tick();assert not start.called
  c.bpy=real
 with patch.object(c,'_load_chat_enabled',return_value=False), patch.object(c,'_start') as start:
  c._next_sync=0;c._tick();assert not start.called
 # Opening another build must not remove the background chat updater.
 fixture=str(Path(tmp)/'timer-lifecycle.blend')
 bpy.ops.wm.save_as_mainfile(filepath=fixture)
 bpy.ops.wm.open_mainfile(filepath=fixture)
 assert bpy.app.timers.is_registered(c._tick)
print('CHAT22_BACKGROUND_STARTUP_OPTOUT_PASS')
