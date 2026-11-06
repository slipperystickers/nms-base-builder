"""Read state must survive restart without acknowledging a later DM."""
import sys, tempfile
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src/addons/no_mans_sky_base_builder'))
import bbe_chat_state as s
names=[dict(id='alice',name='Alice')]
state={}
s.update(state,dict(inbox=[],messages=[]),'alice',names)
def message(id, time, sender='bob', target='alice'):
    return dict(id=id,time=time,**{'from':sender},to=target,name=sender,text=id)
public=message('main',50,target=None)
s.update(state,dict(inbox=[public],messages=[public]),'alice',names)
first=message('first',100)
s.update(state,dict(inbox=[public,first],messages=[]),'alice',names)
assert s.toolbar(state,1)['directed']==1
# Selecting an empty conversation alone has not displayed the response.
s.update(state,dict(inbox=[public,first],messages=[]),'alice',names,viewed='bob')
assert s.toolbar(state,1)['directed']==1
s.update(state,dict(inbox=[public,first],messages=[first]),'alice',names,viewed='bob')
assert s.toolbar(state,1)['directed']==0
assert s.toolbar(state,1)['preview']=='bob: main'
assert 'bob' in state['dm_pending']
with tempfile.TemporaryDirectory() as folder:
    path=Path(folder)/'state.json';s.save(path,state);state=s.load(path)
assert s.toolbar(state,1)['directed']==0
assert s.toolbar(state,1)['preview']=='bob: main'
second=message('second',200)
s.update(state,dict(inbox=[public,second],messages=[]),'alice',names)
s.mark_read(state,'bob',first)
assert s.toolbar(state,1)['directed']==1
s.mark_read(state,'bob',second)
assert s.toolbar(state,1)['directed']==0
assert s.toolbar(state,1)['preview']=='bob: main'
public=message('main-new',300,target=None)
s.update(state,dict(inbox=[second,public],messages=[public]),'alice',names)
s.answered(state,'bob',second)
assert s.toolbar(state,1)['preview']=='bob: main-new' and s.toolbar(state,1)['directed']==0
print('CHAT_READ_ATTENTION_PASS')
