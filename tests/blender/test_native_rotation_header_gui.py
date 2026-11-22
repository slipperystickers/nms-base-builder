"""Run with --enable-event-simulate in a disposable Blender profile."""
import math
import os
from pathlib import Path
import sys
import traceback

import bpy
import numpy as np
from bpy_extras.view3d_utils import location_3d_to_region_2d
from mathutils import Quaternion

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_support import QA, module

toolbar = module('toolbar_surface')
readout = module('transform_readout')
strip = module('asset_strip')


def assert_one_badge(path, area, region, context, cached):
    """Find the captured Blender text in the screenshot, including duplicate header copies."""
    image = bpy.data.images.load(str(path), check_existing=False)
    try:
        image.colorspace_settings.name = 'Non-Color'
        pixels = np.empty(len(image.pixels), np.float32)
        image.pixels.foreach_get(pixels)
        screen = pixels.reshape(image.size[1], image.size[0], 4)[:, :, :3].min(axis=2) > .65
    finally:
        bpy.data.images.remove(image)
    texture = cached[2]
    source = np.frombuffer(cached[1], dtype=np.uint8).reshape(texture.height, texture.width, 4)
    ink = (source[:, :, :3].min(axis=2) > .65*255) & (source[:, :, 3] > 160)
    ys, xs = np.where(ink)
    pattern = ink[ys.min():ys.max()+1, xs.min():xs.max()+1]
    h, w = pattern.shape
    top = next(r for r in area.regions if r.type == 'TOOL_HEADER')
    (x, y), _, _ = readout.position(context, texture)
    band = screen[max(0,region.y+y-2):top.y+top.height, region.x:region.x+region.width]
    # Prefilter candidate origins using pixels from several different glyphs.
    candidates = np.ones((band.shape[0]-h+1, band.shape[1]-w+1), dtype=bool)
    points = np.argwhere(pattern.T)
    for px, py in points[np.linspace(0, len(points)-1, 8, dtype=int)]:
        candidates &= band[py:py+candidates.shape[0], px:px+candidates.shape[1]]
    matches = [(dy, dx) for dy, dx in np.argwhere(candidates)
               if (band[dy:dy+h, dx:dx+w] ^ pattern).sum() < .1 * pattern.sum()]
    assert len(matches) == 1 and matches[0][0] < texture.height, (path, matches)


def exercise():
    ctx = bpy.context
    window = ctx.window
    area = next(a for a in window.screen.areas if a.type == 'VIEW_3D')
    region = next(r for r in area.regions if r.type == 'WINDOW')
    key = (window.as_pointer(), area.as_pointer(), 'TOOL_HEADER')
    x, y = region.x + region.width // 2, region.y + region.height // 2

    def event(kind, value='PRESS', dx=120, dy=0, ctrl=False):
        window.event_simulate(type=kind, value=value, x=x+dx, y=y+dy, ctrl=ctrl)

    event('ESC')
    yield 0.6
    # A fresh profile can show Quick Setup followed by the welcome splash.
    event('ESC')
    event('ESC', 'RELEASE')
    yield 0.4
    area.tag_redraw()
    yield 0.5
    assert toolbar._bounds.get(key), 'Missing BBE menus before rotation'
    cube = ctx.active_object
    ctx.scene.tool_settings.snap_elements = {'INCREMENT'}
    ctx.scene.tool_settings.use_snap = False
    ctx.scene.tool_settings.snap_angle_increment_3d = math.radians(5)
    event('MOUSEMOVE', 'NOTHING')
    yield 0.2
    with ctx.temp_override(window=window, area=area, region=region):
        assert bpy.ops.transform.rotate('INVOKE_DEFAULT', constraint_axis=(False, False, True)) == {'RUNNING_MODAL'}
    yield 0.4
    event('LEFT_CTRL', ctrl=True)
    angles = []
    for dy in (55, 66):
        event('MOUSEMOVE', 'NOTHING', 110, dy, True)
        yield 0.5
        angle = math.degrees(cube.rotation_euler.z)
        assert abs(angle - 5 * round(angle / 5)) < 0.001, angle
        angles.append(angle)
    bpy.ops.screen.screenshot(filepath=str(QA/'ticket034-ctrl-rotate.png'))
    assert abs(abs(angles[0]-angles[1])-5) < 0.001, angles
    assert any(op and op.bl_idname == 'TRANSFORM_OT_rotate' for op in window.modal_operators)
    assert toolbar._bounds.get(key), 'BBE menus disappeared during Ctrl-rotate'
    assert key[:2] in readout._readouts
    event('LEFT_CTRL', 'RELEASE')
    event('ESC')
    yield 0.6
    assert abs(cube.rotation_euler.z) < 0.00001
    assert toolbar._bounds.get(key), 'Menus did not return after Cancel'
    assert key[:2] not in readout._readouts
    with ctx.temp_override(window=window, area=area, region=region):
        assert bpy.ops.transform.rotate('INVOKE_DEFAULT', constraint_axis=(False, False, True)) == {'RUNNING_MODAL'}
    yield 0.2
    event('LEFT_CTRL', ctrl=True)
    event('MOUSEMOVE', 'NOTHING', 110, 110, True)
    yield 0.4
    assert toolbar._bounds.get(key), 'BBE menus disappeared during rotation'
    before_confirm = math.degrees(cube.rotation_euler.z)
    assert abs(before_confirm) >= 4.99, before_confirm
    event('LEFTMOUSE', dx=110, dy=110, ctrl=True)
    event('LEFTMOUSE', 'RELEASE', 110, 110, True)
    event('LEFT_CTRL', 'RELEASE', 110, 110)
    yield 0.5
    assert abs(math.degrees(cube.rotation_euler.z)-before_confirm) < 0.001
    assert toolbar._bounds.get(key), 'Menus did not return after Confirm'
    assert key[:2] not in readout._readouts

    with ctx.temp_override(area=area, region=region):
        state = strip.state_for(ctx)
        if not state['enabled']:
            bpy.ops.bbe.asset_strip_toggle()
    yield 0.6
    event('MOUSEMOVE', 'NOTHING')
    yield 0.1
    event('G')
    event('G', 'RELEASE')
    yield 0.2
    event('X')
    event('X', 'RELEASE')
    event('MOUSEMOVE', 'NOTHING', 180, 50)
    yield 0.4
    assert abs(cube.location.x) > 0.01
    with ctx.temp_override(area=area, region=region):
        texture = readout._readouts[key[:2]][2]
        (_, bottom), _, height = readout.position(ctx, texture)
        assert bottom + height < state['bounds'][1]
    bpy.ops.screen.screenshot(filepath=str(QA/'ticket034-move-below-assets.png'))
    event('ESC')
    yield 0.4
    assert key[:2] not in readout._readouts and cube.location.length < 0.001

    # Both asset-browser layouts must leave room for the scale factor.
    for browser_open in (True, False):
        if not browser_open:
            with ctx.temp_override(area=area, region=region):
                bpy.ops.bbe.asset_strip_toggle()
            yield 0.4
        event('MOUSEMOVE', 'NOTHING')
        yield 0.15
        event('S')
        event('S', 'RELEASE')
        yield 0.2
        event('MOUSEMOVE', 'NOTHING', 200, 30)
        yield 0.4
        assert abs(cube.scale.x-1) > .01 and key[:2] in readout._readouts
        assert toolbar._bounds.get(key), 'BBE menus disappeared during scale'
        with ctx.temp_override(area=area, region=region):
            xy, width, height = readout.position(ctx, readout._readouts[key[:2]][2])
            assert width > 20 and height > 5
            if browser_open:
                assert xy[1]+height < state['bounds'][1]
        bpy.ops.screen.screenshot(filepath=str(QA/('ticket034-scale-' + ('assets' if browser_open else 'header') + '.png')))
        with ctx.temp_override(area=area, region=region):
            assert_one_badge(QA/('ticket034-scale-' + ('assets' if browser_open else 'header') + '.png'),
                             area, region, ctx, readout._readouts[key[:2]])
        event('ESC')
        yield 0.3
        assert abs(cube.scale.x-1) < .001 and key[:2] not in readout._readouts
    with ctx.temp_override(area=area, region=region):
        bpy.ops.bbe.asset_strip_toggle()

    space = area.spaces.active
    space.show_region_tool_header = False
    area.tag_redraw()
    yield 1.3  # The periodic workspace scan must respect a manually hidden bar.
    assert not space.show_region_tool_header
    with ctx.temp_override(area=area, region=region):
        assert not strip.visible(ctx)
        assert bpy.ops.transform.translate('INVOKE_DEFAULT') == {'RUNNING_MODAL'}
    event('MOUSEMOVE', 'NOTHING', 190, 40)
    yield .4
    assert cube.location.length > .01 and key[:2] not in readout._readouts
    bpy.ops.screen.screenshot(filepath=str(QA/'ticket034-hidden-toolbar.png'))
    event('ESC')
    yield .3
    space.show_region_tool_header = True
    area.tag_redraw()
    yield .4

    # Hit the native gizmos, which enter transforms through a different keymap.
    space = area.spaces.active
    space.region_3d.view_rotation = Quaternion((1, 0, 0, 0))
    space.region_3d.view_perspective = 'ORTHO'
    for tool, operator in [('builtin.move', 'translate'), ('builtin.rotate', 'rotate')]:
        with ctx.temp_override(area=area, region=region):
            bpy.ops.wm.tool_set_by_id(name=tool)
        area.tag_redraw()
        yield 0.5
        center = location_3d_to_region_2d(region, space.region_3d, cube.matrix_world.translation)
        cx, cy = round(region.x+center.x), round(region.y+center.y)
        # Find the X arrow or the Z ring in the default theme at this UI scale.
        path = QA / ('ticket034-' + operator + '-gizmo.png')
        bpy.ops.screen.screenshot(filepath=str(path))
        image = bpy.data.images.load(str(path), check_existing=False)
        import numpy as np
        colors = np.empty(len(image.pixels), np.float32)
        image.pixels.foreach_get(colors)
        colors = colors.reshape(image.size[1], image.size[0], 4)
        bpy.data.images.remove(image)
        hits = []
        for offset in range(12, 110):
            px, py = cx+offset, cy+(offset if operator == 'rotate' else 0)
            r, g, b = colors[py, px, :3]
            arrow = operator == 'translate' and r > 2*g and r > 2*b
            ring = operator == 'rotate' and b > 2*r and b > 1.2*g
            if arrow or ring:
                hits.append((px, py))
        assert hits, (tool, cx, cy, path)
        px, py = hits[len(hits)//2]
        def at(kind, value, dx=0, dy=0):
            window.event_simulate(type=kind, value=value, x=px+dx, y=py+dy)
        at('MOUSEMOVE', 'NOTHING')
        yield 0.2
        at('LEFTMOUSE', 'PRESS')
        yield 0.1
        at('MOUSEMOVE', 'NOTHING', 28, -24)
        yield 0.35
        at('MOUSEMOVE', 'NOTHING', 38, -34)
        yield 0.4
        bpy.ops.screen.screenshot(filepath=str(QA / ('ticket034-' + operator + '-drag.png')))
        assert key[:2] in readout._readouts, (tool, px, py, [o.bl_idname for o in window.modal_operators if o])
        at('LEFTMOUSE', 'RELEASE', 38, -34)
        yield 0.3
        assert key[:2] not in readout._readouts
    print('NATIVE ROTATION HEADER PASS', angles, flush=True)
    bpy.ops.wm.quit_blender()


steps = exercise()


def tick():
    try:
        return next(steps, None)
    except Exception:
        traceback.print_exc()
        sys.stderr.flush()
        os._exit(1)


bpy.app.timers.register(tick, first_interval=3)
