"""Exercise clearing and undo/redo in a real interactive Blender context."""
from pathlib import Path
import sys
import traceback
sys.path.insert(0, str(Path(__file__).parent))
from test_support import *

assert not bpy.app.background
state = {'step': 0}


def check():
    try:
        window = bpy.context.window_manager.windows[0]
        area = next(a for a in window.screen.areas if a.type == 'VIEW_3D')
        region = next(r for r in area.regions if r.type == 'WINDOW')
        with bpy.context.temp_override(window=window, area=area, region=region):
            scene = bpy.context.scene
            if state['step'] == 0:
                parent = bpy.data.collections.new('Undo old build')
                scene.collection.children.link(parent)
                empty = bpy.data.objects.new('Undo old empty', None)
                parent.objects.link(empty)
                obj = module('builder_v2').add_part('BUILDFLATPANEL', high_res=False).object
                obj.parent = empty
                module('tools.asset_browser_operators').browser_pin_object()
                bpy.ops.ed.undo_push(message='Before clear build')
                bpy.ops.object.nms_new_file('EXEC_DEFAULT')
                bpy.ops.ed.undo_push(message='Cleared build')
                assert not any('ObjectID' in o or o.type == 'EMPTY' for o in scene.objects)
            elif state['step'] == 1:
                bpy.ops.ed.undo()
            elif state['step'] == 2:
                assert 'Undo old empty' in scene.objects
                assert 'Undo old build' in scene.collection.children
                assert any('ObjectID' in o for o in scene.objects)
                bpy.ops.ed.redo()
            else:
                assert not any('ObjectID' in o or o.type == 'EMPTY' for o in scene.objects)
                assert 'Undo old build' not in scene.collection.children
                print('CLEAR_BUILD_UNDO_UI_PASS', bpy.app.version_string, flush=True)
                bpy.ops.wm.quit_blender()
                return None
        state['step'] += 1
        return 1
    except Exception:
        traceback.print_exc()
        bpy.ops.wm.quit_blender()
        return None


bpy.app.timers.register(check, first_interval=2)
