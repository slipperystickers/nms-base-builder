"""Per-browser variant thumbnails and return position."""
import bpy
from . import i18n


def family_parts(part, info):
    from .utils import dictionary
    names = dictionary.get_nice_names_diictionary()
    return {member: dict(info if member == part else {}, name=names.get(member, member), variants=())
            for member in dict.fromkeys((part, *info['variants']))}


def variant_label(root, name):
    if name.casefold().startswith(root.casefold()):
        suffix = name[len(root):].strip()
        if suffix.startswith('(') and suffix.endswith(')'):
            label = suffix[1:-1].strip()
            if label:
                return label.capitalize() if label.isupper() else label
    return name


def location(scene):
    browser = scene.nms_asset_browser
    return (scene.as_pointer(), browser.asset_browser_caterogies, browser.asset_browser_sub_caterogies,
            browser.enum_asset_browser_what_to_display, browser.asset_broser_search_query)


def open_family(surface, part, info):
    if not info.get('variants'):
        return
    parts = family_parts(part, info)
    label = i18n.part_names().get(part) or info.get('name') or part
    names = i18n.part_names()
    for member, entry in parts.items():
        name = names.get(member) or entry['name']
        entry['variant_label'] = i18n.interface('Default') if member == part else variant_label(label, name)
    surface._family = (location(surface._window.scene), {label + ' · ' + i18n.interface('Variants'): parts})
    surface._close_bounds = None
    surface._close_pressed = False
    surface._close_hover = False
    surface._family_offset = surface._offset
    surface._offset = 0
    surface._signature = None
    surface._hover = None
    surface._area.tag_redraw()


def close_family(surface):
    surface._family = None
    surface._signature = None
    surface._area.tag_redraw()


def update_groups(surface, get_groups):
    scene = surface._window.scene
    family = surface._family
    if family and family[0] == location(scene):
        return family[1]
    groups = get_groups(scene)
    if family:
        # A different category or search has its own initial position.
        surface._family = None
        surface._family_offset = None
    if surface._family_offset is not None:
        surface._offset = surface._family_offset
        surface._family_offset = None
    elif tuple(groups) != tuple(surface._groups):
        surface._offset = 0
    return groups


def current(context):
    from .tools import asset_browser_grid, asset_browser_sidebar
    if not context.area:
        return None
    sessions = asset_browser_grid._sessions if context.area.type == 'INFO' else asset_browser_sidebar._sessions
    return sessions.get(context.area.as_pointer())


ARROW_GUTTER = 48


def _luminance(color):
    def linear(channel):
        return channel / 12.92 if channel <= 0.04045 else ((channel + 0.055) / 1.055) ** 2.4
    return sum(weight * linear(channel) for weight, channel in zip((0.2126, 0.7152, 0.0722), color))


def _arrow_ink(palette, hovered):
    background = _luminance(palette['hover' if hovered else 'background'])
    for color in (palette['selected_text' if hovered else 'text'], palette['accent']):
        foreground = _luminance(color)
        if max(foreground, background) + 0.05 >= 3 * (min(foreground, background) + 0.05):
            return color
    # A custom theme can give text and panel nearly identical colors.
    return (0, 0, 0, 1) if background > 0.179 else (1, 1, 1, 1)


def draw_back_arrow(surface, top, scale):
    """Keep the return arrow in the gutter beside the first row of variants."""
    if not surface._family or not surface._tiles:
        return
    from . import curve_widgets as paint
    tile_x, tile_top, _, tile_h = surface._tiles[0][:4]
    size = 42 * scale
    cx = tile_x - size / 2 - 5 * scale
    cy = top - tile_top - tile_h / 2
    surface._close_bounds = (cx - size / 2, cy - size / 2, size, size)
    palette = surface._palette
    hovered = getattr(surface, '_close_hover', False)
    if hovered:
        paint.rounded(surface._rect_shader, *surface._close_bounds, 8 * scale, palette['hover'])
    ink = _arrow_ink(palette, hovered)
    # The shaft meets the solid triangular head inside its base.
    head = ((cx - 16*scale, cy), (cx - scale, cy - 13*scale), (cx - scale, cy + 13*scale))
    paint.polygon(surface._rect_shader, head, ink)
    surface.rectangle(cx - 2*scale, cy - 3*scale, 17*scale, 6*scale, ink)


def close_event(surface, event, x, y):
    bounds = getattr(surface, '_close_bounds', None)
    if not surface._family or bounds is None:
        return False
    left, bottom, width, height = bounds
    inside = left <= x < left + width and bottom <= y < bottom + height
    if event.type == 'LEFTMOUSE':
        if event.value == 'PRESS' and inside:
            surface._close_pressed = True
            surface._pressed = None
            return True
        if event.value == 'RELEASE' and getattr(surface, '_close_pressed', False):
            surface._close_pressed = False
            if inside:
                close_family(surface)
            return True
    if event.type == 'MOUSEMOVE' and inside != getattr(surface, '_close_hover', False):
        surface._close_hover = inside
        surface._area.tag_redraw()
    if inside and event.type in {'MOUSEMOVE', 'LEFTMOUSE', 'RIGHTMOUSE'}:
        surface._pressed = None
        if surface._hover:
            surface._hover = None
            surface._area.tag_redraw()
        return True
    return False


class BBE_OT_asset_family(bpy.types.Operator):
    bl_idname = 'bbe.asset_family'
    bl_label = 'Browse Part Variants'
    part: bpy.props.StringProperty()
    horizontal: bpy.props.BoolProperty(options={'HIDDEN', 'SKIP_SAVE'})

    def execute(self, context):
        if self.horizontal:
            from . import asset_strip
            state = asset_strip._states.get(asset_strip.key(context))
            card = next((info for part, info, _ in state['cards'] if part == self.part), None) if state else None
            if not card or not card.get('variants'):
                return {'CANCELLED'}
            asset_strip.open_variants(state, self.part, card)
            context.area.tag_redraw()
            return {'FINISHED'}
        surface = current(context)
        if surface is None:
            return {'CANCELLED'}
        if self.part:
            tile = next((tile for tile in surface._tiles if tile[4] == self.part), None)
            if tile is None:
                return {'CANCELLED'}
            open_family(surface, self.part, tile[5])
        else:
            close_family(surface)
        return {'FINISHED'}
