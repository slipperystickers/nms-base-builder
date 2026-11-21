"""Trim a repeat guide by distance along its original detected edge."""
import bisect
import hashlib
import json

import bpy
from mathutils import Matrix, Vector

from . import builder_geometry_backend as backend
from . import curve_distribution, curve_studio, curve_tools

SOURCE = 'bbe_edge_trim_source'
RANGE = 'bbe_edge_trim_range'
STAMP = 'bbe_edge_trim_geometry'


def records(guide):
    spline = guide.data.splines[0]
    return [curve_tools.point_record(bp) for bp in spline.bezier_points], spline.use_cyclic_u


def base_records(guide):
    points, closed = records(guide)
    tail = json.loads(guide.get('bbe_edge_tail', 'null'))
    if tail and tail['index'] == len(points)-2:
        index = tail['index']
        original = tail['tip']
        delta = Vector(points[index][0]) - Vector(original[0])
        tip = [tuple(Vector(v)+delta) for v in original[:3]] + list(original[3:])
        points = points[:index]+[tip]
    return points, closed


def fingerprint(points, closed):
    # Blender recalculates VECTOR handles when an extension is added.
    items = [(p[0], p[1] if p[3]!='VECTOR' else None, p[2] if p[4]!='VECTOR' else None,
              *p[3:]) for p in points]
    return hashlib.sha256(repr((items,closed)).encode()).hexdigest()


def split(cubic, t):
    a,b,c,d = cubic
    ab,bc,cd = a.lerp(b,t),b.lerp(c,t),c.lerp(d,t)
    left,right = ab.lerp(bc,t),bc.lerp(cd,t)
    mid = left.lerp(right,t)
    return (a,ab,left,mid),(mid,right,cd,d)


class Trace:
    def __init__(self, guide):
        points,closed = base_records(guide)
        self.limits = (0.,1.)
        if SOURCE in guide and guide.get(STAMP)==fingerprint(points,closed):
            points,closed=json.loads(guide[SOURCE])
            self.limits=tuple(guide[RANGE])
        self.build(points, closed, guide.matrix_world.to_3x3())

    @classmethod
    def from_path(cls, points, closed):
        trace = cls.__new__(cls)
        trace.limits = (0., 1.)
        records = [(tuple(p), tuple(p), tuple(p), 'VECTOR', 'VECTOR', 1., 0.) for p in points]
        trace.build(records, closed, Matrix.Identity(3))
        return trace

    def build(self, points, closed, scale):
        self.original=points,closed
        self.serialized=json.dumps(self.original)
        self.segments=[]
        self.stops=[0.]
        for i in range(len(points) if closed else len(points)-1):
            a,b=points[i],points[(i+1)%len(points)]
            start,end=Vector(a[0]),Vector(b[0])
            straight=a[4]=='VECTOR' and b[3]=='VECTOR'
            cubic=(start,start.lerp(end,1/3),start.lerp(end,2/3),end) if straight else (start,Vector(a[2]),Vector(b[1]),end)
            steps=1 if straight else 32
            lengths=[0.]
            prev=start
            for j in range(1,steps+1):
                point=end if j==steps else split(cubic,j/steps)[0][-1]
                lengths.append(lengths[-1]+(scale @ (point-prev)).length)
                prev=point
            if lengths[-1]<1e-8:continue
            self.segments.append((cubic,lengths,a,b,straight))
            self.stops.append(self.stops[-1]+lengths[-1])
        if not self.segments:raise ValueError('This edge has no length to trim.')

    def longest_straight(self):
        # The picker trace consists of straight mesh edges. Compare with the
        # initial heading so a succession of small turns cannot round a corner.
        first=best_start=0
        best_end=1
        heading=None
        for i,(cubic,*_) in enumerate(self.segments):
            direction=(cubic[-1]-cubic[0]).normalized()
            if heading is None or direction.dot(heading)<.99985:
                first=i;heading=direction
            if self.stops[i+1]-self.stops[first]>self.stops[best_end]-self.stops[best_start]:
                best_start,best_end=first,i+1
        return self.stops[best_start]/self.stops[-1], self.stops[best_end]/self.stops[-1]

    def move_handle(self, lo, hi, start_handle, value, width):
        total=self.stops[-1]
        idx=bisect.bisect_left(self.stops,value*total)
        candidates=self.stops[max(0,idx-1):idx+1]
        near=min(candidates,key=lambda v:abs(v-value*total))/total
        if abs(near-value)*width<=4:value=near
        gap=min(.01,max(.000001,.001/total))
        if start_handle:lo=min(value,hi-gap)
        else:hi=max(value,lo+gap)
        return lo,hi

    def clipped(self, lo, hi):
        if lo==0 and hi==1:return self.original
        run=[]
        total=self.stops[-1]
        # The picker measures world vertices. Rebased Blender spline coordinates
        # are float32, so the same corner can differ by a few millionths.
        def snap_distance(value):
            i=bisect.bisect_left(self.stops,value)
            near=min(self.stops[max(0,i-1):i+1],key=lambda stop:abs(stop-value))
            tolerance=min(total*1e-6,(hi-lo)*total*.05)
            return near if abs(value-near)<=tolerance else value
        left,right=snap_distance(lo*total),snap_distance(hi*total)
        first=max(0,bisect.bisect_right(self.stops,left)-1)
        last=min(len(self.segments),bisect.bisect_left(self.stops,right))
        for i in range(first,last):
            cubic,lengths,a,b,straight=self.segments[i]
            start=max(0.,left-self.stops[i])
            end=min(lengths[-1],right-self.stops[i])
            if end-start<=1e-8:continue
            def parameter(distance):
                k=min(len(lengths)-2,bisect.bisect_right(lengths,distance)-1)
                return (k+(distance-lengths[k])/max(1e-12,lengths[k+1]-lengths[k]))/(len(lengths)-1)
            t0,t1=parameter(start),parameter(end)
            part=split(cubic,t1)[0]
            part=split(part,t0/t1)[1] if t0 else part
            def point_record_at(t,position):
                return [tuple(position),tuple(position),tuple(position),'FREE','FREE',
                        a[5]+t*(b[5]-a[5]),a[6]+t*(b[6]-a[6])]
            if not run:run.append(point_record_at(t0,part[0]))
            run[-1][2]=tuple(part[1])
            run.append(point_record_at(t1,part[3]))
            run[-1][1]=tuple(part[2])
            run[-1][2]=tuple(part[3]+(part[3]-part[2]))
            if straight:run[-2][4]=run[-1][3]='VECTOR'
        return run,False


def write_spline(guide, points, closed):
    curve_tools.own_data(guide)
    spline=guide.data.splines[0]
    if len(spline.bezier_points)!=len(points):
        resolution=spline.resolution_u
        guide.data.splines.remove(spline)
        spline=guide.data.splines.new('BEZIER')
        spline.resolution_u=resolution
        spline.bezier_points.add(len(points)-1)
    spline.use_cyclic_u=closed
    for bp,rec in zip(spline.bezier_points,points):curve_tools.restore_point(bp,rec)
    for key in ('total_length','val_data'):
        if key in guide:del guide[key]
    guide.data.update_tag()


def trim(guide, trace, lo, hi):
    points,closed=trace.clipped(lo,hi)
    if len(points)<2:return
    pose=backend.first_pose(guide)
    write_spline(guide,points,closed)
    if 'bbe_edge_tail' in guide:del guide['bbe_edge_tail']
    if guide.get(SOURCE)!=trace.serialized:guide[SOURCE]=trace.serialized
    guide[RANGE]=[lo,hi]
    guide[STAMP]=fingerprint(*base_records(guide))
    count=int(guide.get('objects_count',1))
    length=curve_studio.length(guide)
    if 'bbe_edge_anchor' in guide:
        from . import duplication_tools
        pitch = duplication_tools.step(guide)
        if not closed:
            span = duplication_tools.distance(guide) + pitch * bool(guide.get('bbe_edge_skip_source'))
            duplication_tools.extend_edge(guide, span)
        curve_tools.refresh(guide)
        return
    if count>1:
        curve_distribution.fill(guide,length,count,guide.bbe_curve)
        guide['bbe_curve_spacing']=length/(count if closed else count-1)
    curve_tools.refresh(guide)
    backend.restore_first_pose(guide,pose)


class BBE_OT_trim_edge(bpy.types.Operator):
    bl_idname='bbe.trim_edge_path'
    bl_label='Trim Edge Path'
    bl_description='Drag either end of the range to keep part of the detected edge. Handles snap to nearby corners'
    bl_options={'REGISTER','UNDO','BLOCKING'}
    track_x:bpy.props.FloatProperty(options={'HIDDEN'})
    track_width:bpy.props.FloatProperty(options={'HIDDEN'})

    def invoke(self,context,event):
        self.guide=curve_tools.active_curve(context)
        if not self.guide or self.guide.get('bbe_repeat_kind')!='EDGE':return {'CANCELLED'}
        try:self.trace=Trace(self.guide)
        except ValueError as exc:
            self.report({'WARNING'},str(exc));return {'CANCELLED'}
        self.old=records(self.guide)
        keys=(SOURCE,RANGE,STAMP,'bbe_edge_tail','bbe_curve_spacing',curve_distribution.KEY)
        self.saved={}
        for key in keys:
            value=self.guide.get(key)
            if hasattr(value,'to_dict'):value=value.to_dict()
            if hasattr(value,'to_list'):value=value.to_list()
            self.saved[key]=value
        self.lo,self.hi=self.trace.limits
        coord=curve_tools.press_position(context,event).mouse_region_x
        self.start_handle=abs(self.fraction(coord)-self.lo)<=abs(self.fraction(coord)-self.hi)
        self.drag(coord)
        if event.type=='LEFTMOUSE' and event.value=='RELEASE':return {'FINISHED'}
        context.window_manager.modal_handler_add(self)
        return {'RUNNING_MODAL'}

    def fraction(self,x):
        return max(0.,min(1.,(x-self.track_x)/max(1.,self.track_width)))

    def drag(self,x):
        value=self.fraction(x)
        lo,hi=self.trace.move_handle(self.lo,self.hi,self.start_handle,value,self.track_width)
        if (lo,hi)!=(self.lo,self.hi):
            trim(self.guide,self.trace,lo,hi)
            self.lo,self.hi=lo,hi

    def cancel(self,context):
        pose=backend.first_pose(self.guide)
        write_spline(self.guide,*self.old)
        for key,value in self.saved.items():
            if value is not None:self.guide[key]=value
            elif key in self.guide:del self.guide[key]
        curve_tools.refresh(self.guide)
        if 'bbe_edge_anchor' not in self.guide:
            backend.restore_first_pose(self.guide,pose)

    def modal(self,context,event):
        if event.type in {'ESC','RIGHTMOUSE'}:
            self.cancel(context);return {'CANCELLED'}
        if event.type=='MOUSEMOVE' or (event.type=='LEFTMOUSE' and event.value=='RELEASE'):
            self.drag(event.mouse_region_x)
        if event.type=='LEFTMOUSE' and event.value=='RELEASE':return {'FINISHED'}
        return {'RUNNING_MODAL'}
