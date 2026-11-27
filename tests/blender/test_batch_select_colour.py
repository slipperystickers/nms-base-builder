"""Same Colour matches game swatches independently of IDs, finishes and state."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_support import bpy, module

select = module('utils.blend_utils').select
builder = module('builder_v2')
userdata = module('utils.userdata')
context = bpy.context


def part(part_id):
    return builder.add_part(part_id, high_res=False, user_data=0).object


seed, twin, other, finish, other_colour, other_id = [
    part(k) for k in ('BUILDFLATPANEL', 'BUILDFLATPANEL', 'BUILDWALL', 'S_FLOOR', 'BUILDFLATPANEL', 'BUILDWALL')
]
select([seed, twin, other, finish])
assert bpy.ops.object.nms_apply_colour(colour_index=37) == {'FINISHED'}
finish['UserData'] = str(userdata.set_material(int(finish['UserData']), 1) | userdata.RESERVED_BITS)
other['UserData'] = int(other['UserData'])
select([other_colour, other_id])
assert bpy.ops.object.nms_apply_colour(colour_index=42) == {'FINISHED'}

select(seed)
assert bpy.ops.object.nms_select_same_colors() == {'FINISHED'}
assert set(context.selected_objects) == {seed, twin, other, finish}
assert context.view_layer.objects.active == seed

helper = bpy.data.objects.new('Non-part', None)
context.scene.collection.objects.link(helper)
helper['UserData'] = other['UserData']
broken, hidden, locked = [part('BUILDWALL') for _ in range(3)]
broken['UserData'] = 'invalid'
hidden['UserData'] = locked['UserData'] = seed['UserData']
hidden.hide_set(True)
locked.hide_select = True
select([seed, twin])
assert context.scene.nms_batch_tool.select_same_colored_objects() == 2
assert set(context.selected_objects) == {seed, twin, other, finish}

select([seed, other_colour])
assert bpy.ops.object.nms_select_all_same_colors() == {'FINISHED'}
assert set(context.selected_objects) == {seed, twin, other, finish, other_colour, other_id}
select(seed)
assert bpy.ops.object.nms_select_same_objects() == {'FINISHED'}
assert set(context.selected_objects) == {seed, twin, other_colour}
print('BATCH COLOUR MATCH PASS', bpy.app.version_string, flush=True)
