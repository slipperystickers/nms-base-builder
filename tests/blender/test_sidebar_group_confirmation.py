"""One Builder click must leave the pivot dialog open for a separate user choice."""
import os
from pathlib import Path
import sys
import traceback

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_support import bpy, module


def steps():
    ctx = bpy.context
    win = ctx.window_manager.windows[0]
    area = next(a for a in win.screen.areas if a.type == 'VIEW_3D')
    ctx.preferences.view.show_splash = False
    area.spaces.active.show_region_ui = True
    yield .5
    side = next(r for r in area.regions if r.type == 'UI')
    viewport = next(r for r in area.regions if r.type == 'WINDOW')
    sidebar = module('sidebar_builder')
    toolbar = module('tools_menu.base_builder_menu')
    prefs = toolbar._preferences(ctx)
    prefs.bbe_sidebar_hidden = ','.join(k for k in toolbar.SIDE_LABELS if k != 'builder')
    side.active_panel_category = sidebar.CATEGORY
    with ctx.temp_override(window=win, area=area, region=viewport):
        parts = [module('builder_v2').add_part('STORAGEPANEL', high_res=False).object for _ in range(2)]
        parts[1].location.x += 3
        module('utils.blend_utils').select(parts)
        ctx.view_layer.objects.active = parts[0]
    area.tag_redraw()
    yield .5

    def event(key, value, x, y):
        win.event_simulate(type=key, value=value, x=round(x), y=round(y))

    def click(x, y, release_x=None):
        event('MOUSEMOVE', 'NOTHING', x, y)
        yield .12
        event('LEFTMOUSE', 'PRESS', x, y)
        yield .3
        if release_x is not None:
            x = release_x
            event('MOUSEMOVE', 'NOTHING', x, y)
            yield .1
        event('LEFTMOUSE', 'RELEASE', x, y)
        yield .4

    view_key = win.as_pointer(), area.as_pointer(), 'builder'
    for _ in range(3):
        if view_key in sidebar._views and sidebar._views[view_key].visible:
            break
        yield from click(side.x+40, side.y+side.height-15)
    view = sidebar._views[view_key]
    node, bounds = next((n, g) for n, g in view.leaves if n.options.get('identifier') == 'object.nms_group_objects')
    assert node.can_click
    left, bottom, width, height = view.rect(bounds)
    x, y = side.x+left+width/2, side.y+bottom+height/2

    def groups():
        return [o for o in ctx.scene.objects if 'GroupID' in o]

    yield from click(x, y, release_x=side.x-25)
    event('RET', 'PRESS', x, y)
    event('RET', 'RELEASE', x, y)
    yield .25
    assert not groups(), 'Releasing outside Group should abandon the click'

    yield from click(x, y)
    assert not groups(), 'The opening click also confirmed Group'
    event('ESC', 'PRESS', x, y)
    event('ESC', 'RELEASE', x, y)
    yield .25
    assert all(p.select_get() for p in parts) and not groups()

    yield from click(x, y)
    assert not groups()
    # The native confirm button's position depends on the Blender version and available space.
    event('RET', 'PRESS', x, y)
    event('RET', 'RELEASE', x, y)
    yield .5
    assert len(groups()) == 1 and groups()[0] == ctx.active_object, 'Explicit confirmation did not merge the two panels'
    print('GROUP CONFIRMATION PASS', bpy.app.version_string, flush=True)


workflow = steps()


def tick():
    try:
        return next(workflow)
    except StopIteration:
        bpy.ops.wm.quit_blender()
    except Exception:
        traceback.print_exc()
        sys.stderr.flush()
        os._exit(1)


bpy.app.timers.register(tick, first_interval=1.2)
