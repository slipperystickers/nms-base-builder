from .reload_support import prepare_package as _prepare_package
_prepare_package(globals())

from .furby_errors import report_error
import json
import base64
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

from . import builder, icons, part, preset, group, builder_v2, viewport_overlay, undo_guard, interchange, project_recovery, progress_ui, compatibility, wasd_navigation
from . import build_metadata, build_metadata_ui
from .base_properties import NMSBaseProperties
from .addon_preferences import NMSAddonPreferences
from .part_overrides import line
from .save_editor import save_editor_operators, save_editor_utils, station_reference
from .save_editor.save_editor_presentation import NMS_PT_save_editor_panel, BBE_OT_backup_settings, BBE_OT_refresh_save_counts, BBE_OT_save_refresh_notice
from .save_editor.save_manager import SaveManager
from .save_editor import save_manager

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
from .utils import userdata as _userdata
from .utils import python as python_utils
from .utils import workspace



FILE_PATH = os.path.dirname(os.path.realpath(__file__))
USER_PATH = os.path.join(os.path.expanduser("~"), "NoMansSkyBaseBuilder")
PRESET_PATH = os.path.join(USER_PATH, "presets")
ASSET_BROWSER_PATH = os.path.join(FILE_PATH, "asset_browser")

BUILDER = builder.get_builder()
GHOSTED_JSON = os.path.join(FILE_PATH, "resources", "ghosted.json")
ghosted_reference = python_utils.load_dictionary(GHOSTED_JSON)
GHOSTED_ITEMS = ghosted_reference["GHOSTED"]
nice_name_dictionary = dictionary.get_nice_names_diictionary()

ADDON_ID = __package__


def _clear_build_source(scene):
    # Keep the old Text block for Blender's undo history, but stop saving an
    # orphaned package once no scene refers to it.
    old_name = scene.get('bbe_build_source_text')
    block = bpy.data.texts.get(old_name) if old_name else None
    if block and not any(other != scene and other.get('bbe_build_source_text') == old_name
                         for other in bpy.data.scenes):
        block.use_fake_user = False
    for key in ('bbe_build_source_text', 'bbe_build_source_suffix', 'bbe_ship_source_error', 'bbe_ship_export_origin'):
        if key in scene:
            del scene[key]


def _store_build_source(scene, build_file, suffix):
    from uuid import uuid4
    block = bpy.data.texts.new('BBE build source ' + uuid4().hex[:10])
    block.write(base64.b64encode(build_file.source_bytes).decode('ascii'))
    block.use_fake_user = True  # retain package metadata across .blend saves
    scene['bbe_build_source_text'] = block.name
    scene['bbe_build_source_suffix'] = suffix.lower()


def _restore_build_source(scene):
    name = scene.get('bbe_build_source_text')
    block = bpy.data.texts.get(name) if name else None
    if block is None:
        return None
    try:
        raw = base64.b64decode(block.as_string(), validate=True)
        return interchange.BuildFile.from_bytes(raw, scene['bbe_build_source_suffix'])
    except (KeyError, ValueError) as exc:
        raise ValueError('The source build stored in this .blend is damaged; import the original file again') from exc
# Use the installed manifest for both sidebar and updater version labels.
import tomllib
with open(Path(FILE_PATH) / "blender_manifest.toml", "rb") as _manifest_stream:
    ADDON_VERSION = tomllib.load(_manifest_stream)["version"]


# Setting Support Methods ---
def ShowMessageBox(message="", title="Message Box", icon="INFO"):
    def draw(self, context):
        self.layout.label(text=message)

    bpy.context.window_manager.popup_menu(draw, title=title, icon=icon)


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

    def serialise(self, get_presets=False, objects_only=False, progress=None,
                  progress_range=(.02, .70)):
        """Export the data in the blender scene to NMS compatible data.

        This will slot the data into the clip-board so you can easy copy
        and paste data back and forth between the tool.
        """
        
        # Capture Individual Objects
        objects_data = BUILDER.serialise(get_presets=get_presets, progress=progress,
                                         progress_range=progress_range)
        if objects_only:
            return objects_data["Objects"]
        
        base_props = bpy.context.scene.nms_base_tool
        data = base_props.serialise()
        
        data.update(objects_data)
        return data

    # Import and Export Methods ---
    def import_nms_data(self, clipboard_data=None):
        """Import and build a base based on the contents of user clipboard.

        The clipboard should contain a copy of the base data found in the
        No Man's Sky Save Editor.
        """
        # Read clipboard data.
        if clipboard_data is None:
            clipboard_data = bpy.context.window_manager.clipboard
        try:
            with progress_ui.Activity('Reading clipboard build') as progress:
                progress.update(.1, 'Parsing parts')
                nms_import_data = json.loads(clipboard_data)
                progress.update(1.0, 'Importing models')
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
        # An Objects-only paste replaces the parts, not the destination build's
        # identity. In particular, keep the Corvette package stored in the
        # .blend so the new parts can still be exported as a .nmsship.
        parts_only = (isinstance(nms_import_data, dict)
                      and 'Objects' in nms_import_data
                      and 'BaseType' not in nms_import_data)
        if parts_only:
            scene = bpy.context.scene
            previous_metadata = scene.nms_base_tool.serialise()
            previous_owner_save = scene.nms_base_tool.metadata_owner_to_save
            previous_owner_reviewed = scene.nms_base_tool.metadata_owner_reviewed
            source_name = scene.get('bbe_build_source_text')
            source_suffix = scene.get('bbe_build_source_suffix')
            source_error = scene.get('bbe_ship_source_error')
        self.deserialise_from_data(nms_import_data)
        if parts_only:
            scene.nms_base_tool.deserialise_from_data(previous_metadata)
            scene.nms_base_tool.metadata_owner_to_save = previous_owner_save
            scene.nms_base_tool.metadata_owner_reviewed = previous_owner_reviewed
            source_block = bpy.data.texts.get(source_name) if source_name else None
            if source_block and source_suffix:
                source_block.use_fake_user = True
                scene['bbe_build_source_text'] = source_block.name
                scene['bbe_build_source_suffix'] = source_suffix
            if source_error:
                scene['bbe_ship_source_error'] = source_error
        previous_objects = set(bpy.context.scene.objects)
        builder_v2.deserialise_from_data(nms_import_data)
        station_reference.finish_transfer_import(bpy.context, nms_import_data, previous_objects)
        #BUILDER.deserialise_from_data(nms_import_data)

    def export_nms_data(self, objects_only=False):
        """Generate data and place it into the user's clipboard.

        This generates a flat set of individual base parts for NMS to read.
        All preset information is lost in this process.
        """
        with progress_ui.Activity('Exporting to clipboard') as progress:
            data = self.serialise(objects_only=objects_only, progress=progress,
                                  progress_range=(.02, .82))
            progress.update(.86, 'Encoding clipboard data')
            bpy.context.window_manager.clipboard = json.dumps(data, indent=4)
            progress.update(1.0, 'Clipboard ready')

    def import_build_file(self, file_path, parts_base_type='HomePlanetBase'):
        """Open a standalone build without touching any game save."""
        path = Path(file_path)
        with progress_ui.Activity('Opening build file') as progress:
            progress.update(.1, f'Reading {path.name}')
            build_file = interchange.BuildFile.read(path)
            progress.update(1.0, 'Importing models')
        data = build_file.import_document(parts_base_type, path.stem)
        self.deserialise_from_data(data)
        previous_objects = set(bpy.context.scene.objects)
        builder_v2.deserialise_from_data(data)
        station_reference.finish_transfer_import(bpy.context, data, previous_objects)
        _store_build_source(bpy.context.scene, build_file, path.suffix)
        return len(build_file.objects), build_file.kind

    def export_base_file(self, file_path):
        with progress_ui.Activity('Exporting base file') as progress:
            return self._export_base_file(file_path, progress)

    def _export_base_file(self, file_path, progress):
        data = self.serialise(progress=progress, progress_range=(.02, .76))
        base_type = data.get('BaseType', {}).get('PersistentBaseTypes')
        if base_type == 'PlayerShipBase':
            raise ValueError('Corvettes use Export Ship Package or Export Build JSON')
        if base_type not in interchange.BASE_TYPES:
            raise ValueError('Choose a supported base type in I/O metadata first')
        progress.update(.80, 'Preparing base package')
        source = _restore_build_source(bpy.context.scene)
        if source and source.kind == 'base':
            data = source.with_scene(data)
        data.pop('Presets', None)  # Prefabs are a BBE project feature, not a base-file payload.
        interchange.BuildFile.from_bytes(interchange._encode(data), '.nmsbase')
        progress.update(.92, 'Writing base file')
        interchange.atomic_write(file_path, interchange._encode(data))
        progress.update(1.0, 'Base file ready')
        return len(data['Objects']), base_type

    def export_ship_file(self, file_path, template_path='', use_selected_save=False, warnings=None):
        with progress_ui.Activity('Exporting Corvette package') as progress:
            return self._export_ship_file(file_path, template_path, progress, use_selected_save, warnings)

    def _export_ship_file(self, file_path, template_path, progress, use_selected_save=False, warnings=None):
        data = self.serialise(objects_only=True, progress=progress,
                              progress_range=(.02, .72))
        progress.update(.76, 'Reading ship package metadata')
        from .save_editor import ship_package
        source = (ship_package.selected_save_source(bpy.context) if use_selected_save
                  else _restore_build_source(bpy.context.scene))
        if source is None or source.kind != 'ship':
            if template_path:
                source = interchange.BuildFile.read(template_path)
            else:
                if bpy.context.scene.get('bbe_build_source_suffix') == '.nmsship':
                    raise ValueError('The imported ship metadata is unavailable. Re-import its .nmsship or choose a complete ship template to preserve its inventory and stats.')
                source = ship_package.new_corvette_source()
                if warnings is not None:
                    warnings.append('Used new Corvette defaults for class, inventory, technology and appearance.')
        if source.kind != 'ship':
            raise ValueError('Ship template must be a complete .nmsship package')
        payload = source.ship_bytes(data, bpy.context.scene.nms_base_tool.string_base,
                                    metadata=build_metadata.export_package_metadata(
                                        bpy.context.scene.nms_base_tool, source))
        from .save_editor.ship_repair import cockpit_warning
        if warnings is not None and cockpit_warning(data):
            warnings.append(cockpit_warning(data))
        progress.update(.92, 'Writing Corvette package')
        interchange.atomic_write(file_path, payload)
        progress.update(1.0, 'Corvette package ready')
        return len(data)

    # Save and Load Methods ---
    def save_nms_data(self, file_path):
        """Generate data and place it into a json file.

        This preserves any presets built in scene.

        Args:
            file_path (str): The path to the json file.
        """
        with progress_ui.Activity('Saving BBE project JSON') as progress:
            return self._save_nms_data(file_path, progress)

    def _save_nms_data(self, file_path, progress):
        data = self.serialise(get_presets=True, progress=progress,
                              progress_range=(.02, .75))
        progress.update(.78, 'Preparing project data')
        source = _restore_build_source(bpy.context.scene)
        if source and source.kind == 'base':
            data = source.with_scene(data)
        path = Path(file_path)
        if path.suffix.lower() != '.json':
            path = path.with_suffix('.json')
        progress.update(.91, 'Writing project JSON')
        interchange.atomic_write(path, interchange._encode(data))
        progress.update(1.0, 'Project JSON ready')

    def load_nms_data(self, file_path):
        # First load
        with progress_ui.Activity('Opening BBE project JSON') as progress:
            with open(file_path, "r") as stream:
                try:
                    progress.update(.1, 'Reading project data')
                    save_data = json.load(stream)
                    progress.update(1.0, 'Importing models')
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
        from . import bubble_preview
        bubble_preview.inspect_loaded_tubes(bpy.context.scene)

    def new_file(self):
        """Clear the current build's objects, helpers, collections and metadata."""
        from . import stages, scene_cleanup

        _clear_build_source(bpy.context.scene)
        stages.prepare_import(bpy.context.scene)

        BUILDER.clear_caches()

        base_props = bpy.context.scene.nms_base_tool
        base_props.new_file()
        base_props.string_base_type = 'HomePlanetBase'

        station_reference.clear_reference(bpy.context.scene)
        bpy.context.scene.bbe_stage.collection = None
        scene_cleanup.clear(bpy.context.scene)
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
        selected_objects = preset.colour_targets(bpy.context.selected_objects)
        if not selected_objects:
            ShowMessageBox(
                message="Make sure you have an item selected.", title="Apply Colour"
            )
            return {"FINISHED"}

        # A NMScribe White Border stroke is two overlapping native decals.
        # Painting just one leaves the other white over the same artwork and
        # makes the new colour appear to have done nothing. Treat this pair as
        # one stroke while keeping both real parts and their export records.
        trial_roots = {obj.parent for obj in selected_objects
                       if obj.parent and obj.parent.get("nms_decal_trial_root")
                       and obj.get("nms_text_owner") == obj.parent.get("nms_text_owner")}
        for root in trial_roots:
            for obj in root.children:
                if (obj.get("ObjectID") == "BUILDDECAL2"
                        and obj.get("nms_text_owner") == root.get("nms_text_owner")
                        and obj not in selected_objects):
                    selected_objects.append(obj)

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

        painted_meshes = {}
        for obj in selected_objects:
            if "ObjectID" in obj and not _materials_v2.is_high_res(obj):
                # Share only copies of the same source mesh and packed colour.
                # Each placement still needs its own viewport colour/labels;
                # those properties do not live on the shared mesh.
                new_userdata = _userdata.update_colour_material(
                    int(obj.get("UserData", 0)),
                    colour_index=int(colour_index),
                    material_index=maeterial_index,
                )
                key = (obj.data.as_pointer(), new_userdata)
                if key not in painted_meshes:
                    obj.data = obj.data.copy()
                    painted_meshes[key] = obj.data
                else:
                    obj.data = painted_meshes[key]
                _material.assign_material(obj, int(colour_index), maeterial_index)

        for obj in selected_objects:
            # detect if object is nms curve
            if "has_linked_objects" in obj and curve.is_bezier_or_nurbs_path(obj):
                for child_obj in bpy.context.scene.objects:
                    if "curve_parent" in child_obj and child_obj["curve_parent"] == obj.name:
                        _material.assign_material(child_obj, int(colour_index), int(maeterial_index))
                        obj["dup_UserData"] = child_obj["UserData"]
            elif "GroupID" in obj:
                _material.assign_material(obj, int(colour_index), int(maeterial_index))
        # Refresh the viewport.
        for window in bpy.context.window_manager.windows:
            for area in window.screen.areas:
                if area.type == "VIEW_3D":
                    area.tag_redraw()

    def apply_default_colour(self):
        """Gives an item a new colour."""
        selected_objects = preset.colour_targets(bpy.context.selected_objects)
        if not selected_objects:
            ShowMessageBox(
                message="Make sure you have an item selected.", title="Apply Colour"
            )
            return {"FINISHED"}

        # Keep unselected prefab copies independent in the simple-model path.
        default_meshes = {}
        # Apply Colour Material.
        for obj in selected_objects:
            if "GroupID" in obj:
                if not group.Group.restore_cached_colours(obj, BUILDER):
                    raise RuntimeError("Could not restore the group's cached colours")
                continue
            if "ObjectID" not in obj:
                continue
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
            if not _materials_v2.is_high_res(obj) and hasattr(obj.data, 'materials'):
                key = (obj.data.as_pointer(), index)
                if key not in default_meshes:
                    default_meshes[key] = obj.data.copy()
                obj.data = default_meshes[key]
            _material.assign_default_material(obj, index=index)

        # Refresh the viewport.
        for window in bpy.context.window_manager.windows:
            for area in window.screen.areas:
                if area.type == "VIEW_3D":
                    area.tag_redraw()
        
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
        selected_objects = preset.colour_targets(bpy.context.selected_objects)

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
                        _material.restore_material(obj, target_userdata)
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
    bl_label = "BBE"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "No Mans Sky Base Builder"
    bl_context = "objectmode"

    @classmethod
    def poll(self, context):
        return True

    def draw_header_preset(self, context):
        row = self.layout.row()
        row.alignment = 'RIGHT'
        row.label(text='V' + ADDON_VERSION)

    def draw(self, context):
        scene = context.scene
        nms_tool = scene.nms_main
        layout = self.layout
        
        pcoll = icons.get_icons_pscroll()
        pateron_icon = pcoll["patreon"]
        discord_icon = pcoll["discord"]
        steam_icon = pcoll["steam"]
        online_icon = pcoll["online"]
        
        icons.draw_sidebar_brand(layout, context)
        
        community_row = layout.row(align=True)
        communuity_box = community_row.box()
        third_column = communuity_box.column(align=True)
        third_column.label(text="Community")
        third_column.operator("object.nms_visit_guides", icon_value = online_icon.icon_id)
        third_column.operator("object.nms_visit_community", icon_value = discord_icon.icon_id)
        
        support_box = community_row.box()
        fourth_column = support_box.column(align = True)
        fourth_column.label(text = "Support DjMonkey")
        fourth_column.operator("object.nms_visit_patreon", text = "Patreon", icon_value = pateron_icon.icon_id)
        fourth_column.operator("object.nms_visit_steam_games", text = "Steam Games", icon_value = steam_icon.icon_id)
        
        wasd_navigation.draw_controls(layout, context)
        from .save_editor.corvette_optimizer import draw_cockpit_controls
        draw_cockpit_controls(layout)
        from .save_editor.function_help import help_button
        help_button(layout, text='BBE Feature Help')

        workspace_row = layout.row(align=True)
        workspace_box = workspace_row.box()
        workspace_column = workspace_box.column(align = False)
        workspace_label_row = workspace_column.row(align = True)
        workspace_label_row.label(text = "Workspace")
        
        workspace_column_2 = workspace_column.column(align = True)
        workspace_cleanup_row = workspace_column_2.row(align = True)
        workspace_cleanup_row.enabled = not nms_tool.is_workspace_cleaned
        workspace_cleanup_row.operator("object.nms_cleanup_workspace", text = "Simplify Blender Workspace", **icons.ui_icon("WORKSPACE"))
        
        workspace_column_2.separator()
        workspace_column_2.operator("object.nms_workspace_settings", text = "Workspace Settings", **icons.ui_icon("SETTINGS"))
        
        
        
        file_box = workspace_row.box()
        file_column = file_box.column(align = True)
            
        file_column.label(text="Scene")
        file_column.operator("object.nms_new_file", text="Clear Build Scene...", **icons.ui_icon("FILE_NEW"))
        file_column.separator()
        file_column.label(text="Build files")
        file_column.operator("object.nms_save_data", text="Save Project JSON...", **icons.ui_icon("FILE_TICK"))
        file_column.operator("bbe.import_build_file", text="Import Build from File...", **icons.ui_icon("IMPORT"))


# File Buttons Panel ---
class NMS_PT_project_recovery_panel(Panel):
    bl_idname = 'NMS_PT_project_recovery_panel'
    bl_label = 'Project Recovery'
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'No Mans Sky Base Builder'
    bl_context = 'objectmode'
    bl_options = {'DEFAULT_CLOSED'}

    def draw_header(self, context):
        icons.draw_panel_icon(self.layout, 'recovery')

    def draw(self, context):
        project_recovery.draw_controls(self.layout, context, boxed=False)


class NMS_PT_file_buttons_panel(Panel):
    bl_idname = "NMS_PT_file_buttons_panel"
    bl_label = 'Import/Export'
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "No Mans Sky Base Builder"
    bl_options = {'DEFAULT_CLOSED'}
    bl_context = "objectmode"

    @classmethod
    def poll(self, context):
        return True

    def draw_header(self, context):
        icons.draw_panel_icon(self.layout, 'io')

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
        first_column.label(text="Metadata", **icons.ui_icon("PROPERTIES"))
        first_column.label(text="Ship Name" if base_props.string_base_type == "PlayerShipBase" else "Base Name")
        build_metadata.draw_name(first_column, base_props)
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
        clipboard_box.label(text="Import & Export", **icons.ui_icon("IMPORT"))
        second_column = clipboard_box.column(align=False)
        second_column.operator("object.nms_import_nms_data", **icons.ui_icon("PASTEDOWN"))
        second_column.separator()
        second_column.prop(nms_tool,"check_export_objects_only", text = "Objects only") 
        second_column.operator("object.nms_export_nms_data", **icons.ui_icon("COPYDOWN"))
            


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
    bl_label = 'Colour & Materials'
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "No Mans Sky Base Builder"
    bl_context = "objectmode"
    bl_options = {'DEFAULT_CLOSED'}

    @classmethod
    def poll(self, context):
        return True

    def draw_header(self, context):
        icons.draw_panel_icon(self.layout, 'color')

    def draw(self, context):
        draw_colour_palette(self.layout, context)


_palette_selection = None


def selected_colour_row(context):
    obj = context.view_layer.objects.active if context.view_layer else None
    if obj is None or not obj.select_get():
        return None
    value = obj.get('UserData', obj.get('dup_UserData'))
    if value is None:
        return None
    try:
        colour, material = _userdata.get_colour(int(value)), _userdata.get_material(int(value))
    except (ValueError, TypeError):
        return None
    return next((row for row in _material.BAKED_COLOURS
                 if int(row[3]) == colour and int(row[4]) == material), None)


def sync_selected_palette(context):
    # Palette selection is UI state. Never call the eyedropper's paint callback.
    global _palette_selection
    obj = context.view_layer.objects.active if context.view_layer else None
    key = (context.scene.as_pointer(), obj.as_pointer(), obj.get('UserData', obj.get('dup_UserData'))) if obj and obj.select_get() else None
    if key == _palette_selection:
        return
    _palette_selection = key
    row = selected_colour_row(context)
    if row is not None:
        context.scene.nms_main.material_switch = f'{row[4]}_{row[2]}'


def draw_colour_palette(layout, context, *, horizontal=False):
    """Share the same palette controls between the sidebar and tool header."""
    nms_tool = context.scene.nms_main
    selected = selected_colour_row(context)
    colours = _material.get_colours_from_palette(nms_tool.material_switch)
    pcoll = preview_collections.get("main")
    if selected is not None:
        current_icon = pcoll.get(os.path.splitext(selected[9])[0]) if pcoll else None
        current = layout.row(align=True)
        current.label(text=f'Current: {selected[5]}', icon_value=current_icon.icon_id if current_icon else 0)
        current.label(text=selected[2])
    if horizontal:
        colour_area = layout.row(align=True)
        palette = colour_area.row(align=True)
        palette.ui_units_x = 8
        palette.prop(nms_tool, "material_switch", text="")
        grid = colour_area.row(align=True)
        grid.scale_x = 1.0
    else:
        colour_area = layout.box().column(align=False)
        colour_area.row(align=True).prop(nms_tool, "material_switch", text="Palette")
        colour_area.separator()
        grid = colour_area.grid_flow(columns=12, even_columns=True, align=True)
        grid.scale_x = 0.6
        grid.scale_y = 1.0

    if pcoll is None:
        return
    for row in colours:
        index, name, thumb = row[3], row[5], row[9]
        colour_icon = pcoll.get(os.path.splitext(thumb)[0])
        op = grid.operator(
            "object.nms_apply_colour", text="",
            icon_value=colour_icon.icon_id if colour_icon else 0,
            depress=selected is not None and row[3:5] == selected[3:5],
        )
        op.colour_index = int(index)
        op.colour_name = name
    picker = grid.row(align=True)
    if horizontal:
        picker.ui_units_x = 1.5
    picker.prop(nms_tool, "color_picker", icon="BLANK1", text="")


# Colour Panel ---
class NMS_PT_logic_panel(Panel):
    bl_idname = "NMS_PT_logic_panel"
    bl_label = 'Cables & Logic'
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "No Mans Sky Base Builder"
    bl_context = "objectmode"
    bl_options = {'DEFAULT_CLOSED'}

    @classmethod
    def poll(self, context):
        return True

    def draw_header(self, context):
        icons.draw_panel_icon(self.layout, 'cables')

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
        operations_col_1.operator("object.nms_point", **icons.ui_icon("EMPTY_DATA"))
        operations_col_1.operator("object.nms_divide", **icons.ui_icon("LINCURVE"))
        
        operations_col_2 = row.column(align = True)
        operations_col_2.operator("object.nms_connect", **icons.ui_icon("PARTICLES"))
        operations_col_2.operator("object.nms_split", **icons.ui_icon("MOD_PHYSICS"))
        
        operations_col_3 = row.column(align = True)
        operations_col_3.operator("object.nms_select_connected", **icons.ui_icon("RESTRICT_SELECT_OFF"))
        operations_col_3.operator("object.nms_select_floating", **icons.ui_icon("RESTRICT_INSTANCED_ON"))
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
    bl_label = 'Prefabs'
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "No Mans Sky Base Builder"
    bl_context = "objectmode"
    bl_options = {'DEFAULT_CLOSED'}

    @classmethod
    def poll(self, context):
        return True

    def draw_header(self, context):
        icons.draw_panel_icon(self.layout, 'parts')

    def draw(self, context):
        layout = self.layout
        scene = context.scene
        nms_tool = scene.nms_main
        
        build_column = layout.column(align = True)
        main_col = build_column.box().column(align = True)
        
        presets_box = main_col.column(align = True)
        presets_box.label(text = "Prefabs")
        preset_row = presets_box.row(align = True)
        preset_row.operator("object.nms_save_as_preset", **icons.ui_icon("SCENE_DATA"))
        preset_row.operator("object.nms_split_preset", **icons.ui_icon("MOD_EXPLODE"))
        row = presets_box.row(align=True)
        row.operator("object.nms_get_more_presets", **icons.ui_icon("WORLD_DATA"))
        row.operator("object.nms_open_preset_folder", **icons.ui_icon("FILE_FOLDER"))
        
        presets_v2_col = main_col
        presets_v2_col.label(text = "Grouping")
        presets_v2_row = presets_v2_col.row(align = True)
        presets_v2_row.operator("object.nms_group_objects", text = "Group", **icons.ui_icon("OUTLINER_OB_POINTCLOUD") )
        presets_v2_row.operator("object.nms_ungroup_objects", text = "Ungroup",  **icons.ui_icon("OUTLINER_DATA_POINTCLOUD"))
        

        catalogue = layout.box()
        heading = catalogue.row(align=True)
        heading.label(text="Prefab Catalogue")
        heading.operator("object.nms_refresh_prefabs", text="", **icons.ui_icon("FILE_REFRESH"))
        wm = context.window_manager
        if wm.bbe_prefabs:
            catalogue.template_list("NMS_UL_actions_list", "prefabs", wm,
                                    "bbe_prefabs", wm, "bbe_prefab_index", rows=6)
        else:
            catalogue.label(text="No prefabs found")


class NMS_UL_actions_list(bpy.types.UIList):
    def draw_item(self, context, layout, data, item, icon, active_data, active_propname):
        self.use_filter_show = True
        if item.title:
            layout.label(text=item.title)
        elif item.description:
            row = layout.row(align=True)
            place = row.operator("object.list_build_operator", text=item.description)
            place.part_id = item.description
            place.prefab_only = True
            place.tooltip = "Place this prefab in the scene."
            row.operator("object.list_edit_operator", text="", **icons.ui_icon("GREASEPENCIL")).part_id = item.description
            row.operator("object.list_delete_operator", text="", **icons.ui_icon("TRASH")).part_id = item.description


class PartCollection(bpy.types.PropertyGroup):
    title: bpy.props.StringProperty()
    description: bpy.props.StringProperty()


def refresh_prefab_catalogue():
    """Cache folder contents outside draw callbacks and scene undo data."""
    entries = []
    try:
        # Scan once, rather than rescanning the folder for every visible row.
        grouped = {}
        for name, filename in preset.Preset.get_presets().items():
            parent = Path(filename).parent
            category = ("Uncategorized Prefabs" if parent == Path(preset.Preset.PRESET_PATH)
                        else parent.name.replace("_", " "))
            grouped.setdefault(category, []).append(name)
        for category, names in sorted(grouped.items(), key=lambda pair: pair[0].casefold()):
            entries.append((category, ""))
            entries.extend(("", name) for name in sorted(names, key=str.casefold))
    except OSError as exc:
        print("BBE: unable to read prefab catalogue:", exc)
    for wm in bpy.data.window_managers:
        wm.bbe_prefabs.clear()
        for title, description in entries:
            item = wm.bbe_prefabs.add()
            item.title, item.description = title, description
            item.name = description or title
        wm.bbe_prefab_index = min(wm.bbe_prefab_index, max(0, len(entries) - 1))
        for window in wm.windows:
            for area in window.screen.areas:
                if area.type == 'VIEW_3D':
                    area.tag_redraw()


def _refresh_prefab_catalogue_deferred():
    if not undo_guard.history_ready():
        return 0.5
    refresh_prefab_catalogue()
    return None


@persistent
def schedule_prefab_catalogue(_=None):
    if not bpy.app.timers.is_registered(_refresh_prefab_catalogue_deferred):
        bpy.app.timers.register(_refresh_prefab_catalogue_deferred, first_interval=0.1)


class RefreshPrefabCatalogue(bpy.types.Operator):
    """Reload the prefab catalogue from the prefab folder"""
    bl_idname = "object.nms_refresh_prefabs"
    bl_label = "Refresh Prefab Catalogue"

    def execute(self, context):
        refresh_prefab_catalogue()
        return {'FINISHED'}


# Operators ---
# File Operators ---
class NewFile(bpy.types.Operator):
    bl_idname = "object.nms_new_file"
    bl_label = "Clear Build Scene..."
    bl_description = "Clear objects and collections from this build scene, keeping the workspace and Asset Browser"
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
    bl_label = "Save BBE Project JSON..."
    filepath: bpy.props.StringProperty(subtype="FILE_PATH")
    filter_glob: bpy.props.StringProperty(default="*.json", options={'HIDDEN'})

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
    bl_label = "Open BBE Project JSON..."
    bl_options = {"UNDO", "REGISTER"}
    filepath: bpy.props.StringProperty(subtype="FILE_PATH")
    filter_glob: bpy.props.StringProperty(default="*.json", options={'HIDDEN'})

    def execute(self, context):
        scene = context.scene
        nms_tool = scene.nms_main
        nms_tool.load_nms_data(self.filepath)
        return {"FINISHED"}

    def invoke(self, context, event):
        context.window_manager.fileselect_add(self)
        return {"RUNNING_MODAL"}


class ImportBuildFile(bpy.types.Operator):
    bl_idname = 'bbe.import_build_file'
    bl_label = 'Import Build from File...'
    bl_description = 'Open a Corvette package, base file, prefab, or JSON/TXT build in this Blender scene'
    bl_options = {'REGISTER', 'UNDO'}
    filepath: bpy.props.StringProperty(subtype='FILE_PATH')
    filter_glob: bpy.props.StringProperty(
        default='*.nmsship;*.nmsbase;*.nmsprefab;*.json;*.txt', options={'HIDDEN'})
    parts_base_type: bpy.props.EnumProperty(
        name='Fallback build type',
        description='Type to use when base-type metadata is missing, blank, or unsupported',
        items=[('HomePlanetBase', 'Planet Base', ''),
               ('PlayerShipBase', 'Corvette', ''),
               ('FreighterBase', 'Freighter Base', ''),
               ('PlayerSpaceBase', 'Space Base', ''),
               ('PlayerSpaceStationBase', 'Station Base', '')],
        default='HomePlanetBase')

    def draw(self, context):
        self.layout.prop(self, 'parts_base_type')

    def execute(self, context):
        try:
            count, kind = context.scene.nms_main.import_build_file(self.filepath, self.parts_base_type)
        except (OSError, ValueError, KeyError, TypeError) as exc:
            report_error(self, {'ERROR'}, f'Could not import build: {exc}')
            return {'CANCELLED'}
        label = {'parts': 'build', 'base': 'base', 'ship': 'Corvette'}[kind]
        self.report({'INFO'}, f'Imported {count} {label} parts; no game save changed')
        return {'FINISHED'}

    def invoke(self, context, event):
        context.window_manager.fileselect_add(self)
        return {'RUNNING_MODAL'}


class ExportBaseFile(bpy.types.Operator):
    bl_idname = 'bbe.export_base_file'
    bl_label = 'Export Base File (.nmsbase)...'
    bl_description = 'Save the current planet, freighter, space, or station base as a standalone file'
    filepath: bpy.props.StringProperty(subtype='FILE_PATH')
    filter_glob: bpy.props.StringProperty(default='*.nmsbase', options={'HIDDEN'})

    def execute(self, context):
        path = str(Path(self.filepath).with_suffix('.nmsbase'))
        try:
            count, base_type = context.scene.nms_main.export_base_file(path)
        except (OSError, ValueError, KeyError, TypeError) as exc:
            report_error(self, {'ERROR'}, f'Could not export base: {exc}')
            return {'CANCELLED'}
        self.report({'INFO'}, f'Exported {count} {base_type} parts to {path}')
        return {'FINISHED'}

    def invoke(self, context, event):
        context.window_manager.fileselect_add(self)
        return {'RUNNING_MODAL'}


class ExportShipFile(bpy.types.Operator):
    bl_idname = 'bbe.export_ship_file'
    bl_label = 'Export Corvette Package (.nmsship)...'
    bl_description = 'Save current parts as .nmsship; retain imported ship metadata, choose a saved ship or template, or use new Corvette defaults'
    filepath: bpy.props.StringProperty(subtype='FILE_PATH')
    filename_ext = '.nmsship'
    template_path: bpy.props.StringProperty(
        name='Ship package template', subtype='FILE_PATH',
        description='Optional: copy class, inventory, technology and appearance from a complete .nmsship; leave empty for new Corvette defaults')
    filter_glob: bpy.props.StringProperty(default='*.nmsship', options={'HIDDEN'})
    use_selected_save: bpy.props.BoolProperty(name='Use selected save Corvette', default=False,
        description='Use class, inventory, technology and appearance from the Corvette selected in I/O; export current Blender parts')

    def check(self, context):
        if not self.filepath:
            return False
        path = str(Path(self.filepath).with_suffix('.nmsship'))
        changed = path != self.filepath
        self.filepath = path
        return changed

    def draw(self, context):
        source = context.scene.get('bbe_build_source_suffix')
        source_text = bpy.data.texts.get(context.scene.get('bbe_build_source_text', ''))
        if context.scene.nms_base_tool.string_base_type != 'PlayerShipBase':
            self.layout.label(text='This export creates a Corvette package from your scene parts.', icon='INFO')
        if source != '.nmsship' or source_text is None:
            self.layout.prop(self, 'use_selected_save')
            if self.use_selected_save:
                selected = context.scene.nms_save_data.get_current_base_identifiers()
                if selected and selected.base_type == 'PlayerShipBase' and type(selected.user_data) is int and 0 <= selected.user_data < 12:
                    self.layout.label(text=f'{selected.save_context} / Ship slot {selected.user_data + 1}: {selected.base_name}')
                    self.layout.label(text='Exports current Blender parts with this saved ship’s stats and inventory.')
                else:
                    self.layout.label(text='Select the original Corvette in I/O first.', icon='ERROR')
            else:
                if source == '.nmsship':
                    self.layout.label(text='Imported ship metadata is missing.', icon='ERROR')
                    self.layout.label(text='Choose a saved Corvette or a complete template.')
                else:
                    self.layout.label(text='Empty template uses new Corvette defaults.')
                    self.layout.label(text='No cockpit or template parts are added.')
                self.layout.prop(self, 'template_path')
        else:
            self.layout.label(text='Class, inventory and appearance come from imported ship.')

    def execute(self, context):
        path = str(Path(self.filepath).with_suffix('.nmsship'))
        try:
            warnings = []
            count = context.scene.nms_main.export_ship_file(path, self.template_path, self.use_selected_save, warnings)
        except (OSError, ValueError, KeyError, TypeError) as exc:
            report_error(self, {'ERROR'}, f'Could not export Corvette: {exc}')
            return {'CANCELLED'}
        self.report({'WARNING'} if warnings else {'INFO'}, f'Exported {count} Corvette parts to {path}' + (' — ' + ' '.join(warnings) if warnings else ''))
        return {'FINISHED'}

    def invoke(self, context, event):
        self.use_selected_save = False
        if context.scene.get('bbe_build_source_suffix') != '.nmsship':
            selected = context.scene.nms_save_data.get_current_base_identifiers()
            self.use_selected_save = bool(
                selected and selected.base_type == 'PlayerShipBase'
                and type(selected.user_data) is int and 0 <= selected.user_data < 12)
        name = context.scene.nms_base_tool.string_base.strip()
        if not name:
            name = Path(bpy.data.filepath).stem if bpy.data.filepath else 'Corvette'
        filename = bpy.path.clean_name(name) + '.nmsship'
        self.filepath = str(Path(bpy.data.filepath).parent / filename) if bpy.data.filepath else filename
        context.window_manager.fileselect_add(self)
        return {'RUNNING_MODAL'}


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
        refresh_prefab_catalogue()
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
    prefab_only: BoolProperty(default=False, options={'HIDDEN'})

    @classmethod
    def description(cls, context, operator):
        return operator.tooltip

    def execute(self, context):
        # Get Selection
        selection = blend_utils.get_current_selection()

        # Build item
        if self.part_id in preset.Preset.get_presets():
            new_item = BUILDER.add_preset(self.part_id)
        elif self.prefab_only:
            refresh_prefab_catalogue()
            self.report({'WARNING'}, "This prefab is no longer in the prefab folder")
            return {'CANCELLED'}
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
            refresh_prefab_catalogue()
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
        layout.label(text = "Select Origin of Merged Object", **icons.ui_icon("OUTLINER_OB_POINTCLOUD"))
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


def reset_curve_tracking():
    """Reseed Python-only caches from restored IDs without editing the scene."""
    global known_curve_names, last_active
    last_active = None
    scene = getattr(bpy.context, 'scene', None)
    known_curve_names = {
        obj.name for obj in scene.objects
        if obj.type == 'CURVE' and curve.Curve.PROP_CURVE_ID in obj
    } if scene is not None else set()

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
    
    
    # Rebind project UI, then restore this session's local save destination.
    for scene in bpy.data.scenes:
        asset_browser = scene.nms_asset_browser
        asset_browser.initialise_asset_browser()
        from . import bubble_preview
        bubble_preview.inspect_loaded_tubes(scene)
    save_manager.restore_after_load()

            
# Whenever a curve is modified, automatically update whatever child objects that are associated with that curve.
@persistent
def udpates_handler(scene, depsgraph):
    if getattr(bpy.context, 'view_layer', None) and hasattr(scene, 'nms_main'):
        sync_selected_palette(bpy.context)
    if not undo_guard.curve_tracking_ready():
        return
    
    global known_curve_names
    global last_active
    
    
    # Blender can invoke persistent depsgraph handlers with a restricted
    # context while extensions are being enabled. The scene/depsgraph
    # arguments remain valid, but context.view_layer does not exist yet.
    view_layer = getattr(bpy.context, "view_layer", None)
    active_object = view_layer.objects.active if view_layer is not None else None

    # keep track of active object to display or hide additional options related to that object
    # only continue when active object actually changes
    active_key = active_object.as_pointer() if active_object is not None else None
    if active_object is not None and active_key != last_active:
        properties = scene.nms_properties
        properties.set_active_obect(active_object)
        last_active = active_key

    # Collect curves that have recieved updates by user
    updated_curve_names = set()
    native_bubble_changed = False
    for update in depsgraph.updates:
        if isinstance(update.id, bpy.types.Object):
            if update.id.get('ObjectID') == 'BASE_BUBPIPE':
                native_bubble_changed = True
            # validate each object
            orig_obj = bpy.data.objects.get(update.id.name)
            # the object can already be gone by the time we look it up
            if orig_obj is None:
                continue
            if orig_obj.type == 'CURVE' and curve.Curve.PROP_CURVE_ID in orig_obj:
                updated_curve_names.add(orig_obj.name)
            elif curve.Curve.PROP_CURVE_PARENT in orig_obj:
                parent_curve_name = orig_obj[curve.Curve.PROP_CURVE_PARENT]
                parent_curve = scene.objects.get(parent_curve_name,None)
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

    if native_bubble_changed:
        from . import bubble_preview
        bubble_preview.request_refresh(scene)


    
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
    ImportBuildFile,
    ExportBaseFile,
    ExportShipFile,
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
    NMS_PT_project_recovery_panel,
    NMS_PT_file_buttons_panel,
    NMS_PT_station_transfer_reference,
    NMS_PT_save_editor_panel,
    BBE_OT_backup_settings,
    BBE_OT_refresh_save_counts,
    BBE_OT_save_refresh_notice,
    NMS_PT_transformation_panel,
    NMS_PT_colour_panel,
    NMS_PT_logic_panel,
    NMS_PT_tools_panel,
    NMS_PT_batch_tools_panel,
    NMS_PT_build_panel,
    RefreshPrefabCatalogue,
    NMSAddonPreferences,
    
    SwitchWorkspace,
    SplitPreset,
    
    GroupObjects,
    UngroupObjects
)

classes = classes + build_metadata_ui.classes + asset_browser_presentation.classes + base_builder_menu.classes

classes = classes  + save_editor_operators.classes + station_reference.classes + build_tool_operators.classes + batch_tool_operators.classes + prooperties_operators.classes + asset_browser_operators.classes + base_builder_menu_operators.classes



_core_registered = False


def register():
    compatibility.register()
    if compatibility.conflicting_charon():
        compatibility.begin_preflight()
        return
    register_core()
    compatibility.watch()


def register_core():
    global _core_registered

    from . import release_updates
    release_updates.register('bbe', ADDON_VERSION, 'No Mans Sky Base Builder')

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
    build_metadata_ui.register_handlers()
    bpy.types.WindowManager.bbe_prefabs = bpy.props.CollectionProperty(type=PartCollection, options={'SKIP_SAVE'})
    bpy.types.WindowManager.bbe_prefab_index = bpy.props.IntProperty(default=0, options={'SKIP_SAVE'})
    if schedule_prefab_catalogue not in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.append(schedule_prefab_catalogue)
    schedule_prefab_catalogue()
    bpy.types.Scene.nms_save_data = bpy.props.PointerProperty(type=SaveManager)
    bpy.types.Scene.nms_build_tool = bpy.props.PointerProperty(type=BuildTool)
    bpy.types.Scene.nms_properties = bpy.props.PointerProperty(type=Properties)
    bpy.types.Scene.nms_batch_tool = bpy.props.PointerProperty(type=BatchTool)
    bpy.types.Scene.nms_asset_browser = bpy.props.PointerProperty(type=AssetBrowser)
    from .tools import asset_browser_grid, asset_browser_sidebar
    asset_browser_grid.register()
    asset_browser_sidebar.register()

    # Puts the "Base Builder" menu in the 3D viewport header. The menu classes
    # themselves are registered with everything else, above.
    from . import bbe_chat
    bbe_chat.register()
    base_builder_menu.register_menu()
    from . import hd_library_ui, stages, decals, hab_windows
    hd_library_ui.register()
    stages.register()
    decals.register()
    hab_windows.register()
    undo_guard.register()
    project_recovery.register()
    wasd_navigation.register()
    from .save_editor import corvette_optimizer
    from .save_editor import function_help
    from . import bubble_preview
    bubble_preview.register()
    from . import snap_markers
    snap_markers.register()
    from . import habitat_preview
    habitat_preview.register()
    from . import decal_controls
    decal_controls.register()
    from . import pilot_reference
    pilot_reference.register()
    from . import character_references
    character_references.register()
    from . import wire_selection
    wire_selection.register()
    function_help.register()
    corvette_optimizer.register()
    from .save_editor import ship_management
    ship_management.register()
    from .save_editor import buildable_unlocks_ui
    buildable_unlocks_ui.register()
    from .save_editor import raw_json_launcher
    raw_json_launcher.register()
    from .save_editor import corvette_io
    corvette_io.register()
    from .save_editor import corvette_actions
    corvette_actions.register()
    
    if reset_plugin_state not in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.append(reset_plugin_state)
    if save_manager.capture_before_load not in bpy.app.handlers.load_pre:
        bpy.app.handlers.load_pre.append(save_manager.capture_before_load)
    
    if udpates_handler not in bpy.app.handlers.depsgraph_update_post:
        bpy.app.handlers.depsgraph_update_post.append(udpates_handler)
    
    bpy.app.timers.register(viewport_overlay.register_draw, first_interval=0.01)
    _core_registered = True

def unregister():
    build_metadata_ui.unregister_handlers()
    global _core_registered
    compatibility.unregister()
    if not _core_registered:
        return
    _core_registered = False
    if bpy.app.timers.is_registered(_refresh_prefab_catalogue_deferred):
        bpy.app.timers.unregister(_refresh_prefab_catalogue_deferred)
    if schedule_prefab_catalogue in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.remove(schedule_prefab_catalogue)
    del bpy.types.WindowManager.bbe_prefabs
    del bpy.types.WindowManager.bbe_prefab_index
    wasd_navigation.unregister()
    project_recovery.unregister()
    undo_guard.unregister()
    from .tools import asset_browser_grid, asset_browser_sidebar
    asset_browser_sidebar.unregister()
    asset_browser_grid.unregister()
    from .save_editor import ship_management
    from .save_editor import corvette_io
    from .save_editor import corvette_actions
    corvette_actions.unregister()
    corvette_io.unregister()
    ship_management.unregister()
    from .save_editor import raw_json_launcher
    raw_json_launcher.unregister()
    from .save_editor import buildable_unlocks_ui
    buildable_unlocks_ui.unregister()
    from .save_editor import corvette_optimizer
    corvette_optimizer.unregister()
    from .save_editor import function_help
    function_help.unregister()
    from . import bubble_preview
    from . import decal_controls
    from . import pilot_reference
    pilot_reference.unregister()
    from . import character_references
    character_references.unregister()
    decal_controls.unregister()
    from . import wire_selection
    wire_selection.unregister()
    bubble_preview.unregister()
    from . import snap_markers
    snap_markers.unregister()
    from . import habitat_preview
    habitat_preview.unregister()
    from . import release_updates
    release_updates.unregister()
    from . import hd_library_ui, stages, decals, hab_windows
    hab_windows.unregister()
    decals.unregister()
    stages.unregister()
    hd_library_ui.unregister()
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
    from . import bbe_chat
    bbe_chat.unregister()


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
    if save_manager.capture_before_load in bpy.app.handlers.load_pre:
        bpy.app.handlers.load_pre.remove(save_manager.capture_before_load)
        
    if udpates_handler in bpy.app.handlers.depsgraph_update_post:
        bpy.app.handlers.depsgraph_update_post.remove(udpates_handler)
    
    viewport_overlay.unregister_draw()


if __name__ == "__main__":
    register()
