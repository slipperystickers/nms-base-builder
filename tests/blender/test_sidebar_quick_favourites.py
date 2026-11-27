"""Exercise Quick Access with a long favourites list in an isolated Blender window."""
import os
import sys
import traceback
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_support import bpy, module


def exercise():
    ctx = bpy.context
    wm = ctx.window_manager
    side = module('sidebar_builder')
    toolbar = module('tools_menu.base_builder_menu')
    browser = ctx.scene.nms_asset_browser
    catalogue = module('utils.asset_browser_utils')
    # Older files may have explicitly saved the old scene property as Favourites.
    ctx.scene['enum_assets_quick_access_view_mode'] = 0
    assert wm.enum_assets_quick_access_view_mode == 'recent'
    parts = [k for k, v in catalogue.iter_all_parts(browser.get_categories_data())
             if v.get('name') and not v.get('variants') and not v.get('is_preset')]
    browser.set_favourite_objects(list(dict.fromkeys(parts))[:60])
    ids = list(browser.get_favourite_objects_data())
    assert len(ids) == 60

    win = wm.windows[0]
    area = next(a for a in win.screen.areas if a.type == 'VIEW_3D')
    area.spaces.active.show_region_ui = True
    ctx.preferences.view.show_splash = False
    yield .4
    region = next(r for r in area.regions if r.type == 'UI')
    region.active_panel_category = side.CATEGORY
    prefs = toolbar._preferences(ctx)
    prefs.bbe_menu_guide_seen = True
    prefs.bbe_menu_guide_version = 99
    prefs.bbe_sidebar_hidden = ','.join(k for k in toolbar.SIDE_LABELS if k != 'proxies')
    area.tag_redraw()
    yield .4

    def event(kind, value, x, y):
        win.event_simulate(type=kind, value=value, x=round(region.x+x), y=round(region.y+y))
        yield .18

    def click(x, y):
        yield from event('MOUSEMOVE', 'NOTHING', x, y)
        yield from event('LEFTMOUSE', 'PRESS', x, y)
        yield from event('LEFTMOUSE', 'RELEASE', x, y)

    yield from click(5, 28)
    key = win.as_pointer(), area.as_pointer(), 'proxies'
    for _ in range(3):
        if key in side._views and side._views[key].visible:
            break
        yield from click(40, region.height-15)
    view = side._views[key]

    def shown():
        return [node.options['props'].object_id for node, _ in view.leaves
                if node.options.get('identifier') == 'object.nms_asset_browser_object_selected'
                and not node.options['props'].has_variants]

    def footer():
        return next(bounds for node, bounds in view.leaves
                    if node.options.get('identifier') == 'object.nms_workspace_settings')

    wm.enum_assets_quick_access_view_mode = 'fav'
    wm.bbe_prefab_offset = 7
    area.tag_redraw()
    yield .4
    assert shown() == ids[:5], shown()
    mark, bounds = next((node, b) for node, b in view.leaves if node.kind == 'list_scroll')
    rect = view.rect(bounds)
    x, y = rect[0]+rect[2]/2, rect[1]+rect[3]/2
    footer_at_start = footer()
    yield from event('MOUSEMOVE', 'NOTHING', x, y)
    yield from event('WHEELDOWNMOUSE', 'PRESS', x, y)
    assert shown() == ids[1:6], (wm.bbe_quick_favourite_offset, shown())

    mark, bounds = next((node, b) for node, b in view.leaves if node.kind == 'list_scroll')
    track, thumb, _ = view.scrollbar_geometry(mark, view.rect(bounds))
    x, y = thumb[0]+thumb[2]/2, thumb[1]+thumb[3]/2
    yield from event('MOUSEMOVE', 'NOTHING', x, y)
    yield from event('LEFTMOUSE', 'PRESS', x, y)
    yield from event('MOUSEMOVE', 'NOTHING', x, track[1]+thumb[3]/2)
    yield from event('LEFTMOUSE', 'RELEASE', x, track[1]+thumb[3]/2)
    assert shown() == ids[-5:], (wm.bbe_quick_favourite_offset, shown())
    assert footer() == footer_at_start and wm.bbe_prefab_offset == 7

    # Blender 5.2+ leaves a live UI region when just the category tabs are visible.
    # Drag the native divider and exercise both standard and compact tabs.
    if hasattr(ctx.preferences.system, 'show_panel_tabs_compact'):
        for compact in (False, True):
            ctx.preferences.system.show_panel_tabs_compact = compact
            area.tag_redraw()
            yield .3
            start = region.width
            origin = region.x
            y = region.y + region.height // 2
            right = region.alignment == 'RIGHT'
            edge = origin + (1 if right else start - 2)
            narrow = edge + (start - 32) * (1 if right else -1)
            for kind, value, x in [('MOUSEMOVE', 'NOTHING', edge), ('LEFTMOUSE', 'PRESS', edge),
                                   ('MOUSEMOVE', 'NOTHING', narrow), ('LEFTMOUSE', 'RELEASE', narrow)]:
                win.event_simulate(type=kind, value=value, x=x, y=y)
                yield .2
            assert region.width < start / 2 and area.spaces.active.show_region_ui
            with ctx.temp_override(window=win, area=area, region=region):
                assert not list(side.active_views(ctx))
                assert not bpy.ops.bbe.sidebar_builder_input.poll()
            with patch.object(side.InlineView, 'draw') as paint:
                area.tag_redraw()
                yield .3
                paint.assert_not_called()
            area.spaces.active.show_region_ui = False
            yield .2
            area.spaces.active.show_region_ui = True
            area.tag_redraw()
            yield .4
            assert region.width > start / 2
            assert shown() == ids[-5:]
            with ctx.temp_override(window=win, area=area, region=region):
                assert view in side.active_views(ctx)

    # Exercise Blender's standard panel path as well as the graphical sidebar.
    with patch.object(side, 'native_panel', return_value=None):
        area.tag_redraw()
        yield .6
        assert wm.bbe_quick_favourites.keys() == ids
        browser.set_favourite_objects(ids[:-1])
        area.tag_redraw()
        yield .5
        assert wm.bbe_quick_favourites.keys() == ids[:-1]

    browser.set_favourite_objects(ids[:2])
    area.tag_redraw()
    yield .4
    assert shown() == ids[:2] and not any(n.kind == 'list_scroll' for n, _ in view.leaves)
    assert footer()[1] < footer_at_start[1]
    browser.set_favourite_objects([])
    area.tag_redraw()
    yield .3
    assert not shown()
    assert any(n.options.get('text') == 'No favourite parts yet.' for n, _ in view.leaves)
    print('QUICK FAVOURITES PASS', bpy.app.version_string, flush=True)
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


bpy.app.timers.register(tick, first_interval=1.5)

