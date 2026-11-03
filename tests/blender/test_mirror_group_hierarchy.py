"""Check reflected surfaces, group export and renamed-part parenting."""
import math,sys
from pathlib import Path
import bpy
from mathutils import Matrix,Euler,Vector
from mathutils.bvhtree import BVHTree
sys.path.insert(0,str(Path(__file__).resolve().parent))
from test_support import addon,module,report
Group=module('group').Group
Part=module('part').Part

def surface(objects):
    vertices,faces=[],[]
    for obj in objects:
        offset=len(vertices)
        vertices.extend(obj.matrix_world@v.co for v in obj.data.vertices)
        faces.extend(tuple(i+offset for i in p.vertices) for p in obj.data.polygons)
    return vertices,faces

def reflected(shape,matrix):
    return [matrix@v for v in shape[0]],shape[1]

def distance(a,b):
    def one(a,b):
        tree=BVHTree.FromPolygons(*b,all_triangles=False)
        return max(tree.find_nearest(p)[3] for p in a[0][::max(1,len(a[0])//1000)])
    return max(one(a,b),one(b,a))

def fresh(high=False):
    bpy.context.scene.nms_main.new_file()
    for obj in list(bpy.context.scene.objects):
        if obj.type=='EMPTY':bpy.data.objects.remove(obj,do_unlink=True)
    bpy.context.scene.bbe_detailed_proxies=high

def add(ident,matrix):
    bpy.ops.object.select_all(action='DESELECT')
    assert bpy.ops.object.nms_asset_browser_object_selected(object_id=ident)=={'FINISHED'}
    obj=bpy.context.view_layer.objects.active;obj.matrix_world=matrix
    bpy.context.view_layer.update()
    return obj

def select(obj):
    bpy.ops.object.select_all(action='DESELECT');obj.select_set(True)
    bpy.context.view_layer.objects.active=obj

checks=[]
for high in (False,True):
    for sign in (-1,1):
        for axis in 'XYZ':
            fresh(high)
            pose=Matrix.Translation((5.9285,-.75074,2.8767))@Euler((math.pi/2,math.radians(-16.65),0)).to_matrix().to_4x4()@Matrix.Scale(.312*sign,4)
            obj=add('B_WNG_O_2_R',pose)
            parent=bpy.data.objects.new('Parent',None);bpy.context.scene.collection.objects.link(parent)
            parent.matrix_world=Matrix.Translation((3,-2,1))@Euler((.3,.4,.5)).to_matrix().to_4x4()
            obj.parent=parent;obj.matrix_world=pose;bpy.context.view_layer.update()
            before=surface([obj]);inverse=obj.matrix_parent_inverse.copy()
            reflect=Matrix.Identity(4);reflect['XYZ'.index(axis)]['XYZ'.index(axis)]=-1
            op=getattr(bpy.ops.object,'nms_universal_mirror_'+axis.lower())
            assert op()=={'FINISHED'};bpy.context.view_layer.update()
            assert obj.parent==parent and obj.matrix_parent_inverse==inverse
            assert obj['ObjectID']=='B_WNG_O_2'
            error=distance(reflected(before,reflect),surface([obj]));assert error<1e-4,error
            assert op()=={'FINISHED'};bpy.context.view_layer.update()
            assert obj.parent==parent and obj['ObjectID']=='B_WNG_O_2_R'
            assert distance(before,surface([obj]))<1e-4
            checks.append(dict(high=high,sign=sign,axis=axis,error=error))

    for opname,axis in (('nms_mirror','X'),('nms_flip','Y'),('nms_turn','Z')):
        fresh(high)
        frame=Matrix.Translation((2,3,4))@Euler((.3,.4,.5)).to_matrix().to_4x4()
        objects=[add('B_WNG_O_2_R',frame@Matrix.Translation((x,y,0))@Euler((.2,.4,z)).to_matrix().to_4x4()@Matrix.Scale(.312,4))
                 for x,y,z in ((2,1,.1),(-1,-2,.8))]
        obj=Group.group_objects(objects,frame);select(obj);bpy.context.view_layer.update()
        before=surface([obj]);reflect=Matrix.Identity(4);reflect['XYZ'.index(axis)]['XYZ'.index(axis)]=-1
        expected=reflected(before,frame@reflect@frame.inverted())
        op=getattr(bpy.ops.object,opname)
        assert op()=={'FINISHED'};bpy.context.view_layer.update();obj=bpy.context.view_layer.objects.active
        assert distance(expected,surface([obj]))<1e-4
        assert distance(before,surface([obj]))>.01
        records=addon.BUILDER.serialise()['Objects'];assert len(records)==2
        assert op()=={'FINISHED'};bpy.context.view_layer.update();obj=bpy.context.view_layer.objects.active
        assert distance(before,surface([obj]))<1e-4
        fresh(high)
        module('builder_v2').deserialise_from_data({'Objects':records})
        restored=[o for o in bpy.context.scene.objects if 'ObjectID' in o]
        bpy.context.view_layer.update()
        error=distance(expected,surface(restored))
        assert error<1e-4,(opname,high,error,records)
        checks.append(dict(high=high,group_action=opname,export_roundtrip=True))

report('mirror_group_hierarchy_pass',dict(version=bpy.app.version_string,addon_path=addon.__file__,checks=checks))
