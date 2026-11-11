"""Display overrides survive grouping, ungrouping and save serialization."""
from pathlib import Path
import sys
import bpy

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_support import addon, module

builder = module('builder_v2')
Group = module('group').Group
controls = module('part_controls')

def faces(obj):
    graph = bpy.context.evaluated_depsgraph_get()
    return len(obj.evaluated_get(graph).data.polygons)

for detailed, show_beam in ((True, False), (True, True), (False, False)):
    beam = builder.add_part('B_MAG_1X1', high_res=detailed).object
    beam.bbe_show_magnetic_beam = show_beam
    room = builder.add_part('B_HAB_A', high_res=detailed).object
    room.bbe_hide_ceiling = True
    room.bbe_ceiling_height = .37
    room.bbe_ceiling_height = .56
    high = faces(room)
    room.bbe_ceiling_height = .37
    assert faces(room) < high
    expected = faces(beam) + faces(room)
    full = faces(beam) + len(room.data.polygons)
    group = Group.group_objects([beam, room], room.matrix_world.copy())
    assert group is not None
    assert faces(group) == expected, (faces(group), expected)
    assert len(Group.serialise(group)) == 2
    # Render uses the intact room and the selected beam visibility.
    modifier = group.modifiers['BBE Group Cutaway']
    switch = next(n for n in modifier.node_group.nodes if n.bl_idname == 'GeometryNodeSwitch')
    link = switch.inputs['Switch'].links[0]
    output = link.from_socket
    modifier.node_group.links.remove(link)
    switch.inputs['Switch'].default_value = False
    assert faces(group) == full, (faces(group), full)
    modifier.node_group.links.new(output, switch.inputs['Switch'])
    restored = Group.ungroup_objects(addon.BUILDER, group)
    beam, room = restored
    assert beam.bbe_show_magnetic_beam == show_beam
    assert room.bbe_hide_ceiling and abs(room.bbe_ceiling_height - .37) < 1e-5
    if detailed:
        assert faces(room) + faces(beam) == expected
print('GROUP DISPLAY PASS')
