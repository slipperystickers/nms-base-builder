"""Run in Blender background to verify isolated chat registration and identity storage."""
import importlib.util
import json
import os
from pathlib import Path
import tempfile

import bpy

source = Path(__file__).resolve().parents[2] / 'src/addons/no_mans_sky_base_builder/bbe_chat.py'
spec = importlib.util.spec_from_file_location('bbe_chat_smoke', source)
chat = importlib.util.module_from_spec(spec)
spec.loader.exec_module(chat)

with tempfile.TemporaryDirectory() as directory:
    chat._identity_path = lambda: Path(directory) / 'identity.json'
    chat._settings_path = lambda: Path(directory) / 'settings.json'
    saved = {'secret': 'a' * 43, 'name': 'TestUser', 'active': False}
    chat._save_identity(saved)
    assert chat._load_identity() == {**saved, 'names': []}
    assert json.loads((Path(directory) / 'identity.json').read_text()) == saved
    chat.register()
    assert chat._chat_enabled is False
    assert chat._start('sync', to='') is False
    assert bpy.ops.bbe.chat_toggle() == {'FINISHED'}
    assert chat._chat_enabled is True
    assert json.loads((Path(directory) / 'settings.json').read_text()) == {'enabled': True}
    assert bpy.ops.bbe.chat_toggle() == {'FINISHED'}
    assert chat._chat_enabled is False
    assert Path(chat._python_executable()).is_file()
    assert hasattr(bpy.types.WindowManager, 'bbe_chat_name')
    assert hasattr(bpy.types.WindowManager, 'bbe_chat_draft')
    assert hasattr(bpy.types.WindowManager, 'bbe_chat_recovery')
    assert bpy.types.VIEW3D_PT_bbe_chat.bl_rna
    chat._identity = {'secret': 'a' * 43, 'id': '1' * 32, 'name': 'First', 'active': True,
                      'names': [{'id': '1' * 32, 'name': 'First'}, {'id': '2' * 32, 'name': 'FF'}]}
    assert bpy.ops.bbe.chat_switch(identity_id='2' * 32) == {'FINISHED'}
    assert chat._identity['name'] == 'FF'
    assert chat._load_identity()['id'] == '2' * 32
    assert bpy.ops.bbe.chat_switch(identity_id='3' * 32) == {'CANCELLED'}
    chat.unregister()
    assert not hasattr(bpy.types.WindowManager, 'bbe_chat_name')
    assert not hasattr(bpy.types.WindowManager, 'bbe_chat_draft')
print('BBE_CHAT_SMOKE_OK')
