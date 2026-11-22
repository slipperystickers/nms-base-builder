from .. import i18n
from ..furby_errors import report_error
import bpy
from pathlib import Path

from . import save_editor_utils
from .. import build_metadata
ADDON_ID = __package__.rsplit(".", 1)[0]
_pending_save_imports = {}

# Operator for button to select save folder directory
class SelectSaveFolder(bpy.types.Operator):
    bl_idname = "object.nms_select_save_folder"
    bl_translation_context = "BBEExtendedInterface"
    bl_label = "Select Folder"
    
    bl_description = "Manually select location of save folder of NMS"

    directory: bpy.props.StringProperty(
        subtype='DIR_PATH'
    )

    def execute(self, context):
        folder = Path(bpy.path.abspath(self.directory))
        if not save_editor_utils.validate_save_folder(folder):
            self.report({'ERROR'}, "Choose HelloGames/NMS, the GOG DefaultUser folder, or a Steam st_ account folder.")
            return {'CANCELLED'}
        direct = save_editor_utils.is_account_folder(folder)
        if direct and not save_editor_utils.get_hg_files_in_folder(folder):
            self.report({'ERROR'}, "This account folder contains no save*.hg files. Choose the account where you saved your game.")
            return {'CANCELLED'}
        prefs = context.preferences.addons[ADDON_ID].preferences
        prefs.nms_save_folder_path = str(folder)
        bpy.ops.wm.save_userpref()
        save_data = context.scene.nms_save_data
        save_data.on_check_plugin_enabled(context)
        save_data.nms_account_selected = str(folder) if direct and save_data.check_plugin_enabled else 'Default'
        self.report({'INFO'}, "Save folder selected")
        return {'FINISHED'}

    def invoke(self, context, event):
        prefs = context.preferences.addons[ADDON_ID].preferences
        save_root_folder = prefs.nms_save_folder_path
        self.directory = save_root_folder
        context.window_manager.fileselect_add(self)
        return {'RUNNING_MODAL'}
    
# Button to import base selected from list of bases in save editor section
class ImportBaseFromSave(bpy.types.Operator):
    bl_idname = "object.nms_import_base_from_save"
    bl_translation_context = "BBEExtendedInterface"
    bl_label = "Import data from selected file"
    bl_description = "Import base from save file while also pinning it on top"

    expected_scene: bpy.props.StringProperty(options={'HIDDEN'})
    expected_account: bpy.props.StringProperty(options={'HIDDEN'})
    expected_slot: bpy.props.StringProperty(options={'HIDDEN'})
    expected_base_type: bpy.props.StringProperty(options={'HIDDEN'})
    expected_base_index: bpy.props.StringProperty(options={'HIDDEN'})

    @classmethod
    def poll(cls, context):
        data = getattr(context.scene, 'nms_save_data', None)
        return bool(data and data.has_selected_base())

    def invoke(self, context, event):
        # Starting a large import before returning from this button leaves the
        # header popover over the viewport progress display. Let Blender finish
        # the click and dismiss the popover, then run the normal execute path.
        window = context.window
        scene = context.scene
        save_data = scene.nms_save_data
        window_id = window.as_pointer()
        if window_id in _pending_save_imports:
            self.report({'WARNING'}, 'An import is already starting in this window')
            return {'CANCELLED'}
        selection = {
            'expected_scene': scene.name,
            'expected_account': save_data.nms_account_selected,
            'expected_slot': save_data.nms_save_slot,
            'expected_base_type': save_data.nms_base_type,
            'expected_base_index': save_data.nms_base_index,
        }
        def start_import():
            try:
                if not any(w.as_pointer() == window_id for w in bpy.context.window_manager.windows):
                    return None
                if bpy.data.scenes.get(selection['expected_scene']) != scene:
                    return None
                with bpy.context.temp_override(window=window, scene=scene):
                    bpy.ops.object.nms_import_base_from_save('EXEC_DEFAULT', **selection)
            except Exception as exc:
                print(f'Could not start deferred save import: {exc}')
            finally:
                _pending_save_imports.pop(window_id, None)
            return None

        _pending_save_imports[window_id] = start_import
        bpy.app.timers.register(start_import, first_interval=0.1)
        return {'FINISHED'}

    def execute(self, context):
        scene = context.scene
        save_data = scene.nms_save_data
        if self.expected_scene and (
            scene.name != self.expected_scene
            or save_data.nms_account_selected != self.expected_account
            or save_data.nms_save_slot != self.expected_slot
            or save_data.nms_base_type != self.expected_base_type
            or save_data.nms_base_index != self.expected_base_index
        ):
            report_error(self, {'ERROR'}, 'Save selection changed before import started; choose the base and try again')
            return {'CANCELLED'}
        if scene.name.startswith('BBE Ship Management Preview'):
            source_name = scene.get('bbe_ship_management_source_scene')
            source = bpy.data.scenes.get(source_name) if source_name else None
            if source is None:
                report_error(self, {'ERROR'}, 'Close Ship Management and import in your main Blender scene')
                return {'CANCELLED'}
            context.window.scene = source
            self.report({'INFO'}, f'Importing into {source.name}')
        try:
            result = save_data.import_base_from_save_file(context)
        except Exception as exc:
            report_error(self, {'ERROR'}, f"Import failed: {exc}")
            return {'CANCELLED'}
        if not result or result.startswith(('Error', 'Could not')):
            report_error(self, {'ERROR'}, result or 'Error importing base')
            return {'CANCELLED'}
        self.report({'INFO'}, result)
        return {'FINISHED'}

# Button to export base selected from list of bases in save editor section
class ExportBaseToSave(bpy.types.Operator):
    bl_idname = "object.nms_export_base_to_save"
    bl_translation_context = "BBEExtendedInterface"
    bl_label = "Export data to save file"
    bl_description = "Export base to save_file"

    @classmethod
    def poll(cls, context):
        data = getattr(context.scene, 'nms_save_data', None)
        return bool(data and data.has_selected_base())

    def invoke(self, context, event):
        data = context.scene.nms_save_data
        selected = data.get_current_base_identifiers()
        if selected and selected.base_type == save_editor_utils.BaseType.CORVETTE:
            return bpy.ops.bbe.corvette_export('INVOKE_DEFAULT')
        if build_metadata.save_owner(context.scene.nms_base_tool) is not None:
            self._metadata_signature = build_metadata.save_target_signature(context)
            return context.window_manager.invoke_props_dialog(self, width=570, confirm_text='Export to Save')
        return self.execute(context)

    def draw(self, context):
        build_metadata.draw_save_warning(i18n.localized_layout(self.layout), context.scene.nms_base_tool)
        i18n.localized_layout(self.layout).label(text='Updates the selected base with your scene parts and name.')

    def execute(self, context):
        if (hasattr(self, '_metadata_signature') and self._metadata_signature !=
                build_metadata.save_target_signature(context)):
            self.report({'ERROR'}, 'Ownership changed. Review the export again.')
            return {'CANCELLED'}
        scene = context.scene
        save_data = scene.nms_save_data
        try:
            result = save_data.export_base_to_save_file(context)
        except Exception as exc:
            report_error(self, {'ERROR'}, f'Export failed: {exc}')
            return {'CANCELLED'}
        self.report({'INFO'}, result)
        return {"FINISHED"}
    
# Button to pin base to top of the editor
class PinBase(bpy.types.Operator):
    bl_idname = "object.nms_pin_base"
    bl_translation_context = "BBEExtendedInterface"
    bl_label = "Pin"
    bl_description = "Pin this base at top of Save Editor for easy access to updating functionality and persistence"
    
    def execute(self, context):
        scene = context.scene
        save_data = scene.nms_save_data
        base_tool = scene.nms_main
        
        save_data.pin_base()
        pinned_base = save_data.get_pinned_base_data()
        
        if pinned_base is not None:
            base_tool.deserialise_from_data(nms_data = pinned_base, start_new_file = False)
        else:
            report_error(self,{'ERROR'}, "Base not found")
        
        return {"FINISHED"}
    
# Button to unpin base from top of editor
class UnpinBase(bpy.types.Operator):
    
    bl_idname = "object.nms_unpin_base"
    bl_translation_context = "BBEExtendedInterface"
    bl_label = "Unpin"
    bl_description = "Unpin base from top of save editor"
    
    def execute(self, context):
        scene = context.scene
        save_data = scene.nms_save_data
        save_data.unpin_base()
        return {"FINISHED"}
    
# button to imoprt base data from a pinned base
class ImportPinnedBase(bpy.types.Operator):
    bl_idname = "object.import_pinned_base"
    bl_translation_context = "BBEExtendedInterface"
    bl_label = "Import"
    
    bl_description = (
        "Import latest data from save file into scene, \n"
        "replace all objects in scene with data imported"
    )
    
    def execute(self, context):
        scene = context.scene
        save_data = scene.nms_save_data
        save_data.import_pinned_base(context)
        return {"FINISHED"}
    
# button to export data to save file from pinned base
class ExoprtPinnedBase(bpy.types.Operator):
    
    bl_idname = "object.export_pinned_base"
    bl_translation_context = "BBEExtendedInterface"
    bl_label = "Export"
    bl_description = (
        "Update changes to save_file onto location that is pinned.\n"
        "Only ['Objects'] are updated.\n"
        "Check export base name to update name along with objects.\n"
        "Base Name will be taken from 'Base Name' field in Base properties section"
    )
    
        
    def invoke(self, context, event):
        if build_metadata.save_owner(context.scene.nms_base_tool) is not None:
            self._metadata_signature = build_metadata.save_target_signature(context, pinned=True)
            return context.window_manager.invoke_props_dialog(self, width=570, confirm_text='Export to Pinned Save')
        return self.execute(context)

    def draw(self, context):
        build_metadata.draw_save_warning(i18n.localized_layout(self.layout), context.scene.nms_base_tool)
        i18n.localized_layout(self.layout).label(text='Updates the pinned base with your scene parts and name.')

    def execute(self, context):
        if (hasattr(self, '_metadata_signature') and self._metadata_signature !=
                build_metadata.save_target_signature(context, pinned=True)):
            self.report({'ERROR'}, 'Ownership changed. Review the export again.')
            return {'CANCELLED'}
        scene = context.scene
        save_data = scene.nms_save_data
        try:
            result = save_data.export_pinned_base(context)
        except Exception as exc:
            report_error(self, {'ERROR'}, f'Export failed: {exc}')
            return {'CANCELLED'}
        self.report({'INFO'}, result)
        return {"FINISHED"}
    
# a button to manually backup save files
class MakeBackupPinned(bpy.types.Operator):
    
    bl_idname = "object.make_pinned_savefile_backup"
    bl_translation_context = "BBEExtendedInterface"
    bl_label = "Backup"
    bl_description = (
        "Back up the save files linked to the pinned base in the shared Backup Folder"
    )
        
    def execute(self, context):
        scene = context.scene
        save_data = scene.nms_save_data
        save_data.backup_pinned_save_files()
        self.report({'INFO'}, "Backup created sucessfully")
        return {"FINISHED"}
    
    
class MakeBackup(bpy.types.Operator):
    
    bl_idname = "object.make_savefile_backup"
    bl_translation_context = "BBEExtendedInterface"
    bl_label = "Backup"
    bl_description = (
        "Back up the selected save slot in the shared Backup Folder"
    )
        
    def execute(self, context):
        scene = context.scene
        save_data = scene.nms_save_data
        save_data.backup_save_files()
        self.report({'INFO'}, "Backup created sucessfully")
        return {"FINISHED"}
    
class OpenBackupFolder(bpy.types.Operator):
    
    bl_idname = "object.open_backup_folder"
    bl_translation_context = "BBEExtendedInterface"
    bl_label = "Open Save Slot Backups"
    bl_description = (
        "Open the selected save slot's subfolder inside the shared Backup Folder"
    )
        
    def execute(self, context):
        scene = context.scene
        save_data = scene.nms_save_data
        save_data.open_backup_folder_in_explorer()
        return {"FINISHED"}

# these classes can be appened to classes list in __init__.py file with + operator  
classes = (
    SelectSaveFolder,
    ImportBaseFromSave,
    ExportBaseToSave,
    PinBase,
    UnpinBase,
    ImportPinnedBase,
    ExoprtPinnedBase,
    MakeBackupPinned,
    MakeBackup,
    OpenBackupFolder
)
