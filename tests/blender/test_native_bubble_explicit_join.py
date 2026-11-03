"""Existing straight ducts keep their shape until Join is pressed."""
import sys
from pathlib import Path
import bpy
from mathutils import Matrix

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_support import addon
from no_mans_sky_base_builder import bubble_preview

def add_straight():
    part = addon.BUILDER.add_part('BASE_BUBPIPE')
    part.object['bbe_bubble_shape'] = 'STRAIGHT:Y'
    return part.object

first = add_straight()
second = add_straight()
second.matrix_world = first.matrix_world @ Matrix.Translation((0, 2, 0))
third = add_straight()
third.matrix_world = second.matrix_world @ Matrix.Translation((0, 0, 2))
bpy.context.view_layer.update()
bubble_preview.refresh(bpy.context.scene)
assert second.get('bbe_bubble_shape') == 'STRAIGHT:Y'
assert not str(second.data.get('bbe_native_bubble_preview')).startswith('ELBOW:')
from no_mans_sky_base_builder import bubble_export
payload = addon.BUILDER.serialise()['Objects']
contacts, uncertain = bubble_export.native_contacts({i: bubble_export.frame(p) for i,p in enumerate(payload)})
assert not uncertain
assert all(bubble_export.shape(ports) in [frozenset(p) for p in bubble_export.STRAIGHTS.values()]
           for ports in contacts.values()), 'Export must preserve straight choices before Join'
assert second['bbe_bubble_shape'] == 'STRAIGHT:Y'

bpy.ops.object.select_all(action='DESELECT')
second.select_set(True)
third.select_set(True)
bpy.context.view_layer.objects.active = second
assert bpy.ops.bbe.join_bubble_ducts() == {'FINISHED'}
assert str(second.get('bbe_bubble_shape')).startswith('ELBOW:')
assert first.get('bbe_bubble_shape') == 'STRAIGHT:Y'
assert len(addon.BUILDER.serialise()['Objects']) == 3

fourth = add_straight()
fourth.matrix_world = Matrix.Translation((20, 0, 0))
fifth = add_straight()
fifth.matrix_world = Matrix.Translation((25, 0, 0))
bpy.ops.object.select_all(action='DESELECT')
fourth.select_set(True)
fifth.select_set(True)
bpy.context.view_layer.objects.active = fifth
assert bpy.ops.bbe.join_bubble_ducts() == {'FINISHED'}
assert bubble_preview._snapped([fourth, fifth])[fourth.name]
assert len(addon.BUILDER.serialise()['Objects']) == 5
print('NATIVE_BUBBLE_EXPLICIT_JOIN_PASS', bpy.app.version_string, flush=True)
