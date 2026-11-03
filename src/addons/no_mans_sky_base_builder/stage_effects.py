"""Original BBE preview effects, using the local NMS Preview viewer as reference.

Display materials and lamps only; never changes meshes or exported placements.
White pill accents use short-range spill around their luminous surfaces.
Coloured fixtures retain the game's surrounding spill, including embedded stacks.
"""
import json
import math
import re
from pathlib import Path
from functools import lru_cache
from . import hd_library
import bpy
from mathutils import Vector

TAG = 'bbe_stage_effect'
LINKS = 'bbe_stage_material_links'
COLOURS = {
    'WALLLIGHTBLUE': (.12,.48,1), 'WALLLIGHTGREEN': (.16,1,.38),
    'WALLLIGHTPINK': (1,.12,.55), 'WALLLIGHTRED': (1,.08,.05),
    'WALLLIGHTWHITE': (1,1,1), 'WALLLIGHTYELLOW': (1,.72,.08),
    'B_GEN_3': (.12,.48,1), 'SWARM_TROPHY_G': (.08,1,.22),
    'SWARM_TROPHY_R': (1,.08,.04), 'SWARM_TROPHY_B': (.08,.38,1),
    'SET_CLASS_A': (.52,.16,1), 'SET_CLASS_B': (.15,.48,1),
    'SET_CLASS_S': (1,.65,.08),
    'BASE_BEAMSTONE': (1,.18,.025),
}
POWER_PARTS = {'B_GEN_' + str(i) for i in range(6)} | {'B_TRU_' + c for c in 'ABCDEFGH'}
COLOURS.update({pid: (.025, .12, 1) for pid in POWER_PARTS})


def preview_value(scene, name):
    return scene.get('bbe_stage_applied', {}).get(name, getattr(scene.bbe_stage, name))


def soften_door(mat):
    """Soften both hologram surfaces and fade the tube depth; keep the door rim."""
    tree = mat.node_tree
    coords = tree.nodes.new('ShaderNodeTexCoord')
    axes = tree.nodes.new('ShaderNodeSeparateXYZ')
    fade = tree.nodes.new('ShaderNodeMapRange')
    fade.name = 'BBE Door Edge Fade'
    fade.interpolation_type = 'SMOOTHERSTEP'
    fade.inputs['From Min'].default_value = 1.05
    fade.inputs['From Max'].default_value = 3.17577
    fade.inputs['To Min'].default_value = .38
    fade.inputs['To Max'].default_value = 0
    tree.links.new(coords.outputs['Object'], axes.inputs[0])
    tree.links.new(axes.outputs['Z'], fade.inputs['Value'])
    output = next(n for n in tree.nodes if n.type == 'OUTPUT_MATERIAL')
    source = output.inputs['Surface'].links[0].from_socket
    transparent = tree.nodes.new('ShaderNodeBsdfTransparent')
    mix = tree.nodes.new('ShaderNodeMixShader')
    tree.links.new(fade.outputs['Result'], mix.inputs[0])
    tree.links.new(transparent.outputs[0], mix.inputs[1])
    tree.links.new(source, mix.inputs[2])
    tree.links.new(mix.outputs[0], output.inputs['Surface'])
    mat.surface_render_method = 'BLENDED'


def hull_seep(mat, shader, embedded=False, water=False):
    """A small warm back-light response for the game's thin-hull light bleed."""
    tree = mat.node_tree
    tint = tree.nodes.new('ShaderNodeMixRGB')
    tint.blend_type = 'MULTIPLY'
    tint.inputs[0].default_value = 1
    tint.inputs[2].default_value = (.32, .32, .32, 1) if embedded else (.12, .05, .007, 1)
    base = shader.inputs['Base Color']
    if base.is_linked:
        tree.links.new(base.links[0].from_socket, tint.inputs[1])
    else:
        tint.inputs[1].default_value = base.default_value
    translucent = tree.nodes.new('ShaderNodeBsdfTranslucent')
    translucent.name = 'BBE Embedded Light Seep' if embedded else 'BBE Warm Hull Seep'
    if water:
        # The native water colour contains dark surface reflections. Using
        # those as absorption also extinguishes lamps placed under the pond.
        translucent.inputs['Color'].default_value = (.25, .35, .4, 1)
        if shader.inputs['Normal'].is_linked:
            tree.links.new(shader.inputs['Normal'].links[0].from_socket, translucent.inputs['Normal'])
    else:
        tree.links.new(tint.outputs[0], translucent.inputs['Color'])
    output = next(n for n in tree.nodes if n.type == 'OUTPUT_MATERIAL')
    source = output.inputs['Surface'].links[0].from_socket
    add = tree.nodes.new('ShaderNodeAddShader')
    tree.links.new(source, add.inputs[0])
    tree.links.new(translucent.outputs[0], add.inputs[1])
    tree.links.new(add.outputs[0], output.inputs['Surface'])


@lru_cache(maxsize=2)
def effect_data(root):
    if root is None:
        return {}, {}
    return (json.loads((root / 'lighting_profiles.json').read_text()),
            json.loads((root / 'display_effects/lights.json').read_text()))


@lru_cache(maxsize=1)
def freighter_profiles():
    return json.loads((Path(__file__).parent / 'resources/freighter_lighting.json').read_text())


def display_effect(part, collection):
    pid = part.get('ObjectID', '').lstrip('^')
    root = hd_library.scenes_root()
    _, effect_lights = effect_data(root)
    fire = pid == 'BLD_FIREPIT'
    if pid not in effect_lights and not fire:
        return
    name = ('BBE Effect 18.1.21 / ' if fire else 'BBE Effect 18.1.9 / ') + pid
    mesh = bpy.data.meshes.get(name)
    if mesh is None:
        path = (Path(__file__).parent / 'resources' if fire else root) / 'display_effects' / (pid + '.blend')
        with bpy.data.libraries.load(str(path), link=False) as (source, target):
            target.objects = list(source.objects)
        for obj in target.objects:
            if obj is not None:
                if obj.type == 'MESH' and mesh is None:
                    mesh = obj.data
                    mesh.name = name
                bpy.data.objects.remove(obj, do_unlink=True)
    if mesh:
        obj = bpy.data.objects.new(('BBE Flame / ' if fire else 'BBE Hover Effect / ') + part.name, mesh)
        obj[TAG] = obj['bbe_stage_owned'] = True
        collection.objects.link(obj)
        obj.parent = part
        obj.hide_select = True


def material_nodes(tree, seen=None):
    seen = set() if seen is None else seen
    if tree is None or tree.as_pointer() in seen:
        return
    seen.add(tree.as_pointer())
    for node in tree.nodes:
        yield node
        if node.type == 'GROUP':
            yield from material_nodes(node.node_tree, seen)


def restore_object_materials(obj):
    saved = json.loads(obj.get(LINKS, '{}'))
    for index, link in saved.items():
        if int(index) >= len(obj.material_slots):
            continue
        slot = obj.material_slots[int(index)]
        mat = slot.material
        if mat and mat.get(TAG) and mat.get('bbe_stage_source'):
            slot.material = mat['bbe_stage_source']
            slot.link = link
    if LINKS in obj:
        del obj[LINKS]


def release_material_override(obj, index):
    """A newly painted proxy must display its new material immediately."""
    saved = json.loads(obj.get(LINKS, '{}'))
    if str(index) not in saved or index >= len(obj.material_slots):
        return
    slot = obj.material_slots[index]
    if slot.material and slot.material.get(TAG):
        slot.link = saved.pop(str(index))
        if saved:
            obj[LINKS] = json.dumps(saved)
        elif LINKS in obj:
            del obj[LINKS]


def restore_materials(scene):
    for obj in scene.objects:
        restore_object_materials(obj)
    for mat in list(bpy.data.materials):
        if mat.get(TAG) and mat.users == 0:
            bpy.data.materials.remove(mat)


def clear(scene):
    restore_materials(scene)
    coll = scene.bbe_stage.collection
    if coll:
        for obj in list(coll.objects):
            if obj.get(TAG):
                data = obj.data
                bpy.data.objects.remove(obj, do_unlink=True)
                if data.users == 0:
                    if isinstance(data, bpy.types.Light):
                        bpy.data.lights.remove(data)
                    elif isinstance(data, bpy.types.Mesh):
                        bpy.data.meshes.remove(data)


def emissive(node):
    if node.type not in {'BSDF_PRINCIPLED', 'EMISSION'}:
        return False
    strength = node.inputs['Emission Strength' if node.type == 'BSDF_PRINCIPLED' else 'Strength']
    colour = node.inputs['Emission Color' if node.type == 'BSDF_PRINCIPLED' else 'Color']
    return (strength.is_linked or strength.default_value > 0) and (colour.is_linked or max(colour.default_value[:3]) > 0)


def lens_patches(mesh, slots):
    """Separate disconnected station lenses instead of lighting their centroid."""
    if not slots:
        return
    faces = [p for p in mesh.polygons if p.material_index in slots]
    groups, vertex_groups = {}, {}
    for face in faces:
        keys = [tuple(round(v, 4) for v in mesh.vertices[i].co) for i in face.vertices]
        neighbours = {vertex_groups[k] for k in keys if k in vertex_groups}
        group = min(neighbours) if neighbours else face.index
        members = groups.setdefault(group, [])
        for other in neighbours - {group}:
            members.extend(groups.pop(other))
            for k, value in list(vertex_groups.items()):
                if value == other:
                    vertex_groups[k] = group
        members.append(face)
        for k in keys:
            vertex_groups[k] = group
    total = sum(p.area for p in faces)
    for patch in groups.values():
        area = sum(p.area for p in patch)
        if area > max(1e-9, total * .01):
            yield sum((p.center*p.area for p in patch), Vector()) / area, area


def budget_lights(candidates, budget):
    """Keep each lamp family's energy when reducing preview source count.

    Small white accents retain their placement. Share the remaining slots
    between coloured fixtures and power parts, then combine nearby sources
    within each family instead of discarding their light.
    """
    groups = {priority: [c for c in candidates if c[7] == priority]
              for priority in (4, 3, 2, 1, 0)}
    quotas = {p: 0 for p in groups}
    quotas[3] = min(len(groups[3]), budget // 2)
    primary = [p for p in (4, 3, 2, 1) if groups[p]]
    while sum(quotas.values()) < budget:
        eligible = [p for p in primary if quotas[p] < len(groups[p])]
        if not eligible:
            eligible = [0] if quotas[0] < len(groups[0]) else []
        if not eligible:
            break
        p = max(eligible, key=lambda p: math.sqrt(len(groups[p])) / (quotas[p] + 1))
        quotas[p] += 1

    selected = []
    for priority, sources in groups.items():
        slots = quotas[priority]
        if not slots:
            continue
        # Farthest-point anchors retain coverage of the whole assembly.
        remaining = sorted(sources, key=lambda c: c[3], reverse=True)
        anchors = [remaining.pop(0)]
        def distance(a, b):
            spatial = (a[4] - b[4]).length_squared
            colour = sum((a[2][j] - b[2][j])**2 for j in range(3))
            return spatial + colour * min(a[6], b[6])**2
        while remaining and len(anchors) < slots:
            index = max(range(len(remaining)), key=lambda i:
                        min(distance(remaining[i], a) for a in anchors))
            anchors.append(remaining.pop(index))
        clusters = [[a] for a in anchors]
        for c in remaining:
            index = min(range(len(anchors)), key=lambda i: distance(c, anchors[i]))
            clusters[index].append(c)
        for members in clusters:
            a = members[0]
            if len(members) == 1:
                selected.append(a)
                continue
            watts = sum(c[3] for c in members)
            point = sum((c[4] * c[3] for c in members), Vector()) / watts
            colour = tuple(sum(c[2][j] * c[3] for c in members) / watts for j in range(3))
            reach = max(c[6] + (c[4] - point).length for c in members)
            local = a[0].matrix_world.inverted_safe() @ point
            selected.append((a[0], local, colour, watts, point, None, reach, priority))
    return selected


def build(scene, progress=None):
    # These display IDs can be replaced by the idle timer between undo steps.
    # Incremental restore may reuse stale graph IDs after that replacement.
    from . import undo_guard
    undo_guard.track_generated_preview()
    clear(scene)
    # World transforms must be evaluated before sizing lights after file load.
    bpy.context.view_layer.update()
    settings = scene.bbe_stage
    root = hd_library.scenes_root()
    if not settings.ship_lights or root is None:
        return
    profiles, effect_lights = effect_data(root)
    copies, candidates = {}, []
    objects = list(scene.objects)
    total = len(objects)
    for index, obj in enumerate(objects):
        if progress and index % 16 == 0:
            progress.batch(index, total, .16, .89, 'Preview parts')
        pid = obj.get('ObjectID', '').lstrip('^')
        if not pid or obj.type != 'MESH' or obj.hide_render or obj.hide_get():
            continue
        if getattr(scene, 'bbe_detailed_proxies', True):
            display_effect(obj, settings.collection)
        freighter = pid in freighter_profiles()
        profile = freighter_profiles()[pid] if freighter else profiles.get(pid, {})
        fire = pid == 'BLD_FIREPIT'
        fixture = pid.startswith('WALLLIGHT') or pid == 'CEILINGLIGHT'
        hull = pid.startswith('B_') and pid not in POWER_PARTS and pid not in effect_lights
        colour = COLOURS.get(pid) or profile.get('colour')
        colour = tuple(colour) if colour else None
        lit_slots = []
        pill_slots = []
        saved = {}
        for index, slot in enumerate(obj.material_slots):
            original = slot.material
            if not original or not original.node_tree:
                continue
            nodes = [n for n in original.node_tree.nodes if n.type == 'BSDF_PRINCIPLED']
            name = original.name.lower()
            station_pill = 'clasp_glow_mat' in name
            if station_pill:
                pill_slots.append(index)
            native_unlit = re.sub(r'\.\d{3}$', '', original.name) in profile.get('unlit', ())
            force = native_unlit or (pid.startswith('WALLLIGHT') and ('lightoff' in name or 'pulselight' in name))
            emits = force or any(emissive(n) for n in material_nodes(original.node_tree))
            water = pid == 'SET_FISHPOND' and 'fishpondwatermat' in name
            embedded = pid == 'S_CEMENTBAG' or water
            seep = (hull or embedded) and nodes and not emits and all(
                not n.inputs['Alpha'].is_linked and n.inputs['Alpha'].default_value >= 1
                and not n.inputs['Transmission Weight'].is_linked
                and n.inputs['Transmission Weight'].default_value == 0 for n in nodes)
            if not emits and not seep:
                continue
            if emits:
                lit_slots.append(index)
            if not nodes:
                continue  # Preserve authored emission/group/hologram shaders.
            # Leave the independent hologram shaders alone; they already emit.
            key = (original.as_pointer(), colour, fixture, pid in POWER_PARTS, force, bool(seep), embedded, freighter, fire)
            if key not in copies:
                mat = original.copy()
                mat.name = 'BBE Glow / ' + original.name
                mat[TAG] = True
                mat['bbe_stage_source'] = original
                for n in mat.node_tree.nodes:
                    if n.type != 'BSDF_PRINCIPLED' or not (force or emissive(n)):
                        continue
                    strength = n.inputs['Emission Strength']
                    power_glow = pid in POWER_PARTS and ('biggslight' in name or 'glowscroll' in name)
                    if not strength.is_linked:
                        # Decorative trim is not a lamp. Retain its authored
                        # intensity instead of making every hull seam neon.
                        strength.default_value = max(strength.default_value, 22 if power_glow else 5.8 if fixture else 4 if freighter or fire else 3.4 if station_pill else 1 if force else 0)
                    if force and not n.inputs['Emission Color'].is_linked and max(n.inputs['Emission Color'].default_value[:3]) == 0:
                        base = n.inputs['Base Color']
                        if base.is_linked:
                            mat.node_tree.links.new(base.links[0].from_socket, n.inputs['Emission Color'])
                        else:
                            n.inputs['Emission Color'].default_value = base.default_value
                    if colour and ((force and pid.startswith('WALLLIGHT')) or power_glow):
                        socket = n.inputs['Emission Color']
                        for link in list(socket.links):
                            mat.node_tree.links.remove(link)
                        socket.default_value = (*colour, 1)
                if pid == 'BUILDDOOR_WATER' and 'hologramdisplacement_mat' in name:
                    soften_door(mat)
                if seep:
                    hull_seep(mat, next(n for n in mat.node_tree.nodes if n.type == 'BSDF_PRINCIPLED'), embedded, water)
                copies[key] = mat
            saved[str(index)] = slot.link
            slot.link = 'OBJECT'
            slot.material = copies[key]
        if saved:
            obj[LINKS] = json.dumps(saved)
        # Area-weighted emitter center, in the unchanged part's local space.
        # Core and wall lamps use their known hue; other lamps use warm white.
        if not lit_slots and not colour:
            continue
        faces = [p for p in obj.data.polygons if p.material_index in lit_slots]
        area = sum(p.area for p in faces)
        center = sum((p.center * p.area for p in faces), Vector()) / area if area > 1e-9 else Vector()
        if pid.startswith('B_GEN_') and faces:
            # An average of opposite emitter faces lies inside the housing.
            # Place the spill just above the native Y-up luminous surfaces.
            points = [obj.data.vertices[i].co for face in faces for i in face.vertices]
            top = max(p.y for p in points)
            bottom = min(p.y for p in points)
            center.y = top + max(.08, (top-bottom)*.08)
        if pid.startswith('SET_CLASS_') or pid == 'U_BYTEBEATLINE':
            continue  # Holograms glow in the image; they are not floodlights.
        scale = max(abs(v) for v in obj.matrix_world.to_scale())
        if fire:
            point = Vector((.021924, 1.619476, -.026527))
            candidates.append((obj, point, (1,.32,.035), max(8, 95*scale**2), obj.matrix_world @ point, None, max(1.5, 5*scale), 4))
            continue
        if freighter:
            # Room lamps retain their floodlight output when the room is
            # miniaturised. Only their positions follow the part's scale.
            lamps = profile.get('native_lights', [])
            if lamps:
                for lamp in lamps:
                    point = Vector(lamp['position'])
                    candidates.append((obj, point, tuple(lamp['colour']), 30*lamp['intensity'], obj.matrix_world @ point,
                                       None, max(3, lamp['radius']), 4))
            elif faces:
                # Assembled room variants also contain luminous strips that
                # are absent from their placement-only native scene.
                patches = list(lens_patches(obj.data, set(lit_slots)))
                area_sum = sum(a for _, a in patches)
                watts = 360 if pid.startswith('FRE_ROOM') or pid == 'FREIGHTER_CORE' else 90
                for point, a in patches:
                    candidates.append((obj, point, colour or (1, .93, .82), watts*a/max(area_sum, 1e-9),
                                       obj.matrix_world @ point, None, 6, 4))
            continue
        for point, area in lens_patches(obj.data, pill_slots):
            watts = max(3, min(20, area * scale**2 * 180))
            candidates.append((obj, point, (1,1,1), watts, obj.matrix_world @ point, None, 1.5, 3))
        direction = None
        if fixture and faces:
            # The rear status LED used to drag the averaged source inside the
            # housing. Use the actual front lens, including miniature accents.
            lens_slots = {i for i in lit_slots if any(token in obj.material_slots[i].material.name.lower()
                          for token in ('lightoff', 'redlight', 'lights1_'))}
            lens = [p for p in faces if p.material_index in lens_slots] or faces
            lens_area = sum(p.area for p in lens)
            if lens_area > 1e-9:
                center = sum((p.center * p.area for p in lens), Vector()) / lens_area
                direction = sum((p.normal * p.area for p in lens), Vector())
                direction = direction.normalized() if direction.length > 1e-6 else Vector((0, 1, 0))
                center += direction * .035
            white = pid in {'WALLLIGHTWHITE', 'CEILINGLIGHT'}
            watts = max(7.0 if white else 1, (55 if white else 35) * scale**2)
            reach = max(1.15 if white else min(4, 2.5*scale), min(4.0, max(obj.dimensions)*2))
            # Embedded red/yellow stacks intentionally illuminate the hull in
            # NMS. Directional, shadowed lamps lose that surrounding orange.
            direction = None
            candidates.append((obj, center, colour or (1,1,1), watts, obj.matrix_world @ center, direction, reach, 3 if white else 1))
            continue
        if pid in effect_lights:
            for lamp in effect_lights[pid]:
                point = Vector(lamp['position'])
                candidates.append((obj, point, (.08, .3, 1.0), 4800 * scale**2, obj.matrix_world @ point, None, max(.5, 8*scale), 2))
            continue
        watts = 450 if pid.startswith('SWARM_TROPHY_') else 7200 if pid in POWER_PARTS else 4 if pid in COLOURS else 1
        candidates.append((obj, center, colour or (1,.82,.58), watts * scale**2, obj.matrix_world @ center, None,
                           max(.25, min(4, (10 if pid in POWER_PARTS else 2)*scale)), 2 if pid in POWER_PARTS else 0))
    if progress:
        progress.update(.89, 'Placing preview lights')
    # Collapse virtually coincident sources of the same colour, then spread a
    # bounded lamp budget over the assembly. Every visible emissive is retained.
    unique = {}
    for candidate in candidates:
        # Never merge distinct small fixtures across opposite sides of a panel.
        if candidate[7] == 4:
            # World-space quantisation merges separate lamps in tiny rooms.
            location_key = (candidate[0].name, tuple(round(v, 6) for v in candidate[1]))
        elif candidate[7] in {1, 3}:
            location_key = (candidate[0].name, tuple(round(v / .03) for v in candidate[4]))
        else:
            location_key = tuple(round(v / .15) for v in candidate[4])
        key = (location_key, candidate[2])
        if key not in unique or candidate[3] > unique[key][3]:
            unique[key] = candidate
    # Combine co-located coloured fixtures before budgeting. Keeping only one
    # member of a red/yellow stack changes its colour rather than its quality.
    clusters = []
    for c in unique.values():
        if c[7] != 1:
            clusters.append(c)
            continue
        match = next((i for i, a in enumerate(clusters) if a[7] == 1
                      and (a[4]-c[4]).length < .08), None)
        if match is None:
            clusters.append(c)
        else:
            a = clusters[match]
            total = a[3]+c[3]
            colour = tuple((a[2][j]*a[3]+c[2][j]*c[3])/total for j in range(3))
            clusters[match] = (a[0], a[1], colour, total, a[4], None, max(a[6],c[6]), 1)
    budget = 32 if settings.quality == 'EDIT' else 64
    selected = budget_lights(clusters, budget)
    shadows = 0
    for part, center, colour, watts, _, direction, reach, priority in selected:
        light = bpy.data.lights.new('BBE Part Glow', 'SPOT' if direction is not None else 'POINT')
        light.color = colour
        light.energy = watts * preview_value(scene, 'light_strength')
        light.shadow_soft_size = max(.01, min(.15, max(part.dimensions) * .04))
        light.use_shadow = direction is not None and shadows < (8 if settings.quality == 'EDIT' else 16)
        shadows += int(light.use_shadow)
        if direction is not None:
            light.spot_size = math.radians(165)
            light.spot_blend = .65
        light.use_custom_distance = True
        light.cutoff_distance = reach
        obj = bpy.data.objects.new('BBE Glow / '+part.name, light)
        obj[TAG] = obj['bbe_stage_owned'] = True
        settings.collection.objects.link(obj)
        obj.hide_select = True
        obj.parent = part
        obj.location = center
        if direction is not None:
            obj.rotation_euler = direction.to_track_quat('-Z', 'Y').to_euler()


def compositor(scene):
    """Use a separate node group and restore the user's group when disabled."""
    s = scene.bbe_stage
    if not hasattr(scene, 'compositing_node_group'):
        return  # Pre-5 Blender keeps its original scene compositor untouched.
    if not s.glow:
        scene.compositing_node_group = s.previous_compositor
        return
    tree = s.compositor
    if tree is None or any(o != scene and o.bbe_stage.compositor == tree for o in bpy.data.scenes):
        tree = bpy.data.node_groups.new('BBE Preview Glow', 'CompositorNodeTree')
        s.compositor = tree
        tree.interface.new_socket(name='Image', in_out='OUTPUT', socket_type='NodeSocketColor')
        source = tree.nodes.new('CompositorNodeRLayers')
        source.scene = scene
        glare = tree.nodes.new('CompositorNodeGlare')
        if 'Type' in glare.inputs:
            # Bloom uses a cheap image pyramid; Fog Glow's convolution dominated
            # viewport frame time on the FF scene even with ray tracing off.
            glare.inputs['Type'].default_value = 'Bloom'
            glare.inputs['Quality'].default_value = 'Medium'
            glare.inputs['Threshold'].default_value = 1.2
            glare.inputs['Strength'].default_value = .35
            glare.inputs['Size'].default_value = .25
        else:
            glare.glare_type = 'FOG_GLOW'
            glare.quality = 'MEDIUM'
            glare.threshold = 1.2
            glare.mix = -.65
        output = tree.nodes.new('NodeGroupOutput')
        tree.links.new(source.outputs['Image'], glare.inputs['Image'])
        tree.links.new(glare.outputs['Image'], output.inputs['Image'])
    # Saved scenes may still carry a previous preview's expensive Fog Glow node.
    for node in tree.nodes:
        if node.type == 'GLARE' and 'Type' in node.inputs:
            node.inputs['Type'].default_value = 'Bloom'
    scene.compositing_node_group = tree
    scene.render.use_compositing = True
