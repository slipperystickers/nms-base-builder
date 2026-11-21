"""Follow placed instances, including group members, from the dialog draft to save records."""
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_support import addon, bpy, module

ctx = bpy.context
opt = module('save_editor.corvette_optimizer')
builder = module('builder_v2')
actions = module('save_editor.corvette_actions')
timer = module('build_timer')
Group = module('group').Group


def draft():
    state = ctx.window_manager.bbe_optimizer
    opt.populate(state, opt.load_settings())
    rows = opt.ship_instances()
    opt.populate_instances(ctx, state, ctx.scene.bbe_optimizer_order, rows)
    fake = SimpleNamespace(_scene_uid=ctx.scene.session_uid,
                           _sources=[(o.session_uid, key, pid) for o, key, pid in rows],
                           report=lambda *args: None,
                           cancel=lambda context: opt.BBE_OT_optimizer_settings.cancel(None, context))
    return state, fake


def records(optimized):
    with actions.progress_ui.Activity('Testing ship order') as progress:
        return actions.scene_parts(ctx, optimized, progress)[0]


with TemporaryDirectory() as tmp, patch.object(opt, 'settings_file', return_value=Path(tmp)/'priority.json'):
    ctx.scene.nms_main.new_file()
    parts = []
    for index, pid in enumerate(('B_COK_A', 'B_GEN_2', 'B_GEN_2', 'BUILDWALL', 'BUILDWALL')):
        obj = builder.add_part(pid, high_res=False, user_data=0).object
        obj.name = f'Instance {index}'
        obj.location.x = index * 4
        parts.append(obj)
    ctx.view_layer.update()
    group = Group.group_objects(parts[-2:])
    ctx.view_layer.update()
    before = records(False)
    automatic = records(True)
    state, dialog = draft()
    assert len(state.instances) == len(before) == 5
    indices = [i for i, row in enumerate(state.instances) if row.owner == group]
    assert len(indices) == 2
    state.active_instance = indices[-1]
    selected_group_child = state.instances[indices[-1]].child
    assert bpy.ops.bbe.move_ship_instance(action='FIRST') == {'FINISHED'}
    state.active_instance = next(i for i, row in enumerate(state.instances) if row.owner == parts[2])
    assert bpy.ops.bbe.move_ship_instance(action='LAST') == {'FINISHED'}
    assert records(True) == automatic  # The draft has not been applied.
    sources = []
    raw = ctx.scene.nms_main.serialise(objects_only=True, for_save=True, sources=sources)
    expected = [raw[sources.index((row.owner, row.child))] for row in state.instances]
    signature = timer.save_signature(ctx.scene)
    assert opt.BBE_OT_optimizer_settings.execute(dialog, ctx) == {'FINISHED'}
    assert timer.save_signature(ctx.scene) != signature
    assert expected != automatic and records(True) == expected and records(False) == before
    with patch.object(opt, 'destination', return_value=(SimpleNamespace(), [])):
        assert opt.prepare(ctx, False)[3] == expected
    parts[2].name = 'Renamed reactor'
    bpy.ops.wm.save_as_mainfile(filepath=str(Path(tmp)/'ship.blend'))
    bpy.ops.wm.open_mainfile(filepath=str(Path(tmp)/'ship.blend'))
    assert records(True) == expected
    state, dialog = draft()
    assert state.instances[0].child == selected_group_child and state.instances[-1].owner.name == 'Renamed reactor'
    bpy.ops.bbe.move_ship_instance(action='AUTO')
    dialog.cancel(ctx)
    assert records(True) == expected
    obj = builder.add_part('B_GEN_2', high_res=False).object
    obj.location.y = 42
    ctx.view_layer.update()
    assert records(True)[:-1] == expected
    bpy.data.objects.remove(ctx.scene.objects['Renamed reactor'], do_unlink=True)
    assert records(True)[:-1] == expected[:-1]
    state, dialog = draft()
    bpy.ops.bbe.move_ship_instance(action='AUTO')
    assert opt.BBE_OT_optimizer_settings.execute(dialog, ctx) == {'FINISHED'}
    assert not ctx.scene.bbe_optimizer_order
    assert records(True) == opt.core.optimize(records(False), opt.load_settings(),
                                               addon.BUILDER.get_nice_name)[0]
print('PASS ship-instance order, both export paths, group members, reopen, rename, add, delete, cancel and reset')
