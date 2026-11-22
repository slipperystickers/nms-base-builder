"""Shared Save Manager controls for the viewport header and sidebar."""
from .. import i18n
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
    bl_translation_context = "BBEExtendedInterface"
    bl_label = 'Backup Folder Settings'
    bl_description = 'Choose the shared folder for project recovery and game-save backups'
    folder: bpy.props.StringProperty(name='Backup Folder', subtype='DIR_PATH',
                                     description='Blank uses NoMansSkyBaseBuilder/Backups in your home folder')
    retention: bpy.props.IntProperty(name='Backups per Save Slot', min=1, max=500, default=20)
    retention_input: bpy.props.StringProperty(options={'HIDDEN', 'SKIP_SAVE'})

    def backup_location(self, context):
        return str(backup_policy.root_directory(self.folder.strip()))

    def invoke(self, context, event):
        prefs = context.preferences.addons[ADDON_ID].preferences
        self.folder = prefs.nms_backup_folder_path
        self.retention = prefs.nms_backup_retention
        self.retention_input = str(self.retention)
        self._default_folder = str(backup_policy.root_directory(''))
        self._original_folder = self.folder.strip()
        from ..build_editors import BackupFolderEditor, open_editor
        return open_editor(self, context, event, BackupFolderEditor, 520, 'Save settings')

    def modal(self, context, event):
        return self._editor.modal(context, event)

    def cancel(self, context):
        editor = getattr(self, '_editor', None)
        if editor and not editor.closed:
            editor.finish()

    def draw(self, context):
        layout = i18n.localized_layout(self.layout)
        folder = layout.box()
        folder.label(text='Backup location', icon='FILE_FOLDER')
        folder.prop(self, 'folder', text='')
        if not self.folder.strip():
            for line in textwrap.wrap(self._default_folder, width=62):
                folder.label(text=line)
        folder.label(text='Existing backups stay in the previous folder.' if self.folder.strip() != self._original_folder
                     else 'Projects and game saves use separate subfolders.')
        history = layout.box()
        history.label(text='Game-save history', icon='TIME')
        history.prop(self, 'retention')
        history.label(text='Each backup is a complete copy of that slot’s save files.')

    def execute(self, context):
        try:
            path = backup_policy.root_directory(self.folder.strip())
            path.mkdir(parents=True, exist_ok=True)
            with tempfile.TemporaryFile(dir=path):
                pass
        except (OSError, ValueError, RuntimeError) as exc:
            message = f'Choose a writable folder. {getattr(exc, "strerror", None) or str(exc)}'
            editor = getattr(self, '_editor', None)
            if editor:
                editor.error = message
            else:
                report_error(self, {'ERROR'}, message)
            return {'CANCELLED'}
        prefs = context.preferences.addons[ADDON_ID].preferences
        prefs.nms_backup_folder_path = str(path) if self.folder.strip() else ''
        prefs.nms_backup_retention = self.retention
        if not bpy.app.background:
            bpy.ops.wm.save_userpref()
        return {'FINISHED'}


class BBE_OT_choose_backup_folder(bpy.types.Operator):
    bl_idname = 'bbe.choose_backup_folder'
    bl_label = 'Choose Backup Folder'
    bl_options = {'INTERNAL'}
    directory: bpy.props.StringProperty(subtype='DIR_PATH', options={'SKIP_SAVE'})
    filter_folder: bpy.props.BoolProperty(default=True, options={'HIDDEN'})

    def invoke(self, context, event):
        from ..build_editors import BackupFolderEditor
        from ..menu_surface import _sessions
        editor = _sessions.get(context.area.as_pointer())
        if not isinstance(editor, BackupFolderEditor) or editor.browsing:
            return {'CANCELLED'}
        self._editor = editor
        try:
            self.directory = editor.modal_owner.backup_location(context)
        except (OSError, ValueError, RuntimeError):
            self.directory = editor.modal_owner._default_folder
        editor.browsing = True
        try:
            context.window_manager.fileselect_add(self)
        except RuntimeError:
            editor.browsing = False
            raise
        return {'RUNNING_MODAL'}

    def execute(self, context):
        editor = getattr(self, '_editor', None)
        if not editor or editor.closed:
            return {'CANCELLED'}
        editor.modal_owner.folder = self.directory
        editor.error = ''
        self.cancel(context)
        return {'FINISHED'}

    def cancel(self, context):
        editor = getattr(self, '_editor', None)
        if editor and not editor.closed:
            editor.browsing = False
            with context.temp_override(window=editor.window, area=editor.area, region=editor.region):
                editor.rebuild(context)


_refresh_prompt_pending = False
_refresh_generation = 0


def needs_save_refresh(message):
    text = str(message).lower()
    return ('refresh' in text and 'save' in text
            and ('save changed' in text or 'no longer exists' in text))


def prompt_save_refresh(message):
    """Open a dismissible refresh dialog without disabling I/O."""
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
    bl_translation_context = "BBEExtendedInterface"
    bl_label = 'Refresh Save'
    bl_description = 'Refresh the changed save or cancel this notice'
    bl_options = {'INTERNAL'}

    def invoke(self, context, event):
        self._generation = _refresh_generation
        # A child operator inside invoke_popup leaves that popup alive after
        # refresh and Blender redraws it as a second I/O menu. The dialog's
        # own confirmation closes when execute finishes.
        return context.window_manager.invoke_props_dialog(
            self, width=470, confirm_text='REFRESH SAVE', cancel_default=True)

    def execute(self, context):
        if self._generation != _refresh_generation:
            return {'FINISHED'}
        return bpy.ops.bbe.refresh_save_counts('EXEC_DEFAULT')

    def draw(self, context):
        if self._generation != _refresh_generation:
            i18n.localized_layout(self.layout).label(text='The save has already been refreshed.', icon='CHECKMARK')
            return
        focus = i18n.localized_layout(self.layout).box()
        focus.alert = True
        focus.label(text='The game save has changed.', icon='FILE_REFRESH')
        focus.label(text='Press REFRESH SAVE below to reload the selected save.')
        i18n.localized_layout(self.layout).label(text='This only reads the save from disk; it does not edit it.')


class BBE_OT_refresh_save_counts(bpy.types.Operator):
    bl_idname = 'bbe.refresh_save_counts'
    bl_translation_context = "BBEExtendedInterface"
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

def draw_base_picker(container, save_data, narrow=False, *, sidebar_width=None):
    save_folder_path = get_save_folder_path(bpy.context)
    
    # Make a separate section to display elements related to selecting bases.
    save_folder_box = container
    sf_column = save_folder_box.column(align=True)
    if not save_data.check_plugin_enabled:
        from .. import build_timer
        return

    if save_data.session_status:
        for line in textwrap.wrap(save_data.session_status, 58):
            sf_column.label(text=line, icon='INFO')

    if not save_data.validate_save_folder(save_folder_path):
        sf_column.separator()
        select_folder_info_col = sf_column.column(align=True)
        select_folder_info_col.scale_y = 0.8
        select_folder_info_col.label(text="Choose the HelloGames/NMS folder")
        select_folder_info_col.label(text="or a GOG DefaultUser or Steam st_ account.")
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
    if sidebar_width:
        sf_column.prop(save_data, "nms_account_selected", text="Account")
        slot_row = sf_column.row(align=True)
        slot_row.enabled = save_data.nms_account_selected != 'Default'
        slot_row.prop(save_data, "nms_save_slot", text="Save Slot")
    else:
        account_row = sf_column.split(factor=0.20, align=True)
        account_row.label(text="1. Account")
        account_row.prop(save_data, "nms_account_selected", text="", **icons.ui_icon("COMMUNITY"))
        slot_row = sf_column.split(factor=0.20, align=True)
        slot_row.alert = save_data.nms_account_selected != 'Default' and save_data.nms_save_slot == 'Default'
        slot_row.enabled = save_data.nms_account_selected != 'Default'
        slot_row.label(text="2. Save Slot")
        slot_row = (slot_row.split(factor=0.77, align=True) if save_data.is_base_data_loaded()
                    else slot_row.row(align=True))
        slot_row.prop(save_data, "nms_save_slot", text="", **icons.ui_icon("LINENUMBERS_ON"))
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
        from .. import build_timer
        if save_data.nms_account_selected != 'Default':
            unavailable = sf_column.column(align=True)
            unavailable.enabled = False
            unavailable.operator("object.nms_import_base_from_save", **icons.ui_icon("IMPORT"), text="Import from Save")
        return

    # Display backup buttons when a slot is selected.
    base_type = ("External Base" if save_data.nms_base_type == BaseType.EXTERNAL_BASE
                 else save_data.get_base_type_string(save_data.nms_base_type))
    (sf_column if sidebar_width else slot_row).label(text=f"{int(save_data.get_total_parts_count())} parts")
    backup_row = sf_column.row(align=True)
    backup_row.operator_context = 'INVOKE_DEFAULT'
    backup_row.operator("object.make_savefile_backup", **icons.ui_icon("COLLECTION_NEW"), text="Backup")
    backup_row.operator("object.open_backup_folder", **icons.ui_icon("FOLDER_REDIRECT"), text="Slot Backups")
    actions = sf_column.row(align=True) if narrow else backup_row
    actions.operator_context = 'INVOKE_DEFAULT'
    actions.operator('bbe.ship_duplicate', **icons.ui_icon('DUPLICATE'), text='Duplicate...')
    actions.operator('bbe.refresh_save_counts', **icons.ui_icon('FILE_REFRESH'), text='Refresh Save')
    source = save_data.extracted_base_data
    if source.get('source_file'):
        read_at = time.strftime('%b %d, %I:%M %p', time.localtime(source['source_mtime']))
        sf_column.label(text=f"Read from {source['source_file']} ({read_at})", **icons.ui_icon('INFO'))
    se_column = sf_column.column(align=True)
    from .. import build_timer
    scene = bpy.context.scene
    target = build_timer.selected_key(save_data)
    if not sidebar_width:
        se_column.label(text="Base Type:")
    # Radio buttons to select type of base.
    base_type_row = (se_column.grid_flow(columns=max(2,min(5,int(sidebar_width/76))), even_columns=True,align=True)
                     if sidebar_width else se_column.row(align=True))
    for kind in (BaseType.CORVETTE, BaseType.BASE, BaseType.SPACE_BASE, BaseType.STATION, BaseType.EXTERNAL_BASE):
        label = {"text": "External"} if sidebar_width and kind == BaseType.EXTERNAL_BASE else {}
        base_type_row.prop_enum(save_data, "nms_base_type", kind, **label)
    se_column.separator()

    heading = se_column.row(align=True)
    heading.label(text=base_type if sidebar_width else f"{base_type} Selected:")
    timer = heading.column(align=True)
    timer.alignment = 'RIGHT'
    build_timer.draw_labeled(timer, scene, scene.get(build_timer.SCENE_KEY) or target)

    # List of bases/corvettes.
    compact_ship = not narrow and save_data.nms_base_type == BaseType.CORVETTE
    if compact_ship:
        fields = se_column.split(factor=0.58, align=True)
        picker = fields.column(align=True)
        name_field = fields.column(align=True)

    else:
        picker = name_field = se_column
    base_index_row = picker.row(align=True)
    selected = save_data.has_selected_base()
    base_index_row.alert = not selected
    if save_data.nms_base_type == BaseType.CORVETTE:
        from . import corvette_io
        base_index_row.prop(save_data, 'nms_base_index', text='')
        add = picker.row(align=True)
        add.operator_context = 'INVOKE_DEFAULT'
        add.operator('bbe.io_add_minimal_corvette', text='Add Minimal Corvette', icon='ADD')
    else:
        base_index_row.prop(save_data, "nms_base_index", text="", **icons.ui_icon("GEOMETRY_SET"))
    selected_data = save_data.get_current_base_identifiers() if selected else None
    if save_data.nms_base_type == BaseType.CORVETTE:
        # Edit the existing scene metadata used by both export paths. The saved
        # name is only a placeholder; choosing a destination must not rename
        # the current Blender design or write anything into the game save.
        from .. import build_metadata
        build_metadata.draw_name(name_field, bpy.context.scene.nms_base_tool, text='Name' if compact_ship else 'Ship Name',
                       placeholder=selected_data.base_name if selected_data else 'Name for exported Corvette')
    if save_data.nms_base_type == BaseType.CORVETTE:
        corvette_io.draw_status(se_column, save_data)
        if save_data.extracted_base_data.get('missing_corvettes'):
            notice = se_column.row(); notice.alert = True
            notice.menu('BBE_MT_corvette_picker', text='Review / Repair Missing Corvette Builds', icon='ERROR')
    se_column.separator()
    import_export_row = se_column.column(align=True) if sidebar_width and sidebar_width < 300 else se_column.row(align=True)
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

    if any(obj.get('ObjectID') == 'BASE_BUBPIPE_L' for obj in bpy.context.scene.objects):
        warning = se_column.column(align=True)
        warning.alert = True
        warning.label(text='Old bubble corners must be converted before export.', icon='ERROR')
        warning.operator('bbe.convert_legacy_bubble_corners', text='Convert Old Bubble Corners...', icon='MODIFIER')

    if save_data.nms_base_type == BaseType.STATION:
        station_reference.draw(se_column, bpy.context)
    elif save_data.nms_base_type == BaseType.CORVETTE:
        optimize_row = se_column.row()
        optimize_row.scale_y = 1.0
        corvette_optimizer.draw_row(optimize_row)


def draw_save_manager(layout, context, heading=False, *, sidebar_width=None):
    from .function_help import corner_help
    save_data = get_save_data(context)
    header=layout.row(align=True)
    heading_row=header.row(align=True);heading_row.alignment='LEFT'
    if not sidebar_width or save_data is None:
        heading_row.label(text='Save Manager', **icons.ui_icon('FILE_TICK'))
    if save_data is not None:
        label = ''
        if sidebar_width:
            label = 'Save Manager'
        elif context.region.type == 'UI':
            label = 'On' if save_data.check_plugin_enabled else 'Off'
        heading_row.prop(save_data, 'check_plugin_enabled', text=label, toggle=True)
    tools=header.row(align=True);tools.alignment='RIGHT'
    tools.operator_context='INVOKE_DEFAULT'
    tools.operator('bbe.backup_settings', text='', **icons.ui_icon('PREFERENCES'))
    tools.operator('object.nms_select_save_folder', text='', **icons.ui_icon('FILE_FOLDER'))
    corner_help(tools, 'IO')
    base_props = getattr(context.scene, "nms_base_tool", None)
    save_folder_path = get_save_folder_path(context)

    from .. import base_boundary
    base_boundary.draw(layout, context)
    build = layout.box()
    available = save_data is not None and base_props is not None and save_folder_path is not None
    if available:
        region = context.region
        narrow = (region and region.type == 'UI' and
                  region.width < 400 * context.preferences.system.ui_scale)
        if sidebar_width is not None:
            narrow = sidebar_width < 400
        draw_base_picker(build, save_data, narrow, sidebar_width=sidebar_width)
    else:
        build.label(text="Save Manager unavailable", **icons.ui_icon("ERROR"))

    # Charon integration is retained but intentionally hidden in regular BBE.
    if not available:
        return
    if not save_data.check_plugin_enabled:
        layout.label(text="Enable to choose a save and access its tools.", **icons.ui_icon("INFO"))
    elif save_data.get_current_slot_data() is not None:
        layout.separator()
        advanced = layout.column(align=True)
        advanced.label(text='Advanced save tools', **icons.ui_icon('WARNING_LARGE'))
        advanced.operator_context = 'INVOKE_DEFAULT'
        ship = advanced.column(align=True)
        ship.enabled = save_data.nms_base_type == BaseType.CORVETTE
        ship.operator('bbe.ship_management', text='Ship Management (Beta)',
                      **icons.ui_icon('OUTLINER_OB_LIGHTPROBE'))
        advanced.operator('bbe.buildable_unlocks', text='Account Item Unlock and Currency Modify',
                          **icons.ui_icon('UNLOCKED'))
        advanced.operator('bbe.raw_save_json', text='Raw Save JSON Viewer / Editor',
                          **icons.ui_icon('TEXT'))


# Save Editor Panel ---
class NMS_PT_save_editor_panel(Panel):
    bl_idname = "NMS_PT_save_editor_panel"
    bl_translation_context = "BBEExtendedInterface"
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
        from .. import sidebar_builder
        sidebar_builder.begin_header(self, context, 'saves')
        icons.draw_panel_icon(i18n.localized_layout(self.layout), 'save')

    def draw(self, context):
        from .. import sidebar_builder
        if not sidebar_builder.draw_inline(self, context, 'saves'):
            draw_save_manager(i18n.localized_layout(self.layout), context)
