"""View-dependent Dock 5 cutaway. Each view uses its own eye position in the shader."""
def configure(mesh):
    # The clear volume over the pad, in native dock coordinates. A wall
    # disappears only when the eye and that wall cross the same boundary.
    for material in mesh.materials:
        tree = material.node_tree
        if tree.nodes.get('Dock 5 cutaway'):
            continue
        new, link = tree.nodes.new, tree.links.new
        output = next(node for node in tree.nodes if node.type == 'OUTPUT_MATERIAL')
        surface = output.inputs['Surface']
        original = surface.links[0].from_socket

        def vector(op, a, b):
            node = new('ShaderNodeVectorMath')
            node.operation = op
            link(a, node.inputs[0])
            if isinstance(b, tuple):
                node.inputs[1].default_value = b
            else:
                link(b, node.inputs[1])
            return node.outputs['Vector']

        def berth_coordinates(position):
            centered = vector('SUBTRACT', position, (0, 0, 22))
            return vector('DIVIDE', centered, (33, 60, 21.4))

        eye = new('ShaderNodeVectorTransform')
        eye.vector_type, eye.convert_from, eye.convert_to = 'POINT', 'CAMERA', 'OBJECT'
        eye.inputs['Vector'].default_value = (0, 0, 0)
        position = new('ShaderNodeTexCoord').outputs['Object']
        camera = berth_coordinates(eye.outputs[0])
        point = berth_coordinates(position)
        high = vector('MINIMUM', camera, point)
        low = vector('MULTIPLY', vector('MAXIMUM', camera, point), (-1, -1, -1))
        sides = new('ShaderNodeSeparateXYZ')
        link(vector('MAXIMUM', high, low), sides.inputs[0])
        largest = sides.outputs['X']
        for component in ('Y', 'Z'):
            maximum = new('ShaderNodeMath')
            maximum.operation = 'MAXIMUM'
            link(largest, maximum.inputs[0])
            link(sides.outputs[component], maximum.inputs[1])
            largest = maximum.outputs[0]
        outside = new('ShaderNodeMath')
        outside.operation = 'GREATER_THAN'
        link(largest, outside.inputs[0])
        outside.inputs[1].default_value = 1
        # Ribs project into the clear volume, so a wall-plane test alone leaves
        # them hanging in front of the ship. Look along each pixel's viewing
        # ray in berth coordinates. This also works for parallel ortho rays.
        incoming = new('ShaderNodeVectorTransform')
        incoming.vector_type, incoming.convert_from, incoming.convert_to = 'VECTOR', 'WORLD', 'OBJECT'
        link(new('ShaderNodeNewGeometry').outputs['Incoming'], incoming.inputs['Vector'])
        scaled = vector('DIVIDE', incoming.outputs[0], (33, 60, 21.4))
        direction = new('ShaderNodeVectorMath')
        direction.operation = 'NORMALIZE'
        link(scaled, direction.inputs[0])
        ray = direction.outputs['Vector']

        def scalar(op, a, b):
            node = new('ShaderNodeMath')
            node.operation = op
            link(a, node.inputs[0])
            if isinstance(b, (float, int)):
                node.inputs[1].default_value = b
            else:
                link(b, node.inputs[1])
            return node.outputs[0]

        # The point must be on the eye side of the berth and the continued
        # ray must pass through it. The landing surface stays under the ship.
        dot = new('ShaderNodeVectorMath')
        dot.operation = 'DOT_PRODUCT'
        link(point, dot.inputs[0])
        link(ray, dot.inputs[1])
        front = scalar('GREATER_THAN', dot.outputs['Value'], 0)
        offset = vector('CROSS_PRODUCT', point, ray)
        distance = new('ShaderNodeVectorMath')
        distance.operation = 'LENGTH'
        link(offset, distance.inputs[0])
        in_sight = scalar('LESS_THAN', distance.outputs['Value'], 1.15)
        height = new('ShaderNodeSeparateXYZ')
        link(position, height.inputs[0])
        above_deck = scalar('GREATER_THAN', height.outputs['Z'], .6)
        obstruction = scalar('MULTIPLY', scalar('MULTIPLY', front, in_sight), above_deck)
        cut = scalar('MAXIMUM', outside.outputs[0], obstruction)
        mix = new('ShaderNodeMixShader')
        mix.name = 'Dock 5 cutaway'
        link(cut, mix.inputs[0])
        link(original, mix.inputs[1])
        link(new('ShaderNodeBsdfTransparent').outputs[0], mix.inputs[2])
        link(mix.outputs[0], surface)

