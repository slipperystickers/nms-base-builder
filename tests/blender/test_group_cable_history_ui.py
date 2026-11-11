"""Windowed replay of wall-switch Fan and Chain, including native undo and redo."""
import math
import os
import sys
import traceback
from pathlib import Path
import bpy
from mathutils import Quaternion
sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_support import addon, module
c = module('cable_connections')
t = module('cable_targets')
v = module('builder_v2')
select = module('utils.blend_utils').select

def workflow():
    ctx = bpy.context
    win = ctx.window_manager.windows[0]
    area = next(a for a in win.screen.areas if a.type == 'VIEW_3D')
    region = next(r for r in area.regions if r.type == 'WINDOW')
    def override():
        return ctx.temp_override(window=win, area=area, region=region)
    def wires():
        return sorted(tuple((c.control_owner(e).name, e['bbe_socket_key']) for e in c.endpoints(w))
                      for w in ctx.scene.objects if w.get('ObjectID') == c.POWER)
    def paint():
        area.tag_redraw()
        with override():
            bpy.ops.wm.redraw_timer(type='DRAW_WIN_SWAP', iterations=2)
    with override():
        ctx.scene.nms_main.new_file()
        for pid,xy in [('U_BATTERY_S',(0,0)),('U_BATTERY_S',(3,0)),('U_BATTERY_S',(6,0)),
                       ('U_SWITCHBUTTON',(0,5)),('U_TRANSISTOR2',(3,5)),
                       ('U_TRANSISTOR1',(6,5)),('U_SWITCHWALL',(-3,5))]:
            obj=v.add_part(pid,high_res=False).object
            obj.location.x,obj.location.y=xy
        ctx.view_layer.update()
        selected=[o for o in ctx.scene.objects if o.get('ObjectID')]
        select(selected)
        area.spaces.active.region_3d.view_perspective='ORTHO'
        area.spaces.active.region_3d.view_distance=14
        area.spaces.active.region_3d.view_location=(1,2,0)
        area.spaces.active.region_3d.view_rotation=Quaternion((1,0,0),.45)
        ctx.scene.nms_main.line_switch='POWER'
        prefs=ctx.preferences.addons[addon.__name__].preferences
        prefs.nms_check_show_part_count=True
        bpy.ops.ed.undo_push(message='Wiring fixture')
    yield 2.0
    assert module('part_counts').displayed(ctx.scene) == 7
    for index, mode in enumerate(('FAN', 'CHAIN') * 3):
        before = wires()
        with override():
            selected=[o for o in ctx.scene.objects if o.get('ObjectID') and o.get('ObjectID')!=c.POWER]
            select(selected)
            assert bpy.ops.object.nms_connect('EXEC_DEFAULT',routing=mode)=={'FINISHED'}
        yield .2
        with override():
            row=next(row for row in t.projected_targets(ctx) if row[:2]==('U_SWITCHWALL','POWER_A'))
            x,y=row[4]
        for typ,val in [('MOUSEMOVE','NOTHING'),('LEFTMOUSE','PRESS'),('LEFTMOUSE','RELEASE')]:
            win.event_simulate(type=typ,value=val,x=round(region.x+x),y=round(region.y+y))
            yield .12
        assert t.session(ctx) is None
        result=wires()
        print('ROUTED',mode,len(result),flush=True)
        assert len(result) > len(before)
        paint()
        yield 1.9
        assert module('part_counts').displayed(ctx.scene)==7+len(result)
        with override(): bpy.ops.ed.undo()
        yield .45
        print('UNDO',mode,len(wires()),flush=True)
        assert wires()==before
        paint()
        with override(): bpy.ops.ed.redo()
        yield .5
        assert wires()==result
        paint()
        if index == 4:
            # Keep the last Fan and overlay Chain on it, as in the crash log.
            continue
        with override(): bpy.ops.ed.undo()
        yield 1.9
        assert wires()==before
        assert module('part_counts').displayed(ctx.scene)==7+len(before)
    print('CABLE HISTORY PASS',bpy.app.version_string,flush=True)

steps=workflow()
def tick():
    try:return next(steps)
    except StopIteration:bpy.ops.wm.quit_blender()
    except BaseException:
        traceback.print_exc()
        sys.stderr.flush()
        os._exit(1)
bpy.app.timers.register(tick,first_interval=2)

