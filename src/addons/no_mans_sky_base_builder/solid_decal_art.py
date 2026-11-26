"""Draw projected decal artwork over Workbench's per-object hull paint."""
import bpy
import gpu
import numpy as np
from gpu_extras.batch import batch_for_shader


_alpha = 'bbe_solid_art_original_alpha'
_scenes = {}
_batches = {}
_shader = None
_view_buffer = None
_handler = None


def artwork(mat):
    if not mat or not mat.node_tree:
        return None
    nodes = mat.node_tree.nodes
    node = nodes.get('Diffuse')
    if not node or node.type != 'TEX_IMAGE' or not node.image:
        node = next((n for n in nodes if n.type == 'TEX_IMAGE' and n.image), None)
    return node.image if node else None


def restore(obj):
    if _alpha in obj:
        if obj.color[3] == 0:
            obj.color[3] = obj[_alpha]
        del obj[_alpha]


def sync(scenes):
    """Keep only the drawn decal surfaces transparent in native Object color."""
    _scenes.clear()
    active = set()
    for scene, objects in scenes.items():
        draw = []
        for obj in objects:
            if not obj.data.uv_layers.active or not any(artwork(s.material) for s in obj.material_slots):
                continue
            active.add(obj.session_uid)
            draw.append(obj)
            if _alpha not in obj or obj.color[3] != 0:
                obj[_alpha] = obj.color[3]
                obj.color[3] = 0
        _scenes[scene.session_uid] = draw
    for obj in bpy.data.objects:
        if obj.session_uid not in active and _alpha in obj:
            restore(obj)
    live = {obj.data.session_uid for group in _scenes.values() for obj in group}
    for key in _batches.keys() - live:
        del _batches[key]


def invalidate(mesh):
    _batches.pop(mesh.session_uid, None)


def shader():
    global _shader
    if _shader is None:
        iface = gpu.types.GPUStageInterfaceInfo('bbe_solid_decal_uv')
        iface.smooth('VEC2', 'uv')
        iface.smooth('VEC3', 'world')
        info = gpu.types.GPUShaderCreateInfo()
        info.vertex_in(0, 'VEC3', 'position')
        info.vertex_in(1, 'VEC2', 'texCoord')
        info.vertex_out(iface)
        info.fragment_out(0, 'VEC4', 'pixel')
        info.typedef_source('struct DecalView { mat4 projection; vec4 planes[6]; };')
        info.uniform_buf(0, 'DecalView', 'view')
        info.push_constant('MAT4', 'model')
        info.sampler(0, 'FLOAT_2D', 'art')
        info.vertex_source("""
            void main() {
                vec4 p = model * vec4(position, 1.0);
                world = p.xyz;
                uv = texCoord;
                gl_Position = view.projection * p;
            }
        """)
        info.fragment_source("""
            void main() {
                for (int i = 0; i < 6; ++i)
                    if (dot(vec4(world, 1.0), view.planes[i]) < 0.0) discard;
                vec4 texel = texture(art, uv);
                if (texel.a < 0.1) discard;
                pixel = texel;
            }
        """)
        _shader = gpu.shader.create_from_info(info)
    return _shader


def batches(mesh, program):
    if mesh.session_uid in _batches:
        return _batches[mesh.session_uid]
    mesh.calc_loop_triangles()
    result = []
    if mesh.loop_triangles and mesh.uv_layers.active:
        def read(items, field, width, dtype):
            values = np.empty(len(items) * width, dtype=dtype)
            items.foreach_get(field, values)
            return values.reshape(-1, width)
        coords = read(mesh.vertices, 'co', 3, np.float32)
        vertices = read(mesh.loops, 'vertex_index', 1, np.int32).ravel()
        uvs = read(mesh.uv_layers.active.data, 'uv', 2, np.float32)
        tris = read(mesh.loop_triangles, 'loops', 3, np.int32)
        slots = read(mesh.loop_triangles, 'material_index', 1, np.int32).ravel()
        for slot in np.unique(slots):
            loops = tris[slots == slot].ravel()
            result.append((int(slot), batch_for_shader(program, 'TRIS', {
                'position': coords[vertices[loops]], 'texCoord': uvs[loops]})))
    _batches[mesh.session_uid] = result
    return result


def draw():
    global _view_buffer
    context = bpy.context
    space = context.space_data
    if space.shading.type != 'SOLID' or space.shading.color_type != 'OBJECT':
        return
    objects = _scenes.get(context.scene.session_uid)
    if not objects or not context.scene.bbe_solid_decals:
        return
    program = shader()
    program.bind()
    rv = context.region_data
    planes = rv.clip_planes if rv.use_clip_planes else ((0., 0., 0., 1.),) * 6
    values = np.concatenate((np.asarray(rv.perspective_matrix).T.ravel(), np.ravel(planes))).astype('f')
    data = gpu.types.Buffer('FLOAT', len(values), values)
    if _view_buffer is None:
        _view_buffer = gpu.types.GPUUniformBuf(data)
    else:
        _view_buffer.update(data)
    program.uniform_block('view', _view_buffer)
    depth, blend, mask = gpu.state.depth_test_get(), gpu.state.blend_get(), gpu.state.depth_mask_get()
    try:
        gpu.state.depth_test_set('LESS_EQUAL')
        gpu.state.depth_mask_set(False)
        gpu.state.blend_set('ALPHA')
        for obj in objects:
            try:
                if not obj.visible_get(view_layer=context.view_layer, viewport=space):
                    continue
                mesh = obj.data
            except ReferenceError:  # Deleted between reconciliation and this redraw.
                continue
            program.uniform_float('model', obj.matrix_world)
            for slot, batch in batches(mesh, program):
                if slot < len(obj.material_slots):
                    image = artwork(obj.material_slots[slot].material)
                    if image:
                        program.uniform_sampler('art', gpu.texture.from_image(image))
                        batch.draw(program)
    finally:
        gpu.state.blend_set(blend)
        gpu.state.depth_mask_set(mask)
        gpu.state.depth_test_set(depth)


def reset():
    _scenes.clear()
    _batches.clear()


def register():
    global _handler
    _handler = bpy.types.SpaceView3D.draw_handler_add(draw, (), 'WINDOW', 'POST_VIEW')


def unregister():
    global _handler, _shader, _view_buffer
    bpy.types.SpaceView3D.draw_handler_remove(_handler, 'WINDOW')
    _handler = _shader = _view_buffer = None
    reset()
