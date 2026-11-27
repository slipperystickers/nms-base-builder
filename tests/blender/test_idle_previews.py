"""Idle previews must still follow scene edits, shared objects and proxy quality."""
from pathlib import Path
import sys
import time
from unittest.mock import patch

import bpy

sys.path.insert(0, str(Path(__file__).parent))
from test_support import module

bubble = module('bubble_preview')
habs = module('hab_windows')
scene = bpy.context.scene
space = next(area.spaces.active for area in bpy.context.screen.areas if area.type == 'VIEW_3D')
space.shading.type = 'SOLID'
space.shading.color_type = 'SINGLE'


def update():
    bpy.context.view_layer.update()
    habs.tick()
    bubble._sync_draft_shading(cached=True)


# An enabled extension receives load_post at startup. Wait for the same
# history guard as the interactive preview timer before measuring refreshes.
guard = module('undo_guard')
deadline = time.monotonic() + 5
while not guard.history_ready() and time.monotonic() < deadline:
    time.sleep(.05)
assert guard.history_ready()
habs.loaded(None)
bubble._reset_draft_cache()
with patch.object(habs, 'refresh', wraps=habs.refresh) as refresh:
    update()
    initial = refresh.call_count
    assert initial > 0
    for _ in range(10):
        habs.tick()
    assert refresh.call_count == initial

    mesh = bpy.data.meshes.new('Draft')
    mesh['bbe_bubble_draft'] = True
    obj = bpy.data.objects.new('Draft', mesh)
    scene.collection.objects.link(obj)
    update()
    assert refresh.call_count > initial
    assert space.shading.color_type == 'MATERIAL'

    initial = refresh.call_count
    obj.location.x += 1
    update()
    assert refresh.call_count > initial

    initial = refresh.call_count
    scene.bbe_detailed_proxies = not scene.bbe_detailed_proxies
    habs.tick()
    assert refresh.call_count > initial

    shared = bpy.data.scenes.new('Shared')
    shared.collection.objects.link(obj)
    update()
    assert shared.session_uid in habs._checked_quality
    bpy.data.objects.remove(obj, do_unlink=True)
    update()
    assert space.shading.color_type == 'SINGLE'
    assert not bubble._scene_has_draft[scene.session_uid]
