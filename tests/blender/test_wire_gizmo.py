import sys, time, hashlib
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from test_support import addon, module, QA, report
import bpy
from mathutils import Vector

assert addon._core_registered
wire = module('wire_selection')
fixture = Path('C:/Users/kengo/Downloads/base.blend')
original_hash = hashlib.sha256(fixture.read_bytes()).hexdigest()
bpy.ops.wm.open_mainfile(filepath=str(fixture), load_ui=False, use_scripts=False)
layer = bpy.context.view_layer
lines = [o for o in bpy.context.scene.objects if o.get('ObjectID') in wire.LINE_IDS]
assert len(lines) == 3
for obj in bpy.context.scene.objects:
    obj.select_set(obj.get('ObjectID') not in {'BASE_FLAG', 'U_PARAGON'} and obj.visible_get())
layer.objects.active = bpy.data.objects['MAINROOM']
layer.update()
wire.refresh_selection()
assert all(not any(o.lock_location) for o in lines)
assert all(all(o.lock_rotation) and all(o.lock_scale) for o in lines)
snapshots = {o.name:o.matrix_world.copy() for o in bpy.context.scene.objects}
delta = Vector((4, -7, 3))
bpy.ops.transform.translate(value=delta)
layer.update()
for obj in bpy.context.scene.objects:
    expected = delta if obj.select_get() else Vector()
    assert (obj.matrix_world.translation - snapshots[obj.name].translation - expected).length < 0.0001, obj.name

line = lines[0]
end = bpy.data.objects[line['end_control']]
end.select_set(False)
layer.update()
wire.refresh_selection()
assert all(line.lock_location), 'An incomplete cable selection must stay protected'
end.select_set(True)
end.lock_location[0] = True
wire.refresh_selection()
assert all(line.lock_location), 'A locked endpoint must not enable cable movement'
end.lock_location[0] = False
wire.refresh_selection()
assert not any(line.lock_location)

# Do not silently replace a manually configured lock pattern.
del line[wire.TAG]
line.lock_location = (True, False, True)
wire.invalidate(); wire.refresh_selection()
assert tuple(line.lock_location) == (True, False, True)
line.lock_location = (True, True, True)
wire.invalidate(); wire.refresh_selection()
assert not any(line.lock_location)

wire.before_save()
assert all(all(o.lock_location) for o in lines)
wire.after_save()
assert all(not any(o.lock_location) for o in lines)
copy = QA/'base_gizmo_saved.blend'
bpy.ops.wm.save_as_mainfile(filepath=str(copy))
assert all(not any(o.lock_location) for o in lines)
wire.unregister()
assert all(all(o.lock_location) for o in lines)
bpy.ops.wm.open_mainfile(filepath=str(copy), load_ui=False, use_scripts=False)
lines = [o for o in bpy.context.scene.objects if o.get('ObjectID') in wire.LINE_IDS]
assert all(all(o.lock_location) for o in lines), 'Saved file must remain protected without the handler'
wire.register()
assert all(not any(o.lock_location) for o in lines)

# Selection updates have no network calls, timers or scene geometry rebuilds.
start = time.perf_counter()
for _ in range(1000): wire.refresh_selection()
ms = (time.perf_counter()-start)
assert hashlib.sha256(fixture.read_bytes()).hexdigest() == original_hash
report('wire_gizmo', dict(blender=bpy.app.version_string, lines=len(lines), average_refresh_ms=ms,
                         checks=['whole-base movement', 'incomplete selection', 'locked endpoint',
                                 'custom locks', 'save/reopen', 'disable/re-enable', 'source unchanged']))
print('WIRE_GIZMO_PASS', flush=True)
