"""Exercise the actual Delete key, confirmation, undo and Outliner selection."""
from pathlib import Path
import os
import sys
import traceback
import bpy

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_support import addon, module

prefs = bpy.context.preferences.addons[addon.__name__].preferences
prefs.bbe_menu_guide_seen = True
prefs.bbe_menu_guide_version = 99


def exercise():
    c = module('cable_connections')
    d = module('cable_delete')
    ctx = bpy.context
    win = ctx.window
    view = next(a for a in win.screen.areas if a.type == 'VIEW_3D')
    outliner = next(a for a in win.screen.areas if a.type == 'OUTLINER')

    def region(area):
        return next(r for r in area.regions if r.type == 'WINDOW')

    position = {}
    def key(event):
        for value in ('PRESS','RELEASE'):
            win.event_simulate(type=event,value=value,**position)
            yield .12

    ctx.preferences.view.show_splash = False
    yield from key('ESC')
    yield from key('ESC')
    b = addon.BUILDER
    with ctx.temp_override(window=win,area=view,region=region(view)):
        a = b.add_part('L_FLOOR_Q',build_rigs=False).object
        neighbor = b.add_part('L_FLOOR_Q',build_rigs=False).object
        a.name = 'AA cable delete test'
        neighbor.location.x = 8
        ctx.view_layer.update()
        socket = next(iter(c.local_sockets(a,c.POWER)))
        wire = c.connect(a,socket,neighbor,socket,c.POWER,b)
        names = {obj.name for obj in (a,wire,*c.endpoints(wire))}
        device_name, neighbor_name = a.name, neighbor.name
        for obj in ctx.selected_objects:
            obj.select_set(False)
        a.select_set(True)
        ctx.view_layer.objects.active = a
        bpy.ops.ed.undo_push(message='Wired floor')

    confirmations = []
    original = d.ask

    def observe(operator, context, plan):
        confirmations.append((context.area.type, len(plan.attached)))
        return original(operator, context, plan)

    d.ask = observe
    try:
        for area, shortcut in ((view,'X'),(view,'DEL'),(outliner,'DEL')):
            position.update(x=region(area).x+region(area).width//3,
                            y=region(area).y+region(area).height//2)
            win.event_simulate(type='MOUSEMOVE',value='NOTHING',**position)
            yield .3
            if area == outliner:
                with ctx.temp_override(window=win,area=area,region=region(area)):
                    bpy.ops.outliner.show_active()
            yield .25
            previous = len(confirmations)
            yield from key(shortcut)
            assert confirmations[previous:] == [(area.type,1)], confirmations
            assert names <= set(ctx.scene.objects.keys())
            yield from key('ESC')
            assert names <= set(ctx.scene.objects.keys())
            yield from key(shortcut)
            yield from key('RET')
            yield .35
            assert not names.intersection(ctx.scene.objects.keys()), (area.type,names.intersection(ctx.scene.objects.keys()))
            assert neighbor_name in ctx.scene.objects
            with ctx.temp_override(window=win,area=view,region=region(view)):
                assert bpy.ops.ed.undo() == {'FINISHED'}
            yield .3
            assert names <= set(ctx.scene.objects.keys())
            assert ctx.scene.objects[device_name].select_get()
    finally:
        d.ask = original
    print('CABLE DELETE DIALOG PASS', bpy.app.version_string, flush=True)
    bpy.ops.wm.quit_blender()


steps = exercise()


def tick():
    try:
        return next(steps)
    except StopIteration:
        return None
    except Exception:
        traceback.print_exc()
        sys.stderr.flush()
        os._exit(1)


bpy.app.timers.register(tick,first_interval=2.0)
