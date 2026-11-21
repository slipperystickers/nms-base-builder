"""Keep native Blender cable pastes usable in the destination scene."""
import json
import uuid
from pathlib import Path
import bpy
from bpy.app.handlers import persistent


def unlink_preview_sources(objects):
    # Object Info still owns its mesh source through the node tree. It must
    # have no scene collection membership, just as when initially generated.
    for obj in objects:
        if obj.library is None and obj.get('furby_supply_preview_source'):
            if 'furby_supply_source_id' not in obj:
                obj['furby_supply_source_id'] = uuid.uuid4().hex
            for collection in tuple(obj.users_collection):
                if collection.library is None:
                    collection.objects.unlink(obj)


@persistent
def after_paste(info):
    if not info.import_items:
        return
    buffer_path = Path(bpy.app.tempdir).parent / 'copybuffer.blend'
    imported = {}
    for item in info.import_items:
        if item.id_type != 'OBJECT' or not item.id or item.id.library or not item.source_library:
            continue
        if Path(item.source_library.filepath) == buffer_path:
            imported[item.id] = item.name
    if imported:
        unlink_preview_sources(imported)
        for obj, name in imported.items():
            source_id = obj.get('furby_supply_source_id')
            if obj.get('furby_supply_preview_source') and source_id and obj.users:
                original = bpy.data.objects.get(name)
                if (original and original != obj and original.get('furby_supply_preview_source')
                        and original.get('furby_supply_source_id') == source_id):
                    reuse_dependency(obj, original)
        restore_single_selection(imported)
        organize_paste({obj: name for obj, name in imported.items() if obj.users_collection})


def repair_rig_names(wire, old_name=None):
    from . import cable_connections as cables
    # Blender remaps ID references when pasting, but not strings in custom
    # properties. Only use actual driver and constraint targets for repair.
    anim = wire.animation_data
    start = None
    for fc in anim.drivers if anim else ():
        if fc.data_path == 'location' and fc.driver.variables:
            start = fc.driver.variables[0].targets[0].id
            break
    end = next((c.target for c in wire.constraints if c.type == 'TRACK_TO'), None)
    for key, obj in (('start_control', start), ('end_control', end)):
        if not isinstance(obj,bpy.types.Object) or not obj.get('rig_item') or obj.library:
            continue
        stale = wire.get(key) != obj.name
        if stale:
            wire[key] = obj.name
        if old_name and obj.get('power_line') == old_name:
            obj['power_line'] = wire.name
        elif stale:
            previous = bpy.data.objects.get(obj.get('power_line', ''))
            if not previous or obj not in cables.endpoints(previous):
                obj['power_line'] = wire.name
        device = cables.attached_device(obj)
        if device and obj.get('snapped_to') != device.name:
            obj['snapped_to'] = device.name


def organize_paste(imported):
    from . import cable_connections as cables, wire_selection
    for wire, old_name in imported.items():
        if wire.get('ObjectID') in cables.KINDS and wire.name in bpy.context.scene.objects:
            repair_rig_names(wire, old_name)
            cables.organize(wire)
            wire_selection.invalidate()


@persistent
def repair_saved(*_):
    from . import cable_connections as cables
    unlink_preview_sources(bpy.data.objects)
    for obj in bpy.data.objects:
        if obj.library is None and obj.get('ObjectID') in cables.KINDS:
            repair_rig_names(obj)

def owns_cable(obj):
    from . import cable_connections as cables
    return obj.get('ObjectID') in cables.KINDS


def single_cable_attachments(ctx, wire):
    from . import cable_connections as cables
    if not owns_cable(wire):
        return
    ends = cables.endpoints(wire)
    if all(ends) and all(o == wire or o in ends for o in ctx.selected_objects):
        return [owner for end in ends if (owner := cables.attached_device(end))]

COPY_ORIGIN = '_bbe_native_cable_copy'
SESSION = uuid.uuid4().hex
_keymaps = []
_unused = set()


def local_copy_source(ctx):
    wire = ctx.active_object
    if not wire or ctx.mode != 'OBJECT' or not wire.select_get() or not wire.is_editable:
        return None
    return single_cable_attachments(ctx, wire)


class BBE_OT_copy_bound_cable(bpy.types.Operator):
    bl_idname = 'bbe.copy_bound_cable'
    bl_label = 'Copy Cable'
    bl_description = 'Copy the cable and remember the sockets it is attached to'

    @classmethod
    def poll(cls, ctx):
        return ctx.area and ctx.area.type == 'VIEW_3D' and bool(local_copy_source(ctx))

    def execute(self, ctx):
        wire = ctx.active_object
        owners = local_copy_source(ctx)
        if not owners:
            return {'CANCELLED'}
        # Native copy includes dependency objects even if only the cable was
        # selected. Remember their exact identities, separately from the rig.
        ids = {}
        for owner in owners:
            while owner and owner.name not in ids:
                ids[owner.name] = owner.session_uid
                owner = owner.parent
        old = wire.get(COPY_ORIGIN)
        wire[COPY_ORIGIN] = json.dumps([SESSION, ctx.scene.session_uid, ids])
        try:
            return bpy.ops.view3d.copybuffer()
        finally:
            if old is None:
                del wire[COPY_ORIGIN]
            else:
                wire[COPY_ORIGIN] = old


def discard_unused():
    for name, uid in _unused:
        obj = bpy.data.objects.get(name)
        if obj is not None and obj.session_uid == uid and not obj.users:
            bpy.data.objects.remove(obj)
    _unused.clear()


def reuse_dependency(copy, original):
    for collection in tuple(copy.users_collection):
        collection.objects.unlink(copy)
    copy.user_remap(original)
    # The callback's import items still reference the pasted IDs until it returns.
    _unused.add((copy.name, copy.session_uid))
    if not bpy.app.timers.is_registered(discard_unused):
        bpy.app.timers.register(discard_unused, first_interval=0.0)


def restore_single_selection(imported):
    ctx = bpy.context
    for wire in imported:
        if not owns_cable(wire) or COPY_ORIGIN not in wire:
            continue
        marker = wire.pop(COPY_ORIGIN)
        try:
            session, scene_id, owners = json.loads(marker)
            if not isinstance(owners, dict):
                continue
        except (ValueError, TypeError):
            continue
        if session == SESSION and scene_id == ctx.scene.session_uid:
            for copy, name in imported.items():
                uid = owners.get(name)
                original = ctx.scene.objects.get(name)
                if uid is None:
                    continue
                if not original or original.session_uid != uid:
                    original = next((obj for obj in ctx.scene.objects if obj.session_uid == uid), None)
                if original and original != copy:
                    reuse_dependency(copy, original)
        if ctx.view_layer.objects.active == wire and wire.select_get():
            for obj in imported:
                if obj != wire and obj.name in ctx.view_layer.objects and obj.select_get():
                    obj.select_set(False)


def start_copy():
    bpy.utils.register_class(BBE_OT_copy_bound_cable)
    config = bpy.context.window_manager.keyconfigs.addon
    if config:
        km = config.keymaps.new(name='3D View', space_type='VIEW_3D')
        _keymaps.append((km,km.keymap_items.new('bbe.copy_bound_cable','C','PRESS',ctrl=True,head=True)))


def stop_copy():
    for km,item in _keymaps:
        km.keymap_items.remove(item)
    _keymaps.clear()
    bpy.utils.unregister_class(BBE_OT_copy_bound_cable)
    if bpy.app.timers.is_registered(discard_unused):
        bpy.app.timers.unregister(discard_unused)
    discard_unused()


def register():
    start_copy()
    bpy.app.handlers.blend_import_post.append(after_paste)
    bpy.app.handlers.load_post.append(repair_saved)
    bpy.app.timers.register(repair_saved, first_interval=0.0)


def unregister():
    stop_copy()
    if bpy.app.timers.is_registered(repair_saved):
        bpy.app.timers.unregister(repair_saved)
    bpy.app.handlers.load_post.remove(repair_saved)
    bpy.app.handlers.blend_import_post.remove(after_paste)
