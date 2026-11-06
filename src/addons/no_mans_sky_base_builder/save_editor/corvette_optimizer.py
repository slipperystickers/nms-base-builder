"""Corvette priority editor and explicit optimized export for both Save Manager views."""
from ..furby_errors import report_error
import json
from pathlib import Path
from uuid import uuid4
import bpy
from bpy.app.handlers import persistent
from .. import icons
from .. import progress_ui
from . import optimizer_core as core, optimizer_export
from .save_editor_utils import BaseType

_pending_optimizer_exports = {}
_cockpit_dialogs = {}
_no_cockpit_choices = ()


def settings_file():
    return Path(bpy.utils.user_resource('CONFIG', path='bbe', create=True)) / 'corvette_optimizer.json'


def load_settings():
    path = settings_file()
    if not path.exists():
        return core.defaults()
    return core.validate(json.loads(path.read_text(encoding='utf-8')))


def save_settings(config):
    config = core.validate(config)
    path = settings_file()
    temp = path.with_suffix('.tmp')
    temp.write_text(json.dumps(config, indent=2), encoding='utf-8')
    temp.replace(path)


class BBE_PG_optimizer_part(bpy.types.PropertyGroup):
    part_id: bpy.props.StringProperty()


class BBE_PG_optimizer_group(bpy.types.PropertyGroup):
    parts: bpy.props.CollectionProperty(type=BBE_PG_optimizer_part)
    active_part: bpy.props.IntProperty(default=0)


class BBE_PG_optimizer_settings(bpy.types.PropertyGroup):
    groups: bpy.props.CollectionProperty(type=BBE_PG_optimizer_group)
    active_group: bpy.props.IntProperty(default=0)
    delete_identical: bpy.props.BoolProperty(
        name='Auto-delete identical objects on optimized export', default=False,
        description='Remove only exact duplicate saved records, including rotation, scale, colour, timestamp, messages and other data. Blender objects are kept')


def populate(state, config):
    state.groups.clear()
    state.active_group = 0
    state.delete_identical = config['delete_identical']
    for group in config['groups']:
        item = state.groups.add()
        item.name = group['name']
        for pid in group['parts']:
            item.parts.add().part_id = pid


def read_state(state):
    return {'version': 1, 'delete_identical': state.delete_identical,
            'groups': [{'name': g.name, 'parts': [p.part_id for p in g.parts]} for g in state.groups]}


def placed_cockpits(context):
    objects = [obj for obj in context.scene.objects
               if str(obj.get('ObjectID', '')).lstrip('^').upper().startswith('B_COK_')]
    # Match Builder.get_all_parts: stable scene order breaks duplicate order ties.
    return sorted(objects, key=lambda obj: obj.get('order', 0))


def ordered_parts(context):
    return sorted((o for o in context.scene.objects if o.get('ObjectID')),
                  key=lambda o: o.get('order', 0))


def order_groups(context):
    """Cockpit roles span variants; all other choices require duplicate IDs."""
    from .. import BUILDER
    parts = ordered_parts(context)
    cockpits = placed_cockpits(context)
    by_id = {}
    for obj in parts:
        pid = str(obj['ObjectID']).lstrip('^').upper()
        if not pid.startswith('B_COK_'):
            by_id.setdefault(pid, []).append(obj)
    groups = []
    if len(cockpits) > 1:
        groups.append(('COCKPITS', 'Cockpits', cockpits))
    def priority(pid):
        return (0 if pid in {'DRESSING_TABLE', 'FRE_ROOM_DRESS'} else 1,
                BUILDER.get_nice_name(pid).casefold(), pid)
    for pid in sorted(by_id, key=priority):
        if len(by_id[pid]) > 1:
            groups.append((pid, f'{BUILDER.get_nice_name(pid).title()} ({pid})', by_id[pid]))
    return groups


def cockpit_snapshot(context):
    return (context.scene.session_uid,
            tuple((obj.session_uid, obj.name, str(obj.get('ObjectID', '')), obj.get('order', 0))
                  for obj in ordered_parts(context)))


def prepare_cockpit_choices(operator, context):
    groups = order_groups(context)
    if not groups:
        raise ValueError('Add two cockpits or two objects with the same Object ID to swap their order.')
    key = uuid4().hex
    # RNA borrows enum strings: retain plain data for the dialog and redo.
    _cockpit_dialogs[key] = dict(snapshot=cockpit_snapshot(context),
        groups=tuple((pid, f'{label} — {len(objects)} objects', label) for pid, label, objects in groups),
        items_by_group={pid: tuple(
            (str(index), f'{index + 1}. {obj.get("ObjectID", "")} — {obj.name}',
             f'Current order within this group. Location: {tuple(round(v, 2) for v in obj.matrix_world.translation)}')
            for index, obj in enumerate(objects)) for pid, _, objects in groups})
    operator.choice_key = key
    operator.object_type = groups[0][0]


def group_choices(self, context):
    return _cockpit_dialogs.get(self.choice_key, {}).get('groups', ())


def role_choices(self, context):
    data = _cockpit_dialogs.get(self.choice_key, {})
    groups = data.get('groups', ())
    selected = getattr(self, 'object_type', '') or (groups[0][0] if groups else '')
    return data.get('items_by_group', {}).get(selected, _no_cockpit_choices)


def change_order_group(self, context):
    if len(role_choices(self, context)) >= 2:
        self.first = '0'
        self.second = '1'


@persistent
def clear_cockpit_choices(_=None):
    _cockpit_dialogs.clear()


class BBE_OT_swap_corvette_cockpits(bpy.types.Operator):
    bl_idname = 'bbe.swap_corvette_cockpits'
    bl_label = 'Swap Cockpit/Object order...'
    bl_description = ('Immediately exchange two cockpits or matching objects in this scene’s export order without moving them. '
                      'Save the .blend to retain it; Ctrl+Z undoes it. The game save changes only when exported')
    bl_options = {'REGISTER', 'UNDO'}

    choice_key: bpy.props.StringProperty(options={'HIDDEN'})
    object_type: bpy.props.EnumProperty(name='Object type', items=group_choices, update=change_order_group)
    first: bpy.props.EnumProperty(name='First object', items=role_choices,
        description='One of the two placed objects to exchange in export order; numbers show the current order')
    second: bpy.props.EnumProperty(name='Second object', items=role_choices,
        description='The other object to exchange with the first selection; its physical position stays unchanged')

    def invoke(self, context, event):
        try:
            prepare_cockpit_choices(self, context)
        except ValueError as exc:
            report_error(self, {'ERROR'}, str(exc)); return {'CANCELLED'}
        self.first = '0'
        self.second = '1'
        return context.window_manager.invoke_props_dialog(self, width=570, confirm_text='Swap Order')

    def draw(self, context):
        layout = self.layout
        layout.prop(self, 'object_type')
        layout.separator()
        layout.prop(self, 'first')
        layout.prop(self, 'second')
        layout.label(text='Swap Order changes export order now. Neither object moves.')
        layout.label(text='Save the .blend to keep it. Ctrl+Z undoes the swap.')
        layout.label(text='Ordinary and optimized exports both use this order.')
        from .function_help import help_button
        help_button(layout, 'COCKPIT')

    def cancel(self, context):
        _cockpit_dialogs.pop(self.choice_key, None)

    def execute(self, context):
        reviewed = _cockpit_dialogs.get(self.choice_key)
        if not reviewed or reviewed['snapshot'] != cockpit_snapshot(context):
            report_error(self, {'ERROR'}, 'The object list or order changed. Reopen Swap Cockpit/Object order and choose again.')
            return {'CANCELLED'}
        groups = order_groups(context)
        chosen = getattr(self, 'object_type', '') or (groups[0][0] if groups else '')
        objects = next((objects for pid, _, objects in groups if pid == chosen), [])
        try:
            first, second = int(self.first), int(self.second)
        except (TypeError, ValueError):
            report_error(self, {'ERROR'}, 'Choose two placed parts')
            return {'CANCELLED'}
        if first == second or min(first, second) < 0 or max(first, second) >= len(objects):
            report_error(self, {'ERROR'}, 'Choose two different placed parts')
            return {'CANCELLED'}
        # Normalize all placed part order values first: Blender duplicates and
        # newly added parts can have the same value, but serialization must be
        # deterministic after the swap.
        from .. import BUILDER
        for index, obj in enumerate(BUILDER.get_all_parts()):
            obj['order'] = index
        left, right = objects[first], objects[second]
        left['order'], right['order'] = right['order'], left['order']
        from .. import pilot_reference
        pilot_reference.sync_flight_reference(context)
        self.report({'INFO'}, f'Swapped {left.name} and {right.name} in export order')
        return {'FINISHED'}


class BBE_UL_optimizer_groups(bpy.types.UIList):
    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index):
        layout.label(text=f'{index + 1}. {item.name}')


class BBE_UL_optimizer_parts(bpy.types.UIList):
    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index):
        from .. import BUILDER
        row = layout.row()
        row.label(text=f'{index + 1}. {BUILDER.get_nice_name(item.part_id)}')
        row.label(text=item.part_id)


class BBE_OT_optimizer_move(bpy.types.Operator):
    bl_idname = 'bbe.optimizer_move'
    bl_label = 'Move Priority'
    bl_description = 'Move the selected category or part earlier or later in the export priority order'
    group: bpy.props.BoolProperty(default=False)
    direction: bpy.props.IntProperty(default=-1)

    def execute(self, context):
        state = context.window_manager.bbe_optimizer
        if not state.groups:
            return {'CANCELLED'}
        owner = state if self.group else state.groups[state.active_group]
        collection = owner.groups if self.group else owner.parts
        prop = 'active_group' if self.group else 'active_part'
        index = getattr(owner, prop)
        target = index + self.direction
        if 0 <= target < len(collection):
            collection.move(index, target)
            setattr(owner, prop, target)
        if context.area:
            context.area.tag_redraw()
        return {'FINISHED'}


class BBE_OT_optimizer_edit(bpy.types.Operator):
    bl_idname = 'bbe.optimizer_edit'
    bl_label = 'Edit Priority List'
    bl_description = 'Add, rename or remove a category or part in this draft; removal does not delete ship objects'
    action: bpy.props.EnumProperty(items=[(v, v.title(), '') for v in ('ADD_GROUP','RENAME_GROUP','REMOVE_GROUP','ADD_PART','REMOVE_PART')])
    value: bpy.props.StringProperty(name='Name / Part ID')

    def invoke(self, context, event):
        state = context.window_manager.bbe_optimizer
        if self.action == 'RENAME_GROUP' and state.groups:
            self.value = state.groups[state.active_group].name
        elif self.action == 'ADD_GROUP':
            self.value = 'New Category'
        else:
            self.value = ''
        return context.window_manager.invoke_props_dialog(self, width=440)

    def draw(self, context):
        if self.action.startswith('REMOVE'):
            self.layout.label(text='Remove the selected entry from priority settings?')
            self.layout.label(text='Its ship objects will be kept as unlisted parts.')
        else:
            self.layout.prop(self, 'value', text='Part ID' if self.action == 'ADD_PART' else 'Category')
            if self.action == 'ADD_PART':
                self.layout.label(text='Enter the Object ID shown on a selected Blender part.')

    def execute(self, context):
        state = context.window_manager.bbe_optimizer
        config = read_state(state)
        gi = state.active_group
        try:
            if self.action == 'ADD_GROUP':
                config['groups'].append({'name': self.value, 'parts': []})
                gi = len(config['groups']) - 1
            elif not config['groups']:
                raise ValueError('Add a category first')
            elif self.action == 'RENAME_GROUP':
                config['groups'][gi]['name'] = self.value
            elif self.action == 'REMOVE_GROUP':
                config['groups'].pop(gi)
                gi = max(0, gi - 1)
            elif self.action == 'ADD_PART':
                config['groups'][gi]['parts'].append(self.value)
            elif self.action == 'REMOVE_PART':
                parts = config['groups'][gi]['parts']
                if parts:
                    parts.pop(state.groups[gi].active_part)
            config = core.validate(config)
        except (ValueError, IndexError) as exc:
            report_error(self, {'ERROR'}, str(exc))
            return {'CANCELLED'}
        populate(state, config)
        state.active_group = min(gi, max(0, len(state.groups) - 1))
        return {'FINISHED'}


class BBE_OT_optimizer_reset(bpy.types.Operator):
    bl_idname = 'bbe.optimizer_reset'
    bl_label = 'Reset to Default'
    bl_description = 'Restore the standard priority order and turn off duplicate removal; use Save Settings to keep this change'

    def execute(self, context):
        populate(context.window_manager.bbe_optimizer, core.defaults())
        return {'FINISHED'}


class BBE_OT_optimizer_settings(bpy.types.Operator):
    bl_idname = 'bbe.optimizer_settings'
    bl_label = 'Corvette Optimizer Settings'
    bl_description = 'Reorder Corvette categories and individual parts, and choose whether optimized exports remove truly identical objects'

    def invoke(self, context, event):
        try:
            config = load_settings()
        except (OSError, ValueError, TypeError) as exc:
            self.report({'WARNING'}, f'Could not load settings: {exc}. Defaults shown.')
            config = core.defaults()
        populate(context.window_manager.bbe_optimizer, config)
        return context.window_manager.invoke_props_dialog(self, width=850, confirm_text='Save Settings')

    def check(self, context):
        return True

    def draw(self, context):
        state = context.window_manager.bbe_optimizer
        layout = self.layout
        from .function_help import help_button
        help_button(layout, 'OPTIMIZER')
        layout.label(text='Earlier entries are exported first. Select an entry and use the arrows.')
        columns = layout.split(factor=.30)
        for is_group, column in ((True, columns.column()), (False, columns.column())):
            column.label(text='Categories' if is_group else 'Parts in selected category')
            row = column.row()
            if is_group:
                row.template_list('BBE_UL_optimizer_groups', '', state, 'groups', state, 'active_group', rows=10)
            elif state.groups:
                group = state.groups[state.active_group]
                row.template_list('BBE_UL_optimizer_parts', '', group, 'parts', group, 'active_part', rows=10)
            arrows = row.column(align=True)
            for direction, icon in ((-1, 'TRIA_UP'), (1, 'TRIA_DOWN')):
                op = arrows.operator('bbe.optimizer_move', text='', **icons.ui_icon(icon))
                op.group = is_group
                op.direction = direction
            edits = column.row(align=True)
            edits.operator_context = 'INVOKE_DEFAULT'
            edits.operator('bbe.optimizer_edit', text='Add', **icons.ui_icon('ADD')).action = 'ADD_GROUP' if is_group else 'ADD_PART'
            edits.operator('bbe.optimizer_edit', text='Remove', **icons.ui_icon('REMOVE')).action = 'REMOVE_GROUP' if is_group else 'REMOVE_PART'
            if is_group:
                column.operator('bbe.optimizer_edit', text='Rename Category').action = 'RENAME_GROUP'
        layout.separator()
        layout.label(text='Order affects which functional parts the game processes first; it can change stats and cockpit roles.')
        layout.label(text='Defaults are a starting point, not a guarantee of maximum stats. Removing entries keeps their objects.')
        layout.prop(state, 'delete_identical')
        layout.label(text='Every saved field must match exactly. Different rotations, scales or colours are kept.', **icons.ui_icon('INFO'))
        layout.label(text='Applies to Optimize & Export only. Unlisted parts follow warning tiers, then names.')
        layout.operator_context = 'INVOKE_DEFAULT'
        layout.separator()
        layout.label(text='Separate scene edit: cockpit swaps apply immediately and are saved in the .blend.')
        layout.operator('bbe.swap_corvette_cockpits', text='Swap Placed Cockpit Order', **icons.ui_icon('ARROW_LEFTRIGHT'))
        layout.operator('bbe.optimizer_reset', **icons.ui_icon('LOOP_BACK'))

    def execute(self, context):
        try:
            save_settings(read_state(context.window_manager.bbe_optimizer))
        except (OSError, ValueError, TypeError) as exc:
            report_error(self, {'ERROR'}, str(exc))
            return {'CANCELLED'}
        self.report({'INFO'}, 'Corvette optimizer settings saved')
        return {'FINISHED'}


def destination(context, pinned):
    manager = context.scene.nms_save_data
    if pinned:
        identifier = manager.get_pinned_base_identifiers()
        links = identifier.save_slot if identifier else []
    else:
        identifier = manager.get_current_base_identifiers()
        slot = manager.get_current_slot_data()
        links = slot['saves'] if slot else []
    if identifier is None or identifier.base_type != BaseType.CORVETTE or not links:
        raise ValueError('Select a Corvette and save slot first')
    return identifier, list(links)


def prepare(context, pinned, progress=None):
    identifier, links = destination(context, pinned)
    context.view_layer.update()
    objects = context.scene.nms_main.serialise(
        objects_only=True, progress=progress, progress_range=(.02, .12))
    if not objects:
        raise ValueError('There are no objects to export')
    config = load_settings()
    if progress:
        progress.update(.13, 'Ordering and checking parts')
    from .. import BUILDER
    ordered, counts = core.optimize(objects, config, name_for_part=BUILDER.get_nice_name)
    name = context.scene.nms_base_tool.string_base.strip() or None
    from ..build_metadata import save_owner
    owner_override = save_owner(context.scene.nms_base_tool)
    signature = core.fingerprint([owner_override, objects, config, links, identifier.base_index,
                                  identifier.base_name, identifier.base_type,
                                  identifier.user_data, identifier.galactic_address, getattr(identifier, 'save_context', None), name])
    return identifier, links, name, ordered, counts, signature


class BBE_OT_optimizer_export(bpy.types.Operator):
    bl_idname = 'bbe.optimizer_export'
    bl_label = 'Optimize & Export to Save'
    bl_description = 'Export this scene to the selected Corvette using saved priorities and optional exact duplicate removal, with verified backups'
    pinned: bpy.props.BoolProperty(default=False, options={'HIDDEN'})
    expected_signature: bpy.props.StringProperty(default='', options={'HIDDEN'})

    def invoke(self, context, event):
        if not self.pinned:
            return bpy.ops.bbe.corvette_export('INVOKE_DEFAULT', optimized=True)
        try:
            with progress_ui.Activity('Preparing optimized export') as progress:
                progress.update(.05, 'Collecting scene parts')
                self._plan = prepare(context, self.pinned, progress)
                progress.update(1.0, 'Review export details')
        except Exception as exc:
            report_error(self, {'ERROR'}, str(exc))
            return {'CANCELLED'}
        return context.window_manager.invoke_props_dialog(
            self, width=540, confirm_text='Optimize & Export')

    def draw(self, context):
        identifier, links, name, ordered, counts, signature = self._plan
        layout = self.layout
        layout.label(text=f'Corvette: {identifier.base_name}', **icons.ui_icon('OUTLINER_OB_LIGHTPROBE'))
        for link in links:
            layout.label(text=str(Path(link)), **icons.ui_icon('FILE'))
        if name and name != identifier.base_name:
            layout.label(text=f'Export name: {name}')
        layout.separator()
        layout.label(text=f"Objects: {counts['before']} → {counts['after']}   •   Reordered: {counts['moved']}")
        layout.label(text=f"Identical objects to remove from export: {counts['removed']}")
        from ..build_metadata import draw_save_warning
        draw_save_warning(layout, context.scene.nms_base_tool)
        layout.label(text='Verified backups will be created before saving.', **icons.ui_icon('INFO'))
        layout.label(text='Your Blender objects stay in the scene.')
        from .corvette_actions import warning
        warning(layout, ordered)

    def execute(self, context):
        # The confirmation dialog must close before the viewport progress bar
        # can become visible. Recheck the scene and destination in the timer.
        if (hasattr(self, '_plan') and not bpy.app.background
                and context.window is not None and not self.expected_signature):
            window = context.window
            scene = context.scene
            window_id = window.as_pointer()
            if window_id in _pending_optimizer_exports:
                self.report({'WARNING'}, 'An optimized export is already starting')
                return {'CANCELLED'}
            signature = self._plan[-1]
            pinned = self.pinned

            def start_export():
                try:
                    if not any(w.as_pointer() == window_id
                               for w in bpy.context.window_manager.windows):
                        return None
                    if bpy.data.scenes.get(scene.name) != scene or window.scene != scene:
                        return None
                    with bpy.context.temp_override(window=window, scene=scene):
                        bpy.ops.bbe.optimizer_export('EXEC_DEFAULT', pinned=pinned,
                                                    expected_signature=signature)
                except Exception as exc:
                    print(f'Could not start optimized export: {exc}')
                finally:
                    _pending_optimizer_exports.pop(window_id, None)
                return None

            _pending_optimizer_exports[window_id] = start_export
            bpy.app.timers.register(start_export, first_interval=0.1)
            self.report({'INFO'}, 'Optimized export is starting')
            return {'FINISHED'}

        try:
            with progress_ui.Activity('Optimizing and exporting') as progress:
                progress.update(.02, 'Collecting and ordering scene parts')
                current = prepare(context, self.pinned, progress)
                expected = self.expected_signature or (
                    self._plan[-1] if hasattr(self, '_plan') else '')
                if expected and current[-1] != expected:
                    raise ValueError('Scene, settings or destination changed. Review the export again.')
                identifier, links, name, ordered, counts, signature = current
                progress.update(.15, 'Optimization complete')
                from ..build_metadata import save_owner
                backups = optimizer_export.export(ordered, identifier, links, name,
                                                  progress=progress, owner_override=save_owner(context.scene.nms_base_tool))
                progress.update(.98, 'Refreshing save list')
                try:
                    context.scene.nms_save_data.refresh_bases_list()
                except Exception as exc:
                    self.report({'WARNING'}, f'Saved, but the save list could not refresh: {exc}')
                progress.update(1.0, 'Export complete')
        except Exception as exc:
            report_error(self, {'ERROR'}, f'Optimized export failed: {exc}')
            return {'CANCELLED'}
        from .ship_repair import cockpit_warning
        warning = cockpit_warning(ordered)
        self.report({'WARNING'} if warning else {'INFO'}, f"Exported {counts['after']} objects; removed {counts['removed']} exact duplicates; {len(backups)} backups created" + (' — ' + warning if warning else ''))
        return {'FINISHED'}


def draw_row(layout, pinned=False):
    row = layout.row(align=True)
    row.operator_context = 'INVOKE_DEFAULT'
    row.operator('bbe.optimizer_export', **icons.ui_icon('EXPORT')).pinned = pinned
    row.operator('bbe.optimizer_settings', text='', **icons.ui_icon('PREFERENCES'))


def draw_cockpit_controls(layout):
    row = layout.row(align=True)
    row.operator_context = 'INVOKE_DEFAULT'
    row.operator('bbe.swap_corvette_cockpits', text='Swap Cockpit/Object order...', **icons.ui_icon('ARROW_LEFTRIGHT'))
    row.operator('bbe.function_help', text='', icon='QUESTION').topic = 'COCKPIT'


CLASSES = (BBE_PG_optimizer_part, BBE_PG_optimizer_group, BBE_PG_optimizer_settings,
           BBE_UL_optimizer_groups, BBE_UL_optimizer_parts, BBE_OT_optimizer_move,
           BBE_OT_optimizer_edit, BBE_OT_optimizer_reset, BBE_OT_swap_corvette_cockpits,
           BBE_OT_optimizer_settings, BBE_OT_optimizer_export)


def register():
    for cls in CLASSES:
        bpy.utils.register_class(cls)
    bpy.types.WindowManager.bbe_optimizer = bpy.props.PointerProperty(type=BBE_PG_optimizer_settings)
    bpy.app.handlers.load_pre.append(clear_cockpit_choices)


def unregister():
    del bpy.types.WindowManager.bbe_optimizer
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)
    if clear_cockpit_choices in bpy.app.handlers.load_pre:
        bpy.app.handlers.load_pre.remove(clear_cockpit_choices)
    clear_cockpit_choices()
