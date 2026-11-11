"""Exercise Curve Studio selection, history, and tool exits in Blender's event loop."""
from pathlib import Path
import os
import sys
import traceback

import bpy

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_support import module

studio = module('curve_studio')
curves = module('curve_tools')
builder = module('builder_v2')
overrides = ('LOCAL', 'INDIVIDUAL_ORIGINS')


def exercise():
    ctx = bpy.context
    area = next(a for a in ctx.screen.areas if a.type == 'VIEW_3D')
    region = next(r for r in area.regions if r.type == 'WINDOW')
    ctx.scene.nms_main.new_file()
    seed = builder.add_part('BUILDWALL', high_res=False).object
    with ctx.temp_override(area=area, region=region):
        bpy.ops.transform.create_orientation(name='Workshop axes', use=True)
    original = ('Workshop axes', 'CURSOR')
    ctx.scene.tool_settings.transform_pivot_point = original[1]
    guide = curves.new_curve(ctx, 'CIRCLE')
    studio.choose(ctx, [guide, seed])
    ctx.scene.nms_build_tool.duplicate_along_curve(4, 1)
    guide_name = guide.name
    other = builder.add_part('BUILDFLATPANEL', high_res=False).object
    other_name = other.name
    studio.select_children(ctx, guide)
    assert studio.transform_settings(ctx.scene) == overrides
    bpy.ops.bbe.studio_action(action='PIVOT')
    studio.select_parent(ctx, guide)
    yield .4
    studio.select_children(ctx, guide)
    assert studio.transform_settings(ctx.scene) == ('LOCAL', 'MEDIAN_POINT')

    studio.choose(ctx, [other])
    yield .5
    assert studio.transform_settings(ctx.scene) == original
    original = ('VIEW', 'ACTIVE_ELEMENT')
    studio.set_transform_settings(ctx.scene, *original)
    studio.select_children(ctx, guide)
    for obj in ctx.selected_objects:
        obj.select_set(False)
    yield .5
    assert studio.transform_settings(ctx.scene) == original

    studio.select_children(ctx, guide)
    ctx.scene.bbe_curve_helper = False
    yield .5
    assert studio.transform_settings(ctx.scene) == original
    ctx.scene.bbe_curve_helper = True

    studio.select_parent(ctx, guide)
    bpy.ops.ed.undo_push(message='Before editing followers')
    bpy.ops.bbe.studio_action(action='CHILDREN')
    bpy.ops.ed.undo_push(message='Editing followers')
    bpy.ops.ed.undo()
    yield 2
    assert studio.transform_settings(ctx.scene) == original, ('Undo', studio.transform_settings(ctx.scene))
    bpy.ops.ed.redo()
    yield 2
    assert studio.transform_settings(ctx.scene) == overrides, ('Redo', studio.transform_settings(ctx.scene))
    studio.choose(ctx, [ctx.scene.objects[other_name]])
    yield .5
    assert studio.transform_settings(ctx.scene) == original, ('Redo exit', studio.transform_settings(ctx.scene))
    guide = ctx.scene.objects[guide_name]

    studio.select_children(ctx, guide)
    scene = ctx.scene
    second = bpy.data.scenes.new('Other workspace scene')
    ctx.window.scene = second
    yield .5
    assert studio.transform_settings(scene) == original
    ctx.window.scene = scene
    studio.select_children(ctx, guide)
    bpy.ops.bbe.studio_action(action='DETACH')
    assert studio.transform_settings(ctx.scene) == original
    print('CURVE TRANSFORM RESTORE PASS', bpy.app.version_string, flush=True)
    bpy.ops.wm.quit_blender()


steps = exercise()
def tick():
    try:
        return next(steps, None)
    except BaseException:
        traceback.print_exc()
        sys.stderr.flush()
        os._exit(1)


bpy.app.timers.register(tick, first_interval=2)
