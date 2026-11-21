"""Show open walls for native Corvette windows, doors and waste-disposal slots.

Only display meshes change. Placement, colour, ownership and export data stay
on the original objects; removing/moving an attachment restores the closed section.
"""
import json
import re
from time import perf_counter
from functools import lru_cache
from pathlib import Path
import bpy
import numpy as np
from mathutils import Vector, Matrix
from mathutils.kdtree import KDTree
from bpy.app.handlers import persistent
from .utils import materials_v2
from . import undo_guard, corvette_snapping

SOURCE = 'bbe_hab_closed_mesh'
OPEN = 'bbe_hab_open_slots'
DOORWAYS = 'bbe_hab_doorway_slots'
WINDOWS = {f'B_WALL_WIND{i}' for i in range(4)}
STAIRS = 'B_STAIRS0'
WASTE = 'B_WALL_TOIL0'
MAGNETS = {'B_MAG_1X1', 'B_MAG_1X2'}
TECH = {'B_WALL_TECH0', 'B_WALL_TECH1'}
UTILITY = TECH | WINDOWS | {'B_WALL_BUNK0','B_WALL_PLAN0','B_WALL_KITC0','B_WALL_MED0','B_WALL_CANT0'} | {f'B_WALL_CARG{i}' for i in range(10)}
ATTACHMENTS = UTILITY | {'B_DOOR0', WASTE} | MAGNETS | TECH
GHOST = 'bbe_waste_ghost_state'
REFERENCE = 'bbe_waste_reference_mesh'
GHOST_MESH = 'bbe_waste_ghost_mesh'
_table = None
_signatures = {}
_busy = False


def table():
    global _table
    if _table is None:
        _table = json.loads((Path(__file__).parent/'resources/hab_wall_slots.json').read_text())
    return _table


@lru_cache(maxsize=1)
def deck_slots():
    return json.loads((Path(__file__).parent/'resources/hab_deck_slots.json').read_text())


def source_mesh(obj):
    if not obj.data.get(OPEN) and obj.get(SOURCE) != obj.data:
        obj[SOURCE] = obj.data
    return obj.get(SOURCE, obj.data)


def ghost(obj, enabled):
    """Use real frame geometry so viewport clicks select the exported part."""
    if enabled and GHOST not in obj:
        undo_guard.track_generated_preview()
        obj[GHOST] = dict(display_type=obj.display_type,
                          display_bounds_type=obj.display_bounds_type,
                          show_in_front=obj.show_in_front, hide_render=obj.hide_render,
                          hide_select=obj.hide_select)
        obj.display_type = 'TEXTURED'
        obj.show_in_front = True
        obj.hide_render = True
        obj.hide_select = False
    if enabled and not obj.data.get(GHOST_MESH):
        source = obj.data
        obj[REFERENCE] = source
        mesh = next((m for m in bpy.data.meshes if m.get(GHOST_MESH) == source), None)
        if mesh is None:
            lo = Vector([min(v.co[i] for v in source.vertices) for i in range(3)])
            hi = Vector([max(v.co[i] for v in source.vertices) for i in range(3)])
            # Expand slightly beyond the original footprint to separate the
            # handles from coincident hab trim. Object/save matrices never move.
            lo -= Vector((.035, .035, .035));hi += Vector((.035, .035, .035))
            corners = [Vector((x,y,z)) for x in (lo.x,hi.x)
                       for y in (lo.y,hi.y) for z in (lo.z,hi.z)]
            verts, faces = [], []
            for i, start in enumerate(corners):
                for bit in (1,2,4):
                    j = i ^ bit
                    if j < i:
                        continue
                    end = corners[j]
                    axis = (end-start).normalized()
                    ref = Vector((0,1,0)) if abs(axis.y)<.9 else Vector((0,0,1))
                    u = axis.cross(ref).normalized()*.018
                    v = axis.cross(u).normalized()*.018
                    offset = len(verts)
                    verts.extend(p+du*u+dv*v for p in (start,end)
                                 for du,dv in ((-1,-1),(1,-1),(1,1),(-1,1)))
                    faces.extend(tuple(offset+k for k in f) for f in
                                 ((0,3,2,1),(4,5,6,7),(0,1,5,4),
                                  (1,2,6,5),(2,3,7,6),(3,0,4,7)))
            mesh = bpy.data.meshes.new('BBE Waste / selectable ghost frame')
            mesh.from_pydata(verts, [], faces);mesh.update()
            mat = bpy.data.materials.get('BBE Waste / reference frame')
            if mat is None:
                mat = bpy.data.materials.new('BBE Waste / reference frame')
                mat.diffuse_color = (.16,.65,.72,1)
                mat.use_nodes = True
                bsdf = mat.node_tree.nodes.get('Principled BSDF')
                bsdf.inputs['Base Color'].default_value = mat.diffuse_color
                bsdf.inputs['Roughness'].default_value = .65
            mesh.materials.append(mat)
            for name,value in source.items():mesh[name] = value
            mesh[GHOST_MESH] = source
        undo_guard.track_generated_preview()
        obj.data = mesh
    elif not enabled and GHOST in obj:
        if obj.data.get(GHOST_MESH) and obj.get(REFERENCE):
            obj.data = obj[REFERENCE]
        for name, value in obj[GHOST].items():
            setattr(obj, name, value)
        del obj[GHOST]
        if REFERENCE in obj:del obj[REFERENCE]


WASTE_STYLE = 'bbe_waste_wall_style'
WASTE_REVISION = 'bbe_waste_wall_revision'
WASTE_SOURCE = 'bbe_waste_wall_source'


def display_waste(obj, style):
    # The free-standing model is also the native A wall. B and C supply
    # different assemblies. The D-style table has no east/west toilet model.
    if GHOST in obj and style == 'D' and obj.data.get(GHOST_MESH):
        return
    ghost(obj, False)
    source = obj.data.get(WASTE_SOURCE) or obj.data
    if style in ('A', 'B', 'C'):
        if obj.data.get(WASTE_STYLE) == style and obj.data.get(WASTE_REVISION) == 1:
            return
        mesh = next((m for m in bpy.data.meshes if m.get(WASTE_STYLE) == style
                     and m.get(WASTE_SOURCE) == source and m.get(WASTE_REVISION) == 1), None)
        if mesh is None:
            from . import builder_v2
            detailed = builder_v2.MESH_TAG in source
            quality = 'detailed' if detailed else 'simple'
            from . import hd_library
            root = hd_library.additions_root(allow_previous=False) if detailed else Path(__file__).parent / 'resources'
            if root is None:
                return
            path = root / 'waste_walls' / (quality + '.blend')
            with bpy.data.libraries.load(str(path), link=False) as (_, dst):
                dst.meshes = [f'BBE Waste Wall {style} {quality}']
            mesh = dst.meshes[0]
            if detailed:
                builder_v2._relink_mesh_textures(mesh)
                materials_v2.note_appended_data()
                materials_v2.dedupe_appended_data()
            else:
                for mat in source.materials:
                    mesh.materials.append(mat)
            for key, value in source.items():
                mesh[key] = value
            mesh[WASTE_SOURCE] = source
            mesh[WASTE_STYLE] = style
            mesh[WASTE_REVISION] = 1
        undo_guard.track_generated_preview()
        obj.data = mesh
    elif obj.data != source:
        obj.data = source
    if style == 'D':
        ghost(obj, True)


TECH_SOURCE = 'bbe_tech_wall_source'
TECH_VARIANT = 'bbe_tech_wall_variant'


@lru_cache(maxsize=1)
def utility_variants():
    return json.loads((Path(__file__).parent / 'resources/utility_walls/variants.json').read_text())


def display_tech(obj, hab=None, slot=None):
    """Swap only display geometry, aligned with the host's authored wall locator."""
    source = obj.data.get(TECH_SOURCE) or obj.data
    if hab is None:
        if obj.data != source:
            undo_guard.track_generated_preview()
            obj.data = source
        return False
    pid = obj.get('ObjectID')
    host_id = hab.get('ObjectID')
    axis = 'NS' if slot[4] in 'NS' else 'EW'
    style = host_id[-1]
    detailed = 'nms_high_res_id' in source
    quality = 'detailed' if detailed else 'simple'
    model = utility_variants().get(f'{pid}:{axis}:{style}')
    if not model:
        return False
    directory = Path(__file__).parent / 'resources/utility_walls'
    if detailed:
        from . import hd_library
        additions = hd_library.additions_root()
        path = additions / 'utility_walls' / f'{model}_detailed.blend' if additions else None
    else:
        path = directory / f'{model}_simple.blend'
    if not path or not path.is_file():
        # Older HD packs still contain the original refiner and radar assemblies.
        legacy = additions / 'tech_walls/detailed.blend' if detailed and additions and pid in TECH else None
        if legacy and legacy.is_file() and axis=='EW':
            path=legacy
        else:
            path=directory / f'{model}_simple.blend'
            quality='simple'
    mesh_name = f'BBE Tech Wall {pid[-1]} {axis} {style} detailed' if path.parent.name=='tech_walls' else 'BBE '+model
    # The wall mesh is authored in host-local coordinates. Convert the wall
    # locator into the attachment's existing local space; never move its origin.
    local = (obj.matrix_world.inverted_safe() @ corvette_snapping._native_target(hab)
             @ Matrix(table()[host_id]['slots'][slot]['matrix']))
    key = f'{model} {quality} ' + ','.join(str(round(v,5)) for row in local for v in row)
    if obj.data.get(TECH_VARIANT) == key:
        return True
    mesh = next((m for m in bpy.data.meshes if m.get(TECH_VARIANT) == key
                 and m.get(TECH_SOURCE) == source), None)
    if mesh is None:
        with bpy.data.libraries.load(str(path), link=False) as (src, dst):
            # Per-assembly libraries contain one mesh. Blender may suffix its
            # name if the generator has already built the other proxy quality.
            dst.meshes = [mesh_name] if mesh_name in src.meshes else src.meshes[:1] if path.parent.name=='utility_walls' else []
        if not dst.meshes:
            return False
        mesh = dst.meshes[0]
        if mesh is None:
            return False
        mesh.transform(local)
        if quality=='simple':
            for mat in source.materials:
                mesh.materials.append(mat)
        if detailed:
            from . import builder_v2
            builder_v2._relink_mesh_textures(mesh)
            materials_v2.note_appended_data()
            materials_v2.dedupe_appended_data()
        for key_name, value in source.items():
            mesh[key_name] = value
        mesh[TECH_SOURCE] = source
        mesh[TECH_VARIANT] = key
        mesh.update()
    undo_guard.track_generated_preview()
    obj.data = mesh
    return True


def matching_slots(attachment, hab):
    """Native socket compatibility plus pose, including scaled/rotated ships."""
    if attachment.get('ObjectID') == 'B_MAG_1X1':
        from .magnetic_mounts import single_mount
        match = single_mount(attachment, hab)
        return {match[0]} if match else set()
    slots = set()
    points = corvette_snapping.DATA.get(hab.get('ObjectID'), ())
    for key, _, _, candidate in corvette_snapping.options(attachment, hab):
        name = points[int(key.split(':')[0])]['name']
        if attachment.get('ObjectID') in (UTILITY - WINDOWS) | {WASTE} and not name.startswith('SnapPoint_Int'):
            # An opposite-side socket keeps the host wall in place.
            continue
        match = re.fullmatch(r'SnapPoint_(?:SPIGN_)?(?:IntOpp|Int)?([NSEW]\d+)', name)
        if not match:
            continue
        slot = 'WALL' + match.group(1) + '_'
        if slot not in table()[hab['ObjectID']]['slots']:
            continue
        if abs(candidate.determinant()) < 1e-12:
            continue
        delta = candidate.inverted() @ attachment.matrix_world
        if (delta.translation.length < .05 and
                max(abs(delta[r][c] - (1 if r == c else 0))
                    for r in range(3) for c in range(3)) < .025):
            slots.add(slot)
    return slots


@lru_cache(maxsize=32)
def stair_poses(pid):
    """Legal stair placements and the authored deck panel each one replaces."""
    result = []
    for key, _, _, pose in corvette_snapping._local_options(STAIRS, pid):
        name = corvette_snapping.DATA[pid][int(key.split(':')[0])]['name']
        site = re.fullmatch(r'SnapPoint_(Int)?Stairs(\d+)', name)
        if site:
            slot = ('FLOOR' if site[1] else 'CEILING') + site[2] + '_'
            if slot in deck_slots()[pid]['detailed']:
                result.append((slot, pose))
    return result


def frames_match(inverse, other):
    delta = inverse @ other
    return (delta.translation.length < .05 and
            max(abs(delta[r][c] - (r == c)) for r in range(3) for c in range(3)) < .025)


def mounted_stairs(parts, habs):
    frames = [corvette_snapping._native_target(obj) for obj in parts if obj.get('ObjectID') == STAIRS]
    mounted = set()
    if not frames:
        return mounted
    tree = KDTree(len(frames))
    for index, frame in enumerate(frames):
        tree.insert(frame.translation, index)
    tree.balance()
    for hab in habs:
        native = corvette_snapping._native_target(hab)
        if abs(native.determinant()) < 1e-12:
            continue
        for slot, local in stair_poses(hab['ObjectID']):
            pose = native @ local
            for _, index, _ in tree.find_range(pose.translation, .05 * max(map(abs, pose.to_scale()))):
                if frames_match(pose.inverted(), frames[index]):
                    mounted.add((hab, slot))
                    break
    return mounted


@lru_cache(maxsize=128)
def deck_panel(locator):
    site = re.fullmatch(r'SnapPoint_([TB])([13])', locator)
    if site:
        return ('CEILING' if site[1] == 'T' else 'FLOOR') + ('0_' if site[2] == '1' else '1_')
    return None


def room_connections(parts, habs):
    """Match Room outputs to inputs, not merely nearby geometry or Block snaps.

    Native hab rules replace closed walls when their Room output is connected.
    Index socket positions so moving a part does not compare every room pair.
    """
    inputs=[];outputs=[]
    mounted = mounted_stairs(parts, habs)
    hab_set=set(habs)
    for obj in parts:
        pid=obj.get('ObjectID','')
        if pid not in table() and not pid.startswith('B_COK_'):
            continue
        native=corvette_snapping._native_target(obj)
        for key, _, kind, role, local in corvette_snapping._sockets(pid):
            if kind!='Room':continue
            world=native@local
            name=corvette_snapping.DATA[pid][int(key.split(':')[0])]['name']
            deck = deck_panel(name) if mounted and obj in hab_set else None
            if role=='In':inputs.append((obj,world,deck))
            elif deck and (obj, deck) in mounted:
                outputs.append((obj,deck,world))
            elif obj in hab_set:
                match=re.fullmatch(r'SnapPoint_([NSEW]\d+)',name)
                if match and 'WALL'+match.group(1)+'_' in table()[pid]['slots']:
                    outputs.append((obj,'WALL'+match.group(1)+'_',world))
    occupied={obj:set() for obj in habs}
    for hab, slot in mounted:
        occupied[hab].add(slot)
    if not inputs:return occupied
    tree=KDTree(len(inputs))
    for i,(_,frame,_) in enumerate(inputs):tree.insert(frame.translation,i)
    tree.balance()
    for obj,slot,frame in outputs:
        if abs(frame.determinant())<1e-12:continue
        inverse=frame.inverted()
        radius=max(map(abs, frame.to_scale()))*.05
        for _,index,_ in tree.find_range(frame.translation,radius):
            other,other_frame,other_deck=inputs[index]
            if other==obj or not frames_match(inverse, other_frame):
                continue
            if slot.startswith('WALL'):
                occupied[obj].add(slot)
            elif other_deck:
                # A stair landing also clears the mating panel on the next deck.
                occupied[other].add(other_deck)
            else:
                continue
            break
    return occupied


def open_mesh(source, pid, slots, detailed=True, doorways=()):
    token = ','.join(sorted(slots))
    doorway_token=','.join(sorted(doorways))
    for mesh in bpy.data.meshes:
        if (mesh.get(OPEN) == token and mesh.get(SOURCE) == source
                and mesh.get(DOORWAYS,'')==doorway_token):
            return mesh
    spec = table()[pid]
    original = source
    if not detailed:
        spec = spec.get('simple')
        if not spec:
            return source
        # Small geometry-only opening previews. No HD textures or models are
        # required, and the original closed proxy is restored on disconnect.
        name = 'BBE Hab simple source / ' + pid
        source = bpy.data.meshes.get(name)
        if source is None:
            path = Path(__file__).parent / 'resources' / spec['file']
            with bpy.data.libraries.load(str(path), link=False) as (src, dst):
                dst.meshes = [src.meshes[0]]
            source = dst.meshes[0]
            source.name = name
    # Do not apply face masks to an unrelated/custom or older asset revision.
    if len(source.vertices) != spec['vertices'] or len(source.polygons) != spec['polygons']:
        return original
    keep = np.ones(len(source.polygons), dtype=bool)
    for slot in slots:
        if slot in spec['slots']:
            ranges = spec['slots'][slot]['faces']
        else:
            ranges = deck_slots()[pid]['detailed' if detailed else 'simple'][slot]
        for first, last in ranges:
            keep[first:last+1] = False
    from . import hab_doorways
    mesh = hab_doorways.build_preview(source, original, pid, keep, doorways, detailed,
                                      'BBE Hab / '+pid+' / '+token)
    mesh[OPEN] = token
    mesh[SOURCE] = original
    mesh[DOORWAYS]=doorway_token
    return mesh


_activities = {}


def finish_activity(key):
    activity = _activities.pop(key, None)
    if activity:
        activity.__exit__(None, None, None)


def refresh(scene=None, force=False, *, interactive=False):
    global _busy
    if _busy or not undo_guard.history_ready():
        return
    scene = scene or bpy.context.scene
    supported = table().keys() | ATTACHMENTS | {STAIRS}
    parts = [o for o in scene.objects if o.type == 'MESH' and
             (o.get('ObjectID') in supported or
              str(o.get('ObjectID','')).startswith('B_COK_'))]
    signature = (getattr(scene, 'bbe_detailed_proxies', True), tuple(
        (o.as_pointer(), o.data.as_pointer(), o.get('ObjectID'), tuple(round(v,5) for row in o.matrix_world for v in row))
        for o in parts))
    key = scene.as_pointer()
    if not force and _signatures.get(key) == signature:
        finish_activity(key)
        return
    _busy = True
    try:
        habs = [o for o in parts if o.get('ObjectID') in table()]
        attachments = [o for o in parts if o.get('ObjectID') in ATTACHMENTS]
        occupied = {o: set() for o in habs}
        connections=room_connections(parts,habs)
        matches = []
        for attachment in attachments:
            for hab in habs:
                slots = matching_slots(attachment, hab)
                if slots:
                    if attachment.get('ObjectID') in UTILITY and not display_tech(attachment, hab, sorted(slots)[0]):
                        continue
                    occupied[hab].update(slots)
                    matches.append((attachment, hab, slots))
        deadline = perf_counter() + .012
        deferred = 0
        built = False
        for hab in habs:
            # An explicit wall attachment supplies its own frame/panel.
            doorways={slot for slot in connections[hab]-occupied[hab] if slot.startswith('WALL')}
            occupied[hab].update(connections[hab])
            source = source_mesh(hab)
            slots = occupied[hab]
            if slots and hab.data.get(SOURCE) == source and (
                    hab.data.get(OPEN) == ','.join(sorted(slots)) and
                    hab.data.get(DOORWAYS, '') == ','.join(sorted(doorways))):
                continue
            if interactive and built and slots and perf_counter() > deadline:
                deferred += 1
                continue
            wanted = open_mesh(source, hab['ObjectID'], slots,
                               materials_v2.is_high_res(hab), doorways) if slots else source
            if hab.data != wanted:
                built = True
                undo_guard.track_generated_preview()
                hab.data = wanted
        if deferred:
            if key not in _activities:
                from .progress_ui import Activity
                _activities[key] = Activity('Updating hab doorways', deferred_redraw=True).__enter__()
            _activities[key].batch(len(habs)-deferred, len(habs), label='Habs')
            return True
        finish_activity(key)
        for attachment in attachments:
            if attachment.get('ObjectID') in UTILITY and not any(a == attachment for a, _, _ in matches):
                display_tech(attachment)
            if attachment.get('ObjectID') in MAGNETS:
                from . import magnetic_mounts
                mount = next(((hab, slots) for a, hab, slots in matches if a == attachment), None)
                magnetic_mounts.refresh(attachment, mount)
            if attachment.get('ObjectID') == WASTE:
                style = next((room['ObjectID'][-1] for a, room, slots in matches
                              if a == attachment and slots <= set(room.data.get(OPEN, '').split(','))), None)
                if style is None:
                    from . import habitat_preview
                    if any(o.get('ObjectID') == 'B_COK_E' and
                           habitat_preview.opening_mask(o, [attachment]) for o in parts):
                        style = 'D'
                display_waste(attachment, style or 'A')
        _signatures[key] = signature
        # Keep unused display meshes: older undo steps can still own them.
    finally:
        _busy = False


def tick():
    try:
        if not bpy.app.is_job_running('RENDER'):
            pending = False
            if _activities:
                for key in _activities.keys() - {scene.as_pointer() for scene in bpy.data.scenes}:
                    finish_activity(key)
            for scene in bpy.data.scenes:
                pending = refresh(scene, interactive=True) or pending
            if pending:
                return .016
    except Exception as exc:
        for key in tuple(_activities):
            finish_activity(key)
        print('BBE hab windows:', exc)
    return .25


@persistent
def loaded(_):
    for key in tuple(_activities):
        finish_activity(key)
    _signatures.clear()
    # The timer refreshes after the load/undo settle period.


@persistent
def before_render(scene, *_):
    refresh(scene)


def register():
    if not bpy.app.timers.is_registered(tick):
        bpy.app.timers.register(tick, first_interval=.5, persistent=True)
    for handlers, callback in ((bpy.app.handlers.load_post, loaded),
                               (bpy.app.handlers.undo_post, loaded),
                               (bpy.app.handlers.redo_post, loaded),
                               (bpy.app.handlers.render_pre, before_render)):
        if callback not in handlers:
            handlers.append(callback)


def unregister():
    loaded(None)
    if bpy.app.timers.is_registered(tick):
        bpy.app.timers.unregister(tick)
    for handlers, callback in ((bpy.app.handlers.load_post, loaded),
                               (bpy.app.handlers.undo_post, loaded),
                               (bpy.app.handlers.redo_post, loaded),
                               (bpy.app.handlers.render_pre, before_render)):
        if callback in handlers:
            handlers.remove(callback)
    for obj in bpy.data.objects:
        if obj.type == 'MESH' and obj.get('ObjectID') in UTILITY:
            display_tech(obj)
        if obj.type == 'MESH' and obj.get('ObjectID') in MAGNETS:
            from . import magnetic_mounts
            magnetic_mounts.refresh(obj, None)
        if obj.type == 'MESH' and obj.get('ObjectID') == WASTE:
            display_waste(obj, None)
        if obj.type == 'MESH' and obj.data.get(OPEN) and obj.get(SOURCE):
            obj.data = obj[SOURCE]
    _signatures.clear()
