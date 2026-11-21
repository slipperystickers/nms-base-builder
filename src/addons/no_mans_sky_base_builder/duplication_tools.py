"""First-party axis and edge repeats, edited through the existing Curve Studio."""
import json
import bpy
from mathutils import Matrix, Quaternion, Vector
from . import builder_geometry_backend as backend,curve_tools,curve_studio,curve_distribution
PREFIX=backend.PREFIX

def props(guide):return getattr(guide,backend.PROPERTY)

def seed_center(sources):
    return backend.seed_center(sources)

def seed_pitch(sources,direction):
    points=[o.matrix_world@Vector(co) for root in sources for o in [root,*root.children_recursive] if o.type=='MESH' for co in o.bound_box]
    values=[p.dot(direction) for p in points]
    return max(.01,max(values)-min(values)) if values else 1.0

def create_axis(context,sources,axis='X',count=3,spacing=None,space='GLOBAL'):
    if not sources:raise ValueError('Select the parts to duplicate first')
    unit=Vector(tuple(float(i=='XYZ'.index(axis)) for i in range(3)))
    reference=context.view_layer.objects.active
    if reference not in sources:reference=sources[0]
    basis=reference.matrix_world.to_quaternion().normalized()
    if space=='LOCAL':unit=basis @ unit
    step=seed_pitch(sources,unit) if spacing is None else max(.001,spacing)
    guide=curve_tools.new_curve(context,'LINE')
    guide.name='BBE Axis Repeat'
    guide['bbe_axis_basis']=list(basis)
    guide['bbe_axis_space']=space
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

def matching_edge(obj, target, start, direction):
    """Locate a corresponding contact on the copy when picking another part."""
    import numpy as np

    local = target.matrix_world.inverted_safe() @ start
    if obj.data == target.data:
        local_heading = target.matrix_world.to_3x3().inverted_safe() @ direction
        return obj.matrix_world @ local, (obj.matrix_world.to_3x3() @ local_heading).normalized()

    def bounds(part):
        box = np.asarray(part.bound_box)
        return box.min(axis=0), np.maximum(box.max(axis=0) - box.min(axis=0), 1e-9)

    low, extent = bounds(target)
    fraction = (np.asarray(local) - low) / extent
    low, extent = bounds(obj)
    reference = obj.matrix_world @ Vector(low + fraction * extent)
    mesh = obj.data
    vertices = np.empty((len(mesh.vertices), 3), dtype=np.float32)
    indices = np.empty((len(mesh.edges), 2), dtype=np.int32)
    mesh.vertices.foreach_get('co', vertices.ravel())
    mesh.edges.foreach_get('vertices', indices.ravel())
    matrix = np.asarray(obj.matrix_world)
    vertices = vertices @ matrix[:3, :3].T + matrix[:3, 3]
    starts = vertices[indices[:, 0]]
    spans = vertices[indices[:, 1]] - starts
    lengths = np.linalg.norm(spans, axis=1)
    units = spans / np.maximum(lengths[:, None], 1e-12)
    alignment = units @ np.asarray(direction)
    candidates = (lengths > 1e-7) & (np.abs(alignment) >= np.abs(alignment).max() - .0002)
    if not candidates.any():
        raise ValueError('The selected part has no usable edge to repeat.')
    along = np.clip(np.einsum('ij,ij->i', np.asarray(reference) - starts, units), 0, lengths)
    points = starts + units * along[:, None]
    distances = np.linalg.norm(points - np.asarray(reference), axis=1)
    index = int(np.argmin(np.where(candidates, distances, np.inf)))
    return Vector(points[index]), Vector(units[index] if alignment[index] >= 0 else -units[index])


def edge_contact(context, guide, sources, traced):
    context.view_layer.update()
    points = guide.data.splines[0].bezier_points
    start = guide.matrix_world @ points[0].co
    direction = (guide.matrix_world.to_3x3() @ (points[1].co - points[0].co)).normalized()
    on_source = any(root == traced or root in backend.ancestors(traced) for root in sources)
    seed_frame = sources[0].matrix_world if len(sources) == 1 else Matrix.Translation(seed_center(sources))
    contact, heading = start, direction
    if not on_source:
        meshes = (obj for root in sources for obj in (root, *root.children_recursive)
                  if obj.type == 'MESH' and obj.data.edges)
        reference = min(meshes, key=lambda obj: (obj.matrix_world.translation - start).length_squared,
                        default=None)
        if reference is None:
            raise ValueError('Select a building part with a mesh edge to repeat.')
        contact, heading = matching_edge(reference, traced, start, direction)
    return seed_frame.inverted_safe() @ contact, on_source, heading, direction


def edge_pitch(sources, direction):
    """Measure the occupied width along the picked edge, including rotated parts."""
    import numpy as np

    low, high = float('inf'), -float('inf')
    for root in sources:
        for obj in (root, *root.children_recursive):
            if obj.type != 'MESH' or not obj.data.vertices:
                continue
            matrix = obj.matrix_world
            axis = matrix.to_3x3().transposed() @ direction
            origin = matrix.translation.dot(direction)
            vertices = np.empty((len(obj.data.vertices), 3), dtype=np.float32)
            obj.data.vertices.foreach_get('co', vertices.ravel())
            projections = vertices @ np.asarray(axis, dtype=np.float32)
            low = min(low, origin + float(projections.min()))
            high = max(high, origin + float(projections.max()))
    return max(.01, high - low) if high >= low else 1.


def anchor_repeat(guide, sources, contact):
    anchor, on_source, heading, direction = contact
    if not on_source:
        pose = backend.first_pose(guide)
        if pose:
            backend.restore_first_pose(guide, (pose[0], heading.rotation_difference(direction) @ pose[1]))
    guide['bbe_edge_anchor'] = list(anchor)
    guide['bbe_edge_skip_source'] = on_source
    count = int(guide['objects_count'])
    if open_edge(guide):
        pitch = edge_pitch(sources, heading)
        extend_edge(guide, (count - 1 + int(on_source)) * pitch)
    else:
        pitch = curve_studio.length(guide) / (count + int(on_source))
    guide['bbe_curve_spacing'] = pitch
    curve_tools.refresh(guide)


def finish_edge(context,guide,names,limits=(0.,1.),traced=None):
    sources=[context.scene.objects.get(name) for name in names]
    if not sources or any(o is None for o in sources):raise ValueError('The selected source parts are no longer available')
    guide['bbe_repeat_kind']='EDGE';guide.name='BBE Edge Path Repeat'
    if limits!=(0.,1.):
        from . import edge_trim
        context.view_layer.update()
        curve_studio.prepare_frame(guide)
        context.view_layer.update()
        edge_trim.trim(guide,edge_trim.Trace(guide),*limits)
    try:
        contact = edge_contact(context, guide, sources, traced) if traced is not None else None
    except ValueError:
        bpy.data.objects.remove(guide, do_unlink=True)
        curve_studio.choose(context, sources)
        raise
    backend.make_array(context,guide,sources,3)
    if contact is None:guide['bbe_curve_spacing']=curve_studio.spacing(guide)
    else:anchor_repeat(guide,sources,contact)
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
    # Only the incoming geometry belongs to the retained path. Its unused
    # outgoing handle (or a float-sized leftover bevel) can point anywhere.
    world=guide.matrix_world.to_3x3()
    tolerance=max(1e-8,abs(base_length)*1e-6)
    direction=Vector((0.,0.,0.))
    for previous in reversed(records[:-1]):
        chord=anchor-Vector(previous[0])
        if (world @ chord).length<=tolerance:continue
        incoming=anchor-Vector(tip[1])
        direction=incoming if previous is records[-2] and tip[3]!='VECTOR' and (world @ incoming).length>tolerance else chord
        break
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


def fill_edge(guide):
    # A projected tail provides room for more copies. Fill only the picked portion.
    length = curve_studio.length(guide)
    spline = guide.data.splines[0]
    if 'bbe_edge_tail' in guide:
        points = spline.bezier_points
        length -= (guide.matrix_world.to_3x3() @ (points[-1].co - points[-2].co)).length
    count = int(guide['objects_count'])
    average = 1 - props(guide).taper / 200 if curve_distribution.KEY in guide else 1
    intervals = (count - 1 + int(spline.use_cyclic_u)) * average + bool(guide.get('bbe_edge_skip_source'))
    if intervals:
        curve_studio.set_spacing(guide, length / intervals)


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
    if guide.get('bbe_edge_skip_source'):required+=pitch
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

def change_axis(guide,axis,space=None):
    if guide.get('bbe_repeat_kind')!='AXIS':raise ValueError('Select an axis repeat')
    old=(guide.matrix_world.to_3x3()@Vector((1,0,0))).normalized()
    unit=Vector(tuple(float(i=='XYZ'.index(axis)) for i in range(3)))
    pose=backend.first_pose(guide)
    if 'bbe_axis_basis' not in guide:
        guide['bbe_axis_basis']=list(pose[1] if pose else guide.matrix_world.to_quaternion())
    space=space or guide.get('bbe_axis_space','GLOBAL')
    if space=='LOCAL':unit=Quaternion(guide['bbe_axis_basis']) @ unit
    spacing=step(guide);origin=guide.matrix_world.translation-old*spacing
    rotation=old.rotation_difference(unit).to_matrix().to_4x4()
    guide.matrix_world=Matrix.Translation(origin)@rotation@Matrix.Translation(-origin)@guide.matrix_world
    guide['bbe_repeat_axis']=axis;guide['bbe_axis_space']=space
    curve_tools.refresh(guide)
    backend.restore_first_pose(guide,pose)

class BBE_OT_duplicate_axis(bpy.types.Operator):
    bl_idname=PREFIX+'.duplicate_axis';bl_label='Duplicate Along Axis';bl_options={'REGISTER','UNDO'}
    bl_description='Repeat the selected parts along a world axis, then adjust copies, spacing and distance in the axis controls'
    axis:bpy.props.EnumProperty(items=[(a,a,a+' axis') for a in 'XYZ'],default='X',options={'SKIP_SAVE'})
    space:bpy.props.EnumProperty(name="Axis space",items=[("GLOBAL","Global","Use world axes"),("LOCAL","Part Local","Use the active selected part's axes")],default="GLOBAL",options={'SKIP_SAVE'})
    count:bpy.props.IntProperty(default=3,min=1,max=1000)
    @classmethod
    def poll(cls,context):return context.mode=='OBJECT' and bool(backend.selection(context))
    def execute(self,context):
        try:create_axis(context,backend.selection(context),self.axis,self.count,space=self.space)
        except (ValueError,RuntimeError) as exc:self.report({'ERROR'},str(exc));return {'CANCELLED'}
        return {'FINISHED'}

class BBE_OT_repeat_axis(bpy.types.Operator):
    bl_idname=PREFIX+'.repeat_axis';bl_label='Repeat Axis';bl_options={'REGISTER','UNDO'}
    axis:bpy.props.EnumProperty(items=[(a,a,a+' axis') for a in 'XYZ'],default='X',options={'SKIP_SAVE'})
    space:bpy.props.EnumProperty(items=[('KEEP','Current',''),('GLOBAL','Global',''),('LOCAL','Part Local','')],default='KEEP',options={'SKIP_SAVE'})
    def execute(self,context):
        guide=curve_tools.active_curve(context)
        if guide is None:return {'CANCELLED'}
        if self.space=='KEEP':change_axis(guide,self.axis)
        else:change_axis(guide,guide.get('bbe_repeat_axis','X'),self.space)
        return {'FINISHED'}

class BBE_OT_duplicate_edge_path(bpy.types.Operator):
    bl_idname=PREFIX+'.duplicate_edge_path';bl_label='Duplicate Along Edge Path';bl_options={'REGISTER','UNDO'}
    bl_description='Select the parts to copy, then use the edge selector to choose one continuous path; Enter opens the repeat controls'
    @classmethod
    def poll(cls,context):return context.mode=='OBJECT' and bool(backend.selection(context))
    def invoke(self,context,event):
        result=getattr(bpy.ops,PREFIX).curve_from_surface('INVOKE_DEFAULT',purpose='DUPLICATE',repeat_sources=json.dumps([o.name for o in backend.selection(context)]))
        return {'FINISHED'} if result=={'RUNNING_MODAL'} else result

from .edge_trim import BBE_OT_trim_edge

CLASSES=(BBE_OT_trim_edge,BBE_OT_duplicate_axis,BBE_OT_repeat_axis,BBE_OT_duplicate_edge_path)
def register():
    for cls in CLASSES:bpy.utils.register_class(cls)
def unregister():
    for cls in reversed(CLASSES):bpy.utils.unregister_class(cls)
