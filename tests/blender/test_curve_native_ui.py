"""Native viewport tools, defaults, compact controls, and curve persistence."""
from pathlib import Path
import sys,math,bpy
from mathutils import Vector,Matrix
from types import SimpleNamespace
sys.path.insert(0,str(Path(__file__).parent))
from test_support import module,report,QA
c=module('curve_tools');s=module('curve_studio');curve=module('utils.curve');b=module('builder_v2')
bpy.context.scene.nms_main.new_file()
seed=b.add_part('BUILDWALL',high_res=False,user_data=0).object
obj=c.new_curve(bpy.context,'CIRCLE')
s.choose(bpy.context,[obj,seed]);bpy.context.view_layer.objects.active=obj
bpy.context.scene.nms_build_tool.duplicate_along_curve(8,1)
s.select_children(bpy.context,obj)
children=curve.get_all_curve_children(obj)
assert len(bpy.context.selected_objects)==8
assert bpy.context.scene.transform_orientation_slots[0].type=='LOCAL'
assert bpy.context.scene.tool_settings.transform_pivot_point=='INDIVIDUAL_ORIGINS'
area=next(a for a in bpy.context.screen.areas if a.type=='VIEW_3D')
region=next(r for r in area.regions if r.type=='WINDOW')
def worlds():
    bpy.context.view_layer.update()
    return [x.matrix_world.copy() for x in children]
def equal(a,b):return max(abs(a[i][j]-b[i][j]) for i in range(4) for j in range(4))<1e-4
with bpy.context.temp_override(area=area,region=region):
    for action,tool in [('MOVE','builtin.move'),('ROTATE','builtin.rotate'),('SCALE','builtin.scale')]:
        assert bpy.ops.bbe.studio_action(action=action)=={'FINISHED'}
        assert bpy.context.workspace.tools.from_space_view3d_mode('OBJECT').idname==tool
        assert area.spaces.active.show_gizmo and area.spaces.active.show_gizmo_tool
    before=worlds()
    bpy.ops.transform.translate(value=(1,2,3),orient_type='GLOBAL')
    assert all((a.translation-z.translation-Vector((1,2,3))).length<1e-4 for a,z in zip(worlds(),before))
    before=worlds()
    bpy.ops.transform.rotate(value=.4,orient_axis='Z',orient_type='LOCAL',constraint_axis=(False,False,True))
    after=worlds()
    assert all((a.translation-z.translation).length<1e-4 for a,z in zip(after,before))
    assert all(a.to_quaternion().rotation_difference(z.to_quaternion()).angle>.3 for a,z in zip(after,before))
    before=after
    bpy.ops.transform.resize(value=(1.2,1.2,1.2),orient_type='LOCAL')
    after=worlds()
    assert all((a.translation-z.translation).length<1e-4 for a,z in zip(after,before))
    assert all(abs(u/v-1.2)<1e-4 for a,z in zip(after,before) for u,v in zip(a.to_scale(),z.to_scale()))
    bpy.ops.bbe.studio_action(action='AXES');bpy.ops.bbe.studio_action(action='PIVOT')
    assert bpy.context.scene.transform_orientation_slots[0].type=='GLOBAL'
    assert bpy.context.scene.tool_settings.transform_pivot_point=='MEDIAN_POINT'
    before=worlds();center=sum((m.translation for m in before),Vector())/len(before)
    bpy.ops.transform.rotate(value=.3,orient_axis='Z',orient_type='GLOBAL',constraint_axis=(False,False,True))
    rotation=Matrix.Rotation(.3,3,'Z')
    assert all((a.translation-(center+rotation@(z.translation-center))).length<1e-4 for a,z in zip(worlds(),before))
    before=worlds()
    bpy.ops.bbe.studio_action(action='PARENT')
    c.refresh(obj)
    assert all(equal(a,z) for a,z in zip(worlds(),before))
    bpy.ops.bbe.studio_action(action='CHILDREN')
    assert len(bpy.context.selected_objects)==8
    # User choices survive switching Parent / Children; defaults aren't forced repeatedly.
    assert bpy.context.scene.transform_orientation_slots[0].type=='GLOBAL'
    assert bpy.context.scene.tool_settings.transform_pivot_point=='MEDIAN_POINT'
    bpy.ops.bbe.studio_action(action='AXES');bpy.ops.bbe.studio_action(action='PIVOT')
    # The card starts below the information overlay in a full-height viewport.
    fake=SimpleNamespace(preferences=SimpleNamespace(system=SimpleNamespace(ui_scale=1.0)),scene=bpy.context.scene,
        area=area,region=SimpleNamespace(width=1920,height=1200),active_object=children[0],selected_objects=children)
    x,y,w,h=c.card_rect(fake)
    assert abs(y+h-950)<1e-4,(x,y,w,h,c._anchors)
    # Run the actual control layout without a GPU to inspect the exposed actions.
    class Hidden:
        hide=False
    class Layout:
        def __init__(self):self.buttons=[];self.points=[];self.card=SimpleNamespace();self.entries=[]
        def button(self,index,label,operator,x,y,w,props=None,style='BUTTON',height=28):
            self.entries.append((label,operator,props or {},style))
            return SimpleNamespace()
        def draw_points(self,*args):pass
    ui=Layout();c.BBE_GGT_curve_controls.draw_prepare(ui,bpy.context)
    labels=[r[0] for r in ui.entries];ops=[r[1] for r in ui.entries]
    assert 'Edit Parent' in labels and 'Select All Children' in labels
    assert 'bbe.studio_drag' not in ops and 'bbe.studio_transform' not in ops
    assert len([r for r in ui.entries if r[3]=='SWITCH'])==2
    assert next(r for r in ui.entries if r[0]=='Edit Parent')[3]=='NAV'
    bpy.ops.bbe.studio_action(action='PARENT')
    ui=Layout();c.BBE_GGT_curve_controls.draw_prepare(ui,bpy.context)
    assert next(r for r in ui.entries if r[0]=='Edit Children')[3]=='NAV'
before=worlds();data=bpy.context.scene.nms_main.serialise(objects_only=True)
path=QA/'curve-native-ui.blend'
bpy.ops.wm.save_as_mainfile(filepath=str(path));bpy.ops.wm.open_mainfile(filepath=str(path))
assert bpy.context.scene.nms_main.serialise(objects_only=True)==data
report('curve_native_ui',dict(status='passed',native_tools=3,native_move=True,native_individual_rotate_scale=True,
    median_rotation=True,defaults=True,toggles=True,selection=True,layout=True,lower_position=True,
    edit_persistence=True,save_export_roundtrip=True))
