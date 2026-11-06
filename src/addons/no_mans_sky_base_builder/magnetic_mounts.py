"""Authored magnetic mounting variants; object/save transforms stay untouched."""
import math
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


def mounting_frame(obj,hab,slots):
    native=snapping._native_target(hab)
    if obj.get('ObjectID')=='B_MAG_1X1':
        slot=sorted(slots)[0][4:-1]
        point=next(p for p in snapping.DATA[hab['ObjectID']] if p['name']=='SnapPoint_Int'+slot)
        # The native NS/EW assemblies include the frame and the referenced magnet
        # at their authored heights (1.470776 / 1.418625), unlike the loose magnet.
        desired=native@Matrix(point['matrix'])@Matrix.Translation((0,-1.5,0))
        return ('NS' if slot[0] in 'NS' else 'EW'),obj.matrix_world.inverted_safe()@desired
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
    if not obj.data.get(MOUNT):obj[SOURCE]=obj.data
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
        mesh.transform(frame);mesh.update()
        for key,value in source.items():mesh[key]=value
        mesh[REVISION_KEY]=REVISION
        mesh[MOUNT]=token;mesh[SOURCE]=source
    if obj.data!=mesh:
        undo_guard.track_generated_preview();obj.data=mesh
    if hasattr(obj,'bbe_show_magnetic_beam'):part_controls.update_beam(obj)
