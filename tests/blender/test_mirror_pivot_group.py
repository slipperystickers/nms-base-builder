"""A group containing offset-pivot parts mirrors visually and exports natively."""
import sys
from pathlib import Path
import bpy
from mathutils import Matrix,Vector
from mathutils.kdtree import KDTree
sys.path.insert(0,str(Path(__file__).parent))
from test_support import addon,module,report
Group=module('group').Group
v2=module('builder_v2')

def points(objects):
    return [o.matrix_world @ v.co for o in objects for v in o.data.vertices]

def error(expected,actual):
    tree=KDTree(len(expected))
    for i,p in enumerate(expected):tree.insert(p,i)
    tree.balance()
    return max(tree.find(p)[2] for p in actual[::max(1,len(actual)//15000)])

checks=[]
for high in (False,True):
    bpy.context.scene.nms_main.new_file()
    bpy.context.scene.bbe_detailed_proxies=high
    frame=Matrix.Translation((2,3,4))
    first=v2.add_part('B_STR_J_Y_NE',high_res=high).object
    first.matrix_world=frame @ Matrix.Translation((1,0,0))
    second=v2.add_part('B_CON_7',high_res=high).object
    second.matrix_world=frame @ Matrix.Translation((-1,0,0))
    bpy.context.view_layer.update()
    group=Group.group_objects([first,second],frame)
    assert group is not None
    before=points([group])
    bpy.ops.object.select_all(action='DESELECT')
    group.select_set(True)
    bpy.context.view_layer.objects.active=group
    assert bpy.ops.object.nms_mirror()=={'FINISHED'}
    bpy.context.view_layer.update()
    mirrored=bpy.context.view_layer.objects.active
    expected=[Vector((4-p.x,p.y,p.z)) for p in before]
    surface_error=error(expected,points([mirrored]))
    assert surface_error<.05,(high,surface_error)
    records=addon.BUILDER.serialise()['Objects']
    assert len(records)==2
    assert {r['ObjectID'] for r in records}=={'^B_STR_J_Y_NW','^B_CON_7'}
    bpy.context.scene.nms_main.new_file()
    bpy.context.scene.bbe_detailed_proxies=high
    v2.deserialise_from_data({'Objects':records})
    restored=[o for o in bpy.context.scene.objects if 'ObjectID' in o]
    reload_error=error(expected,points(restored))
    assert reload_error<.05,(high,reload_error)
    checks.append((high,surface_error,reload_error))
report('mirror_pivot_group_pass',{'checks':checks})
