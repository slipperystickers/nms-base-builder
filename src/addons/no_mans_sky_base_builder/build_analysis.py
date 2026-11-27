"""Transient asset-weight colours in the viewport that invoked Analyze Build."""
import bpy
import gpu
import numpy as np
from bpy.app.handlers import persistent
from gpu_extras.batch import batch_for_shader

from . import asset_weights, viewport_cutaway

_views = set()
_batches = {}
_targets = {}
_handler = None
_legend = None
_shader = None
_view_buffer = None


def key(context):
    return (context.window.as_pointer(), context.area.as_pointer(), context.scene.session_uid)


def active(context):
    return bool(_views and context.area and key(context) in _views)


def button(context):
    return "Exit Build Analysis" if active(context) else "Analyze Build"


def shader():
    global _shader
    if _shader is None:
        interface = gpu.types.GPUStageInterfaceInfo("bbe_weight_surface")
        interface.smooth("VEC3", "world")
        info = gpu.types.GPUShaderCreateInfo()
        info.vertex_in(0, "VEC3", "position")
        info.vertex_out(interface)
        info.fragment_out(0, "VEC4", "pixel")
        info.typedef_source("struct WeightView { mat4 projection; vec4 planes[6]; };")
        info.uniform_buf(0, "WeightView", "view")
        info.push_constant("MAT4", "model")
        info.push_constant("VEC4", "tint")
        info.vertex_source("""
            void main() {
                vec4 p = model * vec4(position, 1.0);
                world = p.xyz;
                gl_Position = view.projection * p;
            }
        """)
        info.fragment_source("""
            void main() {
                for (int i = 0; i < 6; ++i)
                    if (dot(vec4(world, 1.0), view.planes[i]) < 0.0) discard;
                if (tint.a == 0.0) { pixel = vec4(0.0); return; }
                vec3 n = cross(dFdx(world), dFdy(world));
                float shade = 0.82 + 0.18 * abs(dot(normalize(n), vec3(0.36, 0.48, 0.8)));
                vec3 linearTint = mix(tint.rgb / 12.92, pow((tint.rgb + 0.055) / 1.055, vec3(2.4)),
                                      step(vec3(0.04045), tint.rgb));
                pixel = vec4(linearTint * shade, 1.0);
            }
        """)
        _shader = gpu.shader.create_from_info(info)
    return _shader


def mesh_batch(mesh, program):
    mesh.calc_loop_triangles()
    result = None
    if mesh.loop_triangles:
        coords = np.empty(len(mesh.vertices) * 3, dtype=np.float32)
        tris = np.empty(len(mesh.loop_triangles) * 3, dtype=np.int32)
        mesh.vertices.foreach_get("co", coords)
        mesh.loop_triangles.foreach_get("vertices", tris)
        result = batch_for_shader(program, "TRIS", {"position": coords.reshape(-1, 3)},
                                  indices=tris.reshape(-1, 3))
    return result


def batch(obj, program):
    if obj.type == "MESH":
        key = ("mesh", obj.data.as_pointer())
        if key not in _batches:
            _batches[key] = mesh_batch(obj.data, program)
    else:
        key = ("curve", obj.as_pointer())
        if key not in _batches:
            mesh = obj.to_mesh()
            try:
                _batches[key] = mesh_batch(mesh, program) if mesh else None
            finally:
                obj.to_mesh_clear()
    return _batches[key]


def owner_id(obj):
    while obj is not None:
        if obj.get("bbe_pilot_reference") or obj.get("station_reference_only"):
            return None
        if obj.get("ObjectID"):
            return obj["ObjectID"]
        obj = obj.parent
    return None


def draw():
    global _view_buffer
    context = bpy.context
    if not active(context):
        return
    region = context.region_data
    cuts = viewport_cutaway.limits(context.scene)
    planes = (viewport_cutaway.equations(cuts) if cuts else region.clip_planes
              if region.use_clip_planes else ((0, 0, 0, 1),) * 6)
    values = np.concatenate((np.asarray(region.perspective_matrix).T.ravel(), np.ravel(planes))).astype("f")
    data = gpu.types.Buffer("FLOAT", len(values), values)
    if _view_buffer is None:
        _view_buffer = gpu.types.GPUUniformBuf(data)
    else:
        _view_buffer.update(data)
    program = shader()
    # Resolve the heatmap and its occluders together. Comparing a second drawing
    # of identical surfaces against Blender's jittered scene depth causes stipple.
    from mathutils import Matrix
    from gpu_extras.presets import draw_texture_2d
    viewport = gpu.state.viewport_get()
    scissor = gpu.state.scissor_get()
    size = viewport[2:]
    view = key(context)
    target = _targets.get(view)
    if target is None or (target.width, target.height) != size:
        target = _targets[view] = gpu.types.GPUOffScreen(*size, format='RGBA16F')
    depth, mask, blend = gpu.state.depth_test_get(), gpu.state.depth_mask_get(), gpu.state.blend_get()
    try:
        try:
            with target.bind():
                gpu.state.viewport_set(0, 0, *size)
                gpu.state.scissor_set(0, 0, *size)
                gpu.state.depth_mask_set(True)
                gpu.state.depth_test_set("LESS")
                gpu.state.blend_set("NONE")
                gpu.state.active_framebuffer_get().clear(color=(0,0,0,0), depth=1.0)
                program.bind()
                program.uniform_block("view", _view_buffer)
                for instance in context.evaluated_depsgraph_get().object_instances:
                    obj = instance.object
                    if (obj.type not in {"MESH", "CURVE", "SURFACE", "FONT"} or not instance.show_self
                            or obj.display_type in {"BOUNDS", "WIRE"}):
                        continue
                    owner = instance.parent if instance.is_instance else obj
                    if not owner or not owner.original.visible_get(view_layer=context.view_layer, viewport=context.space_data):
                        continue
                    part = owner_id(obj.original) or (owner_id(owner.original) if instance.is_instance else None)
                    geometry = batch(obj, program)
                    if geometry:
                        program.uniform_float("model", instance.matrix_world)
                        program.uniform_float("tint", asset_weights.rgba(part) if part else (0,0,0,0))
                        geometry.draw(program)
        finally:
            gpu.state.viewport_set(*viewport)
            gpu.state.scissor_set(*scissor)
        gpu.state.depth_mask_set(False)
        gpu.state.depth_test_set("NONE")
        gpu.state.blend_set("ALPHA")
        with gpu.matrix.push_pop(), gpu.matrix.push_pop_projection():
            gpu.matrix.load_identity()
            gpu.matrix.load_projection_matrix(Matrix.Identity(4))
            draw_texture_2d(target.texture_color, (-1,-1), 2, 2, is_scene_linear_with_rec709_srgb_target=True)
    finally:
        gpu.state.blend_set(blend)
        gpu.state.depth_mask_set(mask)
        gpu.state.depth_test_set(depth)


def draw_legend():
    context = bpy.context
    if not active(context):
        return
    from . import curve_widgets as ui, i18n
    scale = context.preferences.system.ui_scale
    width = 244 * scale
    if context.region.width < width:
        return
    x = (context.region.width-width)/2
    y = 47 * scale
    with ui.canvas(context):
        ui.rounded(None, x, y, width, 44*scale, 6*scale, (.10, .10, .13, .95))
        ui.text(i18n.interface(asset_weights.TITLE), x+9*scale, y+27*scale, 11*scale, (.95, .95, .95, 1))
        for index, (minimum, _, colour) in enumerate((*asset_weights.BANDS, asset_weights.UNKNOWN)):
            left = x+(9+33*index)*scale
            ui.rounded(None, left, y+10*scale, 9*scale, 4*scale, 0, asset_weights.hex_rgba(colour))
            ui.text(str(minimum) if minimum is not None else "?", left+11*scale, y+8*scale,
                    9*scale, (.95, .95, .95, 1))


@persistent
def clear(*_):
    global _handler, _legend, _shader, _view_buffer
    if _handler is not None:
        bpy.types.SpaceView3D.draw_handler_remove(_handler, "WINDOW")
    if _legend is not None:
        bpy.types.SpaceView3D.draw_handler_remove(_legend, "WINDOW")
    _views.clear()
    _batches.clear()
    _targets.clear()
    _handler = _legend = _shader = _view_buffer = None


@persistent
def invalidate(scene, depsgraph):
    if _views and any(update.is_updated_geometry for update in depsgraph.updates):
        _batches.clear()


class BBE_OT_analyze_build(bpy.types.Operator):
    bl_idname = "bbe.analyze_build"
    bl_label = "Analyze Build"
    bl_description = "Colour visible build parts by asset footprint and effects. Click again to return to normal."

    @classmethod
    def poll(cls, context):
        return context.area and context.area.type == "VIEW_3D"

    def execute(self, context):
        global _handler, _legend
        view = key(context)
        if view in _views:
            _views.remove(view)
            _targets.pop(view, None)
            if not _views:
                clear()
        else:
            if _handler is None:
                _handler = bpy.types.SpaceView3D.draw_handler_add(draw, (), "WINDOW", "POST_VIEW")
                _legend = bpy.types.SpaceView3D.draw_handler_add(draw_legend, (), "WINDOW", "POST_PIXEL")
            _views.add(view)
            self.report({"INFO"}, "Estimated weight ranges from pale green to burgundy. Grey means unmeasured.")
        context.area.tag_redraw()
        return {"FINISHED"}


def register():
    from .tools.asset_browser_presentation import BBE_OT_asset_weight_info
    bpy.utils.register_class(BBE_OT_asset_weight_info)
    bpy.utils.register_class(BBE_OT_analyze_build)
    bpy.app.handlers.load_pre.append(clear)
    bpy.app.handlers.undo_pre.append(clear)
    bpy.app.handlers.depsgraph_update_post.append(invalidate)


def unregister():
    clear()
    bpy.app.handlers.load_pre.remove(clear)
    bpy.app.handlers.undo_pre.remove(clear)
    bpy.app.handlers.depsgraph_update_post.remove(invalidate)
    from .tools.asset_browser_presentation import BBE_OT_asset_weight_info, release_weight_icons
    release_weight_icons()
    bpy.utils.unregister_class(BBE_OT_analyze_build)
    bpy.utils.unregister_class(BBE_OT_asset_weight_info)
