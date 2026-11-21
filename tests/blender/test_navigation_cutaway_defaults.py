"""Fresh and returning users, with remembered choices independent of project geometry."""
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_support import bpy, module

memory = module('settings_memory')
scene = bpy.context.scene
pref = memory.preferences()
with TemporaryDirectory() as tmp, patch.object(memory, 'path', return_value=Path(tmp)/'settings.json'):
    memory.unregister()
    memory.register()
    memory.tick()
    assert pref.bbe_wasd_enabled and scene.bbe_cutaway.shown
    assert tuple(scene.bbe_cutaway.handles) == (0., 1.) * 3
    pref.bbe_wasd_enabled = False
    scene.bbe_cutaway.shown = False
    assert memory.path().is_file()
    memory.unregister()
    pref.bbe_wasd_enabled = True
    scene.bbe_cutaway.shown = True
    memory.register()
    memory.tick()
    assert not pref.bbe_wasd_enabled and not scene.bbe_cutaway.shown
    fresh = bpy.data.scenes.new('Another build')
    bpy.context.window.scene = fresh
    memory.tick()
    assert not fresh.bbe_cutaway.shown
    fresh.bbe_cutaway.shown = True
    memory.unregister()
    memory.register()
    memory.tick()
    assert fresh.bbe_cutaway.shown and not pref.bbe_wasd_enabled
print('PASS defaults, independent opt-outs, remembered on re-enable and across scene changes')
