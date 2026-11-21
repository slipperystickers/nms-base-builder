"""Material Preview and Rendered cutaways. The scene supplies two shared shader uniforms."""
import bpy

LOW = '_bbe_cutaway_shader_min'
HIGH = '_bbe_cutaway_shader_max'
TAG = '_bbe_viewport_cutaway'
_group = None
_plain = None
_wrapped = {}
_copies = {}
_values = {}
_dirty = True


def mask_group():
    global _group
    if _group is not None:
        return _group
    group = bpy.data.node_groups.new('BBE · viewport cutaway', 'ShaderNodeTree')
    _group = group
    group[TAG] = 'shader'
    group.interface.new_socket(name='Original', in_out='INPUT', socket_type='NodeSocketShader')
    group.interface.new_socket(name='Surface', in_out='OUTPUT', socket_type='NodeSocketShader')
    group.interface.new_socket(name='Volume', in_out='OUTPUT', socket_type='NodeSocketShader')
    nodes, link = group.nodes, group.links.new
    source = nodes.new('NodeGroupInput')
    dest = nodes.new('NodeGroupOutput')
    position = nodes.new('ShaderNodeNewGeometry').outputs['Position']
    outside = []
    for prop in (LOW, HIGH):
        attr = nodes.new('ShaderNodeAttribute')
        attr.attribute_type = 'VIEW_LAYER'
        attr.attribute_name = prop
        delta = nodes.new('ShaderNodeVectorMath')
        delta.operation = 'SUBTRACT'
        a, b = (attr.outputs['Vector'], position) if prop == LOW else (position, attr.outputs['Vector'])
        link(a, delta.inputs[0])
        link(b, delta.inputs[1])
        outside.append(delta.outputs['Vector'])
    maximum = nodes.new('ShaderNodeVectorMath')
    maximum.operation = 'MAXIMUM'
    for i, value in enumerate(outside):
        link(value, maximum.inputs[i])
    # Any positive component lies beyond a cut.
    positive = nodes.new('ShaderNodeVectorMath')
    positive.operation = 'MAXIMUM'
    link(maximum.outputs[0], positive.inputs[0])
    distance = nodes.new('ShaderNodeVectorMath')
    distance.operation = 'DOT_PRODUCT'
    link(positive.outputs[0], distance.inputs[0])
    distance.inputs[1].default_value = (1, 1, 1)
    test = nodes.new('ShaderNodeMath')
    test.operation = 'GREATER_THAN'
    test.inputs[1].default_value = 0.0
    link(distance.outputs['Value'], test.inputs[0])
    enabled = nodes.new('ShaderNodeMath')
    enabled.operation = 'MULTIPLY'
    link(test.outputs[0], enabled.inputs[0])
    link(attr.outputs['Alpha'], enabled.inputs[1])
    mix = nodes.new('ShaderNodeMixShader')
    link(enabled.outputs[0], mix.inputs[0])
    link(source.outputs['Original'], mix.inputs[1])
    link(nodes.new('ShaderNodeBsdfTransparent').outputs[0], mix.inputs[2])
    link(mix.outputs[0], dest.inputs[0])
    volume = nodes.new('ShaderNodeMixShader')
    link(enabled.outputs[0], volume.inputs[0])
    link(source.outputs['Original'], volume.inputs[1])
    link(volume.outputs[0], dest.inputs['Volume'])
    return group


def wrap(mat):
    if mat.session_uid in _wrapped:
        return
    tree = mat.node_tree
    if tree is None:
        return
    active = tree.nodes.active
    for node in tuple(tree.nodes):
        if node.type != 'OUTPUT_MATERIAL':
            continue
        for name in ('Surface', 'Volume'):
            socket = node.inputs[name]
            if not socket.is_linked:
                continue
            original = socket.links[0].from_socket
            if original.node.get(TAG) and original.node.node_tree == _group:
                continue
            wrapper = tree.nodes.new('ShaderNodeGroup')
            wrapper.node_tree = mask_group()
            wrapper[TAG] = True
            wrapper.label = 'Viewport cutaway'
            wrapper.hide = True
            wrapper.location = (node.location.x-80, node.location.y+90)
            wrapper.select = False
            tree.links.new(original, wrapper.inputs[0])
            tree.links.new(wrapper.outputs[name], socket)
    tree.nodes.active = active
    _wrapped[mat.session_uid] = mat


def plain():
    global _plain
    if _plain is None:
        _plain = bpy.data.materials.new('BBE · unassigned viewport surface')
        _plain[TAG] = 'plain'
        _plain.use_nodes = True
        wrap(_plain)
    return _plain


def prepare(scenes):
    """Cover new parts and collection instances without walking geometry on slider moves."""
    global _dirty
    if not _dirty:
        return
    _dirty = False
    seen = set()
    def visit(obj):
        if obj.session_uid in seen:
            return
        seen.add(obj.session_uid)
        if obj.instance_type == 'COLLECTION' and obj.instance_collection:
            for child in obj.instance_collection.all_objects:
                visit(child)
        if obj.type not in {'MESH', 'CURVE', 'SURFACE', 'FONT', 'META'}:
            return
        data = obj.data
        if not len(data.materials) and data.is_editable:
            data.materials.append(plain())
            data[TAG + '_added'] = True
        for idx, slot in enumerate(obj.material_slots):
            mat = slot.material
            if mat and mat.is_editable and mat.node_tree is not None:
                wrap(mat)
                continue
            if not obj.is_editable:
                continue
            if mat is None:
                display = plain()
            else:
                display = _copies.get(mat.session_uid)
                if display is None:
                    display = mat.copy()
                    display[TAG] = 'display'
                    display[TAG + '_original'] = mat
                    display.use_nodes = True
                    _copies[mat.session_uid] = display
                    wrap(display)
            if TAG + '_slots' not in obj:
                obj[TAG + '_slots'] = {}
            obj[TAG + '_slots'][str(idx)] = slot.link
            slot.link = 'OBJECT'
            slot.material = display
    for scene in scenes:
        for obj in scene.objects:
            visit(obj)


def dirty():
    global _dirty
    _dirty = True


def set_bounds(scene, cuts):
    if _values.get(scene.session_uid) == cuts:
        return
    if cuts is None:
        for key in (LOW, HIGH):
            if key in scene:
                del scene[key]
        _values.pop(scene.session_uid, None)
    else:
        scene[LOW] = [v if v is not None else -1.e30 for v in cuts[::2]] + [1.]
        scene[HIGH] = [v if v is not None else 1.e30 for v in cuts[1::2]] + [1.]
        _values[scene.session_uid] = cuts
    scene.update_tag(refresh={'TIME'})


def unwrap(tree, group):
    for node in tuple(tree.nodes):
        if node.type != 'GROUP' or not node.get(TAG) or node.node_tree != group:
            continue
        source = node.inputs[0].links
        if source:
            original = source[0].from_socket
            for output in node.outputs:
                for edge in tuple(output.links):
                    tree.links.new(original, edge.to_socket)
        tree.nodes.remove(node)


def recover():
    """Unwind preview copies resurrected by undo or loaded from an autosave."""
    groups = [g for g in bpy.data.node_groups if g.get(TAG) == 'shader' and g.is_editable]
    temporary = [m for m in bpy.data.materials if m.get(TAG) in {'plain','display'} and m.is_editable]
    if not groups and not temporary:
        return
    for mat in bpy.data.materials:
        if mat.is_editable and mat.node_tree:
            for group in groups:
                unwrap(mat.node_tree, group)
    authored_slots = set()
    for obj in bpy.data.objects:
        if not obj.is_editable:
            continue
        records = obj.get(TAG + '_slots')
        if records is not None:
            for key, link_type in records.items():
                idx = int(key)
                if idx < len(obj.material_slots):
                    slot = obj.material_slots[idx]
                    if slot.material in temporary:
                        slot.material = slot.material.get(TAG + '_original')
                        slot.link = link_type
            del obj[TAG + '_slots']
        # Respect material assignments made by the user while a formerly empty
        # mesh had a temporary first slot.
        if obj.data and obj.data.get(TAG + '_added') and len(obj.material_slots):
            slot = obj.material_slots[0]
            if slot.link == 'OBJECT' and slot.material and slot.material not in temporary:
                authored_slots.add(obj.data.session_uid)
    for collection in (bpy.data.meshes, bpy.data.curves, bpy.data.metaballs):
        for data in collection:
            if not data.is_editable or not data.get(TAG + '_added'):
                continue
            if len(data.materials) and data.materials[0] in temporary:
                if data.session_uid in authored_slots:
                    data.materials[0] = None
                elif len(data.materials) == 1:
                    data.materials.clear()
                else:
                    data.materials.pop(index=0)
            del data[TAG + '_added']
    for mat in temporary:
        if not mat.users:
            bpy.data.materials.remove(mat)
    for group in groups:
        if not group.users:
            bpy.data.node_groups.remove(group)
    for scene in bpy.data.scenes:
        for key in (LOW, HIGH):
            if key in scene:
                del scene[key]


def clear():
    global _group, _plain
    for scene in bpy.data.scenes:
        if scene.session_uid in _values:
            set_bounds(scene, None)
    if _group is not None or _plain is not None or _copies:
        recover()
    _wrapped.clear()
    _copies.clear()
    _plain = None
    _group = None
    _values.clear()
    dirty()
