"""Interactive thumbnail surface for the dedicated Asset Browser window.

Uses the existing category/search/favourite data and placement operators. The
window's left-hand native controls are unchanged. Geometry supplies both drawing
and hit testing, so image clicks do not depend on undocumented UI button sizes.
"""
import json
import math
from collections import OrderedDict
from array import array

import bpy
import blf
import gpu
from bpy.app.handlers import persistent
from gpu_extras.batch import batch_for_shader
from .. import icons
from ..utils import new_assets
from ..utils.asset_browser_utils import get_grid_settings, resolve_sub_categories

_sessions = {}
_resources = {}
_pending_windows = set()
_enabled = False
_loading_handler = None


def draw_auto_snap(surface, right, top, scale):
    from ..utils.asset_browser_utils import auto_snap_enabled
    from .. import curve_widgets as widgets
    enabled=auto_snap_enabled()
    width,height=154*scale,29*scale
    x,y=max(4*scale,right-width),top-height
    surface._auto_snap_bounds=(x,y,width,height)
    hovered=getattr(surface,'_snap_hover',False)
    shader=surface._rect_shader
    widgets.rounded(shader,x,y,width,height,6*scale,(.48,.54,.59,1) if hovered else (.29,.33,.37,1))
    widgets.rounded(shader,x+scale,y+scale,width-2*scale,height-2*scale,5*scale,
                    (.19,.22,.25,1) if hovered else (.10,.12,.14,1))
    surface.label(x+10*scale,y+9*scale,'Auto-Snap',86*scale,12,(.9,.93,.96,1))
    track_x,track_y=x+106*scale,y+5*scale
    widgets.rounded(shader,track_x,track_y,40*scale,19*scale,9.5*scale,
                    (.18,.72,.38,1) if enabled else (.36,.40,.44,1))
    knob_x=track_x+(30.5 if enabled else 9.5)*scale
    widgets.disc(shader,knob_x,track_y+8.5*scale,7.5*scale,(.08,.12,.13,.45))
    widgets.disc(shader,knob_x,track_y+9.5*scale,7.5*scale,(.96,.98,1,1))


def auto_snap_event(surface, event, x, y):
    """The fixed overlay owns its click, never the scrolling tile below it."""
    bounds=getattr(surface,'_auto_snap_bounds',None)
    inside=bounds is not None and _contains(bounds,x,y)
    if event.type=='MOUSEMOVE' and inside!=getattr(surface,'_snap_hover',False):
        surface._snap_hover=inside;surface._area.tag_redraw()
    if event.type=='LEFTMOUSE':
        if event.value=='PRESS' and inside:
            surface._snap_pressed=True;surface._pressed=None;return True
        if event.value=='RELEASE' and getattr(surface,'_snap_pressed',False):
            surface._snap_pressed=False
            if inside:
                from ..utils.asset_browser_utils import toggle_auto_snap
                if not toggle_auto_snap():surface.report({'WARNING'},'Could not save the Auto-Snap setting.')
            return True
    if inside and event.type in {'MOUSEMOVE','RIGHTMOUSE'}:
        surface._hover=None;surface._area.tag_redraw();return True
    return False


def browser_palette(context):
    """Read live theme colors so open browser windows follow preset changes."""
    ui = context.preferences.themes[0].user_interface
    def opaque(value):
        return (*value[:3], 1)
    return {
        'background': opaque(ui.wcol_box.inner),
        'card': opaque(ui.wcol_regular.inner),
        'hover': opaque(ui.wcol_regular.inner_sel),
        'text': opaque(ui.wcol_regular.text),
        'selected_text': opaque(ui.wcol_regular.text_sel),
        'footer': opaque(ui.panel_header),
        'accent': opaque(ui.wcol_regular.inner_sel),
    }


def _draw_loading():
    """Cover only our saved browser surface while its grid is being restored."""
    context=bpy.context
    if (not context.window or not context.area or context.area.as_pointer() in _sessions
            or _saved_browser_target(context.window) != context.area):
        return
    region=context.region
    shader=gpu.shader.from_builtin('UNIFORM_COLOR')
    shader.bind()
    palette = browser_palette(context)
    shader.uniform_float('color', palette['background'])
    batch_for_shader(shader,'TRI_FAN',{'pos':((0,0),(region.width,0),
        (region.width,region.height),(0,region.height))}).draw(shader)
    blf.size(0,16*context.preferences.system.ui_scale)
    blf.color(0, *palette['text'])
    blf.position(0,24,region.height-42,0)
    blf.draw(0,'Loading assets…')


def _restore_soon():
    if not _enabled or bpy.app.background:
        return None
    try:
        _restore_saved_windows(bpy.context.window_manager)
        pending=any((area:=_saved_browser_target(window)) is not None
                    and area.as_pointer() not in _sessions
                    for window in bpy.context.window_manager.windows)
        return .05 if pending else None
    except (ReferenceError,RuntimeError,TypeError,AttributeError):
        return .05


@persistent
def _load_ready(_dummy=None):
    # Saved windows have no modal handlers until we restore them. Run on the
    # first UI tick rather than waiting for the one-second cleanup interval.
    if not bpy.app.background and not bpy.app.timers.is_registered(_restore_soon):
        bpy.app.timers.register(_restore_soon,first_interval=.01)


def mark_window_pending(window):
    _pending_windows.add(window.as_pointer())


def unmark_window_pending(window):
    try:
        _pending_windows.discard(window.as_pointer())
    except ReferenceError:
        pass


def release_stale_sessions(window_manager):
    """A just-closed pop-out may still own the pointer Blender reuses."""
    live = {(window.as_pointer(), area.as_pointer())
            for window in window_manager.windows for area in window.screen.areas
            if area.type == 'IMAGE_EDITOR'}
    for key, session in tuple(_sessions.items()):
        try:
            identity = (session._window.as_pointer(), session._area.as_pointer())
        except ReferenceError:
            identity = None
        if identity not in live:
            _release_session(key, window_manager)


def request_redraw():
    """Property callbacks request a frame immediately, without waiting for a timer."""
    for session in tuple(_sessions.values()):
        try:
            session._area.tag_redraw()
        except ReferenceError:
            pass  # The window cleanup timer owns disposal of closed sessions.


def _release_session(key, window_manager):
    # Blender invalidates an operator's RNA as soon as its window closes. Keep
    # cleanup handles outside that operator so closing the window is safe too.
    resources = _resources.pop(key, None)
    if resources:
        handler, timer, textures = resources
        bpy.types.SpaceImageEditor.draw_handler_remove(handler, 'WINDOW')
        try:
            window_manager.event_timer_remove(timer)
        except ReferenceError:
            pass  # The window may already have disposed of its event timer.
        textures.clear()
    _sessions.pop(key, None)


def _groups(scene):
    browser = scene.nms_asset_browser
    mode = browser.enum_asset_browser_what_to_display
    if mode == 'search':
        return browser.get_search_results()
    if mode == 'fav':
        return {'Favourite Objects': browser.get_favourite_objects_data()}
    if mode == 'recent':
        return {'Recent Objects': browser.get_recent_objects_data()}
    if mode == 'preset':
        return {'Presets': browser.get_preset_data()}
    return resolve_sub_categories(browser.get_categories_data(),
                                  browser.asset_browser_caterogies,
                                  browser.asset_browser_sub_caterogies)


def grid_geometry(groups, width, icon_size, columns, scale=1):
    """Return content-space rectangles; scroll is applied only at draw/hit time."""
    margin, gap = 10 * scale, 4 * scale
    columns = max(1, min(columns, int(max(width - margin * 2, 1) / (68 * scale))))
    tile_w = max(1, (width - margin * 2 - gap * (columns - 1)) / columns)
    image_h = max(32 * scale, min(icon_size * 20 * scale, tile_w - 8 * scale))
    tile_h = image_h + 48 * scale
    titles, tiles, top = [], [], margin
    for title, parts in groups.items():
        titles.append((margin, top, str(title)))
        top += 28 * scale
        for index, (object_id, data) in enumerate(parts.items()):
            x = margin + (index % columns) * (tile_w + gap)
            y = top + (index // columns) * (tile_h + gap)
            tiles.append((x, y, tile_w, tile_h, object_id, data))
        top += math.ceil(len(parts) / columns) * (tile_h + gap) + 10 * scale
    return titles, tiles, top


def _contains(rect, x, y):
    left, top, width, height = rect
    return left <= x < left + width and top <= y < top + height


def tile_action(tile, x, y, scale=1):
    left, top, width, height, _object_id, data = tile
    if not _contains((left, top, width, height), x, y):
        return None
    button = 24 * scale
    if not data.get('is_preset') and _contains((left, top, button, button), x, y):
        return 'options'
    if data.get('variants') and _contains((left + width - button, top, button, button), x, y):
        return 'variants'
    return 'place'


def bubble_notice(context, hover=None):
    from ..bubble_preview import ELBOW_HELP
    from ..utils.dictionary import PLACEMENT_HELP
    if hover and hover[0] == 'BASE_BUBPIPE_L':
        return ELBOW_HELP
    if hover and hover[0] in PLACEMENT_HELP:
        return (PLACEMENT_HELP[hover[0]],)
    return ()


class BBE_OT_asset_grid(bpy.types.Operator):
    bl_idname = 'bbe.asset_grid'
    bl_label = 'Asset Browser Grid'
    bl_options = {'INTERNAL'}

    def invoke(self, context, event):
        if context.area.type != 'IMAGE_EDITOR':
            return {'CANCELLED'}
        release_stale_sessions(context.window_manager)
        key = context.area.as_pointer()
        if key in _sessions:
            return {'CANCELLED'}
        if _saved_browser_target(context.window) == context.area:
            context.window.screen['bbe_asset_browser'] = True
        self._window, self._area, self._key = context.window, context.area, key
        self._offset, self._hover, self._drag = 0, None, False
        self._pressed = None
        self._signature, self._geometry_key = None, None
        self._textures = OrderedDict()
        self._groups, self._tiles, self._titles = {}, [], []
        self._total, self._max_offset, self._view_height = 0, 0, 1
        self._scale = 1
        self._rect_shader = gpu.shader.from_builtin('UNIFORM_COLOR')
        self._image_shader = gpu.shader.from_builtin('IMAGE')
        self._handler = bpy.types.SpaceImageEditor.draw_handler_add(
            self.draw_grid, (), 'WINDOW', 'POST_PIXEL')
        self._timer = context.window_manager.event_timer_add(.25, window=context.window)
        _sessions[key] = self
        _resources[key] = (self._handler, self._timer, self._textures)
        context.window_manager.modal_handler_add(self)
        self.refresh(context)
        return {'RUNNING_MODAL'}

    def refresh(self, context):
        scene = self._window.scene
        browser = scene.nms_asset_browser
        notice = bubble_notice(context, self._hover)
        if getattr(self, '_notice_signature', None) != notice:
            self._notice_signature = notice
            self._area.tag_redraw()
        size, columns = get_grid_settings(context, 'asset_browser_icon_size_other',
                                         'asset_browser_number_of_columns_other')
        # Contents change through the browser's mutation methods. A revision
        # avoids walking every part and variant on every Blender timer event.
        signature = (scene.as_pointer(), browser.view_revision, size, columns,
                     browser.enum_asset_browser_what_to_display,
                     browser.asset_browser_caterogies, browser.asset_browser_sub_caterogies)
        if signature != self._signature:
            groups = _groups(scene)
            # Reset scroll only when the visible group changes; adding a recent
            # item or toggling a favourite should not jump the category view.
            if tuple(groups) != tuple(self._groups):
                self._offset = 0
            self._signature, self._groups = signature, groups
            self._size, self._columns = size, columns
            self._geometry_key = None
            self._hover = None
            self._area.tag_redraw()

    def finish(self, context):
        _release_session(self._key, context.window_manager)

    def modal(self, context, event):
        if not _enabled or self._key not in _sessions:
            return {'CANCELLED'}
        try:
            if self._area.type != 'IMAGE_EDITOR' or self._area not in tuple(self._window.screen.areas):
                self.finish(context)
                return {'CANCELLED'}
            if event.type == 'TIMER':
                self.refresh(context)
                return {'PASS_THROUGH'}
            region = next(r for r in self._area.regions if r.type == 'WINDOW')
            x, y = event.mouse_x - region.x, region.height - (event.mouse_y - region.y)
            if auto_snap_event(self,event,x,region.height-y):return {'RUNNING_MODAL'}
            inside = 0 <= x < region.width and 0 <= y < self._view_height
            if not inside and not self._drag:
                if self._hover is not None:
                    self._hover = None
                    self._area.tag_redraw()
                return {'PASS_THROUGH'}
            if event.type in {'WHEELUPMOUSE', 'WHEELDOWNMOUSE'}:
                self._offset = max(0, min(self._max_offset, self._offset +
                                   (1 if event.type == 'WHEELDOWNMOUSE' else -1) * 100 * self._scale))
                self._area.tag_redraw()
                return {'RUNNING_MODAL'}
            if event.type == 'TRACKPADPAN':
                self._offset = max(0, min(self._max_offset, self._offset + event.mouse_prev_y - event.mouse_y))
                self._area.tag_redraw()
                return {'RUNNING_MODAL'}
            if event.type == 'LEFTMOUSE' and event.value == 'RELEASE' and self._drag:
                self._drag = False
                return {'RUNNING_MODAL'}
            if self._drag or (event.type == 'LEFTMOUSE' and event.value == 'PRESS'
                              and x >= region.width - 14 * self._scale):
                self._drag = True
                self._offset = self._max_offset * min(1, max(0, y / max(1, self._view_height)))
                self._area.tag_redraw()
                return {'RUNNING_MODAL'}
            hit = next(((tile, tile_action(tile, x, y + self._offset, self._scale))
                        for tile in self._tiles if _contains(tile[:4], x, y + self._offset)), None)
            hover = (hit[0][4], hit[1]) if hit else None
            if hover != self._hover:
                self._hover = hover
                self._area.tag_redraw()
            if event.type in {'LEFTMOUSE', 'RIGHTMOUSE'} and event.value == 'PRESS':
                self._pressed = (hover, event.type)
                return {'RUNNING_MODAL'}
            if event.type in {'LEFTMOUSE', 'RIGHTMOUSE'} and event.value == 'RELEASE':
                pressed, self._pressed = self._pressed, None
                if hit and pressed == (hover, event.type):
                    tile, action = hit
                    if not tile[5].get('is_preset'):
                        new_assets.mark_viewed(tile[4])
                    if event.type == 'RIGHTMOUSE' or action == 'options':
                        self.show_options(context, tile)
                    else:
                        object_id, data = tile[4:]
                        try:
                            bpy.ops.object.nms_asset_browser_object_selected(
                                'EXEC_DEFAULT', True, object_id=object_id, is_preset=bool(data.get('is_preset')),
                                has_variants=action == 'variants',
                                variants=json.dumps([object_id, *(data.get('variants') or [])]))
                        except RuntimeError as error:
                            self.report({'WARNING'}, str(error))
                    self.refresh(context)
                return {'RUNNING_MODAL'}
            # Keep Blender's image zoom/pan shortcuts from taking over the grid.
            if event.type in {'MIDDLEMOUSE', 'WHEELINMOUSE', 'WHEELOUTMOUSE'}:
                return {'RUNNING_MODAL'}
        except ReferenceError:
            self.finish(context)
            return {'CANCELLED'}
        return {'PASS_THROUGH'}

    def show_options(self, context, tile):
        object_id, data = tile[4:]
        def menu(menu, _context):
            from ..save_editor.function_help import corner_help
            layout = menu.layout
            corner_help(layout, 'ASSETS')
            op = layout.operator('object.nms_asset_browser_object_selected',
                                 text='Place Reference' if data.get('is_reference') else 'Place Part', icon='ADD')
            op.object_id, op.is_preset = object_id, bool(data.get('is_preset'))
            if data.get('variants'):
                op = layout.operator('object.nms_asset_browser_object_selected', text='Choose Variant', icon='PAUSE')
                op.object_id, op.has_variants = object_id, True
                op.variants = json.dumps([object_id, *data['variants']])
            if not data.get('is_preset'):
                layout.separator()
                op = layout.operator('object.nms_asset_browser_object_favourite', icon='HEART',
                    text='Remove from Favourites' if data.get('is_fav') else 'Add to Favourites')
                op.object_id = object_id
                if not data.get('is_reference'):
                    op = layout.operator('object.nms_asset_browser_batch_replace', text='Replace Selected Objects')
                    op.object_id = object_id
        context.window_manager.popup_menu(menu, title=data['name'])

    def rectangle(self, x, y, w, h, color):
        shader = self._rect_shader
        shader.bind()
        shader.uniform_float('color', color)
        batch_for_shader(shader, 'TRI_FAN', {'pos': ((x, y), (x+w, y), (x+w, y+h), (x, y+h))}).draw(shader)

    def new_border(self, x, y, w, h, scale):
        color = (1.0, 0.78, 0.06, 1.0)
        edge = max(2, 2 * scale)
        for rect in ((x, y, w, edge), (x, y+h-edge, w, edge),
                     (x, y, edge, h), (x+w-edge, y, edge, h)):
            self.rectangle(*rect, color)

    def label(self, x, y, label, width, size=12, color=None):
        blf.size(0, size * self._scale)
        label = str(label)
        if blf.dimensions(0, label)[0] > width:
            while label and blf.dimensions(0, label + '...')[0] > width:
                label = label[:-1]
            label += '...'
        blf.color(0, *(color if color is not None else self._palette['text']))
        blf.position(0, x, y, 0)
        blf.draw(0, label)

    def preview(self, object_id, x, y, size):
        if object_id not in self._textures:
            preview = icons.get_asset_icons_pcoll().get(object_id)
            if preview is None or not preview.image_size[0]:
                return
            width, height = preview.image_size
            # Bulk-copy the thumbnail into a contiguous buffer. Slicing the RNA
            # array creates tens of thousands of Python floats for each icon.
            values = array('f', [0.0]) * (width * height * 4)
            preview.image_pixels_float.foreach_get(values)
            pixels = gpu.types.Buffer('FLOAT', len(values), values)
            self._textures[object_id] = gpu.types.GPUTexture((width, height), format='RGBA8', data=pixels)
            # Only displayed previews become GPU textures. Cap the cache so a
            # long browsing session cannot load the complete library onto GPU.
            if len(self._textures) > 160:
                self._textures.popitem(last=False)
        self._textures.move_to_end(object_id)
        # Font drawing changes Blender's blend state between tiles.
        gpu.state.blend_set('ALPHA')
        shader = self._image_shader
        shader.bind()
        shader.uniform_sampler('image', self._textures[object_id])
        batch_for_shader(shader, 'TRI_FAN', {
            'pos': ((x,y), (x+size,y), (x+size,y+size), (x,y+size)),
            'texCoord': ((0,0), (1,0), (1,1), (0,1))}).draw(shader)

    def draw_grid(self):
        context = bpy.context
        if context.area is None or context.area.as_pointer() != self._key:
            return
        self.refresh(context)
        palette = self._palette = browser_palette(context)
        region = context.region
        width, height = region.width, region.height
        scale = max(.75, context.preferences.system.ui_scale)
        self._scale = scale
        notice = bubble_notice(context, self._hover)
        lines = []
        blf.size(0, 13 * scale)
        for paragraph in notice:
            line = ''
            for word in paragraph.split():
                candidate = (line + ' ' + word).strip()
                if line and blf.dimensions(0, candidate)[0] > width - 40 * scale:
                    lines.append(line)
                    line = word
                else:
                    line = candidate
            lines.append(line)
        footer = (30 + (len(lines) * 21 + 22 if lines else 0)) * scale
        self._view_height = max(1, height - footer)
        key = (width, height, scale, self._size, self._columns, self._signature, footer)
        if key != self._geometry_key:
            self._titles, self._tiles, self._total = grid_geometry(
                self._groups, width - 14 * scale, self._size, self._columns, scale)
            self._max_offset = max(0, self._total - self._view_height)
            self._offset = min(self._offset, self._max_offset)
            self._geometry_key = key
        gpu.state.blend_set('ALPHA')
        try:
            self.rectangle(0, 0, width, height, palette['background'])
            for x, top, title in self._titles:
                y = height - top + self._offset - 18 * scale
                if footer <= y <= height:
                    self.label(x, y, title, width - 30 * scale)
            for x, top, w, h, object_id, data in self._tiles:
                y = height - top - h + self._offset
                if y + h < footer or y > height:
                    continue
                hovered = self._hover and self._hover[0] == object_id
                self.rectangle(x, y, w, h, palette['hover'] if hovered else palette['card'])
                if not data.get('is_preset') and new_assets.is_new(object_id):
                    self.new_border(x, y, w, h, scale)
                text_color = palette['selected_text'] if hovered else palette['text']
                size = min(w - 8 * scale, h - 48 * scale)
                self.preview(object_id, x + (w-size)/2, y + 26 * scale, size)
                label_width = w - 12 * scale
                blf.size(0, 11 * scale)
                if (object_id in {'PIPE', 'PIPESHAPE'}
                        and blf.dimensions(0, data['name'])[0] > label_width):
                    # Keep the behavior visible even on the smallest tiles.
                    self.label(x+6*scale, y+18*scale, 'Pipe', label_width, 10, text_color)
                    behavior = data['name'].split(' — ', 1)[-1]
                    self.label(x+6*scale, y+5*scale, behavior, label_width, 10, text_color)
                else:
                    self.label(x+6*scale, y+8*scale, data['name'], label_width, 11, text_color)
                # These rectangles match tile_action's hit boxes exactly.
                if not data.get('is_preset'):
                    for line in range(3):
                        self.rectangle(x+8*scale, y+h-(8+line*4)*scale, 11*scale, scale, text_color)
                if data.get('variants'):
                    for line in range(2):
                        self.rectangle(x+w-(16-line*6)*scale, y+h-18*scale, 2*scale, 11*scale, text_color)
            if not self._tiles:
                self.label(12*scale, height-60*scale, 'No parts in this view.', width-24*scale)
            if self._max_offset:
                thumb = max(30*scale, self._view_height**2 / max(self._total, 1))
                top = self._offset / self._max_offset * (self._view_height-thumb)
                self.rectangle(width-9*scale, height-top-thumb, 5*scale, thumb, palette['accent'])
            self.rectangle(0, 0, width, 30*scale, palette['footer'])
            item = next((t for t in self._tiles if self._hover and t[4] == self._hover[0]), None)
            hint = item[5]['name'] + '  |  ' + item[4] if item else 'Click an image to place  |  Right-click for favourites and options'
            self.label(10*scale, 10*scale, hint, width-20*scale, 11)
            if lines:
                self.rectangle(0, 30*scale, width, footer-30*scale, palette['background'])
                self.rectangle(0, 30*scale, 5*scale, footer-30*scale, palette['accent'])
                for i, line in enumerate(lines):
                    self.label(16*scale, footer-(23+i*21)*scale, line, width-32*scale,
                               13, palette['text'])
            draw_auto_snap(self,width-19*scale,height-5*scale,scale)
        finally:
            gpu.state.blend_set('NONE')


@persistent
def _close_all(_dummy=None):
    for key in tuple(_resources):
        _release_session(key, bpy.context.window_manager)
    _pending_windows.clear()


def _saved_browser_target(window):
    areas = sorted(window.screen.areas, key=lambda area: area.x)
    if len(areas) != 2 or areas[0].type != 'PROPERTIES':
        return None
    pinned = areas[0].spaces.active.pin_id
    tagged = getattr(window.screen, 'get', lambda *args: False)('bbe_asset_browser', False)
    if not (_is_browser_pin(pinned) or _is_legacy_browser_layout(areas)
            or (pinned is None and tagged) or _is_unpinned_browser_layout(areas)):
        return None
    right = areas[1]
    return right if right.type in {'PROPERTIES', 'IMAGE_EDITOR'} else None


def _is_unpinned_browser_layout(areas):
    """Migrate the old pop-out layout when its object was omitted from a file.

    Require its complete hidden-chrome, empty-image, side-by-side layout. A
    normal Properties/Image Editor workspace or a pinned model is not ours.
    """
    if len(areas) != 2 or [area.type for area in areas] != ['PROPERTIES', 'IMAGE_EDITOR']:
        return False
    left, right = areas
    props, image = left.spaces.active, right.spaces.active
    return (props.pin_id is None and props.context == 'CONSTRAINT'
            and not props.show_region_header and not image.show_region_header
            and image.image is None and not image.show_region_ui
            and not image.show_region_toolbar and not image.show_region_tool_header
            and left.y == right.y and left.height == right.height
            and left.width < right.width)


def _is_legacy_browser_layout(areas):
    """Older launchers pinned an unlinked cube, not the newer tagged mesh.

    Recognize that only inside its dedicated saved browser layout. Do not
    broaden the scene-cleanup predicate: a similarly named model is user data.
    """
    if len(areas) != 2 or areas[0].type != 'PROPERTIES':
        return False
    left = areas[0].spaces.active
    obj = left.pin_id
    if (obj is None or getattr(obj, 'type', None) != 'MESH'
            or obj.name != 'Asset Browser Window' or not obj.use_fake_user
            or 'ObjectID' in obj
            or obj.users_collection or not left.use_pin_id
            or left.context != 'CONSTRAINT'):
        return False
    mesh = obj.data
    if (len(mesh.vertices), len(mesh.edges), len(mesh.polygons)) not in {
            (0, 0, 0), (8, 12, 6)}:
        return False
    right = areas[1]
    if right.type == 'IMAGE_EDITOR':
        return not right.spaces.active.show_region_header
    if right.type == 'PROPERTIES':
        return (right.spaces.active.pin_id == obj
                and right.spaces.active.context == 'MODIFIER')
    return False


def _is_browser_pin(obj):
    if obj is None or getattr(obj, 'type', None) != 'MESH':
        return False
    if obj.get('bbe_asset_browser_pin'):
        return True
    # Recognize the empty hidden helper saved by earlier BBE versions without
    # treating a user's ordinary object with the same name as our UI data.
    return (obj.name == 'Asset Browser Window' and not obj.data.vertices
            and obj.hide_render and obj.hide_select and obj.use_fake_user)


def _unlink_closed_browser_pins(window_manager):
    """Keep the UI pin in bpy.data, but out of the Outliner while closed."""
    if _pending_windows:
        return
    active = set()
    for window in window_manager.windows:
        for area in window.screen.areas:
            if area.type == 'PROPERTIES':
                pin = area.spaces.active.pin_id
                if _is_browser_pin(pin):
                    active.add(pin)
    for obj in tuple(bpy.data.objects):
        if _is_browser_pin(obj) and obj not in active:
            for collection in tuple(obj.users_collection):
                collection.objects.unlink(obj)


def _restore_saved_windows(window_manager):
    """A saved Blender layout restores areas, but not their modal grid operator."""
    for window in tuple(window_manager.windows):
        if window.as_pointer() in _pending_windows:
            continue
        right = _saved_browser_target(window)
        if right is None:
            continue
        if right.as_pointer() in _sessions:
            continue
        from .asset_browser_operators import browser_pin_object
        left = min(window.screen.areas, key=lambda area: area.x)
        with bpy.context.temp_override(window=window, area=left):
            left.spaces.active.pin_id = browser_pin_object()
            left.spaces.active.use_pin_id = True
            left.spaces.active.context = 'CONSTRAINT'
        window.screen['bbe_asset_browser'] = True
        if right.type == 'PROPERTIES':
            right.type = 'IMAGE_EDITOR'
        space = right.spaces.active
        space.show_region_ui = False
        space.show_region_toolbar = False
        space.show_region_header = False
        space.show_region_tool_header = False
        space.show_region_hud = False
        space.show_gizmo = False
        region = next((region for region in right.regions if region.type == 'WINDOW'), None)
        if region is None:
            continue  # The editor's region is created on the next UI update.
        with bpy.context.temp_override(window=window, area=right, region=region):
            bpy.ops.bbe.asset_grid('INVOKE_DEFAULT')


def _cleanup_closed():
    if not _enabled:
        return None
    live_areas = {area.as_pointer() for window in bpy.context.window_manager.windows
                  for area in window.screen.areas if area.type == 'IMAGE_EDITOR'}
    for key in tuple(_resources):
        if key not in live_areas:
            _release_session(key, bpy.context.window_manager)
    try:
        _restore_saved_windows(bpy.context.window_manager)
        _unlink_closed_browser_pins(bpy.context.window_manager)
    except (ReferenceError, RuntimeError, TypeError, AttributeError) as exc:
        print(f'BBE Asset Browser: grid restore will retry: {exc}')
    return 1.0


def register():
    global _enabled, _loading_handler
    bpy.utils.register_class(BBE_OT_asset_grid)
    _enabled = True
    bpy.app.handlers.load_pre.append(_close_all)
    bpy.app.handlers.load_post.append(_load_ready)
    _loading_handler=bpy.types.SpaceImageEditor.draw_handler_add(
        _draw_loading,(), 'WINDOW','POST_PIXEL')
    _load_ready()
    bpy.app.timers.register(_cleanup_closed, first_interval=1, persistent=True)


def unregister():
    global _enabled, _loading_handler
    _enabled = False
    if bpy.app.timers.is_registered(_restore_soon):
        bpy.app.timers.unregister(_restore_soon)
    if _loading_handler is not None:
        bpy.types.SpaceImageEditor.draw_handler_remove(_loading_handler,'WINDOW')
        _loading_handler=None
    bpy.app.handlers.load_post.remove(_load_ready)
    if bpy.app.timers.is_registered(_cleanup_closed):
        bpy.app.timers.unregister(_cleanup_closed)
    bpy.app.handlers.load_pre.remove(_close_all)
    _close_all()
    bpy.utils.unregister_class(BBE_OT_asset_grid)
