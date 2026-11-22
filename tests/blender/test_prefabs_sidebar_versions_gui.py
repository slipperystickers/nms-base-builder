"""Verify the Home and Prefabs panel bodies in a real, default-theme sidebar."""
from pathlib import Path
import os
import sys
import traceback

import bpy

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_support import QA, module

sidebar = module('sidebar_builder')
folds = module('sidebar_state')


def exercise():
    ctx = bpy.context
    area = next(a for a in ctx.screen.areas if a.type == 'VIEW_3D')
    toolbar = module('tools_menu.base_builder_menu')
    prefs = toolbar._preferences(ctx)
    prefs.bbe_menu_guide_seen = True
    prefs.bbe_menu_guide_version = 99
    prefs.bbe_sidebar_hidden = ','.join(key for key in toolbar.SIDE_LABELS if key not in {'proxies', 'parts'})
    folds._saved.update(proxies=True, parts=True)
    folds._observed.clear()
    area.spaces.active.show_region_ui = True
    yield 0.5
    side = next(r for r in area.regions if r.type == 'UI')
    side.active_panel_category = sidebar.CATEGORY
    area.tag_redraw()
    yield 0.8
    with ctx.temp_override(area=area, region=side):
        views = {v.menu for v in sidebar.active_views(ctx) if isinstance(v, sidebar.ToolView) and v.leaves}
    assert {'parts', 'proxies'} <= views, views
    bpy.ops.screen.screenshot(filepath=str(QA / ('prefab-sidebar-' + bpy.app.version_string + '.png')))
    print('GRAPHICAL HOME AND PREFABS PASS', bpy.app.version_string, flush=True)


steps = exercise()


def tick():
    try:
        return next(steps)
    except StopIteration:
        bpy.ops.wm.quit_blender()
    except Exception:
        traceback.print_exc()
        sys.stderr.flush()
        os._exit(1)


bpy.app.timers.register(tick, first_interval=2)
