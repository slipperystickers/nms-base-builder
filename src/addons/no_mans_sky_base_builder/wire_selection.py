"""Allow the normal Move gizmo when a driven cable and both ends are selected.

Blender intersects the location locks of every selected object when drawing
its gizmo. Cable meshes are driven by their ends, so their redundant locks
must not hide the Move arrows for an otherwise movable complete selection.
Selected spans bring their free controls into native Move. Shared junctions
are included only when every incident span is selected.
"""
import bpy
from bpy.app.handlers import persistent
from . import cable_connections as cables

LINE_IDS = frozenset({'U_POWERLINE', 'U_BYTEBEATLINE', 'U_PIPELINE', 'U_PORTALLINE'})
TAG = '_bbe_endpoint_move_lock'
_rigs = []
_endpoint_uses = {}
_signature = None
_selection_key = None
_auto_controls = set()
_busy = False
_saving = False


def invalidate():
    global _signature, _selection_key
    _signature = None
    _selection_key = None
    _auto_controls.clear()


def shared_endpoint(control):
    return _endpoint_uses.get(control, 0) > 1


def _endpoints(obj):
    start, end = cables.endpoints(obj)
    if start is None or end is None or start == end:
        return None
    # Only manage the standard BBE location drivers. Leave custom rigs alone.
    animation = obj.animation_data
    if animation is None:
        return None
    axes = set()
    for curve in animation.drivers:
        driver = curve.driver
        if curve.data_path != 'location' or curve.array_index not in (0, 1, 2):
            continue
        if driver.type != 'SCRIPTED' or len(driver.variables) != 1 or curve.mute:
            continue
        variable = driver.variables[0]
        target = variable.targets[0]
        if (variable.type == 'SINGLE_PROP' and target.id == start
                and target.data_path == 'location.' + 'xyz'[curve.array_index]
                and driver.expression == variable.name and driver.is_valid):
            axes.add(curve.array_index)
    return (start, end) if len(axes) == 3 else None


def _restore():
    for obj, _start, _end in _rigs:
        try:
            if obj.get(TAG) and not all(obj.lock_location):
                obj.lock_location = (True, True, True)
        except ReferenceError:
            pass


def _movable_control(control, layer):
    return (cables.free_control(control) and not any(control.lock_location)
            and not control.hide_select and control.name in layer.objects
            and control.visible_get(view_layer=layer))


def _end_moves_with_selection(control, layer, selected):
    owner = cables.attached_device(control)
    if owner is not None:
        return owner in selected
    return (control.name in layer.objects and control.select_get(view_layer=layer)
            and not control.hide_select and control.visible_get(view_layer=layer)
            and not any(control.lock_location))


def _include_controls(layer, selected):
    """Complete a span selection once, leaving manual endpoint edits alone."""
    global _selection_key
    chosen = {obj for obj, _, _ in _rigs if obj in selected}
    group = len(chosen) > 1 or any(not o.get('rig_item') for o in selected - chosen)
    key = (layer.as_pointer(), frozenset(chosen), group)
    if key == _selection_key:
        return
    _selection_key = key
    if not chosen:
        _auto_controls.clear()
        return

    uses = {}
    for obj, start, end in _rigs:
        if obj in chosen:
            for control in (start, end):
                uses[control] = uses.get(control, 0) + 1
    eligible = {control for control, count in uses.items()
                if count == _endpoint_uses[control] and _movable_control(control, layer)}
    # A lone click on an attached span must still allow its socket to be picked.
    if not group:
        lone = next(iter(chosen))
        if (layer.objects.active != lone or lone.get('ObjectID') not in cables.EDITABLE_LINES
                or len(eligible) != 2 or (selected - chosen - _auto_controls)):
            eligible.clear()
    for control in (_auto_controls & selected) - eligible:
        control.select_set(False, view_layer=layer)
    _auto_controls.intersection_update(eligible & selected)
    for control in eligible - selected:
        control.select_set(True, view_layer=layer)
        _auto_controls.add(control)


@persistent
def refresh_selection(scene=None, _depsgraph=None):
    global _busy, _signature, _rigs
    if _busy or _saving:
        return
    context = bpy.context
    scene = getattr(context, 'scene', None)
    layer = getattr(context, 'view_layer', None)
    if scene is None or layer is None:
        return
    _busy = True
    try:
        signature = (scene.as_pointer(), layer.as_pointer(), len(bpy.data.objects))
        if signature != _signature:
            _restore()
            _rigs = []
            _endpoint_uses.clear()
            for obj in scene.objects:
                if obj.get('ObjectID') not in LINE_IDS:
                    continue
                for end in cables.endpoints(obj):
                    if end is not None:
                        _endpoint_uses[end] = _endpoint_uses.get(end, 0) + 1
                if not obj.get(TAG) and not all(obj.lock_location):
                    continue  # Preserve manual/custom lock configurations.
                ends = _endpoints(obj)
                if ends is not None:
                    if not obj.get(TAG):
                        obj[TAG] = True
                    _rigs.append((obj, *ends))
            _signature = signature
        object_mode = context.mode == 'OBJECT'
        if not _rigs:
            return
        selected = set(context.selected_objects or ()) if object_mode else set()
        _include_controls(layer, selected)
        for obj, start, end in _rigs:
            try:
                complete = obj in selected and not obj.hide_select and all(
                    _end_moves_with_selection(control, layer, selected)
                    for control in (start, end)
                )
                locks = (not complete,) * 3
                if tuple(obj.lock_location) != locks:
                    obj.lock_location = locks
            except ReferenceError:
                invalidate()
    finally:
        _busy = False


@persistent
def reset(_unused=None):
    invalidate()
    refresh_selection()


@persistent
def before_save(_unused=None):
    global _saving
    _saving = True
    _restore()  # Files remain protected when opened without BBE enabled.


@persistent
def after_save(_unused=None):
    global _saving
    _saving = False
    refresh_selection()


_HANDLERS = (
    ('depsgraph_update_post', refresh_selection),
    ('load_post', reset), ('undo_post', reset), ('redo_post', reset),
    ('save_pre', before_save), ('save_post', after_save), ('save_post_fail', after_save),
)


def register():
    for name, callback in _HANDLERS:
        handlers = getattr(bpy.app.handlers, name)
        if callback not in handlers:
            handlers.append(callback)
    reset()


def unregister():
    global _rigs, _saving
    for name, callback in _HANDLERS:
        handlers = getattr(bpy.app.handlers, name)
        if callback in handlers:
            handlers.remove(callback)
    _restore()
    _rigs = []
    _endpoint_uses.clear()
    _saving = False
    invalidate()
