"""Upgrade the packaged extension in an isolated Blender repository."""
import os, sys, zipfile, importlib
from pathlib import Path
import bpy, addon_utils
repo = Path(__file__).resolve().parents[2]
qa = repo/'tests/.artifacts'
profile = f'{bpy.app.version[0]}{bpy.app.version[1]}'
root = qa/('extension_upgrade_'+profile)
target = root/'no_mans_sky_base_builder'
root.mkdir(exist_ok=True)
os.environ['NMS_BASE_BUILDER_DATA_DIR'] = str(root/'data')
sys.path.insert(0, str(qa/'python_dependencies'))
with zipfile.ZipFile(repo/'dist/no_mans_sky_base_builder-18.2.23.zip') as archive:
    archive.extractall(target)
prefs = bpy.context.preferences
prefs.extensions.repos.new(name='BBE isolated upgrade', module='bbe_clean_test', custom_directory=str(root))
name = 'bl_ext.bbe_clean_test.no_mans_sky_base_builder'
errors = []
addon = addon_utils.enable(name, default_set=True, handle_error=errors.append, refresh_handled=True)
assert not errors and addon is not None, errors
assert addon.ADDON_VERSION == '18.2.23' and addon._core_registered
assert bpy.ops.bbe.backup_settings.get_rna_type()
old_panel = importlib.import_module(name+'.save_editor.save_editor_presentation')
addon_utils.disable(name, default_set=False, refresh_handled=True)
del old_panel.BBE_OT_backup_settings
# Before the fix the older cached module reproduces the exact reported error.
try:
    importlib.reload(addon)
except ImportError as exc:
    assert "cannot import name 'BBE_OT_backup_settings'" in str(exc), str(exc)
    print('REPRODUCED_COUNTRYBOY_IMPORT_ERROR', str(exc), flush=True)
else:
    raise AssertionError('18.2.23 unexpectedly accepted a stale save panel')
with zipfile.ZipFile(repo/'dist/no_mans_sky_base_builder-18.2.26.zip') as archive:
    archive.extractall(target)
addon.__time__ = 0
errors = []
updated = addon_utils.enable(name, default_set=True, handle_error=errors.append, refresh_handled=True)
assert not errors and updated is not None, errors
assert updated.ADDON_VERSION == '18.2.26' and updated._core_registered
new_panel = importlib.import_module(name+'.save_editor.save_editor_presentation')
assert new_panel is not old_panel and hasattr(new_panel, 'BBE_OT_backup_settings')
for operator in ('backup_settings', 'corvette_export', 'optimizer_export', 'chat_open'):
    assert getattr(bpy.ops.bbe, operator).get_rna_type()
print('PACKAGED_EXTENSION_UPGRADE_PASS', bpy.app.version_string, name, flush=True)
