"""Run with --background --factory-startup to check full BBE integration."""
import sys
from pathlib import Path
import bpy

root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(root / 'src/addons'))
import no_mans_sky_base_builder as addon

assert hasattr(bpy.app, 'online_access')
assert 'confirm_text' in bpy.context.window_manager.invoke_props_dialog.__doc__
addon.register()
try:
    from no_mans_sky_base_builder.tools_menu import base_builder_menu
    assert 'chat' in base_builder_menu._ITEMS
    assert bpy.types.VIEW3D_PT_bbe_chat.bl_rna
    assert bpy.ops.bbe.chat_snapshot.get_rna_type()
    assert bpy.ops.bbe.chat_compose.get_rna_type()
    assert bpy.ops.bbe.chat_open.get_rna_type()
    from no_mans_sky_base_builder import bbe_chat
    assert Path(bbe_chat._qt_site_packages(), 'PySide6').is_dir()
    import tempfile, json
    with tempfile.TemporaryDirectory() as directory:
        settings = Path(directory) / 'settings.json'
        identity = Path(directory) / 'identity.json'
        original_settings, original_identity = bbe_chat._settings_path, bbe_chat._identity_path
        original_popen = bbe_chat.subprocess.Popen
        original_identity_value = bbe_chat._identity
        calls = []
        class FakeProcess:
            def poll(self): return 0
        bbe_chat.subprocess.Popen = lambda *a, **k: calls.append((a,k)) or FakeProcess()
        bbe_chat._settings_path = lambda: settings
        bbe_chat._identity_path = lambda: identity
        bbe_chat._identity = None
        bbe_chat._chat_enabled = False
        bbe_chat._last_theme = None
        try:
            assert bpy.ops.bbe.chat_open() == {'FINISHED'}
            assert calls and 'bbe_chat_messenger.py' in str(calls[0][0])
            import os
            assert calls[0][0][0][-2:] == ['--blender-pid', str(os.getpid())]
            assert not json.loads(settings.read_text())['enabled']
            assert json.loads(identity.read_text())['names'] == []
            settings.write_text('{"enabled":true}')
            bbe_chat._last_theme = None
            bbe_chat.sync_theme()
            assert json.loads(settings.read_text())['enabled'] is True
        finally:
            bbe_chat._settings_path, bbe_chat._identity_path = original_settings, original_identity
            bbe_chat.subprocess.Popen = original_popen
            bbe_chat._identity = original_identity_value
            bbe_chat._messenger_process = None
    presentation = (root / 'src/addons/no_mans_sky_base_builder/tools_menu/base_builder_menu_presentation.py').read_text()
    assert 'Chat & account settings' not in presentation
finally:
    addon.unregister()
print('BBE_CHAT_ADDON_OK')
