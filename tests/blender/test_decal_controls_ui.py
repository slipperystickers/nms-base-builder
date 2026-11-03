"""Exercise actual gizmo buttons, surface picking, cancellation and undo."""
import sys
import traceback
from pathlib import Path

import bpy
from mathutils import Matrix
from bpy_extras.view3d_utils import location_3d_to_region_2d, region_2d_to_origin_3d, region_2d_to_vector_3d

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_support import module, QA
ctrl, decals = module('decal_controls'), module('decals')
state = {'step': -1, 'buttons': {}}
original_draw = ctrl.BBE_GGT_decal_controls.draw_prepare

def capture(self, context):
    original_draw(self, context)
    for index, (button, _) in enumerate(self.buttons):
        p = button.matrix_basis.translation
        state['buttons'][index] = (int(context.region.x+p.x+button.width/2),
                                    int(context.region.y+p.y+button.height/2))
ctrl.BBE_GGT_decal_controls.draw_prepare = capture

def event(kind, value, xy):
    bpy.context.window.event_simulate(type=kind, value=value, x=int(xy[0]), y=int(xy[1]))

def run():
    try:
        step = state['step']; state['step'] += 1
        print('DECAL_UI_STEP', step, flush=True)
        if step == -1:
            event('ESC', 'PRESS', (0, 0)); event('ESC', 'RELEASE', (0, 0))
        elif step == 0:
            bpy.context.scene.bbe_detailed_proxies = True
            target = bpy.data.objects['B_STR_H_Y_NW.023']
            face = target.data.polygons[252]
            point = target.matrix_world @ face.center
            normal = (target.matrix_world.to_3x3().inverted().transposed() @ face.normal).normalized()
            for obj in bpy.context.selected_objects: obj.select_set(False)
            obj = module('builder_v2').add_part('BUILDDECALNUM0', user_data=1, build_rigs=False).object
            obj.matrix_world = Matrix.Diagonal((.265, .265, .265, 1))
            obj.matrix_world = ctrl.surface_matrix(obj, point, normal, offset=.05)
            obj.select_set(True); bpy.context.view_layer.objects.active = obj
            state.update(name=obj.name, original=obj.matrix_world.copy(), point=point)
            area = next(a for a in bpy.context.window.screen.areas if a.type == 'VIEW_3D')
            region = next(r for r in area.regions if r.type == 'WINDOW')
            state.update(area=area, region=region)
            space = area.spaces.active
            space.show_region_ui = False
            space.region_3d.view_location = point
            space.region_3d.view_rotation = normal.to_track_quat('Z', 'Y')
            space.region_3d.view_distance = 3
            space.region_3d.view_perspective = 'ORTHO'
            space.shading.type = 'SOLID'
            space.overlay.show_floor = False
            bpy.ops.ed.undo_push(message='Decal test fixture')
            return 3
        elif step == 1:
            bpy.ops.screen.screenshot(filepath=str(QA/'decal-controls-projected.png'))
            assert 5 in state['buttons']
            state['button_start'] = dict(state['buttons'])
            event('MOUSEMOVE', 'NOTHING', state['buttons'][5])
        elif step == 2: event('LEFTMOUSE', 'PRESS', state['buttons'][5])
        elif step == 3: event('LEFTMOUSE', 'RELEASE', state['buttons'][5]); return 2
        elif step == 4:
            obj = bpy.data.objects[state['name']]
            assert obj.get(decals.PREVIEW_DISABLED)
            assert obj.data.get('bbe_decal_floating')
            assert obj.matrix_world == state['original']
            bpy.ops.screen.screenshot(filepath=str(QA/'decal-controls-flat.png'))
            event('MOUSEMOVE', 'NOTHING', state['buttons'][0])
        elif step == 5: event('LEFTMOUSE', 'PRESS', state['buttons'][0])
        elif step == 6: event('LEFTMOUSE', 'RELEASE', state['buttons'][0])
        elif step == 7:
            region, area = state['region'], state['area']
            xy = location_3d_to_region_2d(region, area.spaces.active.region_3d, state['point'])
            state['pick'] = (region.x+xy.x, region.y+xy.y)
            with bpy.context.temp_override(area=area, region=region):
                hit = ctrl.surface_hit(bpy.context,
                    region_2d_to_origin_3d(region, area.spaces.active.region_3d, xy),
                    region_2d_to_vector_3d(region, area.spaces.active.region_3d, xy))
            assert hit, 'No visible surface under the test click'
            state['expected_pick'] = hit[0] + hit[1]*.002
            print('PICK_VISIBLE_SURFACE', hit[2].name, tuple(hit[0]), flush=True)
            event('MOUSEMOVE', 'NOTHING', state['pick'])
        elif step == 8: event('LEFTMOUSE', 'PRESS', state['pick'])
        elif step == 9: event('LEFTMOUSE', 'RELEASE', state['pick']); return 2
        elif step == 10:
            obj = bpy.data.objects[state['name']]
            assert (obj.matrix_world.translation-state['expected_pick']).length < .003, (tuple(obj.matrix_world.translation), tuple(state['expected_pick']))
            state['placed'] = obj.matrix_world.copy()
            assert state['buttons'] == state['button_start'], 'Panel moved during placement'
            with bpy.context.temp_override(area=state['area'], region=state['region']):
                bpy.ops.ed.undo()
            return 2
        elif step == 11:
            obj = bpy.data.objects[state['name']]
            assert (obj.matrix_world.translation-state['original'].translation).length < 1e-5
            with bpy.context.temp_override(area=state['area'], region=state['region']):
                bpy.ops.ed.redo()
            return 2
        elif step == 12:
            assert (bpy.data.objects[state['name']].matrix_world.translation-state['placed'].translation).length < 1e-5
            event('MOUSEMOVE', 'NOTHING', state['buttons'][1])
        elif step == 13: event('LEFTMOUSE', 'PRESS', state['buttons'][1])
        elif step == 14: event('LEFTMOUSE', 'RELEASE', state['buttons'][1])
        elif step == 15: event('MOUSEMOVE', 'NOTHING', (state['pick'][0]+80, state['pick'][1]+40))
        elif step == 16:
            assert (bpy.data.objects[state['name']].matrix_world.translation-state['placed'].translation).length > .01, 'Free Move did not move the decal'
            assert decals.transform_active(), 'Native move was not active'
            display = bpy.data.objects[state['name']].data
            assert decals.refresh() == 0
            assert bpy.data.objects[state['name']].data == display, 'Preview rebuilt during a drag'
            event('ESC', 'PRESS', state['pick']); event('ESC', 'RELEASE', state['pick']); return 2
        elif step == 17:
            assert (bpy.data.objects[state['name']].matrix_world.translation-state['placed'].translation).length < 1e-5
            event('MOUSEMOVE', 'NOTHING', state['buttons'][2])
        elif step == 18: event('LEFTMOUSE', 'PRESS', state['buttons'][2])
        elif step == 19: event('LEFTMOUSE', 'RELEASE', state['buttons'][2])
        elif step == 20:
            bpy.ops.screen.screenshot(filepath=str(QA/'decal-rotation-dialog.png'))
            event('ESC', 'PRESS', state['buttons'][2]); event('ESC', 'RELEASE', state['buttons'][2])
        elif step == 21:
            print('DECAL_CONTROLS_UI_PASS', bpy.app.version_string, flush=True)
            bpy.ops.wm.quit_blender(); return None
        return .4
    except Exception:
        traceback.print_exc(); bpy.ops.wm.quit_blender(); return None
bpy.app.timers.register(run, first_interval=2)
