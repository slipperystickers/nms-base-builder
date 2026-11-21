"""Regression coverage for live placements, edge repeat ranges, and popup hit areas."""
import math
from pathlib import Path
import sys
from types import SimpleNamespace

sys.path.insert(0,str(Path(__file__).resolve().parent))
from test_support import bpy, module
from mathutils import Euler, Matrix, Vector

align=module('alignment_tools')
tools=module('duplication_tools')
trim=module('edge_trim')
surface=module('curve_surface')
studio=module('curve_studio')
backend=module('builder_geometry_backend')
controls=module('part_controls')
ctx=bpy.context


def cube(name, at, rotation):
    bpy.ops.mesh.primitive_cube_add(location=at,rotation=rotation)
    obj=ctx.active_object
    obj.name=name
    obj['ObjectID']='BUILDFLATPANEL'
    obj['UserData']=0
    obj['SnapID']='BUILDFLATPANEL'
    return obj


def feature(obj, polygon, kind):
    m=obj.matrix_world.copy()
    pts=[m @ obj.data.vertices[i].co for i in polygon.vertices]
    lines=[v for edge in zip(pts,pts[1:]+pts[:1]) for v in edge]
    pos=m @ polygon.center
    axis=(m.to_3x3().inverted().transposed() @ polygon.normal).normalized()
    if kind=='EDGE':pos=(pts[0]+pts[1])/2;axis=(pts[1]-pts[0]).normalized();lines=pts[:2]
    if kind=='POINT':pos=pts[0];axis=Vector();lines=[]
    return align.Feature(obj,obj,pos,axis,lines,m,m,kind)


source=cube('Moving panel',(2,1,-3),(.4,-.2,1.4))
target=cube('Destination panel',(-1,7,5),(-.3,.8,.2))
source.scale=(2,.4,.2);target.scale=(3,.7,.2)
ctx.view_layer.update()
original=source.matrix_world.copy()
for kind in ('FACE','EDGE','POINT'):
    a=feature(source,source.data.polygons[1],kind)
    b=feature(target,target.data.polygons[4],kind)
    live=align.Placement(ctx,a,b)
    basis=align.alignment_delta(a,b)
    axis=b.direction if kind!='POINT' else Vector((0,1,0))
    for angle in (0,90,13.25,-28,180,360):
        delta=Matrix.Translation(b.point) @ Matrix.Rotation(math.radians(angle),4,axis) @ Matrix.Translation(-b.point) @ basis
        live.place(delta)
        real=source.matrix_world @ original.inverted()
        assert (real @ a.point-b.point).length<2e-5
        if kind!='POINT':
            dot=(real.to_3x3() @ a.direction).normalized().dot(b.direction)
            assert abs(dot+1)<1e-5 if kind=='FACE' else abs(dot)>.99999
        if angle==0 and kind=='FACE':
            side=real.to_3x3() @ align.face_tangents(a)[0]
            assert max(abs(side.dot(v)) for v in align.face_tangents(b))>.99999
    live.restore()
    assert align.matrix_error(original,source.matrix_world)<1e-5
    if kind=='FACE':
        live=align.Placement(ctx,a,b)
        live.place(align.alignment_delta(a,b,reverse=True))
        assert ((live.delta.to_3x3() @ a.direction).dot(b.direction))>.99999
        live.restore()
assert align.BBE_OT_align_geometry.bl_rna is not None
for closed in (False,True):
    points=[Vector(v) for v in [(0,1,0),(.5,.2,0),(1,0,0),(9,0,0),(9.5,.2,0),(10,1,0)]]
    guide=surface.create_guides(ctx,[(points,closed)])[0]
    tools.finish_edge(ctx,guide,[source.name])
    trace=trim.Trace(guide)
    lo=trace.stops[2]/trace.stops[-1];hi=trace.stops[3]/trace.stops[-1]
    trim.trim(guide,trace,lo,hi)
    spline=guide.data.splines[0]
    actual=[guide.matrix_world @ bp.co for bp in spline.bezier_points]
    assert len(actual)==2 and not spline.use_cyclic_u and (actual[0]-points[2]).length<1e-4 and (actual[-1]-points[3]).length<1e-4,actual
    ctx.view_layer.update()
    children=backend.children(guide)
    assert len(children)==3
    stations=sorted([o.matrix_world.translation.copy() for o in children],key=lambda v:v.x)
    assert (stations[0]-points[2]).length<.01 and (stations[-1]-points[3]).length<.01,stations
    tools.adjust(guide,'distance',12)
    tip=guide.matrix_world @ guide.data.splines[0].bezier_points[-1].co
    assert tip.x>12.9 and abs(tip.y)<1e-4,tip
    reopened=trim.Trace(guide)
    assert all(abs(a-b)<1e-5 for a,b in zip(reopened.limits,(lo,hi))),reopened.limits
    trim.trim(guide,reopened,0.,1.)
    restored=guide.data.splines[0]
    assert restored.use_cyclic_u==closed and len(restored.bezier_points)==len(points)
    for co,bp in zip(points,restored.bezier_points):assert (guide.matrix_world @ bp.co-co).length<1e-5

from types import SimpleNamespace as NS
for x,y in ((200,220),(690,60),(30,35),(535,350)):
    fake=NS(region=NS(width=800,height=480,x=0,y=0),area=NS(regions=[NS(type='UI',width=120,height=480,alignment='RIGHT',x=680,y=0)]),space_data=NS(show_gizmo=True),selected_objects=[source],scene=ctx.scene,preferences=ctx.preferences)
    buttons=[NS(width=114,height=25),NS(width=105,height=25)]
    controls.position_part_buttons(fake,Vector((x,y)),buttons)
    radius=max(48,fake.preferences.view.gizmo_size)*1.3*fake.preferences.system.ui_scale
    for button in buttons:
        bx,by=button.matrix_basis.translation[:2]
        assert 0<=bx and bx+button.width<=680 and 0<=by and by+button.height<=480
        assert module('bubble_controls').overlap((bx,by,bx+button.width,by+button.height),(x-radius,y-radius,x+radius,y+radius))==0
print('PASS real mesh contact, spins, flip, rollback; open/closed trace trim, copies, extension and restoration; gizmo clearance')
