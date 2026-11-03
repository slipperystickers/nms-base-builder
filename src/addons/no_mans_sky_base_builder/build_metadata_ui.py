"""Explicit Apply/Cancel editor for advanced build ownership metadata."""
import copy
from .build_metadata import OWNER_FIELDS, encode, edited_owner, field_text, approve_save_owner, clear_save_approvals, ownership_sources
from pathlib import Path
import bpy
from bpy.app.handlers import persistent

_dialogs = {}
_empty_donors = [('NONE', 'Choose a saved Corvette', '')]


def dialog_key(operator):
    properties = getattr(operator, 'properties', operator)
    return properties.as_pointer() if hasattr(properties, 'as_pointer') else id(operator)


def live_dialog(operator):
    # RNA update/enum callbacks receive a different Python wrapper from invoke.
    return _dialogs.get(dialog_key(operator), operator)


@persistent
def reset_save_approval(_=None):
    # PropertyGroup SKIP_SAVE is not a reliable .blend boundary. Approval is
    # deliberately cleared on file load and add-on enable, in every scene.
    clear_save_approvals()
    _dialogs.clear()
    scenes = getattr(bpy.data, 'scenes', None)
    if scenes is None:
        return 0.1  # Add-on enable can run under Blender's restricted data context.
    for scene in scenes:
        props = getattr(scene, 'nms_base_tool', None)
        if props is not None:
            props.metadata_owner_to_save = False
            props.metadata_owner_reviewed = ''


def register_handlers():
    if reset_save_approval not in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.append(reset_save_approval)
    if reset_save_approval() is not None and not bpy.app.timers.is_registered(reset_save_approval):
        bpy.app.timers.register(reset_save_approval, first_interval=0.0)


def unregister_handlers():
    if reset_save_approval in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.remove(reset_save_approval)
    if bpy.app.timers.is_registered(reset_save_approval):
        bpy.app.timers.unregister(reset_save_approval)
    reset_save_approval()


def donor_items(self, context):
    # Keep strings alive for Blender's dynamic EnumProperty. No file I/O in draw.
    return getattr(live_dialog(self), '_donor_items', _empty_donors)


def selected_save_paths(context):
    slot = context.scene.nms_save_data.get_current_slot_data()
    paths = list(dict.fromkeys(str(Path(p)) for p in (slot or {}).get('saves', []) if p and Path(p).is_file()))
    if not paths:
        raise ValueError('Choose an account and save slot in I/O first.')
    return paths


def set_owner_fields(self, owner):
    self._owner_source = copy.deepcopy(owner)
    for key in OWNER_FIELDS:
        setattr(self, 'owner_' + key.lower(), field_text(owner.get(key)))


def select_donor(self, context):
    self = live_dialog(self)
    donor = getattr(self, '_donors', {}).get(self.owner_donor)
    if donor is not None:
        set_owner_fields(self, donor[1])


def toggle_copy(self, context):
    self = live_dialog(self)
    if not hasattr(self, '_original'):
        return
    self._donor_error = ''
    if not self.copy_owner:
        set_owner_fields(self, self._original.get('Owner', {}))
        return
    try:
        from .save_editor import ship_files
        paths = selected_save_paths(context)
        root, hashes, _ = ship_files.read(paths)
        self._donors = ownership_sources(root)
        self._donor_paths, self._donor_hashes = paths, hashes
        self._donor_items = [('NONE', 'Choose a saved Corvette', '')] + [
            (key, label, 'Copy its complete Owner record into these fields')
            for key, (label, owner) in self._donors.items()]
        self.owner_donor = 'NONE'
        if not self._donors:
            raise ValueError('This save has no unambiguously linked Corvette Owner records.')
    except (OSError, ValueError, KeyError, TypeError) as exc:
        self._donor_error = str(exc)


class BBE_OT_build_metadata(bpy.types.Operator):
    bl_idname = 'bbe.build_metadata'
    bl_label = 'Advanced Build Metadata'
    bl_description = 'Edit this build\'s Owner record and metadata; changes apply to this Blender project first'
    bl_options = {'UNDO'}
    owner_usn: bpy.props.StringProperty(name='Owner name (USN)')
    owner_uid: bpy.props.StringProperty(name='User ID (UID)')
    owner_lid: bpy.props.StringProperty(name='LID')
    owner_ptk: bpy.props.StringProperty(name='PTK')
    owner_ts: bpy.props.StringProperty(name='Owner timestamp (TS)')
    copy_owner: bpy.props.BoolProperty(name='Copy ownership from another saved ship', default=False,
        description='Read a Corvette from the save selected in I/O; review its ownership below before applying',
        update=toggle_copy)
    owner_donor: bpy.props.EnumProperty(name='Source ship', items=donor_items, update=select_donor)
    last_editor_id: bpy.props.StringProperty(name='Last editor ID')
    last_editor_name: bpy.props.StringProperty(name='Last editor name')
    owner_to_save: bpy.props.BoolProperty(name='Include this Owner when exporting to a game save', default=False,
        description='Explicitly update the chosen destination build Owner on your next confirmed export; importing a build never enables this')

    def invoke(self, context, event):
        props = context.scene.nms_base_tool
        _dialogs.pop(dialog_key(self), None)
        self.copy_owner = False
        self._donors = {}
        self._donor_error = ''
        self._donor_items = [('NONE', 'Choose a saved Corvette', '')]
        self._scene = context.scene
        self._original = props.serialise()
        self._signature = encode(self._original)
        _dialogs[dialog_key(self)] = self
        owner = self._original.get('Owner', {})
        if not isinstance(owner, dict):
            _dialogs.pop(dialog_key(self), None)
            self.report({'ERROR'}, 'This build has an unsupported Owner record; no metadata changed.')
            return {'CANCELLED'}
        set_owner_fields(self, owner)
        self.last_editor_id = field_text(self._original.get('LastEditedById'))
        self.last_editor_name = field_text(self._original.get('LastEditedByUsername'))
        self.owner_to_save = props.metadata_owner_to_save
        return context.window_manager.invoke_props_dialog(self, width=570, confirm_text='Apply to Build')

    def draw(self, context):
        state = live_dialog(self)
        layout = self.layout
        layout.label(text='Edit this build\'s Owner record. Ship slot links stay unchanged.', icon='INFO')
        layout.label(text='Full build files and clipboard exports retain these fields.')
        layout.prop(self, 'copy_owner')
        if getattr(self, 'copy_owner', False):
            layout.prop(self, 'owner_donor')
            if getattr(state, '_donor_error', ''):
                layout.label(text=state._donor_error, icon='ERROR')
            layout.label(text='Copies ownership only. The source ship stays unchanged.')
        column = layout.column(align=True)
        for key in OWNER_FIELDS:
            column.prop(self, 'owner_' + key.lower())
        if not getattr(self, 'owner_usn', ''):
            layout.label(text='No owner name (USN) is stored here; IDs may still identify the owner.', icon='INFO')
        layout.separator()
        layout.prop(self, 'last_editor_name')
        layout.prop(self, 'last_editor_id')
        layout.separator()
        layout.prop(self, 'owner_to_save')
        layout.label(text='Unchecked: game-save exports keep the destination Owner.')
        layout.label(text='Apply changes this project. Export confirmation writes the save.')
        layout.label(text='Other imported metadata and extra Owner fields are preserved.')

    def execute(self, context):
        try:
            props = context.scene.nms_base_tool
            if (not hasattr(self, '_original') or context.scene != self._scene
                    or encode(props.serialise()) != self._signature):
                raise ValueError('The build changed. Reopen Advanced Build Metadata and review it again.')
            if getattr(self, 'copy_owner', False):
                if self._donor_error or self.owner_donor not in self._donors:
                    raise ValueError(self._donor_error or 'Choose a source ship before applying ownership.')
                from .save_editor import ship_files
                if (selected_save_paths(context) != self._donor_paths
                        or ship_files.hashes(self._donor_hashes) != self._donor_hashes):
                    raise ValueError('The source save changed. Reopen metadata and choose the source ship again.')
            owner = edited_owner(self._owner_source,
                {key: getattr(self, 'owner_' + key.lower()) for key in OWNER_FIELDS})
            updated = copy.deepcopy(self._original)
            updated['Owner'] = owner
            for key, text in (('LastEditedById', self.last_editor_id),
                              ('LastEditedByUsername', self.last_editor_name)):
                if text != field_text(self._original.get(key)):
                    updated[key] = text
            props.deserialise_from_data(updated)
            approve_save_owner(props, self.owner_to_save)
        except (OSError, ValueError, TypeError) as exc:
            self.report({'ERROR'}, str(exc))
            _dialogs.pop(dialog_key(self), None)
            return {'CANCELLED'}
        _dialogs.pop(dialog_key(self), None)
        self.report({'INFO'}, 'Build metadata updated in this project.')
        return {'FINISHED'}

    def cancel(self, context):
        _dialogs.pop(dialog_key(self), None)


classes = (BBE_OT_build_metadata,)
