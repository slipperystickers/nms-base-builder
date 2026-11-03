"""Disposable real-window asset thumbnails, mouse spawn and quality UI check.

Run factory-startup Blender with --enable-event-simulate. No user files opened.
"""
from pathlib import Path
import json
import sys
import traceback
import bpy
from mathutils import Vector
sys.path.insert(0,str(Path(__file__).parent))
from test_support import module,QA
c=module('character_references');grid=module('tools.asset_browser_grid')
state={'step':0,'main':bpy.context.window}
bpy.context.preferences.view.show_splash=False

def finish(passed):
    (QA/'character-references-ui.json').write_text(json.dumps({'pass':passed,'step':state['step']}))
    print('CHARACTER_REFERENCES_UI_PASS' if passed else 'CHARACTER_REFERENCES_UI_FAIL',flush=True)
    bpy.ops.wm.quit_blender()

def main_context():
    window=state['main'];area=next(a for a in window.screen.areas if a.type=='VIEW_3D')
    region=next(r for r in area.regions if r.type=='WINDOW')
    return bpy.context.temp_override(window=window,area=area,region=region)

def click_tile(identifier):
    session=state['grid'];tile=next(t for t in session._tiles if t[4]==identifier)
    region=next(r for r in session._area.regions if r.type=='WINDOW')
    x,y,w,h=tile[:4]
    position=(int(region.x+x+w*.5),int(region.y+region.height-y-h*.5+session._offset))
    window=session._window
    for kind,value in [('MOUSEMOVE','NOTHING'),('LEFTMOUSE','PRESS'),('LEFTMOUSE','RELEASE')]:
        window.event_simulate(type=kind,value=value,x=position[0],y=position[1])

def run():
    try:
        step=state['step']
        if step==0:
            bpy.data.batch_remove(list(bpy.context.scene.objects))
            bpy.context.scene.bbe_detailed_proxies=False
            browser=bpy.context.scene.nms_asset_browser
            browser.initialise_asset_browser()
            browser.asset_browser_caterogies='Character References'
            browser.asset_browser_sub_caterogies='All'
            bpy.ops.object.nms_launch_asset_browser_window(target_width=1200,target_height=900)
        elif step==1:
            if not grid._sessions:return .5
            state['grid']=next(iter(grid._sessions.values()))
            if len(state['grid']._tiles)!=14:return .5
            session=state['grid']
            with bpy.context.temp_override(window=session._window,area=session._area):
                bpy.ops.screen.screenshot(filepath=str(QA/'character-reference-assets-ui.png'))
            click_tile(c.asset_id('ASTRO_ARMOURED','STANDING'))
        elif step==2:
            references=[o for o in bpy.context.scene.objects if o.get(c.TAG)]
            assert len(references)==1 and references[0]['bbe_character_pose']=='STANDING'
            bpy.context.scene.cursor.location=(2.5,0,0)
            click_tile(c.asset_id('GEK_DEFAULT','SEATED'))
        elif step==3:
            references=[o for o in bpy.context.scene.objects if o.get(c.TAG)]
            assert len(references)==2 and any(o['bbe_character_pose']=='SEATED' for o in references)
            for obj in references:
                assert not obj.hide_select and not any(obj.lock_location)
            with main_context():
                space=bpy.context.space_data
                space.show_region_ui=False
                space.region_3d.view_location=(1.25,0,1)
                space.region_3d.view_distance=5.5
                space.region_3d.view_rotation=Vector((3.6,6,2.2)).to_track_quat('Z','Y')
                space.shading.type='SOLID';space.shading.color_type='MATERIAL'
                for obj in references:obj.select_set(True)
                bpy.context.view_layer.objects.active=references[0]
                bpy.ops.transform.translate(value=(.3,0,.2))
                state['matrices']={o.name:o.matrix_world.copy() for o in references}
        elif step==4:
            with main_context():
                bpy.ops.screen.screenshot(filepath=str(QA/'character-reference-spawn-light-ui.png'))
                assert bpy.ops.object.nms_switch_proxies_to_high()=={'FINISHED'}
                next(a for a in state['main'].screen.areas if a.type=='VIEW_3D').spaces.active.shading.type='MATERIAL'
            state['step']+=1
            return 6
        elif step==5:
            references=[o for o in bpy.context.scene.objects if o.get(c.TAG)]
            assert all(o['bbe_character_detailed'] and o.matrix_world==state['matrices'][o.name] for o in references)
            with main_context():
                bpy.ops.screen.screenshot(filepath=str(QA/'character-reference-spawn-detailed-ui.png'))
                assert bpy.ops.object.nms_switch_proxies_to_low()=={'FINISHED'}
            assert not module('builder').Builder().get_all_parts()
            finish(True);return None
        state['step']+=1
        return 2
    except Exception:
        traceback.print_exc();finish(False);return None
bpy.app.timers.register(run,first_interval=2)
