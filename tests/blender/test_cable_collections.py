"""Individual Asset Browser placements, hidden rig exports, and legacy .blend loading."""
from pathlib import Path
import sys
import tempfile

import bpy

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_support import addon, module

c = module('cable_connections')
targets = module('cable_targets')
ctx = bpy.context
ctx.scene.nms_main.new_file()
devices = []
for x in (0, 12):
    obj = addon.BUILDER.add_part('U_MINIPORTAL', build_rigs=False).object
    obj.location.x = x
    devices.append(obj)
ctx.view_layer.update()
placed = {}
for kind in c.COLLECTIONS:
    assert bpy.ops.object.nms_asset_browser_object_selected(object_id=kind) == {'FINISHED'}
    if kind in c.KINDS:
        assert targets.session(ctx)['kind'] == kind
        if kind == c.TELEPORT:
            for obj in devices:
                assert bpy.ops.bbe.click_cable_target(owner=obj.name, key='PORTAL_A', kind=kind) == {'FINISHED'}
        else:
            for point in ((2, 5, 0), (7, 5, 0)):
                assert bpy.ops.bbe.click_cable_target(free=True, position=point, kind=kind) == {'FINISHED'}
    cable = next(obj for obj in ctx.scene.objects if obj.get('ObjectID') == kind)
    placed[kind] = cable
    collection, = cable.users_collection
    assert collection.get('bbe_cable_kind') == kind
    assert collection.name == c.COLLECTIONS[kind]
    for end in c.endpoints(cable):
        if end is not None:
            assert end.users_collection == (collection,)

loose = c.junction(addon.BUILDER, c.POWER, (0,4,0))
assert loose.users_collection == placed[c.POWER].users_collection
ctx.view_layer.update()
for kind, cable in placed.items():
    collection, = cable.users_collection
    layer = ctx.view_layer.layer_collection.children[collection.name]
    layer.hide_viewport = True
    ctx.view_layer.update()
    assert not cable.visible_get()
    assert all(not ctrl.visible_get() for ctrl in c.endpoints(cable) if ctrl is not None)
    assert all(other.visible_get() for k,other in placed.items() if k != kind)
    assert all(obj.visible_get() for obj in devices)
    assert all('^'+k in {row['ObjectID'] for row in addon.BUILDER.serialise()['Objects']} for k in placed)
    layer.hide_viewport = False

# A game-build import recreates all four line types and their endpoint rigs.
payload = addon.BUILDER.serialise()
ctx.scene.nms_main.new_file()
module('builder_v2').deserialise_from_data(payload)
placed = {o['ObjectID']:o for o in ctx.scene.objects if o.get('ObjectID') in c.COLLECTIONS}
assert len(placed) == 4
for kind, cable in placed.items():
    collection, = cable.users_collection
    assert collection.get('bbe_cable_kind') == kind
    ends = c.endpoints(cable)
    assert all(ends) and all(end.users_collection == (collection,) for end in ends)
loose = c.junction(addon.BUILDER, c.POWER, (0,4,0))

# Reopen a legacy scene with unsorted lines, a loose point, and a collection the user renamed.
electrical, = placed[c.POWER].users_collection
electrical.name = 'My wiring'
for obj in [*placed.values(), loose, *(end for cable in placed.values() for end in c.endpoints(cable) if end)]:
    if obj.name not in ctx.scene.collection.objects:
        ctx.scene.collection.objects.link(obj)
    for collection in obj.users_collection:
        if collection != ctx.scene.collection:
            collection.objects.unlink(obj)
with tempfile.TemporaryDirectory() as work:
    filename = str(Path(work)/'legacy.blend')
    bpy.ops.wm.save_as_mainfile(filepath=filename)
    bpy.ops.wm.open_mainfile(filepath=filename)
    for kind in c.COLLECTIONS:
        cable = next(o for o in ctx.scene.objects if o.get('ObjectID') == kind)
        collection, = cable.users_collection
        assert collection.get('bbe_cable_kind') == kind
        assert all(ctrl.users_collection == (collection,) for ctrl in c.endpoints(cable) if ctrl)
    assert next(o for o in ctx.scene.objects if o.get('bbe_junction')).users_collection[0].name == 'My wiring'
print('ASSET BROWSER CABLE COLLECTIONS PASS', bpy.app.version_string)
