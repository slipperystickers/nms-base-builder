"""Native JSON reimport restores the same displayed part and exact export."""
import sys
from pathlib import Path
import bpy
from mathutils import Matrix
sys.path.insert(0,str(Path(__file__).parent))
from test_support import addon,module,report
v2=module('builder_v2')
pivot=module('utils.mirror_pivot')
Part=module('part').Part

def bounds(obj):
    points=[obj.matrix_world @ v.co for v in obj.data.vertices]
    return [(min(v[i] for v in points),max(v[i] for v in points)) for i in range(3)]

def compare(a,b,tol):
    return max(abs(a[i][j]-b[i][j]) for i in range(3) for j in (0,1))<tol

def records_close(a,b):
    assert a['ObjectID']==b['ObjectID'] and a['Timestamp']==b['Timestamp']
    for key in ('Position','Up','At'):
        assert max(abs(x-y) for x,y in zip(a[key],b[key]))<1e-5,(key,a[key],b[key])

checks=[]
for high in (False,True):
    bpy.context.scene.nms_main.new_file()
    bpy.context.scene.bbe_detailed_proxies=high
    part=v2.add_part('B_STR_J_Y_NE',high_res=high)
    obj=part.object
    obj.matrix_world=Matrix.Translation((4.5154,25.7044,11.9521)) @ Matrix.Scale(.655,4)
    bpy.context.view_layer.update()
    assert pivot.is_normalized(obj)
    record=Part.deserialise_from_object(obj,v2.BUILDER).serialise()
    before=bounds(obj)
    display_before=obj.matrix_world.translation.copy()
    bpy.context.scene.nms_main.new_file()
    bpy.context.scene.bbe_detailed_proxies=high
    restored=Part.deserialise_from_data(record,v2.BUILDER,high_res=high)
    records_close(restored.serialise(),record)
    assert compare(bounds(restored.object),before,.03)
    assert (restored.object.matrix_world.translation-display_before).length<1e-4
    bpy.context.scene.nms_main.new_file()
    bpy.context.scene.bbe_detailed_proxies=high
    v2.deserialise_from_data({'Objects':[record]})
    imported=[x for x in bpy.context.scene.objects if x.get('ObjectID')=='B_STR_J_Y_NE']
    assert len(imported)==1,(high,len(imported))
    assert pivot.is_normalized(imported[0])
    records_close(Part.deserialise_from_object(imported[0],v2.BUILDER).serialise(),record)
    assert compare(bounds(imported[0]),before,.03)
    checks.append((high,list(display_before)))
report('mirror_pivot_reimport_pass',{'checks':checks})
