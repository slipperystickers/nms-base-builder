"""Authored magnetic mounting variants; object/save transforms stay untouched."""
import math
import re
from functools import lru_cache
from pathlib import Path
import bpy
from mathutils import Matrix
from . import corvette_snapping as snapping, undo_guard
from .utils import materials_v2

SOURCE='bbe_magnetic_free_mesh'
MOUNT='bbe_magnetic_mount'
REVISION=2
REVISION_KEY='bbe_magnetic_revision'


def variant_mesh(variant,detailed):
    quality='detailed' if detailed else 'simple'
    name='BBE Magnetic '+variant+' '+quality
    mesh=next((m for m in bpy.data.meshes
               if m.get('bbe_magnetic_variant')==variant
               and m.get('bbe_magnetic_quality')==quality
               and m.get(REVISION_KEY)==REVISION and not m.get(MOUNT)),None)
    if mesh is None:
        path=Path(__file__).parent/'resources/magnetic_mounts'/(variant+'_'+quality+'.blend')
        with bpy.data.libraries.load(str(path),link=False) as (a,b):b.meshes=[name]
        mesh=b.meshes[0]
    return mesh


@lru_cache(maxsize=16)
def single_mount_poses(hab_id):
    """The 1x1 placement entity switches meshes only for its IntWall outputs."""
    poses = []
    for _, channel, kind, role, source in snapping._sockets('B_MAG_1X1'):
        if role != 'Out' or not channel.startswith('0:'):
            continue
        socket = snapping.DATA['B_MAG_1X1'][0]['sockets'][int(channel.split(':')[1])]
        for key, _, target_kind, target_role, target in snapping._sockets(hab_id):
            if target_kind != kind or target_role != 'In':
                continue
            name = snapping.DATA[hab_id][int(key.split(':')[0])]['name']
            wall = re.fullmatch(r'SnapPoint_Int([NSEW]\d+)', name)
            deck = re.fullmatch(r'SnapPoint_([TB])([13])', name)
            if wall and kind.startswith(('IntNS','IntEW')):
                slot = 'WALL' + wall[1] + '_'
                variant = kind[3:5]
                locator = Matrix.Identity(4)
            elif deck and socket in ('RoomT_Out_', 'RoomB_Out_'):
                slot = ('CEILING' if deck[1] == 'T' else 'FLOOR') + ('0_' if deck[2] == '1' else '1_')
                variant = 'TB'
                # Native TOP_ and BOT_ locators within EXT_MAG_1X1.
                locator = Matrix.Translation((0, 1.5, 0))
                if socket == 'RoomB_Out_':
                    locator = locator @ Matrix.Diagonal((1, -1, -1, 1))
            else:
                continue
            poses.append((slot, variant, locator, (target @ source.inverted()).inverted()))
    return poses


def single_mount(obj, hab):
    host = snapping._native_target(hab)
    if abs(host.determinant()) < 1e-12:
        return None
    relative = host.inverted() @ snapping._native_target(obj)
    for slot, variant, locator, inverse_pose in single_mount_poses(hab['ObjectID']):
        delta = inverse_pose @ relative
        if (delta.translation.length < (.1 if variant == 'TB' else .05) and
                max(abs(delta[r][c] - (r == c)) for r in range(3) for c in range(3)) < .025):
            return slot, variant, locator
    return None


def mounting_frame(obj,hab,slots):
    native=snapping._native_target(hab)
    if obj.get('ObjectID')=='B_MAG_1X1':
        match = single_mount(obj, hab)
        if match is None:
            return None, None
        _, variant, locator = match
        return variant, obj.matrix_world.inverted_safe() @ snapping._native_target(obj) @ locator
    # The 1x2 part selects a locator when its Room output is connected. Its
    # existing proxy is the top assembly, whose long axis runs from -12 to 0.
    # Center that display about the pair of native sockets at Z=-3,+3.
    for _,_,kind,role,sm in snapping._sockets(obj['ObjectID']):
        if kind!='Room' or role!='Out':continue
        for _,_,tk,tr,tm in snapping._sockets(hab['ObjectID']):
            if tk!='Room' or tr!='In':continue
            candidate=native@tm@sm.inverted()
            delta=candidate.inverted_safe()@obj.matrix_world
            if delta.translation.length>.05 or max(abs(delta[r][c]-(r==c)) for r in range(3) for c in range(3))>.025:continue
            # Match the authored locator's mounting normal to the socket frame.
            normal=sm.to_3x3().col[0]
            if abs(normal.x)>.9:angle=-math.pi/2 if normal.x>0 else math.pi/2
            else:angle=0 if normal.y>0 else math.pi
            return 'DOUBLE',Matrix.Rotation(angle,4,'Z')@Matrix.Translation((0,0,6))
    return None,None


def refresh(obj,mount):
    from . import part_controls
    if not obj.data.get(MOUNT) and obj.get(SOURCE) != obj.data:
        obj[SOURCE] = obj.data
    source=obj.get(SOURCE,obj.data)
    if mount is None:
        if obj.data!=source:
            undo_guard.track_generated_preview();obj.data=source
            if hasattr(obj,'bbe_show_magnetic_beam'):part_controls.update_beam(obj)
        return
    hab,slots=mount
    variant,frame=mounting_frame(obj,hab,slots)
    if variant is None:return
    detailed=materials_v2.is_high_res(obj)
    token=str(REVISION)+':'+variant+':'+','.join(str(round(v,4)) for row in frame for v in row)
    mesh=next((m for m in bpy.data.meshes if m.get(MOUNT)==token and m.get(SOURCE)==source),None)
    if mesh is None:
        mesh=(source if variant=='DOUBLE' else variant_mesh(variant,detailed)).copy()
        mesh.name='BBE Mounted '+obj['ObjectID']+' '+variant
        if not detailed and not mesh.materials:
            for material in source.materials:
                mesh.materials.append(material)
        mesh.transform(frame);mesh.update()
        for key,value in source.items():mesh[key]=value
        mesh[REVISION_KEY]=REVISION
        mesh[MOUNT]=token;mesh[SOURCE]=source
    if obj.data!=mesh:
        undo_guard.track_generated_preview();obj.data=mesh
    if hasattr(obj,'bbe_show_magnetic_beam'):part_controls.update_beam(obj)
