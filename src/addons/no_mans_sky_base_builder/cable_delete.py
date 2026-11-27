"""Plan snapped cable cleanup before an object deletion. Nothing runs at idle."""
from collections import defaultdict
from functools import wraps
from types import SimpleNamespace

import bpy

from . import cable_connections as cables, i18n, wire_selection
from .utils import curve


def selection(context, source):
    if source == 'OUTLINER':
        ids = getattr(context, 'selected_ids', ())
        if any(not isinstance(item, bpy.types.Object) for item in ids):
            return set()  # Leave mixed datablocks and collections to the Outliner.
    else:
        ids = context.selected_objects or ()
    return {obj for obj in ids if obj.is_editable and obj.name in context.scene.objects}


def deletion_targets(scene, selected, source, hierarchy):
    targets = set(selected)
    if source == 'BUILDER':
        guides = {obj.name for obj in selected if curve.is_bezier_or_nurbs_path(obj)}
        parents = {obj for obj in selected if obj.name not in guides}
        # Object.children scans all Blender objects. Walk the scene once for a
        # batch of floor tiles instead of repeating that scan for each tile.
        if parents:
            targets.update(obj for obj in bpy.data.objects if obj.parent in parents)
        if guides:
            followers = curve.get_curve_children_map(bpy.data.objects)
            targets.update(obj for name in guides for obj in followers.get(name, ()))
    elif hierarchy:
        targets.update(child for obj in selected for child in obj.children_recursive
                       if child.name in scene.objects and child.is_editable)
    return targets


def is_point(obj):
    return obj is not None and obj.get('rig_item') and obj.get('SnapID') == 'POWER_CONTROL'


def binding(point):
    owner = cables.attached_device(point)
    if owner is not None:
        return owner
    if point.parent is not None and (point.get('bbe_socket_key') or point.get('snapped_to') == point.parent.name):
        return point.parent
    if 'bbe_socket_key' not in point and point.get('snapped_to'):
        # Older tools explicitly recorded the socket owner by name.
        return bpy.data.objects.get(point['snapped_to'])
    return None


class DeletePlan:
    def __init__(self, scene, targets):
        self.targets = targets
        self.spans = {}
        self.incident = defaultdict(set)
        self.bound = {}
        self.attached = set()
        self.selected_spans = set()
        dependents = defaultdict(list)
        for obj in scene.objects:
            if obj.get('ObjectID') in cables.KINDS:
                ends = {point for point in cables.endpoints(obj) if is_point(point)}
                self.spans[obj] = ends
                for point in ends:
                    self.incident[point].add(obj)
                if obj in targets:
                    self.selected_spans.add(obj)
            elif is_point(obj):
                owner = binding(obj)
                if owner is not None:
                    dependents[owner].append(obj)
        # A legacy endpoint can snap to another endpoint. Follow bindings
        # toward controls only; never traverse a span into the next device.
        pending = list(targets & dependents.keys())
        while pending:
            owner = pending.pop()
            for point in dependents.get(owner, ()):
                if point not in self.bound:
                    self.bound[point] = owner
                    pending.append(point)
        for point in self.bound.keys() | (targets & self.incident.keys()):
            self.attached.update(self.incident.get(point, ()))
        self.attached.difference_update(self.selected_spans)

    @property
    def relevant(self):
        return bool(self.attached or self.selected_spans or self.bound)

    def apply(self, context, remove_attached, global_delete):
        spans = self.selected_spans | (self.attached if remove_attached else set())
        points = set(self.bound)
        for span in spans:
            points.update(self.spans[span])
        points.update(self.targets & self.incident.keys())
        pending = list(points)
        while pending:
            owner = binding(pending.pop())
            if is_point(owner) and owner not in points and owner.name in context.scene.objects:
                points.add(owner)
                pending.append(owner)
        # Consult real ID users as well as legacy, name-based endpoints. A rig
        # in another scene or a custom dependency can still need the point.
        users = bpy.data.user_map(subset=points) if points else {}
        keep = set()
        for point in points:
            other_users = users.get(point, set()) - self.targets - spans - points
            if (self.incident.get(point, set()) - spans or
                    any(not isinstance(user, (bpy.types.Collection, bpy.types.Scene)) for user in other_users)):
                keep.add(point)
        # Old rigs can drive one endpoint from another. Keep the entire chain
        # if an outside object still uses its last endpoint.
        pending = list(keep)
        while pending:
            point = pending.pop()
            owner = binding(point)
            if owner in points and owner not in keep:
                keep.add(owner)
                pending.append(owner)
        doomed = (self.targets | spans | points) - keep
        root_folders = set(context.scene.collection.children)
        folders = {folder for obj in spans | (points - keep) for folder in obj.users_collection
                   if folder in root_folders and folder.library is None
                   and folder.name == cables.COLLECTIONS.get(folder.get('bbe_cable_kind'))}
        context.view_layer.update()
        for point in keep:
            if point in self.bound and self.bound[point] in doomed:
                # Normal Blender Delete may unlink just this scene.
                if global_delete or len(point.users_scene) <= 1 or len(self.bound[point].users_scene) <= 1:
                    world = point.matrix_world.copy()
                    if cables.attached_device(point) is not None:
                        for axis in range(3):
                            point.driver_remove('location', axis)
                    if point.parent == self.bound[point]:
                        point.parent = None
                    point.matrix_world = world
                    for key in ('bbe_socket_key', 'snapped_to'):
                        if key in point:
                            del point[key]
            survivors = self.incident.get(point, set()) - spans
            if survivors and point.get('power_line') not in {obj.name for obj in survivors}:
                point['power_line'] = min(obj.name for obj in survivors)

        if global_delete:
            bpy.data.batch_remove(doomed)
        elif doomed:
            # Let Blender handle scene-local unlinking, including multi-scene
            # objects. The Outliner's selection can differ from the viewport.
            with context.temp_override(selected_objects=list(doomed)):
                bpy.ops.object.delete('EXEC_DEFAULT', use_global=False, confirm=False)
        for folder in folders:
            if not folder.objects and not folder.children and folder.users == 1:
                bpy.data.collections.remove(folder)
        wire_selection.invalidate()


def make_plan(context, source, hierarchy=False):
    selected = selection(context, source)
    if not selected:
        return None
    targets = deletion_targets(context.scene, selected, source, hierarchy)
    if not any(obj.get('ObjectID') or is_point(obj) for obj in targets):
        return None
    plan = DeletePlan(context.scene, targets)
    return plan if plan.relevant else None


def ask(operator, context, plan):
    if not operator.properties.is_property_set('remove_cabling'):
        operator.remove_cabling = True
    operator._scene = context.scene.session_uid
    operator._targets = {obj.session_uid for obj in plan.targets}
    operator._cables = {obj.session_uid for obj in plan.attached}
    return context.window_manager.invoke_props_dialog(
        operator, width=350, title=i18n.interface('Delete connected cabling?'),
        confirm_text=i18n.interface('Delete'), translate=False)


def draw(operator):
    layout = i18n.localized_layout(operator.layout)
    count = len(getattr(operator, '_cables', ()))
    label = i18n.interface('Connected cables and pipes')
    layout.label(text=f"{label} · {count}", icon='LINKED', translate=False)
    layout.prop(operator, 'remove_cabling', text='Delete connected cables and unused points')
    layout.label(text=('Shared points stay with their remaining cables.' if operator.remove_cabling
                       else 'Kept cable ends stay in place.'))


def valid(operator, context, plan):
    return not hasattr(operator, '_targets') or (
        plan is not None and operator._scene == context.scene.session_uid
        and operator._targets == {obj.session_uid for obj in plan.targets}
        and operator._cables == {obj.session_uid for obj in plan.attached})


class BBE_OT_delete_with_cables(bpy.types.Operator):
    bl_idname = 'bbe.delete_with_cables'
    bl_label = 'Delete'
    bl_options = {'UNDO', 'INTERNAL'}
    use_global: bpy.props.BoolProperty(options={'HIDDEN','SKIP_SAVE'})
    hierarchy: bpy.props.BoolProperty(options={'HIDDEN','SKIP_SAVE'})
    from_menu: bpy.props.BoolProperty(options={'HIDDEN','SKIP_SAVE'})
    remove_cabling: bpy.props.BoolProperty(default=False, options={'SKIP_SAVE'})

    def source(self, context):
        return 'OUTLINER' if context.area.type == 'OUTLINER' else 'VIEWPORT'

    def invoke(self, context, event):
        source = self.source(context)
        plan = make_plan(context, source, self.hierarchy) if context.mode == 'OBJECT' else None
        if plan is None:
            if not self.from_menu:
                return {'PASS_THROUGH'}
            if source == 'OUTLINER':
                return bpy.ops.outliner.delete('INVOKE_DEFAULT', hierarchy=self.hierarchy)
            return bpy.ops.object.delete('EXEC_DEFAULT', use_global=self.use_global, confirm=False)
        if plan.attached:
            return ask(self, context, plan)
        plan.apply(context, False, self.use_global)
        return {'FINISHED'}

    def draw(self, context):
        draw(self)

    def execute(self, context):
        plan = make_plan(context, self.source(context), self.hierarchy)
        if not plan or not valid(self, context, plan):
            return {'CANCELLED'}
        plan.apply(context, self.remove_cabling, self.use_global)
        return {'FINISHED'}


class _DeleteLayout:
    """Forward Blender's own menu, substituting only its standard Delete item."""
    def __init__(self, layout, native_id):
        object.__setattr__(self, 'layout', layout)
        object.__setattr__(self, 'native_id', native_id)

    def __getattr__(self, name):
        return getattr(self.layout, name)

    def __setattr__(self, name, value):
        setattr(self.layout, name, value)

    def operator(self, identifier, *args, **kwargs):
        if identifier != self.native_id:
            return self.layout.operator(identifier, *args, **kwargs)
        row = self.layout.row()
        row.operator_context = 'INVOKE_DEFAULT'
        props = row.operator(BBE_OT_delete_with_cables.bl_idname, *args, **kwargs)
        props.from_menu = True
        return props


_keymaps = []
_menus = []


def wrap_menu(original, native_id):
    @wraps(original)
    def wrapper(menu, context):
        source = 'OUTLINER' if native_id == 'outliner.delete' else 'VIEWPORT'
        if context.mode == 'OBJECT' and any(
                obj.get('ObjectID') or is_point(obj) for obj in selection(context, source)):
            menu = SimpleNamespace(layout=_DeleteLayout(menu.layout, native_id))
        return original(menu, context)
    return wrapper


def register():
    bpy.utils.register_class(BBE_OT_delete_with_cables)
    config = bpy.context.window_manager.keyconfigs.addon
    if config:
        for name, space in (('Object Mode','EMPTY'), ('Outliner','OUTLINER')):
            km = config.keymaps.new(name=name, space_type=space, region_type='WINDOW')
            for key in ('X','DEL'):
                for shift in ((False,True) if name == 'Object Mode' else (False,)):
                    item = km.keymap_items.new(BBE_OT_delete_with_cables.bl_idname,key,'PRESS',shift=shift,head=True)
                    item.properties.use_global = shift
                    _keymaps.append((km,item))
    for menu, native in ((bpy.types.VIEW3D_MT_object, 'object.delete'),
                         (bpy.types.VIEW3D_MT_object_context_menu, 'object.delete'),
                         (bpy.types.OUTLINER_MT_object, 'outliner.delete')):
        # Only wrap Blender's built-in draw callback; preserve all menu extensions.
        callbacks = menu._dyn_ui_initialize()
        for index, original in enumerate(callbacks):
            if original.__qualname__ == menu.__name__+'.draw' and original.__module__.startswith('bl_ui.'):
                wrapper = wrap_menu(original, native)
                callbacks[index] = wrapper
                _menus.append((callbacks, original, wrapper))
                break


def unregister():
    for callbacks, original, wrapper in _menus:
        if wrapper in callbacks:
            callbacks[callbacks.index(wrapper)] = original
    _menus.clear()
    for km, item in _keymaps:
        km.keymap_items.remove(item)
    _keymaps.clear()
    bpy.utils.unregister_class(BBE_OT_delete_with_cables)
