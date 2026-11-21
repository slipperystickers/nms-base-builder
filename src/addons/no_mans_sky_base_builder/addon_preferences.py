from . import i18n
import bpy
from bpy.props import (BoolProperty, EnumProperty, FloatProperty, IntProperty,
                       PointerProperty, StringProperty)

from .save_editor import save_editor_utils
from .wasd_navigation import settings_changed

ADDON_ID = __package__

class NMSAddonPreferences(bpy.types.AddonPreferences):
    bbe_button_style: StringProperty(default='THEME', options={'HIDDEN'})
    bbe_button_style_original: StringProperty(default='', options={'HIDDEN'})
    bl_idname = ADDON_ID

    def _prefab_previews_changed(self, context):
        from . import prefab_thumbnails, settings_memory
        if not self.bbe_prefab_previews:
            prefab_thumbnails.stop_work()
        prefab_thumbnails.redraw()
        settings_memory.flush()

    bbe_prefab_previews: BoolProperty(
        name='Prefab Previews', default=False, update=_prefab_previews_changed,
        description='Generate and display 3D thumbnails in the local prefab library and Asset Browser',
    )
    bbe_language: i18n.language_property()
    bbe_wasd_enabled: BoolProperty(
        name='WASD Navigation', default=True, update=settings_changed,
        description='Hold right mouse in the 3D view for WASD movement and mouse look (Object and Mesh Edit modes); quick right-click still opens the context menu',
    )
    bbe_wasd_speed: FloatProperty(name='Navigation Speed', default=10, min=.01, max=10000,
        description='View movement in Blender units per second; mouse wheel adjusts while navigating')
    bbe_wasd_sensitivity: FloatProperty(name='Look Sensitivity', default=1, min=.1, max=5)

    bbe_recovery_mode: EnumProperty(translation_context="BBEExtendedInterface", 
        name='Project Recovery',
        description='When to make an independent recovery copy of the current Blender project',
        items=[('TIME', 'Time interval', 'Back up after the selected number of minutes'),
               ('PARTS', 'Part placement', 'Back up after the selected number of placed parts'),
               ('OFF', 'Off', 'Disable automatic recovery copies')],
        default='TIME',
    )
    bbe_recovery_minutes: IntProperty(
        name='Minutes', default=10, min=1, max=240,
        description='Minutes between recovery copies while the project has changes',
    )
    bbe_recovery_parts: IntProperty(
        name='Parts placed', default=5, min=1, max=1000,
        description='New BBE parts between recovery copies',
    )

    shape_use_blender_tools: BoolProperty(name="Use Blender Tools", default=False)
    curve_use_blender_tools: BoolProperty(name="Use Blender tools",default=False)
    curve_edge_max_turn: FloatProperty(name="Edge turn limit",default=35,min=0,max=90)
    bbe_sidebar_order: bpy.props.StringProperty(default='', options={'HIDDEN'})
    bbe_workspace_tab: bpy.props.EnumProperty(items=[('DISPLAY','Display','Viewport information'),('TOP','Top Bar','Show, hide and reorder top menus'),('SIDE','Sidebar','Show, hide and reorder sidebar panels')], default='DISPLAY')
    bbe_sidebar_hidden: StringProperty(default="")
    bbe_optional_menus_initialized: BoolProperty(default=False)
    bbe_menu_guide_seen: BoolProperty(default=False)
    bbe_menu_guide_version: IntProperty(default=0,options={"HIDDEN"})
    decal_projection_disabled: BoolProperty(default=False,options={"HIDDEN"})
    bbe_toolbar_order: StringProperty(
        name="Toolbar Order", default="",
        description="Order of the Base Builder toolbar menus",
    )
    bbe_toolbar_hidden: StringProperty(
        name="Hidden Toolbar Menus", default="transforms",
        description="Base Builder menus hidden from the second toolbar row",
    )

    nms_save_folder_path: StringProperty(
        name="Save Directory",
        description="Folder where save files are stored",
        subtype='DIR_PATH',
        default = str(save_editor_utils.get_default_save_folder())
    )

    nms_backup_folder_path: StringProperty(
        name='Backup Folder',
        description='Shared folder for project recovery and game-save backups; blank uses NoMansSkyBaseBuilder/Backups in your home folder',
        subtype='DIR_PATH',
        default='',
    )

    def _build_timer_changed(self, context):
        from . import build_timer
        build_timer.tracking_changed(self, context)

    build_timer_enabled: BoolProperty(
        name='Build timer', default=True, update=_build_timer_changed,
        description='Track time spent editing builds on this computer',
    )
    build_idle_minutes: IntProperty(
        name='Build Timer Idle Timeout (minutes)',
        description='Pause active build time after this many minutes without an edit to build parts',
        default=2, min=1, max=30,
    )

    nms_backup_retention: IntProperty(
        name='Backups per Save Slot',
        description='Number of automatic and manual backup generations to keep per account and save slot',
        default=20,
        min=1,
        max=500,
    )
    
    nms_check_show_properties : BoolProperty(
        name = "Display details in viewport",
        description = "Display some details like Part Count or active-object details on bottom left side of 3-d viewport",
        default = True
    )
    
    nms_check_show_active_object_properties : BoolProperty(
        name = "Display details in viewport",
        description = "Display some details like Part Count or active-object details on bottom left side of 3-d viewport",
        default = True
    )
    
    nms_active_object_properties_position: EnumProperty(translation_context="BBEExtendedInterface", 
        name="Active-Object poroperties locatino",
        description="Location in 3d viewport where object properties are to be displayed",
        items = [
            ("Top", "Top", "Display properties at top"),
            ("Bottom", "Bottom", "Display properties at bottom"),
        ],
        default = "Bottom"
    )
    
    nms_check_show_part_count : BoolProperty(
        name = "Display details in viewport",
        description = "Display some details like Part Count or active-object details on bottom left side of 3-d viewport",
        default = True
    )
    
    nms_part_count_position: EnumProperty(translation_context="BBEExtendedInterface", 
        name="Place where part count is to be shown",
        description="Location in 3d viewport where properties are to be displayed",
        items = [
            ("Top", "Top", "Display properties at top"),
            ("Bottom", "Bottom", "Display properties at bottom"),
        ],
        default = "Bottom"
    )
    
    asset_browser_icon_size_other: bpy.props.IntProperty(
        name="Size",
        description="Icons Size",
        default = 4,
        min = 1,
        max = 10,
        options={'TEXTEDIT_UPDATE'}
    )
    
    asset_browser_number_of_columns_other: bpy.props.IntProperty(
        name="Nomber of Columns",
        description="Number of elements to display in each row",
        default = 10,
        min = 4,
        max = 15,
        options={'TEXTEDIT_UPDATE'}
    )
    
    asset_browser_icon_size_list: bpy.props.IntProperty(
        name="Size",
        description="Icons Size",
        default = 2,
        min = 1,
        max = 10,
        options={'TEXTEDIT_UPDATE'}
    )
    
    asset_browser_number_of_columns_list: bpy.props.IntProperty(
        name="Nomber of Columns",
        description="Number of elements to display in each row",
        default = 3,
        min = 1,
        max = 16,
        options={'TEXTEDIT_UPDATE'}
    )
    
    asset_browser_icon_size: bpy.props.IntProperty(
        name="Size",
        description="Icons Size",
        default = 3,
        min = 1,
        max = 10,
        options={'TEXTEDIT_UPDATE'}
    )
    
    asset_browser_number_of_columns: bpy.props.IntProperty(
        name="Nomber of Columns",
        description="Number of elements to display in each row",
        default = 3,
        min = 1,
        max = 10,
        options={'TEXTEDIT_UPDATE'}
    )
    
    enum_asset_browser_mode: bpy.props.EnumProperty(translation_context="BBEExtendedInterface", 
        name="View Mode",
        description="Asset Browser View Mode",
        items = [
            ("List", "List", "List","ALIGN_LEFT", 0),
            ("Grid", "Grid", "Grid","LIGHTPROBE_VOLUME",1)
        ],
        default = "Grid"
    )
    
    favourite_categories: bpy.props.StringProperty(
        name = "Favourite Categories",
        description = "List of Categories that are marked as Favourite",
        default = ""
    )
    
    favourite_objects: bpy.props.StringProperty(
        name = "Favourite Objects",
        description = "List of Objects that are marked as Favourite",
        default = ""
    )
    
    recent_objects: bpy.props.StringProperty(
        name = "Recent Objects",
        description = "List of Objects that have been recently added",
        default = ""
    )

    def draw(self, context):
        layout = i18n.localized_layout(self.layout)
        layout.prop(self, "bbe_language")
        layout.label(text="No Man's Sky Base Builder")
        layout.label(text="Original creator: DjMonkey")
        layout.prop(self, 'nms_save_folder_path')
        from .save_editor import backup_policy
        layout.label(text=f'Backup Folder: {backup_policy.root_directory()}', icon='FILE_FOLDER')
        row = layout.row(align=True)
        row.operator('bbe.open_backup_root', text='Open Backup Folder', icon='FOLDER_REDIRECT')
        row.operator_context = 'INVOKE_DEFAULT'
        row.operator('bbe.backup_settings', text='Change Folder...', icon='PREFERENCES')
        layout.prop(self, 'nms_backup_retention')
        layout.prop(self, 'build_idle_minutes')
        layout.operator('bbe.recover_draft_time', text='Recover Draft Time...', icon='TIME')
        layout.separator()
        from .tools_menu.base_builder_menu import draw_toolbar_settings
        draw_toolbar_settings(layout, context)
        layout.separator()
        credits = layout.box()
        credits.label(text="Contributors")
        credits.label(text="Kuma The Wizard of Cosmos - high-res assets and builder updates")
        credits.label(text="FuriousFurby - station references, settlement icons and integration")
