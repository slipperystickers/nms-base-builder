"""Exercise browser variants, multi-part curves, pipe placement and connector choices."""
from pathlib import Path
import sys
import bpy
from mathutils import Vector

sys.path.insert(0,str(Path(__file__).resolve().parent))
from test_support import module, addon

v = module('builder_v2')
curve = module('utils.curve')
studio = module('curve_tools')
select = module('utils.blend_utils').select
cables = module('cable_connections')
targets = module('cable_targets')
prefs = module('utils.asset_browser_utils')
markers = module('snap_markers')
area = next(a for a in bpy.context.screen.areas if a.type == 'VIEW_3D')
region = next(r for r in area.regions if r.type == 'WINDOW')

with bpy.context.temp_override(area=area,region=region):
    bpy.context.scene.nms_main.new_file()
    for studio_action in (False, True):
        left = v.add_part('W_WALL', high_res=False).object
        right = v.add_part('W_FLOOR', high_res=False).object
        right.location.x = left.location.x + 3
        select([left,right])
        guide = studio.new_curve(bpy.context,'CIRCLE')
        assert set(bpy.context.selected_objects) == {guide,left,right}
        if studio_action:
            assert bpy.ops.bbe.studio_action(action='DUPLICATE') == {'FINISHED'}
        else:
            assert bpy.ops.object.nms_duplicate_along_curve(number_of_objects=3) == {'FINISHED'}
        followers = curve.get_all_curve_children(guide)
        assert len(followers) == (10 if studio_action else 3)
        for follower in followers:
            entries = module('group').Group.serialise(follower)
            assert {x['ObjectID'].lstrip('^') for x in entries} == {'W_WALL','W_FLOOR'}
            assert abs((Vector(entries[0]['Position'])-Vector(entries[1]['Position'])).length-3) < 1e-4
        curve.select_children_of_curve(guide)
        assert not guide.hide_select
        name = guide.name
        select(followers[0])
        assert bpy.ops.object.nms_curve_delete() == {'FINISHED'}
        assert name not in bpy.data.objects and not any(o.get('curve_parent')==name for o in bpy.data.objects)

    # A grouped seed can be combined with another part without nesting game records.
    group = next(o for o in bpy.context.scene.objects if o.get('GroupID'))
    extra = v.add_part('W_ROOF', high_res=False).object
    select([group, extra])
    guide = studio.new_curve(bpy.context, 'LINE')
    assert bpy.ops.object.nms_duplicate_along_curve(number_of_objects=2) == {'FINISHED'}
    for follower in curve.get_all_curve_children(guide):
        assert follower['part_count'] == 3
        assert len(module('group').Group.serialise(follower)) == 3

    part = v.add_part('B_COK_C7').object
    cockpits = prefs.build_category_tree()['Corvette']['Cockpits and Habitation Modules']
    for i in range(1, 10):
        pid = f'B_COK_C{i}'
        assert pid in cockpits and not cockpits[pid].get('variants')
        assert bpy.ops.object.nms_asset_browser_object_selected(object_id=pid) == {'FINISHED'}
        assert bpy.context.active_object.get('ObjectID') == pid
    for target in ('B_COK_C8', 'B_COK_C9'):
        select(part)
        assert bpy.ops.object.nms_asset_browser_batch_replace(object_id=target) == {'FINISHED'}
        part = bpy.context.active_object
        assert part.get('ObjectID') == target and bpy.context.selected_objects == [part]
    props = dict(prefs.read_store())
    try:
        for enabled in (False, True):
            prefs.write_store(dict(props,auto_snap=enabled))
            for pid in ('PIPE', 'PIPESHAPE', 'CURVEPIPESHAPE','BASE_BUBPIPE'):
                bpy.context.scene.nms_main.new_file()
                for i in range(2):
                    assert bpy.ops.object.nms_asset_browser_object_selected(object_id=pid)=={'FINISHED'}
                    obj=bpy.context.active_object
                    assert bpy.context.selected_objects == [obj] and markers.objects(bpy.context) is None
                    if i==0:
                        previous=obj
                assert (previous.matrix_world.translation-obj.matrix_world.translation).length > .05, pid
    finally:
        prefs.write_store(props)

    a = v.add_part('U_BATTERY_S').object
    others = [v.add_part('U_SWITCHBUTTON').object for _ in range(2)]
    for i,o in enumerate(others):
        o.location.x += (i+1)*12
    select([*others,a])
    bpy.context.scene.nms_main.line_switch = 'POWER'
    assert bpy.ops.object.nms_connect()=={'FINISHED'}
    assert not [w for w in bpy.context.scene.objects if w.get('ObjectID')==cables.POWER]
    start = Vector((20, 8, 1))
    assert bpy.ops.bbe.click_cable_target(kind=cables.POWER,free=True,position=start)=={'FINISHED'}
    wires=[w for w in bpy.context.scene.objects if w.get('ObjectID')==cables.POWER]
    assert len(wires)==3
    controls=[cables.endpoints(w) for w in wires]
    assert len({left for left, right in controls})==1
    assert (controls[0][0].matrix_world.translation-start).length < 1e-5
    expected = min(cables.sockets(a,cables.POWER).items(),key=lambda row:(row[1]-start).length_squared)[0]
    assert {(cables.control_owner(end),end['bbe_socket_key']) for _,end in controls} == {
        (others[0],'POWER_A'),(others[1],'POWER_A'),(a,expected)}
    assert targets.session(bpy.context) is None
print('WORKFLOW FIXES PASS')

