"""Mirrored numbers, visible geometry, and native export agree at both qualities."""
import sys
from pathlib import Path
import bpy
from mathutils import Matrix, Vector
from mathutils.kdtree import KDTree

sys.path.insert(0, str(Path(__file__).parent))
from test_support import addon, module, report

v2 = module('builder_v2')
pivots = module('utils.mirror_pivot')
Part = module('part').Part

def world_points(obj):
    return [obj.matrix_world @ v.co for v in obj.data.vertices]

def nearest_error(expected, actual):
    tree = KDTree(len(expected))
    for i, point in enumerate(expected):
        tree.insert(point, i)
    tree.balance()
    return max(tree.find(point)[2] for point in actual[::max(1, len(actual)//10000)])

checks = []
for high in (False, True):
  for axis in 'XYZ':
    for identity, twin in [('B_STR_J_Y_NE','B_STR_J_Y_NW'),('B_CON_7','B_CON_7')]:
        bpy.context.scene.nms_main.new_file()
        bpy.context.scene.bbe_detailed_proxies = high
        part = v2.add_part(identity, high_res=high)
        obj = part.object
        obj.matrix_world = (Matrix.Translation((4.5154,25.7044,11.9521)) @
                            Matrix.Scale(0.655,4))
        bpy.context.view_layer.update()
        assert pivots.is_normalized(obj)
        before_display = obj.matrix_world.copy()
        before_native = pivots.native_matrix(before_display, identity)
        before_points = world_points(obj)
        bpy.ops.object.select_all(action='DESELECT')
        obj.select_set(True)
        bpy.context.view_layer.objects.active = obj
        op=getattr(bpy.ops.object,'nms_universal_mirror_'+axis.lower())
        assert op() == {'FINISHED'}
        bpy.context.view_layer.update()
        assert obj['ObjectID'] == twin
        expected_origin = before_display.translation.copy()
        expected_origin['XYZ'.index(axis)] *= -1
        origin_error = (obj.matrix_world.translation-expected_origin).length
        expected_points=[]
        for p in before_points:
            q=p.copy();q['XYZ'.index(axis)] *= -1;expected_points.append(q)
        surface_error = nearest_error(expected_points,world_points(obj))
        native_after = pivots.native_matrix(obj.matrix_world,twin)
        exported = Part.deserialise_from_object(obj,v2.BUILDER).serialise()
        export_position = Vector(exported['Position'])
        native_position = (module('part').z_compensate @ native_after).translation
        export_error = (export_position-native_position).length
        assert origin_error < 1e-5,(identity,origin_error)
        assert surface_error < 0.01,(identity,surface_error)
        assert export_error < 1e-5,(identity,export_error)
        assert op() == {'FINISHED'}
        bpy.context.view_layer.update()
        assert obj['ObjectID'] == identity
        assert (obj.matrix_world.translation-before_display.translation).length < 1e-5
        checks.append((high,axis,identity,origin_error,surface_error,export_error))

report('mirror_display_pivots_pass',{'checks':checks})
