"""The last legacy mirror offset moves to the display pivot without visual drift."""
import sys
from pathlib import Path

import bpy
from mathutils import Matrix, Vector

sys.path.insert(0, str(Path(__file__).parent))
from test_support import addon, module, report

v2 = module('builder_v2')
pivots = module('utils.mirror_pivot')
Part = module('part').Part

checks = []
identity = 'STORAGEPANEL'
offset = 0.05444555
for high in (False, True):
    for axis in 'XYZ':
        bpy.context.scene.nms_main.new_file()
        bpy.context.scene.bbe_detailed_proxies = high
        obj = v2.add_part(identity, high_res=high).object
        obj.matrix_world = Matrix.Translation((4.5154, 25.7044, 11.9521)) @ Matrix.Scale(0.655, 4)
        bpy.context.view_layer.update()
        assert pivots.is_normalized(obj)
        original_display = obj.matrix_world.copy()
        original_native = pivots.native_matrix(original_display, identity)
        native_vertices = [v.co - pivots.pivot(identity) for v in obj.data.vertices]
        world = Matrix.Identity(4)
        world['XYZ'.index(axis)]['XYZ'.index(axis)] = -1.0
        native_relation = Matrix.Diagonal((-1.0, 1.0, 1.0, 1.0)) @ Matrix.Translation((offset, 0, 0))
        expected_native = world @ original_native @ native_relation
        expected_world = [expected_native @ p for p in native_vertices]
        bpy.ops.object.select_all(action='DESELECT')
        obj.select_set(True)
        bpy.context.view_layer.objects.active = obj
        op = getattr(bpy.ops.object, 'nms_universal_mirror_' + axis.lower())
        assert op() == {'FINISHED'}
        bpy.context.view_layer.update()
        actual_world = [obj.matrix_world @ v.co for v in obj.data.vertices]
        shape_error = max((a-b).length for a,b in zip(actual_world, expected_world))
        origin = original_display.translation.copy()
        origin['XYZ'.index(axis)] *= -1
        origin_error = (obj.matrix_world.translation - origin).length
        exported = Part.deserialise_from_object(obj, v2.BUILDER).serialise()
        native_after = pivots.native_matrix(obj.matrix_world, identity)
        export_error = (Vector(exported['Position']) - (module('part').z_compensate @ native_after).translation).length
        assert shape_error < 1e-5, (high, axis, shape_error)
        assert origin_error < 1e-5, (high, axis, origin_error)
        assert export_error < 1e-5, (high, axis, export_error)
        checks.append([high, axis, shape_error, origin_error, export_error])

report('storagepanel_mirror_pivot_pass', {'checks': checks})
