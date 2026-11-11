"""Build a proximity-controlled power door using ordinary exportable parts and wires."""
import math
from collections import defaultdict

import bpy
from mathutils import Matrix, Vector

from . import cable_connections as cables, cable_targets
from .utils import blend_utils, mirror_pivot


DOORS = {material + '_GDOOR' + variant
         for material in ('B', 'F', 'S', 'T') for variant in ('', 'B0', 'M0', 'T0')}
DOORS.update({'C_GDOOR', 'M_GDOOR', 'W_GDOOR'})
SUPPLIES = {'U_BATTERY_S', 'U_BIOGENERATOR', 'U_GENERATOR_S', 'U_SOLAR_S'}
INVERTER = 'U_TRANSISTOR1'
SENSOR = 'U_SWITCHPROX'
FEED, OUTPUT, CONTROL = cables.POWER_IN, cables.POWER_OUT, cables.POWER_TRIGGER


def electrical_grid(scene):
    """Index exact terminals and shared rig controls without crossing a switch."""
    links = defaultdict(set)
    wires = defaultdict(list)
    # Imported or freely placed wires can meet at the exact same location with
    # separate controls. Avoid guessing between coincident device terminals.
    positions = defaultdict(set)
    for wire in scene.objects:
        if wire.get('ObjectID') != cables.POWER:
            continue
        ends = cables.endpoints(wire)
        if not all(ends):
            continue
        a, b = map(cables.socket_identity, ends)
        links[a].add(b)
        links[b].add(a)
        for node, end, other in zip((a, b), ends, (b, a)):
            wires[node].append((end, other))
            position = tuple(round(v, 5) for v in end.matrix_world.translation)
            positions[position].add(node)
    for nodes in positions.values():
        devices = [n for n in nodes if not n[0].get('rig_item')]
        if len(nodes) < 2 or len(devices) > 1:
            continue
        join = devices[0] if devices else next(iter(nodes))
        for node in nodes - {join}:
            links[join].add(node)
            links[node].add(join)
    return links, wires


def supplied_nodes(scene, links, excluded):
    reached = {(obj, key) for obj in scene.objects if obj.get('ObjectID') in SUPPLIES
               for key in cables.local_sockets(obj, cables.POWER)}
    stack = list(reached)
    while stack:
        for node in links.get(stack.pop(), ()):
            if node not in reached and node[0] not in excluded:
                reached.add(node)
                stack.append(node)
    return reached


def nearest_supply(context, nodes, position, excluded):
    best = None
    for obj, key in nodes:
        if obj in excluded or not cable_targets.visible(context, obj):
            continue
        point = cables.sockets(obj, cables.POWER).get(key)
        if point is None:
            continue
        distance = (position - point).length_squared
        if distance <= 1e-12:
            continue
        rank = (distance, obj.name, key)
        if best is None or rank < best[0]:
            best = rank, (obj, key)
    return best[1] if best else None


def installed_pair(door_nodes, links):
    for node in door_nodes:
        for inv, out in links.get(node, ()):
            if inv.get('ObjectID') == INVERTER and out == OUTPUT:
                for prox, control_side in links.get((inv, CONTROL), ()):
                    if (prox.get('ObjectID') == SENSOR and control_side == OUTPUT
                            and (prox, FEED) in links.get((inv, FEED), ())):
                        return inv, prox
    return None


def add_controls(door, socket, builder, created):
    from . import builder_v2
    # Native Y is up. Mount both devices on the front of the lintel.
    face = Matrix.Rotation(math.pi / 2, 4, 'X')
    result = []
    for pid, x in ((INVERTER, .62), (SENSOR, -.62)):
        part = builder_v2.add_part(pid, builder_object=builder)
        obj = part.object
        created.append(obj)
        anchor = socket + Vector((x, 0, 0))
        mesh = door.evaluated_get(bpy.context.evaluated_depsgraph_get())
        hit, surface, _, _ = mesh.ray_cast(anchor + Vector((0, 0, 1)), Vector((0, 0, -1)), distance=2)
        if hit:
            anchor.z = surface.z
        pose = door.matrix_world @ Matrix.Translation(anchor) @ face
        obj.matrix_world = mirror_pivot.display_matrix(pose, pid) if mirror_pivot.is_normalized(obj) else pose
        result.append(obj)
    bpy.context.view_layer.update()
    return result


class BBE_OT_door_proximity(bpy.types.Operator):
    bl_idname = 'bbe.add_door_proximity'
    bl_label = 'Add Prox Control'
    bl_description = 'Wire a proximity switch and inverter to this door and the nearest supply-connected socket'
    bl_options = {'UNDO'}
    owner: bpy.props.StringProperty(options={'SKIP_SAVE', 'HIDDEN'})

    def execute(self, context):
        door = context.active_object
        if (context.mode != 'OBJECT' or door is None or not door.select_get()
                or door.get('ObjectID') not in DOORS or (self.owner and self.owner != door.name)):
            self.report({'WARNING'}, 'Select a power door.')
            return {'CANCELLED'}
        from .builder import get_builder
        builder = get_builder()
        context.view_layer.update()
        ports = cables.local_sockets(door, cables.POWER)
        # Native front socket, including the salvaged variants with numbered keys.
        door_key = max(ports, key=lambda key: ports[key].z)
        door_nodes = [(door, key) for key in ports]
        links, wires = electrical_grid(context.scene)
        pair = installed_pair(door_nodes, links)
        excluded = {door, *(pair or ())}
        live = supplied_nodes(context.scene, links, excluded)
        previous = [entry for node in door_nodes for entry in wires.get(node, ())]
        if not pair and previous and (len(previous) != 1 or previous[0][1] not in live):
            self.report({'WARNING'}, 'This door already has custom wiring. Disconnect its door leads before adding proximity control.')
            return {'CANCELLED'}
        created = []
        moved_feed = None

        def wire(a, key_a, b, key_b):
            if cables.existing_connection(a, key_a, b, key_b, cables.POWER):
                return
            obj = cables.connect(a, key_a, b, key_b, cables.POWER, builder)
            created.append(obj)
            created.extend(end for end in cables.endpoints(obj) if end not in (a, b))

        try:
            if pair:
                inv, prox = pair
                if any(node != (prox, FEED) for node in links.get((inv, FEED), ())):
                    self.report({'INFO'}, 'This door already has a wired proximity circuit.')
                    return {'FINISHED'}
            else:
                inv, prox = add_controls(door, ports[door_key], builder, created)
                wire(inv, OUTPUT, door, door_key)
                wire(inv, FEED, prox, FEED)
                wire(prox, OUTPUT, inv, CONTROL)
            if previous and not pair:
                # Move the original supply lead off the door to prevent a bypass.
                end, _ = previous[0]
                moved_feed = (end, end.get('bbe_socket_key'))
                cables.bind(end, inv, FEED, cables.POWER)
                context.view_layer.update()
            else:
                origin = cables.sockets(inv, cables.POWER)[FEED]
                source = nearest_supply(context, live, origin, {door, inv, prox})
                if source:
                    wire(inv, FEED, *source)
                else:
                    blend_utils.select(inv)
                    result = bpy.ops.bbe.start_cable_connection('INVOKE_DEFAULT', kind=cables.POWER,
                                                               source_name=inv.name, source_key=FEED)
                    if result == {'CANCELLED'}:
                        raise ValueError('Could not start the electrical cable picker.')
                    cable_targets.session(context)['excluded_devices'] = {door, prox}
                    self.report({'INFO'}, 'Proximity circuit ready. Click the supply for the highlighted feed wire.')
                    return {'FINISHED'}
        except (ValueError, RuntimeError, KeyError) as error:
            if moved_feed:
                end, key = moved_feed
                cables.bind(end, door, key, cables.POWER)
            if created:
                bpy.data.batch_remove(created)
            blend_utils.select(door)
            self.report({'WARNING'}, str(error))
            return {'CANCELLED'}
        blend_utils.select(door)
        self.report({'INFO'}, 'Proximity control connected to the power grid.')
        return {'FINISHED'}
