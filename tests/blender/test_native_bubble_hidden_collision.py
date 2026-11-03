"""Nearby hidden sockets do not consume the editor's visible open ends."""
import sys
from pathlib import Path

import bpy
from mathutils import Matrix

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_support import addon
from no_mans_sky_base_builder import bubble_preview as ducts


def straight(position):
    obj = addon.BUILDER.add_part('BASE_BUBPIPE').object
    obj['bbe_bubble_shape'] = 'STRAIGHT:Y'
    obj.matrix_world = Matrix.Translation(position)
    return obj


target = straight((0, 0, 0))
neighbor = straight((0, 0, 2))
problem = ducts.placement_error(target, bpy.context.scene)
assert problem is None, problem
count = len(ducts._native_objects(bpy.context.scene))
curve = ducts.add_native_bend_point(addon.BUILDER, target=target)
assert len(ducts._native_objects(bpy.context.scene)) == count + 1
assert curve.object['bbe_bubble_shape'].startswith('ELBOW:')
bpy.data.objects.remove(curve.object, do_unlink=True)

bpy.data.objects.remove(target, do_unlink=True)
bpy.data.objects.remove(neighbor, do_unlink=True)
target = straight((0, 0, 0))
bottom = straight((0, -2, 0))
side = straight((0, 2, 2))
source = addon.BUILDER.add_part('BASE_BUBPIPE').object
source['bbe_bubble_shape'] = 'ELBOW:Bot+Front'
source.matrix_world = Matrix.Translation((20, 0, 0))
before = source.matrix_world.copy()
assert ducts.snap_native(source, target)
assert ducts._editor_contacts([source, target])[source.name]
assert source.get('bbe_bubble_shape') == 'ELBOW:Bot+Front'
print('NATIVE_BUBBLE_HIDDEN_COLLISION_PASS', bpy.app.version_string, flush=True)
