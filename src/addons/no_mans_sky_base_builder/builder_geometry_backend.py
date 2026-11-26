"""Regular BBE bindings for first-party duplication and alignment tools."""
import bpy
from mathutils import Quaternion
from . import curve_links
from . import curve_tools,curve_studio
from .utils import curve
PREFIX='bbe'
PROPERTY='bbe_curve'

def ancestors(obj):
    while obj.parent:
        obj=obj.parent;yield obj

def selection(context):
    selected=[o for o in context.selected_objects if ('ObjectID' in o or 'GroupID' in o) and 'bbeplus_part_json' not in o]
    return [o for o in selected if not any(p in selected for p in ancestors(o))]

def owner(obj,selected=()):
    chain=[obj,*ancestors(obj)]
    grouped=next((p for p in reversed(chain) if p in selected and 'GroupID' in p),None)
    return grouped or next((p for p in chain if 'ObjectID' in p),obj)

def make_array(context,guide,sources,count):
    # Grouping the temporary seed set must not reparent the user's originals.
    originals=set(bpy.data.objects);copies={}
    try:
        for source in dict.fromkeys(o for root in sources for o in [root,*root.children_recursive]):
            clone=source.copy();context.scene.collection.objects.link(clone);copies[source]=clone
        for source,clone in copies.items():
            clone.parent=copies.get(source.parent);clone.matrix_world=source.matrix_world.copy()
        curve_studio.choose(context,[*(copies[o] for o in sources),guide]);context.view_layer.objects.active=guide
        # The grouping operation uses a world-aligned frame for multiple seeds.
        seed_rotation = sources[0].matrix_world.to_quaternion().normalized() if len(sources)==1 else Quaternion()
        result=context.scene.nms_build_tool.duplicate_along_curve(count,1)
        if result=={'CANCELLED'} or not curve_links.has_followers(guide):raise ValueError('Could not duplicate the selected BBE parts')
    finally:
        followers=curve.get_all_curve_children(guide) or []
        keep={guide,*followers,*(child for obj in followers for child in obj.children_recursive)}
        transient=[o for o in bpy.data.objects if o not in originals and o not in keep and (o in copies.values() or 'GroupID' in o)]
        if transient:bpy.data.batch_remove(transient)
    pose=first_pose(guide)
    if pose and abs(pose[1].dot(seed_rotation))<1.-1e-7:
        restore_first_pose(guide,(pose[0],seed_rotation))
    curve_studio.select_children(context,guide)

def first_pose(guide):
    followers = children(guide)
    if not followers or curve.Curve.PROP_START_ALIGNMENT not in guide:
        return None
    tracked = [(c.offset_factor, obj) for obj in followers for c in obj.constraints
               if c.type == 'FOLLOW_PATH' and c.target == guide]
    if not tracked:
        return None
    first = min(tracked, key=lambda entry: entry[0])[1]
    bpy.context.view_layer.update()
    return first, first.matrix_world.to_quaternion().normalized()


def restore_first_pose(guide, pose):
    if pose is None:
        return
    first, desired = pose
    bpy.context.view_layer.update()
    local = first.rotation_euler.to_quaternion()
    frame = first.matrix_world.to_quaternion().normalized() @ local.inverted()
    correction = frame.inverted() @ desired @ local.inverted()
    key = curve.Curve.PROP_START_ALIGNMENT
    guide[key] = list(correction @ Quaternion(guide[key]))
    for child in children(guide):
        child.rotation_euler = (correction @ child.rotation_euler.to_quaternion()).to_euler('XYZ', child.rotation_euler)


def rebuild(guide,count,size):
    from .utils import curve_utils
    guide['density_step']=curve_utils.get_total_curve_density(guide,count)/max(1,count-1)
    old=guide.get('parent_selected',True);guide['parent_selected']=True
    try:curve.duplicate_along_curve(None,guide,count,size)
    finally:guide['parent_selected']=old
    bpy.context.scene.nms_properties.show_curve_edit_options(guide)
    curve_studio.select_children(bpy.context,guide)

def children(guide):return curve.get_all_curve_children(guide) or []


def seed_center(sources):
    from mathutils import Vector
    return sum((o.matrix_world.translation for o in sources),Vector())/len(sources)
