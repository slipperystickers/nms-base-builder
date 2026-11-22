"""Windowed input regression for Save Manager, with synthetic save discovery."""
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from contextlib import ExitStack
from tempfile import TemporaryDirectory
import os
import sys
import traceback

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_support import bpy, module, QA

ctx = bpy.context
ui = module('sidebar_builder')
toolbar = module('tools_menu.base_builder_menu')
manager = module('save_editor.save_manager')
data = ctx.scene.nms_save_data


def run():
    win = ctx.window_manager.windows[0]
    area = next(a for a in win.screen.areas if a.type == 'VIEW_3D')
    area.spaces.active.show_region_ui = True
    ctx.preferences.view.show_splash = False
    yield .5
    region = next(r for r in area.regions if r.type == 'UI')
    port = next(r for r in area.regions if r.type == 'WINDOW')
    region.active_panel_category = ui.CATEGORY
    prefs = toolbar._preferences(ctx)
    prefs.bbe_menu_guide_version = 99
    prefs.bbe_sidebar_hidden = ','.join(k for k in toolbar.SIDE_LABELS if k != 'saves')
    with ctx.temp_override(window=win,area=area,region=port):
        module('bbe_themes').apply_theme('VIOLET')
    area.tag_redraw()
    yield .4

    def click(x,y):
        for key,value in [('MOUSEMOVE','NOTHING'),('LEFTMOUSE','PRESS'),('LEFTMOUSE','RELEASE')]:
            win.event_simulate(type=key,value=value,x=round(x+region.x),y=round(y+region.y))
            yield .1
        yield .2

    view_key=(win.as_pointer(),area.as_pointer(),'saves')
    for attempt in range(3):
        if view_key in ui._views and ui._views[view_key].visible:
            break
        yield from click(40, region.height-15)
    view=ui._views[view_key]

    def leaf(**attrs):
        return next((n,g) for n,g in view.leaves if all(n.options.get(k)==v for k,v in attrs.items()))

    def press(**attrs):
        node,g=leaf(**attrs)
        x,y,w,h=view.rect(g)
        assert node.can_click and 0 < y+h/2 < region.height,attrs
        yield from click(x+w/2,y+h/2)

    def choose(key,value):
        before=view.bottom
        yield from press(key=key)
        choices=view.dropdown
        assert choices and view.bottom==before
        left,top,w,count=view.choice_geometry()
        items=[item[0] for item in choices['items']]
        assert '' not in items
        index=items.index(value)
        assert index<count
        yield from click(left+w/2,top-(index+.5)*31*view.scale)
        assert getattr(data,key)==value

    def shot(name):
        win.event_simulate(type='MOUSEMOVE',value='NOTHING',x=port.x+100,y=port.y+200)
        yield .15
        with ctx.temp_override(window=win,area=area):
            bpy.ops.screen.screenshot(filepath=str(QA/('sidebar-save-'+name+'.png')))

    cls=manager.SaveManager
    util=manager.save_editor_utils
    kinds=util.BaseType
    def entry(kind,name,index):
        return SimpleNamespace(base_type=kind,base_name=name,base_index=index,save_context='Main',
                               parts_count=8,save_slot=['test-only'],user_data=0,galactic_address='123',issues=[])
    catalog=dict(total_parts_count=16,corvettes=[entry(kinds.CORVETTE,'Practice Corvette',0)],
                 bases=[entry(kinds.BASE,'Practice Base',7)],space=[entry(kinds.SPACE_BASE,'Orbital Base',9)],
                 spacestation=[entry(kinds.STATION,'Practice Station',10)],external=[entry(kinds.EXTERNAL_BASE,'External',12)])
    with ExitStack() as stack:
        sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
        from test_ship_link_resilience import TEMPLATE, fixture
        payload=fixture()
        player=payload['BaseContext']['PlayerStateData']
        core=module('save_editor.ship_core')
        player['CharacterCustomisationData']=[{} for _ in range(core.CUSTOM_SLOTS[0])]+[TEMPLATE['custom']]
        base=player['PersistentPlayerBases'][0]
        base['Name']='Practice Corvette'
        path=Path(stack.enter_context(TemporaryDirectory()))/'save9.hg'
        disk=module('save_editor.save_file').SaveFile(path)
        disk.json_data=core.translate(payload,False)
        disk.save()
        original=path.read_bytes()
        catalog['corvettes'][0].save_slot=[str(path)]
        for obj,func,result in [(cls,'get_accounts_enum_list',[('Default','Select Account',''),('practice','Practice Account','')]),
                                (cls,'validate_save_folder',True),
                                (util,'get_save_slots_list',[dict(slot=5,saves=[str(path)],save_name='Practice')]),
                                (util,'extract_bases_list_from_save',catalog)]:
            stack.enter_context(patch.object(obj,func,return_value=result))
        data.check_plugin_enabled=False
        area.tag_redraw()
        yield .25
        yield from shot('off')
        assert leaf(identifier='bbe.backup_settings')[1][1]==leaf(identifier='bbe.function_help')[1][1]
        yield from press(identifier='bbe.backup_settings')
        sessions=module('menu_surface')._sessions
        assert any(isinstance(v,module('build_editors').BackupFolderEditor) for v in sessions.values())
        win.event_simulate(type='ESC',value='PRESS')
        yield .25
        yield from press(key='check_plugin_enabled')
        yield from choose('nms_account_selected','practice')
        yield from choose('nms_save_slot','5')
        yield from choose('nms_base_index','0')
        assert leaf(identifier='object.nms_import_base_from_save')[0].options['primary']
        timer=module('build_timer')
        yield from press(identifier='object.nms_import_base_from_save')
        yield .5
        assert path.read_bytes()==original
        assert sum('ObjectID' in o for o in ctx.scene.objects)==len(base['Objects'])
        assert ctx.scene.nms_base_tool.string_base==base['Name']
        assert view.visible and not leaf(identifier='object.nms_import_base_from_save')[0].options['primary']
        part=next(obj for obj in ctx.scene.objects if obj.get('ObjectID')=='B_COK_D')
        part['SnapID']='custom socket identity'
        timer._parts_digest.clear()
        area.tag_redraw()
        yield .25
        assert part['SnapID']=='custom socket identity'
        for _ in range(2):
            yield from click(40, region.height-15)
            assert not view.visible
            yield from click(40, region.height-15)
            assert view.visible and view.bottom < view.top
            yield from choose('nms_base_index','0')
        assert not leaf(identifier='bbe.optimizer_export')[0].options['primary']
        yield from press(key='string_base')
        assert view.edit
        for letter in 'Aurora':
            win.event_simulate(type=letter.upper(),value='PRESS',unicode=letter)
            yield .06
        win.event_simulate(type='RET',value='PRESS')
        yield .2
        assert ctx.scene.nms_base_tool.string_base=='Aurora'
        with ctx.temp_override(window=win,area=area,region=port):
            top = module('menu_surface').draw_definition('IO', ctx)
            fields = [n.options['data'] for n in ui.walk(top) if n.options.get('key') == 'string_base']
            assert len(fields) == 2 and all(props.string_base == 'Aurora' for props in fields)
        assert leaf(identifier='bbe.optimizer_export')[0].options['primary']
        with ctx.temp_override(window=win,area=area,region=port):
            top=module('menu_surface').draw_definition('IO',ctx)
            assert any(n.options.get('identifier')=='bbe.optimizer_export' and n.options.get('primary')
                       for n in ui.walk(top))
        yield from shot('corvette')
        catalog['missing_corvettes']=[dict(context='Main',index=2,name='Fixture')]
        area.tag_redraw()
        yield .25
        yield from press(identifier='BBE_MT_corvette_picker')
        review=sessions[area.as_pointer()]
        assert review.menu=='MENU:BBE_MT_corvette_picker'
        assert any(n.options.get('identifier')=='bbe.select_corvette' for n,_ in review.leaves)
        review.finish()
        catalog.pop('missing_corvettes')
        area.tag_redraw()
        yield .3
        yield from press(key='nms_base_type',value=kinds.BASE)
        yield from choose('nms_base_index','7')
        leaf(identifier='object.nms_export_base_to_save')
        yield from shot('base')
        with ctx.temp_override(window=win,area=area,region=port):
            timer.mark_saved(ctx.scene,timer.selected_key(data))
            ctx.scene.nms_base_tool.string_base='Edited base'
        area.tag_redraw()
        yield .2
        assert leaf(identifier='object.nms_export_base_to_save')[0].options['primary']
        for kind,index in [(kinds.SPACE_BASE,'9'),(kinds.STATION,'10'),(kinds.EXTERNAL_BASE,'12')]:
            yield from press(key='nms_base_type',value=kind)
            yield from choose('nms_base_index',index)
            assert data.has_selected_base()
        assert all(n.options.get('identifier')!='object.nms_export_base_to_save' for n,_ in view.leaves)
        with ctx.temp_override(window=win,area=area,region=region):
            for width in (185,265,490):
                view.layout(ctx,width)
                assert all(x>=-1 and x+w<=width+1 for _,(x,_,w,_) in view.leaves)
        area.tag_redraw()
        yield .3
        yield from press(key='check_plugin_enabled')
        assert not data.check_plugin_enabled
    print('PASS disk import, repeated sidebar collapse/reopen and selection, five destination types, backup settings, repair menu, import/export guidance and three widths',flush=True)


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
