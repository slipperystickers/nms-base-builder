import json
import os
import subprocess
import sys
import webbrowser

import bpy
import bpy.ops
import bpy.utils
import bpy.utils.previews
import math
from bpy.app.handlers import persistent
from bpy.props import (BoolProperty, EnumProperty, FloatProperty, IntProperty,
                       PointerProperty, StringProperty)
from bpy.types import Panel, PropertyGroup
from pathlib import Path

from . import builder, icons, part, preset, group, builder_v2, viewport_overlay
from .base_properties import NMSBaseProperties
from .addon_preferences import NMSAddonPreferences
from .part_overrides import line
from .save_editor import save_editor_operators, save_editor_utils, station_reference
from .save_editor.save_editor_presentation import NMS_PT_save_editor_panel
from .save_editor.save_manager import SaveManager

from .tools import batch_tool_operators, build_tool_operators, prooperties_operators, asset_browser_operators
from .tools_menu import base_builder_menu, base_builder_menu_operators
from .tools.batch_tool import BatchTool
from .tools.batch_tool_presentation import NMS_PT_batch_tools_panel
from .tools.build_tool import BuildTool
from .tools.build_tool_presentation import NMS_PT_tools_panel
from .tools.properties import Properties
from .tools.properties_presentation import NMS_PT_base_prop_panel, NMS_PT_transformation_panel
from .tools.asset_browser import AssetBrowser, NMSCategoryOrderItem
from .tools import asset_browser_presentation

from .utils import blend_utils, curve, dictionary
from .utils import material as _material
from .utils import materials_v2 as _materials_v2
from .utils import python as python_utils
from .utils import workspace



FILE_PATH = os.path.dirname(os.path.realpath(__file__))
USER_PATH = os.path.join(os.path.expanduser("~"), "NoMansSkyBaseBuilder")
PRESET_PATH = os.path.join(USER_PATH, "presets")
ASSET_BROWSER_PATH = os.path.join(FILE_PATH, "asset_browser")

BUILDER = builder.Builder()
GHOSTED_JSON = os.path.join(FILE_PATH, "resources", "ghosted.json")
ghosted_reference = python_utils.load_dictionary(GHOSTED_JSON)
GHOSTED_ITEMS = ghosted_reference["GHOSTED"]
nice_name_dictionary = dictionary.get_nice_names_diictionary()

ADDON_ID = __package__


# Setting Support Methods ---
def ShowMessageBox(message="", title="Message Box", icon="INFO"):
    def draw(self, context):
        self.layout.label(text=message)

    bpy.context.window_manager.popup_menu(draw, title=title, icon=icon)


def part_switch(self, context):
    """Toggle method for switching between parts and presets."""
    scene = context.scene
    part_list = "presets" if self.enum_switch == {"PRESETS"} else "parts"

    if self.enum_switch not in [{"PRESETS"}]:
        refresh_ui_part_list(scene, part_list, pack=list(self.enum_switch)[0])
    else:
        refresh_ui_part_list(scene, part_list)


def get_line_type_from_enum(context):
    line_object = "U_POWERLINE"
    scene = context.scene
    nms_tool = scene.nms_main
    line_value = nms_tool.line_switch
    if line_value == "TELEPORT":
        line_object = "U_PORTALLINE"
    elif line_value == "PIPE":
        line_object = "U_PIPELINE"
    elif line_value == "BYTEBEAT":
        line_object = "U_BYTEBEATLINE"
        
    print("line value is :", line_value)
    return line_object


# Core Settings Class
class NMSMain(PropertyGroup):
    # Build Array of base part types. (Vanilla Parts - Mods - Presets)
    enum_items = []
    for pack, _ in BUILDER.available_packs:
        enum_items.append((pack, pack, "View {0}...".format(pack)))
    enum_items.append(("PRESETS", "Prefabs", "View Prefabs..."))

    # Blender Properties.
    enum_switch: EnumProperty(
        name="enum_switch",
        description="Toggle to display between parts and presets.",
        items=enum_items,
        options={"ENUM_FLAG"},
        default=None,
        update=part_switch,
    )

    material_switch: EnumProperty(
        name="Material Palette",
        description="Decide what type of material to apply",
        items=_material.BAKED_PALETTES_UI,
    )

    line_switch: EnumProperty(
        name="line_switch",
        description="Decide what type of cable to build",
        items=[
            ("POWER", "Electrical Wire", "Electrical Wire"),
            ("TELEPORT", "Teleport Wire", "Teleport Wire"),
            ("BYTEBEAT", "Byte-Beat Cable", "Byte-Beat Cable"),
            ("PIPE", "Pipe", "Pipe"),
        ],
        #options={"ENUM_FLAG"},
        default="POWER",
    )

    preset_name: StringProperty(
        name="preset_name", description="The of a preset.", default="", maxlen=1024
    )
    
    is_workspace_cleaned: BoolProperty(
        name="Is Workspace Cleaned", description="Check if workspace has been cleaned by user", default=False
    )

    room_vis_switch: IntProperty(name="room_vis_switch", default=0)
    
    color_picker: bpy.props.PointerProperty(
        name="Colour Picker",
        type=bpy.types.Object,
        options={'SKIP_SAVE'},
        description = "Pick an object to use are reference for colouring",
        update = lambda self, context: self.on_color_picked()
    )


    check_export_objects_only: bpy.props.BoolProperty(
        name="Objectsd Only",
        description="Checking this will only export objects when export button is clicked",
        default=False,
    )
    
    def deserialise_from_data(self, nms_data, start_new_file = True):
        if start_new_file:
            # Start new file
            self.new_file()

        base_props = bpy.context.scene.nms_base_tool
        base_props.deserialise_from_data(nms_data)

    def serialise(self, get_presets=False, objects_only=False):
        """Export the data in the blender scene to NMS compatible data.

        This will slot the data into the clip-board so you can easy copy
        and paste data back and forth between the tool.
        """
        
        # Capture Individual Objects
        objects_data = BUILDER.serialise(get_presets=get_presets)
        if objects_only:
            return objects_data["Objects"]
        
        base_props = bpy.context.scene.nms_base_tool
        data = base_props.serialise()
        
        data.update(objects_data)
        return data

    # Import and Export Methods ---
    def import_nms_data(self):
        """Import and build a base based on the contents of user clipboard.

        The clipboard should contain a copy of the base data found in the
        No Man's Sky Save Editor.
        """
        # Read clipboard data.
        clipboard_data = bpy.context.window_manager.clipboard
        try:
            nms_import_data = json.loads(clipboard_data)
        except:
            message = (
                "Could not import base data, are you sure you copied "
                "the data to the clipboard? (Ctrl+C from No Man's Sky Save Editor)"
            )
            ShowMessageBox(message=message, title="Import")
            return

        # Start a new file
        if isinstance(nms_import_data, list):
            nms_import_data = {"Objects": nms_import_data}
        self.deserialise_from_data(nms_import_data)
        previous_objects = set(bpy.context.scene.objects)
        builder_v2.deserialise_from_data(nms_import_data)
        station_reference.finish_transfer_import(bpy.context, nms_import_data, previous_objects)
        #BUILDER.deserialise_from_data(nms_import_data)

    def export_nms_data(self, objects_only=False):
        """Generate data and place it into the user's clipboard.

        This generates a flat set of individual base parts for NMS to read.
        All preset information is lost in this process.
        """
        data = self.serialise(objects_only=objects_only)
        bpy.context.window_manager.clipboard = json.dumps(data, indent=4)

    # Save and Load Methods ---
    def save_nms_data(self, file_path):
        """Generate data and place it into a json file.

        This preserves any presets built in scene.

        Args:
            file_path (str): The path to the json file.
        """
        data = self.serialise(get_presets=True)
        # Add .json if it's not specified.
        if not file_path.endswith(".json"):
            file_path += ".json"
        # Save to file path
        with open(file_path, "w") as stream:
            json.dump(data, stream, indent=4)

    def load_nms_data(self, file_path):
        # First load
        with open(file_path, "r") as stream:
            try:
                save_data = json.load(stream)
            except BaseException:
                message = (
                    "Could not load base data, are you sure you chose the "
                    "correct file? (.json)"
                )
                ShowMessageBox(message=message, title="Import")
                return
        # Build from Data
        if isinstance(save_data, list):
            save_data = {"Objects": save_data}
        self.deserialise_from_data(save_data)
        previous_objects = set(bpy.context.scene.objects)
        BUILDER.deserialise_from_data(save_data)
        station_reference.finish_transfer_import(bpy.context, save_data, previous_objects)

    def new_file(self):
        """Reset's the entire Blender scene to default.

        Note:
            * Removes all base information in the Blender properties.
            * Resets the build part order in the part builder.
            * Removes all items with ObjectID, PresetID and NMS_LIGHT properties.
            * Resets the room visibility switch to default.
        """
        BUILDER.clear_caches()

        # Remove basic blender default items.
        blend_utils.remove_object("Cube")
        blend_utils.remove_object("Light")
        blend_utils.remove_object("Camera")

        base_props = bpy.context.scene.nms_base_tool
        base_props.new_file()

        # Remove all no mans sky items from scene.
        # Deselect all
        bpy.ops.object.select_all(action="DESELECT")
        # Select NMS Items
        for bpy_object in bpy.data.objects:
            id_check = "ObjectID" in bpy_object
            preset_check = "PresetID" in bpy_object
            light_check = "NMS_LIGHT" in bpy_object
            rig_check = "rig_item" in bpy_object
            
            curve_check = "CurveID" in bpy_object
            group_check = "GroupID" in bpy_object
            if any([id_check, preset_check, light_check, rig_check, curve_check, group_check]):
                blend_utils.remove_object(bpy_object.name)

        station_reference.clear_reference(bpy.context.scene)
        bpy.context.scene.nms_save_data.station_key = ""
        bpy.context.scene.nms_save_data.station_transfer_reference = False
        # Reset room vis
        self.room_vis_switch = 0

    def toggle_room_visibility(self):
        """Cycle through room visibilities.

        Note:
            Visibility types are...
                0: Normal
                1: Ghosted
                2: Invisible
        """
        # Increment Room Vis
        if self.room_vis_switch < 2:
            self.room_vis_switch += 1
        else:
            self.room_vis_switch = 0

        # Set Shading.
        if self.room_vis_switch in [0, 1, 2]:
            bpy.context.space_data.shading.type = "SOLID"
            bpy.context.scene.render.engine = "BLENDER_EEVEE_NEXT"

        # Set Hide
        hidden = True
        if self.room_vis_switch in [0, 1]:
            hidden = False

        # Transparency.
        show_transparent = False
        if self.room_vis_switch in [1]:
            show_transparent = True

        # Hide Select.
        hide_select = False
        if self.room_vis_switch in [1]:
            hide_select = True

        # Iterate materials for transparency.
        # NOTE: Seems in 2.8 you can't set per object alpha toggling anymore :/
        for material in bpy.data.materials:
            if "transparent" in material.name:
                material.diffuse_color[3] = 0.07 if show_transparent else 1.0

        # Iterate object for selection.
        for ob in bpy.data.objects:
            if "ObjectID" in ob:
                if ob["ObjectID"] in GHOSTED_ITEMS:
                    is_preset = ob.get("belongs_to_preset", False)
                    # Normal
                    ob.hide_viewport = hidden
                    # ob.show_transparent = show_transparent
                    if not is_preset:
                        ob.hide_select = hide_select
                    ob.select_set(False)


    

    def apply_colour(self, colour_index=0, material=0):
        """Gives an item a new colour."""
        selected_objects = bpy.context.selected_objects
        if not selected_objects:
            ShowMessageBox(
                message="Make sure you have an item selected.", title="Apply Colour"
            )
            return {"FINISHED"}

        # Apply Colour Material.
        maeterial_index = int(material.split("_")[0])

        # A high res part is repainted in place, all of them in one pass - its
        # colour is four object properties, so it never needs a mesh of its own
        # and goes on sharing the one datablock for its ObjectID no matter how
        # many colours are on screen. Only the flat material fbx proxies still
        # need a copy per colour, which is what the ObjectID cache below is for.
        _materials_v2.recolour(
            [obj for obj in selected_objects if _materials_v2.is_high_res(obj)],
            colour_index=int(colour_index),
            material_index=int(maeterial_index),
        )

        unique_objects = {}
        for obj in selected_objects:
            if "ObjectID" in obj and not _materials_v2.is_high_res(obj):
                obj_id = obj["ObjectID"]
                if obj_id not in unique_objects:
                    obj.data = obj.data.copy()
                    _material.assign_material(obj, int(colour_index), int(maeterial_index))
                    unique_objects[obj_id] = obj

        for obj in selected_objects:
            # detect if object is nms curve
            if "has_linked_objects" in obj and curve.is_bezier_or_nurbs_path(obj):
                for child_obj in bpy.context.scene.objects:
                    if "curve_parent" in child_obj and child_obj["curve_parent"] == obj.name:
                        _material.assign_material(child_obj, int(colour_index), int(maeterial_index))
                        obj["dup_UserData"] = child_obj["UserData"]
            elif "GroupID" in obj:
                _material.assign_material(obj, int(colour_index), int(maeterial_index))
            # for any other object
            else :
                if "ObjectID" in obj:
                    obj_id = obj["ObjectID"]
                    if obj_id in unique_objects:
                        key = unique_objects[obj_id]
                        obj.data = key.data
                        obj["UserData"] = key["UserData"]

        # Refresh the viewport.
        bpy.ops.wm.redraw_timer(type="DRAW_WIN_SWAP", iterations=1)

    def apply_default_colour(self):
        """Gives an item a new colour."""
        selected_objects = bpy.context.selected_objects
        if not selected_objects:
            ShowMessageBox(
                message="Make sure you have an item selected.", title="Apply Colour"
            )
            return {"FINISHED"}

        # Apply Colour Material.
        for obj in selected_objects:
            index = 0
            # Figure out default index.
            object_id = obj["ObjectID"]
            if object_id:
                parent_folder = BUILDER.get_obj_parent_folder(object_id)
                if parent_folder:
                    if parent_folder == "alloy_structures":
                        index = 37
                    elif parent_folder == "timber_structures":
                        index = 45
                    elif parent_folder == "stone_structures":
                        index = 23
            _material.assign_default_material(obj, index=index)

        # Refresh the viewport.
        bpy.ops.wm.redraw_timer(type="DRAW_WIN_SWAP", iterations=1)
        
    # update materials of selected objects depending on material picked using picker
    def on_color_picked(self):
        target_object = self.color_picker
        if target_object is None:
            return 
        
        # extract user_data from target according to type of object
        target_userdata = None
        if "UserData" in target_object:
            target_userdata = target_object["UserData"]
        elif "has_linked_objects" in target_object:
            target_userdata = target_object["dup_UserData"]
            
        unique_keys = {}
        selected_objects = bpy.context.selected_objects

        # High res parts take the picked UserData straight onto the object and
        # keep the mesh they already share. Everything else is a flat material
        # proxy, so one object per ObjectID gets its own copy and the rest of
        # that id point at it - they all end up on the same UserData here, so
        # ObjectID alone is enough to key the cache.
        _materials_v2.recolour_from_user_data(
            [obj for obj in selected_objects if _materials_v2.is_high_res(obj)],
            target_userdata,
        )

        for obj in selected_objects:
            if "ObjectID" not in obj or _materials_v2.is_high_res(obj):
                continue
            obj_id = obj["ObjectID"]
            if obj_id not in unique_keys:
                obj.data = obj.data.copy()
                _material.restore_material(obj, target_userdata)
                unique_keys[obj_id] = obj

        if target_userdata is not None:

            for obj in selected_objects:
                if "has_linked_objects" in obj and curve.is_bezier_or_nurbs_path(obj):
                    curve.apply_color(obj, target_userdata)
                elif "ObjectID" in obj and not _materials_v2.is_high_res(obj):
                    obj_id = obj["ObjectID"]
                    key = unique_keys.get(obj_id, None)
                    if key is not None:
                        obj.data = key.data
                        obj["UserData"] = target_userdata
                    else:
                        _material.restore_material(obj, target_userdata)
        
        def clear_picker():
            self.color_picker = None
            return None
        
        # clear color picker value after operator execution finishes so that blender doesnt fire a warning popup
        bpy.app.timers.register(clear_picker, first_interval=0.0)
        

# UI ---

# File Buttons Panel ---
class NMS_PT_hero_panel(Panel):
    bl_idname = "NMS_PT_hero_panel"
    bl_label = "No Man's Sky Base Builder"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "No Mans Sky Base Builder"
    bl_context = "objectmode"

    @classmethod
    def poll(self, context):
        return True

    def draw(self, context):
        scene = context.scene
        nms_tool = scene.nms_main
        layout = self.layout
        
        pcoll = icons.get_icons_pscroll()
        plugin_icon = pcoll["plugin_icon"]
        pateron_icon = pcoll["patreon"]
        discord_icon = pcoll["discord"]
        steam_icon = pcoll["steam"]
        online_icon = pcoll["online"]
        
        icon_row = layout.row(align = True)
        icon_split = icon_row.split(factor = 0.35)
        icon_holder = icon_split.column(align = True)
        icon_holder.scale_y = 0.8
        icon_holder.template_icon(
            icon_value= plugin_icon.icon_id,
            scale=4
        )
        
        icon_text_column = icon_split.column(align = True)
        icon_text_column.scale_y = 0.6
        icon_text_column.label(text = "")
        icon_text_column.label(text = "No Man's Sky")
        icon_text_column.label(text = "Base and Corvette Builder")
        icon_text_column.separator()
        icon_text_sec = icon_text_column.column(align = True)
        icon_text_sec.alert = True
        #icon_text_sec.scale_y = 0.4
        icon_text_sec.label(text = "🐵 by DjMonkey")
        
        community_row = layout.row(align=True)
        communuity_box = community_row.box()
        third_column = communuity_box.column(align=True)
        third_column.label(text="Commmunity")
        third_column.operator("object.nms_visit_guides", icon_value = online_icon.icon_id)
        third_column.operator("object.nms_visit_community", icon_value = discord_icon.icon_id)
        
        support_box = community_row.box()
        fourth_column = support_box.column(align = True)
        fourth_column.label(text = "Support Me")
        fourth_column.operator("object.nms_visit_patreon", text = "Patreon", icon_value = pateron_icon.icon_id)
        fourth_column.operator("object.nms_visit_steam_games", text = "Steam Games", icon_value = steam_icon.icon_id)
        
        workspace_row = layout.row(align=True)
        workspace_box = workspace_row.box()
        workspace_column = workspace_box.column(align = False)
        workspace_label_row = workspace_column.row(align = True)
        workspace_label_row.label(text = "Workspace")
        
        workspace_column_2 = workspace_column.column(align = True)
        workspace_cleanup_row = workspace_column_2.row(align = True)
        workspace_cleanup_row.enabled = not nms_tool.is_workspace_cleaned
        workspace_cleanup_row.operator("object.nms_cleanup_workspace", text = "Simplify Blender Workspace", icon = "WORKSPACE")
        
        workspace_column_2.separator()
        workspace_column_2.operator("object.nms_workspace_settings", text = "Workspace Settings", icon = "SETTINGS")
        
        
        
        file_box = workspace_row.box()
        file_column = file_box.column(align = True)
            
        file_column.label(text="File")# icon = "COLLECTION_COLOR_04"
        file_column.operator("object.nms_new_file", icon="FILE_NEW")
        file_column.separator()
        file_column.operator("object.nms_save_data", icon="FILE_TICK")
        file_column.operator("object.nms_load_data", icon="FILE_FOLDER")


# File Buttons Panel ---
class NMS_PT_file_buttons_panel(Panel):
    bl_idname = "NMS_PT_file_buttons_panel"
    bl_label = "🔄 Import/Export"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "No Mans Sky Base Builder"
    bl_context = "objectmode"

    @classmethod
    def poll(self, context):
        return True

    def draw(self, context):
        
        layout = self.layout
        scene = context.scene
        nms_tool = scene.nms_main
        base_props = scene.nms_base_tool
        
        file_col = layout.column(align = True)
        file_row = file_col.row(align=True)
        file_box = file_row.box()
        first_column = file_box.column(align=True)
        first_column.scale_x = 0.5 if base_props.string_base_type == "PlayerShipBase" else 1.0
        first_column.label(text="Metadata", icon = "PROPERTIES")
        first_column.label(text="Base Name")
        first_column.prop(base_props, "string_base", text = "")
        first_row = first_column.row(align = True)
        first_row.enabled = False
        fc_1 = first_row.column(align = True)
        fc_1.label(text="Basetype")
        fc_1.prop(base_props, "string_base_type", text = "")
        
        if base_props.string_base_type == "PlayerShipBase":
            fc_2 = first_row.column(align = True)
            fc_2.label(text="Userdata")
            fc_2.prop(base_props, "string_userdata", text = "")

        clipboard_box = file_row.box()
        clipboard_box.label(text="Import & Export", icon = "IMPORT")
        second_column = clipboard_box.column(align=False)
        second_column.operator("object.nms_import_nms_data", icon="PASTEDOWN")
        second_column.separator()
        second_column.prop(nms_tool,"check_export_objects_only", text = "Objects only") 
        second_column.operator("object.nms_export_nms_data", icon="COPYDOWN")
            


class NMS_PT_station_transfer_reference(Panel):
    bl_idname = "NMS_PT_station_transfer_reference"
    bl_label = "Station Reference"
    bl_parent_id = "NMS_PT_file_buttons_panel"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "No Mans Sky Base Builder"
    bl_options = {'DEFAULT_CLOSED'}

    @classmethod
    def poll(cls, context):
        manager = context.scene.nms_save_data
        return bool(manager.station_transfer_reference and manager.station_key
                    and any(c.get(station_reference.TAG) for c in context.scene.collection.children))

    def draw(self, context):
        station_reference.draw(self.layout, context)


# Colour Panel ---
class NMS_PT_colour_panel(Panel):
    bl_idname = "NMS_PT_colour_panel"
    bl_label = "🎨 Colour & Materials"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "No Mans Sky Base Builder"
    bl_context = "objectmode"
    bl_options = {'DEFAULT_CLOSED'}

    @classmethod
    def poll(self, context):
        return True

    def draw(self, context):
        layout = self.layout
        scene = context.scene
        nms_tool = scene.nms_main
        colours = _material.get_colours_from_palette(nms_tool.material_switch)
        pcoll = preview_collections["main"]
        
        colour_area = layout.box().column(align=False)
        material_row = colour_area.row(align = True)
        
        material_row.prop(nms_tool, "material_switch",text = "Palette")
        colour_area.separator()
        grid = colour_area.grid_flow(columns=12, even_columns=True, align = True)
        grid.scale_x = 0.6
        grid.scale_y = 1.0
        for row in colours:
            index = row[3]
            name = row[5]
            colour = row[6]
            thumb = row[9]
            index, name, colour, thumb
            colour_icon = pcoll.get(os.path.splitext(thumb)[0], None)
            op = grid.operator(
                "object.nms_apply_colour",
                text="",
                icon_value=colour_icon.icon_id if colour_icon else 0,
            )
            op.colour_index = int(index)
            op.colour_name = name
            
        grid.prop(nms_tool,"color_picker", icon = "BLANK1", text = "")


# Colour Panel ---
class NMS_PT_logic_panel(Panel):
    bl_idname = "NMS_PT_logic_panel"
    bl_label = "⚡ Cables & Logic"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "No Mans Sky Base Builder"
    bl_context = "objectmode"
    bl_options = {'DEFAULT_CLOSED'}

    @classmethod
    def poll(self, context):
        return True

    def draw(self, context):
        layout = self.layout
        scene = context.scene
        nms_tool = scene.nms_main
        layout = self.layout
        
        box = layout.box()
        col = box.column(align = True)
        enum_row = col.row(align = True)
        enum_row.prop(nms_tool, "line_switch", text = "Cable")
        
        col.separator()
        col.label(text = "Operations")
        row = col.row(align = True)
        operations_col_1 = row.column(align = True)
        operations_col_1.operator("object.nms_point", icon="EMPTY_DATA")
        operations_col_1.operator("object.nms_divide", icon="LINCURVE")
        
        operations_col_2 = row.column(align = True)
        operations_col_2.operator("object.nms_connect", icon="PARTICLES")
        operations_col_2.operator("object.nms_split", icon="MOD_PHYSICS")
        
        operations_col_3 = row.column(align = True)
        operations_col_3.operator("object.nms_select_connected", icon="RESTRICT_SELECT_OFF")
        operations_col_3.operator("object.nms_select_floating", icon="RESTRICT_INSTANCED_ON")
        logic_col= box.column(align = True)
        logic_col.label(text="Logic")
        logic_row_1 = logic_col.row(align = True)
        logic_row_1.operator("object.nms_logic_button")
        logic_row_1.operator("object.nms_logic_wall_switch")
        logic_row_1.operator("object.nms_logic_prox_switch")
        logic_row_1.operator("object.nms_logic_inv_switch")
        logic_row_1.operator("object.nms_logic_auto_switch")
        logic_row_1.operator("object.nms_logic_floor_switch")
        logic_row_1.operator("object.nms_logic_beat_switch")


# Build Panel ---
class NMS_PT_build_panel(Panel):
    bl_idname = "NMS_PT_build_panel"
    bl_label = "🏗️ Parts & Prefabs"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "No Mans Sky Base Builder"
    bl_context = "objectmode"
    bl_options = {'DEFAULT_CLOSED'}

    @classmethod
    def poll(self, context):
        return True

    def draw(self, context):
        layout = self.layout
        scene = context.scene
        nms_tool = scene.nms_main
        
        build_column = layout.column(align = True)
        main_col = build_column.box().column(align = True)
        
        presets_box = main_col.column(align = True)
        presets_box.label(text = "Prefabs")
        preset_row = presets_box.row(align = True)
        preset_row.operator("object.nms_save_as_preset", icon="SCENE_DATA")
        preset_row.operator("object.nms_split_preset", icon="MOD_EXPLODE")
        row = presets_box.row(align=True)
        row.operator("object.nms_get_more_presets", icon="WORLD_DATA")
        row.operator("object.nms_open_preset_folder", icon="FILE_FOLDER")
        
        presets_v2_col = main_col
        presets_v2_col.label(text = "Grouping")
        presets_v2_row = presets_v2_col.row(align = True)
        presets_v2_row.operator("object.nms_group_objects", text = "Group", icon = "OUTLINER_OB_POINTCLOUD" )
        presets_v2_row.operator("object.nms_ungroup_objects", text = "Ungroup",  icon = "OUTLINER_DATA_POINTCLOUD")
        
class NMS_PT_nms_legacy_asset_browser(Panel):
    bl_label = "Legacy Asset Browser";  
    bl_idname = "NMS_PT_legacy_asset_browser"
    bl_space_type = 'VIEW_3D';   
    bl_region_type = 'UI';  
    bl_category = "No Mans Sky Base Builder"
    bl_parent_id  = "NMS_PT_build_panel"
    bl_context = "objectmode"
    bl_options = {'DEFAULT_CLOSED'}
    
    def draw(self, context):
        layout = self.layout
        
        scene = context.scene
        nms_tool = scene.nms_main
        
        lab_col = layout.box().column(align = True)
        lab_col.label(text = "Parts and Prefabs", icon = "ASSET_MANAGER")
        lab_col.row(align = True).prop(nms_tool, "enum_switch", expand=True)
        lab_col.template_list(
            "NMS_UL_actions_list",
            "compact",
            context.scene,
            "col",
            context.scene,
            "col_idx",
        )


class NMS_UL_actions_list(bpy.types.UIList):
    previous_layout = None

    def draw_item(
        self, context, layout, data, item, icon, active_data, active_propname
    ):
        self.use_filter_show = True
        if self.layout_type in {"DEFAULT", "COMPACT"}:
            # Add a category item if the title is specified.
            if item.title:
                layout.label(text=item.title)

            # Draw Parts
            if item.item_type == "parts" and item.description:
                all_parts = [x for x in item.description.split(",") if x]
                part_row = layout.column_flow(columns=3)
                for part in all_parts:
                    operator = part_row.operator(
                        "object.list_build_operator",
                        text=BUILDER.get_nice_name(part),
                    )
                    operator.part_id = part
                    operator.tooltip = (
                        f"Name: {BUILDER.get_nice_name(part)}\nID: ({part})"
                    )

            # Draw Presets
            if item.item_type == "presets":
                if item.description in preset.Preset.get_presets():
                    # Create Sub layuts
                    build_area = layout.split(factor=0.7)
                    operator = build_area.operator(
                        "object.list_build_operator", text=item.description
                    )
                    edit_area = build_area.split(factor=0.6)
                    edit_operator = edit_area.operator(
                        "object.list_edit_operator", text="Edit"
                    )
                    delete_operator = edit_area.operator(
                        "object.list_delete_operator", text="X"
                    )
                    operator.part_id = item.description
                    edit_operator.part_id = item.description
                    delete_operator.part_id = item.description
                    operator.tooltip = "Place this prefab in the scene."


class PartCollection(bpy.types.PropertyGroup):
    title: bpy.props.StringProperty()
    description: bpy.props.StringProperty()
    item_type: bpy.props.StringProperty()


def create_sublists(input_list, n=3):
    """Create a list of sub-lists with n elements."""
    if not input_list:
        return []
    total_list = [input_list[x : x + n] for x in range(0, len(input_list), n)]
    # Fill in any blanks.
    last_list = total_list[-1]
    while len(last_list) < n:
        last_list.append("")
    return total_list


def generate_ui_list_data(item_type="parts", pack=None):
    """Generate a list of Blender UI friendly data of categories and parts.

    When we retrieve presets we just want an item name.

    For parts I am doing a trick where I am grouping sets of 3 parts in order
    to make a grid in each UIList entry.

    Args:
        item_type (str): The type of items we want to retrieve
            options - "presets", "parts".

    Return:
        list: tuple (str, str): Label and Description of items for the UIList.
    """
    ui_list_data = []
    # Presets
    if "presets" in item_type:
        preset_categories = BUILDER.get_preset_categories()
        for category in preset_categories:
            presets = BUILDER.get_presets_from_category(category)
            if presets:
                ui_list_data.append((category, ""))
                for _preset in sorted(presets):
                    ui_list_data.append(("", _preset))
        # Uncategorized.
        presets = BUILDER.get_uncategorized_presets()
        if presets:
            ui_list_data.append(("Uncategorized Prefabs", ""))
            for _preset in sorted(presets):
                ui_list_data.append(("", _preset))
    else:
        # Packs/Parts
        for category in BUILDER.get_categories(pack=pack):
            ui_list_data.append((category, ""))
            category_parts = BUILDER.get_parts_from_category(category, pack=pack)
            category_parts = sorted(category_parts, key=BUILDER.get_nice_name)
            new_parts = create_sublists(category_parts)
            for part in new_parts:
                joined_list = ",".join(part)
                ui_list_data.append(("", joined_list))
    return ui_list_data


def refresh_ui_part_list(scene, item_type="parts", pack=None):
    """Refresh the UI List.

    Args:
        item_type: The type of items we want to retrieve.
            options - "presets", "parts".
    """
    # Clear the scene col.
    try:
        scene.col.clear()
    except:
        pass

    # Get part data based on
    ui_list_data = generate_ui_list_data(item_type=item_type, pack=pack)
    # Create items with labels and descriptions.
    for i, (label, description) in enumerate(ui_list_data, 1):
        item = scene.col.add()
        item.title = label.title().replace("_", " ")
        item.description = description
        item.item_type = item_type
        item.name = " ".join((str(i), label, description))


# Operators ---
# File Operators ---
class NewFile(bpy.types.Operator):
    bl_idname = "object.nms_new_file"
    bl_label = "New Base..."
    bl_options = {"REGISTER", "INTERNAL", "UNDO", "UNDO_GROUPED"}

    def execute(self, context):
        scene = context.scene
        nms_tool = scene.nms_main
        nms_tool.new_file()
        return {"FINISHED"}

    def invoke(self, context, event):
        return context.window_manager.invoke_confirm(self, event)


class SaveData(bpy.types.Operator):
    bl_idname = "object.nms_save_data"
    bl_label = "Save Base As..."
    filepath: bpy.props.StringProperty(subtype="FILE_PATH")

    def execute(self, context):
        scene = context.scene
        nms_tool = scene.nms_main
        nms_tool.save_nms_data(self.filepath)
        return {"FINISHED"}

    def invoke(self, context, event):
        context.window_manager.fileselect_add(self)
        return {"RUNNING_MODAL"}


class LoadData(bpy.types.Operator):
    bl_idname = "object.nms_load_data"
    bl_label = "Open Base..."
    bl_options = {"UNDO", "REGISTER"}
    filepath: bpy.props.StringProperty(subtype="FILE_PATH")

    def execute(self, context):
        scene = context.scene
        nms_tool = scene.nms_main
        nms_tool.load_nms_data(self.filepath)
        return {"FINISHED"}

    def invoke(self, context, event):
        context.window_manager.fileselect_add(self)
        return {"RUNNING_MODAL"}


class ImportData(bpy.types.Operator):
    bl_idname = "object.nms_import_nms_data"
    bl_label = "Import from Clipboard"
    bl_options = {"UNDO", "REGISTER"}

    def execute(self, context):
        scene = context.scene
        nms_tool = scene.nms_main
        nms_tool.import_nms_data()
        return {"FINISHED"}


class ExportData(bpy.types.Operator):
    bl_idname = "object.nms_export_nms_data"
    bl_label = "Export to Clipboard"

    def execute(self, context):
        scene = context.scene
        nms_tool = scene.nms_main
        objects_only = nms_tool.check_export_objects_only
        nms_tool.export_nms_data( objects_only )
        return {"FINISHED"}


class ExportObjectsData(bpy.types.Operator):
    bl_idname = "object.nms_export_nms_data_objects"
    bl_label = "Export to Clipboard (Objects Only)"

    def execute(self, context):
        scene = context.scene
        nms_tool = scene.nms_main
        nms_tool.export_nms_data(objects_only=True)
        return {"FINISHED"}
    
    
class SwitchWorkspace(bpy.types.Operator):
    """Switch to a simpler workspace"""
    bl_idname = "object.nms_cleanup_workspace"
    bl_label = "Switch workspace"

    def execute(self, context):
        scene = context.scene
        nms_tool = scene.nms_main
        nms_tool.is_workspace_cleaned = True
        workspace.cleanup_workspace(context)
        return {"FINISHED"}

class SaveAsPreset(bpy.types.Operator):
    """Save the current scene contents as a new Prefab"""

    bl_idname = "object.nms_save_as_preset"
    bl_label = "Save As Prefab"
    preset_name: bpy.props.StringProperty(name="Prefab Name")

    def execute(self, context):
        # Save Preset.
        BUILDER.save_preset_to_file(self.preset_name)
        # Refresh Preset List.
        scene = context.scene
        nms_tool = scene.nms_main
        if nms_tool.enum_switch == {"PRESETS"}:
            refresh_ui_part_list(scene, "presets")
        # Reset string variable.
        self.preset_name = ""
        return {"FINISHED"}

    def invoke(self, context, event):
        wm = context.window_manager
        return wm.invoke_props_dialog(self)


class LoadFancyUI(bpy.types.Operator):
    """Launch the standalone asset browser."""

    bl_idname = "object.nms_launch_asset_browser"
    bl_label = "Launch Asset Browser..."

    def execute(self, context):
        from .asset_browser import check_dependencies

        valid = check_dependencies.check_dependencies()
        if not valid:
            ShowMessageBox(
                message="Could not load Asset Browser. See Window > Toggle System Console for detials.",
                title="Asset Browser",
            )
            return {"FINISHED"}
        from .asset_browser import main as asset_browser_main

        asset_browser_main.load()
        return {"FINISHED"}


class PresetsMenu(bpy.types.Menu):
    bl_idname = "OBJECT_MT_nms_get_more_presets_menu"
    bl_label = "Get More Prefabs..."

    def draw(self, context):
        layout = self.layout
        layout.operator("object.nms_visit_prefab_community")
        layout.operator("object.nms_visit_github")


class GetMorePresets(bpy.types.Operator):
    """Load the No Man's Sky Prefabs web page to find more community prefabs."""

    bl_idname = "object.nms_get_more_presets"
    bl_label = "Get More Prefabs..."

    def execute(self, context):
        # Load web page.
        bpy.ops.wm.call_menu(name=PresetsMenu.bl_idname)
        return {"FINISHED"}


class VisitDiscord(bpy.types.Operator):
    """Launch the community discord URL."""

    bl_idname = "object.nms_visit_community"
    bl_label = "Discord"

    def execute(self, context):
        # Load web page.
        webbrowser.open_new("https://discord.gg/kpGVRKPn5W")
        return {"FINISHED"}


class VisitGuides(bpy.types.Operator):
    """Launch the dedicated online guides."""

    bl_idname = "object.nms_visit_guides"
    bl_label = "Online Guides"

    def execute(self, context):
        # Load web page.
        webbrowser.open_new(
            "https://djmonkey.uk/no-mans-sky-base-builder-blender/guides/"
        )
        return {"FINISHED"}


class VisitPatreon(bpy.types.Operator):
    """Open the Patreon page."""

    bl_idname = "object.nms_visit_patreon"
    bl_label = "Patreon"

    def execute(self, context):
        webbrowser.open_new("https://www.patreon.com/cw/djmonkeyuk/")
        return {"FINISHED"}


class VisitSteamGames(bpy.types.Operator):
    """Open DjMonkey's Steam developer page."""

    bl_idname = "object.nms_visit_steam_games"
    bl_label = "Wishlist/Buy my Steam games"

    def execute(self, context):
        webbrowser.open_new("https://store.steampowered.com/developer/djmonkey")
        return {"FINISHED"}


class VisitPrefabDiscord(bpy.types.Operator):
    """Launch the community discord URL."""

    bl_idname = "object.nms_visit_prefab_community"
    bl_label = "from the Community Discord..."

    def execute(self, context):
        # Load web page.
        webbrowser.open_new("https://discord.gg/EqCXaFcd7Y")
        return {"FINISHED"}


class VisitGitHubRepo(bpy.types.Operator):
    """Launch the GitHub Repo URL."""

    bl_idname = "object.nms_visit_github"
    bl_label = "from the GitHub Repository..."

    def execute(self, context):
        # Load web page.
        webbrowser.open_new("https://djmonkeyuk.github.io/nms-base-builder-presets/")
        return {"FINISHED"}


class OpenPresetFolder(bpy.types.Operator):
    """Open the folder containing your prefabs."""

    bl_idname = "object.nms_open_preset_folder"
    bl_label = "Open Prefab Folder"

    def execute(self, context):
        # Open the preset folder with the system's default file manager.
        if hasattr(os, "startfile"):
            # Windows
            os.startfile(PRESET_PATH)
        elif sys.platform == "darwin":
            # macOS
            subprocess.Popen(["open", PRESET_PATH])
        else:
            # Linux etc. (requires XDG tools)
            subprocess.call(["xdg-open", PRESET_PATH])
        return {"FINISHED"}


# List Operators ---
class ListBuildOperator(bpy.types.Operator):
    """Build the specified item."""

    bl_idname = "object.list_build_operator"
    bl_label = "Simple Object Operator"
    bl_options = {"UNDO", "REGISTER"}
    part_id: StringProperty()
    tooltip: StringProperty()

    @classmethod
    def description(cls, context, operator):
        return operator.tooltip

    def execute(self, context):
        # Get Selection
        selection = blend_utils.get_current_selection()

        # Build item
        if self.part_id in preset.Preset.get_presets():
            new_item = BUILDER.add_preset(self.part_id)
        else:
            new_item = builder_v2.add_part(self.part_id, builder_object=BUILDER)
            if hasattr(new_item, "build_rig"):
                new_item.build_rig()

        # Make this item the selected.
        new_item.select()

        # If there was a previous selection, snap the new item to it.
        if selection:
            builder_selection = BUILDER.get_builder_object_from_bpy_object(selection)
            if builder_selection:
                new_item.snap_to(builder_selection)
        return {"FINISHED"}


class ListEditOperator(bpy.types.Operator):
    """Edit the specified prefab."""

    bl_idname = "object.list_edit_operator"
    bl_label = "Edit Prefab"
    bl_options = {"UNDO", "REGISTER"}
    part_id: StringProperty()

    def execute(self, context):
        nms_tool = context.scene.nms_main
        if self.part_id in preset.Preset.get_presets():
            nms_tool.new_file()
            preset.Preset(
                preset_id=self.part_id,
                builder_object=BUILDER,
                create_control=False,
                apply_shader=False,
                build_rigs=True,
            )
            BUILDER.build_rigs()
            BUILDER.optimise_control_points()
        return {"FINISHED"}

    def invoke(self, context, event):
        return context.window_manager.invoke_confirm(self, event)


class ListDeleteOperator(bpy.types.Operator):
    """Delete the specified preset."""

    bl_idname = "object.list_delete_operator"
    bl_label = "Delete"
    part_id: StringProperty()

    def execute(self, context):
        scene = context.scene
        nms_tool = context.scene.nms_main
        if self.part_id in preset.Preset.get_presets():
            preset.Preset.delete_preset(self.part_id)
            if nms_tool.enum_switch == {"PRESETS"}:
                refresh_ui_part_list(scene, "presets")
        return {"FINISHED"}

    def invoke(self, context, event):
        return context.window_manager.invoke_confirm(self, event)





class ApplyColour(bpy.types.Operator):
    """Apply this colour to the selected part."""

    bl_idname = "object.nms_apply_colour"
    bl_label = ""
    bl_options = {"UNDO", "REGISTER"}
    
    colour_index: IntProperty(default=0)
    colour_name: bpy.props.StringProperty()

    def execute(self, context):
        scene = context.scene
        nms_tool = scene.nms_main
        material = nms_tool.material_switch
        nms_tool.apply_colour(colour_index=self.colour_index, material=material)
        return {"FINISHED"}
    
    @classmethod
    def description(cls, context, properties):
        return f"{properties.colour_name}"


class ApplyDefaultColour(bpy.types.Operator):
    """Revert the colour back to default on selected part."""

    bl_idname = "object.nms_apply_default_colour"
    bl_label = "Apply Default Colour"
    bl_options = {"UNDO", "REGISTER"}
    colour_index: IntProperty(default=0)

    def execute(self, context):
        scene = context.scene
        nms_tool = scene.nms_main
        nms_tool.apply_default_colour()
        return {"FINISHED"}



# Logic Operators ---
class Point(bpy.types.Operator):
    """Create a new point controller used to create logic cables.\nSelect this twice to create a cables between 2 points."""

    bl_idname = "object.nms_point"
    bl_label = "New Point"
    bl_options = {"UNDO", "REGISTER"}

    def execute(self, context):
        # Get current selection.
        selection = blend_utils.get_current_selection()

        # Don't stack multiple for multiple clicks
        if selection and context.scene.cursor.location == selection.location:
            return {"CANCELLED"}

        # Create a new point at the cursor.
        point = line.Line.create_point(BUILDER, name="ARBITRARY_POINT")
        point.location = context.scene.cursor.location

        # If another powerline was already selected, connect it
        if selection and "rig_item" in selection:
            line_object = selection.get("power_line", "U_POWERLINE").split(".")[0]
            power_line = BUILDER.add_part(line_object, build_rigs=False)
            # Create controls.
            power_line.build_rig(start=selection, end=point)

        # Now select the new point.
        blend_utils.select(point)
        return {"FINISHED"}


class Connect(bpy.types.Operator):
    """Form a cable between 2 objects that have cable connections."""

    bl_idname = "object.nms_connect"
    bl_label = "Connect"
    bl_options = {"UNDO", "REGISTER"}

    def execute(self, context):
        # Validate selection.
        selected_objects = [
            BUILDER.get_builder_object_from_bpy_object(o)
            for o in bpy.context.selected_objects
        ]
        selected_objects = [o for o in selected_objects if o.has_snap_point("POWER")]
        if len(selected_objects) < 2:
            message = "Make sure you have two or more electric points selected."
            ShowMessageBox(message=message, title="Connect")
            return {"FINISHED"}

        # Test this after selection for better error reporting
        if not bpy.context.active_object:
            message = "Make sure one object is the active object (shift select the object to connect everything to)."
            ShowMessageBox(message=message, title="Connect")
            return {"FINISHED"}

        active_object = BUILDER.get_builder_object_from_bpy_object(
            bpy.context.active_object
        )
        if not active_object.has_snap_point("POWER"):
            message = "Make sure the active object supports electrical connections."
            ShowMessageBox(message=message, title="Connect")
            return {"FINISHED"}

        for selected_object in selected_objects:
            if selected_object is active_object:
                continue
            if selected_object.name == active_object.name:
                continue
            # Build and perform connection.
            start_point, end_point = line.Line.generate_control_points(
                active_object, selected_object, BUILDER
            )
            if not start_point or not end_point:
                # should have been tested by filtering selected_objects above
                continue

            # Re-obtain objects
            start_point = blend_utils.get_item_by_name(start_point.name)
            end_point = blend_utils.get_item_by_name(end_point.name)

            # Create new power line.
            line_object_id = get_line_type_from_enum(context)

            # if "power_line" in start_point:
            #     line_object_id = start_point["power_line"].split(".")[0]
            power_line = BUILDER.add_part(line_object_id, build_rigs=False)
            # Create controls.
            power_line.build_rig(start=start_point, end=end_point)

        return {"FINISHED"}


class Divide(bpy.types.Operator):
    """Divide a selected cable into 2 cables."""

    bl_idname = "object.nms_divide"
    bl_label = "Divide"
    bl_options = {"UNDO", "REGISTER"}

    def execute(self, context):
        # Get Selected item.
        target = blend_utils.get_current_selection()

        # Validate
        invalid_message = "Make sure you have a powerline item selected."
        title = "Divide"
        if not target:
            ShowMessageBox(message=invalid_message, title=title)
            return {"FINISHED"}
        if "ObjectID" not in target:
            ShowMessageBox(message=invalid_message, title=title)
            return {"FINISHED"}
        valid_parts = ["U_POWERLINE", "U_PIPELINE", "U_PORTALLINE", "U_BYTEBEATLINE"]
        if target["ObjectID"] not in valid_parts:
            ShowMessageBox(message=invalid_message, title=title)
            return {"FINISHED"}

        # Perform split.
        power_line = BUILDER.get_builder_object_from_bpy_object(target)
        power_line.divide()
        return {"FINISHED"}


class Split(bpy.types.Operator):
    """Divide a selected cable into 2 cables with a gap between them."""

    bl_idname = "object.nms_split"
    bl_label = "Split"

    def execute(self, context):
        # Get Selected item.
        target = blend_utils.get_current_selection()

        # Validate
        invalid_message = "Make sure you have a powerline item selected."
        title = "Split"
        if not target:
            ShowMessageBox(message=invalid_message, title=title)
            return {"FINISHED"}
        if "ObjectID" not in target:
            ShowMessageBox(message=invalid_message, title=title)
            return {"FINISHED"}
        valid_parts = ["U_POWERLINE", "U_PIPELINE", "U_PORTALLINE", "U_BYTEBEATLINE"]
        if target["ObjectID"] not in valid_parts:
            ShowMessageBox(message=invalid_message, title=title)
            return {"FINISHED"}

        # Perform split.
        power_line = BUILDER.get_builder_object_from_bpy_object(target)
        power_line.split()
        return {"FINISHED"}


class SelectConnected(bpy.types.Operator):
    """Select all objects that are connected to the selected cable."""

    bl_idname = "object.nms_select_connected"
    bl_label = "Select Connected"
    bl_options = {"UNDO", "REGISTER"}

    def execute(self, context):
        selected_objects = [
            BUILDER.get_builder_object_from_bpy_object(o)
            for o in bpy.context.selected_objects
        ]

        newly_selected = set()
        for o in selected_objects:
            newly_selected.update(o.get_connected_snapped_objects("POWER"))
        for o in newly_selected:
            o.object.select_set(True)
        return {"FINISHED"}


class SelectFloating(bpy.types.Operator):
    """Select free-floating cable points."""

    bl_idname = "object.nms_select_floating"
    bl_label = "Select Floating"
    bl_options = {"UNDO", "REGISTER"}

    def execute(self, context):
        for part in BUILDER.get_all_parts(include_lines=True):
            if not "SnapID" in part:
                continue
            part = BUILDER.get_builder_object_from_bpy_object(part)
            if part.snap_id != "POWER_CONTROL":
                continue
            is_connected_to_object = False
            num_line_connections = 0
            for target in part.get_connected_snapped_objects(
                "POWER", include_lines=False
            ):
                if not hasattr(target, "start_control"):
                    is_connected_to_object = True
                    break
                else:
                    num_line_connections += 1

            if not is_connected_to_object and num_line_connections < 2:
                part.object.select_set(True)

        return {"FINISHED"}


class LogicButton(bpy.types.Operator):
    """Add a Logic Button to the scene."""

    bl_idname = "object.nms_logic_button"
    bl_label = "BTN"
    bl_options = {"UNDO", "REGISTER"}

    def execute(self, context):
        # Get Selected item.
        selection = blend_utils.get_current_selection()
        # Build button.
        button = builder_v2.add_part("U_SWITCHBUTTON", builder_object=BUILDER)
        # Snap to selection.
        if selection:
            selection = BUILDER.get_builder_object_from_bpy_object(selection)
            button.snap_to(selection)

        # Select new item.
        button.select()
        return {"FINISHED"}


class LogicWallSwitch(bpy.types.Operator):
    """Add a Logic Switch to the scene."""

    bl_idname = "object.nms_logic_wall_switch"
    bl_label = "SWITCH"
    bl_options = {"UNDO", "REGISTER"}

    def execute(self, context):
        # Get Selected item.
        selection = blend_utils.get_current_selection()
        button = builder_v2.add_part("U_SWITCHWALL", builder_object=BUILDER)
        # Snap to selection.
        if selection:
            selection = BUILDER.get_builder_object_from_bpy_object(selection)
            button.snap_to(selection)
        # Select new item.
        button.select()
        return {"FINISHED"}


class LogicProxSwitch(bpy.types.Operator):
    """Add a Logic Proximity Sensor to the scene."""

    bl_idname = "object.nms_logic_prox_switch"
    bl_label = "PROX"
    bl_options = {"UNDO", "REGISTER"}

    def execute(self, context):
        # Get Selected item.
        selection = blend_utils.get_current_selection()
        button = builder_v2.add_part("U_SWITCHPROX", builder_object=BUILDER)
        # Snap to selection.
        if selection:
            selection = BUILDER.get_builder_object_from_bpy_object(selection)
            button.snap_to(selection)
        # Select new item.
        button.select()
        return {"FINISHED"}


class LogicInvSwitch(bpy.types.Operator):
    """Add a Logic Inverter to the scene."""

    bl_idname = "object.nms_logic_inv_switch"
    bl_label = "INV"
    bl_options = {"UNDO", "REGISTER"}

    def execute(self, context):
        # Get Selected item.
        selection = blend_utils.get_current_selection()
        button = builder_v2.add_part("U_TRANSISTOR1", builder_object=BUILDER)
        # Snap to selection.
        if selection:
            selection = BUILDER.get_builder_object_from_bpy_object(selection)
            button.snap_to(selection)
        # Select new item.
        button.select()
        return {"FINISHED"}


class LogicAutoSwitch(bpy.types.Operator):
    """Add a Logic Auto to the scene."""

    bl_idname = "object.nms_logic_auto_switch"
    bl_label = "AUTO"
    bl_options = {"UNDO", "REGISTER"}

    def execute(self, context):
        # Get Selected item.
        selection = blend_utils.get_current_selection()
        button = builder_v2.add_part("U_TRANSISTOR2", builder_object=BUILDER)
        # Snap to selection.
        if selection:
            selection = BUILDER.get_builder_object_from_bpy_object(selection)
            button.snap_to(selection)
        # Select new item.
        button.select()
        return {"FINISHED"}


class LogicFloorSwitch(bpy.types.Operator):
    """Add a Logic Floor Switch to the scene."""

    bl_idname = "object.nms_logic_floor_switch"
    bl_label = "FLOOR"
    bl_options = {"UNDO", "REGISTER"}

    def execute(self, context):
        # Get Selected item.
        selection = blend_utils.get_current_selection()
        button = builder_v2.add_part("U_SWITCHPRESS", builder_object=BUILDER)
        # Snap to selection.
        if selection:
            selection = BUILDER.get_builder_object_from_bpy_object(selection)
            button.snap_to(selection)
        # Select new item.
        button.select()
        return {"FINISHED"}


class LogicBeatSwitch(bpy.types.Operator):
    """Add a Logic ByteBeat switch to the scene."""

    bl_idname = "object.nms_logic_beat_switch"
    bl_label = "BEAT"
    bl_options = {"UNDO", "REGISTER"}

    def execute(self, context):
        # Get Selected item.
        selection = blend_utils.get_current_selection()
        button = builder_v2.add_part("BYTEBEATSWITCH", builder_object=BUILDER)
        # Snap to selection.
        if selection:
            selection = BUILDER.get_builder_object_from_bpy_object(selection)
            button.snap_to(selection)
        # Select new item.
        button.select()
        return {"FINISHED"}
    

class SplitPreset(bpy.types.Operator):
    """Split the selected prefab into individual parts"""

    bl_idname = "object.nms_split_preset"
    bl_label = "Split Prefab to Parts"

    def execute(self, context):
        from . import preset as _preset_mod

        # Find the selected preset, or any preset in the scene
        selected = [o for o in context.selected_objects if "PresetID" in o]
        if not selected:
            selected = [o for o in bpy.data.objects if "PresetID" in o]
            
        if not selected:
            self.report({"WARNING"}, "No preset found to split")
            return {"CANCELLED"}

        total = 0
        names = []
        for ctrl in selected:
            pid = ctrl.get("PresetID")
            n = _preset_mod.Preset.split_to_parts(pid)
            total += n
            names.append(pid)

        # Clear builder caches
        BUILDER.clear_caches()
        
        self.report({"INFO"}, f"Prefabs split: {len(names)}, parts: {total}")
        return {"FINISHED"}
    
class GroupObjects(bpy.types.Operator):
    """Group parts together into"""

    bl_idname = "object.nms_group_objects"
    bl_label = "Group Objects together"
    bl_options = {'REGISTER', 'UNDO'}

    origin_type: bpy.props.EnumProperty(
        name="Select Origin",
        description="Choose how to group the objects",
        items=[
            ("median", "Median", "Use median of obejcts in viewport as origin of Group",  "PIVOT_MEDIAN", 0),
            ("active", "Active Object", "Use active object in viewport as origin of Group", "CON_PIVOT", 1),
            ("cursor", "3D Cursor", "Use 3D cursor in viewport as origin of Group",  "CURSOR", 2)
            
        ],
        default='active',
    )
    
    def invoke(self, context, event):
        
        selected_objects = context.selected_objects
        if not selected_objects or len(selected_objects) < 2:
            message = "Please select atleast two objects"
            ShowMessageBox(
                message,
                title="Group Objects",
                icon = "WARNING_LARGE"
            )
            return {"CANCELLED"}
        
        return context.window_manager.invoke_props_dialog(
            self,
            title="Group Objects",
            confirm_text="Group"
        )

    def execute(self, context):
        selected_objects = context.selected_objects
        
        # Grab the full matrix instead of just the location
        if self.origin_type == "active" and context.active_object:
            target_matrix = context.active_object.matrix_world.copy()
        elif self.origin_type == "cursor" and context.scene.cursor:
            target_matrix = context.scene.cursor.matrix.copy()
        else :
            target_matrix = None
            
        # Pass the matrix to our group function
        if not selected_objects or len(selected_objects) < 2:
            return {"CANCELLED"}
        
        merged_object = group.Group.group_objects(selected_objects, target_matrix)
        if merged_object is not None:
            self.report({'INFO'}, f"{len(selected_objects)} objects merged into {merged_object.name}")
        
        return {"FINISHED"}

    def draw(self, context):
        layout = self.layout
        layout.label(text = "Select Origin of Merged Object", icon = "OUTLINER_OB_POINTCLOUD")
        type_row = layout.row(align=True)
        type_row.prop(self, "origin_type", expand = True)
        layout.label(text="This point will act as transformations pivot point")
    
class UngroupObjects(bpy.types.Operator):
    """Ungroup Parts"""

    bl_idname = "object.nms_ungroup_objects"
    bl_label = "Ungroup Objects"

    def execute(self, context):
        selected_objects = bpy.context.selected_objects
        restored_obejcts_collection = []
        for item in selected_objects:
            if "GroupID" in item:
                restored_obejcts = group.Group.ungroup_objects(BUILDER,item)
                if restored_obejcts is not None:
                    restored_obejcts_collection += restored_obejcts
        if len(restored_obejcts_collection) > 0:
            self.report({'INFO'}, f"ungrouped into {len(restored_obejcts_collection)} objects")
            blend_utils.select(restored_obejcts_collection)
        return {"FINISHED"}
    
class WorkspaceSettings(bpy.types.Operator):
    """Some settings related to workspace"""

    bl_idname = "object.nms_workspace_settings"
    bl_label = "Workspace Settings"
    
    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self)
    
    def draw(self, context):
        prefs = context.preferences.addons[ADDON_ID].preferences
        layout = self.layout
        column = layout.column(align = True)
        column.label(text = "Part Count")
        column.prop(prefs,"nms_check_show_part_count")
        part_cout_pos_row = column.row(align = True)
        part_cout_pos_row.enabled = prefs.nms_check_show_part_count
        part_cout_pos_row.label(text = "Position :", icon = "BLANK1")
        part_cout_pos_row.prop(prefs,"nms_part_count_position", expand = True)
        
        column.separator()
        column.separator()
        column.label(text = "Active_object properties")
        column.prop(prefs,"nms_check_show_active_object_properties")
        prop_row = column.row(align = True)
        prop_row.enabled = prefs.nms_check_show_active_object_properties
        prop_row.label(text = "Position :", icon = "BLANK1")
        prop_row.prop(prefs,"nms_active_object_properties_position", expand = True)
        
        column.separator()
    
    def execute(self, context):
        return {"FINISHED"}
    
    

# Track objects
known_curve_names = set()
last_active = None
first_update_skipped = False

# To reset toggle button of save editor and initialize curve registry
@persistent
def reset_plugin_state(dummy):
    _material.optimise_materials()
    
    # collect all curves when a blend file is reopened
    global known_curve_names
    known_curves = set( obj for obj in bpy.context.scene.objects  if obj.type == 'CURVE' and obj.get("has_linked_objects", False) )
    known_curve_names = set( obj.name for obj in known_curves )
    # one scene pass shared by every curve, rather than one per curve
    curve.update_curves(known_curves, children_by_curve=curve.get_curve_children_map())
    
    
    # reset save editor's state to closed
    for scene in bpy.data.scenes:
        save_data = scene.nms_save_data
        save_data.check_plugin_enabled = False
        
        asset_browser = scene.nms_asset_browser
        asset_browser.initialise_asset_browser()

            
# Whenever a curve is modified, automatically update whatever child objects that are associated with that curve.
@persistent
def udpates_handler(scene, depsgraph):
    
    global known_curve_names
    global last_active
    
    
    active_object = bpy.context.view_layer.objects.active

    # keep track of active object to display or hide additional options related to that object
    # only continue when active object actually changes
    if active_object is not None and active_object != last_active:
        properties = scene.nms_properties
        properties.set_active_obect(active_object)
        last_active = active_object

    # Collect curves that have recieved updates by user
    updated_curve_names = set()
    for update in depsgraph.updates:
        if isinstance(update.id, bpy.types.Object):
            # validate each object
            orig_obj = bpy.data.objects.get(update.id.name)
            # the object can already be gone by the time we look it up
            if orig_obj is None:
                continue
            if orig_obj.type == 'CURVE' and curve.Curve.PROP_CURVE_ID in orig_obj:
                updated_curve_names.add(orig_obj.name)
            elif curve.Curve.PROP_CURVE_PARENT in orig_obj:
                parent_curve_name = orig_obj[curve.Curve.PROP_CURVE_PARENT]
                parent_curve = bpy.context.scene.objects.get(parent_curve_name,None)
                if parent_curve is not None and not parent_curve.get(curve.Curve.PROP_PARENT_SELECTED,True):
                    #store base scale of object 
                    orig_obj[curve.Curve.PROP_BASE_SCALE] = curve.calculate_base_scale(parent_curve, orig_obj)
    
    # identify new curves
    new_curve_names_detected = updated_curve_names - known_curve_names
                    
    # Detect Shift+d duplication of curves and Handle syncing
    if new_curve_names_detected and known_curve_names:
        for new_curve_name in new_curve_names_detected:
            # if two curves have equal Curve.PROP_CURVE_ID, that means they have been duplicated using shift+d
            # we need to duplicate objects in similar way on new curve too
            try:
                new_curve = bpy.context.scene.objects.get(new_curve_name,None)
                if new_curve is None:
                    continue
                new_uuid = new_curve.get(curve.Curve.PROP_CURVE_ID)
                # Look for curves that have same unique_id as new curve
                # if a duplciate unique_id found, new curve must be duplicate of that curve
                for curve_name in known_curve_names:
                    matching_curve = bpy.context.scene.objects.get(curve_name,None)
                    if matching_curve is not None and matching_curve.get(curve.Curve.PROP_CURVE_ID) == new_uuid and matching_curve.name != new_curve.name:
                        curve.sync_curves(new_curve, matching_curve)
                        break
            except ReferenceError as error:
                print("Reference error :", error)
                continue
    
    # Work out whether there is anything to rebuild at all.
    #
    # This used to rebuild the active curve on EVERY depsgraph update - moving
    # the camera, changing a selection, editing an unrelated part - and each
    # rebuild scans the whole scene looking for that curve's children. On a
    # 5000 part base that is 3.3 ms of work per update against a 16 ms frame,
    # which is what made big bases feel sticky. Now it only runs when the curve
    # itself changed, or when the count/radius sliders moved.
    properties = scene.nms_properties
    sliders_moved = (
        properties.active_curve_number_of_objects != properties.prev_curve_number_of_objects
        or properties.active_curve_radius_multiplier != properties.prev_curve_radius_multiplier
    )

    curves_to_update = []
    if last_active is not None:
        if sliders_moved:
            # the sliders apply to everything selected, so all of them rebuild
            selected = getattr(bpy.context, "selected_objects", None) or []
            curves_to_update = [
                obj for obj in selected if curve.Curve.PROP_CURVE_ID in obj
            ]
        elif updated_curve_names:
            # otherwise only the curves the depsgraph says actually moved
            scene_objects = scene.objects
            curves_to_update = [
                obj for obj in (scene_objects.get(name) for name in updated_curve_names)
                if obj is not None
            ]

        if (active_object is not None
                and curve.Curve.PROP_CURVE_ID in active_object
                and (sliders_moved or active_object.name in updated_curve_names)
                and active_object not in curves_to_update):
            curves_to_update.append(active_object)

    if curves_to_update:
        # one pass over the scene grouping every follower by the curve it is on,
        # instead of one full scan per curve inside update_curve_children
        curve.update_curves(
            curves_to_update, children_by_curve=curve.get_curve_children_map()
        )


    
    dead_curve_names = set()
    # check for deleted curve in know curves
    for curve_name in known_curve_names:
        if bpy.context.scene.objects.get(curve_name,None) is None:
            dead_curve_names.add(curve_name)
    # delete dead curves
    if dead_curve_names:
        known_curve_names.difference_update(dead_curve_names)
        # one batch rather than a remove() per orphan - each of those re-syncs the
        # whole scene, which is ~4 ms a piece once a base gets big
        orphans = [
            obj for obj in curve.get_follower_objects()
            if obj.get(curve.Curve.PROP_CURVE_PARENT) in dead_curve_names
        ]
        if orphans:
            bpy.data.batch_remove(orphans)
        
    # Sync back down to the global tracking set 
    known_curve_names |= updated_curve_names  
                

preview_collections = {}

# Plugin Registration ---

classes = (
    NMSMain,
    NMSBaseProperties,
    
    Point,
    Connect,
    Divide,
    Split,
    SelectConnected,
    SelectFloating,
    LogicButton,
    LogicWallSwitch,
    LogicProxSwitch,
    LogicInvSwitch,
    LogicAutoSwitch,
    LogicFloorSwitch,
    LogicBeatSwitch,
    ApplyColour,
    ApplyDefaultColour,
    SaveAsPreset,
    LoadFancyUI,
    GetMorePresets,
    PresetsMenu,
    VisitDiscord,
    VisitGuides,
    VisitPatreon,
    VisitSteamGames,
    VisitPrefabDiscord,
    VisitGitHubRepo,
    OpenPresetFolder,
    NewFile,
    SaveData,
    LoadData,
    ExportData,
    ExportObjectsData,
    ImportData,
    PartCollection,
    ListDeleteOperator,
    ListEditOperator,
    ListBuildOperator,
    SaveManager,
    BuildTool,
    Properties,
    BatchTool,
    WorkspaceSettings,
    NMSCategoryOrderItem,
    AssetBrowser,

    NMS_UL_actions_list,
    NMS_PT_hero_panel,
    NMS_PT_file_buttons_panel,
    NMS_PT_station_transfer_reference,
    NMS_PT_save_editor_panel,
    NMS_PT_transformation_panel,
    NMS_PT_colour_panel,
    NMS_PT_logic_panel,
    NMS_PT_tools_panel,
    NMS_PT_batch_tools_panel,
    NMS_PT_build_panel,
    NMS_PT_nms_legacy_asset_browser,
    NMSAddonPreferences,
    
    SwitchWorkspace,
    SplitPreset,
    
    GroupObjects,
    UngroupObjects
)

classes = classes + asset_browser_presentation.classes + base_builder_menu.classes 

classes = classes  + save_editor_operators.classes + station_reference.classes + build_tool_operators.classes + batch_tool_operators.classes + prooperties_operators.classes + asset_browser_operators.classes + base_builder_menu_operators.classes



def register():

    # Ensure User data folder structure exists
    for data_path in [USER_PATH, PRESET_PATH]:
        if not os.path.exists(data_path):
            os.makedirs(data_path)

    # Load Icons.
    pcoll = bpy.utils.previews.new()

    # Load Colours
    colours_dir = os.path.join(os.path.dirname(__file__), "images", "colours")
    colour_files = os.listdir(colours_dir)
    for colour_file in colour_files:
        file_name = os.path.splitext(colour_file)[0]
        pcoll.load(
            file_name,
            os.path.join(colours_dir, colour_file),
            "IMAGE",
        )
        
    preview_collections["main"] = pcoll
    icons.register_icons()
    
    # Register Plugin
    for _class in classes:
        bpy.utils.register_class(_class)
    bpy.types.Scene.nms_main = PointerProperty(type=NMSMain)
    bpy.types.Scene.nms_base_tool = PointerProperty(type = NMSBaseProperties)
    bpy.types.Scene.col = bpy.props.CollectionProperty(type=PartCollection)
    bpy.types.Scene.col_idx = bpy.props.IntProperty(default=0)
    bpy.types.Scene.nms_save_data = bpy.props.PointerProperty(type=SaveManager)
    bpy.types.Scene.nms_build_tool = bpy.props.PointerProperty(type=BuildTool)
    bpy.types.Scene.nms_properties = bpy.props.PointerProperty(type=Properties)
    bpy.types.Scene.nms_batch_tool = bpy.props.PointerProperty(type=BatchTool)
    bpy.types.Scene.nms_asset_browser = bpy.props.PointerProperty(type=AssetBrowser)

    # Puts the "Base Builder" menu in the 3D viewport header. The menu classes
    # themselves are registered with everything else, above.
    base_builder_menu.register_menu()
    
    if reset_plugin_state not in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.append(reset_plugin_state)
    
    if udpates_handler not in bpy.app.handlers.depsgraph_update_post:
        bpy.app.handlers.depsgraph_update_post.append(udpates_handler)
    
    bpy.app.timers.register(viewport_overlay.register_draw, first_interval=0.01)

def unregister():
    for pcoll in preview_collections.values():
        bpy.utils.previews.remove(pcoll)
    preview_collections.clear()
    icons.unregister_icons()

    # Blender's own toolbar was patched by the workspace cleanup, so hand it
    # back before we go.
    workspace.restore_viewport_tools()

    # Taken out of the header before its classes go, so nothing is left drawing
    # a menu that no longer exists.
    base_builder_menu.unregister_menu()

    for _class in reversed(classes):
        bpy.utils.unregister_class(_class)
        
    del bpy.types.Scene.nms_main
    del bpy.types.Scene.nms_base_tool
    del bpy.types.Scene.nms_save_data
    del bpy.types.Scene.nms_build_tool
    del bpy.types.Scene.nms_properties
    del bpy.types.Scene.nms_batch_tool
    del bpy.types.Scene.nms_asset_browser
    
    if reset_plugin_state in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.remove(reset_plugin_state)
        
    if udpates_handler in bpy.app.handlers.depsgraph_update_post:
        bpy.app.handlers.depsgraph_update_post.remove(udpates_handler)
    
    viewport_overlay.unregister_draw()


if __name__ == "__main__":
    register()
