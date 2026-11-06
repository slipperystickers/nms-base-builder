"""Planar handle drags, spatial guides, and click-back selection regression."""
from pathlib import Path
import sys
from types import SimpleNamespace
from unittest.mock import patch
import bpy
from mathutils import Vector, Matrix, Euler
sys.path.insert(0,str(Path(__file__).parent))
from test_support import module,report,QA
c=module('curve_tools');studio=module('curve_studio');curve=module('utils.curve');b=module('builder_v2')
bpy.context.scene.nms_main.new_file()
tested=0
for kind,_,_ in c.SHAPES:
    if kind in {'HELIX','FREE'}:continue
    obj=c.new_curve(bpy.context,kind)
    obj.matrix_world=Matrix.Translation((3,-2,4))@Euler((.8,.5,.3)).to_matrix().to_4x4()@Matrix.Diagonal((2,.7,-1.4,1))
    bpy.context.view_layer.update()
    normal=c.control_plane_normal(obj)
    for axis in (None,'X','Y','Z'):
        for part in ('POINT','LEFT','RIGHT'):
            spline=obj.data.splines[0];records=[c.point_record(p) for p in spline.bezier_points]
            op=SimpleNamespace(obj=obj,spline=0,index=0,records=records,part=part,
                origin=Vector(),normal=Vector((0,0,1)),flat_normal=normal,hit=Vector(),axis=axis)
            ctx=SimpleNamespace(area=SimpleNamespace(header_text_set=lambda *args:None))
            event=SimpleNamespace(type='MOUSEMOVE',value='NOTHING',shift=False)
            with patch.object(c,'plane_hit',return_value=Vector((1.2,2.3,4.5))):
                assert c.BBE_OT_curve_drag_point.modal(op,ctx,event)=={'RUNNING_MODAL'}
            assert max(abs(v.z) for p in spline.bezier_points for v in (p.co,p.handle_left,p.handle_right))<2e-5,(kind,axis,part)
            # Escape restores points and both handle positions, without altering the guide transform.
            assert c.BBE_OT_curve_drag_point.modal(op,ctx,SimpleNamespace(type='ESC'))=={'CANCELLED'}
            for bp,record in zip(spline.bezier_points,records):
                assert max((Vector(a)-Vector(z)).length for a,z in zip(c.point_record(bp)[:3],record[:3]))<1e-5
            tested+=1
# A world Z shortcut cannot pull a horizontal guide out of its plane.
assert c.control_drag_delta(Vector((1,2,3)),Vector((0,1,0)),Vector((0,0,1)),'Z').length==0
helix=c.new_curve(bpy.context,'HELIX')
assert c.control_plane_normal(helix) is None
delta=c.control_drag_delta(Vector((1,0,3)),Vector((0,1,0)),None,'Z')
assert abs(delta.z-3)<1e-6
bp=helix.data.splines[0].bezier_points[0];old=bp.handle_right.copy()
c.move_control(bp,c.point_record(bp),delta,'RIGHT',False)
assert abs(bp.handle_right.z-old.z-3)<1e-5
# Both legacy tilted drawings and genuinely spatial free curves are recognized.
free=c.new_curve(bpy.context,'FREE')
rot=Euler((.7,.9,.2)).to_matrix()
c.set_free_points(free,[rot@Vector(v) for v in [(0,0,0),(3,0,0),(3,4,0),(0,4,0)]])
assert abs(abs(c.control_plane_normal(free).dot(rot@Vector((0,0,1))))-1)<1e-5
c.set_free_points(free,[(0,0,0),(3,0,0),(3,4,2),(0,4,0)])
assert c.control_plane_normal(free) is None
# Real duplicate and selection paths, including saved locks from previous versions.
seed=b.add_part('BUILDWALL',high_res=False,user_data=0).object
drawn=c.new_curve(bpy.context,'FREE');drawn['bbe_curve_draw_plane']=True
c.set_free_points(drawn,[(0,0,0),(3,2,0),(6,0,0)])
studio.choose(bpy.context,[drawn,seed]);bpy.context.view_layer.objects.active=drawn
bpy.context.scene.nms_build_tool.duplicate_along_curve(6,1)
studio.select_children(bpy.context,drawn)
assert not drawn.hide_select
assert all(not x.hide_select for x in curve.get_all_curve_children(drawn))
children=curve.get_all_curve_children(drawn);bpy.context.view_layer.update()
before=[x.matrix_world.copy() for x in children]
# This is the same active-object change delivered by a viewport click.
studio.choose(bpy.context,[drawn]);bpy.context.scene.nms_properties.set_active_obect(drawn)
assert drawn['parent_selected'] and not studio.child_mode(bpy.context,drawn)
assert all(x.hide_select for x in children)
bpy.context.view_layer.update()
assert all(max(abs(a[i][j]-x.matrix_world[i][j]) for i in range(4) for j in range(4))<1e-5 for a,x in zip(before,children))
assert bpy.ops.bbe.curve_action(action='LINK')=={'FINISHED'}
assert not drawn.bbe_curve.linked_handles
assert bpy.ops.bbe.curve_action(action='LINK')=={'FINISHED'}
assert drawn.bbe_curve.linked_handles
studio.select_children(bpy.context,drawn);drawn.hide_select=True
path=QA/'curve-plane-selection.blend'
bpy.ops.wm.save_as_mainfile(filepath=str(path));bpy.ops.wm.open_mainfile(filepath=str(path))
drawn=next(o for o in bpy.data.objects if o.get('bbe_curve_draw_plane'))
assert not drawn.hide_select
assert c.control_plane_normal(drawn) is not None
report('curve_plane_selection',dict(status='passed',flat_modal_drags=tested,transformed_planes=True,
    helix_3d=True,legacy_drawings=True,spatial_free=True,cancel=True,selection=True,reopen=True,toggle=True))
