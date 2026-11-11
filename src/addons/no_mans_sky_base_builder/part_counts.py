"""Keep scene collection traversal out of viewport and panel draw callbacks."""
import bpy
from bpy.app.handlers import persistent
from . import undo_guard


_counts = {}
_pending = set()


def count(scene):
    return sum(('ObjectID' in obj) + (obj.get('part_count', 0) if 'GroupID' in obj else 0)
               for obj in scene.collection.all_objects)


def displayed(scene):
    key = scene.as_pointer()
    if key not in _counts:
        _pending.add(key)
    return _counts.get(key, '…')


@persistent
def changed(scene, depsgraph):
    if scene.as_pointer() in _counts and any(depsgraph.id_type_updated(kind) for kind in ('OBJECT', 'COLLECTION', 'SCENE')):
        _pending.add(scene.as_pointer())


@persistent
def reset(*_):
    _counts.clear()
    _pending.clear()


def refresh():
    wm = bpy.context.window_manager
    if not _pending or not wm or wm.is_interface_locked or not undo_guard.history_ready():
        return .2
    pending = _pending.copy()
    _pending.difference_update(pending)
    for scene in bpy.data.scenes:
        key = scene.as_pointer()
        if key not in pending:
            continue
        current = count(scene)
        if _counts.get(key) != current:
            _counts[key] = current
            for window in wm.windows:
                if window.scene == scene:
                    for area in window.screen.areas:
                        if area.type == 'VIEW_3D':
                            area.tag_redraw()
    return .2


_HANDLERS = ((bpy.app.handlers.depsgraph_update_post, changed),
             (bpy.app.handlers.undo_post, reset), (bpy.app.handlers.redo_post, reset),
             (bpy.app.handlers.load_post, reset))


def register():
    reset()
    for handlers, callback in _HANDLERS:
        if callback not in handlers:
            handlers.append(callback)
    if not bpy.app.timers.is_registered(refresh):
        bpy.app.timers.register(refresh, first_interval=.2, persistent=True)


def unregister():
    if bpy.app.timers.is_registered(refresh):
        bpy.app.timers.unregister(refresh)
    for handlers, callback in _HANDLERS:
        if callback in handlers:
            handlers.remove(callback)
    reset()
