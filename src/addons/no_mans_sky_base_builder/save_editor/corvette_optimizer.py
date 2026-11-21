"""Corvette priority editor and explicit optimized export for both Save Manager views."""
from .. import i18n
from ..furby_errors import report_error
import json
from functools import lru_cache
from pathlib import Path
from uuid import uuid4
import bpy
from bpy.app.handlers import persistent
from .. import icons
from .. import progress_ui
from ..utils import dictionary
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


class BBE_PG_ship_instance(bpy.types.PropertyGroup):
    owner: bpy.props.PointerProperty(type=bpy.types.Object)
    child: bpy.props.StringProperty()
    part_id: bpy.props.StringProperty()


def refresh_automatic_tab(state, context):
    if state.tab == 'SHIP' and not state.manual and state.instances:
        populate_instances(context, state, ())


class BBE_PG_optimizer_settings(bpy.types.PropertyGroup):
    rules_revision: bpy.props.IntProperty(options={'SKIP_SAVE'})
    dialog_key: bpy.props.StringProperty(options={'SKIP_SAVE'})
    instances: bpy.props.CollectionProperty(type=BBE_PG_ship_instance)
    active_instance: bpy.props.IntProperty(default=0)
    manual: bpy.props.BoolProperty()
    order_edited: bpy.props.BoolProperty()
    search: bpy.props.StringProperty(name='Find a ship part', options={'TEXTEDIT_UPDATE'})
    tab: bpy.props.EnumProperty(items=[
        ('SHIP', 'Ship parts', 'Export order for this build', 'OBJECT_DATA', 0),
        ('RULES', 'Priority rules', 'Automatic ordering across projects', 'PREFERENCES', 1)],
        update=refresh_automatic_tab)
    groups: bpy.props.CollectionProperty(type=BBE_PG_optimizer_group)
    active_group: bpy.props.IntProperty(default=0)
    delete_identical: bpy.props.BoolProperty(
        name='Auto-delete identical objects on optimized export', default=False,
        description='Remove only exact duplicate saved records, including rotation, scale, colour, timestamp, messages and other data. Blender objects are kept')


def populate(state, config):
    state.rules_revision += 1
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


def ship_instances():
    from .. import BUILDER
    from ..group import Group
    rows = [(obj, '', obj['ObjectID']) for obj in BUILDER.get_all_parts()]
    for group in BUILDER.get_all_groups():
        sources = []
        records = Group.serialise(group, sources=sources) or []
        rows.extend((owner, child, record['ObjectID'].lstrip('^'))
                    for (owner, child), record in zip(sources, records))
    return rows


def instance_indices(saved, sources):
    by_source = {source: index for index, source in enumerate(sources)}
    return [by_source[key] for row in saved if (key := (row.owner, row.child)) in by_source]


def populate_instances(context, state, saved, rows=None):
    from .. import BUILDER
    rows = ship_instances() if rows is None else rows
    manual = instance_indices(saved, [(obj, child) for obj, child, pid in rows])
    order = core.export_order([{'ObjectID': pid} for obj, child, pid in rows],
                              read_state(state), BUILDER.get_nice_name, manual)
    state.instances.clear()
    for index in order:
        obj, child, pid = rows[index]
        row = state.instances.add()
        row.owner, row.child, row.part_id = obj, child, pid
        label = BUILDER.get_nice_name(pid)
        row.name = label.title() if label.isupper() else label
    state.manual = bool(manual)
    state.active_instance = 0


def optimized_scene(context, config, progress, progress_range):
    from .. import BUILDER
    saved = context.scene.bbe_optimizer_order
    sources = []
    objects = context.scene.nms_main.serialise(
        objects_only=True, for_save=True, progress=progress, progress_range=progress_range,
        **({'sources': sources} if saved else {}))
    if saved and len(objects) != len(sources):
        raise ValueError('Could not match every exported part to the ship order.')
    return core.optimize(objects, config, BUILDER.get_nice_name, instance_indices(saved, sources))


def instance_matches(row, text):
    query = text.strip().casefold()
    return query in ' '.join((row.name, row.part_id, row.child,
                              row.owner.name if row.owner else '')).casefold()


class BBE_UL_ship_instances(bpy.types.UIList):
    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index):
        columns = layout.split(factor=.08)
        row = columns.row()
        row.label(text=str(index + 1))
        row = columns.split(factor=.55)
        previews = icons.get_asset_icons_pcoll()
        preview = previews.get(item.part_id) if previews is not None else None
        row.label(text=item.name, **({'icon_value': preview.icon_id} if preview else {'icon': 'OBJECT_DATA'}))
        row.label(text=item.child or (item.owner.name if item.owner else 'Removed'))

    def filter_items(self, context, data, propname):
        query = data.search.strip().casefold()
        if not query:
            return [], []
        return [self.bitflag_filter_item if instance_matches(row, query) else 0
                for row in data.instances], []


class BBE_OT_move_ship_instance(bpy.types.Operator):
    bl_idname = 'bbe.move_ship_instance'
    bl_label = 'Move Ship Part'
    bl_description = 'Move this placed part in the full optimized export order'
    bl_options = {'INTERNAL'}
    action: bpy.props.EnumProperty(items=[(key, label, '') for key, label in (
        ('FIRST', 'Move to first'), ('UP', 'Move up'), ('DOWN', 'Move down'),
        ('LAST', 'Move to last'), ('AUTO', 'Use priority rules'))])

    def execute(self, context):
        state = context.window_manager.bbe_optimizer
        if self.action == 'AUTO':
            populate_instances(context, state, ())
            state.order_edited = True
            return {'FINISHED'}
        index, last = state.active_instance, len(state.instances) - 1
        target = {'FIRST': 0, 'UP': index - 1, 'DOWN': index + 1, 'LAST': last}[self.action]
        if not (0 <= index <= last and 0 <= target <= last) or target == index:
            return {'CANCELLED'}
        state.instances.move(index, target)
        state.active_instance = target
        state.manual = True
        state.order_edited = True
        return {'FINISHED'}


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
    snapshot = cockpit_snapshot(context)
    slots = {uid: i for i, (uid, _, _, _) in enumerate(snapshot[1], 1)}
    operator._placed = {pid: [(obj.name, obj['ObjectID'], slots[obj.session_uid],
                              tuple(obj.matrix_world.translation)) for obj in objects]
                        for pid, _, objects in groups}
    _cockpit_dialogs[key] = dict(snapshot=snapshot,
        groups=tuple((pid, f'{label} ({len(objects)} objects)', label) for pid, label, objects in groups),
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
    if not groups:
        return _no_cockpit_choices
    selected = getattr(self, 'object_type', '') or groups[0][0]
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
    bl_translation_context = "BBEExtendedInterface"
    bl_label = 'Swap Cockpit / Object Order'
    bl_description = ('Exchange the export positions of two placed cockpits or matching objects. '
                      'Save the .blend to retain it; Ctrl+Z undoes it. The game save changes only when exported')
    bl_options = {'REGISTER', 'UNDO'}

    choice_key: bpy.props.StringProperty(options={'HIDDEN'})
    search: bpy.props.StringProperty(name='Search', options={'SKIP_SAVE', 'HIDDEN'})
    object_type: bpy.props.EnumProperty(translation_context="BBEExtendedInterface", name='Object type', items=group_choices, update=change_order_group)
    first: bpy.props.EnumProperty(translation_context="BBEExtendedInterface", name='First object', items=role_choices,
        description='One of the two placed objects to exchange in export order; numbers show the current order')
    second: bpy.props.EnumProperty(translation_context="BBEExtendedInterface", name='Second object', items=role_choices,
        description='The other object to exchange with the first selection; its physical position stays unchanged')

    def invoke(self, context, event):
        try:
            prepare_cockpit_choices(self, context)
        except ValueError as exc:
            report_error(self, {'ERROR'}, str(exc)); return {'CANCELLED'}
        self.first = '0'
        self.second = '1'
        self.search = ''
        from ..build_editors import open_editor, SwapOrderEditor
        return open_editor(self, context, event, SwapOrderEditor, 570, 'Swap Order')

    def modal(self, context, event):
        return self._editor.modal(context, event)

    def draw(self, context):
        layout = i18n.localized_layout(self.layout)
        layout.prop(self, 'object_type')
        layout.separator()
        layout.prop(self, 'first')
        layout.prop(self, 'second')
        layout.label(text='Swap Order changes export order now. Neither object moves.')
        layout.label(text='Save the .blend to keep it. Ctrl+Z undoes the swap.')
        if context.scene.bbe_optimizer_order:
            layout.label(text='Optimize & Export uses this build’s manual ship order.', icon='INFO')
        from .function_help import help_button
        help_button(layout, 'COCKPIT')

    def cancel(self, context):
        editor = getattr(self, '_editor', None)
        if editor and not editor.closed:
            editor.finish()
        elif not editor or getattr(editor, 'result', None) != {'FINISHED'}:
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
        name = BUILDER.get_nice_name(item.part_id)
        layout.label(text=f'{index + 1}. {name.title() if name.isupper() else name}')


class BBE_OT_optimizer_move(bpy.types.Operator):
    bl_idname = 'bbe.optimizer_move'
    bl_translation_context = "BBEExtendedInterface"
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


@lru_cache(maxsize=1)
def part_library():
    # Blender borrows the enum strings, so keep them alive across search redraws.
    names = dictionary.get_nice_names_diictionary()
    return tuple((pid, f'{name} ({pid})', pid) for pid, name in
                 sorted(names.items(), key=lambda item: (item[1].casefold(), item[0])))


def library_items(self, context):
    return part_library()


class BBE_OT_optimizer_choose_part(bpy.types.Operator):
    bl_idname = 'bbe.optimizer_choose_part'
    bl_translation_context = "BBEExtendedInterface"
    bl_label = 'Add Library Part'
    bl_description = 'Find a part by name or Object ID and add it to the selected priority category'
    bl_property = 'part_id'
    part_id: bpy.props.EnumProperty(translation_context="BBEExtendedInterface", name='Part', items=library_items)

    def invoke(self, context, event):
        if not context.window_manager.bbe_optimizer.groups:
            self.report({'WARNING'}, 'Add a category first')
            return {'CANCELLED'}
        context.window_manager.invoke_search_popup(self)
        return {'RUNNING_MODAL'}

    def execute(self, context):
        state = context.window_manager.bbe_optimizer
        if not state.groups:
            return {'CANCELLED'}
        for gi, group in enumerate(state.groups):
            for pi, part in enumerate(group.parts):
                if part.part_id == self.part_id:
                    state.active_group = gi
                    group.active_part = pi
                    self.report({'INFO'}, f'{self.part_id} is already in {group.name}')
                    return {'FINISHED'}
        return bpy.ops.bbe.optimizer_edit(action='ADD_PART', value=self.part_id)


class BBE_OT_optimizer_edit(bpy.types.Operator):
    bl_idname = 'bbe.optimizer_edit'
    bl_translation_context = "BBEExtendedInterface"
    bl_label = 'Edit Priority List'
    bl_description = 'Add, rename or remove a category or part in this draft; removal does not delete ship objects'
    action: bpy.props.EnumProperty(translation_context="BBEExtendedInterface", items=[(v, v.title(), '') for v in ('ADD_GROUP','RENAME_GROUP','REMOVE_GROUP','ADD_PART','REMOVE_PART')])
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
            i18n.localized_layout(self.layout).label(text='Remove the selected entry from priority settings?')
            i18n.localized_layout(self.layout).label(text='Its ship objects will be kept as unlisted parts.')
        elif self.action == 'ADD_PART':
            i18n.localized_layout(self.layout).prop(self, 'value', text='Object ID')
        else:
            i18n.localized_layout(self.layout).prop(self, 'value', text='Category')

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
                pid = self.value.strip().lstrip('^').upper()
                previous = next((group for group in config['groups'] if pid in group['parts']), None)
                if previous:
                    raise ValueError(f"{pid} is already in {previous['name']}")
                config['groups'][gi]['parts'].append(pid)
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
        if self.action == 'ADD_PART':
            state.groups[gi].active_part = len(state.groups[gi].parts) - 1
        return {'FINISHED'}


class BBE_OT_optimizer_reset(bpy.types.Operator):
    bl_idname = 'bbe.optimizer_reset'
    bl_translation_context = "BBEExtendedInterface"
    bl_label = 'Reset to Default'
    bl_description = 'Restore the standard priority order and turn off duplicate removal; use Save Settings to keep this change'

    def execute(self, context):
        populate(context.window_manager.bbe_optimizer, core.defaults())
        return {'FINISHED'}


class BBE_OT_optimizer_settings(bpy.types.Operator):
    bl_idname = 'bbe.optimizer_settings'
    bl_translation_context = "BBEExtendedInterface"
    bl_label = 'Corvette Optimizer Settings'
    bl_description = 'Reorder Corvette categories and individual parts, and choose whether optimized exports remove truly identical objects'

    def invoke(self, context, event):
        try:
            config = load_settings()
        except (OSError, ValueError, TypeError) as exc:
            self.report({'WARNING'}, f'Could not load settings: {exc}. Defaults shown.')
            config = core.defaults()
        state = context.window_manager.bbe_optimizer
        if state.dialog_key:
            self.report({'INFO'}, 'Optimizer settings are already open.')
            return {'CANCELLED'}
        state.instances.clear()
        state.tab = 'SHIP'
        state.search = ''
        state.order_edited = False
        populate(state, config)
        try:
            rows = ship_instances()
            populate_instances(context, state, context.scene.bbe_optimizer_order, rows)
        except (ValueError, RuntimeError) as exc:
            report_error(self, {'ERROR'}, str(exc))
            return {'CANCELLED'}
        self._scene_uid = context.scene.session_uid
        self._sources = [(o.session_uid, child, pid) for o, child, pid in rows]
        state.dialog_key = uuid4().hex
        from ..build_editors import open_editor, OptimizerEditor
        return open_editor(self, context, event, OptimizerEditor, 650, 'Apply Settings')

    def modal(self, context, event):
        return self._editor.modal(context, event)

    def check(self, context):
        return True

    def draw(self, context):
        state = context.window_manager.bbe_optimizer
        layout = i18n.localized_layout(self.layout)
        tabs = layout.row(align=True)
        tabs.scale_y = 1.2
        tabs.prop(state, 'tab', expand=True)
        tabs.operator('bbe.function_help', text='', icon='QUESTION').topic = 'OPTIMIZER'
        box = layout.box()
        if state.tab == 'SHIP':
            header = box.row()
            name = context.scene.nms_base_tool.string_base.strip() or 'Current build'
            header.label(text=f'{name}  ·  {len(state.instances)} parts', icon='OUTLINER_OB_GROUP_INSTANCE')
            if not state.instances:
                box.label(text='Import a Corvette or place a part to start ordering.', icon='INFO')
                return
            header.label(text='Manual order' if state.manual else 'Automatic order',
                         icon='SORTSIZE' if state.manual else 'SORTALPHA')
            box.prop(state, 'search', text='', icon='VIEWZOOM', placeholder='Find by part name, Object ID or instance')
            row = box.split(factor=.84)
            row.column().template_list('BBE_UL_ship_instances', '', state, 'instances', state,
                              'active_instance', rows=9, sort_lock=True)
            index, last = state.active_instance, len(state.instances) - 1
            controls = row.column(align=True)
            for action, label, icon, enabled in (('FIRST', 'First', 'TRIA_UP_BAR', index > 0),
                    ('UP', 'Up', 'TRIA_UP', index > 0), ('DOWN', 'Down', 'TRIA_DOWN', index < last),
                    ('LAST', 'Last', 'TRIA_DOWN_BAR', index < last)):
                button = controls.row()
                button.enabled = enabled and instance_matches(state.instances[index], state.search)
                button.operator('bbe.move_ship_instance', text=label, icon=icon).action = action
            selected = state.instances[index]
            if selected.owner and instance_matches(selected, state.search):
                detail = box.row()
                detail.label(text=f'#{index + 1}   {selected.part_id}', icon='OBJECT_DATA')
                if selected.child:
                    detail.label(text=selected.owner.name, icon='GROUP')
                else:
                    x, y, z = selected.owner.matrix_world.translation
                    detail.label(text=f'X {x:.2f}    Y {y:.2f}    Z {z:.2f}', icon='ORIENTATION_GLOBAL')
            footer = layout.row()
            footer.label(text='Ship order is saved with this .blend.', icon='FILE_BLEND')
            reset = footer.row()
            reset.enabled = state.manual
            reset.operator('bbe.move_ship_instance', text='Use priority rules', icon='LOOP_BACK').action = 'AUTO'
            return
        box.label(text='Automatic order for all builds', icon='SORTSIZE')
        columns = box.split(factor=.38)
        for is_group, column in ((True, columns.column()), (False, columns.column())):
            column.label(text='Categories' if is_group else 'Parts in selected category')
            row = column.row()
            if is_group:
                row.template_list('BBE_UL_optimizer_groups', '', state, 'groups', state, 'active_group', rows=8)
            elif state.groups:
                group = state.groups[state.active_group]
                row.template_list('BBE_UL_optimizer_parts', '', group, 'parts', group, 'active_part', rows=8)
            arrows = row.column(align=True)
            for direction, icon in ((-1, 'TRIA_UP'), (1, 'TRIA_DOWN')):
                op = arrows.operator('bbe.optimizer_move', text='', **icons.ui_icon(icon))
                op.group = is_group
                op.direction = direction
            edits = column.row(align=True)
            edits.operator_context = 'INVOKE_DEFAULT'
            if is_group:
                edits.operator('bbe.optimizer_edit', text='Add', **icons.ui_icon('ADD')).action = 'ADD_GROUP'
            else:
                edits.operator('bbe.optimizer_choose_part', text='Add Part', **icons.ui_icon('ADD'))
                edits.operator('bbe.optimizer_edit', text='By ID...').action = 'ADD_PART'
            edits.operator('bbe.optimizer_edit', text='Remove', **icons.ui_icon('REMOVE')).action = 'REMOVE_GROUP' if is_group else 'REMOVE_PART'
            if is_group:
                column.operator('bbe.optimizer_edit', text='Rename Category').action = 'RENAME_GROUP'
            elif state.groups and group.parts:
                column.label(text=group.parts[group.active_part].part_id, icon='OBJECT_DATA')
        layout.separator()
        footer = layout.row()
        footer.prop(state, 'delete_identical', text='Remove exact duplicates on export')
        footer.operator('bbe.optimizer_reset', text='Reset priority rules', icon='LOOP_BACK')
        footer.operator_context = 'INVOKE_DEFAULT'
        footer.operator('bbe.swap_corvette_cockpits', text='Swap scene order…',
                        **icons.ui_icon('ARROW_LEFTRIGHT'))

    def cancel(self, context):
        editor = getattr(self, '_editor', None)
        if editor and not editor.closed:
            editor.finish()
            return
        state = context.window_manager.bbe_optimizer
        state.dialog_key = ''
        state.instances.clear()

    def execute(self, context):
        state = context.window_manager.bbe_optimizer
        try:
            if getattr(self, '_scene_uid', None) != context.scene.session_uid or (
                    state.order_edited and self._sources != [
                        (obj.session_uid, child, pid) for obj, child, pid in ship_instances()]):
                raise ValueError('The loaded parts changed. Reopen settings to review their order.')
            save_settings(read_state(state))
            saved = context.scene.bbe_optimizer_order
            new_order = [(row.owner, row.child) for row in state.instances] if state.manual else []
            if state.order_edited and new_order != [(row.owner, row.child) for row in saved]:
                saved.clear()
                for owner, child in new_order:
                    entry = saved.add()
                    entry.owner, entry.child = owner, child
                if new_order:
                    context.scene['bbe_optimizer_order_revision'] = uuid4().hex
                else:
                    context.scene.pop('bbe_optimizer_order_revision', None)
        except (OSError, ValueError, TypeError) as exc:
            report_error(self, {'ERROR'}, str(exc))
            return {'CANCELLED'}
        finally:
            self.cancel(context)
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
    config = load_settings()
    ordered, counts = optimized_scene(context, config, progress, (.02, .12))
    if not ordered:
        raise ValueError('There are no objects to export')
    if progress:
        progress.update(.13, 'Ordering and checking parts')
    name = context.scene.nms_base_tool.string_base.strip() or None
    signature = ''
    if pinned:
        from ..build_metadata import save_owner
        signature = core.fingerprint([save_owner(context.scene.nms_base_tool), ordered, counts, config, links,
                                      identifier.base_index, identifier.base_name, identifier.base_type,
                                      identifier.user_data, identifier.galactic_address,
                                      getattr(identifier, 'save_context', None), name])
    return identifier, links, name, ordered, counts, signature


class BBE_OT_optimizer_export(bpy.types.Operator):
    bl_idname = 'bbe.optimizer_export'
    bl_translation_context = "BBEExtendedInterface"
    bl_label = 'Optimize & Export to Save'
    bl_description = 'Back up the save and immediately write the optimized scene to the selected Corvette. Choose a destination if no Corvette is selected'
    pinned: bpy.props.BoolProperty(default=False, options={'HIDDEN'})
    expected_signature: bpy.props.StringProperty(default='', options={'HIDDEN'})

    def invoke(self, context, event):
        if not self.pinned:
            if context.scene.nms_save_data.has_selected_base():
                return self.execute(context)
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
        layout = i18n.localized_layout(self.layout)
        layout.label(text=f'Corvette: {identifier.base_name}', **icons.ui_icon('OUTLINER_OB_LIGHTPROBE'))
        for link in links:
            layout.label(text=str(Path(link)), **icons.ui_icon('FILE'))
        if name and name != identifier.base_name:
            layout.label(text=f'Export name: {name}')
        layout.separator()
        layout.label(text=f"Objects: {counts['before']} to {counts['after']}    Reordered: {counts['moved']}")
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

        from . import corvette_actions, ship_management, ship_repair
        manager = context.scene.nms_save_data
        try:
            if not self.pinned and ship_management.SESSION is not None:
                raise ValueError('Finish or discard the open Ship Management draft before exporting.')
            if not self.pinned:
                manager.refresh_before_export()
            with progress_ui.Activity('Optimizing and exporting') as progress:
                progress.update(.02, 'Collecting and ordering scene parts')
                current = prepare(context, self.pinned, progress)
                expected = self.expected_signature or (
                    self._plan[-1] if hasattr(self, '_plan') else '')
                if expected and current[-1] != expected:
                    raise ValueError('Scene, settings or destination changed. Review the export again.')
                identifier, links, name, ordered, counts, signature = current
                ship_repair.validate_parts(ordered)
                progress.update(.15, 'Optimization complete')
                from ..build_metadata import save_owner
                backups = optimizer_export.export(ordered, identifier, links, name,
                                                  progress=progress, owner_override=save_owner(context.scene.nms_base_tool),
                                                  selected_source=None if self.pinned else manager.extracted_base_data)
                from .. import build_timer
                build_timer.mark_saved(context.scene, build_timer.base_key(identifier, links))
                progress.update(.98, 'Refreshing save list')
                try:
                    if self.pinned:
                        from .. import build_timer
                        build_timer.bind(context.scene, build_timer.base_key(identifier, links))
                        manager.refresh_bases_list()
                    else:
                        corvette_actions.remember_ship_source(context.scene, links, identifier.save_context,
                                                              identifier.user_data, name or identifier.base_name)
                        corvette_actions.refresh_selection({'scene': context.scene}, identifier.save_context,
                                                          identifier.user_data)
                except Exception as exc:
                    self.report({'WARNING'}, f'Saved, but the save list could not refresh: {exc}')
                progress.update(1.0, 'Export complete')
        except Exception as exc:
            report_error(self, {'ERROR'}, f'Optimized export failed: {exc}')
            return {'CANCELLED'}
        from .ship_repair import cockpit_warning
        warning = cockpit_warning(ordered)
        self.report({'WARNING'} if warning else {'INFO'}, f"Saved {name or identifier.base_name} in ship slot {identifier.user_data + 1} ({counts['after']} parts, {len(backups)} files backed up)" + (' — ' + warning if warning else ''))
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


CLASSES = (BBE_PG_optimizer_part, BBE_PG_optimizer_group, BBE_PG_ship_instance, BBE_PG_optimizer_settings,
           BBE_UL_ship_instances, BBE_OT_move_ship_instance,
           BBE_UL_optimizer_groups, BBE_UL_optimizer_parts, BBE_OT_optimizer_move,
           BBE_OT_optimizer_edit, BBE_OT_optimizer_choose_part, BBE_OT_optimizer_reset, BBE_OT_swap_corvette_cockpits,
           BBE_OT_optimizer_settings, BBE_OT_optimizer_export)


def register():
    for cls in CLASSES:
        bpy.utils.register_class(cls)
    bpy.types.WindowManager.bbe_optimizer = bpy.props.PointerProperty(type=BBE_PG_optimizer_settings)
    bpy.types.Scene.bbe_optimizer_order = bpy.props.CollectionProperty(type=BBE_PG_ship_instance)
    bpy.app.handlers.load_pre.append(clear_cockpit_choices)


def unregister():
    del bpy.types.Scene.bbe_optimizer_order
    del bpy.types.WindowManager.bbe_optimizer
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)
    if clear_cockpit_choices in bpy.app.handlers.load_pre:
        bpy.app.handlers.load_pre.remove(clear_cockpit_choices)
    clear_cockpit_choices()
