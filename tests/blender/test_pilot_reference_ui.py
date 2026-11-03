"""Actual gizmo click, character selection and undo UI test, isolated profile."""
from pathlib import Path
import sys, traceback, json, math
import bpy
from mathutils import Quaternion, Vector
sys.path.insert(0,str(Path(__file__).parent))
from test_support import module, QA
p=module('pilot_reference')
original_asset_path=p.asset_path
p.asset_path=lambda race,detailed: (Path(p.__file__).parent/'resources/hd_additions/pilot_references'/f'{race}.blend'
                                   if detailed else original_asset_path(race,detailed))
state={'step':-1,'buttons':{}}
draw=p.BBE_GGT_pilot_reference.draw_prepare
def capture(self,context):
    draw(self,context)
    for i,(button,_) in enumerate(self.buttons):
        xy=button.matrix_basis.translation
        state['buttons'][i]=(int(context.region.x+xy.x+button.width/2),int(context.region.y+xy.y+button.height/2))
p.BBE_GGT_pilot_reference.draw_prepare=capture

def event(kind,value,xy):
    bpy.context.window.event_simulate(type=kind,value=value,x=xy[0],y=xy[1])
def click(i,value):event('LEFTMOUSE',value,state['buttons'][i])
def finish(ok):
    (QA/'pilot-ui-result.json').write_text(json.dumps({'pass':ok,'step':state['step']}))
    print('PILOT_UI_PASS' if ok else 'PILOT_UI_FAIL',flush=True)
    bpy.ops.wm.quit_blender()

def run():
    try:
        s=state['step'];state['step']+=1
        if s==-1:
            event('ESC','PRESS',(0,0));event('ESC','RELEASE',(0,0))
        elif s==0:
            bpy.ops.object.select_all(action='SELECT');bpy.ops.object.delete(use_global=False)
            obj=module('builder_v2').add_part('B_COK_D',build_rigs=False).object
            obj.location=(0,0,0);obj.scale=(.04,)*3
            for other in bpy.context.selected_objects:other.select_set(False)
            obj.select_set(True);bpy.context.view_layer.objects.active=obj
            bpy.context.view_layer.update()
            state['cockpit_name']=obj.name
            area=next(a for a in bpy.context.screen.areas if a.type=='VIEW_3D')
            state['area']=area;state['region']=next(r for r in area.regions if r.type=='WINDOW')
            space=area.spaces.active;space.show_region_ui=False
            space.show_gizmo=True;space.show_gizmo_context=True
            space.region_3d.view_location=(0,0,.65);space.region_3d.view_distance=3.8
            space.region_3d.view_rotation=Vector((3,-6,2)).to_track_quat('Z','Y')
            space.shading.type='SOLID';space.shading.color_type='MATERIAL'
            bpy.ops.ed.undo_push(message='Pilot test start')
            return 3
        elif s==1:
            print('PILOT_UI_POLL',p.BBE_GGT_pilot_reference.poll(bpy.context),bpy.context.active_object,len(bpy.context.selected_objects),flush=True)
            bpy.ops.screen.screenshot(filepath=str(QA/'pilot-picker-start.png'))
            assert 1 in state['buttons']
            assert not [o for o in bpy.context.scene.objects if o.get(p.TAG)]
            bpy.ops.screen.screenshot(filepath=str(QA/'pilot-picker-empty.png'))
            event('MOUSEMOVE','NOTHING',state['buttons'][1])
        elif s==2:click(1,'PRESS')
        elif s==3:click(1,'RELEASE');return 1
        elif s==4:
            model=p.preview(bpy.context);assert model and model[p.RACE]=='GEK_DEFAULT'
            state['model_name']=model.name
            for o in bpy.context.selected_objects:o.select_set(False)
            model.select_set(True);bpy.context.view_layer.objects.active=model
            assert p.BBE_GGT_pilot_reference.poll(bpy.context)
            return 1
        elif s==5:
            bpy.ops.screen.screenshot(filepath=str(QA/'pilot-picker-selected-gek.png'))
            event('MOUSEMOVE','NOTHING',state['buttons'][3])
        elif s==6:click(3,'PRESS')
        elif s==7:click(3,'RELEASE');return 1
        elif s==8:
            model=p.preview(bpy.context);assert model[p.RACE]=='VYKEEN_DEFAULT'
            assert len([o for o in bpy.context.scene.objects if o.get(p.TAG)])==1
            bpy.ops.screen.screenshot(filepath=str(QA/'pilot-picker-selected-vykeen.png'))
            with bpy.context.temp_override(area=state['area'],region=state['region']):bpy.ops.ed.undo()
            return 2
        elif s==9:
            model=p.preview(bpy.context);assert model and model[p.RACE]=='GEK_DEFAULT'
            with bpy.context.temp_override(area=state['area'],region=state['region']):bpy.ops.ed.redo()
            return 2
        elif s==10:
            model=p.preview(bpy.context);assert model and model[p.RACE]=='VYKEEN_DEFAULT'
            assert len(state['buttons'])==len(p.RACES)+2, 'Pilot picker must not have a separate quality toggle'
            assert bpy.ops.object.nms_switch_proxies_to_high()=={'FINISHED'}
            return 1
        elif s==11:
            event('MOUSEMOVE','NOTHING',state['buttons'][6]);click(6,'PRESS')
        elif s==12:click(6,'RELEASE');return 1
        elif s==13:
            assert p.preview(bpy.context)[p.DETAIL]
            assert p.preview(bpy.context)[p.RACE]=='ASTRO_ARMOURED'
            bpy.ops.screen.screenshot(filepath=str(QA/'pilot-picker-detailed.png'))
            finish(True);return None
        return .4
    except Exception:
        traceback.print_exc();finish(False);return None
bpy.app.timers.register(run,first_interval=2)
