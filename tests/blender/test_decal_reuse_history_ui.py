import sys,traceback
from pathlib import Path
import bpy
sys.path.insert(0,str(Path(__file__).resolve().parent))
from test_support import module
d=module('decals');c=module('decal_controls')
state={'step':0,'states':[],'name':'BUILDDECALNUM0'}
def snapshot():
    o=bpy.context.scene.objects.get(state['name'])
    return None if o is None else (tuple(v for r in o.matrix_world for v in r),bool(o.get(d.PREVIEW_DISABLED)))
def run():
    try:
        i=state['step'];state['step']+=1
        area=next(a for a in bpy.context.screen.areas if a.type=='VIEW_3D')
        region=next(r for r in area.regions if r.type=='WINDOW')
        with bpy.context.temp_override(area=area,region=region):
            if i==0:
                for o in bpy.context.selected_objects:o.select_set(False)
                o=bpy.data.objects[state['name']];o.select_set(True);bpy.context.view_layer.objects.active=o
                state['materials']=tuple(m.name for m in o.data.materials)
                bpy.ops.ed.undo_push(message='Isolated decal history fixture')
                state['states'].append(snapshot())
            elif i==1:
                bpy.ops.bbe.toggle_decal_projection('EXEC_DEFAULT',True)
                state['states'].append(snapshot())
            elif i==2:
                bpy.ops.bbe.rotate_decal('EXEC_DEFAULT',True,degrees=-37.5)
                bpy.context.view_layer.update();state['states'].append(snapshot())
            elif i==3:
                bpy.ops.object.delete('EXEC_DEFAULT',True);state['states'].append(None)
            elif i<22:
                phase=(i-4)%6
                if phase<3:bpy.ops.ed.undo();expected=state['states'][2-phase]
                else:bpy.ops.ed.redo();expected=state['states'][phase-2]
                assert snapshot()==expected,(i,snapshot(),expected)
                o=bpy.context.scene.objects.get(state['name'])
                if o:
                    assert tuple(m.name for m in o.data.materials)==state['materials']
                    assert d.source_mesh(o) != o.data
            else:
                assert not module('undo_guard').restoring
                print('DECAL_REUSE_HISTORY_UI_PASS',bpy.app.version_string,flush=True)
                bpy.ops.wm.quit_blender();return None
        print('HISTORY_STEP',i,flush=True)
        return 1.9
    except Exception:
        traceback.print_exc();bpy.ops.wm.quit_blender();return None
bpy.app.timers.register(run,first_interval=3)
