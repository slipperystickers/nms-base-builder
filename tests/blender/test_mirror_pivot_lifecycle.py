"""Legacy objects, proxy switches, groups and native export keep their geometry."""
import sys
from pathlib import Path
import bpy
from mathutils import Matrix, Vector

sys.path.insert(0,str(Path(__file__).parent))
from test_support import addon,module,report
v2=module('builder_v2')
pivot=module('utils.mirror_pivot')
Part=module('part').Part
Group=module('group').Group
menu=module('tools_menu.base_builder_menu_operators')

def serialized(obj):
    return Part.deserialise_from_object(obj,v2.BUILDER).serialise()

def bounds(obj):
    coords=[obj.matrix_world @ v.co for v in obj.data.vertices]
    return [(min(p[i] for p in coords),max(p[i] for p in coords)) for i in range(3)]

def bound_error(a,b):
    return max(abs(a[i][j]-b[i][j]) for i in range(3) for j in (0,1))

bpy.context.scene.nms_main.new_file()
bpy.context.scene.bbe_detailed_proxies=True
obj=v2.add_part('B_STR_J_Y_NE',high_res=True).object
obj.matrix_world=Matrix.Translation((4.5,2.7,9.1)) @ Matrix.Scale(.6,4)
bpy.context.view_layer.update()
original_record=serialized(obj)
original_bounds=bounds(obj)
assert pivot.is_normalized(obj)

# Simulate an older .blend: native mesh and native matrix, without pivot tags.
u=pivot.pivot('B_STR_J_Y_NE')
legacy_mesh=obj.data.copy()
legacy_mesh.transform(Matrix.Translation(-u))
del legacy_mesh[pivot.MESH_TAG]
obj.data=legacy_mesh
obj.matrix_world=pivot.native_matrix(obj.matrix_world,'B_STR_J_Y_NE')
del obj[pivot.OBJECT_TAG]
assert bound_error(bounds(obj),original_bounds)<1e-5
assert serialized(obj)['Position']==original_record['Position']
pivot.ensure_object(obj)
assert pivot.is_normalized(obj)
assert bound_error(bounds(obj),original_bounds)<1e-5
assert serialized(obj)['Position']==original_record['Position']

switched,missing=menu._switch_scene_parts(bpy.context,False,{})
assert switched==1 and missing==0,(switched,missing)
low_bounds=bounds(obj)
assert bound_error(low_bounds,original_bounds)<.03,bound_error(low_bounds,original_bounds)
assert serialized(obj)['Position']==original_record['Position']
switched,missing=menu._switch_scene_parts(bpy.context,True,{})
assert switched==1 and missing==0,(switched,missing)
assert bound_error(bounds(obj),original_bounds)<1e-4
assert serialized(obj)['Position']==original_record['Position']

# A regular grouped cache stores display matrices and exports native positions.
other=v2.add_part('B_CON_7',high_res=True).object
other.matrix_world=Matrix.Translation((2.2,3.1,8.0))
bpy.context.view_layer.update()
expected=sorted((serialized(obj),serialized(other)),key=lambda p:p['ObjectID'])
group=Group.group_objects([obj,other])
assert group is not None
actual=sorted(Group.serialise(group),key=lambda p:p['ObjectID'])
for a,b in zip(expected,actual):
    assert a['ObjectID']==b['ObjectID']
    assert max(abs(x-y) for x,y in zip(a['Position'],b['Position']))<1e-5,(a,b)

# A cache from an older .blend is converted only when read; the group mesh is
# left intact, so its visible geometry cannot jump on open.
cache=__import__('json').loads(group[Group.PROP_CHILD_CACHE])
for entry in cache.values():
    identity=entry['ObjectID']
    if pivot.has_pivot(identity):
        native=Matrix(entry['matrix_local']) @ Matrix.Translation(pivot.pivot(identity))
        entry['matrix_local']=[list(row) for row in native]
group[Group.PROP_CHILD_CACHE]=__import__('json').dumps(cache)
del group[Group.PROP_DISPLAY_PIVOT_CACHE]
before_group_bounds=bounds(group)
actual=sorted(Group.serialise(group),key=lambda p:p['ObjectID'])
assert bound_error(bounds(group),before_group_bounds)<1e-5
for a,b in zip(expected,actual):
    assert max(abs(x-y) for x,y in zip(a['Position'],b['Position']))<1e-5,(a,b)

report('mirror_pivot_lifecycle_pass',{'low_bound_error':bound_error(low_bounds,original_bounds),
    'legacy_geometry_preserved':True,'group_geometry_preserved':True})
