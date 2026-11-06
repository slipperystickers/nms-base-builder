"""Curve shapes, editing and integration with existing BBE followers."""
from pathlib import Path
import sys,math,bpy,json
from types import SimpleNamespace
from mathutils import Vector
sys.path.insert(0,str(Path(__file__).resolve().parent))
from test_support import module,report,QA
c=module('curve_tools');shapes=module('curve_shapes');b=module('builder_v2');curve=module('utils.curve')
bpy.context.scene.nms_main.new_file()
created=[]
for kind,_,_ in shapes.SHAPES:
 if kind=='FREE':continue
 obj=c.new_curve(bpy.context,kind);created.append(obj)
 s=obj.data.splines[0];assert len(s.bezier_points)>=4
 assert s.use_cyclic_u==(kind in {'CIRCLE','ELLIPSE'})
 assert all(math.isfinite(v) for p in s.bezier_points for v in p.co)
 assert not obj.get('ObjectID')
# Circle handles remain tangent and endpoints satisfy radius.
o=created[0];s=o.data.splines[0]
for p in s.bezier_points:
 assert abs(p.co.length-4)<1e-5
 assert abs(p.co.dot(p.handle_right-p.co))<1e-5
# A hand-moved point survives radius edits and an increased control point count.
bp=s.bezier_points[0];bp.co.z+=2;bp.handle_left.z+=2;bp.handle_right.z+=2
bp.radius=1.25;bp.tilt=.4
o.bbe_curve.radius=7
assert abs(o.data.splines[0].bezier_points[0].co.z-2)<1e-5
assert abs(o.data.splines[0].bezier_points[0].radius-1.25)<1e-5
assert abs(o.data.splines[0].bezier_points[0].tilt-.4)<1e-5
o.bbe_curve.points=16
assert abs(o.data.splines[0].bezier_points[0].co.z-2)<1e-5
# Explicit tangent handles preserve the anchor, align optionally, and survive parameters.
bp=o.data.splines[0].bezier_points[0]
record=c.point_record(bp);delta=Vector((.5,1.25,.3))
c.move_control(bp,record,delta,'RIGHT',True)
assert (bp.co-Vector(record[0])).length<1e-6
assert (bp.handle_right-(Vector(record[2])+delta)).length<1e-5
assert (bp.handle_left-bp.co).cross(bp.handle_right-bp.co).length<1e-5
assert abs((bp.handle_left-bp.co).length-(Vector(record[1])-Vector(record[0])).length)<1e-5
handles=json.loads(o['bbe_curve_handle_baseline']);base=json.loads(o['bbe_curve_baseline'])
custom=bp.handle_right-bp.co-(Vector(handles[0][1])-Vector(base[0]))
o.bbe_curve.radius=8
bp=o.data.splines[0].bezier_points[0]
handles=json.loads(o['bbe_curve_handle_baseline']);base=json.loads(o['bbe_curve_baseline'])
assert (bp.handle_right-bp.co-(Vector(handles[0][1])-Vector(base[0]))-custom).length<1e-5
record=c.point_record(bp)
c.move_control(bp,record,delta,'LEFT',False)
assert (bp.handle_right-Vector(record[2])).length<1e-5
assert (bp.co-Vector(record[0])).length<1e-5
c.restore_point(bp,record)
assert all((Vector(a)-Vector(b)).length<1e-5 for a,b in zip(c.point_record(bp)[:3],record[:3]))
o.bbe_curve.radius=7

# Linked duplicate curve data becomes independent on editing.
copy=o.copy();bpy.context.collection.objects.link(copy);assert copy.data==o.data
copy.bbe_curve.radius=9;assert copy.data!=o.data
assert o.bbe_curve.radius==7
helix=next(o for o in created if o.bbe_curve.kind=='HELIX')
helix.bbe_curve.turns=12
assert len(helix.data.splines[0].bezier_points)>=97
assert helix.bbe_curve.points==len(helix.data.splines[0].bezier_points)
# Free curves interpolate placed points and stay out of game data.
free=c.new_curve(bpy.context,'FREE');c.set_free_points(free,[(0,0,0),(3,2,1),(6,0,2)])
assert [tuple(p.co) for p in free.data.splines[0].bezier_points]==[(0,0,0),(3,2,1),(6,0,2)]
assert bpy.context.scene.nms_main.serialise(objects_only=True)==[]
# Legacy duplicate tool consumes a new guide and follows subsequent point changes.
seed=b.add_part('BUILDWALL',high_res=False,user_data=0).object
for obj in bpy.context.selected_objects:obj.select_set(False)
seed.select_set(True);free.select_set(True);bpy.context.view_layer.objects.active=free
bpy.context.scene.nms_build_tool.duplicate_along_curve(6,1)
children=curve.get_all_curve_children(free);assert len(children)==6
bpy.context.view_layer.update();before=[o.matrix_world.copy() for o in children]
free.data.splines[0].bezier_points[1].co.y+=4;c.refresh(free);bpy.context.view_layer.update()
assert any((a.translation-o.matrix_world.translation).length>0.01 for a,o in zip(before,children))
c.value_set(free,'objects_count',9);assert len(curve.get_all_curve_children(free))==9
c.value_set(free,'radius_multiplier',1.5);assert abs(free['radius_multiplier']-1.5)<1e-6
# Handle editing updates the existing linked-object layout without moving its anchor.
bpy.context.view_layer.update();followers=curve.get_all_curve_children(free)
old_matrices=[o.matrix_world.copy() for o in followers]
bp=free.data.splines[0].bezier_points[1];record=c.point_record(bp)
c.move_control(bp,record,Vector((0,3,0)),'RIGHT',False);c.refresh(free);bpy.context.view_layer.update()
assert (bp.co-Vector(record[0])).length<1e-6
assert any((a.translation-o.matrix_world.translation).length>.01 for a,o in zip(old_matrices,followers))
c.restore_point(bp,record);c.refresh(free);bpy.context.view_layer.update()
assert len(curve.get_all_curve_children(free))==9
# Child selection resolves the same curve and helper parameters.
child=curve.get_all_curve_children(free)[0];child.hide_select=False
for obj in bpy.context.selected_objects:obj.select_set(False)
child.select_set(True);bpy.context.view_layer.objects.active=child
assert c.active_curve(bpy.context)==free
assert ('objects_count','Copies') in c.helper_parameters(free)
# Add/remove/smooth point controls, open/close, undo, project persistence.
assert bpy.ops.bbe.curve_action(action='ADD')=={'FINISHED'};assert len(free.data.splines[0].bezier_points)==4
assert bpy.ops.bbe.curve_action(action='REMOVE')=={'FINISHED'};assert len(free.data.splines[0].bezier_points)==3
assert bpy.ops.bbe.curve_action(action='CLOSED')=={'FINISHED'};assert free.data.splines[0].use_cyclic_u
assert bpy.ops.bbe.curve_action(action='SMOOTH')=={'FINISHED'}
bpy.context.view_layer.update()
serialized=bpy.context.scene.nms_main.serialise(objects_only=True)
print('EXPORTED_COUNT',len(serialized),'CHILDREN',len(curve.get_all_curve_children(free)),'COUNT',free['objects_count'],flush=True)
assert len(serialized)==10
path=QA/'easy-curves.blend';bpy.ops.wm.save_as_mainfile(filepath=str(path));bpy.ops.wm.open_mainfile(filepath=str(path))
assert bpy.context.scene.nms_main.serialise(objects_only=True)==serialized
assert len(c.active_curve(bpy.context).data.splines[0].bezier_points)==3
# Exercise both real panel draw functions to catch context/signature regressions.
class Layout:
 def __init__(self):self.ops=[];self.fields=[]
 def __getattr__(self,name):return lambda *args,**kwargs:self
 def operator(self,name,**kwargs):self.ops.append(name);return SimpleNamespace()
 def prop(self,obj,name,**kwargs):self.fields.append(name)
builder_layout=Layout()
module('tools.build_tool_presentation').NMS_PT_tools_panel.draw(SimpleNamespace(layout=builder_layout,toolbar_group='builder_tools'),bpy.context)
assert {'location','rotation_euler','uniform_scale'}<=set(builder_layout.fields)
assert 'object.nms_duplicate' in builder_layout.ops
assert 'object.nms_duplicate_along_curve' not in builder_layout.ops
curve_layout=Layout();c.draw_controls(curve_layout,bpy.context)
assert {'object.nms_duplicate_along_curve','object.nms_duplicate','bbe.curve_draw'}<=set(curve_layout.ops)
assert 'location' not in curve_layout.fields
# Clean unregister/register roundtrip of the new module.
c.unregister();assert not hasattr(bpy.types.Object,'bbe_curve')
c.register();assert hasattr(bpy.types.Object,'bbe_curve')
report('easy_curves',dict(status='passed',presets=8,manual_offsets=True,tangent_handles=True,handle_preservation=True,point_radius_tilt=True,high_turn_sampling=True,independent_data=True,followers=True,child_selection=True,helpers_not_exported=True,persistence=True,menu_draws=True,lifecycle=True))
