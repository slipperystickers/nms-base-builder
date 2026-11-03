"""A legacy .blend duplicate mirror keeps source visible and coordinates exact."""
import sys
from pathlib import Path
import bpy
from mathutils import Matrix,Vector
sys.path.insert(0,str(Path(__file__).parent))
from test_support import addon,module,report
v2=module('builder_v2');pivot=module('utils.mirror_pivot')
bpy.context.scene.nms_main.new_file()
source=v2.add_part('B_STR_J_Y_NE').object
source.matrix_world=Matrix.Translation((4.5154,25.7044,11.9521))
u=pivot.pivot(source['ObjectID'])
legacy=source.data.copy();legacy.transform(Matrix.Translation(-u));del legacy[pivot.MESH_TAG]
source.data=legacy
source.matrix_world=pivot.native_matrix(source.matrix_world,source['ObjectID'])
del source[pivot.OBJECT_TAG]
before=[source.matrix_world @ v.co for v in source.data.vertices]
bpy.ops.object.select_all(action='DESELECT')
source.select_set(True);bpy.context.view_layer.objects.active=source
bpy.context.scene.nms_build_tool.mirror(axis='X',center=Vector((0,0,0)),auto_duplicate=True)
bpy.context.view_layer.update()
parts=[o for o in bpy.context.scene.objects if o.get('ObjectID') in {'B_STR_J_Y_NE','B_STR_J_Y_NW'}]
assert len(parts)==2
original=next(o for o in parts if o['ObjectID']=='B_STR_J_Y_NE')
mirrored=next(o for o in parts if o['ObjectID']=='B_STR_J_Y_NW')
assert pivot.is_normalized(original) and pivot.is_normalized(mirrored)
assert (mirrored.matrix_world.translation-Vector((-original.matrix_world.translation.x,
    original.matrix_world.translation.y,original.matrix_world.translation.z))).length<1e-5
assert max((before[i]-(original.matrix_world @ v.co)).length for i,v in enumerate(original.data.vertices))<1e-5
report('mirror_pivot_legacy_duplicate_pass',{'original_visible_unchanged':True,'numeric_reflection':True})
