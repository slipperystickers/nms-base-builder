"""Undo callbacks must not traverse restored scene objects inside undo_post."""
import sys
import time
from pathlib import Path

import bpy

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_support import addon, module

guard = module('undo_guard')
curve = module('utils.curve')
decals = module('decals')


class RestoringGraph:
    @property
    def updates(self):
        raise AssertionError('Read dependency-graph IDs during history recovery')
data = bpy.data.curves.new('QA curve cache', 'CURVE')
obj = bpy.data.objects.new('QA curve cache', data)
bpy.context.scene.collection.objects.link(obj)
obj[curve.Curve.PROP_CURVE_ID] = 'qa-reseed'

calls = []
original = addon.reset_curve_tracking

def tracked():
    calls.append(True)
    return original()

addon.reset_curve_tracking = tracked
try:
    guard.before_history(None)
    decals.changed(None, RestoringGraph())
    assert decals.tick() == .2
    guard.after_history(None)
    # undo_post has finished, but Blender's discarded update IDs are not safe.
    decals.changed(None, RestoringGraph())
    assert decals.tick() == .2
    assert not calls, 'undo_post traversed scene objects'
    assert not guard.curve_tracking_ready()
    addon.udpates_handler(None, None)  # Pending restore must not read partial IDs.

    # Simulate the later idle callback without waiting for wall-clock time.
    guard._resume_at = time.monotonic() - 1
    assert guard._reseed_curves_when_idle() is None
    assert len(calls) == 1
    assert obj.name in addon.known_curve_names
    assert guard.curve_tracking_ready()
    print('UNDO_CURVE_RESEED_DEFERRED', bpy.app.version_string, flush=True)
finally:
    addon.reset_curve_tracking = original
    guard.unregister()
    guard.register()
    bpy.data.objects.remove(obj, do_unlink=True)
    bpy.data.curves.remove(data)
