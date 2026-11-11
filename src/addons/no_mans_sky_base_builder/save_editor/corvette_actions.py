"""Reviewed keep-build repairs and one-step exports to occupied or empty slots."""
from pathlib import Path
from uuid import uuid4
import textwrap
import json
import bpy
from bpy.app.handlers import persistent
from . import ship_core as core, ship_repair as repair, ship_files, ship_management, corvette_io as io
from .. import progress_ui, build_metadata
from ..furby_errors import report_error
from .function_help import help_button

_pending = {}
_dialogs = {}
_NO_SLOTS = [('NONE', 'No available slot', '')]
_MAIN_CONTEXT = [('Main', 'Main', '')]


def destination_scope(links):
    return repair.fingerprint(sorted(str(Path(p).resolve()).casefold() for p in links))


def remember_ship_source(scene, links, context_name, index, name):
    # Advisory provenance only. Never use a project's stored source to choose
    # a local export destination or authorize a write.
    scene['bbe_ship_export_origin'] = json.dumps(dict(scope=destination_scope(links),
        context=context_name, index=index, name=name or 'Unnamed'))


def overwrite_warning(op):
    if op.destination != 'SELECTED' or getattr(op, '_error', ''):
        return []
    ship = core.ships(op._s['root'], op.context_name)[op._index]
    target_name = core.get(ship, 'Name') or 'Unnamed'
    target = (destination_scope(op._s['links']), op.context_name, op._index)
    origin = getattr(op, '_origin', None)
    changed = origin and target != (origin['scope'], origin['context'], origin['index'])
    selected = getattr(op, '_initial_destination', None)
    changed_selection = selected and (op.context_name, op._index) != selected
    different_name = bool(op._name and op._name != target_name)
    if origin and not (changed or changed_selection or different_name):
        return []
    heading = ('DIFFERENT SHIP / DESTINATION — CHECK BEFORE OVERWRITING'
               if changed or changed_selection else
               'VERIFY OVERWRITE TARGET — SCENE SOURCE UNKNOWN' if not origin else
               'SHIP NAME WILL CHANGE — CHECK BEFORE OVERWRITING')
    lines = [heading,
             f'Replacing: {op.context_name} / Slot {op._index + 1}: {target_name}',
             f'With scene: {op._name or "Unnamed build"}']
    if changed:
        lines.append(f'Scene source: {origin["context"]} / Slot {origin["index"] + 1}: {origin["name"]}')
        if origin['scope'] != target[0]:
            lines.append('The scene source belongs to a different save.')
    return lines


def snapshot(context):
    if ship_management.SESSION is not None:
        raise ValueError('Finish or discard the Ship Management draft before editing a save from I/O.')
    data = context.scene.nms_save_data
    slot = data.get_current_slot_data()
    if not slot:
        raise ValueError('Select an account and save slot first.')
    links = list(dict.fromkeys(str(Path(p)) for p in slot['saves'] if p and Path(p).exists()))
    root, hashes, source = ship_files.read(links)
    cache = data.extracted_base_data
    if str(source) != cache.get('source_path') or hashes[str(source)] != cache.get('source_hash'):
        raise ValueError('The save changed. Refresh the save list before continuing.')
    return dict(root=root, source=str(source), hashes=hashes, links=links, scene=context.scene, expected=io.cache_key(data))


def check_snapshot(s, context):
    if (ship_management.SESSION is not None or context.scene != s['scene']
            or io.cache_key(context.scene.nms_save_data) != s['expected']):
        raise ValueError('The save selection or editing session changed. Review again.')


def scene_parts(context, optimized, progress):
    context.view_layer.update()
    objects = context.scene.nms_main.serialise(objects_only=True, progress=progress, progress_range=(.02, .65))
    repair.validate_parts(objects)
    name = context.scene.nms_base_tool.string_base.strip()
    config = None
    if optimized:
        from . import corvette_optimizer
        from .. import BUILDER
        config = corvette_optimizer.load_settings()
        progress.update(.70, 'Ordering and checking parts')
        objects, counts = corvette_optimizer.core.optimize(objects, config, name_for_part=BUILDER.get_nice_name)
    else:
        counts = dict(before=len(objects), after=len(objects), moved=0, removed=0)
    return objects, name, counts, repair.fingerprint([objects, name, config, build_metadata.save_owner(context.scene.nms_base_tool)])


def warning(layout, objects):
    message = repair.cockpit_warning(objects)
    if message:
        box = layout.box(); box.alert = True
        for line in textwrap.wrap(message, 76):
            box.label(text=line)


def preservation(layout, resets, new=False):
    if new:
        layout.label(text='New ship: minimal Corvette inventory, technology and stats.')
    else:
        layout.label(text='Keeps readable inventories, technology, hyperslots, class and stats.')
    for message in resets:
        row = layout.column(align=True); row.alert = True
        for line in textwrap.wrap(message, 76):
            row.label(text=line)


def refresh_selection(s, context_name, index):
    data = s['scene'].nms_save_data
    data.refresh_bases_list()
    data.nms_base_type = 'PlayerShipBase'
    selected = next((b for b in io.entries(data) if b.base_type == 'PlayerShipBase'
                     and b.save_context == context_name and b.user_data == index), None)
    if selected:
        data.nms_base_index = io.identifier(selected)


def commit(s, context, report):
    with progress_ui.Activity('Saving Corvette') as progress:
        _commit(s, context, report, progress)


def _commit(s, context, report, progress):
    progress.update(.01, 'Checking reviewed destination')
    check_snapshot(s, context)
    if s.get('signature'):
        if scene_parts(context, s['optimized'], progress)[-1] != s['signature']:
            raise ValueError('Scene or optimizer settings changed. Review the export again.')
    plan = s['plan']
    progress.update(.73, 'Preparing reviewed ship data')
    draft = repair.apply_plan(s['root'], plan)
    progress.update(.80, 'Validating ship data and preserved records')
    repair.validate_reviewed_draft(s['root'], draft, [plan])
    ship_files.commit(draft, s['links'], s['hashes'], progress=progress_ui.Range(progress, .85, .97))
    if s.get('signature'):
        remember_ship_source(s['scene'], s['links'], plan['context'], plan['index'],
                             core.get(plan['payload']['ship'], 'Name'))
    progress.update(.98, 'Refreshing Corvette list')
    try:
        refresh_selection(s, plan['context'], plan['index'])
    except Exception:
        report({'WARNING'}, 'Saved with backups. Refresh the save list to see the Corvette.')
        return
    message = f"{s['caption']} in ship slot {plan['index'] + 1}, with verified backups."
    if repair.cockpit_warning(plan['payload']['objects']):
        report({'WARNING'}, message + ' No cockpit: ship will be unflyable; none was added.')
    else:
        report({'INFO'}, message)
    progress.update(1.0, 'Corvette saved with verified backups')


def submit(s, context, report):
    # Dismiss the review before displaying the existing viewport progress bar.
    if bpy.app.background or context.window is None:
        commit(s, context, report)
        return
    token = uuid4().hex
    _pending[token] = s
    window = context.window
    def run():
        try:
            if token in _pending and any(w == window for w in bpy.context.window_manager.windows) and window.scene == s['scene']:
                with bpy.context.temp_override(window=window, scene=s['scene']):
                    bpy.ops.bbe.corvette_commit('EXEC_DEFAULT', token=token)
        finally:
            _pending.pop(token, None)
        return None
    bpy.app.timers.register(run, first_interval=.1)


class BBE_OT_corvette_commit(bpy.types.Operator):
    bl_idname = 'bbe.corvette_commit'
    bl_label = 'Save Reviewed Corvette'
    token: bpy.props.StringProperty(options={'HIDDEN'})

    def execute(self, context):
        try:
            s = _pending.pop(self.token, None)
            if s is None:
                raise ValueError('The Corvette review expired.')
            commit(s, context, self.report)
        except Exception as exc:
            report_error(self, {'ERROR'}, str(exc)); return {'CANCELLED'}
        return {'FINISHED'}


class BBE_OT_corvette_repair_keep(bpy.types.Operator):
    bl_idname = 'bbe.corvette_repair_keep'
    bl_label = 'Repair Corvette — Keep My Build'
    bl_description = ('Repair the selected game-save build while keeping its parts and readable ship data. '
                      'I/O saves after confirmation; Ship Management stages until Save Changes. No cockpit is added')
    context_name: bpy.props.StringProperty(options={'HIDDEN'})
    index: bpy.props.IntProperty(default=-1, options={'HIDDEN'})
    base_index: bpy.props.IntProperty(default=-1, options={'HIDDEN'})
    expected: bpy.props.StringProperty(options={'HIDDEN'})
    in_manager: bpy.props.BoolProperty(default=False, options={'HIDDEN'})
    anchor: bpy.props.IntProperty(name='Keep objects from build record', min=1)
    confirm: bpy.props.BoolProperty(name='This slot should be a Corvette; repair it with the build shown', default=False)
    confirm_duplicates: bpy.props.BoolProperty(name='Remove the other duplicate builds listed above', default=False)
    confirm_resets: bpy.props.BoolProperty(name='Allow the data resets listed above', default=False)

    def invoke(self, context, event):
        try:
            if self.in_manager:
                self._session = ship_management.state()
                self._session['busy'] = True
                self.context_name, self.index = self._session['context'], self._session['index']
                self._s = dict(root=self._session['root'])
                self._fingerprint = repair.fingerprint(self._s['root'])
            else:
                self._s = snapshot(context)
                if self.expected != self._s['expected']:
                    raise ValueError('Save selection changed. Reopen the repair.')
            self._records = repair.linked_builds(self._s['root'], self.context_name, self.index)
            if not self._records:
                raise ValueError('No saved build exists to preserve. Export your scene to this ship or replace it from a file.')
            self.anchor = (self.base_index if self.base_index in self._records else self._records[0]) + 1
            self.confirm = self.confirm_duplicates = self.confirm_resets = False
            self._reviewed_anchor = self.anchor
            self._prepare()
            return context.window_manager.invoke_props_dialog(self, width=660, confirm_text='Stage Repair' if self.in_manager else 'Repair Corvette')
        except Exception as exc:
            self.cancel(context); report_error(self, {'ERROR'}, str(exc)); return {'CANCELLED'}

    def _prepare(self):
        self._payload, self._resets = repair.rebuild_payload(self._s['root'], self.context_name, self.index, self.anchor - 1)

    def check(self, context):
        if self.anchor != getattr(self, '_reviewed_anchor', self.anchor):
            self.confirm = self.confirm_duplicates = self.confirm_resets = False
        self._reviewed_anchor = self.anchor
        try:
            self._prepare(); self._error = ''
        except ValueError as exc:
            self._error = str(exc)
        return True

    def draw(self, context):
        l = self.layout
        help_button(l, 'REPAIR')
        ship = core.ships(self._s['root'], self.context_name)[self.index]
        l.label(text=f"Destination: {self.context_name} / Slot {self.index + 1}: {core.get(ship, 'Name') or 'Unnamed'}")
        bases = core.get(core.player(self._s['root'], self.context_name), 'PersistentPlayerBases')
        for n in self._records:
            l.label(text=f"Build {n + 1}: {core.get(bases[n], 'Name')} ({len(core.get(bases[n], 'Objects', []))} parts)")
        if len(self._records) > 1:
            l.prop(self, 'anchor'); l.prop(self, 'confirm_duplicates')
        if getattr(self, '_error', ''):
            l.label(text=self._error, icon='ERROR'); return
        l.label(text=f"Preserves all {len(self._payload['objects'])} parts, their transforms and colors.")
        preservation(l, self._resets)
        if self._resets:
            l.prop(self, 'confirm_resets')
        warning(l, self._payload['objects'])
        l.label(text='Other ships and the freighter are preserved. No parts are added.')
        l.label(text='Save Changes writes the repair with backups.' if self.in_manager else 'Verified backups are created before saving.')
        l.prop(self, 'confirm')

    def cancel(self, context):
        if self.in_manager and ship_management.SESSION is getattr(self, '_session', None):
            ship_management.finish_dialog()

    def execute(self, context):
        try:
            if not self.confirm:
                raise ValueError('Confirm the destination before repairing. Nothing was written.')
            self._prepare()
            if self._resets and not self.confirm_resets:
                raise ValueError('Review and confirm the listed data resets before repairing.')
            plan = repair.make_plan(self._s['root'], self.context_name, self.index, self._payload, 'FULL',
                                    self.anchor - 1, self.confirm_duplicates)
            if self.in_manager:
                s = ship_management.state()
                if s is not self._session or repair.fingerprint(s['root']) != self._fingerprint:
                    raise ValueError('Ship Management changed. Review the repair again.')
                draft = repair.apply_plan(s['root'], plan)
                plans = [*s.get('repairs', []), plan]
                repair.validate_reviewed_draft(s['original'], draft, plans)
                s.update(root=draft, repairs=plans, dirty=True, error='Repair staged. Review, then Save Changes.')
                ship_management.refresh_status(s); ship_management.finish_dialog()
            else:
                check_snapshot(self._s, context)
                self._s.update(plan=plan, caption='Corvette repaired')
                submit(self._s, context, self.report)
        except Exception as exc:
            self.cancel(context); report_error(self, {'ERROR'}, str(exc)); return {'CANCELLED'}
        return {'FINISHED'}


def context_items(self, context):
    return _dialogs.get(self.dialog_key, {}).get('contexts', _MAIN_CONTEXT)


def slot_items(self, context):
    return _dialogs.get(self.dialog_key, {}).get('slots', {}).get((self.context_name, self.destination), _NO_SLOTS)


def minimal_slot_items(self, context):
    return _dialogs.get(self.dialog_key, {}).get('minimal_slots', _NO_SLOTS)


class BBE_OT_io_add_minimal_corvette(bpy.types.Operator):
    bl_idname = 'bbe.io_add_minimal_corvette'
    bl_label = 'Add Minimal Corvette'
    bl_description = 'Create an S-class starter Corvette in an empty ship slot and select it in I/O'
    dialog_key: bpy.props.StringProperty(options={'HIDDEN'})
    slot: bpy.props.EnumProperty(name='Empty ship slot', items=minimal_slot_items)
    ship_name: bpy.props.StringProperty(name='Ship name', default='New Corvette', maxlen=80)

    @classmethod
    def poll(cls, context):
        data = context.scene.nms_save_data
        return data.nms_base_type == 'PlayerShipBase' and data.is_base_data_loaded()

    def invoke(self, context, event):
        try:
            self._snapshot = snapshot(context)
            state = self._snapshot
            self._roots = {}
            for path in state['links']:
                if path == state['source']:
                    self._roots[path] = state['root']
                else:
                    save = ship_files.SaveFile(path)
                    self._roots[path] = save.load()
                    if save.source_hash != state['hashes'][path]:
                        raise ValueError('The save changed. Refresh the save list before continuing.')

            selected = context.scene.nms_save_data.get_current_base_identifiers()
            preferred = selected.save_context if selected else core.get(state['root'], 'ActiveContext')
            choices = []
            problems = []
            for ctx in sorted(core.contexts(state['root']), key=lambda ctx: ctx != preferred):
                if not all(ctx in core.contexts(root) for root in self._roots.values()):
                    continue
                available = set(range(12))
                try:
                    for root in self._roots.values():
                        core.validate_links(root, ctx)
                        available.intersection_update(repair.empty_ship_slots(root, ctx))
                except ValueError as exc:
                    problems.append(str(exc))
                    continue
                title = 'Expedition' if ctx == 'Season' else ctx
                choices.extend((f'{ctx}:{i}', f'{title} / Slot {i + 1}', '') for i in sorted(available))
            if not choices:
                raise ValueError(' '.join(problems) or 'No ship slot is empty across the selected save points.')
            self.dialog_key = uuid4().hex
            _dialogs[self.dialog_key] = {'minimal_slots': choices}
            self.slot = choices[0][0]
            return context.window_manager.invoke_props_dialog(self, width=360, confirm_text='Add Corvette')
        except Exception as exc:
            self.cancel(context)
            report_error(self, {'ERROR'}, str(exc))
            return {'CANCELLED'}

    def draw(self, context):
        self.layout.prop(self, 'slot')
        self.layout.prop(self, 'ship_name')
        self.layout.label(text='Creates an S-class starter ship in the save.')

    def cancel(self, context):
        _dialogs.pop(self.dialog_key, None)

    def execute(self, context):
        try:
            if self.slot not in {item[0] for item in _dialogs.get(self.dialog_key, {}).get('minimal_slots', [])}:
                raise ValueError('Reopen Add Minimal Corvette to choose an empty ship slot.')
            check_snapshot(self._snapshot, context)
            ctx, number = self.slot.split(':')
            index = int(number)
            for root in self._roots.values():
                core.add_minimal(root, ctx, index, self.ship_name)
            ship_files.commit_roots(self._roots, self._snapshot['hashes'])
        except Exception as exc:
            report_error(self, {'ERROR'}, str(exc))
            return {'CANCELLED'}
        finally:
            self.cancel(context)
        try:
            refresh_selection(self._snapshot, ctx, index)
        except Exception:
            self.report({'WARNING'}, 'Corvette saved with backups. Refresh the save list to select it.')
        else:
            self.report({'INFO'}, f'Added {self.ship_name.strip()} to ship slot {index + 1} with verified backups.')
        return {'FINISHED'}


class BBE_OT_corvette_export(bpy.types.Operator):
    bl_idname = 'bbe.corvette_export'
    bl_label = 'Export Corvette to Save'
    bl_description = ('Review exporting current scene parts over a selected ship or to a new empty slot. '
                      'Writes the game save after confirmation with backups; Blender Undo does not undo save-file writes')
    dialog_key: bpy.props.StringProperty(options={'HIDDEN'})
    destination: bpy.props.EnumProperty(name='Destination', items=[
        ('CHOOSE', 'Choose destination', 'Choose an existing ship or explicitly create a new ship'),
        ('SELECTED', 'Overwrite selected ship', 'Replace its build with scene parts; keep readable inventory, technology, hyperslots and stats. Non-Corvette ships are converted'),
        ('NEW', 'New empty ship slot', 'Create a Corvette in an unused slot with minimal default inventory/stats and exactly the scene objects; no template parts are added')])
    context_name: bpy.props.EnumProperty(name='Save context', items=context_items)
    slot: bpy.props.EnumProperty(name='Ship slot', items=slot_items)
    optimized: bpy.props.BoolProperty(default=False, options={'HIDDEN'})
    confirm: bpy.props.BoolProperty(name='Confirm this destination and export', default=False)
    confirm_resets: bpy.props.BoolProperty(name='Allow the data resets listed above', default=False)
    confirm_duplicates: bpy.props.BoolProperty(name='Replace all duplicate builds linked to this slot', default=False)

    def invoke(self, context, event):
        try:
            self._s = snapshot(context)
            root = self._s['root']
            self._contexts = [(c, 'Expedition' if c == 'Season' else 'Main', '') for c in core.contexts(root)]
            self._slots = {}
            for ctx, _, _ in self._contexts:
                empty = repair.empty_ship_slots(root, ctx)
                self._slots[ctx, 'NEW'] = [(str(i), f'Slot {i+1}: Empty', '') for i in empty] or [('NONE', 'No empty ship slots', '')]
                self._slots[ctx, 'SELECTED'] = [('NONE', 'Choose ship to overwrite', '')] + [
                    (str(i), f"Slot {i+1}: {core.get(ship, 'Name') or 'Unnamed'}", 'Corvette' if core.corvette(ship) else 'Will be converted to a Corvette')
                    for i, ship in enumerate(core.ships(root, ctx)) if i not in empty]
            # RNA enum callbacks receive OperatorProperties, not this Python
            # operator instance. Keep choices/strings alive behind an RNA key.
            self.dialog_key = uuid4().hex
            _dialogs[self.dialog_key] = dict(contexts=self._contexts, slots=self._slots)
            selected = context.scene.nms_save_data.get_current_base_identifiers()
            current_context = selected.save_context if selected else core.get(root, 'ActiveContext')
            self.context_name = current_context if current_context in core.contexts(root) else self._contexts[0][0]
            valid_selected = selected and selected.base_type == 'PlayerShipBase' and type(selected.user_data) is int and 0 <= selected.user_data < 12
            self._initial_destination = (selected.save_context, selected.user_data) if valid_selected else None
            self._origin = None
            try:
                origin = json.loads(context.scene.get('bbe_ship_export_origin', 'null'))
                if (isinstance(origin, dict) and isinstance(origin.get('scope'), str)
                        and origin.get('context') in ('Main', 'Season')
                        and type(origin.get('index')) is int and 0 <= origin['index'] < 12
                        and isinstance(origin.get('name'), str)):
                    self._origin = origin
            except (ValueError, TypeError):
                pass
            self.destination = 'SELECTED' if valid_selected else 'CHOOSE'
            self.slot = str(selected.user_data) if valid_selected else 'NONE'
            with progress_ui.Activity('Preparing Corvette export') as progress:
                self._objects, self._name, self._counts, self._signature = scene_parts(context, self.optimized, progress)
            self.confirm = self.confirm_resets = self.confirm_duplicates = False
            self._scope = self.context_name, self.destination
            self._choice = None
            self.check(context)
            return context.window_manager.invoke_props_dialog(
                self, width=660, confirm_text='Export Corvette')
        except Exception as exc:
            self.cancel(context)
            report_error(self, {'ERROR'}, str(exc)); return {'CANCELLED'}

    def cancel(self, context):
        _dialogs.pop(getattr(self, 'dialog_key', ''), None)

    def check(self, context):
        scope = self.context_name, self.destination
        if scope != getattr(self, '_scope', scope):
            self.slot = self._slots.get(scope, _NO_SLOTS)[0][0]
        self._scope = scope
        choice = self.context_name, self.destination, self.slot
        if choice == self._choice:
            return False
        self._choice = choice
        self.confirm = self.confirm_resets = self.confirm_duplicates = False
        self._error = ''
        try:
            if self.destination not in ('SELECTED', 'NEW'):
                raise ValueError('Select a ship to overwrite, or choose Create new ship. Nothing was written.')
            if not self.slot.isdigit():
                raise ValueError('Choose a destination ship slot.')
            self._index = int(self.slot)
            self._records = repair.linked_builds(self._s['root'], self.context_name, self._index)
            self._anchor = self._records[0] if self._records else None
            self._payload, self._resets = repair.rebuild_payload(self._s['root'], self.context_name, self._index,
                self._anchor, self._objects, self._name or None, new=self.destination == 'NEW')
        except (ValueError, KeyError) as exc:
            self._error = str(exc)
        return True

    def draw(self, context):
        l = self.layout
        help_button(l, 'EXPORT')
        if self.destination == 'CHOOSE':
            l.label(text='No ship is selected.', icon='QUESTION')
            l.label(text='Create a new ship in an empty slot to save this build?')
            l.prop(self, 'context_name')
            new = l.column()
            new.enabled = self._slots[self.context_name, 'NEW'][0][0] != 'NONE'
            new.prop_enum(self, 'destination', 'NEW', text='Create new ship in an empty slot', icon='ADD')
            if not new.enabled:
                l.label(text='No empty ship slots in this save context.', icon='INFO')
            l.prop_enum(self, 'destination', 'SELECTED', text='Choose an existing ship instead', icon='VIEWZOOM')
            l.label(text='Nothing is saved until you choose and confirm a destination.')
            return
        l.prop(self, 'context_name')
        row = l.row(align=True)
        row.prop_enum(self, 'destination', 'SELECTED')
        new = row.row(align=True); new.enabled = self._slots[self.context_name, 'NEW'][0][0] != 'NONE'
        new.prop_enum(self, 'destination', 'NEW')
        l.prop(self, 'slot')
        l.label(text=f"Scene parts: {self._counts['before']} → {self._counts['after']}")
        if self.optimized:
            l.label(text=f"Reordered: {self._counts['moved']} / Identical duplicates removed: {self._counts['removed']}")
        if self._error:
            l.label(text=self._error, icon='ERROR'); return
        l.label(text=f"Destination: {self.context_name} / Slot {self._index+1}")
        l.label(text=f"Ship Name: {core.get(self._payload['ship'], 'Name')}")
        changed = overwrite_warning(self)
        if changed:
            box = l.box(); box.alert = True
            for line in changed:
                for wrapped in textwrap.wrap(line, 76):
                    box.label(text=wrapped, icon='ERROR' if wrapped == changed[0] else 'NONE')
        if len(self._records) > 1:
            l.label(text='Duplicate builds to replace: ' + ', '.join(str(n+1) for n in self._records), icon='ERROR')
            l.prop(self, 'confirm_duplicates')
        build_metadata.draw_save_warning(l, context.scene.nms_base_tool)
        preservation(l, self._resets, new=self.destination == 'NEW')
        if self._resets:
            l.prop(self, 'confirm_resets')
        warning(l, self._objects)
        l.label(text='Only the scene’s parts are exported. No template parts are added.')
        l.label(text='Other ships and the freighter are preserved; verified backups precede writes.')
        row = l.row(); row.alert = bool(changed)
        row.prop(self, 'confirm')

    def execute(self, context):
        try:
            self.check(context)
            if self._error:
                raise ValueError(self._error)
            if not self.confirm:
                raise ValueError('Confirm the export destination. Nothing was written.')
            if self._resets and not self.confirm_resets:
                raise ValueError('Confirm the listed data resets before exporting.')
            check_snapshot(self._s, context)
            self._payload['owner_override'] = build_metadata.save_owner(context.scene.nms_base_tool)
            plan = repair.make_plan(self._s['root'], self.context_name, self._index, self._payload, 'FULL',
                                    self._anchor, self.confirm_duplicates)
            self._s.update(plan=plan, signature=self._signature, optimized=self.optimized,
                           caption='Corvette exported')
            submit(self._s, context, self.report)
        except Exception as exc:
            self.cancel(context)
            report_error(self, {'ERROR'}, str(exc)); return {'CANCELLED'}
        self.cancel(context)
        return {'FINISHED'}


@persistent
def clear_pending(_=None):
    _pending.clear()
    _dialogs.clear()


CLASSES = (BBE_OT_corvette_commit, BBE_OT_corvette_repair_keep, BBE_OT_io_add_minimal_corvette, BBE_OT_corvette_export)


def register():
    for cls in CLASSES:
        bpy.utils.register_class(cls)
    bpy.app.handlers.load_pre.append(clear_pending)


def unregister():
    clear_pending()
    if clear_pending in bpy.app.handlers.load_pre:
        bpy.app.handlers.load_pre.remove(clear_pending)
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)
