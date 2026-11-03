"""A Blender-only curved proxy must never silently become a straight tube."""
import sys
from pathlib import Path

import bpy

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_support import addon, module


builder_module = module('builder')
builder = addon.BUILDER
bpy.context.scene.nms_main.new_file()

straight = builder.add_part('BASE_BUBPIPE', build_rigs=False)
corner = builder.add_part('BASE_BUBPIPE_L', build_rigs=False)
corner.object.location.x = 2.0

project_objects = builder.serialise(get_presets=True)['Objects']
assert [item['ObjectID'] for item in project_objects] == [
    '^BASE_BUBPIPE', '^BASE_BUBPIPE_L'], project_objects
assert corner.object['ObjectID'] == 'BASE_BUBPIPE_L'
try:
    builder.serialise()
except ValueError as exc:
    assert 'straight tube' in str(exc), str(exc)
else:
    raise AssertionError('Game export silently turned a curved duct into a straight tube')

# Grouped parts join the same output list after their cache is expanded.
grouped = [{'ObjectID': '^BASE_BUBPIPE_L', 'Position': [2, 0, 0]}]
try:
    builder_module.native_placeable_objects(grouped)
except ValueError as exc:
    assert 'straight tube' in str(exc), str(exc)
else:
    raise AssertionError('Grouped curved duct was silently converted')
assert grouped[0]['ObjectID'] == '^BASE_BUBPIPE_L'

bpy.data.objects.remove(corner.object, do_unlink=True)
assert [item['ObjectID'] for item in builder.serialise()['Objects']] == ['^BASE_BUBPIPE']

print('NATIVE_BUBBLE_EXPORT_GUARD_PASS', bpy.app.version_string, flush=True)
