"""Check the actual viewport guide, bilingual search, navigation and catalogue coverage."""
import os
from pathlib import Path
import sys
import traceback

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_support import bpy, module, QA

ui = module('menu_surface')
help_ui = module('save_editor.function_help')
browser = module('save_editor.guide_browser')
i18n = module('i18n')


def exercise():
    context = bpy.context
    context.preferences.view.show_splash = False
    window = context.window_manager.windows[0]
    area = next(area for area in window.screen.areas if area.type == 'VIEW_3D')
    region = next(region for region in area.regions if region.type == 'WINDOW')

    def override():
        return context.temp_override(window=window, area=area, region=region)

    def panel():
        return ui._sessions[area.as_pointer()]

    def click(**options):
        surface = panel()
        node, geometry = next((n, g) for n, g in surface.leaves
                              if all(n.options.get(k) == v for k, v in options.items()))
        rect = surface.rect(geometry)
        assert surface.visible(rect), options
        x, y, w, h = rect
        for typ, val in [('MOUSEMOVE', 'NOTHING'), ('LEFTMOUSE', 'PRESS'), ('LEFTMOUSE', 'RELEASE')]:
            window.event_simulate(type=typ, value=val,
                                  x=round(region.x+x+w/2), y=round(region.y+y+h/2))
            yield .1

    keys = [key for _, _, group in browser.GROUPS for key in group]
    assert not hasattr(bpy.types, 'BBE_PT_practice_course')
    assert not hasattr(bpy.types, 'BBE_OT_practice_lessons')
    assert len(keys) == len(set(keys)) and set(keys) == set(help_ui.TOPICS)
    messages = {s for title, steps in help_ui.TOPICS.values()
                for s in (title, *(v for pair in steps for v in pair))}
    messages.update(group for group, _, _ in browser.GROUPS)
    messages.update(('How-To Guide', 'Search the guide', 'Back to guides', 'Show all steps','No matching guides'))
    prefs = context.preferences.addons['no_mans_sky_base_builder'].preferences
    for tag, catalogue in i18n.catalogues().items():
        assert messages <= catalogue.keys(), (tag, messages-catalogue.keys())
        assert all(catalogue[k].strip() for k in messages)
        prefs.bbe_language = tag
        with override():
            assert bpy.ops.bbe.find_guide('INVOKE_DEFAULT') == {'FINISHED'}
        yield .2
        assert panel().topic is None
        yield from click(key='query')
        query = i18n.interface('Prefab Previews')
        context.window_manager.clipboard = query
        window.event_simulate(type='V', value='PRESS', ctrl=True)
        yield .2
        assert panel().modal_owner.query == query
        window.event_simulate(type='RET', value='PRESS')
        yield .1
        yield from click(text=query)
        assert panel().topic == 'ASSETS' and panel().step >= 0
        yield from click(text=i18n.interface('Show all steps'))
        assert panel().step == -1
        if tag == 'zh_HANS':
            with override():
                bpy.ops.screen.screenshot(filepath=str(QA/'howto-zh.png'))
        yield from click(text=i18n.interface('Back to guides'))
        assert panel().topic is None and panel().modal_owner.query == query
        window.event_simulate(type='ESC', value='PRESS')
        yield .2
        assert area.as_pointer() not in ui._sessions

    prefs.bbe_language = 'en_US'
    with override():
        bpy.ops.bbe.function_help('INVOKE_DEFAULT', topic='SHAPES')
    yield .2
    assert panel().topic == 'SHAPES'
    yield from click(text='Back to guides')
    guide = panel()
    assert not any(n.options.get('identifier') == 'bbe.practice_lessons' for n, _ in guide.leaves)
    start = guide.left, guide.top
    s = guide.scale
    px = round(region.x + (guide.left + 90)*s)
    py = round(region.y + (guide.top - 22)*s)
    for typ, val, dx, dy in [('MOUSEMOVE', 'NOTHING', 0, 0), ('LEFTMOUSE', 'PRESS', 0, 0),
                             ('MOUSEMOVE', 'NOTHING', -48, 32), ('LEFTMOUSE', 'RELEASE', -48, 32)]:
        window.event_simulate(type=typ, value=val, x=px+dx, y=py+dy)
        yield .1
    anchor = guide.workspace_position
    assert anchor is not None and guide.panel_drag is None
    assert abs((guide.left-start[0])*s + 48) < 2 and abs((guide.top-start[1])*s - 32) < 2
    with override():
        bpy.ops.screen.screenshot(filepath=str(QA/'howto-browser.png'))
    yield from click(text='Shape and connect')
    yield from click(text=help_ui.TOPICS['SHAPES'][0])
    assert panel().topic == 'SHAPES'
    yield from click(text='Shape and connect')
    assert panel().category == 'Shape and connect' and panel().topic is None
    assert panel().workspace_position == anchor
    assert (guide.left, guide.top) == guide.clamped_position(*anchor)
    for typ, val in [('MOUSEMOVE', 'NOTHING'), ('LEFTMOUSE', 'PRESS'), ('LEFTMOUSE', 'RELEASE')]:
        window.event_simulate(type=typ, value=val, x=round(region.x+(guide.left+guide.width-22)*s),
                              y=round(region.y+(guide.top-22)*s))
        yield .1
    yield .2
    assert area.as_pointer() not in ui._sessions
    with override():
        bpy.ops.bbe.custom_menu('INVOKE_DEFAULT', menu='CURVES')
        menu = panel()
        assert menu.header_help.options['props'].topic == 'CURVES'
        menu.activate(menu.header_help, context)
    yield .4
    assert panel().topic == 'CURVES'
    window.event_simulate(type='ESC', value='PRESS')
    yield .2
    sidebar = module('sidebar_builder')
    with override():
        view = sidebar.BuilderView()
        view.scale = 1.0
        view.layout(context, 295)
        button = next(n for n, _ in view.leaves if n.options.get('identifier') == 'bbe.function_help')
        sidebar.BBE_OT_sidebar_builder_input.run_operator(context, view, button)
    yield .2
    assert panel().topic == 'BUILDER'
    print('PASS guide navigation, localized search, context help and coverage:', len(keys), 'topics,',
          sum(len(s) for _, s in help_ui.TOPICS.values()), 'instructions', flush=True)


def run():
    try:
        return next(checks)
    except StopIteration:
        bpy.ops.wm.quit_blender()
    except BaseException:
        traceback.print_exc()
        sys.stderr.flush()
        os._exit(1)


checks = exercise()
bpy.app.timers.register(run, first_interval=1.5)

