"""Exercise the graphical sidebar panels and prefab menus with real Blender input in an isolated profile."""
import json
import os
import sys
import tempfile
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_support import QA, addon, bpy, module

ctx = bpy.context
sidebar = module('sidebar_builder')
toolbar = module('tools_menu.base_builder_menu')


def steps():
    ctx.preferences.view.show_splash = False
    win = ctx.window_manager.windows[0]
    area = next(a for a in win.screen.areas if a.type == 'VIEW_3D')
    area.spaces.active.show_region_ui = True
    yield .6
    side = next(r for r in area.regions if r.type == 'UI')
    port = next(r for r in area.regions if r.type == 'WINDOW')
    prefs = toolbar._preferences(ctx)
    prefs.bbe_menu_guide_seen = True
    prefs.bbe_menu_guide_version = 99
    saved_order=prefs.bbe_sidebar_order
    for order, expected in [('', True), ('parts,transform,batch', True), ('shapes,batch,transform', False)]:
        prefs.bbe_sidebar_order=order
        keys=toolbar.sidebar_order(ctx)
        assert (keys.index('shapes')==keys.index('transform')+1) == expected
        if order.startswith('shapes'):
            assert keys[:3]==['shapes','batch','transform']
    prefs.bbe_sidebar_order=saved_order
    panels={toolbar.sidebar_key(cls):cls for cls in toolbar._side_polls}
    assert panels['shapes'].bl_order == panels['transform'].bl_order+1
    side.active_panel_category = sidebar.CATEGORY

    with ctx.temp_override(window=win,area=area,region=port):
        module('bbe_themes').apply_theme('VIOLET')
        theme=ctx.preferences.themes[0].user_interface.wcol_menu_item
        theme.inner_sel=(.40,.49,.77,1)
        ui=module('menu_surface')
        for sample in [theme.inner_sel[:], (.055,.38,.16,1), (.065,.29,.62,1), (.03,.03,.08,1),(.9,.85,.7,1)]:
            for text in [(1,1,1,1),(0,0,0,1)]:
                for hover in (False,True):
                    first,last,ink=ui.primary_button_colors(tuple(sample),text,hover)
                    for fill in (first,last):
                        a,b=sorted((ui._luminance(fill),ui._luminance(ink)))
                        assert (b+.05)/(a+.05)>=7

    def click(x, y):
        for kind, value in [('MOUSEMOVE','NOTHING'), ('LEFTMOUSE','PRESS'), ('LEFTMOUSE','RELEASE')]:
            win.event_simulate(type=kind, value=value, x=round(x), y=round(y))
            yield .09
        yield .16

    def show(key):
        prefs.bbe_sidebar_hidden = ','.join(k for k in toolbar.SIDE_LABELS if k != key)
        area.tag_redraw()
        yield .28
        view_key = (win.as_pointer(), area.as_pointer(), key)
        panel = sidebar._views.get(view_key)
        if not panel or not panel.visible:
            yield from click(side.x+45, side.y+side.height-15)
            panel = sidebar._views[view_key]
        assert panel.visible
        return panel

    def leaf(view, **options):
        return next((n,g) for n,g in view.leaves if all(n.options.get(k)==v for k,v in options.items()))

    def press(view, **options):
        n, g = leaf(view, **options)
        x,y,w,h = view.rect(g)
        assert n.can_click and 0 < y+h/2 < side.height, options
        yield from click(side.x+x+w/2, side.y+y+h/2)

    def shot(key):
        win.event_simulate(type='MOUSEMOVE',value='NOTHING',x=port.x+150,y=port.y+150)
        yield .25
        with ctx.temp_override(window=win, area=area):
            bpy.ops.screen.screenshot(filepath=str(QA/('inline-'+key+'.png')))

    def drag(region, x, start, end):
        for kind,value,y in [('MOUSEMOVE','NOTHING',start),('LEFTMOUSE','PRESS',start),
                              ('MOUSEMOVE','NOTHING',end),('LEFTMOUSE','RELEASE',end)]:
            win.event_simulate(type=kind,value=value,x=round(region.x+x),y=round(region.y+y))
            yield .15

    def check_library_scroll(view, region):
        assert leaf(view,identifier='bbe.prefab_catalogue_open')[0].options['font_size'] >= 15
        mark,g = next((n,g) for n,g in view.leaves if n.kind=='list_scroll')
        track,thumb,last = view.scrollbar_geometry(mark,view.rect(g))
        x=track[0]+track[2]/2
        yield from drag(region,x,thumb[1]+thumb[3]/2,track[1]+thumb[3]/2)
        assert ctx.window_manager.bbe_prefab_offset == last,(region.type,ctx.window_manager.bbe_prefab_offset,last)
        yield from drag(region,x,track[1]+thumb[3]/2,track[1]+track[3]-thumb[3]/2)
        assert ctx.window_manager.bbe_prefab_offset == 0

    batch = yield from show('batch')
    with ctx.temp_override(window=win, area=area, region=port):
        source = module('builder_v2').add_part('BUILDFLATPANEL',high_res=False).object
        other = module('builder_v2').add_part('BUILDFLATPANEL',high_res=False).object
        wall = module('builder_v2').add_part('BUILDWALL', high_res=False).object
        select = module('utils.blend_utils').select
        select([source, wall])
        assert bpy.ops.object.nms_apply_colour(colour_index=37) == {'FINISHED'}
        bpy.ops.object.select_all(action='DESELECT')
        source.select_set(True)
        ctx.view_layer.objects.active = source
    yield from press(batch,identifier='object.nms_select_same_objects')
    assert other.select_get() and not wall.select_get()
    select(source)
    yield from press(batch, identifier='object.nms_select_same_colors')
    assert source.select_get() and wall.select_get() and not other.select_get()
    yield from shot('batch')

    with ctx.temp_override(window=win, area=area, region=port):
        select([source])
        bpy.ops.bbe.custom_menu('INVOKE_DEFAULT', menu='BATCH', anchor_x=port.x+100, anchor_y=port.y+port.height-50)
    yield .4
    popup = ui._sessions[area.as_pointer()]
    node, bounds = leaf(popup, identifier='object.nms_select_same_colors')
    x, y, w, h = popup.rect(bounds)
    yield from click(port.x+x+w/2, port.y+y+h/2)
    assert source.select_get() and wall.select_get() and not other.select_get()
    if area.as_pointer() in ui._sessions:
        popup.finish()
    yield .3

    with tempfile.TemporaryDirectory() as directory:
        preset = module('preset').Preset
        original_preset_path = preset.PRESET_PATH
        preset.PRESET_PATH = directory
        data = {'Objects':[{'ObjectID':'^BUILDFLATPANEL','Position':[0,0,0],
                            'Up':[0,1,0],'At':[0,0,1],'UserData':0}]}
        for i in range(12):
            (Path(directory)/f'Practice {i:02}.nmsprefab').write_text(json.dumps(data))
        addon.refresh_prefab_catalogue()
        parts = yield from show('parts')
        yield from press(parts,key='reverse_order')
        assert leaf(parts,identifier='object.list_build_operator')[0].options['text']=='Practice 11'
        yield from press(parts,key='reverse_order')
        yield from check_library_scroll(parts,side)
        with ctx.temp_override(window=win,area=area,region=port):
            bpy.ops.bbe.custom_menu('INVOKE_DEFAULT',menu='PREFABS',anchor_x=port.x+100,anchor_y=port.y+port.height-50)
        yield .4
        popup=module('menu_surface')._sessions[area.as_pointer()]
        yield from check_library_scroll(popup,port)
        yield from shot('prefab-menus')
        original_accent=tuple(theme.inner_sel)
        original_text=tuple(theme.text)
        theme.inner_sel=(.91,.85,.69,1)
        theme.text=(.06,.06,.06)
        area.tag_redraw()
        yield from shot('prefab-light-accent')
        theme.inner_sel=original_accent
        theme.text=original_text
        popup.finish()
        yield .3
        yield from shot('parts')
        item, geom = leaf(parts,identifier='object.list_build_operator')
        x,y,w,h = parts.rect(geom)
        win.event_simulate(type='MOUSEMOVE',value='NOTHING',x=round(side.x+x+w/2),y=round(side.y+y+h/2))
        yield .12
        win.event_simulate(type='WHEELDOWNMOUSE',value='PRESS',x=round(side.x+x+w/2),y=round(side.y+y+h/2))
        yield .3
        assert ctx.window_manager.bbe_prefab_offset == 1, ctx.window_manager.bbe_prefab_offset
        yield from press(parts,key='bbe_prefab_search')
        win.event_simulate(type='ONE',value='PRESS',unicode='1')
        yield .25
        assert ctx.window_manager.bbe_prefab_search == '1'
        win.event_simulate(type='RET',value='PRESS')
        yield .16
        yield from press(parts,key='exclude_matches')
        assert all('1' not in n.options['text'] for n,_ in parts.leaves
                   if n.options.get('identifier') == 'object.list_build_operator')
        yield from press(parts,key='exclude_matches')
        yield from press(parts,key='bbe_prefab_search')
        win.event_simulate(type='BACK_SPACE',value='PRESS')
        yield .12
        win.event_simulate(type='RET',value='PRESS')
        yield .16
        assert not ctx.window_manager.bbe_prefab_search
        yield from press(parts,identifier='object.list_build_operator')
        assert any(o.get('PresetID','').startswith('Practice') for o in ctx.scene.objects)
        yield from press(parts,identifier='bbe.prefab_catalogue_open')
        assert module('catalogue_surface')._sessions
        module('catalogue_surface')._sessions[-1].close()
        yield .25
        preset.PRESET_PATH = original_preset_path
        addon.refresh_prefab_catalogue()

    logic = yield from show('cables')
    help_node,help_g=leaf(logic,identifier='bbe.function_help')
    last_tile = [g for n,g in logic.leaves if n.options.get('tile')][-1]
    assert abs(help_g[1]-last_tile[1]) < 2
    initial_bottom = logic.bottom
    yield from press(logic,key='line_switch')
    choices = logic.dropdown['items']
    left,top,w,count = logic.choice_geometry()
    index = next(i for i,item in enumerate(choices) if item[0]=='SUPPLY')
    assert index < count and logic.bottom == initial_bottom
    yield from click(side.x+left+w/2, side.y+top-(index+.5)*31*logic.scale)
    assert ctx.scene.nms_main.line_switch=='SUPPLY'
    yield from press(logic,identifier='bbe.start_cable_connection')
    cable = module('cable_targets')
    assert cable.session(ctx)['kind']=='U_PIPELINE'
    yield from click(port.x+180,port.y+210)
    assert cable.session(ctx)['first'] is not None
    win.event_simulate(type='ESC',value='PRESS')
    yield .25
    assert cable.session(ctx) is None
    with ctx.temp_override(window=win, area=area, region=port):
        bpy.ops.object.select_all(action='DESELECT')
    yield from press(logic,identifier='object.nms_logic_button')
    assert ctx.active_object.get('ObjectID')=='U_SWITCHBUTTON'
    yield from shot('logic')
    settings = ctx.scene.nms_main
    settings.line_switch = 'POWER'
    first = ctx.active_object
    with ctx.temp_override(window=win, area=area, region=port):
        second = module('builder_v2').add_part('U_SWITCHBUTTON',high_res=False).object
        first.select_set(True)
        second.select_set(True)
        ctx.view_layer.objects.active = first
    area.tag_redraw()
    yield .25
    yield from press(logic,identifier='object.nms_connect')
    assert [item[0] for item in logic.dropdown['items']] == ['CHAIN','FAN']
    left,top,w,_ = logic.choice_geometry()
    yield from click(side.x+left+w/2, side.y+top-.5*31*logic.scale)
    assert cable.session(ctx)['kind'] == 'U_POWERLINE'
    win.event_simulate(type='ESC',value='PRESS')
    yield .16
    scenes = yield from show('lighting')
    stage=ctx.scene.bbe_stage
    if module('hd_library').scenes_root():
        stage.environment='SPACE'
        yield from press(scenes,key='enabled')
        yield 1.0
        assert stage.enabled
        yield from press(scenes,key='environment')
        assert len(scenes.dropdown['items']) == 3
        win.event_simulate(type='ESC',value='PRESS')
        yield .25
        _,g=leaf(scenes,key='brightness')
        x,y,w,h=scenes.rect(g)
        yield from click(side.x+x+w/2,side.y+y+h/2)
        assert scenes.edit
        for letter in '12':
            win.event_simulate(type={'1':'ONE','2':'TWO'}[letter],value='PRESS',unicode=letter)
            yield .1
            if letter=='1':
                win.event_simulate(type='PERIOD',value='PRESS',unicode='.')
                yield .1
        win.event_simulate(type='RET',value='PRESS')
        yield .2
        assert abs(stage.brightness-1.2)<1e-4,stage.brightness
        yield from press(scenes,identifier='bbe.stage_refresh')
        assert abs(module('stage_effects').preview_value(ctx.scene,'brightness')-1.2)<1e-4
        yield from shot('lighting')
        yield from press(scenes,key='enabled')
        assert not stage.enabled
    else:
        leaf(scenes,identifier='bbe.hd_library')
        yield from shot('lighting')
    shapes = yield from show('shapes')
    layout=module('shape_layout')
    def presets():
        return [n for n,_ in shapes.leaves if n.options.get('identifier')=='bbe.start_shape']
    assert len(presets())==len(layout.SHELLS)
    yield from shot('shapes')
    yield from press(shapes,key='dimension',value='D2')
    assert len(presets())==len(layout.OUTLINES)
    yield from press(shapes,identifier='bbe.start_shape')
    root=module('shapes').selected_root(ctx)
    assert root and root.bbe_shape.dimension=='D2' and len(root.children)
    # Check narrow and wide reflow through the same layout path as real resizing.
    with ctx.temp_override(window=win,area=area,region=side):
        for panel in (batch, parts, logic, scenes, shapes):
            for width in (195, 270, 490):
                panel.layout(ctx,width)
                assert all(x >= -1 and x+w <= width+1 for _,(x,_,w,_) in panel.leaves)
    print('PASS sidebar and top-bar prefab dragging, batch selection, cables, scene preview controls, shape creation and panel reflow',flush=True)


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

bpy.app.timers.register(tick,first_interval=1.3)
