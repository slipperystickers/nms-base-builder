import sys, math, time
from pathlib import Path
import bpy
from mathutils import Matrix, Vector
sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_support import module, report
d, ctrl = module('decals'), module('decal_controls')
module('undo_guard').history_ready = lambda: True
for obj in bpy.context.selected_objects: obj.select_set(False)
bpy.context.scene.bbe_detailed_proxies = True
obj = module('builder_v2').add_part('BUILDDECALNUM0', build_rigs=False).object
obj.select_set(True); bpy.context.view_layer.objects.active = obj
target = bpy.data.objects['B_STR_H_Y_NW.023']; face = target.data.polygons[252]
point = target.matrix_world @ face.center
normal = (target.matrix_world.to_3x3().inverted().transposed() @ face.normal).normalized()
obj.matrix_world = Matrix.Diagonal((.265,.265,.265,1))
obj.matrix_world = ctrl.surface_matrix(obj,point,normal)
bpy.context.view_layer.update()
d.refresh(force=True)
bpy.context.view_layer.update(); d.refresh()
calls=[]; original=d.project
def tracked(*args,**kwargs):
    calls.append(args[0].name); return original(*args,**kwargs)
d.project=tracked
t=time.perf_counter()
for _ in range(5): d.refresh()
idle_ms=(time.perf_counter()-t)*200
assert not calls, calls
matrix=obj.matrix_world.copy()
assert bpy.ops.bbe.rotate_decal(degrees=-12.5)=={'FINISHED'}
bpy.context.view_layer.update()
rotated=obj.matrix_world.copy()
assert (rotated.translation-matrix.translation).length < 1e-6
assert abs(matrix.to_quaternion().rotation_difference(rotated.to_quaternion()).angle-math.radians(12.5)) < 1e-5
assert bpy.ops.bbe.rotate_decal(degrees=12.5)=={'FINISHED'}
bpy.context.view_layer.update()
assert max(abs(a-b) for row_a,row_b in zip(matrix,obj.matrix_world) for a,b in zip(row_a,row_b)) < 1e-6
d.refresh(); bpy.context.view_layer.update(); d.refresh(); calls.clear()
display=obj.data
old_vertices=tuple(tuple(v.co) for v in obj.data.vertices)
target.location.x += .04; bpy.context.view_layer.update(); d.refresh()
assert obj.name in calls, 'Moved receiver failed to invalidate preview'
assert obj.data == display, 'Ordinary display ID changed and would rebuild Material Preview'
assert tuple(tuple(v.co) for v in obj.data.vertices) != old_vertices
calls.clear()
assert bpy.ops.bbe.toggle_decal_projection()=={'FINISHED'}
d.refresh(); bpy.context.view_layer.update(); d.refresh()
flat=obj.data
for _ in range(4):
    obj.location.x += .01; bpy.context.view_layer.update(); d.refresh()
    assert obj.data == flat, 'Flat display unnecessarily rebuilt during movement'
assert bpy.ops.bbe.toggle_decal_projection()=={'FINISHED'}
d.refresh()
assert obj.name in calls, 'Enabling projection did not restore projected geometry'
report('decal_refresh_efficiency',{'blender':bpy.app.version_string,'idle_ms':idle_ms,
    'signed_rotation':True,'receiver_invalidation':True,'flat_mesh_reused':True})
print('DECAL_REFRESH_EFFICIENCY_PASS',flush=True)
