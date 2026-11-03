"""The Save Manager sidebar panel, and the save manager UI itself.

draw_save_manager() holds the whole UI. The "Save Manager" dropdown in the
viewport header (presentation/save_manager_menu.py) draws the same function
into its popover, so the sidebar and the dropdown cannot drift apart.
"""
from ..furby_errors import report_error

import bpy
import tempfile
import textwrap
import time
from bpy.types import Panel

from .. import icons
from .save_editor_utils import BaseType
from . import station_reference, corvette_optimizer, backup_policy

ADDON_ID = __package__.rsplit(".", 1)[0]


class BBE_OT_backup_settings(bpy.types.Operator):
    bl_idname = 'bbe.backup_settings'
    bl_label = 'Backup Folder Settings'
    bl_description = 'Choose the shared folder for project recovery and game-save backups'
    folder: bpy.props.StringProperty(name='Backup Folder', subtype='DIR_PATH',
                                     description='Blank uses NoMansSkyBaseBuilder/Backups in your home folder')
    retention: bpy.props.IntProperty(name='Backups per Save Slot', min=1, max=500, default=20)

    def backup_location(self, context):
        return str(backup_policy.root_directory(self.folder.strip()))

    def invoke(self, context, event):
        prefs = context.preferences.addons[ADDON_ID].preferences
        self.folder = prefs.nms_backup_folder_path
        self.retention = prefs.nms_backup_retention
        return context.window_manager.invoke_props_dialog(self, width=520, confirm_text='Save Settings')

    def draw(self, context):
        self.layout.prop(self, 'folder')
        self.layout.prop(self, 'retention')
        self.layout.label(text='Shared backup folder:')
        for line in textwrap.wrap(self.backup_location(context), width=62, break_long_words=True):
            self.layout.label(text=line)
        self.layout.label(text='Projects and Game Saves use separate subfolders here.')
        self.layout.label(text='Retention counts complete backup generations per save slot.')
        self.layout.label(text='Changing folders leaves existing backups in their previous location.')

    def execute(self, context):
        path = backup_policy.root_directory(self.folder.strip())
        try:
            path.mkdir(parents=True, exist_ok=True)
            with tempfile.TemporaryFile(dir=path):
                pass
        except OSError as exc:
            report_error(self, {'ERROR'}, f'Backup folder is unavailable: {exc}')
            return {'CANCELLED'}
        prefs = context.preferences.addons[ADDON_ID].preferences
        prefs.nms_backup_folder_path = str(path) if self.folder.strip() else ''
        prefs.nms_backup_retention = self.retention
        if not bpy.app.background:
            bpy.ops.wm.save_userpref()
        return {'FINISHED'}


_refresh_prompt_pending = False
_refresh_generation = 0


def needs_save_refresh(message):
    text = str(message).lower()
    return ('refresh' in text and 'save' in text
            and ('save changed' in text or 'no longer exists' in text))


def prompt_save_refresh(message):
    """Transient attention popup; off-click dismisses without disabling I/O."""
    global _refresh_prompt_pending
    if bpy.app.background or _refresh_prompt_pending:
        return
    _refresh_prompt_pending = True
    window = bpy.context.window
    scene = bpy.context.scene

    def show():
        global _refresh_prompt_pending
        _refresh_prompt_pending = False
        if window not in list(bpy.context.window_manager.windows) or window.scene != scene:
            return
        with bpy.context.temp_override(window=window):
            bpy.ops.bbe.save_refresh_notice('INVOKE_DEFAULT')
    bpy.app.timers.register(show, first_interval=0.05)


class BBE_OT_save_refresh_notice(bpy.types.Operator):
    bl_idname = 'bbe.save_refresh_notice'
    bl_label = 'Refresh Save'
    bl_description = 'Refresh the changed save or click outside to dismiss this notice'
    bl_options = {'INTERNAL'}

    def invoke(self, context, event):
        self._generation = _refresh_generation
        return context.window_manager.invoke_popup(self, width=470)

    def execute(self, context):
        return {'FINISHED'}

    def draw(self, context):
        from ..tools_menu.base_builder_menu_presentation import draw_io_contents
        if self._generation != _refresh_generation:
            draw_io_contents(self.layout, context)
            return
        focus = self.layout.box()
        focus.alert = True
        focus.label(text='The game save has changed.', icon='FILE_REFRESH')
        button = focus.row()
        button.scale_y = 1.8
        button.operator('bbe.refresh_save_counts', text='REFRESH SAVE', icon='FILE_REFRESH')
        self.layout.label(text='Refresh current data, or click outside to dismiss.')
        dimmed = self.layout.column()
        dimmed.enabled = False
        draw_io_contents(dimmed, context)


class BBE_OT_refresh_save_counts(bpy.types.Operator):
    bl_idname = 'bbe.refresh_save_counts'
    bl_label = 'Refresh Save'
    bl_description = 'Read the selected game save point again; this does not change the save'

    def execute(self, context):
        global _refresh_generation
        manager = get_save_data(context)
        if manager is None or manager.get_current_slot_data() is None:
            return {'CANCELLED'}
        try:
            manager.refresh_bases_list()
        except Exception as exc:
            report_error(self, {'ERROR'}, f'Could not refresh save counts: {exc}')
            return {'CANCELLED'}
        _refresh_generation += 1
        for window in context.window_manager.windows:
            for area in window.screen.areas:
                area.tag_redraw()
        self.report({'INFO'}, 'Save refreshed from disk')
        return {'FINISHED'}


def get_save_data(context):
    """The save editor's property group, or None if it is not registered yet."""
    return getattr(context.scene, "nms_save_data", None)


def get_save_folder_path(context):
    """The configured save folder, or None if the preferences are unavailable.

    A draw can run before the addon's preferences exist - during registration,
    or after a disable while the header is still on screen - so this never
    assumes the lookup succeeds.
    """
    addon = context.preferences.addons.get(ADDON_ID)
    if addon is None:
        return None
    return addon.preferences.nms_save_folder_path

def draw_pinned_base(container, save_data, base_props):
    """Draw the pinned base UI section if a base is pinned."""
    if not save_data.pinned_base_check:
        return

    pinned_base_type = save_data.get_base_type_string(save_data.pinned_base_type)
    pinned_box = container

    pinned_content_row = pinned_box.row(align=False)
    pinned_text_col = pinned_content_row.column(align=False)
    pinned_buttons_col = pinned_content_row.column(align=True)

    pinned_text_col.label(
        text=f"{base_props.string_base} ({pinned_base_type})", **icons.ui_icon("PINNED")
    )
    pinned_text_condensed_column = pinned_text_col.column(align=True)
    pinned_text_condensed_column.label(
        text=f"{save_data.pinned_save_slot_name}, (...{save_data.pinned_save_account[-3:]})"
    )

    pinned_buttons_col.scale_x = 0.7
    pinned_buttons_col.operator(
        "object.nms_unpin_base", **icons.ui_icon("UNPINNED"), text=f"Unpin {pinned_base_type}"
    )
    pinned_ready = (save_data.pinned_base_type != BaseType.CORVETTE or
                    (save_data.get_current_slot_data() is not None and
                     save_data.nms_base_type == BaseType.CORVETTE))
    pinned_import = pinned_buttons_col.column(align=True)
    pinned_import.enabled = pinned_ready
    pinned_import.operator(
        "object.import_pinned_base", **icons.ui_icon("IMPORT"), text="Import from Save"
    )

    pinned_export_button_row = pinned_box.row(align=False)
    pinned_export_button_row.enabled = pinned_ready
    pinned_export_button_row.operator(
        "object.export_pinned_base", **icons.ui_icon("FILE_TICK"), text="Export to Save"
    )
    pinned_export_button_backup_row = pinned_box.row(align=True)
    pinned_export_button_backup_row.scale_x = 0.7
    pinned_export_button_backup_row.operator(
        "object.make_pinned_savefile_backup",
        **icons.ui_icon("COLLECTION_NEW"),
        text="Backup Save files",
    )
    if save_data.pinned_base_type == BaseType.CORVETTE:
        pinned_optimize = pinned_box.row()
        pinned_optimize.enabled = pinned_ready
        corvette_optimizer.draw_row(pinned_optimize, pinned=True)
    
def draw_base_picker(container, save_data):
    
    save_folder_path = get_save_folder_path(bpy.context)
    
    # Make a separate section to display elements related to selecting bases.
    save_folder_box = container
    sf_column = save_folder_box.column(align=True)
    sf_enable_row = sf_column.row(align=True)
    sf_enable_row.label(text="Select Save")
    sf_enable_row.operator_context = 'INVOKE_DEFAULT'
    sf_enable_row.operator('bbe.backup_settings', text='', **icons.ui_icon('PREFERENCES'))

    # This row will contain a field where location of save folder is displayed.
    if save_data.check_plugin_enabled and save_data.validate_save_folder( save_folder_path ):
        # Button to choose path to save folder.
        sf_enable_row.operator(
            "object.nms_select_save_folder", text="", **icons.ui_icon("FILE_FOLDER")
        )

    # A button to enable the save editor, this will also install additional
    # dependencies required when pressed.
    sf_enable_row.separator()
    sf_enable_button_row = sf_enable_row.row(align=True)
    sf_enable_button_row.scale_x = 0.7 if not save_data.check_plugin_enabled else 1.0
    sf_enable_icon = "TRIA_DOWN" if not save_data.check_plugin_enabled else "TRIA_UP"
    sf_enable_text = "Enable" if not save_data.check_plugin_enabled else ""
    sf_enable_button_row.prop(
        save_data, "check_plugin_enabled", **icons.ui_icon(sf_enable_icon), text=sf_enable_text
    )

    # Everything below is the Select Save section, which only applies once the
    # save editor is switched on.
    if not save_data.check_plugin_enabled:
        return

    if save_data.session_status:
        for line in textwrap.wrap(save_data.session_status, 58):
            sf_column.label(text=line, icon='INFO')

    if not save_data.validate_save_folder(save_folder_path):
        sf_column.separator()
        select_folder_info_col = sf_column.column(align=True)
        select_folder_info_col.scale_y = 0.8
        select_folder_info_col.label(text=" Save Folder should end with")
        select_folder_info_col.label(text=r' path like : "...\HelloGames\NMS"')
        sf_column.separator()
        select_folder_button_col = sf_column.column(align=True)
        select_folder_button_col.alert = True
        select_folder_button_col.operator(
            "object.nms_select_save_folder",
            text="Select Save Folder",
            **icons.ui_icon("FILE_FOLDER"),
        )
        return

    sf_column.separator()
    # Display list of accounts, will display steam ids for recognition.
    sf_column.label(text="1. Account")
    sf_column.prop(save_data, "nms_account_selected", **icons.ui_icon("COMMUNITY"))
    # Account selection only populates the save-slot list. Make the second
    # required choice visible before the build controls can be shown.
    sf_column.label(text="2. Save Slot")
    slot_row = sf_column.row(align=True)
    slot_row.alert = save_data.nms_account_selected != 'Default' and save_data.nms_save_slot == 'Default'
    slot_row.enabled = save_data.nms_account_selected != 'Default'
    slot_row.prop(save_data, "nms_save_slot", **icons.ui_icon("LINENUMBERS_ON"))
    if save_data.get_current_slot_data() is not None and not save_data.is_base_data_loaded():
        slot_row.operator('bbe.refresh_save_counts', text='Refresh Save', **icons.ui_icon('FILE_REFRESH'))
    if save_data.nms_account_selected != 'Default' and save_data.nms_save_slot == 'Default':
        if len(type(save_data).enum_save_slots_list) <= 1:
            sf_column.label(text="No readable save slots found in this account.", **icons.ui_icon("ERROR"))
        else:
            sf_column.label(text="Choose a save slot above to show ship imports.", **icons.ui_icon("INFO"))

    # Section where bases can be selected to import/update/pin. This section
    # will only be visible when the base list has been loaded.
    if not save_data.is_base_data_loaded():
        if save_data.nms_account_selected != 'Default':
            unavailable = sf_column.column(align=True)
            unavailable.enabled = False
            unavailable.operator("object.nms_import_base_from_save", **icons.ui_icon("IMPORT"), text="Import from Save")
        return

    # Display backup buttons when a slot is selected.
    base_type = save_data.get_base_type_string(save_data.nms_base_type)
    backup_row = sf_column.row(align=True)
    backup_row.operator(
        "object.make_savefile_backup", **icons.ui_icon("COLLECTION_NEW"), text="Backup Saves"
    )
    backup_row.operator(
        "object.open_backup_folder", **icons.ui_icon("FOLDER_REDIRECT"), text="Open Slot Backups"
    )
    try:
        path = backup_policy.directory(save_data.get_current_slot_data()['saves'])
        sf_column.label(text=f'Backups: {path}', **icons.ui_icon('FILE_FOLDER'))
    except (KeyError, TypeError, ValueError):
        pass
    duplicate_row = sf_column.row(align=True)
    duplicate_row.operator_context = 'INVOKE_DEFAULT'
    duplicate_row.operator('bbe.ship_duplicate', **icons.ui_icon('DUPLICATE'), text='Duplicate Save...')

    sf_column.separator()
    slot_total = int(save_data.get_total_parts_count())
    count_row = sf_column.row(align=True)
    count_row.label(text=f"\U0001F4E6 Save slot total (owned builds): {slot_total}")
    count_row.operator('bbe.refresh_save_counts', text='Refresh Save', **icons.ui_icon('FILE_REFRESH'))
    source = save_data.extracted_base_data
    if source.get('source_file'):
        read_at = time.strftime('%b %d, %I:%M %p', time.localtime(source['source_mtime']))
        sf_column.label(text=f"Read from {source['source_file']} ({read_at})", **icons.ui_icon('INFO'))
    sf_column.label(text=f"Current Blender scene: {bpy.context.scene.nms_build_tool.get_part_count()} parts")
    se_column = sf_column.column(align=True)
    se_column.label(text="Base Type:")
    # Radio buttons to select type of base.
    base_type_row = se_column.row(align=True)
    base_type_row.prop(save_data, "nms_base_type", expand=True, text="base type")
    se_column.separator()

    # List of bases/corvettes.
    se_column.label(text=f"{base_type} Selected:")

    # Show the base list in red when no base/corvette is selected.
    base_index_row = se_column.row(align=True)
    selected = save_data.has_selected_base()
    base_index_row.alert = not selected
    if save_data.nms_base_type == BaseType.CORVETTE:
        from . import corvette_io
        corvette_io.draw_picker(base_index_row, save_data)
    else:
        base_index_row.prop(save_data, "nms_base_index", text="", **icons.ui_icon("GEOMETRY_SET"))
    selected_data = save_data.get_current_base_identifiers() if selected else None
    if save_data.nms_base_type == BaseType.CORVETTE:
        if selected_data is not None:
            slot = selected_data.user_data
            position = f'Slot {slot + 1}' if type(slot) is int and 0 <= slot < 12 else 'Unlinked build'
            se_column.label(text=f'{position}: {selected_data.parts_count} parts')
        # Edit the existing scene metadata used by both export paths. The saved
        # name is only a placeholder; choosing a destination must not rename
        # the current Blender design or write anything into the game save.
        from .. import build_metadata
        build_metadata.draw_name(se_column, bpy.context.scene.nms_base_tool, text='Ship Name',
                       placeholder=selected_data.base_name if selected_data else 'Name for exported Corvette')
    elif selected_data is not None:
        se_column.label(text=f"Selected {base_type} in save: {selected_data.parts_count} parts")
    if selected_data is not None and selected_data.base_type != BaseType.EXTERNAL_BASE:
        se_column.label(text=f"Other owned builds in save: {slot_total - selected_data.parts_count} parts")

    # Display buttons when a base is selected from the list.
    if selected and save_data.nms_base_type != BaseType.EXTERNAL_BASE:
        # Pin a base without importing it to the scene, so that save data can
        # be updated to the location marked by it.
        base_index_pin_row = base_index_row.row(align=True)
        base_index_pin_row.scale_x = 0.6
        base_index_pin_row.operator(
            "object.nms_pin_base", **icons.ui_icon("PINNED"), text=" Pin for easy-access"
        )

    if save_data.nms_base_type == BaseType.CORVETTE:
        corvette_io.draw_status(se_column, save_data)
        if save_data.extracted_base_data.get('missing_corvettes'):
            notice = se_column.row(); notice.alert = True
            notice.label(text='Missing Corvette builds: open the list to review / repair.', icon='ERROR')
    se_column.separator()
    import_export_row = se_column.row(align=True)
    import_row = import_export_row.row(align=True)
    import_row.enabled = selected
    # Import button, this button will import the base to the scene.
    import_row.operator(
        "object.nms_import_base_from_save", **icons.ui_icon("IMPORT"), text="Import from Save"
    )

    if save_data.nms_base_type != BaseType.EXTERNAL_BASE:
        export_row = import_export_row.row(align=True)
        export_row.operator_context = 'INVOKE_DEFAULT'
        is_corvette = save_data.nms_base_type == BaseType.CORVETTE
        export_row.enabled = selected or is_corvette
        export_row.operator('bbe.corvette_export' if is_corvette else 'object.nms_export_base_to_save',
                            **icons.ui_icon('EXPORT'), text='Export to Save...')

    # Standalone file export uses the build currently in Blender, independent
    # of save-slot selection and never writes the game save.
    file_export = se_column.column(align=True)
    file_export.operator('bbe.export_ship_file', text='Export Scene to .nmsship...', **icons.ui_icon('EXPORT'))
    file_export.operator('bbe.export_base_file', text='Export Scene to .nmsbase...', **icons.ui_icon('EXPORT'))

    if any(obj.get('ObjectID') == 'BASE_BUBPIPE_L' for obj in bpy.context.scene.objects):
        warning = se_column.column(align=True)
        warning.alert = True
        warning.label(text='Old bubble corners must be converted before export.', icon='ERROR')
        warning.operator('bbe.convert_legacy_bubble_corners', text='Convert Old Bubble Corners...', icon='MODIFIER')

    if save_data.nms_base_type == BaseType.STATION:
        station_reference.draw(se_column, bpy.context)
    elif save_data.nms_base_type == BaseType.CORVETTE:
        optimize_row = se_column.row()
        corvette_optimizer.draw_row(optimize_row)


def draw_save_manager(layout, context):
    """The entire save manager UI, drawn into whatever layout is passed in.

    Shared by the sidebar panel below and the header dropdown in
    presentation/save_manager_menu.py, so it takes a layout rather than
    reading self.layout off a particular panel.
    """
    save_data = get_save_data(context)
    base_props = getattr(context.scene, "nms_base_tool", None)
    save_folder_path = get_save_folder_path(context)

    if save_data is None or base_props is None or save_folder_path is None:
        layout.label(text="Save Manager unavailable", **icons.ui_icon("ERROR"))
        return

    # Display data related to a pinned base on top if there is any within a
    # blend file.
    if save_data.pinned_base_check:
        draw_pinned_base(layout.box(),save_data,base_props)

    draw_base_picker(layout.box(), save_data)


# Save Editor Panel ---
class NMS_PT_save_editor_panel(Panel):
    bl_idname = "NMS_PT_save_editor_panel"
    bl_label = 'Save Manager'
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "No Mans Sky Base Builder"
    bl_options = {'DEFAULT_CLOSED'}
    bl_context = "objectmode"

    @classmethod
    def poll(self, context):
        return True

    def draw_header(self, context):
        icons.draw_panel_icon(self.layout, 'save')

    def draw(self, context):
        draw_save_manager(self.layout, context)
