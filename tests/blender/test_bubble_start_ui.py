"""Click the rendered tube-card direction and placement buttons in Blender."""
import sys,traceback,json
from pathlib import Path
import bpy
from mathutils import Quaternion,Vector
sys.path.insert(0,str(Path(__file__).resolve().parent))
from test_support import addon,module,QA
print('START_UI_SCRIPT_READY',flush=True)
controls=module('bubble_controls');pr=module('bubble_preview')
state={'step':-1,'buttons':{}}
draw=controls.BBE_GGT_tube_controls.draw_prepare
def capture(self,context):
    draw(self,context)
    for i,(gz,props) in enumerate(self.buttons):
        if not gz.hide:
            p=gz.matrix_basis.translation
            state['buttons'][i]=(int(context.region.x+p.x+gz.width/2),int(context.region.y+p.y+gz.height/2))
controls.BBE_GGT_tube_controls.draw_prepare=capture
def click(i,value):
    x,y=state['buttons'][i]
    bpy.context.window.event_simulate(type='LEFTMOUSE',value=value,x=x,y=y)
def run():
    try:
        s=state['step'];state['step']+=1
        print('START_UI_STEP',s,flush=True)
        if s==-1:
            bpy.context.window.event_simulate(type='ESC',value='PRESS')
            bpy.context.window.event_simulate(type='ESC',value='RELEASE')
            return 1
        if s==0:
            bpy.context.scene.nms_main.new_file();bpy.context.scene.bbe_detailed_proxies=False
            bpy.ops.object.nms_asset_browser_object_selected(object_id='BASE_BUBPIPE')
            state['first']=bpy.context.view_layer.objects.active
            state['matrix']=state['first'].matrix_world.copy()
            area=next(a for a in bpy.context.window.screen.areas if a.type=='VIEW_3D')
            sp=area.spaces.active;sp.show_region_ui=False
            sp.region_3d.view_rotation=Quaternion((1,0,0,0))
            sp.region_3d.view_location=state['first'].matrix_world@Vector((0,1,0))
            sp.region_3d.view_distance=12;sp.region_3d.view_perspective='ORTHO'
            with bpy.context.temp_override(area=area):bpy.ops.wm.tool_set_by_id(name='builtin.move')
            return 2
        if s==1:
            bpy.ops.screen.screenshot(filepath=str(QA/'bubble-start-ui-before.png'))
            assert 18 in state['buttons'],state
            x,y=state['buttons'][18]
            bpy.context.window.event_simulate(type='MOUSEMOVE',value='NOTHING',x=x,y=y)
        elif s==2:click(18,'PRESS')
        elif s==3:click(18,'RELEASE')
        elif s==4:
            assert state['first'].get(pr._START_KEY)=='Right'
            bpy.ops.screen.screenshot(filepath=str(QA/'bubble-start-ui-chosen.png'))
            x,y=state['buttons'][7]
            bpy.context.window.event_simulate(type='MOUSEMOVE',value='NOTHING',x=x,y=y)
        elif s==5:click(7,'PRESS')
        elif s==6:click(7,'RELEASE')
        else:
            parts=pr._native_objects(bpy.context.scene)
            assert len(parts)==2,len(parts)
            second=next(o for o in parts if o!=state['first'])
            assert pr._joined_sockets(second,state['first'])[0]=='Right'
            assert state['first'].matrix_world==state['matrix']
            bpy.ops.screen.screenshot(filepath=str(QA/'bubble-start-ui-after.png'))
            print('BUBBLE_START_UI_PASS',bpy.app.version_string,flush=True)
            bpy.ops.wm.quit_blender();return None
        return .4
    except Exception:
        traceback.print_exc();bpy.ops.wm.quit_blender();return None
bpy.app.timers.register(run,first_interval=2,persistent=True)
