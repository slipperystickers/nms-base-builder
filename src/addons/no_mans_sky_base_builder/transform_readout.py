"""Move the native tool-header measurement below BBE's viewport controls."""
import bpy
import gpu
from bpy.app.handlers import persistent
from gpu_extras.presets import draw_texture_2d

_readouts = {}
_transform_ops = {'TRANSFORM_OT_rotate', 'TRANSFORM_OT_translate', 'TRANSFORM_OT_resize',
                  'TRANSFORM_OT_transform', 'TRANSFORM_OT_trackball'}


@persistent
def clear(*_):
    _readouts.clear()


def _texture(pixels):
    values = pixels.astype('float32') / 255
    data = gpu.types.Buffer('FLOAT', values.size, values.ravel())
    return gpu.types.GPUTexture((pixels.shape[1], pixels.shape[0]), format='RGBA8', data=data)


def header(context, key, relocate):
    """Return True only after capturing and erasing the native measurement."""
    area_key = key[:2]
    cached = _readouts.get(area_key)
    moved = False
    if not relocate or not any(op and op.bl_idname in _transform_ops for op in context.window.modal_operators):
        if _readouts.pop(area_key, None) is None:
            return False
    else:
        import numpy as np
        region = context.region
        vx, vy, vw, vh = gpu.state.viewport_get()
        width, height = min(region.width, vw), min(region.height, vh)
        if width < 3 or height < 3:
            return
        # Read only the short header row, while a transform owns it. Reuse the
        # exact snapped/typed text, signs, units and language from Blender.
        buffer = gpu.state.active_framebuffer_get().read_color(vx, vy, width, height, 4, 0, 'UBYTE')
        buffer.dimensions = width * height * 4
        pixels = np.frombuffer(buffer, dtype=np.uint8).reshape(height, width, 4)
        columns = np.flatnonzero(np.any(pixels != pixels[:, :1], axis=(0, 2)))
        if not columns.size:
            return
        pad = round(5 * context.preferences.system.ui_scale)
        start, end = max(0, columns[0] - pad), min(width, columns[-1] + pad + 1)
        crop = pixels[:, start:end].copy()
        signature = crop.tobytes()
        changed = cached is None or cached[1] != signature or cached[2].width != end-start or cached[2].height != height
        if changed:
            cached = _readouts[area_key] = key[2], signature, _texture(crop), _texture(pixels[:, :1])
        # Replace the original badge with the untouched margin of its own
        # framebuffer. Copy alpha as well for Blender's transparent headers.
        previous = gpu.state.blend_get()
        try:
            gpu.state.blend_set('NONE')
            draw_texture_2d(cached[3], (int(start), 0), int(end-start), height)
        finally:
            gpu.state.blend_set(previous)
        if not changed:
            return True
        moved = True

    for region in context.area.regions:
        if region.type == 'WINDOW':
            region.tag_redraw()
    return moved


def position(context, texture):
    from . import asset_strip
    region = context.region
    left, right, top = 0, region.width, region.height
    for other in context.area.regions:
        if other.width <= 1 or other.height <= 1:
            continue
        if other.type in {'TOOL_HEADER', 'HEADER'} and other.y > region.y + region.height / 2:
            top = min(top, other.y - region.y)
        elif other.type == 'UI' and context.space_data.show_region_ui:
            right = min(right, other.x - region.x)
        elif other.type == 'TOOLS' and context.space_data.show_region_toolbar:
            left = max(left, other.x + other.width - region.x)
    strip = asset_strip._states.get(asset_strip.key(context), {})
    if strip.get('enabled') and strip.get('bounds') and asset_strip.visible(context):
        x, y, w, _ = strip['bounds']
        left, right, top = max(left, x), min(right, x+w), min(top, y)
    pad = 4 * context.preferences.system.ui_scale
    width = min(texture.width, max(1, right-left-2*pad))
    height = texture.height * width / texture.width
    return (round(left+(right-left-width)/2), max(0, round(top-height-pad))), width, height


def draw():
    context = bpy.context
    cached = _readouts.get((context.window.as_pointer(), context.area.as_pointer()))
    if cached and context.space_data.show_region_tool_header and context.space_data.show_region_header:
        texture = cached[2]
        xy, width, height = position(context, texture)
        previous = gpu.state.blend_get()
        try:
            gpu.state.blend_set('ALPHA_PREMULT')
            draw_texture_2d(texture, xy, width, height)
        finally:
            gpu.state.blend_set(previous)
