"""Game-space poses, display offsets, grouped mirrors and .blend persistence."""
import json
import sys
from pathlib import Path

import bpy
from mathutils import Euler, Matrix, Vector

sys.path.insert(0,str(Path(__file__).parent))
from test_support import addon,module,report,QA
v2=module('builder_v2')
pivot=module('utils.mirror_pivot')
Part=module('part').Part
Group=module('group').Group
translation=module('save_editor.save_translation')
TOL=.0001


def record(obj):
    return Part.deserialise_from_object(obj,v2.BUILDER).serialise()


def compare(a,b):
    assert a['ObjectID']==b['ObjectID']
    for key in ('Position','Up','At'):
        av,bv=Vector(a[key]),Vector(b[key])
        if key=='At':av.normalize();bv.normalize()
        assert (av-bv).length<TOL,(key,a,b)


def vertices(obj):
    return [obj.matrix_world@v.co for v in obj.data.vertices]


catalogue = sorted(set(addon.BUILDER.part_reference) | {
    str(pid).lstrip('^') for pid in module('utils.dictionary').get_parts_definition() if str(pid).lstrip('^')})
# Transform-only coverage for every catalogue ID, independent of proxy quality.
# Actual low/HD mesh loading is exercised below for every nonzero display pivot.
matrix_probe=bpy.data.objects.new('Catalogue pose probe',None)
matrix_probe['Timestamp']=0;matrix_probe['UserData']=0
bpy.context.scene.collection.objects.link(matrix_probe)
catalogue_matrix=Matrix.Translation((17.125,-12.75,4.125))@Euler((.2,.3,.4)).to_matrix().to_4x4()@Matrix.Scale(.75,4)
for pid in catalogue:
    expected=dict(ObjectID='^'+pid,Position=list(catalogue_matrix.translation),Up=list(catalogue_matrix.col[1].xyz),At=list(catalogue_matrix.col[2].xyz.normalized()))
    matrix_probe['ObjectID']=pid
    for normalized in (False,True):
        native=v2.deserialise_matrix_world(expected)
        if normalized:
            matrix_probe[pivot.OBJECT_TAG]=pid
            matrix_probe.matrix_world=pivot.display_matrix(native,pid)
        else:
            if pivot.OBJECT_TAG in matrix_probe:del matrix_probe[pivot.OBJECT_TAG]
            matrix_probe.matrix_world=native
        bpy.context.view_layer.update()
        compare(expected,record(matrix_probe))
bpy.data.objects.remove(matrix_probe,do_unlink=True)
if '--pose-only' in sys.argv:
    report('catalogue_pose_roundtrip_pass',{'catalogue_transform_count':len(catalogue),'position_tolerance':TOL})
    raise SystemExit(0)
ids = sorted(pivot._PIVOTS)
ids = list(dict.fromkeys(ids+['B_STR_R_N','B_STR_S_N','B_STR_J_Y_NE','B_WNG_B','B_WNG_B_R','B_HAB_A','W_FLOOR','CURVEPIPESHAPE','PIPE']+
    [pid for pid in catalogue if 'WALL' in pid and 'DIAG' in pid]))
rows=[]
for i,pid in enumerate(ids):
    frame=Matrix.Translation((17.125+(i%10)*9,-12.75+(i%20)*.25,4.125))@Euler((.2,.3,.4)).to_matrix().to_4x4()@Matrix.Scale(.75,4)
    rows.append(dict(ObjectID='^'+pid,Position=list(frame.translation),Up=list(frame.col[1].xyz),At=list(frame.col[2].xyz.normalized()),UserData=0))
# Base origin is global game metadata; object positions remain base-local.
payload=dict(Name='Pose regression',Position=[87654.125,-54321.5,12345.25],
    BaseType={'PersistentBaseTypes':'HomePlanetBase'},Objects=rows,GalacticAddress=123456,UserData=0)
mapped=translation.translate_to_eng_data(translation.translate_to_obf_data(payload))
assert mapped==payload
save_utils=module('save_editor.save_editor_utils')
SaveFile=module('save_editor.save_file').SaveFile
raw_base=translation.translate_to_obf_data(payload)
source=QA/'transform_source.hg'
fixture=SaveFile(source)
fixture.json_data=translation.translate_to_obf_data({'ActiveContext':'Main','BaseContext':{'PlayerStateData':{'PersistentPlayerBases':[payload]}}})
fixture.save()
original_bytes=source.read_bytes()
identity=save_utils.BaseData(0,raw_base)
checks=[]
for high in (False,True):
    bpy.context.scene.bbe_detailed_proxies=high
    result=bpy.context.scene.nms_save_data.import_base(bpy.context,identity,[str(source)])
    assert 'Imported' in result,result
    bpy.context.view_layer.update()
    objects={o.get('ObjectID'):o for o in bpy.context.scene.objects if o.get('ObjectID')}
    assert set(ids)<=objects.keys(),set(ids)-objects.keys()
    for expected in rows:
        obj=objects[expected['ObjectID'].lstrip('^')]
        compare(expected,record(obj))
    checks.append({'detailed':high,'game_pose_count':len(rows)})
assert source.read_bytes()==original_bytes

# Use representative normalized symmetric and asymmetric objects for a real
# grouped mirror, export, and .blend reopen. No user's save files are opened.
keep={'B_STR_W_NETB1','B_CON_7','B_WNG_B','B_HAB_A'}
selected=[o for pid,o in objects.items() if pid in keep]
assert len(selected)==len(keep)
for obj in list(bpy.context.scene.objects):
    if obj not in selected:bpy.data.objects.remove(obj,do_unlink=True)
group=Group.group_objects(selected)
for obj in bpy.context.selected_objects:obj.select_set(False)
group.select_set(True);bpy.context.view_layer.objects.active=group
assert bpy.ops.object.nms_universal_mirror_x()=={'FINISHED'}
bpy.context.view_layer.update()
group=bpy.context.view_layer.objects.active
expected=sorted(Group.serialise(group),key=lambda r:r['ObjectID'])
coords=vertices(group)
name=group.name
target=QA/'transform_reload.blend'
bpy.ops.wm.save_as_mainfile(filepath=str(target),check_existing=False)
bpy.ops.wm.open_mainfile(filepath=str(target))
bpy.context.view_layer.update()
group=bpy.data.objects[name]
assert len(coords)==len(group.data.vertices)
assert max((a-b).length for a,b in zip(coords,vertices(group)))<TOL
after=sorted(Group.serialise(group),key=lambda r:r['ObjectID'])
for a,b in zip(expected,after):compare(a,b)
# Reimport the grouped/mirrored native records through the same model loader
# used by Import from Save and compare each native position, up and aim.
bpy.context.scene.nms_main.deserialise_from_data({'Objects':after})
v2.deserialise_from_data({'Objects':after})
bpy.context.view_layer.update()
restored=sorted((record(o) for o in bpy.context.scene.objects if o.get('ObjectID')),key=lambda r:r['ObjectID'])
assert len(restored)==len(after)
for a,b in zip(after,restored):compare(a,b)
report('transform_reload_pass',{'catalogue_transform_count':len(catalogue),'display_pivot_count':len(pivot._PIVOTS),'game_import':checks,'grouped_mirror_blend_reopen':True,'position_tolerance':TOL})
