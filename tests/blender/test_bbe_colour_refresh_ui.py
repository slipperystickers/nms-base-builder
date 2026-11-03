import sys,traceback
from pathlib import Path
import bpy
sys.path.insert(0,str(Path(__file__).resolve().parent))
from test_support import addon,module,QA
state={'step':0}
f=module('save_editor.save_editor_presentation')

def run():
    try:
        s=state['step'];state['step']+=1
        area=next(a for a in bpy.context.window.screen.areas if a.type=='VIEW_3D')
        region=next(r for r in area.regions if r.type=='WINDOW')
        if s==0:
            bpy.context.window.event_simulate(type='ESC',value='PRESS');bpy.context.window.event_simulate(type='ESC',value='RELEASE')
        elif s==1:
            obj=bpy.context.active_object;obj['ObjectID']='BASE_BUBPIPE';obj['UserData']=3
            addon.sync_selected_palette(bpy.context)
            with bpy.context.temp_override(area=area,region=region):
                bpy.ops.wm.call_panel(name='VIEW3D_PT_bbe_toolbar_color',keep_open=True)
        elif s==2:
            bpy.ops.screen.screenshot(filepath=str(QA/'bbe-selected-colour-ui.png'))
            bpy.context.window.event_simulate(type='ESC',value='PRESS');bpy.context.window.event_simulate(type='ESC',value='RELEASE')
        elif s==3:
            with bpy.context.temp_override(area=area,region=region):f.prompt_save_refresh('The save changed. Refresh the save list before continuing.')
        elif s==4:
            bpy.ops.screen.screenshot(filepath=str(QA/'bbe-refresh-attention-ui.png'))
            bpy.context.window.event_simulate(type='ESC',value='PRESS');bpy.context.window.event_simulate(type='ESC',value='RELEASE')
        elif s==5:
            with bpy.context.temp_override(area=area,region=region):bpy.ops.wm.call_panel(name='VIEW3D_PT_nms_io_panel',keep_open=True)
        elif s==6:
            bpy.ops.screen.screenshot(filepath=str(QA/'bbe-refresh-dismissed-ui.png'))
            print('BBE_COLOUR_REFRESH_UI_PASS',bpy.app.version_string,flush=True);bpy.ops.wm.quit_blender();return None
        return 1
    except Exception:
        traceback.print_exc();bpy.ops.wm.quit_blender();return None
bpy.app.timers.register(run,first_interval=2)
