"""Allow the normal Move gizmo when a driven cable and both ends are selected.

Blender intersects the location locks of every selected object when drawing
its gizmo. Cable meshes are driven by their ends, so their redundant locks
must not hide the Move arrows for an otherwise movable complete selection.
A single free cable also selects its two private controls for native Move.
"""
import bpy
from bpy.app.handlers import persistent
from . import cable_connections as cables

LINE_IDS = frozenset({'U_POWERLINE', 'U_BYTEBEATLINE', 'U_PIPELINE', 'U_PORTALLINE'})
TAG = '_bbe_endpoint_move_lock'
_rigs = []
_endpoint_uses = {}
_signature = None
_busy = False
_saving = False


def invalidate():
    global _signature
    _signature = None


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
        active = layer.objects.active
        single = (object_mode and active is not None and active.get('ObjectID') in cables.EDITABLE_LINES
                  and context.selected_objects == [active])
        for obj, start, end in _rigs:
            try:
                # A shared junction belongs to other lines too. Only include it
                # in a selection when the user explicitly selects the ends.
                if single and obj == active and all(
                    _endpoint_uses.get(end_obj) == 1 and cables.free_control(end_obj)
                    and not any(end_obj.lock_location) and not end_obj.hide_select
                    and end_obj.name in layer.objects and end_obj.visible_get(view_layer=layer)
                    for end_obj in (start, end)
                ):
                    start.select_set(True, view_layer=layer)
                    end.select_set(True, view_layer=layer)
                complete = object_mode and all(
                    item.name in layer.objects and item.select_get(view_layer=layer)
                    and not item.hide_select and item.visible_get(view_layer=layer)
                    for item in (obj, start, end)
                ) and not any(start.lock_location) and not any(end.lock_location)
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
