"""Toggle from different decals, including old per-object overrides and new placements."""
from pathlib import Path
import sys
import time

import bpy
from mathutils import Matrix

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_support import module

# Installed extensions defer preview updates briefly after Blender loads a file.
guard = module('undo_guard')
deadline = time.monotonic() + 5
while not guard.history_ready() and time.monotonic() < deadline:
    time.sleep(.05)
assert guard.history_ready()

decals = module('decals')
builder = module('builder_v2')
scene = bpy.context.scene
scene.bbe_detailed_proxies = True


def place(part):
    obj = builder.add_part(part, high_res=True, build_rigs=False).object
    obj.matrix_world = Matrix.Identity(4)
    return obj


def toggle(obj):
    for selected in bpy.context.selected_objects:
        selected.select_set(False)
    bpy.context.view_layer.objects.active = obj
    obj.select_set(True)
    assert bpy.ops.bbe.toggle_decal_projection() == {'FINISHED'}


def check(objects, *, flat):
    bpy.context.view_layer.update()
    decals.refresh()
    for obj in objects:
        assert bool(obj.data.get('bbe_decal_floating')) == flat, obj.name
        assert (receiver.name in obj.data['bbe_decal_receivers']) != flat, obj.name


mesh = bpy.data.meshes.new('Decal receiver')
mesh.from_pydata([(-2, 0, -2), (-2, 0, 2), (2, 0, 2), (2, 0, -2)], [], [(0, 1, 2, 3)])
mesh.update()
receiver = bpy.data.objects.new('Decal receiver', mesh)
receiver['ObjectID'] = 'BUILDWALL'
scene.collection.objects.link(receiver)
objects = [place(part) for part in ('BUILDDECALNUM0', 'BUILDDECALNUM3')]
for obj, old_setting in zip(objects, (True, False)):
    obj['bbe_decal_projection_disabled'] = old_setting
check(objects, flat=False)
toggle(objects[0])
check(objects, flat=True)
objects.append(place('BUILDDECALNUM1'))
check(objects, flat=True)
toggle(objects[-1])
check(objects, flat=False)
print('GLOBAL DECAL PREVIEW PASS', bpy.app.version_string)
