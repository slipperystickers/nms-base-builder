"""A legacy curve's embedded group cache migrates once and mirrors exactly."""
import json,sys
from pathlib import Path
import bpy
from mathutils import Matrix,Vector
sys.path.insert(0,str(Path(__file__).parent))
from test_support import addon,module,report
Curve=module('utils.curve').Curve
curve=module('utils.curve')
Group=module('group').Group
pivot=module('utils.mirror_pivot')
identity='B_STR_J_Y_NE'
native=Matrix.Translation((4.5,2.2,8.1))
cache={'Part':{'ObjectID':identity,'UserData':0,'Timestamp':1,
               'matrix_local':[list(row) for row in native]}}
data=bpy.data.curves.new('Legacy','CURVE')
obj=bpy.data.objects.new('Legacy Curve',data)
bpy.context.scene.collection.objects.link(obj)
obj[Curve.PROP_GROUP_CHILD_CACHE]=json.dumps(cache)
curve.ensure_group_display_cache(obj)
assert obj[Curve.PROP_DISPLAY_PIVOT_CACHE]
display=Matrix(json.loads(obj[Curve.PROP_GROUP_CHILD_CACHE])['Part']['matrix_local'])
assert (display.translation-(native @ Matrix.Translation(-pivot.pivot(identity))).translation).length<1e-5
once=obj[Curve.PROP_GROUP_CHILD_CACHE]
curve.ensure_group_display_cache(obj)
assert once==obj[Curve.PROP_GROUP_CHILD_CACHE]
mirrored,origin=Group.mirror_cache_data(once,Matrix.Identity(4),'X',Vector((0,0,0)))
record=json.loads(mirrored)['Part']
assert record['ObjectID']=='B_STR_J_Y_NW'
new=Matrix(record['matrix_local'])
assert (new.translation-Vector((-display.translation.x,display.translation.y,display.translation.z))).length<1e-5
report('mirror_pivot_curve_cache_pass',{'migrated_once':True,'numeric_reflection':True})
