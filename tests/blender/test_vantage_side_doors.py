"""Check Vantage side walls from both sides on rotated, scaled display proxies."""
import sys
from pathlib import Path

import bpy
from mathutils import Matrix, Vector
from mathutils.bvhtree import BVHTree

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_support import module

builder = module('builder_v2')
preview = module('habitat_preview')
snaps = module('corvette_snapping')
scene = bpy.context.scene
scene.nms_main.new_file()
cockpit = builder.add_part('B_COK_E')
cockpit.matrix_world = Matrix.Translation((7, -5, 3)) @ builder.X_ROT_90 @ Matrix.Scale(.6, 4)
bpy.context.view_layer.update()


def snap_pose(part, name):
    return next(matrix for key, _, _, matrix in snaps.options(part.object, cockpit.object)
                if snaps.DATA['B_COK_E'][int(key.split(':')[0])]['name'] == name)


def check_sides(east, west, detailed):
    bpy.context.view_layer.update()
    before = scene.nms_main.serialise(objects_only=True)
    preview.refresh(scene)
    bpy.context.view_layer.update()
    mesh = cockpit.object.data
    assert mesh['bbe_vantage_openings'] == 1 + 8 * east + 16 * west, mesh.name
    assert ('_HD_' in mesh.name) == detailed
    tree = BVHTree.FromObject(cockpit.object, bpy.context.evaluated_depsgraph_get())
    for side, opened in ((1, east), (-1, west)):
        hit = tree.ray_cast(Vector((side * 11, 1.5, 3)), Vector((-side, 0, 0)), 4)
        assert (hit[2] is None) == opened, (mesh.name, side, hit)
    assert before == scene.nms_main.serialise(objects_only=True)


rear_door = builder.add_part('B_DOOR0')
rear_door.matrix_world = snap_pose(rear_door, 'SnapPoint_IntN0')
for part_id in ('B_DOOR0', 'B_WALL_TOIL0'):
    attachments = [builder.add_part(part_id) for _ in range(2)]
    poses = []
    for part, side in zip(attachments, 'EW'):
        opened = snap_pose(part, f'SnapPoint_Int{side}1')
        if part_id == 'B_WALL_TOIL0':
            # The first-facing waste units opened both side walls in the game test.
            closed = snap_pose(part, f'SnapPoint_SPIGN_IntOpp{side}1')
        else:
            closed = Matrix.Translation((0, 0, 25)) @ opened
        poses.append((closed, opened))

    for detailed in (False, True):
        scene.bbe_detailed_proxies = detailed
        for east, west in ((False, False), (True, False), (True, True), (False, True), (False, False)):
            for part, (closed, opened), active in zip(attachments, poses, (east, west)):
                part.matrix_world = opened if active else closed
            check_sides(east, west, detailed)

    for part in attachments:
        bpy.data.objects.remove(part.object, do_unlink=True)
print('VANTAGE SIDE DOORS AND WASTE UNITS PASS', bpy.app.version_string)
