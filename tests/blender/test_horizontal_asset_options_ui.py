"""Exercise both horizontal asset menu shortcuts through the normal Blender keymaps."""
import os
import sys
import traceback
from pathlib import Path

import bpy

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_support import addon, module


def exercise():
    ctx = bpy.context
    win = ctx.window_manager.windows[0]
    area = next(a for a in win.screen.areas if a.type == 'VIEW_3D')
    region = next(r for r in area.regions if r.type == 'WINDOW')
    strip = module('asset_strip')
    store = module('utils.asset_browser_utils')
    prefs = ctx.preferences.addons[addon.__name__].preferences
    prefs.bbe_menu_guide_seen = True
    prefs.bbe_menu_guide_version = 99
    prefs.bbe_wasd_enabled = True
    part = 'CORRIDOR_SPACE'

    def press(key, **position):
        for value in ('PRESS', 'RELEASE'):
            win.event_simulate(type=key, value=value, **position)
            yield .15

    def click(target, button):
        x, y, w, h = dict(state['targets'])[target + ':' + part]
        pos = dict(x=round(region.x+x+w/2), y=round(region.y+y+h/2))
        win.event_simulate(type='MOUSEMOVE', value='NOTHING', **pos)
        yield .15
        yield from press(button, **pos)

    def instances():
        return sum(obj.get('ObjectID') == part for obj in ctx.scene.objects)

    ctx.preferences.view.show_splash = False
    with ctx.temp_override(window=win, area=area, region=region):
        state = strip.state_for(ctx)
        state.update(enabled=True, search=part, height=146)
        area.tag_redraw()
    yield 1.2
    for _ in range(2):
        yield from press('ESC')

    count = instances()
    yield from click('options', 'LEFTMOUSE')
    assert instances() == count, 'Opening the hamburger placed a part'
    yield from press('HOME')
    yield from press('RET')
    assert instances() == count+1, 'Place Part did not act on the clicked card'

    was_favourite = part in store.load_stored_list('favourite_objects')
    for expected in (not was_favourite, was_favourite):
        yield from click('part', 'RIGHTMOUSE')
        yield from press('HOME')
        yield from press('DOWN_ARROW')
        yield from press('RET')
        assert (part in store.load_stored_list('favourite_objects')) == expected
        assert instances() == count+1
    print('HORIZONTAL ASSET OPTIONS PASS', flush=True)
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


bpy.app.timers.register(tick, first_interval=2)
