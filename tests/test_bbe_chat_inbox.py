"""Sparse inbox hydration is bounded and preserves current conversation history."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'src/addons/no_mans_sky_base_builder'))
import bbe_chat_helper as h
calls = []
dm = {'id':'d','from':'bob','to':'alice','name':'Bob','time':2}
def request(route, data):
    calls.append(data)
    return {'messages':[{**dm,'text':'Hello'}] if data['to']=='bob' else [], 'inbox':[dm]}
h.request = request
detail = {'secret':'test-only','as':'alice','to':None}
result = h.sync_chat(detail)
assert result['messages'] == [] and result['inbox'][0]['text'] == 'Hello'
assert len(calls) == 2
calls.clear(); h.sync_chat({**detail,'known_content':['d']})
assert len(calls) == 1
print('CHAT22_SPARSE_INBOX_HYDRATION_PASS')
