"""Exercise real prefab menus, browser tiles and thumbnail caching in an isolated GUI profile."""
from pathlib import Path
import json
import os
import shutil
import sys
import tempfile
import traceback
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_support import bpy, addon, module, QA


def exercise():
    ctx = bpy.context
    ctx.preferences.view.show_splash = False
    win = ctx.window_manager.windows[0]
    area = next(a for a in win.screen.areas if a.type == 'VIEW_3D')
    port = next(r for r in area.regions if r.type == 'WINDOW')
    win.event_simulate(type='ESC', value='PRESS')
    yield .3
    cache = module('prefab_thumbnails')
    ui = module('menu_surface')
    grid = module('tools.asset_browser_grid')
    preset = module('preset').Preset
    before = tuple(obj.as_pointer() for obj in ctx.scene.objects)
    selection = tuple(obj.as_pointer() for obj in ctx.selected_objects)
    original = preset.PRESET_PATH
    with tempfile.TemporaryDirectory() as directory:
        preset.PRESET_PATH = directory
        record = dict(ObjectID='^BUILDFLATPANEL', Position=[0,0,0], Up=[0,1,0], At=[0,0,1])
        for number, key in enumerate(('Prefab','Objects')):
            path = Path(directory)/('Outline '+str(number)+'.nmsprefab')
            path.write_text(json.dumps({key:[dict(record,Position=[x,0,0]) for x in range(1+number)]}))
        samples = os.environ.get('BBE_PREVIEW_TEST_SAMPLES')
        if samples:
            for name in ('little bridge', 'FurbyFreezer'):
                shutil.copyfile(Path(samples)/(name+'.nmsprefab'), Path(directory)/(name+'.nmsprefab'))
        addon.refresh_prefab_catalogue()
        names = list(preset.get_presets())
        with ctx.temp_override(window=win, area=area, region=port):
            bpy.ops.bbe.custom_menu('INVOKE_DEFAULT', menu='PREFABS')
        prefs = ctx.preferences.addons[addon.__package__].preferences
        popup = ui._sessions[area.as_pointer()]

        def toggle():
            node, geometry = next((n,g) for n,g in popup.leaves if n.options.get('key')=='bbe_prefab_previews')
            x,y,w,h = popup.rect(geometry)
            for key, value in [('MOUSEMOVE','NOTHING'),('LEFTMOUSE','PRESS'),('LEFTMOUSE','RELEASE')]:
                win.event_simulate(type=key,value=value,x=round(port.x+x+w/2),y=round(port.y+y+h/2))
                yield .08

        assert not prefs.bbe_prefab_previews
        with patch.object(cache.subprocess,'Popen',side_effect=AssertionError('Disabled renderer launched')):
            yield .3
            assert all(cache.get(name) is None for name in names)
            assert not cache._pending and not cache._keys and cache._worker is None
            assert not bpy.app.timers.is_registered(cache._tick)

        # Disable while a real batch is running, then re-enable using the menu switch.
        prefs.bbe_prefab_previews = True
        for name in names:
            cache.get(name)
        cache._tick()
        worker = cache._worker
        assert worker is not None
        prefs.bbe_prefab_previews = False
        assert worker.poll() is not None
        assert not cache._pending and not cache._running and cache._worker is None
        assert not bpy.app.timers.is_registered(cache._tick)
        yield from toggle()
        assert prefs.bbe_prefab_previews
        for _ in range(100):
            if all(str(Path(directory)/(name+'.nmsprefab')) in cache._keys for name in names) and len(cache._resident)>=len(names):
                break
            yield .1
        previews = {name:cache.get(name) for name in names}
        assert all(p and tuple(p.image_size)==(128,128) for p in previews.values()), previews
        for p in previews.values():
            alpha = list(p.image_pixels_float)[3::4]
            assert min(alpha)==0 and max(alpha)>.95
        popup = ui._sessions[area.as_pointer()]
        assert {n.options['props'].part_id for n,g in popup.leaves if n.options.get('identifier')=='object.list_build_operator'} == set(names)
        with ctx.temp_override(window=win,area=area):
            bpy.ops.screen.screenshot(filepath=str(QA/'prefab-preview-menu.png'))
        popup.finish()
        with ctx.temp_override(window=win,area=area,region=port):
            ctx.scene.nms_asset_browser.show_presets()
            bpy.ops.object.nms_launch_asset_browser_window('EXEC_DEFAULT',target_width=850,target_height=620)
        for _ in range(80):
            if grid._sessions:
                session=next(iter(grid._sessions.values()))
                if session._tiles and all(tile[-1].get('is_preset') for tile in session._tiles):
                    break
            yield .1
        assert set(session._groups['Presets'])==set(names)
        yield .4
        with ctx.temp_override(window=session._window,area=session._area):
            bpy.ops.screen.screenshot(filepath=str(QA/'prefab-preview-browser.png'))
        assert before == tuple(obj.as_pointer() for obj in win.scene.objects)
        assert selection == tuple(obj.as_pointer() for obj in ctx.selected_objects)
        # A saved PNG must survive a fresh preview collection without launching the renderer.
        cache.close()
        addon.refresh_prefab_catalogue()
        with patch.object(cache.subprocess,'Popen',side_effect=AssertionError('Unexpected warm render')):
            for name in names:
                cache.get(name)
            yield .4
            assert all(cache.get(name) for name in names)
        with patch.object(cache.subprocess,'Popen',side_effect=AssertionError('Disabled browser launched renderer')):
            prefs.bbe_prefab_previews = False
            yield .4
            assert all(cache.get(name) is None for name in names)
            assert json.loads(module('settings_memory').path().read_text())['preferences']['bbe_prefab_previews'] is False
            assert not bpy.app.timers.is_registered(cache._tick)
            prefs.bbe_prefab_previews = True
            assert all(cache.get(name) for name in names)
        old=cache.get('Outline 0').icon_id
        path=Path(directory)/'Outline 0.nmsprefab'
        path.write_text(json.dumps({'Objects':[dict(record,ObjectID='^T_WALL_Q1')]}))
        addon.refresh_prefab_catalogue()
        for _ in range(80):
            current=cache.get('Outline 0')
            if current and current.icon_id!=old:
                break
            yield .1
        assert current and current.icon_id!=old
        preset.PRESET_PATH=original
    print('PASS local thumbnails: menus, browser tiles, scene isolation, warm reuse and regeneration',flush=True)


steps=exercise()
def tick():
    try:
        return next(steps)
    except StopIteration:
        bpy.ops.wm.quit_blender()
    except Exception:
        traceback.print_exc()
        sys.stderr.flush()
        os._exit(1)

bpy.app.timers.register(tick, first_interval=1.2)

