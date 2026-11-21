"""First-party axis and edge repeats, edited through the existing Curve Studio."""
import json
import bpy
from mathutils import Matrix,Vector
from . import builder_geometry_backend as backend,curve_tools,curve_studio,curve_distribution
PREFIX=backend.PREFIX

def props(guide):return getattr(guide,backend.PROPERTY)

def seed_center(sources):
    return backend.seed_center(sources)

def seed_pitch(sources,direction):
    points=[o.matrix_world@Vector(co) for root in sources for o in [root,*root.children_recursive] if o.type=='MESH' for co in o.bound_box]
    values=[p.dot(direction) for p in points]
    return max(.01,max(values)-min(values)) if values else 1.0

def create_axis(context,sources,axis='X',count=3,spacing=None):
    if not sources:raise ValueError('Select the parts to duplicate first')
    unit=Vector(tuple(float(i=='XYZ'.index(axis)) for i in range(3)))
    step=seed_pitch(sources,unit) if spacing is None else max(.001,spacing)
    guide=curve_tools.new_curve(context,'LINE')
    guide.name='BBE Axis Repeat'
    guide['bbe_repeat_kind']='AXIS';guide['bbe_repeat_axis']=axis;guide['bbe_axis_step']=step
    guide.rotation_mode='QUATERNION';guide.rotation_quaternion=Vector((1,0,0)).rotation_difference(unit)
    guide.location=seed_center(sources)+unit*step
    props(guide).width=max(.001,(count-1)*step)
    guide['bbe_curve_spacing']=step
    context.view_layer.update()
    try:backend.make_array(context,guide,sources,count)
    except Exception:
        if guide.name in bpy.data.objects:bpy.data.objects.remove(guide,do_unlink=True)
        raise
    return guide

def finish_edge(context,guide,names):
    sources=[context.scene.objects.get(name) for name in names]
    if not sources or any(o is None for o in sources):raise ValueError('The selected source parts are no longer available')
    guide['bbe_repeat_kind']='EDGE';guide.name='BBE Edge Path Repeat'
    backend.make_array(context,guide,sources,3)
    guide['bbe_curve_spacing']=curve_studio.spacing(guide)
    return guide

def step(guide):
    if curve_distribution.KEY in guide:return curve_distribution.pitch(guide)
    return float(guide['bbe_axis_step']) if 'bbe_axis_step' in guide else curve_studio.spacing(guide)

def distance(guide):
    n=int(guide.get('objects_count',1))
    if n<2:return 0.0
    if curve_distribution.KEY in guide:return curve_distribution.distances(guide,n,props(guide))[-1]
    return (n-1)*(step(guide) if guide.get('bbe_repeat_kind')=='AXIS' else curve_studio.spacing(guide))


def open_edge(guide):
    return bool(guide.get('bbe_repeat_kind')=='EDGE' and guide.data.splines and not guide.data.splines[0].use_cyclic_u)


def extend_edge(guide,required):
    """Keep the traced shape, adding only a straight terminal continuation.

    The saved tip record makes reducing/canceling an extension reversible.
    This is actual guide geometry, so both independent and constraint-based
    followers use the same endpoint tangent without clamping their stations.
    """
    spline=guide.data.splines[0]
    if spline.type!='BEZIER' or len(spline.bezier_points)<2:return
    records=[curve_tools.point_record(bp) for bp in spline.bezier_points]
    state=json.loads(guide.get('bbe_edge_tail','null'))
    if state and state['index']!=len(records)-2:
        # A manual topology edit makes the edited geometry the new path.
        state=None;del guide['bbe_edge_tail']
    base_length=curve_studio.length(guide)
    if state:
        index=state['index'];anchor=Vector(records[index][0])
        base_length-=(guide.matrix_world@Vector(records[-1][0])-guide.matrix_world@anchor).length
        records=records[:index+1]
        saved=state['tip'];offset=anchor-Vector(saved[0])
        records[-1]=(tuple(anchor),tuple(Vector(saved[1])+offset),tuple(Vector(saved[2])+offset),*saved[3:])
    else:index=len(records)-1
    extra=max(0.,required-base_length)
    if extra<1e-4:extra=0.
    if extra<1e-6 and state is None:return
    anchor=Vector(records[-1][0]);tip=records[-1]
    direction=Vector(tip[2])-anchor
    if direction.length<1e-8:direction=anchor-Vector(records[-2][0])
    # Edge traces use vector handles; extrapolate their final straight segment.
    if tip[4]=='VECTOR':direction=anchor-Vector(records[-2][0])
    if direction.length<1e-8:raise ValueError('The edge path needs a nonzero final segment')
    world_direction=(guide.matrix_world.to_3x3()@direction).normalized()
    if extra>1e-6:
        state={'index':index,'tip':tip}
        extension=guide.matrix_world.to_3x3().inverted_safe()@(world_direction*(extra+.001))
        end=anchor+extension
        # Freeze the original tip's incoming handle and make a straight tail.
        records[-1]=(tuple(anchor),tip[1],tuple(anchor+extension/3),'FREE','FREE',tip[5],tip[6])
        records.append((tuple(end),tuple(end-extension/3),tuple(end+extension/3),'FREE','FREE',tip[5],tip[6]))
    curve_tools.own_data(guide)
    spline=guide.data.splines[0];guide.data.splines.remove(spline)
    spline=guide.data.splines.new('BEZIER');spline.bezier_points.add(len(records)-1)
    for bp,record in zip(spline.bezier_points,records):curve_tools.restore_point(bp,record)
    if extra>1e-6:guide['bbe_edge_tail']=json.dumps(state)
    elif 'bbe_edge_tail' in guide:del guide['bbe_edge_tail']
    for key in ('val_data','total_length'):
        if key in guide:del guide[key]
    guide.data.update_tag();guide.update_tag(refresh={'DATA'})


def adjust_edge(guide,field,value):
    if field not in {'objects_count','spacing','distance','radius_multiplier','taper'}:return False
    count=int(guide.get('objects_count',1));size=float(guide.get('radius_multiplier',1));taper=props(guide).taper
    pitch=(curve_distribution.pitch(guide) if curve_distribution.KEY in guide else
           float(guide.get('bbe_curve_spacing',curve_studio.length(guide)/max(1,count-1))))
    if field=='objects_count':count=max(1,min(1000,round(value)))
    elif field=='spacing':pitch=max(.001,value)
    elif field=='distance':
        if count<2:return True
        pitch=max(.001,value)/((count-1)*(1-taper/200 if curve_distribution.KEY in guide else 1))
    elif field=='radius_multiplier':
        if curve_distribution.KEY in guide:pitch*=max(.001,value)/max(.001,size)
        size=max(.001,value)
    elif field=='taper':taper=max(0,min(99,value))
    required=max(0,count-1)*pitch*(1-taper/200 if curve_distribution.KEY in guide or taper>0 else 1)
    # Enlarge before assigning properties whose update callbacks enforce capacity.
    # Shrinking afterward avoids callbacks squeezing the old larger count first.
    old_length=curve_studio.length(guide)
    extend_edge(guide,max(old_length,required))
    guide['bbe_curve_spacing']=pitch
    if curve_distribution.KEY in guide:
        # set_pitch uses the current size; rebuilding installs the requested size.
        curve_distribution.set_pitch(guide,pitch*float(guide.get('radius_multiplier',1))/size)
    if field=='taper':props(guide).taper=taper
    backend.rebuild(guide,count,size)
    extend_edge(guide,required)
    curve_tools.refresh(guide)
    return True


def adjust(guide,field,value):
    if open_edge(guide):return adjust_edge(guide,field,value)
    kind=guide.get('bbe_repeat_kind')
    if not kind:return False
    count=int(guide.get('objects_count',1))
    if kind=='EDGE':
        if field!='distance':return False
        if count<2:return True
        factor=(count-1)*(1-props(guide).taper/200 if curve_distribution.KEY in guide else 1)
        curve_studio.set_spacing(guide,max(.001,value)/factor);return True
    if field not in {'objects_count','spacing','distance'}:return False
    spacing=step(guide)
    if field=='objects_count':count=max(1,min(1000,round(value)))
    elif field=='spacing':spacing=max(.001,value)
    elif count>1:
        spacing=max(.001,value)/((count-1)*(1-props(guide).taper/200 if curve_distribution.KEY in guide else 1))
    else:return True
    old_step=step(guide)
    direction=(guide.matrix_world.to_3x3()@Vector((1,0,0))).normalized()
    matrix=guide.matrix_world.copy();matrix.translation+=direction*(spacing-old_step);guide.matrix_world=matrix
    guide['bbe_axis_step']=spacing;guide['bbe_curve_spacing']=spacing
    if curve_distribution.KEY in guide:curve_distribution.set_pitch(guide,spacing)
    # Set the guide geometry before increasing count, so capacity does not cap it.
    props(guide).width=max(.001,(count-1)*spacing)/max(1e-8,abs(guide.matrix_world.to_scale().x))
    backend.rebuild(guide,count,float(guide.get('radius_multiplier',1)))
    curve_tools.refresh(guide)
    return True

def change_axis(guide,axis):
    if guide.get('bbe_repeat_kind')!='AXIS':raise ValueError('Select an axis repeat')
    old=(guide.matrix_world.to_3x3()@Vector((1,0,0))).normalized()
    unit=Vector(tuple(float(i=='XYZ'.index(axis)) for i in range(3)))
    spacing=step(guide);origin=guide.matrix_world.translation-old*spacing
    rotation=old.rotation_difference(unit).to_matrix().to_4x4()
    guide.matrix_world=Matrix.Translation(origin)@rotation@Matrix.Translation(-origin)@guide.matrix_world
    guide['bbe_repeat_axis']=axis;curve_tools.refresh(guide)

class BBE_OT_duplicate_axis(bpy.types.Operator):
    bl_idname=PREFIX+'.duplicate_axis';bl_label='Duplicate Along Axis';bl_options={'REGISTER','UNDO'}
    bl_description='Repeat the selected parts along a world axis, then adjust copies, spacing and distance in Curve Studio'
    axis:bpy.props.EnumProperty(items=[(a,a,'World '+a+' axis') for a in 'XYZ'],default='X')
    count:bpy.props.IntProperty(default=3,min=1,max=1000)
    @classmethod
    def poll(cls,context):return context.mode=='OBJECT' and bool(backend.selection(context))
    def execute(self,context):
        try:create_axis(context,backend.selection(context),self.axis,self.count)
        except (ValueError,RuntimeError) as exc:self.report({'ERROR'},str(exc));return {'CANCELLED'}
        return {'FINISHED'}

class BBE_OT_repeat_axis(bpy.types.Operator):
    bl_idname=PREFIX+'.repeat_axis';bl_label='Repeat Axis';bl_options={'REGISTER','UNDO'}
    axis:bpy.props.EnumProperty(items=[(a,a,'World '+a+' axis') for a in 'XYZ'],default='X')
    def execute(self,context):
        guide=curve_tools.active_curve(context)
        if guide is None:return {'CANCELLED'}
        change_axis(guide,self.axis);return {'FINISHED'}

class BBE_OT_duplicate_edge_path(bpy.types.Operator):
    bl_idname=PREFIX+'.duplicate_edge_path';bl_label='Duplicate Along Edge Path';bl_options={'REGISTER','UNDO'}
    bl_description='Select the parts to copy, then use the edge selector to choose one continuous path; Enter opens the repeat controls'
    @classmethod
    def poll(cls,context):return context.mode=='OBJECT' and bool(backend.selection(context))
    def invoke(self,context,event):
        result=getattr(bpy.ops,PREFIX).curve_from_surface('INVOKE_DEFAULT',purpose='DUPLICATE',repeat_sources=json.dumps([o.name for o in backend.selection(context)]))
        return {'FINISHED'} if result=={'RUNNING_MODAL'} else result

CLASSES=(BBE_OT_duplicate_axis,BBE_OT_repeat_axis,BBE_OT_duplicate_edge_path)
def register():
    for cls in CLASSES:bpy.utils.register_class(cls)
def unregister():
    for cls in reversed(CLASSES):bpy.utils.unregister_class(cls)
