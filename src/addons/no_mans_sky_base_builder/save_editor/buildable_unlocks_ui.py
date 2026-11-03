"""Searchable item unlocks and currency editor; writes only through Apply."""
from pathlib import Path
import re
import bpy
from bpy.app.handlers import persistent
from . import buildable_unlocks as core
from ..furby_errors import report_error
from .. import progress_ui

SESSION = None
_CATEGORIES = [('ALL', 'All Categories', '')]
_GROUPS = [('ALL', 'All Item Groups', '')]
_ORIGINS = [('ALL', 'All Origins', ''), ('STANDARD', 'Standard Items', 'Items without a reward-origin tag')]


def _state(context):
    return context.window_manager.bbe_buildable_unlocks


def _matches(row, state):
    needle = state.search.strip().casefold()
    tags = set(row.tags.split(', ')) if row.tags else set()
    origin = state.origin
    group = row.category.split(' / ', 1)[0]
    return (state.group == 'ALL' or group == state.group) and (
        state.category == 'ALL' or row.category == state.category) and (
        origin == 'ALL' or (origin == 'STANDARD' and not tags) or origin in tags) and (
        not needle or needle in (row.name + ' ' + row.item_id + ' ' + row.object_ids + ' ' + row.related_id + ' ' + row.tags).casefold())


def _populate(context, progress=None):
    if SESSION is None:
        return
    state = _state(context)
    state.items.clear()
    account = SESSION.get('account')
    items = core.describe_items(SESSION['roots'], state.save_context, SESSION['catalogue'],
                               account['root'] if account else None,
                               progress=progress_ui.Range(progress, 0., .45) if progress else None)
    for index, item in enumerate(items):
        row = state.items.add()
        row.name = item['name']
        row.item_key = item['key']
        row.item_id = item['id']
        row.object_ids = ', '.join('^' + value.lstrip('^') for value in item.get('object_ids', []))
        row.related_id = item.get('related_id', '')
        row.category = item['category']
        row.tags = ', '.join(item.get('tags', []))
        row.supported = item['supported']
        row.already_known = item['already_known']
        row.known_count = item['known_count']
        row.point_count = item['point_count']
        row.reason = item['unavailable_reason'] or item.get('scope_note', '')
        row.account_reward = bool(item.get('account_field'))
        row.account_known = item['account_known']
        row.scope = ('Account reward' if item.get('unlock_field') == 'AccountWideSpecials' else 'Save + account') if row.account_reward else 'This save'
        if progress is not None and (index % 128 == 0 or index + 1 == len(items)):
            progress.update(.45 + .45 * (index + 1) / max(1, len(items)),
                            f'Preparing items: {index + 1:,} / {len(items):,}')
    state.active = 0
    state.currencies.clear()
    for name, info in core.describe_currencies(SESSION['roots'], state.save_context).items():
        row = state.currencies.add()
        row.name = name
        row.supported = info['supported']
        row.reason = info['unavailable_reason']
        values = info['values']
        amount = values.get(SESSION.get('latest_path'), info['value'])
        row.amount = f'{amount:,}' if amount is not None else ''
        row.mixed = info['mixed']
        row.current = ' / '.join(f'{value:,}' for value in dict.fromkeys(values.values()))
    if progress is not None:
        progress.update(1., 'Items and balances ready')


def _context_changed(self, context):
    if context is not None and SESSION is not None and not SESSION.get('loading'):
        with progress_ui.Activity('Loading selected save context') as progress:
            _populate(context, progress)


def _currency_selection(state):
    selected = {}
    for row in state.currencies:
        if not row.selected:
            continue
        if not row.supported:
            raise ValueError(row.reason or row.name + ' is unavailable')
        amount = row.amount.strip()
        if not re.fullmatch(r'(?:[0-9]+|[0-9]{1,3}(?:,[0-9]{3})+)', amount):
            raise ValueError(row.name + ' must be a whole number (commas are optional)')
        amount = int(amount.replace(',', ''))
        if amount > core.CURRENCY_MAX:
            raise ValueError(f'{row.name} must be between 0 and {core.CURRENCY_MAX:,}')
        selected[row.name] = amount
    return selected


def _filter_changed(self, context):
    if self.items and (self.active < 0 or self.active >= len(self.items) or not _matches(self.items[self.active], self)):
        self.active = next((i for i, row in enumerate(self.items) if _matches(row, self)), -1)


def _group_changed(self, context):
    self.category = 'ALL'
    _filter_changed(self, context)


def _categories(self, context):
    group = self.group
    if group == 'ALL':
        return _CATEGORIES
    return [row for row in _CATEGORIES if row[0] == 'ALL' or row[0].split(' / ', 1)[0] == group]


def _columns(layout):
    split = layout.split(factor=.045, align=True)
    check, rest = split.row(align=True), split.row(align=True)
    split = rest.split(factor=.49, align=True)
    name, rest = split.row(align=True), split.row(align=True)
    split = rest.split(factor=.65, align=True)
    identifiers, scope = split.row(align=True), split.row(align=True)
    return check, name, identifiers, scope


def _contexts(self, context):
    available = SESSION['contexts'] if SESSION else ('Main',)
    return [(c, 'Main save' if c == 'Main' else 'Expedition', 'Selected save context') for c in available]


class BBE_PG_buildable_unlock_item(bpy.types.PropertyGroup):
    item_key: bpy.props.StringProperty()
    item_id: bpy.props.StringProperty()
    object_ids: bpy.props.StringProperty()
    related_id: bpy.props.StringProperty()
    category: bpy.props.StringProperty()
    tags: bpy.props.StringProperty()
    scope: bpy.props.StringProperty()
    reason: bpy.props.StringProperty()
    selected: bpy.props.BoolProperty(name='Unlock', description='Add this item to the pending unlock selection')
    supported: bpy.props.BoolProperty()
    already_known: bpy.props.BoolProperty()
    known_count: bpy.props.IntProperty()
    point_count: bpy.props.IntProperty()
    account_reward: bpy.props.BoolProperty()
    account_known: bpy.props.BoolProperty()


class BBE_PG_buildable_currency(bpy.types.PropertyGroup):
    selected: bpy.props.BoolProperty(name='Set balance',
        description='Set this balance in the selected context of each reviewed save point; unchecked preserves each current balance')
    amount: bpy.props.StringProperty(name='Amount',
        description='Whole number from 0 to 4,294,967,295; commas are optional')
    supported: bpy.props.BoolProperty()
    reason: bpy.props.StringProperty()
    mixed: bpy.props.BoolProperty()
    current: bpy.props.StringProperty()


class BBE_PG_buildable_unlock_state(bpy.types.PropertyGroup):
    items: bpy.props.CollectionProperty(type=BBE_PG_buildable_unlock_item)
    currencies: bpy.props.CollectionProperty(type=BBE_PG_buildable_currency)
    active: bpy.props.IntProperty()
    search: bpy.props.StringProperty(name='Search name or ID', options={'TEXTEDIT_UPDATE'}, update=_filter_changed)
    group: bpy.props.EnumProperty(name='Item group', items=lambda self, context: _GROUPS, update=_group_changed)
    category: bpy.props.EnumProperty(name='Category', items=_categories, update=_filter_changed)
    origin: bpy.props.EnumProperty(name='Reward origin', items=lambda self, context: _ORIGINS, update=_filter_changed)
    save_context: bpy.props.EnumProperty(name='Context', items=_contexts, update=_context_changed)


class BBE_UL_buildable_unlocks(bpy.types.UIList):
    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index):
        check, name, identifiers, scope = _columns(layout.row(align=True))
        check.enabled = item.supported and not item.already_known
        check.prop(item, 'selected', text='')
        name.label(text=item.name)
        exact_ids = item.object_ids or item.item_id
        if item.object_ids and item.item_id not in {s.strip().lstrip('^') for s in item.object_ids.split(',')}:
            exact_ids = item.item_id + ' / ' + item.object_ids
        if item.related_id:
            exact_ids = item.item_id + ' / ' + item.related_id
        identifiers.label(text=exact_ids)
        scope.label(text='Learned' if item.already_known else ('Unavailable' if not item.supported else item.scope))

    def filter_items(self, context, data, propname):
        state = _state(context)
        return [self.bitflag_filter_item if _matches(row, state) else 0 for row in getattr(data, propname)], []


class BBE_OT_buildable_unlock_select(bpy.types.Operator):
    bl_idname = 'bbe.buildable_unlock_select'
    bl_label = 'Select Unlock Items'
    select: bpy.props.BoolProperty(default=True)
    visible_only: bpy.props.BoolProperty(default=False)

    @classmethod
    def description(cls, context, properties):
        action = 'Select' if properties.select else 'Deselect'
        scope = 'matching the current filters' if properties.visible_only else 'across all categories and filters'
        return f'{action} all available, unlearned items {scope}'

    def execute(self, context):
        if SESSION is None:
            return {'CANCELLED'}
        state = _state(context)
        for row in state.items:
            if (not self.visible_only or _matches(row, state)) and row.supported and not row.already_known:
                row.selected = self.select
        return {'FINISHED'}


def _clear(context):
    global SESSION
    SESSION = None
    if context is not None and hasattr(context.window_manager, 'bbe_buildable_unlocks'):
        _state(context).items.clear()
        _state(context).currencies.clear()


@persistent
def _on_load(_):
    _clear(None)


class BBE_OT_buildable_unlocks(bpy.types.Operator):
    bl_idname = 'bbe.buildable_unlocks'
    bl_label = 'Account Item Unlock and Currency Modify'
    bl_description = 'Review item and account unlocks by name or ID, and edit Units, Nanites, and Quicksilver'
    game_closed: bpy.props.BoolProperty(name='No Man’s Sky is closed', default=False,
        description='Close the game before applying to prevent it overwriting the edited save')

    @classmethod
    def poll(cls, context):
        data = getattr(context.scene, 'nms_save_data', None)
        return bool(data and data.get_current_slot_data())

    def invoke(self, context, event):
        global SESSION, _CATEGORIES, _GROUPS, _ORIGINS
        if SESSION is not None:
            self.report({'WARNING'}, 'An unlock review is already open')
            return {'CANCELLED'}
        try:
            data = context.scene.nms_save_data
            slot = data.get_current_slot_data()
            if not slot:
                raise ValueError('Select an account and save slot first')
            paths = [p for p in slot['saves'] if p and Path(p).is_file()]
            with progress_ui.Activity('Opening Account Item Unlock and Currency Modify') as progress:
                SESSION = core.read_review(paths, progress=progress_ui.Range(progress, 0., .55))
                SESSION['loading'] = True
                SESSION['source_scene'] = context.scene
                SESSION['slot_label'] = str(getattr(data, 'nms_save_slot', ''))
                _CATEGORIES = [('ALL', 'All Categories', '')] + [(c, c, c) for c in sorted({i['category'] for i in SESSION['catalogue']['items']})]
                _GROUPS = [('ALL', 'All Item Groups', '')] + [(g, g, g) for g in sorted({i['category'].split(' / ', 1)[0] for i in SESSION['catalogue']['items']})]
                _ORIGINS = [('ALL', 'All Origins', ''), ('STANDARD', 'Standard Items', 'Items without a reward-origin tag')] + [
                    (tag, tag, 'Filter ' + tag + ' items') for tag in sorted({t for i in SESSION['catalogue']['items'] for t in i.get('tags', [])})]
                state = _state(context)
                state.search = ''
                state.group = 'ALL'
                state.category = 'ALL'
                state.origin = 'ALL'
                selected = data.get_current_base_identifiers()
                preferred = getattr(selected, 'save_context', None)
                state.save_context = preferred if preferred in SESSION['contexts'] else SESSION['contexts'][0]
                _populate(context, progress_ui.Range(progress, .55, 1.))
                SESSION['loading'] = False
            self.game_closed = False
            return context.window_manager.invoke_props_dialog(self, width=900, confirm_text='Apply Changes')
        except Exception as exc:
            _clear(context)
            report_error(self, {'ERROR'}, str(exc))
            return {'CANCELLED'}

    def draw(self, context):
        layout = self.layout
        if SESSION is None:
            layout.label(text='The unlock review has closed')
            return
        state = _state(context)
        layout.label(text=f"Save slot {SESSION['slot_label']} · {len(SESSION['paths'])} save point(s)")
        layout.label(text=' / '.join(Path(p).name for p in SESSION['paths']))
        if SESSION.get('account'):
            layout.label(text='Account rewards: ' + Path(SESSION['account']['path']).parent.name)
        elif SESSION.get('account_error'):
            layout.label(text='Account reward editing unavailable: ' + SESSION['account_error'], icon='INFO')
        filters = layout.row(align=True)
        filters.prop(state, 'save_context')
        filters.prop(state, 'group')
        filters.prop(state, 'category')
        balances = layout.box()
        balances.label(text='Balances · check a currency to set its amount in the selected save context')
        columns = balances.row(align=False)
        for currency in state.currencies:
            column = columns.column(align=True)
            column.enabled = currency.supported
            column.prop(currency, 'selected', text=currency.name)
            amount = column.row(align=True)
            amount.enabled = currency.selected
            amount.prop(currency, 'amount', text='')
            if currency.mixed:
                column.label(text='Current: ' + currency.current, icon='INFO')
            elif not currency.supported:
                column.label(text='Unavailable', icon='INFO')
        try:
            currencies = _currency_selection(state)
        except ValueError as error:
            currencies = {}
            warning = balances.row()
            warning.alert = True
            warning.label(text=str(error), icon='ERROR')
        layout.prop(state, 'origin')
        layout.prop(state, 'search', icon='VIEWZOOM')
        buttons = layout.row(align=True)
        op = buttons.operator('bbe.buildable_unlock_select', text='Select All')
        op.select, op.visible_only = True, False
        op = buttons.operator('bbe.buildable_unlock_select', text='Deselect All')
        op.select, op.visible_only = False, False
        op = buttons.operator('bbe.buildable_unlock_select', text='Select Filtered')
        op.select, op.visible_only = True, True
        check, name, identifiers, scope = _columns(layout.row(align=True))
        check.label(text='', icon='UNLOCKED')
        name.label(text='Common name')
        identifiers.label(text='Object ID / item ID')
        scope.label(text='Scope')
        layout.template_list('BBE_UL_buildable_unlocks', '', state, 'items', state, 'active', rows=12)
        if state.items and 0 <= state.active < len(state.items):
            item = state.items[state.active]
            box = layout.box()
            box.label(text=item.name + ' · ' + item.item_id)
            if item.object_ids:
                box.label(text='Object ID: ' + item.object_ids)
            if item.related_id:
                box.label(text='Linked product ID: ' + item.related_id)
            box.label(text=item.category + (' · ' + item.tags if item.tags else ''))
            if item.reason:
                box.label(text=item.reason, icon='INFO')
            if item.supported:
                box.label(text=f'Already learned in {item.known_count}/{item.point_count} selected save points')
                if item.account_reward:
                    box.label(text='Account reward already unlocked' if item.account_known else 'Adds the listed reward to this account')
        count = sum(row.selected and row.supported and not row.already_known for row in state.items)
        unavailable = sum(not row.supported for row in state.items)
        layout.label(text=f'{count} pending item(s) · {len(currencies)} balance(s) selected · {unavailable} unavailable item(s)')
        layout.label(text='Apply saves checked balances and selected unlocks. Unchecked balances stay unchanged.')
        layout.label(text='Verified backups are created before publication. Existing learned items are kept.')
        layout.prop(self, 'game_closed')

    def execute(self, context):
        try:
            if SESSION is None:
                raise ValueError('Open an unlock review first')
            if not self.game_closed:
                raise ValueError('Close No Man’s Sky and confirm the checkbox before applying')
            state = _state(context)
            selected = [row.item_key for row in state.items if row.selected and row.supported and not row.already_known]
            account = SESSION.get('account')
            currencies = _currency_selection(state)
            with progress_ui.Activity('Saving items and balances') as progress:
                plan = core.make_plan(SESSION['roots'], state.save_context, selected, SESSION['catalogue'],
                                      account['root'] if account else None, currencies=currencies,
                                      progress=progress_ui.Range(progress, 0., .25))
                backups = core.apply_review(SESSION, plan, progress=progress_ui.Range(progress, .25, 1.))
            self.report({'INFO'}, f"Saved {plan['item_count']} unlock(s) and {len(currencies)} balance(s); {len(backups)} verified backup file(s) created")
            _clear(context)
            return {'FINISHED'}
        except Exception as exc:
            report_error(self, {'ERROR'}, str(exc))
            _clear(context)
            return {'CANCELLED'}

    def cancel(self, context):
        _clear(context)


CLASSES = (BBE_PG_buildable_unlock_item, BBE_PG_buildable_currency, BBE_PG_buildable_unlock_state, BBE_UL_buildable_unlocks,
           BBE_OT_buildable_unlock_select, BBE_OT_buildable_unlocks)


def register():
    for cls in CLASSES:
        bpy.utils.register_class(cls)
    bpy.types.WindowManager.bbe_buildable_unlocks = bpy.props.PointerProperty(type=BBE_PG_buildable_unlock_state)
    bpy.app.handlers.load_pre.append(_on_load)


def unregister():
    global SESSION
    SESSION = None
    if _on_load in bpy.app.handlers.load_pre:
        bpy.app.handlers.load_pre.remove(_on_load)
    if hasattr(bpy.types.WindowManager, 'bbe_buildable_unlocks'):
        del bpy.types.WindowManager.bbe_buildable_unlocks
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)
