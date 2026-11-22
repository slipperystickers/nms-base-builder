"""Exercise the file and clipboard controls through the graphical sidebar in Blender."""
import json
import os
import sys
import traceback
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_support import QA, addon, bpy, module

ctx = bpy.context


class Overlay:
    def __init__(self, target, **fields):
        self.target = target
        vars(self).update(fields)

    def __getattr__(self, name):
        return getattr(self.target, name)


def run():
    ctx.preferences.view.show_splash = False
    win = ctx.window_manager.windows[0]
    area = next(a for a in win.screen.areas if a.type == 'VIEW_3D')
    area.spaces.active.show_region_ui = True
    yield .5
    side = next(r for r in area.regions if r.type == 'UI')
    port = next(r for r in area.regions if r.type == 'WINDOW')
    ui = module('sidebar_builder')
    toolbar = module('tools_menu.base_builder_menu')
    prefs = toolbar._preferences(ctx)
    prefs.bbe_menu_guide_version = 99
    prefs.bbe_sidebar_hidden = ','.join(k for k in toolbar.SIDE_LABELS if k != 'io')
    side.active_panel_category = ui.CATEGORY
    with ctx.temp_override(window=win,area=area,region=port):
        module('bbe_themes').apply_theme('VIOLET')
    area.tag_redraw()
    yield .4

    def click(x,y):
        for key,value in [('MOUSEMOVE','NOTHING'), ('LEFTMOUSE','PRESS'), ('LEFTMOUSE','RELEASE')]:
            win.event_simulate(type=key,value=value,x=round(side.x+x),y=round(side.y+y))
            yield .1
        yield .18

    key = (win.as_pointer(),area.as_pointer(),'io')
    for _ in range(3):
        if key in ui._views and ui._views[key].visible:
            break
        yield from click(40,side.height-15)
    view = ui._views[key]

    def press(identifier):
        node,g = next((n,g) for n,g in view.leaves if n.options.get('identifier')==identifier)
        x,y,w,h=view.rect(g)
        assert node.can_click and view.hit(x+w/2,y+h/2) is node,identifier
        yield from click(x+w/2,y+h/2)

    def file_action(identifier,path):
        yield from press(identifier)
        for _ in range(30):
            browser=next(((w,a) for w in ctx.window_manager.windows for a in w.screen.areas
                          if a.type=='FILE_BROWSER' and a.spaces.active.params),None)
            if browser:
                break
            yield .1
        if not browser:
            with ctx.temp_override(window=win,area=area):
                bpy.ops.screen.screenshot(filepath=str(QA/'sidebar-io-failure.png'))
        assert browser,identifier
        w,files=browser
        with ctx.temp_override(window=w,area=files,region=next(r for r in files.regions if r.type=='WINDOW')):
            params=files.spaces.active.params
            params.directory=os.fsencode(path.parent)
            params.filename=path.name
            bpy.ops.file.execute()
        yield .6
        if identifier == 'bbe.export_ship_file':
            # The template-free export reports that it used new Corvette defaults.
            win.event_simulate(type='ESC',value='PRESS')
            win.event_simulate(type='ESC',value='RELEASE')
            yield .2

    def parts():
        return sorted(o.get('ObjectID') for o in ctx.scene.objects if 'ObjectID' in o)

    def shot():
        win.event_simulate(type='MOUSEMOVE',value='NOTHING',x=port.x+100,y=port.y+200)
        yield .2
        with ctx.temp_override(window=win,area=area):
            bpy.ops.screen.screenshot(filepath=str(QA/'sidebar-import-export.png'))

    with ctx.temp_override(window=win,area=area,region=port):
        module('builder_v2').add_part('BUILDFLATPANEL', high_res=False)
        module('builder_v2').add_part('B_COK_D', high_res=False)
        ctx.scene.nms_base_tool.string_base_type='HomePlanetBase'
        assert not ctx.scene.nms_save_data.check_plugin_enabled
        top = module('menu_surface').draw_definition('IO', ctx)
        assert any(n.options.get('key') == 'string_base' for n in ui.walk(top))
    field, geometry = next((n,g) for n,g in view.leaves if n.options.get('key') == 'string_base')
    x,y,w,h = view.rect(geometry)
    yield from click(x+w*.7,y+h/2)
    for char in 'Renamed':
        win.event_simulate(type=char.upper(), value='PRESS', unicode=char)
    win.event_simulate(type='RET', value='PRESS')
    yield .3
    assert ctx.scene.nms_base_tool.string_base == 'Renamed'
    expected=parts()
    assert expected == ['BUILDFLATPANEL', 'B_COK_D']
    yield from shot()
    yield from press('object.nms_new_file')
    assert parts() == expected, 'Clear must wait for a separate confirmation click'
    win.event_simulate(type='ESC',value='PRESS')
    yield .3
    assert parts()==expected,(parts(),expected)
    with TemporaryDirectory() as directory:
        folder=Path(directory)
        for identifier,filename in [('object.nms_save_data','Practice.json'),('bbe.export_ship_file','Practice.nmsship'),
                                    ('bbe.export_base_file','Practice.nmsbase')]:
            yield from file_action(identifier,folder/filename)
            assert (folder/filename).is_file(),filename
            assert module('interchange').BuildFile.read(folder/filename).document['Name'] == 'Renamed',filename
        for filename in ['Practice.nmsbase','Practice.nmsship','Practice.json']:
            yield from file_action('bbe.import_build_file',folder/filename)
            assert parts()==expected and view.visible,filename
            assert ctx.scene.nms_base_tool.string_base == 'Renamed',filename

    # Redirect only clipboard storage; use the real sidebar, operators and serializers.
    clipboard=Overlay(ctx.window_manager,clipboard='')
    with patch.object(addon,'bpy',Overlay(bpy,context=Overlay(ctx,window_manager=clipboard))):
        for identifier, objects_only in [('object.nms_export_nms_data',False),('object.nms_export_nms_data_objects',True)]:
            yield from press(identifier)
            data=json.loads(clipboard.clipboard)
            records=data if objects_only else data['Objects']
            if not objects_only:
                assert data['Name']=='Renamed'
            assert sorted(r['ObjectID'].lstrip('^') for r in records)==expected
            yield from press('object.nms_import_nms_data')
            assert parts()==expected and view.visible
    with ctx.temp_override(window=win,area=area,region=side):
        for width in (185,265,490):
            view.layout(ctx,width)
            assert all(0<=x and x+w<=width+1 for _,(x,_,w,_) in view.leaves)
            assert len([n for n,g in view.leaves if n.kind=='operator'])==9
    area.tag_redraw()
    yield .2
    yield from click(40,side.height-15)
    assert not view.visible
    yield from click(40,side.height-15)
    assert view.visible
    print('PASS inline I/O: native file pickers, 3 formats, 2 clipboard round trips, clear cancellation, reflow and reopen',flush=True)


workflow=run()
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
