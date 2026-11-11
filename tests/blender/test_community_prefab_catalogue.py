"""Run the native catalogue operators against an isolated service and prefab library."""
import json
import os
from pathlib import Path
import sys
import tempfile
import time
from unittest.mock import patch
import bpy
sys.path.insert(0,str(Path(__file__).resolve().parent))
from test_support import addon,module
client=module('community_prefabs')
address=os.environ['BBE_TEST_PREFAB_ORIGIN']
assert address.startswith('http://127.0.0.1:')
def drain():
    deadline=time.monotonic()+20
    while client._busy and time.monotonic()<deadline:
        client._poll()
        time.sleep(.02)
    assert not client._busy,client._status

with tempfile.TemporaryDirectory() as d, patch.object(client,'BASE',address+'/prefabs'),patch.object(client,'HOST',address),patch.object(module('preset').Preset,'PRESET_PATH',d):
    f=Path(d)/'fixture-upload.txt'
    rec=dict(ObjectID='^W_FLOOR',Position=[0.,0.,0.],Up=[0.,1.,0.],At=[0.,0.,1.],UserData=18446744073709551615)
    f.write_text(json.dumps([rec]),encoding='utf-8')
    assert bpy.ops.bbe.prefab_catalogue_upload('EXEC_DEFAULT',filepath=str(f),title='Orbit test',creator='Test builder',description_text='hydroponic lab')=={'FINISHED'}
    drain();assert 'published' in client._status,client._status
    bpy.context.window_manager.bbe_catalogue_query='hydroponic'
    assert bpy.ops.bbe.prefab_catalogue_search()=={'FINISHED'};drain()
    assert len(client._items)==1 and client._items[0]['title']=='Orbit test',client._status
    entry=client._items[0]['id']
    assert bpy.ops.bbe.prefab_catalogue_download(entry=entry)=={'FINISHED'};drain()
    name=client._local_names[entry];saved=Path(d)/'Community'/(name+'.nmsprefab')
    assert json.loads(saved.read_text(encoding='utf-8'))['Objects']==[rec]
    before=len([o for o in bpy.context.scene.objects if o.get('ObjectID')=='W_FLOOR'])
    assert bpy.ops.object.list_build_operator(part_id=name,prefab_only=True)=={'FINISHED'}
    assert len([o for o in bpy.context.scene.objects if o.get('ObjectID')=='W_FLOOR'])==before+1
    assert module('preset').Preset.get_presets()[name]==str(saved)
    client.reset()
print('NATIVE PREFAB UPLOAD SEARCH DOWNLOAD PLACE PASS',bpy.app.version_string,flush=True)
