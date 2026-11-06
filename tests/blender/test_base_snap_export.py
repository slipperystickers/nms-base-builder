"""Native base/freighter placement preserves simple/HD geometry and export frames."""
from pathlib import Path
import sys
import bpy
from mathutils import Matrix
sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_support import addon, module, report

v2 = module('builder_v2')
pivot = module('utils.mirror_pivot')
markers = module('snap_markers')
rows = []
for high_res in (False, True):
    for sid, tid in [('W_WALL', 'W_FLOOR'), ('CUBEROOM', 'CUBEROOM'),
                     ('FRE_ROOM_B', 'FRE_ROOM_B'), ('FRE_FACE_WINDOW', 'FRE_CORR_A')]:
        bpy.context.scene.bbe_detailed_proxies = high_res
        source = v2.add_part(sid, build_rigs=False, high_res=high_res)
        target = v2.add_part(tid, build_rigs=False, high_res=high_res)
        native = Matrix.Translation((12, 3, 7)) @ Matrix.Rotation(.7, 4, 'Z') @ v2.X_ROT_90 @ Matrix.Scale(.25, 4)
        target.matrix_world = pivot.display_matrix(native, tid) if pivot.is_normalized(target.object) else native
        before = target.matrix_world.copy()
        meshes = source.object.data, target.object.data
        for obj in bpy.context.selected_objects: obj.select_set(False)
        source.object.select_set(True); target.object.select_set(True)
        bpy.context.view_layer.objects.active = target.object
        assert bpy.ops.object.nms_snap() == {'FINISHED'}, (sid, tid, high_res)
        points = markers.options(source.object, target.object)
        assert points
        assert bpy.ops.bbe.click_snap_point(target_key=points[-1][0]) == {'FINISHED'}
        exported = v2.deserialise_matrix_world(source.serialise())
        expected = pivot.native_matrix(source.matrix_world, sid, normalized=pivot.is_normalized(source.object))
        assert max(abs(v) for row in exported-expected for v in row) < 1e-4, (sid, high_res)
        target_error = max(abs(v) for row in target.matrix_world-before for v in row)
        assert target_error < 1e-5, (sid, tid, high_res, target_error, before, target.matrix_world)
        assert (source.object.data, target.object.data) == meshes
        assert source.serialise()['ObjectID'] == '^'+sid
        rows.append(dict(source=sid, target=tid, high_res_requested=high_res,
                         selectable=not source.object.hide_select, points=len(points),
                         native_export_matches=True, meshes_unchanged=True))
        bpy.data.objects.remove(source.object, do_unlink=True)
        bpy.data.objects.remove(target.object, do_unlink=True)
report('base_snap_export', rows)
