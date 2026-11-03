"""Real event-loop move/undo/redo regression in the supplied scene; never save it."""
import hashlib
import json
import os
import sys
import traceback
from pathlib import Path

import bpy

sys.path.insert(0, str(Path(__file__).parent))
from test_support import module, QA

assert not bpy.app.background
source = Path(os.environ.get('BBE_HISTORY_PROJECT', r'G:\nmships\big wheel.blend'))
source_hash = hashlib.sha256(source.read_bytes()).hexdigest()
label = os.environ.get('BBE_HISTORY_LABEL', 'baseline')
result_path = QA / ('part_move_undo_' + label + '.json')
state = {'phase': 0, 'round': 0, 'checks': []}
stage = module('stages')
decals = module('decals')


def placements():
    return {o.name: tuple(float(v) for row in o.matrix_world for v in row)
            for o in bpy.context.scene.objects if o.get('ObjectID')}


def check(expected):
    actual = placements()
    assert actual.keys() == expected.keys(), 'Part membership changed'
    assert all(max(abs(a-b) for a, b in zip(actual[n], expected[n])) < 1e-5
               for n in expected), 'Undo/redo changed part placements'
    obj = bpy.context.scene.objects[state['name']]
    assert obj.select_get() and bpy.context.view_layer.objects.active == obj
    tool = bpy.context.workspace.tools.from_space_view3d_mode('OBJECT')
    assert tool.widget == 'VIEW3D_GGT_xform_gizmo', (tool.idname, tool.widget)
    prefs = bpy.context.preferences
    assert (prefs.view.show_developer_ui, prefs.experimental.use_undo_legacy,
            prefs.is_dirty) == state['preferences'], 'History changed user preferences'


def finish(passed, error=None):
    assert hashlib.sha256(source.read_bytes()).hexdigest() == source_hash
    result_path.write_text(json.dumps(dict(passed=passed, error=error,
        version=bpy.app.version_string, source_unchanged=True, **state), indent=2))
    print('PART_MOVE_UNDO_' + ('PASS' if passed else 'FAIL'), label, flush=True)
    bpy.ops.wm.quit_blender()


def run():
    try:
        phase = state['phase']
        print('PART_HISTORY_PHASE', label, state['round'], phase, flush=True)
        window = next(w for w in bpy.context.window_manager.windows
                      if any(a.type == 'VIEW_3D' for a in w.screen.areas))
        area = next(a for a in window.screen.areas if a.type == 'VIEW_3D')
        region = next(r for r in area.regions if r.type == 'WINDOW')
        with bpy.context.temp_override(window=window, area=area, region=region):
            if phase == 0:
                if os.environ.get('BBE_HISTORY_NO_EFFECTS_TIMER'):
                    bpy.app.timers.unregister(stage.refresh_parts)
                if os.environ.get('BBE_HISTORY_LEGACY'):
                    bpy.context.preferences.view.show_developer_ui = True
                    bpy.context.preferences.experimental.use_undo_legacy = True
                if os.environ.get('BBE_HISTORY_NO_DECALS'):
                    bpy.app.handlers.depsgraph_update_post.remove(decals.changed)
                for obj in bpy.context.scene.objects:
                    obj.select_set(False)
                obj = (bpy.context.scene.objects.get('B_CARRIAGEWHEEL.007') or
                       next(o for o in bpy.context.scene.objects
                            if o.get('ObjectID') == 'B_CARRIAGEWHEEL'))
                obj.select_set(True)
                bpy.context.view_layer.objects.active = obj
                state['name'] = obj.name
                state['before'] = placements()
                print('PART_HISTORY_TARGET', obj.name, 'stage', bpy.context.scene.bbe_stage.enabled, flush=True)
                bpy.ops.wm.tool_set_by_id(name='builtin.move')
                bpy.ops.ed.undo_push(message='Move history fixture')
                prefs = bpy.context.preferences
                state['preferences'] = (prefs.view.show_developer_ui,
                    prefs.experimental.use_undo_legacy, prefs.is_dirty)
            elif phase == 1:
                bpy.ops.transform.translate('EXEC_DEFAULT', True,
                    value=(.204206, 0, 0), orient_type='NORMAL',
                    constraint_axis=(True, False, False))
                bpy.context.view_layer.update()
                state['after'] = placements()
                assert state['after'] != state['before']
            elif phase == 2:
                bpy.ops.ed.undo()
            elif phase == 3:
                check(state['before'])
                bpy.ops.ed.redo()
            elif phase == 4:
                check(state['after'])
                bpy.ops.ed.undo()
            elif phase == 5:
                check(state['before'])
                state['checks'].append(state['round'])
                state['round'] += 1
                if state['round'] == 12:
                    finish(True)
                    return None
                state['phase'] = 1
                return .3 if state['round'] % 2 else 2.0
        state['phase'] += 1
        return .3 if state['round'] % 2 else 2.0
    except Exception:
        error = traceback.format_exc()
        print(error, flush=True)
        finish(False, error)
        return None


bpy.ops.wm.open_mainfile(filepath=str(source), load_ui=True, use_scripts=False)
bpy.app.timers.register(run, first_interval=3, persistent=True)
