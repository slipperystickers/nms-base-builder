"""Tilted-plane follower orientation and Curve Studio editing workflow."""
from pathlib import Path
import sys,math,json,bpy
from mathutils import Vector,Matrix,Euler
sys.path.insert(0,str(Path(__file__).resolve().parent))
from test_support import module,report,QA
c=module('curve_tools');studio=module('curve_studio');curve=module('utils.curve');b=module('builder_v2')
bpy.context.scene.nms_main.new_file()
seed=b.add_part('BUILDWALL',high_res=False,user_data=0).object
rot=Euler((.9,.65,.3)).to_matrix().to_4x4()
normal=rot.to_3x3()@Vector((0,0,1))
# Reproduce an old drawn path with a tilted face stored directly in its coordinates.
o=c.new_curve(bpy.context,'FREE')
coords=[rot@Vector((7*math.cos(i*math.tau/12),5*math.sin(i*math.tau/12),0)) for i in range(12)]
c.set_free_points(o,coords,True)
world=[o.matrix_world@p.co for p in o.data.splines[0].bezier_points]
studio.choose(bpy.context,[o,seed]);bpy.context.view_layer.objects.active=o
bpy.context.scene.nms_build_tool.duplicate_along_curve(12,1)
bpy.context.view_layer.update()
assert all((a-o.matrix_world@p.co).length<1e-4 for a,p in zip(world,o.data.splines[0].bezier_points))
children=curve.get_all_curve_children(o)
q0=children[0].matrix_world.to_quaternion();face=q0.inverted()@normal
for child in children:
 assert (child.matrix_world.to_quaternion()@face-normal).length<2e-4,child.name
# Relative rotation progresses around the same face: not parallel copies.
assert abs(children[3].matrix_world.to_quaternion().dot(q0))<.9
# Persisted independent spacing, no repeated end positions, and fill mode.
studio.select_children(bpy.context,o);assert studio.child_mode(bpy.context,o)
assert len(bpy.context.selected_objects)==12
c.value_set(o,'spacing',.7);bpy.context.view_layer.update()
assert abs(studio.spacing(o)-.7)<1e-5
f=[ch['curve_factor'] for ch in children];assert len(set(round(v,6) for v in f))==12
assert max(f)<.4
c.value_set(o,'radius_multiplier',1.3);bpy.context.view_layer.update()
assert all(abs(ch.scale.x-1.3)<1e-4 for ch in children)
c.value_set(o,'objects_count',8);assert len(curve.get_all_curve_children(o))==8
studio.select_children(bpy.context,o);children=curve.get_all_curve_children(o)
# Existing native transforms honor world translation and individual-center rotation.
bpy.context.scene.transform_orientation_slots[0].type='GLOBAL'
bpy.context.scene.tool_settings.transform_pivot_point='INDIVIDUAL_ORIGINS'
bpy.context.view_layer.update();before=[x.matrix_world.copy() for x in children]
assert bpy.ops.bbe.studio_transform(kind='MOVE',move=(1,2,3))=={'FINISHED'}
bpy.context.view_layer.update()
assert all((x.matrix_world.translation-a.translation-Vector((1,2,3))).length<1e-4 for x,a in zip(children,before))
before=[x.matrix_world.copy() for x in children]
assert bpy.ops.bbe.studio_transform(kind='ROTATE',angle=.4,axis='Z')=={'FINISHED'}
bpy.context.view_layer.update()
assert all((x.matrix_world.translation-a.translation).length<1e-4 for x,a in zip(children,before))
assert bpy.ops.bbe.studio_transform(kind='SCALE',size=(1.2,1.2,1.2))=={'FINISHED'}
bpy.context.view_layer.update();scales=[x.scale.copy() for x in children]
studio.select_parent(bpy.context,o);c.refresh(o);bpy.context.view_layer.update()
assert all((x.scale-a).length<1e-4 for x,a in zip(children,scales))
assert bpy.ops.bbe.studio_action(action='FILL')=={'FINISHED'}
assert 'bbe_curve_spacing' not in o
# Local-axis movement differs per object; group rotation shares the evaluated center.
studio.select_children(bpy.context,o);bpy.context.view_layer.update()
bpy.context.scene.transform_orientation_slots[0].type='LOCAL'
bpy.context.scene.tool_settings.transform_pivot_point='INDIVIDUAL_ORIGINS'
before=[ch.matrix_world.copy() for ch in children]
studio.apply_transform(bpy.context,'MOVE',(.4,0,0))
bpy.context.view_layer.update()
for ch,old in zip(children,before):
 assert (ch.matrix_world.translation-old.translation-old.to_quaternion()@Vector((.4,0,0))).length<1e-4
bpy.context.scene.transform_orientation_slots[0].type='GLOBAL'
bpy.context.scene.tool_settings.transform_pivot_point='MEDIAN_POINT'
before=[ch.matrix_world.copy() for ch in children];center=sum((w.translation for w in before),Vector())/len(before)
studio.apply_transform(bpy.context,'ROTATE',.5,'Z');bpy.context.view_layer.update()
rotation=Matrix.Rotation(.5,3,'Z')
for ch,old in zip(children,before):
 assert (ch.matrix_world.translation-(center+rotation@(old.translation-center))).length<1e-4
# New copies remain selectable in child mode, and exact quantity editing works.
assert bpy.ops.bbe.curve_number(field='objects_count',value=11)=={'FINISHED'}
assert len(bpy.context.selected_objects)==11
assert all(not ch.hide_select for ch in curve.get_all_curve_children(o))
c.value_set(o,'objects_count',8);studio.select_parent(bpy.context,o)
# Both themes change all control colors; icons are packaged-independent silhouettes.
w=module('curve_widgets');icons=module('curve_icons')
w.update_theme(bpy.context);old=w.INK
ui=bpy.context.preferences.themes[0].user_interface;before_color=tuple(ui.wcol_box.inner)
ui.wcol_box.inner=(.8,.75,.7,1);w.update_theme(bpy.context);assert w.INK!=old
for kind,_,_ in c.SHAPES:
 if kind!='FREE':
  icons.icon_id(kind,bpy.context)
  assert max(list(icons._collection[kind].icon_pixels_float)[3::4])>0
ui.wcol_box.inner=before_color
path=QA/'curve-studio.blend';bpy.ops.wm.save_as_mainfile(filepath=str(path));bpy.ops.wm.open_mainfile(filepath=str(path))
assert len(curve.get_all_curve_children(bpy.context.active_object))==8
report('curve_studio',dict(status='passed',tilted_face=True,flower_orientation=True,spacing=True,child_size=True,world_local_centers=True,move_rotate_scale=True,exact_quantity=True,scale_persistence=True,theme=True,icons=8))
