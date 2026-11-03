"""Exercise normal Blender movement and exported cable endpoints on both import paths."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from test_support import module, report
import bpy
from mathutils import Vector, Matrix

builder = module('builder').get_builder()
v2 = module('builder_v2')
families = ('U_POWERLINE', 'U_BYTEBEATLINE', 'U_PIPELINE', 'U_PORTALLINE')
delta = Vector((2.5, -3, 1.25))
game_delta = Matrix.Rotation(-1.5707963267948966, 3, 'X') @ delta
checks = []

def close(a, b):
    assert (Vector(a) - Vector(b)).length < 0.0001, (list(a), list(b))

for label, importer in [('simple', builder.deserialise_from_data), ('detailed', v2.deserialise_from_data)]:
    bpy.data.batch_remove(list(bpy.data.objects))
    builder.clear_caches()
    records = [dict(ObjectID='^'+part_id, Position=[i*10, 0, 0], Up=[0, 1, 0], At=[0, 0, 5], UserData=0, Timestamp=0)
               for i, part_id in enumerate(families + ('BASE_FLAG', 'U_PARAGON'))]
    importer({'BaseVersion': 8, 'Objects': records})
    bpy.context.view_layer.update()
    wires = [builder.get_builder_object_from_bpy_object(o) for o in bpy.context.scene.objects if o.get('ObjectID') in families]
    snapshots = {p.name: p.serialise() for p in wires}
    flag = next(o for o in bpy.context.scene.objects if o.get('ObjectID') == 'BASE_FLAG')
    flag_matrix = flag.matrix_world.copy()
    bpy.ops.object.select_all(action='SELECT')
    assert all(bpy.data.objects[p.start_control].select_get() and bpy.data.objects[p.end_control].select_get() for p in wires)
    bpy.ops.transform.translate(value=delta)
    bpy.context.view_layer.update()
    for p in wires:
        before, after = snapshots[p.name], p.serialise()
        close(after['Position'], Vector(before['Position']) + game_delta)
        close(after['At'], before['At'])
        close(after['Up'], before['Up'])
    close(flag.matrix_world.translation, flag_matrix.translation)
    checks.append(label + ': all four cable families move with Select All; export direction/length preserved; flag anchored')

    # The visible cable alone does not include its independently editable ends.
    p = wires[0]
    bpy.ops.object.select_all(action='DESELECT')
    p.object.select_set(True)
    bpy.context.view_layer.objects.active = p.object
    before = p.serialise()
    bpy.ops.transform.translate(value=delta)
    bpy.context.view_layer.update()
    close(p.serialise()['Position'], before['Position'])
    checks.append(label + ': mesh-only selection reproduces immobile cable')

    # Intentional endpoint adjustment must remain available for circuit editing.
    bpy.ops.object.select_all(action='DESELECT')
    ctrl = bpy.data.objects[p.end_control]
    ctrl.select_set(True)
    bpy.context.view_layer.objects.active = ctrl
    start_before = bpy.data.objects[p.start_control].matrix_world.translation.copy()
    end_before = ctrl.matrix_world.translation.copy()
    bpy.ops.transform.translate(value=delta)
    bpy.context.view_layer.update()
    close(ctrl.matrix_world.translation, end_before + delta)
    close(bpy.data.objects[p.start_control].matrix_world.translation, start_before)
    checks.append(label + ': individual endpoint adjustment remains available')

report('line_selection_move', {'blender': bpy.app.version_string, 'checks': checks})
print('LINE_SELECTION_MOVE_PASS', flush=True)
