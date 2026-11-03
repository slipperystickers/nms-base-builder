import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from test_support import addon, module, QA
import bpy
from mathutils import Vector
bpy.ops.wm.open_mainfile(filepath=str(QA/'Base_Move_Review.blend'), load_ui=False, use_scripts=False)
wire = module('wire_selection')
bpy.context.preferences.edit.use_global_undo = True
for o in bpy.context.scene.objects:
    o.select_set(o.get('ObjectID') not in {'BASE_FLAG', 'U_PARAGON'} and o.visible_get())
bpy.context.view_layer.objects.active = bpy.data.objects['MAINROOM']
wire.refresh_selection()
before = {o.name:o.matrix_world.translation.copy() for o in bpy.context.scene.objects}
selected = {o.name for o in bpy.context.selected_objects}
bpy.ops.ed.undo_push(message='Before complete base move')
bpy.ops.transform.translate(value=(2, 0, 0))
bpy.context.view_layer.update()
bpy.ops.ed.undo_push(message='After complete base move')
assert bpy.ops.ed.undo() == {'FINISHED'}
bpy.context.view_layer.update()
for o in bpy.context.scene.objects:
    assert (o.matrix_world.translation-before[o.name]).length < 0.0001, o.name
assert all(not any(o.lock_location) for o in bpy.context.scene.objects if o.get('ObjectID') in wire.LINE_IDS)
assert bpy.ops.ed.redo() == {'FINISHED'}
bpy.context.view_layer.update()
for o in bpy.context.scene.objects:
    expected = Vector((2, 0, 0)) if o.name in selected else Vector()
    assert (o.matrix_world.translation-before[o.name]-expected).length < 0.0001, o.name
print('WIRE_GIZMO_UNDO_REDO_PASS', bpy.app.version_string, flush=True)
