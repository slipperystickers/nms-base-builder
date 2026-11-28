"""Compare a game build with the active Blender scene before changing any parts."""
from collections import defaultdict
from itertools import product
from math import floor, isfinite
import bpy

from . import builder, cable_connections, interchange
from .utils import mirror_pivot, material

TAG = 'bbe_game_update_folder'
ROOT = 'Added in Game'
ADDED = 'New Parts'
MOVED = 'Moved in Game'
EDITED = 'Edited in Game'
DELETED = 'Deleted in Game'
REVIEW = 'Needs Review'
EPS = .001


def fields(record):
    part = record.get('ObjectID')
    if not isinstance(part, str) or not part.lstrip('^'):
        raise ValueError('A part is missing its ObjectID.')
    vectors = []
    for key in ('Position', 'Up', 'At'):
        v = record.get(key)
        if not isinstance(v, (list, tuple)) or len(v) != 3 or not all(isinstance(x, (float, int)) and isfinite(x) for x in v):
            raise ValueError(f'{part}: invalid {key}. Supply a full build export.')
        vectors.extend(v)
    return (part.lstrip('^'), int(record.get('UserData', 0)), str(record.get('Message', '')), tuple(vectors))


def close(a, b):
    return all(abs(x-y) <= EPS for x, y in zip(a, b))


def compare(old, new):
    """Consume equal placements one-to-one, then pair only uniquely identifiable edits."""
    left, right = list(map(fields, old)), list(map(fields, new))
    remaining = set(range(len(left)))
    incoming = set(range(len(right)))
    by_cell = defaultdict(set)
    def cell(values):
        return tuple(floor(x/EPS) for x in values[:3])
    for i, (part, colour, msg, v) in enumerate(left):
        by_cell[part, colour, msg, cell(v)].add(i)
    for j, (part, colour, msg, v) in enumerate(right):
        xyz = cell(v)
        for delta in product((0, -1, 1), repeat=3):
            key = tuple(x+y for x, y in zip(xyz, delta))
            candidates = by_cell.get((part, colour, msg, key))
            if candidates:
                i = next((i for i in candidates if close(left[i][3], v)), None)
                if i is not None:
                    candidates.remove(i)
                    remaining.remove(i)
                    incoming.remove(j)
                    break
    unchanged = len(old) - len(remaining)
    pairs = []
    def pair(key, all_records=False):
        groups = []
        for data, rows, indexes in ((left, old, remaining), (right, new, incoming)):
            grouped = defaultdict(list)
            for i in range(len(rows)) if all_records else sorted(indexes):
                k = key(data[i], rows[i])
                if k is not None:
                    grouped[k].append(i)
            groups.append(grouped)
        for k in groups[0].keys() & groups[1].keys():
            a, b = groups[0][k], groups[1][k]
            if len(a) == len(b) == 1 and a[0] in remaining and b[0] in incoming:
                i, j = a[0], b[0]
                pairs.append((i, j, EDITED if close(left[i][3], right[j][3]) else MOVED))
                remaining.remove(i)
                incoming.remove(j)
    def stamped(f, r):
        return (f[0], str(r['Timestamp'])) if r.get('Timestamp') not in (None, '', 0, '0') else None
    pair(stamped, True)
    pair(lambda f, r: (f[0], tuple(round(x, 3) for x in f[3][:3])))
    pair(stamped)  # One remaining member of an otherwise matched timestamp batch.
    return unchanged, sorted(pairs), sorted(remaining), sorted(incoming)


def read_source(context, source, path):
    if source == 'SAVE':
        settings = context.scene.nms_save_data
        if not settings.has_selected_base():
            raise ValueError('Choose the ship or base in Save Manager first.')
        from .save_editor import save_editor_utils
        data = save_editor_utils.import_paticular_base_from_save(
            settings.get_current_base_identifiers(), settings.get_current_slot_data()['saves'])
        if not data:
            raise ValueError('The selected build could not be read.')
        return data
    if source == 'FILE':
        build = interchange.BuildFile.read(path)
    else:
        build = interchange.BuildFile.from_bytes(context.window_manager.clipboard.encode('utf8'), '.json')
    return build.import_document()


def make_plan(context, data):
    b = builder.get_builder()
    sources = []
    context.view_layer.update()
    old = b.object_records(sources=sources, read_only=True)
    rows = data['Objects']
    if not old or not rows:
        raise ValueError('Both the open scene and the incoming build must contain parts.')
    if len(old) != len(sources):
        raise ValueError('This build has generated parts that cannot be matched to individual scene objects.')
    unchanged, pairs, deleted, added = compare(old, rows)
    affected = {sources[i][0] for i in deleted} | {sources[i][0] for i, _, _ in pairs}
    users = bpy.data.user_map(subset=affected) if affected else {}
    def managed(i):
        obj, member = sources[i]
        return (member or obj.type != 'MESH' or not obj.is_editable or len(obj.users_scene) != 1
                or obj.parent or obj.constraints or obj.modifiers or obj.animation_data
                or obj.get('curve_parent') or obj.get('bbe_curve_parent') or obj.get('bbe_preset_part')
                or any(not isinstance(u, (bpy.types.Collection, bpy.types.Scene))
                       for u in users.get(obj, ())))
    pending = {i for i in deleted if managed(i)} | {i for i, _, _ in pairs if managed(i)}
    return sources, old, unchanged, pairs, deleted, added, pending


def folder(parent, label, created):
    found = next((c for c in parent.children if c.get(TAG) == label), None)
    if found and found.users == 1 and found.library is None:
        return found
    c = bpy.data.collections.new(label)
    created.append(c)
    c[TAG] = label
    parent.children.link(c)
    if label == DELETED:
        c.hide_render = c.hide_viewport = True
    return c


def apply(context, data, plan):
    sources, old, _, pairs, deleted, added, pending = plan
    b = builder.get_builder()
    scene = context.scene
    before = set(bpy.data.objects)
    created, links, moved, old_review_links = [], [], [], []
    doomed = set()
    def link(c, obj):
        if obj.name not in c.objects:
            c.objects.link(obj)
            links.append((c, obj))
    try:
        root = folder(scene.collection, ROOT, created)
        def mark(obj, label):
            target = folder(root, label, created)
            link(target, obj)
            for other in list(obj.users_collection):
                if other != target and other in list(root.children) and other.get(TAG):
                    old_review_links.append((other, obj))
                    other.objects.unlink(obj)
            return target
        for i in sorted(pending):
            mark(sources[i][0], REVIEW)
        for j in added:
            row = data['Objects'][j]
            oid = row['ObjectID'].lstrip('^')
            cls = b.get_part_class(oid)
            args = {'compensate_normal': data.get('BaseVersion', 8) >= 5}
            from .part import Part
            if cls is Part or getattr(cls, 'HIGH_RES_COMPATIBLE', False):
                args['high_res'] = bool(scene.bbe_detailed_proxies)
            part = cls.deserialise_from_data(row, b, **args)
            obj = part.object
            if hasattr(part, 'build_rig') and oid in cable_connections.KINDS:
                part.build_rig()
            target = mark(obj, ADDED)
            if oid not in cable_connections.KINDS:
                for c in list(obj.users_collection):
                    if c != target:
                        c.objects.unlink(obj)
        for i, j, label in pairs:
            if i in pending:
                continue
            obj = sources[i][0]
            row = data['Objects'][j]
            previous = old[i]
            moved.append((obj, obj.matrix_world.copy(), previous, obj.data))
            oid = obj['ObjectID']
            if label == MOVED:
                native = b.get_part_class(oid).create_matrix_from_vectors(row['Position'], row['Up'], row['At'])
                obj.matrix_world = mirror_pivot.display_matrix(native, oid) if mirror_pivot.is_normalized(obj) else native
            if int(previous.get('UserData', 0)) != int(row.get('UserData', 0)):
                # Legacy proxies colour their mesh, which may be shared with an unchanged part.
                from .utils import materials_v2
                if obj.data.users > 1 and not materials_v2.is_high_res(obj):
                    obj.data = obj.data.copy()
                material.restore_material(obj, row.get('UserData', 0))
                obj['UserData'] = str(row.get('UserData', 0))
            if 'Message' in previous or 'Message' in row:
                obj['Message'] = str(row.get('Message', ''))
            mark(obj, label)
        for i in deleted:
            if i in pending:
                continue
            obj = sources[i][0]
            ghost = obj.copy()
            # Archive the appearance and transform without registering another game part.
            for key in ('ObjectID', 'SnapID', 'order'):
                if key in ghost:
                    del ghost[key]
            ghost.name = obj.name + ' (deleted in game)'
            ghost.hide_render = True
            link(folder(root, DELETED, created), ghost)
            doomed.add(obj)
        if any(data['Objects'][j]['ObjectID'].lstrip('^') in cable_connections.KINDS for j in added):
            context.view_layer.update()
            cable_connections.bind_imported(scene, {o.session_uid for o in before if o.get('ObjectID') in cable_connections.KINDS})
        if doomed:
            bpy.data.batch_remove(doomed)
    except Exception:
        for obj, matrix, row, mesh in reversed(moved):
            obj.matrix_world = matrix
            if obj.data != mesh:
                obj.data = mesh
            if int(obj.get('UserData', 0)) != int(row.get('UserData', 0)):
                material.restore_material(obj, row.get('UserData', 0))
                obj['UserData'] = str(row.get('UserData', 0))
            if 'Message' in row:
                obj['Message'] = row['Message']
        for c, obj in reversed(links):
            if obj.name in c.objects:
                c.objects.unlink(obj)
        for c, obj in old_review_links:
            if obj.name not in c.objects:
                c.objects.link(obj)
        bpy.data.batch_remove(set(bpy.data.objects) - before)
        for c in reversed(created):
            bpy.data.collections.remove(c)
        raise


SOURCES = [('SAVE', 'Selected Save Manager Build', 'Read the selected base or Corvette from disk'),
           ('FILE', 'Build File…', 'Choose a full exported build'),
           ('CLIPBOARD', 'Clipboard', 'Compare a full build copied as JSON')]


class ChooseUpdate(bpy.types.Operator):
    bl_idname = 'bbe.update_build'
    bl_label = 'Update Current Build'
    bl_description = 'Compare a game build with this scene and review the changes before applying them'

    def invoke(self, context, event):
        def draw(menu, ctx):
            menu.layout.operator_context = 'INVOKE_DEFAULT'
            for source, label, _ in SOURCES:
                row = menu.layout.row()
                if source == 'SAVE':
                    row.enabled = ctx.scene.nms_save_data.has_selected_base()
                row.operator('bbe.preview_build_update', text=label).source = source
        context.window_manager.popup_menu(draw, title=self.bl_label)
        return {'FINISHED'}


class PreviewUpdate(bpy.types.Operator):
    bl_idname = 'bbe.preview_build_update'
    bl_label = 'Review Build Update'
    bl_options = {'UNDO', 'INTERNAL'}
    source: bpy.props.EnumProperty(items=SOURCES)
    filepath: bpy.props.StringProperty(subtype='FILE_PATH')
    filter_glob: bpy.props.StringProperty(default='*.json;*.txt;*.nmsbase;*.nmsship', options={'HIDDEN'})
    show_details: bpy.props.BoolProperty(name='Show part details', options={'SKIP_SAVE'})
    confirm_build: bpy.props.BoolProperty(name='I verified this is the same build', options={'SKIP_SAVE'})

    def invoke(self, context, event):
        if self.source == 'FILE' and not self.filepath:
            context.window_manager.fileselect_add(self)
            return {'RUNNING_MODAL'}
        try:
            self.data = read_source(context, self.source, self.filepath)
            self.plan = make_plan(context, self.data)
        except Exception as exc:
            self.report({'ERROR'}, str(exc))
            return {'CANCELLED'}
        src, old, same, pairs, deleted, added, pending = self.plan
        if not (pairs or deleted or added):
            self.report({'INFO'}, 'This build already matches the scene.')
            return {'CANCELLED'}
        local_name = context.scene.nms_base_tool.string_base
        incoming_name = self.data.get('Name', '')
        self.warn = (same < max(len(old), len(self.data['Objects'])) * .25 or
                     bool(local_name and incoming_name and local_name.casefold() != incoming_name.casefold()))
        self.stamp = self.fingerprint()
        self.scene_id = context.scene.session_uid
        return context.window_manager.invoke_props_dialog(self, width=430, confirm_text='Apply Update')

    def fingerprint(self):
        sources, old, *_ = self.plan
        return ([(o.session_uid, child, record) for (o, child), record in zip(sources, old)],
                frozenset(self.plan[-1]))

    def draw(self, context):
        if not hasattr(self, 'plan'):  # Blender also draws this operator in the file selector.
            return
        layout = self.layout
        _, _, same, pairs, deleted, added, pending = self.plan
        layout.label(text=self.data.get('Name') or 'Incoming build')
        layout.label(text=f'{same} unchanged · {len(added)} new · {len(deleted)} missing')
        layout.label(text=f'{sum(k == MOVED for _, _, k in pairs)} moved · {sum(k == EDITED for _, _, k in pairs)} edited')
        layout.label(text='Use a full build. Parts missing from it are archived.')
        if deleted and added:
            layout.label(text='Unmatched copies are listed as new and missing.')
        if pending:
            layout.label(text=f'{len(pending)} linked parts need manual review.', icon='INFO')
        layout.prop(self, 'show_details')
        if self.show_details:
            sources = self.plan[0]
            details = [(MOVED if label == MOVED else EDITED, sources[i][1] or sources[i][0].name) for i, _, label in pairs]
            details += [(ADDED, self.data['Objects'][j]['ObjectID'].lstrip('^')) for j in added]
            details += [(DELETED, sources[i][1] or sources[i][0].name) for i in deleted]
            for label, name in details[:12]:
                layout.label(text=f'{label} · {name}')
            if len(details) > 12:
                layout.label(text=f'And {len(details)-12} more')
        if self.warn:
            layout.label(text='Build names differ or few placements match.', icon='ERROR')
            layout.prop(self, 'confirm_build')

    def execute(self, context):
        if not hasattr(self, 'plan'):
            if self.source == 'FILE' and self.filepath:
                # The file selector executes its operator. Start a fresh review dialog.
                result = bpy.ops.bbe.preview_build_update('INVOKE_DEFAULT', source='FILE', filepath=self.filepath)
                return {'FINISHED'} if 'RUNNING_MODAL' in result else {'CANCELLED'}
            return {'CANCELLED'}
        try:
            if self.warn and not self.confirm_build:
                raise ValueError('Verify the build before applying these changes.')
            self.plan = make_plan(context, self.data)
            if context.scene.session_uid != self.scene_id or self.fingerprint() != self.stamp:
                raise ValueError('The scene changed during review. Open Update Current Build again.')
            apply(context, self.data, self.plan)
        except Exception as exc:
            self.report({'ERROR'}, str(exc))
            return {'CANCELLED'}
        self.report({'INFO'}, f'Build update complete. See {ROOT} in the Outliner.')
        return {'FINISHED'}

