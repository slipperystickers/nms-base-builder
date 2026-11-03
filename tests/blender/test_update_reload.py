"""Reproduce an older cached save panel during an in-session add-on update."""
import sys, importlib, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from test_support import addon, module
import bpy, addon_utils

assert addon._core_registered
old_panel = module('save_editor.save_editor_presentation')
old_builder = module('builder')
name = addon.__name__
addon_utils.disable(name, default_set=False, refresh_handled=True)
assert not addon._core_registered
# The previous release stays in sys.modules after Blender disables it.
# Emulate the absent operator in Countryboy's reported install error.
del old_panel.BBE_OT_backup_settings
assert name + '.save_editor.save_editor_presentation' in sys.modules
assert not hasattr(old_panel, 'BBE_OT_backup_settings')
# Use Blender's real upgrade/re-enable route, including its root reload.
addon.__time__ = 0
errors = []
reloaded = addon_utils.enable(name, default_set=True, handle_error=errors.append, refresh_handled=True)
assert not errors, errors
assert reloaded is not None and reloaded._core_registered
new_panel = importlib.import_module(name + '.save_editor.save_editor_presentation')
assert new_panel is not old_panel
assert hasattr(new_panel, 'BBE_OT_backup_settings')
assert bpy.ops.bbe.backup_settings.get_rna_type()
assert bpy.ops.bbe.corvette_export.get_rna_type()
assert bpy.ops.bbe.optimizer_export.get_rna_type()
assert module('builder') is not old_builder
from collections import Counter
for collection in ('depsgraph_update_post', 'load_post', 'undo_post', 'save_pre'):
    handlers = [f.__module__ + '.' + f.__name__ for f in getattr(bpy.app.handlers, collection) if f.__module__.startswith(name+'.')]
    assert all(count == 1 for count in Counter(handlers).values()), (collection, handlers)
print('BBE_UPDATE_RELOAD_PASS', bpy.app.version_string, flush=True)
