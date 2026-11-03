"""Bounded large-transfer client checks without a public chat connection."""
import hashlib, importlib.util, tempfile, threading
from pathlib import Path
p=Path(__file__).resolve().parents[1]/'src/addons/no_mans_sky_base_builder/bbe_chat_helper.py'
spec=importlib.util.spec_from_file_location('helper',p);h=importlib.util.module_from_spec(spec);spec.loader.exec_module(h)
with tempfile.TemporaryDirectory() as folder:
    root=Path(folder);f=root/'test.blend';f.write_bytes(b'BLENDER-v500'+b'x'*(h.CHUNK_BYTES+10))
    chunks=[];actions=[];cancel=threading.Event(); digest=hashlib.sha256(f.read_bytes()).hexdigest()
    def request(action,data=None,**kw):
        actions.append(action)
        if action=='file-start': return {'id':data['uploadId'],'chunkBytes':h.CHUNK_BYTES}
        if action=='file-chunk':
            chunk=kw['raw'];assert len(chunk)<=h.CHUNK_BYTES
            assert hashlib.sha256(chunk).hexdigest()==kw['headers']['X-BBE-SHA256']
            chunks.append(chunk)
            return {'offset':int(kw['headers']['X-BBE-Offset'])+len(chunk)}
        if action=='file-finish':
            assert kw['headers']['X-BBE-SHA256']==digest
            return {'message':{'id':'test'}}
        if action=='file-cancel':return {'ok':True}
    h.request=request
    detail={'secret':'s'*43,'as':'a'*32,'file':str(f),'to':'','text':''}
    assert h.run('send',detail)=={'message':{'id':'test'}}
    assert len(chunks)==2 and b''.join(chunks)==f.read_bytes()
    assert 'file-cancel' not in actions
    actions.clear()
    def stop(done,total):
        if done:cancel.set()
    try:h.run('send',{**detail,'_cancel':cancel,'_progress':stop})
    except RuntimeError as e:assert str(e)=='Transfer cancelled'
    else:raise AssertionError('Cancellation ignored')
    assert actions[-1]=='file-cancel' and 'file-finish' not in actions
    cancel.clear()
    def read(action,data=None,**kw):
        start,end=map(int,kw['headers']['Range'][6:].split('-'))
        with f.open('rb') as stream:stream.seek(start);return stream.read(end-start+1)
    h.request=read
    destination=root/'download.blend'; download={'secret':'s'*43,'id':'a'*32,'path':str(destination),'size':f.stat().st_size,'sha256':digest}
    h.run('download',download);assert destination.read_bytes()==f.read_bytes()
    try:h.run('download',download)
    except FileExistsError:pass
    else:raise AssertionError('Existing file overwritten')
    destination.unlink()
    try:h.run('download',{**download,'_cancel':cancel,'_progress':stop})
    except RuntimeError:pass
    else:raise AssertionError('Download cancellation ignored')
    assert not destination.exists() and not list(root.glob('*.bbe-part'))
    cancel.clear()
    try:h.run('download',{**download,'sha256':'0'*64})
    except RuntimeError as e:assert 'checksum' in str(e)
    else:raise AssertionError('Bad checksum accepted')
    assert not destination.exists() and not list(root.glob('*.bbe-part'))
    assert h.file_limit(f)==2*1024**3 and h.file_limit(root/'a.json')==64*1024**2
print('BBE_CHAT_TRANSFERS_OK')
