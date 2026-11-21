"""Select a shared deck landing and place one native Corvette staircase."""
from functools import lru_cache
from typing import NamedTuple

import bpy
from bpy.app.handlers import persistent

from . import corvette_snapping as snapping, hab_windows
from .utils import materials_v2, mirror_pivot


class Landing(NamedTuple):
    lower: object
    ceiling: str
    upper: object
    floor: str
    point: object
    pose: object


@lru_cache(maxsize=32)
def deck_sites(pid):
    poses = {}
    for slot, pose in hab_windows.stair_poses(pid):
        poses.setdefault(slot, pose)  # Use the first authored stair facing.
    sites = []
    for key, _, kind, role, frame in snapping._sockets(pid):
        if kind != 'Room':
            continue
        name = snapping.DATA[pid][int(key.split(':')[0])]['name']
        slot = hab_windows.deck_panel(name)
        if slot in poses:
            expected_role = 'Out' if slot.startswith('CEILING') else 'In'
            if role == expected_role:
                sites.append((slot, frame, poses[slot]))
    return tuple(sites)


def shared_landings(context, *, verify=False):
    active = context.active_object
    if active is None or active.get('ObjectID') not in hab_windows.table():
        return []
    selected = context.selected_objects
    if len(selected) != 2 or any(obj.get('ObjectID') not in hab_windows.table() for obj in selected):
        return []
    # During drawing, use the existing display state. On a click, check the actual
    # stairs too: two clicks may arrive before the asynchronous doorway refresh.
    mounted = hab_windows.mounted_stairs(context.scene.objects, selected) if verify else set()
    ceilings, floors = [], []
    for obj in selected:
        native = snapping._native_target(obj)
        if abs(native.determinant()) < 1e-12:
            return []
        occupied = obj.data.get(hab_windows.OPEN, '').split(',')
        for slot, frame, pose in deck_sites(obj['ObjectID']):
            if slot in occupied or (obj, slot) in mounted:
                continue
            if slot.startswith('CEILING'):
                ceilings.append((obj, slot, native @ frame, native @ pose))
            else:
                floors.append((obj, slot, native @ frame))
    return [Landing(lower, ceiling, upper, floor, face.translation, pose)
            for lower, ceiling, face, pose in ceilings for upper, floor, mate in floors
            if lower != upper and hab_windows.frames_match(face.inverted(), mate)]


def place(context, landing):
    from . import builder_v2

    lower, upper = landing.lower, landing.upper
    active = context.active_object
    obj = None
    try:
        obj = builder_v2.add_part(hab_windows.STAIRS, build_rigs=False,
                                  high_res=materials_v2.is_high_res(lower)).object
        for collection in lower.users_collection:
            if collection not in obj.users_collection:
                collection.objects.link(obj)
        for collection in tuple(obj.users_collection):
            if collection not in lower.users_collection:
                collection.objects.unlink(obj)
        obj.parent = lower.parent
        obj.matrix_world = (mirror_pivot.display_matrix(landing.pose, hab_windows.STAIRS)
                            if mirror_pivot.is_normalized(obj) else landing.pose)
        obj['snapped_to'] = lower.name
        obj.select_set(False)
        context.view_layer.update()
    except Exception:
        if obj is not None:
            bpy.data.objects.remove(obj, do_unlink=True)
        raise
    finally:
        lower.select_set(True)
        upper.select_set(True)
        context.view_layer.objects.active = active
    return obj


_pickers = {}


def key(context):
    return context.window.as_pointer(), context.area.as_pointer()


def pair_key(context):
    return tuple(sorted(obj.session_uid for obj in context.selected_objects))


def picking(context):
    area = key(context)
    if area in _pickers and _pickers[area] != pair_key(context):
        _pickers.pop(area)
    return area in _pickers


@persistent
def clear(*_):
    _pickers.clear()


class BBE_OT_add_hab_stairs(bpy.types.Operator):
    bl_idname = 'bbe.add_hab_stairs'
    bl_label = 'Add Stairs'
    bl_description = 'Place stairs at a shared landing between the two selected Corvette habs'
    bl_options = {'UNDO'}
    slot: bpy.props.StringProperty(options={'HIDDEN','SKIP_SAVE'})

    @classmethod
    def poll(cls, context):
        return (context.window is not None and context.area is not None and
                context.area.type == 'VIEW_3D' and context.mode == 'OBJECT' and
                len(context.selected_objects) == 2 and
                all(obj.get('ObjectID') in hab_windows.table() for obj in context.selected_objects))

    def execute(self, context):
        area = key(context)
        choosing = picking(context)
        if choosing and not self.slot:
            _pickers.pop(area)
            context.area.tag_redraw()
            return {'CANCELLED'}
        options = shared_landings(context, verify=True)
        if self.slot:
            options = [entry for entry in options if choosing and entry.ceiling == self.slot]
        if not options:
            _pickers.pop(area, None)
            self.report({'INFO'}, 'No free shared stair landing')
            context.area.tag_redraw()
            return {'CANCELLED'}
        if len(options) > 1:
            _pickers[area] = pair_key(context)
            self.report({'INFO'}, 'Click a green landing target between the habs')
            context.area.tag_redraw()
            # Only placing the part should create an undo step.
            return {'CANCELLED'}
        _pickers.pop(area, None)
        place(context, options[0])
        context.area.tag_redraw()
        return {'FINISHED'}

