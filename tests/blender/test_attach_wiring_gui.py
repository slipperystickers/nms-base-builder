"""Click the viewport wiring button and sockets on real NMS parts in windowed Blender.

Run with --factory-startup --enable-event-simulate.
"""
import math
import os
import sys
import traceback
import tempfile
from pathlib import Path

import bpy
from bpy_extras.view3d_utils import location_3d_to_region_2d
from mathutils import Matrix, Quaternion, Vector

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_support import module

cables = module('cable_connections')
targets = module('cable_targets')
builder = module('builder_v2')
select = module('utils.blend_utils').select

def workflow():
    window = bpy.context.window_manager.windows[0]
    area = next(a for a in window.screen.areas if a.type == 'VIEW_3D')
    region = next(r for r in area.regions if r.type == 'WINDOW')
    view = area.spaces.active.region_3d
    def event(kind, value, point=None):
        coords = {} if point is None else dict(x=round(region.x+point.x), y=round(region.y+point.y))
        window.event_simulate(type=kind, value=value, **coords)
    def click(point):
        for kind, value in [('MOUSEMOVE','NOTHING'), ('LEFTMOUSE','PRESS'), ('LEFTMOUSE','RELEASE')]:
            event(kind, value, point)
            yield .18
    def attach(obj):
        select(obj)
        yield .4
        xy = location_3d_to_region_2d(region, view, obj.matrix_world.translation)
        scale = bpy.context.preferences.system.ui_scale
        yield from click(xy + Vector((85*scale, 37*scale)))
        assert targets.session(bpy.context), ('Attach button failed', obj.name)
    def points(obj):
        occupied = []
        result = {}
        for key, pos in cables.sockets(obj, cables.POWER).items():
            xy = location_3d_to_region_2d(region, view, pos)
            center = targets.marker_position(xy, occupied, region.width, region.height)
            assert all((center-p).length > 2*targets.SOCKET_HIT_RADIUS-1e-5 for p in occupied)
            occupied.append(center)
            result[key] = center
        return result

    def preview_visible(source, key, kind, pointer):
        start = location_3d_to_region_2d(region, view, cables.sockets(source, kind)[key])
        midpoint = (start + pointer) / 2
        with tempfile.TemporaryDirectory() as tmp:
            path = str(Path(tmp) / 'viewport.png')
            bpy.ops.screen.screenshot(filepath=path)
            image = bpy.data.images.load(path)
            try:
                image.colorspace_settings.name = 'Non-Color'
                x = round(region.x + midpoint.x)
                y = round(region.y + midpoint.y)
                for dx in (-1, 0, 1):
                    for dy in (-1, 0, 1):
                        offset = 4 * ((y+dy)*image.size[0] + x+dx)
                        r, g, b = image.pixels[offset:offset+3]
                        if kind == cables.POWER and g > .7 and g > max(r,b)*1.3:
                            return True
                        if kind == cables.BYTEBEAT and r > .8 and b > g*1.3 and r > g*1.3:
                            return True
                        if kind == cables.TELEPORT and b > .8 and b > r*1.3 and b > g:
                            return True
                return False
            finally:
                bpy.data.images.remove(image)

    def follow_mouse(source, key, kind):
        initial_count = len(bpy.context.scene.objects)
        start = location_3d_to_region_2d(region, view, cables.sockets(source, kind)[key])
        previous = None
        for delta in ((70, 105), (110, 40)):
            pointer = start + Vector(delta)
            event('MOUSEMOVE', 'NOTHING', pointer)
            yield .4
            assert preview_visible(source, key, kind, pointer), (kind, key, pointer)
            if previous is not None:
                assert not preview_visible(source, key, kind, previous)
            previous = pointer
        assert len(bpy.context.scene.objects) == initial_count
        return previous

    event('ESC','PRESS')
    event('ESC','RELEASE')
    yield .3
    bpy.context.scene.nms_main.new_file()
    def part(pid, x):
        obj = builder.add_part(pid,high_res=False).object
        obj.matrix_world = Matrix.Translation((x,0,0)) @ Matrix.Rotation(math.pi/2,4,'X')
        return obj
    inverter, door, lamp = part('U_TRANSISTOR1', -3), part('F_GDOOR', 3), part('BUILDLIGHT2', 0)
    view.view_rotation = Quaternion((1,0,0), math.pi/2)
    view.view_perspective = 'ORTHO'
    view.view_distance = 13
    view.view_location = (0,0,1.5)
    yield .6
    # In this view the door's front and back sockets project to the same pixel.
    door_keys = list(points(door))
    assert len(door_keys)==2 and len(points(inverter))==3 and len(points(lamp))==1
    for i,key in enumerate(points(inverter)):
        yield from attach(inverter)
        assert targets.session(bpy.context)['first'] is None
        assert {r[0] for r in targets.targets(bpy.context)} == {inverter.name}
        yield from click(points(inverter)[key])
        assert targets.session(bpy.context)['first'] == (inverter,key), (key, targets.session(bpy.context)['first'], points(inverter))
        dest_key = door_keys[i%2]
        yield from click(points(door)[dest_key])
        assert targets.session(bpy.context) is None
        wire = bpy.context.active_object
        assert wire.get('ObjectID')==cables.POWER
        for end,obj,expected in zip(cables.endpoints(wire),(inverter,door),(key,dest_key)):
            assert cables.control_owner(end)==obj and end['bbe_socket_key']==expected
            assert (end.matrix_world.translation-cables.sockets(obj,cables.POWER)[expected]).length<1e-4
        yield .25
    yield from attach(lamp)
    assert targets.session(bpy.context)['first'] == (lamp,next(iter(points(lamp))))
    pointer = yield from follow_mouse(lamp, next(iter(points(lamp))), cables.POWER)
    before = len(bpy.context.scene.objects)
    event('ESC','PRESS')
    event('ESC','RELEASE')
    yield .4
    assert targets.session(bpy.context) is None and len(bpy.context.scene.objects)==before
    assert not preview_visible(lamp, next(iter(points(lamp))), cables.POWER, pointer)
    yield from attach(lamp)
    yield from click(points(door)[door_keys[1]])
    assert targets.session(bpy.context) is None
    assert cables.control_owner(cables.endpoints(bpy.context.active_object)[0])==lamp
    tele_a, tele_b = part('U_MINIPORTAL', -4), part('U_MINIPORTAL', 4)
    yield .4
    assert bpy.ops.object.nms_asset_browser_object_selected(object_id=cables.TELEPORT) == {'FINISHED'}
    yield .4
    def portal_point(obj):
        return location_3d_to_region_2d(region, view, cables.sockets(obj, cables.TELEPORT)['PORTAL_A'])
    yield from click(portal_point(tele_a))
    assert targets.session(bpy.context)['first'] == (tele_a, 'PORTAL_A')
    yield from follow_mouse(tele_a, 'PORTAL_A', cables.TELEPORT)
    yield from click(portal_point(tele_b))
    assert targets.session(bpy.context) is None and bpy.context.active_object.get('ObjectID') == cables.TELEPORT

    # ByteBeat allows a wire in a completely empty scene.
    bpy.context.scene.nms_main.new_file()
    bpy.context.scene.cursor.location = (0, 2, 0)
    def start_beat():
        assert bpy.ops.object.nms_asset_browser_object_selected(object_id=cables.BYTEBEAT) == {'FINISHED'}
    def projected(position):
        return location_3d_to_region_2d(region, view, position)
    def beat_point(obj):
        return projected(cables.sockets(obj,cables.BYTEBEAT)['BYTEBEAT_A'])
    def loose_at(world):
        return projected(Vector(world))
    start_beat()
    yield .4
    yield from click(loose_at((-2,2,0)))
    assert targets.session(bpy.context)['first'][0] is None
    assert not any(o.get('ObjectID') == cables.BYTEBEAT for o in bpy.context.scene.objects)
    event('ESC','PRESS'); event('ESC','RELEASE')
    yield .4
    assert not any(o.get('rig_item') for o in bpy.context.scene.objects)
    start_beat()
    yield .4
    yield from click(loose_at((-2,2,0)))
    yield from click(loose_at((2,2,0)))
    cable = bpy.context.active_object
    assert cable.get('ObjectID') == cables.BYTEBEAT
    assert max(abs(a-b) for a,b in zip(cable.color,cables.COLORS[cables.BYTEBEAT])) < 1e-5
    ends = cables.endpoints(cable)
    for end in ends:
        assert not any(end.lock_location) and not end.animation_data and not cables.control_owner(end)
        assert abs(end.matrix_world.translation.y - 2) < 1e-4
    # Click the loose pink target, move it with Blender's native G command.
    original = ends[1].matrix_world.translation.copy()
    yield from click(projected(original))
    assert bpy.context.active_object == ends[1]
    cursor = projected(original)
    for key in ('G','Z'):
        event(key,'PRESS',cursor)
        yield .18
        event(key,'RELEASE',cursor)
        yield .18
    destination = cursor + Vector((0,60))
    event('MOUSEMOVE','NOTHING',destination)
    yield .3
    event('LEFTMOUSE','PRESS',destination)
    yield .18
    event('LEFTMOUSE','RELEASE',destination)
    yield .3
    assert abs(ends[1].matrix_world.translation.z-original.z) > .1, (original, ends[1].location)
    assert (cable.matrix_world @ Vector((0,0,1))-ends[1].matrix_world.translation).length<1e-4

    device, switch = part('BYTEBEAT', -4), part('BYTEBEATSWITCH', 4)
    yield .4
    assert set(cables.local_sockets(switch,cables.BYTEBEAT)) == {'BYTEBEAT_A'}
    assert len(cables.local_sockets(switch,cables.POWER)) == 2
    start_beat()
    yield .4
    yield from click(beat_point(device))
    assert targets.session(bpy.context)['first'] == (device, 'BYTEBEAT_A')
    yield from follow_mouse(device, 'BYTEBEAT_A', cables.BYTEBEAT)
    yield from click(beat_point(switch))
    wire = bpy.context.active_object
    assert wire.get('ObjectID') == cables.BYTEBEAT
    for end,owner in zip(cables.endpoints(wire),(device,switch)):
        assert cables.control_owner(end)==owner and end['bbe_socket_key']=='BYTEBEAT_A'
    start_beat()
    yield .4
    yield from click(loose_at((-1,2,3)))
    yield from click(beat_point(switch))
    mixed = cables.endpoints(bpy.context.active_object)
    assert cables.control_owner(mixed[0]) is None and cables.control_owner(mixed[1]) == switch
    select(device)
    yield .4
    button_y = 67 if cables.local_sockets(device,cables.POWER) else 37
    scale = bpy.context.preferences.system.ui_scale
    yield from click(projected(device.matrix_world.translation) + Vector((85*scale, button_y*scale)))
    assert targets.session(bpy.context)['first'] == (device, 'BYTEBEAT_A')
    yield from click(loose_at((2,2,3)))
    mixed = cables.endpoints(bpy.context.active_object)
    assert cables.control_owner(mixed[0]) == device and cables.control_owner(mixed[1]) is None
    # Export uses the actual moved positions and NMS's length-plus-one encoding.
    from test_support import addon
    data = addon.BUILDER.get_builder_object_from_bpy_object(cable).serialise()
    assert data['ObjectID'].lstrip('^') == cables.BYTEBEAT
    rot = Matrix.Rotation(math.pi/2,4,'X')
    at = Vector(data['At'])
    assert (rot @ Vector(data['Position'])-ends[0].matrix_world.translation).length < 1e-4
    assert (rot @ (Vector(data['Position'])+at-at.normalized())-ends[1].matrix_world.translation).length < 1e-4
    def topology():
        result = []
        for obj in bpy.context.scene.objects:
            if obj.get('ObjectID') == cables.BYTEBEAT:
                result.append(tuple((tuple(round(n,3) for n in end.matrix_world.translation),
                                     end.get('bbe_socket_key','')) for end in cables.endpoints(obj)))
        return sorted(result)
    original_topology = topology()
    payload = addon.BUILDER.serialise()
    assert len([r for r in payload['Objects'] if r['ObjectID'] == '^U_BYTEBEATLINE']) == 4
    bpy.context.scene.nms_main.new_file()
    builder.deserialise_from_data(payload)
    bpy.context.view_layer.update()
    assert topology() == original_topology, (topology(), original_topology)
    print('ATTACH WIRING GUI PASS', bpy.app.version_string, flush=True)

steps = workflow()
def tick():
    try:
        return next(steps)
    except StopIteration:
        bpy.ops.wm.quit_blender()
    except BaseException:
        traceback.print_exc()
        sys.stdout.flush()
        sys.stderr.flush()
        os._exit(1)
    return None

bpy.app.timers.register(tick, first_interval=2)
