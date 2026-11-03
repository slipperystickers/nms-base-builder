"""Station parts mirror placement/aim; their mesh need not be reflected."""
import math,sys
from pathlib import Path
import bpy
from mathutils import Matrix,Euler,Vector
sys.path.insert(0,str(Path(__file__).resolve().parent))
from test_support import addon,report
results=[]
for high in (False,True):
    for axis in 'XYZ':
        for center in (Vector((0,0,0)),Vector((2,-3,1))):
            bpy.context.scene.nms_main.new_file()
            bpy.context.scene.bbe_detailed_proxies=high
            bpy.ops.object.nms_asset_browser_object_selected(object_id='STA_21')
            obj=bpy.context.view_layer.objects.active
            angles=tuple(math.radians(a) for a in (-25.235,182.05,-15.636))
            pose=Matrix.Translation((.2253,0,4.5721))@Euler(angles).to_matrix().to_4x4()@Matrix.Scale(-.012,4)
            obj.matrix_world=pose;bpy.context.view_layer.update()
            before=obj.matrix_world.copy();mesh=obj.data
            reflect=Matrix.Identity(4);i='XYZ'.index(axis)
            reflect[i][i]=-1;reflect[i][3]=2*center[i]
            bpy.context.scene.nms_build_tool.mirror(axis=axis,center=center)
            bpy.context.view_layer.update()
            after=obj.matrix_world.copy()
            assert obj.data==mesh and obj['ObjectID']=='STA_21'
            assert (after.translation-reflect@before.translation).length<1e-5
            for column in (1,2):
                expected=reflect.to_3x3()@before.col[column].to_3d()
                assert (after.col[column].to_3d()-expected).length<1e-5
            assert (after.to_scale()-before.to_scale()).length<1e-5
            if axis=='X':
                expected_rotation=Euler((angles[0],-angles[1],-angles[2])).to_matrix().to_4x4()@Matrix.Scale(-.012,4)
                assert max(abs(after[r][c]-expected_rotation[r][c]) for r in range(3) for c in range(3))<1e-5
            bpy.context.scene.nms_build_tool.mirror(axis=axis,center=center)
            bpy.context.view_layer.update()
            assert max(abs(obj.matrix_world[r][c]-before[r][c]) for r in range(4) for c in range(4))<1e-5
            results.append(dict(high=high,axis=axis,center=list(center),position=list(after.translation),same_model=True,mirrored_aim=True))
report('station_pose_mirror_pass',dict(version=bpy.app.version_string,addon_path=addon.__file__,cases=results))
