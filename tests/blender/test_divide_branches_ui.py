"""Confirm the Logic > Divide dialog and finish its branches in Blender's event loop."""
import os
import sys
import traceback
from pathlib import Path

import bpy

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_support import addon, module

cables = module('cable_connections')
targets = module('cable_targets')
select = module('utils.blend_utils').select


def exercise():
    ctx = bpy.context
    win = ctx.window
    area = next(a for a in win.screen.areas if a.type == 'VIEW_3D')
    region = next(r for r in area.regions if r.type == 'WINDOW')
    def viewport():
        return ctx.temp_override(window=win, area=area, region=region)

    with viewport():
        ctx.scene.nms_main.new_file()
        ctx.scene.nms_main.line_switch = 'POWER'
    for count, layout in ((1, 'SPACED'), (3, 'SPACED'), (3, 'MIDPOINT')):
        with viewport():
            wire = cables.connect(None, '', None, '', cables.POWER, addon.BUILDER,
                                  free_start=(0, count, 0), free_end=(12, count, 0))
            left, right = cables.endpoints(wire)
            select(wire)
            assert bpy.ops.object.nms_divide('INVOKE_DEFAULT', starts=count, layout_mode=layout) == {'RUNNING_MODAL'}
        yield .3
        for value in ('PRESS', 'RELEASE'):
            win.event_simulate(type='RET', value=value)
            yield .1
        yield .25
        with viewport():
            session = targets.session(ctx)
            assert session and session['cursor_owner']
            points = [session['first'][0], *session.get('next_starts', [])]
            assert len(points) == count
            chain = list(dict.fromkeys([left, *points, right]))
            spans = {cables.endpoints(o) for o in ctx.scene.objects if o.get('ObjectID') == cables.POWER}
            assert all((a, b) in spans for a, b in zip(chain, chain[1:]))
            for i, point in enumerate(points):
                expected_x = 6 if layout == 'MIDPOINT' else 12 * (i+1) / (count+1)
                assert abs(point.matrix_world.translation.x - expected_x) < .0001
                assert targets.session(ctx)['first'][0] == point
                assert bpy.ops.bbe.click_cable_target(kind=cables.POWER, free=True, position=(i, count, 4)) == {'FINISHED'}
            assert targets.session(ctx) is None
            for point in set(points):
                arms = sum(point in cables.endpoints(o) for o in ctx.scene.objects if o.get('ObjectID') == cables.POWER)
                assert arms == 2 + points.count(point)
        yield .15
    print('DIVIDE DIALOG PASS', bpy.app.version_string, flush=True)


steps = exercise()
def tick():
    try:
        return next(steps)
    except StopIteration:
        bpy.ops.wm.quit_blender()
    except BaseException:
        traceback.print_exc()
        sys.stderr.flush()
        os._exit(1)


bpy.app.timers.register(tick, first_interval=1)
