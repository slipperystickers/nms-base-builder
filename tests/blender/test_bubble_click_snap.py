"""Clickable ducts expose fixed visible openings and reject hidden sockets."""
from pathlib import Path
import sys, bpy
from mathutils import Matrix, Vector
sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_support import addon, module, report
v2 = module('builder_v2'); markers = module('snap_markers'); bubble = module('bubble_preview')
s = v2.add_part('BASE_BUBPIPE', builder_object=addon.BUILDER).object
t = v2.add_part('BASE_BUBPIPE', builder_object=addon.BUILDER).object
s['bbe_bubble_shape'] = t['bbe_bubble_shape'] = 'STRAIGHT:Y'
t.matrix_world = v2.X_ROT_90
s.matrix_world = Matrix.Translation((6,0,0)) @ v2.X_ROT_90
bubble.refresh(bpy.context.scene)
for o in bpy.context.selected_objects: o.select_set(False)
s.select_set(True); t.select_set(True); bpy.context.view_layer.objects.active = t
assert markers.start(bpy.context, s, t)
assert {k for k,p in markers.options(s,t)} == {'Top', 'Bot'}
assert bpy.ops.bbe.click_snap_point(target_key='Top') == {'FINISHED'}
assert s.get('bbe_native_target_socket') == 'Top'
assert bubble._joined_sockets(s,t)[0] == 'Top'
previous = s.matrix_world.copy()
assert bpy.ops.bbe.click_snap_point(target_key='Left') == {'CANCELLED'}
assert max(abs(v) for row in previous-s.matrix_world for v in row) < 1e-5
assert bpy.ops.bbe.click_snap_point(target_key='Bot') == {'FINISHED'}
assert bubble._joined_sockets(s,t)[0] == 'Bot'
assert bpy.ops.bbe.click_snap_point(target_key='Bot') == {'FINISHED'}
assert bubble._joined_sockets(s,t)[0] == 'Bot'
report('bubble-click-snap', dict(visible_only=True, click_moves=True, repeat_click=True))
