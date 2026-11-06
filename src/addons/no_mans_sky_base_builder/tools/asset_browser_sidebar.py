"""Clickable thumbnails in the 3D View's NMS Asset Browser sidebar tab.

Blender's template_icon draws a full-size preview but has no click action, while
operator icons are only toolbar-sized. This draws the same GPU thumbnail tiles
as the popout browser into the sidebar UI region and handles their hit boxes.
The search and category controls above the tiles remain native Blender widgets.
"""
import json
from collections import OrderedDict

import bpy
import gpu
from bpy.app.handlers import persistent

from .asset_browser_grid import (
    BBE_OT_asset_grid, _contains, _groups, grid_geometry, tile_action, browser_palette,
    draw_auto_snap, auto_snap_event,
)
from ..utils import new_assets
from ..utils.asset_browser_utils import get_grid_settings

_sessions = {}
_resources = {}
_panel_bodies = {}
_enabled = False
_CATEGORY = 'NMS Asset Browser'
_PANEL_LEFT = 6
_PANEL_RIGHT = 25


def panel_visibility(context, expanded):
    """The native header/body draw callbacks report whether the panel is open.

    Blender draws the header for collapsed panels too, but only calls the body
    callback when expanded. Category selection alone cannot establish that.
    Store region identity as well, since opening a file replaces the layout.
    """
    _panel_bodies[context.area.as_pointer()] = (context.region.as_pointer(), expanded)


def grid_bounds(width, height, scale):
    """Shared drawing/input bounds, excluding Blender's tabs and resize edge."""
    return (_PANEL_LEFT * scale, 0,
            max(0, width - (_PANEL_LEFT + _PANEL_RIGHT) * scale),
            max(0, height - 170 * scale))


def scrollbar_bounds(bounds, scale):
    left, bottom, width, height = bounds
    return (left + width - 11 * scale, bottom, 11 * scale, height)


def request_redraw():
    for session in tuple(_sessions.values()):
        try:
            session._area.tag_redraw()
        except ReferenceError:
            pass


def _release(key, wm):
    resources = _resources.pop(key, None)
    if resources:
        handler, timer, textures = resources
        bpy.types.SpaceView3D.draw_handler_remove(handler, 'UI')
        try:
            wm.event_timer_remove(timer)
        except ReferenceError:
            pass
        textures.clear()
    _sessions.pop(key, None)
    _panel_bodies.pop(key, None)


class BBE_OT_sidebar_asset_grid(bpy.types.Operator):
    bl_idname = 'bbe.sidebar_asset_grid'
    bl_label = 'Sidebar Asset Browser Grid'
    bl_options = {'INTERNAL'}

    # Both browser surfaces must draw the same full-size preview and menus.
    rectangle = BBE_OT_asset_grid.rectangle
    new_border = BBE_OT_asset_grid.new_border
    label = BBE_OT_asset_grid.label
    preview = BBE_OT_asset_grid.preview
    show_options = BBE_OT_asset_grid.show_options

    def invoke(self, context, event):
        if context.area.type != 'VIEW_3D' or context.region.type != 'UI':
            return {'CANCELLED'}
        key = context.area.as_pointer()
        if key in _sessions:
            return {'CANCELLED'}
        self._window, self._area, self._key = context.window, context.area, key
        self._offset, self._hover, self._pressed, self._drag = 0, None, None, False
        self._signature, self._geometry_key = None, None
        self._textures = OrderedDict()
        self._groups, self._tiles, self._titles = {}, [], []
        self._total, self._max_offset, self._view_height = 0, 0, 1
        self._scale = 1
        self._bounds = None
        self._rect_shader = gpu.shader.from_builtin('UNIFORM_COLOR')
        self._image_shader = gpu.shader.from_builtin('IMAGE')
        handler = bpy.types.SpaceView3D.draw_handler_add(self.draw_grid, (), 'UI', 'POST_PIXEL')
        timer = context.window_manager.event_timer_add(.5, window=context.window)
        _sessions[key] = self
        _resources[key] = (handler, timer, self._textures)
        context.window_manager.modal_handler_add(self)
        self.refresh(context)
        return {'RUNNING_MODAL'}

    def refresh(self, context):
        scene = self._window.scene
        browser = scene.nms_asset_browser
        size, columns = get_grid_settings(context, 'asset_browser_icon_size',
                                         'asset_browser_number_of_columns')
        signature = (scene.as_pointer(), browser.view_revision, size, columns,
                     browser.enum_asset_browser_what_to_display,
                     browser.asset_browser_caterogies,
                     browser.asset_browser_sub_caterogies)
        if signature != self._signature:
            groups = _groups(scene)
            if tuple(groups) != tuple(self._groups):
                self._offset = 0
            self._signature, self._groups = signature, groups
            self._size, self._columns = size, columns
            self._geometry_key = None
            self._hover = None
            self._area.tag_redraw()

    def _active(self, region):
        active_object = self._window.view_layer.objects.active
        return (region and region.type == 'UI' and region.width > 64 and
                (active_object is None or active_object.mode == 'OBJECT') and
                self._area.spaces.active.show_region_ui and
                _panel_bodies.get(self._key) == (region.as_pointer(), True) and
                region.active_panel_category == _CATEGORY)

    def modal(self, context, event):
        if not _enabled or self._key not in _sessions:
            return {'CANCELLED'}
        try:
            if self._area.type != 'VIEW_3D' or self._area not in tuple(self._window.screen.areas):
                _release(self._key, context.window_manager)
                return {'CANCELLED'}
            if context.window != self._window:
                return {'PASS_THROUGH'}
            if event.type == 'TIMER':
                region = next((r for r in self._area.regions if r.type == 'UI'), None)
                if self._active(region):
                    self.refresh(context)
                return {'PASS_THROUGH'}
            region = next((r for r in self._area.regions if r.type == 'UI'), None)
            if not self._active(region):
                self._drag, self._pressed, self._hover = False, None, None
                return {'PASS_THROUGH'}
            if self._bounds is None:
                return {'PASS_THROUGH'}
            x = event.mouse_x - region.x
            y = event.mouse_y - region.y
            if auto_snap_event(self,event,x,y):return {'RUNNING_MODAL'}
            inside = _contains(self._bounds, x, y)
            if event.type == 'LEFTMOUSE' and event.value == 'RELEASE' and self._drag:
                self._drag = False
                return {'RUNNING_MODAL'}
            if self._drag or (self._max_offset > 0 and event.type == 'LEFTMOUSE' and
                              event.value == 'PRESS' and
                              _contains(scrollbar_bounds(self._bounds, self._scale), x, y)):
                self._drag = True
                self._offset = self._max_offset * min(1, max(0, (self._view_height-y) / max(1, self._view_height)))
                self._area.tag_redraw()
                return {'RUNNING_MODAL'}
            if not inside:
                if event.value == 'RELEASE':
                    self._pressed = None
                if self._hover is not None:
                    self._hover = None
                    self._area.tag_redraw()
                return {'PASS_THROUGH'}
            if event.type in {'WHEELUPMOUSE', 'WHEELDOWNMOUSE'}:
                step = 90 * self._scale * (1 if event.type == 'WHEELDOWNMOUSE' else -1)
                self._offset = max(0, min(self._max_offset, self._offset + step))
                self._area.tag_redraw()
                return {'RUNNING_MODAL'}
            top_y = self._view_height - y + self._offset
            hit = next(((tile, tile_action(tile, x, top_y, self._scale))
                        for tile in self._tiles
                        if self._offset <= tile[1] and
                        tile[1] + tile[3] <= self._offset + self._view_height and
                        _contains(tile[:4], x, top_y)), None)
            hover = (hit[0][4], hit[1]) if hit else None
            if hover != self._hover:
                self._hover = hover
                self._area.tag_redraw()
            if event.type in {'LEFTMOUSE', 'RIGHTMOUSE'} and event.value == 'PRESS':
                if hit:
                    self._pressed = (hover, event.type)
                    return {'RUNNING_MODAL'}
                return {'PASS_THROUGH'}
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
                        bpy.ops.object.nms_asset_browser_object_selected(
                            'EXEC_DEFAULT', object_id=object_id,
                            is_preset=bool(data.get('is_preset')),
                            has_variants=action == 'variants',
                            variants=json.dumps([object_id, *(data.get('variants') or [])]))
                    self.refresh(context)
                    return {'RUNNING_MODAL'}
        except ReferenceError:
            _release(self._key, context.window_manager)
            return {'CANCELLED'}
        return {'PASS_THROUGH'}

    def draw_grid(self):
        context = bpy.context
        if context.area is None or context.area.as_pointer() != self._key:
            return
        region = context.region
        if not self._active(region):
            self._bounds = None
            return
        self.refresh(context)
        palette = self._palette = browser_palette(context)
        width, height = region.width, region.height
        scale = max(.75, context.preferences.system.ui_scale)
        self._scale = scale
        # Panel header, search, quick categories, category, group and hint.
        # Keep this strip native so text entry and dropdowns retain Blender's UI.
        self._bounds = grid_bounds(width, height, scale)
        left, _bottom, panel_width, self._view_height = self._bounds
        key = (width, height, scale, self._size, self._columns, self._signature)
        if key != self._geometry_key:
            titles, tiles, self._total = grid_geometry(
                self._groups, panel_width, self._size, self._columns, scale)
            self._titles = [(x + left, top, title) for x, top, title in titles]
            self._tiles = [(x + left, top, w, h, object_id, data)
                           for x, top, w, h, object_id, data in tiles]
            self._max_offset = max(0, self._total - self._view_height)
            self._offset = min(self._offset, self._max_offset)
            self._geometry_key = key
        gpu.state.blend_set('ALPHA')
        try:
            self.rectangle(left, 0, panel_width, self._view_height, palette['background'])
            for x, top, title in self._titles:
                y = self._view_height - top + self._offset - 18 * scale
                if 0 <= y <= self._view_height:
                    self.label(x, y, title, panel_width - 20 * scale)
            for x, top, w, h, object_id, data in self._tiles:
                y = self._view_height - top - h + self._offset
                if y + h < 0 or y + h > self._view_height or y < 0:
                    continue
                hovered = self._hover and self._hover[0] == object_id
                self.rectangle(x, y, w, h, palette['hover'] if hovered else palette['card'])
                if not data.get('is_preset') and new_assets.is_new(object_id):
                    self.new_border(x, y, w, h, scale)
                text_color = palette['selected_text'] if hovered else palette['text']
                size = min(w - 8 * scale, h - 48 * scale)
                self.preview(object_id, x + (w-size)/2, y + 26 * scale, size)
                self.label(x+5*scale, y+8*scale, data['name'], w-10*scale, 11, text_color)
                if not data.get('is_preset'):
                    for line in range(3):
                        self.rectangle(x+8*scale, y+h-(8+line*4)*scale,
                                       11*scale, scale, text_color)
                if data.get('variants'):
                    for line in range(2):
                        self.rectangle(x+w-(16-line*6)*scale, y+h-18*scale,
                                       2*scale, 11*scale, text_color)
            if not self._tiles:
                self.label(left + 12*scale, self._view_height-25*scale,
                           'No parts in this view.', panel_width-24*scale)
            if self._max_offset:
                track_x, _bottom, _width, _height = scrollbar_bounds(self._bounds, scale)
                thumb = max(30*scale, self._view_height**2 / max(self._total, 1))
                top = self._offset / self._max_offset * (self._view_height-thumb)
                self.rectangle(track_x+4*scale, self._view_height-top-thumb,
                               4*scale, thumb, palette['accent'])
            draw_auto_snap(self,left+panel_width-13*scale,self._view_height-4*scale,scale)
        finally:
            gpu.state.blend_set('NONE')


@persistent
def _close_all(_dummy=None):
    for key in tuple(_resources):
        _release(key, bpy.context.window_manager)
    _panel_bodies.clear()


def _restore():
    if not _enabled:
        return None
    wm = bpy.context.window_manager
    live = set()
    for window in tuple(wm.windows):
        for area in tuple(window.screen.areas):
            if area.type != 'VIEW_3D':
                continue
            key = area.as_pointer()
            live.add(key)
            if key in _sessions:
                continue
            region = next((r for r in area.regions if r.type == 'UI' and r.width > 1), None)
            if region is None:
                continue
            try:
                with bpy.context.temp_override(window=window, area=area, region=region):
                    bpy.ops.bbe.sidebar_asset_grid('INVOKE_DEFAULT')
            except (ReferenceError, RuntimeError, TypeError, AttributeError) as exc:
                print(f'BBE Asset Browser: sidebar grid will retry: {exc}')
    for key in tuple(_resources):
        if key not in live:
            _release(key, wm)
    return 1.0


def register():
    global _enabled
    bpy.utils.register_class(BBE_OT_sidebar_asset_grid)
    _enabled = True
    bpy.app.handlers.load_pre.append(_close_all)
    bpy.app.timers.register(_restore, first_interval=1, persistent=True)


def unregister():
    global _enabled
    _enabled = False
    if bpy.app.timers.is_registered(_restore):
        bpy.app.timers.unregister(_restore)
    bpy.app.handlers.load_pre.remove(_close_all)
    _close_all()
    bpy.utils.unregister_class(BBE_OT_sidebar_asset_grid)
