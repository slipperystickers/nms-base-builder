"""The UI drawn inside the "Base Builder" dropdown."""

import bpy
from ..tools import asset_browser_presentation
from ..save_editor import save_editor_presentation
from ..save_editor.save_editor_utils import BaseType
from .. import icons, hd_library, hd_library_ui, project_recovery, wasd_navigation

class VIEW3D_PT_nms_io_panel(bpy.types.Panel):
    """ Save Files Browser """

    bl_idname = "VIEW3D_PT_nms_io_panel"
    bl_space_type = "VIEW_3D"
    bl_region_type = "HEADER"
    bl_label = "I/O"
    # Popovers size themselves from this rather than from their content.
    bl_ui_units_x = 22
    

    def draw(self, context):
        layout = self.layout
        draw_io_contents(layout, context)


def draw_io_contents(layout, context):
    files = layout.column(align=True)
    files.label(text='Standalone build files', **icons.ui_icon('FILE_FOLDER'))
    files.operator('bbe.import_build_file', text='Import Build from File...', **icons.ui_icon('IMPORT'))
    files.operator('bbe.export_ship_file', text='Export Corvette (.nmsship)...', **icons.ui_icon('EXPORT'))
    files.operator('bbe.export_base_file', text='Export Base (.nmsbase)...', **icons.ui_icon('EXPORT'))
    files.operator('object.nms_save_data', text='Save BBE Project JSON...', **icons.ui_icon('FILE_TICK'))
    layout.separator()
    layout.label(text="Save Manager", **icons.ui_icon("FILE_TICK"))
    save_editor_presentation.draw_save_manager(layout, context)
    if not context.scene.nms_save_data.check_plugin_enabled:
        layout.label(text="Enable to choose a save and access its tools.", **icons.ui_icon("INFO"))
    elif context.scene.nms_save_data.get_current_slot_data() is not None:
        layout.separator()
        advanced = layout.column(align=True)
        advanced.label(text='Advanced save tools', **icons.ui_icon('WARNING_LARGE'))
        advanced.operator_context = 'INVOKE_DEFAULT'
        ship = advanced.column(align=True)
        ship.enabled = context.scene.nms_save_data.nms_base_type == BaseType.CORVETTE
        ship.operator('bbe.ship_management', text='Ship Management (Beta)',
                      **icons.ui_icon('OUTLINER_OB_LIGHTPROBE'))
        advanced.operator('bbe.buildable_unlocks', text='Account Item Unlock and Currency Modify',
                          **icons.ui_icon('UNLOCKED'))
        advanced.operator('bbe.raw_save_json', text='Raw Save JSON Viewer / Editor',
                          **icons.ui_icon('TEXT'))


class VIEW3D_PT_nms_base_builder(bpy.types.Panel):
    """ Quick options related to NMS Base and Corvette Builder"""

    bl_idname = "VIEW3D_PT_nms_base_builder"
    bl_space_type = "VIEW_3D"
    bl_region_type = "HEADER"
    bl_label = "Base Builder Extended"
    bl_description = "Proxy quality, Asset Browser, and quick access to parts"
    # Popovers size themselves from this rather than from their content.
    bl_ui_units_x = 20
    

    def draw(self, context):
        """Draw the Base Builder dropdown's contents into `layout`."""
        layout = self.layout
        
        asset_browser = context.scene.nms_asset_browser
        enum_assets_quick_access_view_mode = context.scene.enum_assets_quick_access_view_mode
        pcoll = icons.get_asset_icons_pcoll()
        
        
        wasd_navigation.draw_controls(layout, context)
        from ..save_editor.corvette_optimizer import draw_cockpit_controls
        from ..save_editor.function_help import help_button
        draw_cockpit_controls(layout)
        help_button(layout, text='BBE Feature Help')
        layout.popover(panel='VIEW3D_PT_bbe_themes', text='Themes', icon='COLOR')
        layout.separator()
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
            update_row.operator('bbe.hd_library', text='Update HD Asset Packs', icon='IMPORT')
    
        
        layout.separator()
        quick_access_column = layout.column(align = True)
        quick_access_column.label(text = "Quick Access")
        quick_access_column.row(align = True).prop(context.scene,"enum_assets_quick_access_view_mode", expand = True)
        quick_access_column.separator()
        
        
        def draw_assets(asset_data):
            if asset_data:
                # A popover needs full-width rows. Grid cards (and whole
                # search categories) side by side shrink to unusable slivers.
                for object_ids in asset_data.values():
                    for object_id, part_data in object_ids.items():
                        asset_browser_presentation.draw_quick_access_element(
                            quick_access_column, object_id, part_data,
                            pcoll[object_id].icon_id if object_id in pcoll else None)
                
        
        if enum_assets_quick_access_view_mode == "recent":
            recent_data = asset_browser.get_recent_objects_data()
            if recent_data:
                draw_assets({"Recent Objects": dict(list(recent_data.items())[:5])})
            else:
                quick_access_column.label(text="No recent parts yet.", **icons.ui_icon('INFO'))
        elif enum_assets_quick_access_view_mode == "fav":
            fav_data = asset_browser.get_favourite_objects_data()
            if fav_data:
                draw_assets({"Favourite Objects": fav_data})
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
    bl_label = 'Project Recovery'
    bl_ui_units_x = 16

    def draw(self, context):
        project_recovery.draw_controls(self.layout, context)


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
                self.layout.label(text="Select a part to edit its transform.", **icons.ui_icon("INFO"))
            continue
        if len(sources[group]) > 1:
            self.layout.label(text=source.bl_label)
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
        ("transform", "Transformations", "transform", 19, "ORIENTATION_GIMBAL"),
        ("cables", "Cables & Logic", "cables", 18, "CURVE_PATH"),
        ("builder_tools", "Builder Tools", "builder_tools", 20, "TOOL_SETTINGS"),
        ("batch", "Batch Tools", "batch", 19, "MOD_ARRAY"),
        ("parts", "Parts & Prefabs", "parts", 20, "ASSET_MANAGER"),
    )
)
                        


    
    
    

