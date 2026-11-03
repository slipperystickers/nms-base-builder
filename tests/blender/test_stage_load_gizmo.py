"""Exercise real GUI file loads; background mode cannot expose this regression."""
import hashlib
import json
import os
import sys
import traceback
from pathlib import Path

import bpy
from bpy.app.handlers import persistent
from mathutils import Vector

sys.path.insert(0, str(Path(__file__).parent))
from test_support import module, QA

assert not bpy.app.background
source = Path(os.environ.get('BBE_GIZMO_PROJECT', r'G:\nmships\big wheel.blend'))
original_hash = hashlib.sha256(source.read_bytes()).hexdigest()
stage = module('stages')
progress = module('progress_ui')
original_redraw = progress.Activity._redraw
loading = False
redraws = []
rounds = []
baseline = None
result_path = QA / ('stage_load_gizmo_' + bpy.app.version_string.replace(' ', '_')
                    + os.environ.get('BBE_GIZMO_RESULT_SUFFIX', '') + '.json')


@persistent
def before_load(_):
    global loading
    loading = True


@persistent
def after_load(_):
    global loading
    loading = False


def record_redraw(self, *args, **kwargs):
    redraws.append(dict(title=self.title, during_load=loading))
    return original_redraw(self, *args, **kwargs)


progress.Activity._redraw = record_redraw
bpy.app.handlers.load_pre.insert(0, before_load)
bpy.app.handlers.load_post.append(after_load)


def placements():
    return {o.name: [float(v) for row in o.matrix_world for v in row]
            for o in bpy.context.scene.objects if 'ObjectID' in o}


def check():
    global baseline
    try:
        assert not any(r['during_load'] for r in redraws), redraws
        windows = [w for w in bpy.context.window_manager.windows
                   if any(a.type == 'VIEW_3D' for a in w.screen.areas)]
        assert windows
        for window in windows:
            tool = window.workspace.tools.from_space_view3d_mode('OBJECT', create=False)
            assert tool and tool.idname == 'builtin.move'
            assert tool.widget == 'VIEW3D_GGT_xform_gizmo', (tool.idname, tool.widget)
        scene = bpy.context.scene
        assert scene.bbe_stage.enabled and stage.hd_library.scenes_root()
        assert any(o.get(stage.TAG) for o in scene.objects), 'Missing scene preview'
        current = placements()
        assert len(current) == 199
        if baseline is None:
            baseline = current
        assert current == baseline, 'File load changed part placements'
        window = windows[0]
        area = next(a for a in window.screen.areas if a.type == 'VIEW_3D')
        region = next(r for r in area.regions if r.type == 'WINDOW')
        with bpy.context.temp_override(window=window, area=area, region=region):
            for obj in scene.objects:
                obj.select_set(False)
            part = scene.objects['S_CEMENTBAG']
            part.select_set(True)
            bpy.context.view_layer.objects.active = part
            location = part.location.copy()
            world = part.matrix_world.translation.copy()
            bpy.ops.transform.translate(value=(.125, 0, 0), orient_type='GLOBAL')
            bpy.context.view_layer.update()
            assert (part.matrix_world.translation - world - Vector((.125, 0, 0))).length < 1e-5
            part.location = location
            bpy.context.view_layer.update()
            for name in ('builtin.rotate', 'builtin.scale', 'builtin.move'):
                bpy.ops.wm.tool_set_by_id(name=name)
                assert window.workspace.tools.from_space_view3d_mode('OBJECT').widget == 'VIEW3D_GGT_xform_gizmo'
        assert placements() == baseline
        rounds.append(dict(load_ui=len(rounds) != 1, parts=len(current), gizmo=True, translate=True))
        if len(rounds) < 3:
            bpy.ops.wm.open_mainfile(filepath=str(source), load_ui=len(rounds) != 1, use_scripts=False)
            return 2
        # A manual refresh must retain its progress display and working tools.
        count = len(redraws)
        stage.apply(scene)
        assert len(redraws) > count and not any(r['during_load'] for r in redraws)
        assert window.workspace.tools.from_space_view3d_mode('OBJECT').widget == 'VIEW3D_GGT_xform_gizmo'
        assert placements() == baseline
        assert hashlib.sha256(source.read_bytes()).hexdigest() == original_hash
        result_path.write_text(json.dumps(dict(passed=True, version=bpy.app.version_string,
            rounds=rounds, manual_progress=True, source_unchanged=True), indent=2))
        print('STAGE_LOAD_GIZMO_PASS', bpy.app.version_string, flush=True)
    except Exception:
        result_path.write_text(json.dumps(dict(passed=False, rounds=rounds,
            error=traceback.format_exc()), indent=2))
        traceback.print_exc()
    if not os.environ.get('BBE_KEEP_GIZMO_TEST'):
        bpy.ops.wm.quit_blender()
    return None


bpy.ops.wm.open_mainfile(filepath=str(source), load_ui=True, use_scripts=False)
bpy.app.timers.register(check, first_interval=2, persistent=True)
