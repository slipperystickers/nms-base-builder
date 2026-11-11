"""Early Corvette warnings and reviewed repairs from the shared I/O controls."""
from pathlib import Path
import textwrap
from uuid import uuid4
import bpy
from bpy.app.handlers import persistent
from . import ship_core as core, ship_repair, ship_files, ship_management
from .save_editor_utils import BaseType
from ..furby_errors import report_error

_reviews = {}


def cache_key(data):
    cache = data.extracted_base_data
    return '|'.join((str(data.nms_account_selected), str(data.nms_save_slot),
                     cache.get('source_path', ''), cache.get('source_hash', '')))


def entries(data):
    return [base for base in data.extracted_base_data.get('corvettes', [])
            if base.base_type == BaseType.CORVETTE]


def identifier(base):
    return f'Season:{base.base_index}' if base.save_context == 'Season' else str(base.base_index)


def label(base):
    if type(base.user_data) is int and 0 <= base.user_data < 12:
        prefix = f'Slot {base.user_data + 1}: '
    else:
        prefix = 'Unlinked: '
    return f'{prefix}{base.base_name} [{base.parts_count} parts]'


def repair_button(layout, data, ctx, index, base_index=-1):
    layout.operator_context = 'INVOKE_DEFAULT'
    if base_index >= 0:
        op = layout.operator('bbe.corvette_repair_keep', text='Repair — Keep My Build...', icon='TOOL_SETTINGS')
        op.context_name = ctx; op.index = index; op.base_index = base_index
        op.expected = cache_key(data)
    op = layout.operator('bbe.corvette_repair_file', text='Replace From File...', icon='FILE_FOLDER')
    op.context_name = ctx; op.index = index; op.base_index = base_index
    op.expected = cache_key(data)


class BBE_OT_select_corvette(bpy.types.Operator):
    bl_idname = 'bbe.select_corvette'
    bl_label = 'Select Corvette'
    value: bpy.props.StringProperty()
    expected: bpy.props.StringProperty()
    explanation: bpy.props.StringProperty()

    @classmethod
    def description(cls, context, properties):
        return properties.explanation or 'Select this build from the save'

    def execute(self, context):
        data = context.scene.nms_save_data
        if self.expected != cache_key(data) or data.nms_base_type != BaseType.CORVETTE:
            self.report({'WARNING'}, 'Save selection changed. Reopen the Corvette list.')
            return {'CANCELLED'}
        if self.value != 'Default' and self.value not in {identifier(b) for b in entries(data)}:
            return {'CANCELLED'}
        data.nms_base_index = self.value
        return {'FINISHED'}


class BBE_MT_corvette_picker(bpy.types.Menu):
    bl_label = 'Select Corvette'

    def draw(self, context):
        from .function_help import corner_help
        corner_help(self.layout, 'PICK_SHIP')
        data = context.scene.nms_save_data
        for ctx in ('Main', 'Season'):
            builds = [b for b in entries(data) if b.save_context == ctx]
            missing = [b for b in data.extracted_base_data.get('missing_corvettes', []) if b['context'] == ctx]
            if not builds and not missing:
                continue
            self.layout.label(text='Main save' if ctx == 'Main' else 'Expedition')
            for base in builds:
                row = self.layout.row(); row.alert = bool(base.issues)
                op = row.operator('bbe.select_corvette', text=label(base),
                                  icon='ERROR' if base.issues else 'CHECKMARK' if identifier(base) == data.nms_base_index else 'NONE')
                op.value = identifier(base); op.expected = cache_key(data)
                op.explanation = ' '.join(base.issues) or 'Select this saved build'
                if base.issues:
                    note = self.layout.row(); note.alert = True
                    note.label(text=textwrap.shorten(base.issues[0], width=57, placeholder='…'))
            for item in missing:
                row = self.layout.row(); row.alert = True
                row.label(text=f"Slot {item['index'] + 1}: {item['name']} — no linked build", icon='ERROR')
                repair_button(self.layout, data, ctx, item['index'])
        op = self.layout.operator('bbe.select_corvette', text='Clear Selection', icon='X')
        op.value = 'Default'; op.expected = cache_key(data)


def draw_picker(layout, data):
    selected = data.get_current_base_identifiers()
    layout.alert = selected is None or bool(selected.issues)
    if layout.alert:
        # The enum field uses Blender's alert color and still opens our repair-aware menu.
        layout.prop_with_menu(data, 'nms_base_index', text='', menu='BBE_MT_corvette_picker',
                              icon='ERROR' if selected else 'NONE')
    else:
        layout.menu('BBE_MT_corvette_picker', text=label(selected), icon='DOWNARROW_HLT')


def draw_status(layout, data):
    selected = data.get_current_base_identifiers()
    if not selected or selected.base_type != BaseType.CORVETTE or not selected.issues:
        return
    box = layout.box(); warning = box.column(align=True); warning.alert = True
    width = max(24, min(52, int(bpy.context.region.width / 7) - 7)) if bpy.context.region else 52
    for issue in selected.issues:
        for line in textwrap.wrap(issue, width):
            warning.label(text=line)
    index = selected.user_data
    if type(index) is int and 0 <= index < 12:
        repair_button(box, data, selected.save_context, index, selected.base_index)
        box.label(text='Review before saving; verified backups are created.')
    else:
        box.label(text='A destination slot cannot be inferred from this build.')
        box.operator_context = 'INVOKE_DEFAULT'
        box.operator('bbe.ship_management', text='Review Ship Links...', icon='INFO')


class BBE_OT_corvette_repair_file(bpy.types.Operator):
    bl_idname = 'bbe.corvette_repair_file'
    bl_label = 'Choose Replacement Corvette'
    bl_description = 'Replace this slot’s build and ship data with a complete .nmsship after review, with backups. Use Repair — Keep My Build to retain the existing data'
    filepath: bpy.props.StringProperty(subtype='FILE_PATH')
    filter_glob: bpy.props.StringProperty(default='*.nmsship', options={'HIDDEN'})
    context_name: bpy.props.StringProperty(options={'HIDDEN'})
    index: bpy.props.IntProperty(default=-1, options={'HIDDEN'})
    base_index: bpy.props.IntProperty(default=-1, options={'HIDDEN'})
    expected: bpy.props.StringProperty(options={'HIDDEN'})

    def invoke(self, context, event):
        try:
            if ship_management.SESSION is not None:
                raise ValueError('Finish or discard the open Ship Management draft before repairing from I/O.')
            data = context.scene.nms_save_data
            if self.expected != cache_key(data):
                raise ValueError('The save list changed. Select the Corvette again.')
            self._scene = context.scene
            links = list(dict.fromkeys(str(Path(p)) for p in data.get_current_slot_data()['saves'] if p and Path(p).exists()))
            root, hashes, source = ship_files.read(links)
            cache = data.extracted_base_data
            if str(source) != cache.get('source_path') or hashes[str(source)] != cache.get('source_hash'):
                raise ValueError('The save changed. Refresh the list before choosing a repair.')
            if type(self.index) is not int or not 0 <= self.index < 12:
                raise ValueError('Choose an explicit ship slot first.')
            records = ship_repair.linked_builds(root, self.context_name, self.index)
            if self.base_index >= 0 and self.base_index not in records:
                raise ValueError('This build no longer points to the selected slot. Refresh the list.')
            if self.base_index < 0 and (records or not core.corvette(core.ships(root, self.context_name)[self.index])):
                raise ValueError('The missing-build slot changed. Refresh the list.')
            self._snapshot = dict(root=root, hashes=hashes, source=source, links=links,
                                  context=self.context_name, index=self.index, records=records,
                                  anchor=self.base_index if self.base_index >= 0 else None)
            context.window_manager.fileselect_add(self)
            return {'RUNNING_MODAL'}
        except Exception as exc:
            report_error(self, {'ERROR'}, str(exc)); return {'CANCELLED'}

    def draw(self, context):
        self.layout.label(text=f'Destination: {self.context_name} / Slot {self.index + 1}')
        self.layout.label(text='Select a complete .nmsship package.')
        self.layout.label(text='Next: review the ship, inventory and build replacement.')

    def execute(self, context):
        try:
            if context.scene != self._scene or cache_key(context.scene.nms_save_data) != self.expected:
                raise ValueError('The save selection changed. Start the repair again.')
            payload = ship_repair.read_replacement(self.filepath, 'FULL')
            snapshot = self._snapshot
            snapshot.update(payload=payload, filename=Path(self.filepath).name,
                            scene=self._scene, expected=self.expected)
            token = uuid4().hex
            _reviews[token] = snapshot
            try:
                result = bpy.ops.bbe.corvette_repair_review('INVOKE_DEFAULT', token=token)
                if 'CANCELLED' in result:
                    _reviews.pop(token, None)
            except Exception:
                _reviews.pop(token, None); raise
            return {'FINISHED'}
        except Exception as exc:
            report_error(self, {'ERROR'}, str(exc)); return {'CANCELLED'}


class BBE_OT_corvette_repair_review(bpy.types.Operator):
    bl_idname = 'bbe.corvette_repair_review'
    bl_label = 'Review Corvette Repair'
    token: bpy.props.StringProperty(options={'HIDDEN'})
    confirm: bpy.props.BoolProperty(name='This slot should be a Corvette; replace it with the file shown', default=False)
    duplicates: bpy.props.BoolProperty(name='Replace ALL duplicate builds listed for this slot', default=False)

    def invoke(self, context, event):
        if self.token not in _reviews:
            return {'CANCELLED'}
        self.confirm = self.duplicates = False
        return context.window_manager.invoke_props_dialog(self, width=660, confirm_text='Repair Corvette')

    def draw(self, context):
        s = _reviews.get(self.token)
        if not s:
            self.layout.label(text='Review expired. Start the repair again.'); return
        ship = core.ships(s['root'], s['context'])[s['index']]
        l = self.layout
        from .function_help import help_button
        help_button(l, 'REPLACE')
        l.label(text=f"Destination: {s['context']} / Slot {s['index']+1}: {core.get(ship, 'Name') or 'Unnamed / empty'}", icon='ERROR')
        l.label(text=f"Replacement: {core.get(s['payload']['ship'], 'Name')} ({len(s['payload']['objects'])} parts)")
        l.label(text=f"File: {s['filename']}")
        l.label(text='Replaces this slot’s ship, cargo, technology, class, appearance and build.')
        from .corvette_actions import warning
        warning(l, s['payload']['objects'])
        bases = core.get(core.player(s['root'], s['context']), 'PersistentPlayerBases', [])
        for n in s['records']:
            l.label(text=f"Build {n+1}: {core.get(bases[n], 'Name')} ({len(core.get(bases[n], 'Objects', []))} parts)")
        if not s['records']:
            l.label(text='Creates the missing Corvette build link.')
        if len(s['records']) > 1:
            l.prop(self, 'duplicates')
        if s['payload'].get('custom') is None:
            l.label(text='This package has no appearance record; default Corvette appearance will be used.')
        l.label(text='Other ship slots and the freighter are preserved.')
        l.label(text='Verified backups are created before writing these save points:')
        for path in s['links']:
            l.label(text=path)
        l.prop(self, 'confirm')

    def cancel(self, context):
        _reviews.pop(self.token, None)

    def execute(self, context):
        s = _reviews.pop(self.token, None)
        try:
            if not s or not self.confirm:
                raise ValueError('Confirm the destination and replacement before repairing. Nothing was written.')
            if ship_management.SESSION is not None or context.scene != s['scene'] or cache_key(s['scene'].nms_save_data) != s['expected']:
                raise ValueError('The save selection or editing session changed. Review the repair again.')
            plan = ship_repair.make_plan(s['root'], s['context'], s['index'], s['payload'], 'FULL',
                                        anchor=s['anchor'], replace_duplicates=self.duplicates)
            draft = ship_repair.apply_plan(s['root'], plan)
            ship_repair.validate_reviewed_draft(s['root'], draft, [plan])
            ship_files.commit(draft, s['links'], s['hashes'])
        except Exception as exc:
            report_error(self, {'ERROR'}, str(exc)); return {'CANCELLED'}
        try:
            data = s['scene'].nms_save_data
            data.refresh_bases_list()
            repaired = next((b for b in entries(data) if b.base_type == BaseType.CORVETTE
                             and b.save_context == s['context'] and b.user_data == s['index']), None)
            if repaired:
                data.nms_base_index = identifier(repaired)
        except Exception:
            self.report({'WARNING'}, 'Repair saved with backups. Refresh the save list to see the new Corvette.')
            return {'FINISHED'}
        self.report({'INFO'}, 'Corvette repaired with backups. Import from Save to load the repaired ship.')
        return {'FINISHED'}


@persistent
def clear_reviews(_=None):
    _reviews.clear()


CLASSES = (BBE_OT_select_corvette, BBE_MT_corvette_picker, BBE_OT_corvette_repair_file, BBE_OT_corvette_repair_review)


def register():
    for cls in CLASSES:
        bpy.utils.register_class(cls)
    bpy.app.handlers.load_pre.append(clear_reviews)


def unregister():
    clear_reviews()
    if clear_reviews in bpy.app.handlers.load_pre:
        bpy.app.handlers.load_pre.remove(clear_reviews)
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)
