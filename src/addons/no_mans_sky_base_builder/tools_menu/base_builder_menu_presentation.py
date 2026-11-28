"""The UI drawn inside the "Base Builder" dropdown."""
from .. import i18n

import bpy
from itertools import islice
from ..tools import asset_browser_presentation
from ..save_editor import save_editor_presentation
from .. import icons, hd_library, hd_library_ui, project_recovery, wasd_navigation

class VIEW3D_PT_nms_io_panel(bpy.types.Panel):
    """ Save Files Browser """

    bl_idname = "VIEW3D_PT_nms_io_panel"
    bl_space_type = "VIEW_3D"
    bl_region_type = "HEADER"
    bl_translation_context = "BBEExtendedInterface"
    bl_label = "I/O"
    # Popovers size themselves from this rather than from their content.
    bl_ui_units_x = 20
    

    def draw(self, context):
        layout = i18n.localized_layout(self.layout)
        draw_io_contents(layout, context)


def draw_io_contents(layout, context):
    draw_build_files(layout, context)
    layout.separator()
    save_editor_presentation.draw_save_manager(layout, context, heading=True)


def draw_build_files(layout, context):
    from .. import menu_contract
    from ..save_editor.function_help import corner_help
    layout.prop(context.scene.nms_base_tool, 'string_base', text='Build Name')
    def scene_actions(row):
        row.operator('bbe.update_build', text='Update Current Build...', icon='FILE_REFRESH')
        corner_help(row, 'IO')

    menu_contract.files(layout, {
      'clear':('object.nms_new_file',{}), 'import':('bbe.import_build_file',{}),
      'json':('object.nms_save_data',{}), 'ship':('bbe.export_ship_file',{}),
      'base':('bbe.export_base_file',{}), 'paste':('object.nms_import_nms_data',{}),
      'copy_all':('object.nms_export_nms_data',{}), 'copy_objects':('object.nms_export_nms_data_objects',{})
    }, scene_actions)


class VIEW3D_PT_nms_base_builder(bpy.types.Panel):
    """ Quick options related to NMS Base and Corvette Builder"""

    bl_idname = "VIEW3D_PT_nms_base_builder"
    bl_space_type = "VIEW_3D"
    bl_region_type = "HEADER"
    bl_translation_context = "BBEExtendedInterface"
    bl_label = "Base Builder Extended"
    bl_description = "Proxy quality, Asset Browser, and quick access to parts"
    # Popovers size themselves from this rather than from their content.
    bl_ui_units_x = 20
    

    def draw(self, context):
        draw_builder_contents(i18n.localized_layout(self.layout), context)


def draw_builder_contents(layout, context):
    draw_builder_preferences(layout, context)
    wasd_navigation.draw_controls(layout, context)
    from .. import viewport_cutaway
    viewport_cutaway.draw_menu(layout, context)
    layout.separator()
    draw_proxy_controls(layout, context)
    layout.separator()
    draw_quick_access(layout, context)


def draw_builder_preferences(layout, context, *, include_guide=True):
    from ..save_editor.function_help import corner_help
    header = layout.row(align=True)
    header.popover(panel='VIEW3D_PT_bbe_themes', text='Themes', icon='COLOR')
    corner_help(header, 'BBE')
    if include_guide:
        layout.operator('bbe.find_guide', text='How-To Guide', icon='HELP')
    from .. import build_timer
    timer_row = layout.row(align=True)
    timer_row.label(text="Build timer", icon="TIME")
    addon = context.preferences.addons.get(build_timer.__package__)
    if addon:
        layout.prop(addon.preferences, 'bbe_language')
        timer_row.prop(addon.preferences, 'build_idle_minutes', text='Idle (min)')


def draw_proxy_controls(layout, context):
    proxy_box = layout.column(align=True)
    proxy_box.label(text="Switch Proxy Quality")
    proxy_column = proxy_box.row(align=False)
    detailed = hd_library_ui.detailed_enabled(context.scene)
    proxy_column.operator("object.nms_switch_proxies_to_low", **icons.ui_icon("MESH_CUBE"), text="Simple Proxies", depress=not detailed)
    proxy_column.operator("object.nms_switch_proxies_to_high", **icons.ui_icon("MESH_MONKEY"), text="Detailed Proxies", depress=detailed)
    remove_column = proxy_column.row(align=True)
    remove_column.alignment = 'RIGHT'
    remove_column.operator_context = 'INVOKE_DEFAULT'
    remove_column.operator('bbe.hd_remove', text='', **icons.ui_icon('TRASH'))
    if detailed:
        proxy_box.prop(context.scene, 'bbe_solid_decals')
    if hd_library.STATE['busy']:
        # Blender caches an open popover's layout. Keep live progress in
        # the viewport header/sidebar, where timer redraws are supported.
        proxy_box.label(text="Downloading: progress in top bar", **icons.ui_icon('IMPORT'))
        proxy_box.operator('bbe.hd_cancel', text='Cancel Download', **icons.ui_icon('CANCEL'))
    elif hd_library.available() and not hd_library.ready():
        update_row = proxy_box.row()
        update_row.operator_context = 'INVOKE_DEFAULT'
        update_row.operator('bbe.hd_library', text='Update Detailed Proxy Pack', icon='IMPORT')


QUICK_ACCESS_ROWS = 5
_native_favourite_source = None


class BBE_PG_quick_favourite(bpy.types.PropertyGroup):
    """Native list row. Its name is the catalogue part ID."""


class BBE_UL_quick_favourites(bpy.types.UIList):
    def draw_item(self, context, layout, data, item, icon, active_data, active_propname):
        parts = context.scene.nms_asset_browser.get_favourite_objects_data()
        part = parts.get(item.name)
        if part:
            draw_quick_part(i18n.localized_layout(layout), item.name, part, icons.get_asset_icons_pcoll())


def sync_native_favourites():
    # Blender disallows changing RNA collections in a panel draw callback.
    global _native_favourite_source
    wm = bpy.context.window_manager
    parts = bpy.context.scene.nms_asset_browser.get_favourite_objects_data()
    wm.bbe_quick_favourites.clear()
    for part_id in parts:
        wm.bbe_quick_favourites.add().name = part_id
    wm.bbe_quick_favourite_active = min(wm.bbe_quick_favourite_active, max(0, len(parts) - 1))
    _native_favourite_source = parts
    for window in wm.windows:
        for area in window.screen.areas:
            if area.type == 'VIEW_3D':
                area.tag_redraw()


def draw_quick_part(layout, object_id, part_data, pcoll):
    asset_browser_presentation.draw_quick_access_element(
        layout, object_id, part_data, pcoll[object_id].icon_id if object_id in pcoll else None)


def draw_quick_favourites(layout, wm, parts, pcoll):
    if len(parts) <= QUICK_ACCESS_ROWS:
        for part_id, part in parts.items():
            draw_quick_part(layout, part_id, part, pcoll)
        return

    list_window = getattr(layout, 'list_window', None)
    if list_window:
        box, start = list_window('bbe_quick_favourite_offset', len(parts), QUICK_ACCESS_ROWS, 26)
        for part_id, part in islice(parts.items(), start, start + QUICK_ACCESS_ROWS):
            draw_quick_part(box, part_id, part, pcoll)
    else:
        # The catalogue replaces its favourites dictionary on each edit.
        stale = parts is not _native_favourite_source or len(wm.bbe_quick_favourites) != len(parts)
        if stale and not bpy.app.timers.is_registered(sync_native_favourites):
            bpy.app.timers.register(sync_native_favourites, first_interval=0)
        layout.template_list('BBE_UL_quick_favourites', 'quick_access', wm, 'bbe_quick_favourites',
                             wm, 'bbe_quick_favourite_active', rows=QUICK_ACCESS_ROWS,
                             maxrows=QUICK_ACCESS_ROWS, type='DEFAULT')


def draw_quick_access(layout, context, *, compact=False):
    asset_browser = context.scene.nms_asset_browser
    wm = context.window_manager
    mode = wm.enum_assets_quick_access_view_mode
    pcoll = icons.get_asset_icons_pcoll()
    quick_access_column = layout.column(align = True)
    quick_access_column.label(text = "Quick Access")
    if compact:
        quick_access_column.prop(wm, "enum_assets_quick_access_view_mode", text="Parts")
    else:
        quick_access_column.row(align=True).prop(wm, "enum_assets_quick_access_view_mode", expand=True)
    quick_access_column.separator()


    def draw_assets(asset_data):
        if asset_data:
            # A popover needs full-width rows. Grid cards (and whole
            # search categories) side by side shrink to unusable slivers.
            for object_ids in asset_data.values():
                for object_id, part_data in object_ids.items():
                    draw_quick_part(quick_access_column, object_id, part_data, pcoll)


    if mode == "recent":
        recent_data = asset_browser.get_recent_objects_data()
        if recent_data:
            draw_assets({"Recent Objects": dict(islice(recent_data.items(), QUICK_ACCESS_ROWS))})
        else:
            quick_access_column.label(text="No recent parts yet.", **icons.ui_icon('INFO'))
    elif mode == "fav":
        fav_data = asset_browser.get_favourite_objects_data()
        if fav_data:
            draw_quick_favourites(quick_access_column, wm, fav_data, pcoll)
        else:
            quick_access_column.label(text="No favourite parts yet.", **icons.ui_icon('INFO'))
    else:
        quick_access_column.prop(asset_browser, "asset_broser_search_query", text="", **icons.ui_icon('VIEWZOOM'))
        query = asset_browser.asset_broser_search_query.strip()
        if len(query) > 2:
            draw_assets(asset_browser.filter_objects_with_string(query))
        else:
            quick_access_column.label(text="Type at least 3 characters.", **icons.ui_icon('INFO'))


class VIEW3D_PT_bbe_project_recovery(bpy.types.Panel):
    bl_idname = 'VIEW3D_PT_bbe_project_recovery'
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'HEADER'
    bl_translation_context = "BBEExtendedInterface"
    bl_label = 'Project Recovery'
    bl_ui_units_x = 16

    def draw(self, context):
        project_recovery.draw_controls(i18n.localized_layout(self.layout), context)


def _draw_toolbar_group(self, context):
    """Reuse the original controls; no second implementation to drift."""
    from .. import (
        NMS_PT_build_panel,
        NMS_PT_logic_panel,
    )
    from ..tools.properties_presentation import NMS_PT_transformation_panel
    from ..tools.build_tool_presentation import NMS_PT_tools_panel
    from ..tools.batch_tool_presentation import NMS_PT_batch_tools_panel
    group = self.toolbar_group
    sources = {
        "parts": (NMS_PT_build_panel,),
        "transform": (NMS_PT_transformation_panel,),
        "builder_tools": (NMS_PT_tools_panel,),
        "batch": (NMS_PT_batch_tools_panel,),
        "cables": (NMS_PT_logic_panel,),
    }
    for source in sources[group]:
        if hasattr(source, "poll") and not source.poll(context):
            if group == "transform":
                from ..save_editor.function_help import corner_help
                header = i18n.localized_layout(self.layout).row(align=True)
                header.label(text="Select a curve to edit its shape.", **icons.ui_icon("INFO"))
                corner_help(header, 'CURVES')
            continue
        if len(sources[group]) > 1:
            i18n.localized_layout(self.layout).label(text=source.bl_label)
        if source is NMS_PT_tools_panel:
            source.draw_controls(self, context)
        else:
            source.draw(self, context)


def _toolbar_panel(identifier, label, group, width):
    return type(
        "VIEW3D_PT_bbe_toolbar_" + identifier,
        (bpy.types.Panel,),
        {
            "bl_idname": "VIEW3D_PT_bbe_toolbar_" + identifier,
            "bl_label": label,
            "bl_description": "Open " + label + " controls",
            "bl_space_type": "VIEW_3D",
            "bl_region_type": "HEADER",
            "bl_ui_units_x": width,
            "toolbar_group": group,
            "draw": _draw_toolbar_group,
        },
    )


TOOLBAR_GROUPS = tuple(
    (_toolbar_panel(identifier, label, group, width), icon)
    for identifier, label, group, width, icon in (
        ("transform", "Curve Tools", "transform", 20, "CURVE_BEZCURVE"),
        ("cables", "Cables & Logic", "cables", 18, "CURVE_PATH"),
        ("builder_tools", "Builder Tools", "builder_tools", 20, "TOOL_SETTINGS"),
        ("batch", "Batch Tools", "batch", 19, "MOD_ARRAY"),
        ("parts", "Parts & Prefabs", "parts", 20, "ASSET_MANAGER"),
    )
)
                        


    
    
    

