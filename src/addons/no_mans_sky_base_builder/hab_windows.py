"""Show open walls for native Corvette windows, doors and waste-disposal slots.

Only display meshes change. Placement, colour, ownership and export data stay
on the original objects; removing/moving an attachment restores the closed section.
"""
import json
import re
from functools import lru_cache
from pathlib import Path
import bpy
import numpy as np
from mathutils import Vector
from mathutils.kdtree import KDTree
from bpy.app.handlers import persistent
from .utils import materials_v2
from . import undo_guard, corvette_snapping

SOURCE = 'bbe_hab_closed_mesh'
OPEN = 'bbe_hab_open_slots'
DOORWAYS = 'bbe_hab_doorway_slots'
WINDOWS = {'B_WALL_WIND0', 'B_WALL_WIND1', 'B_WALL_WIND2'}
WASTE = 'B_WALL_TOIL0'
MAGNETS = {'B_MAG_1X1', 'B_MAG_1X2'}
ATTACHMENTS = WINDOWS | {'B_DOOR0', WASTE} | MAGNETS
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
    if not obj.data.get(OPEN):
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
        if attachment.get('ObjectID') == WASTE and not name.startswith('SnapPoint_Int'):
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


def room_connections(parts, habs):
    """Match Room outputs to inputs, not merely nearby geometry or Block snaps.

    Native hab rules replace closed walls when their Room output is connected.
    Index socket positions so moving a part does not compare every room pair.
    """
    inputs=[];outputs=[]
    for obj in parts:
        pid=obj.get('ObjectID','')
        if pid not in table() and not pid.startswith('B_COK_'):
            continue
        native=corvette_snapping._native_target(obj)
        for key, _, kind, role, local in corvette_snapping._sockets(pid):
            if kind!='Room':continue
            world=native@local
            if role=='In':inputs.append((obj,world))
            elif obj in habs:
                name=corvette_snapping.DATA[pid][int(key.split(':')[0])]['name']
                match=re.fullmatch(r'SnapPoint_([NSEW]\d+)',name)
                if match and 'WALL'+match.group(1)+'_' in table()[pid]['slots']:
                    outputs.append((obj,'WALL'+match.group(1)+'_',world))
    occupied={obj:set() for obj in habs}
    if not inputs:return occupied
    tree=KDTree(len(inputs))
    for i,(_,frame) in enumerate(inputs):tree.insert(frame.translation,i)
    tree.balance()
    for obj,slot,frame in outputs:
        if abs(frame.determinant())<1e-12:continue
        inverse=frame.inverted()
        radius=max(frame.to_scale())*.05
        for _,index,_ in tree.find_range(frame.translation,radius):
            other,other_frame=inputs[index]
            if other==obj:continue
            delta=inverse@other_frame
            if (delta.translation.length<.05 and
                max(abs(delta[r][c]-(r==c)) for r in range(3) for c in range(3))<.025):
                occupied[obj].add(slot)
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
    faces = [p for p in source.polygons if keep[p.index]]
    loop_ids = np.array([i for p in faces for i in p.loop_indices], dtype=np.int32)
    mesh = bpy.data.meshes.new('BBE Hab / '+pid+' / '+token)
    mesh.from_pydata([v.co[:] for v in source.vertices], [], [p.vertices[:] for p in faces])
    for material in original.materials:
        mesh.materials.append(material)
    mesh.polygons.foreach_set('material_index', [p.material_index for p in faces])
    mesh.polygons.foreach_set('use_smooth', [p.use_smooth for p in faces])
    for uv in source.uv_layers:
        values = np.empty(len(source.loops)*2, dtype=np.float32)
        uv.data.foreach_get('uv', values)
        mesh.uv_layers.new(name=uv.name).data.foreach_set('uv', values.reshape(-1,2)[loop_ids].ravel())
    if len(source.corner_normals) == len(source.loops):
        normals = np.empty(len(source.loops)*3, dtype=np.float32)
        source.corner_normals.foreach_get('vector', normals)
        mesh.normals_split_custom_set(normals.reshape(-1,3)[loop_ids].tolist())
    for key, value in original.items():
        mesh[key] = value
    mesh[OPEN] = token
    mesh[SOURCE] = original
    mesh.update()
    if doorways:
        from . import hab_doorways
        combined=hab_doorways.add_frames(mesh,pid,doorways,detailed)
        bpy.data.meshes.remove(mesh)
        mesh=combined
    mesh[DOORWAYS]=doorway_token
    return mesh


def refresh(scene=None, force=False):
    global _busy
    if _busy or not undo_guard.history_ready():
        return
    scene = scene or bpy.context.scene
    parts = [o for o in scene.objects if o.type == 'MESH' and
             (o.get('ObjectID') in set(table())|ATTACHMENTS or
              str(o.get('ObjectID','')).startswith('B_COK_'))]
    signature = (getattr(scene, 'bbe_detailed_proxies', True), tuple(
        (o.as_pointer(), o.data.as_pointer(), o.get('ObjectID'), tuple(round(v,5) for row in o.matrix_world for v in row))
        for o in parts))
    key = scene.as_pointer()
    if not force and _signatures.get(key) == signature:
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
                    occupied[hab].update(slots)
                    matches.append((attachment, hab, slots))
        for hab in habs:
            # An explicit wall attachment supplies its own frame/panel.
            doorways=connections[hab]-occupied[hab]
            occupied[hab].update(connections[hab])
            source = source_mesh(hab)
            wanted = open_mesh(source, hab['ObjectID'], occupied[hab],
                               materials_v2.is_high_res(hab),doorways) if occupied[hab] else source
            if hab.data != wanted:
                undo_guard.track_generated_preview()
                hab.data = wanted
        for attachment in attachments:
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
            for scene in bpy.data.scenes:
                refresh(scene)
    except Exception as exc:
        print('BBE hab windows:', exc)
    return .25


@persistent
def loaded(_):
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
    if bpy.app.timers.is_registered(tick):
        bpy.app.timers.unregister(tick)
    for handlers, callback in ((bpy.app.handlers.load_post, loaded),
                               (bpy.app.handlers.undo_post, loaded),
                               (bpy.app.handlers.redo_post, loaded),
                               (bpy.app.handlers.render_pre, before_render)):
        if callback in handlers:
            handlers.remove(callback)
    for obj in bpy.data.objects:
        if obj.type == 'MESH' and obj.get('ObjectID') in MAGNETS:
            from . import magnetic_mounts
            magnetic_mounts.refresh(obj, None)
        if obj.type == 'MESH' and obj.get('ObjectID') == WASTE:
            display_waste(obj, None)
        if obj.type == 'MESH' and obj.data.get(OPEN) and obj.get(SOURCE):
            obj.data = obj[SOURCE]
    _signatures.clear()
