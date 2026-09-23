import json
import math
import os
import uuid
import random

import bpy

from .. import builder, builder_v2, part
from . import (blend_utils, collection_utils, curve_utils, material,
               materials_v2, mirror_utils)
from . import dictionary
from ..group import Group
from ..part import Part

BUILDER = builder.Builder()

nice_name_dictionary = dictionary.get_nice_names_diictionary()


class Curve:
    
    """Curve property names."""
    PROP_HAS_LINKED_OBJECTS = "has_linked_objects"
    PROP_RADIUS_MULTIPLIER = "radius_multiplier"
    PROP_INITIAL_CURVE_SCALE = "initial_curve_scale"
    PROP_OBJECTS_COUNT = "objects_count"
    PROP_CURVE_ID = "CurveID"
    PROP_PARENT_SELECTED = "parent_selected"
    PROP_CURVE_PARENT = "curve_parent"
    PROP_BASE_SCALE = "base_scale"
    PROP_CURVE_FACTOR = "base_scale"
    PROP_IS_INITIALISED = "is_initialised"
    PROP_DENSITY_STEP = "density_step"
    PROP_RADIUS = "radius"

    # Duplicated object data
    PROP_DUP_OBJECT_ID = f"dup_{Part.PROP_OBJECT_ID}"
    PROP_DUP_USER_DATA = f"dup_{Part.PROP_USER_DATA}"
    # Duplicated group data
    PROP_DUP_GROUP_ID = f"dup_{Group.PROP_GROUP_ID}"
    PROP_DUP_IS_GROUP = "is_group"
    PROP_GROUP_CHILD_CACHE = f"dup_{Group.PROP_CHILD_CACHE}"
    PROP_ORIGIN_MATRIX = f"dupe_{Group.PROP_ORIGIN_MATRIX}"
    
    def __init__(self):
        """Initialize the Curve manager."""
        pass


def get_follower_objects():
    """Everything in the file that could be following a curve.

    add_objects_to_curve drops every follower it makes into one collection, and
    move_object_into_collection unlinks them from everywhere else, so that
    collection is the complete list. Looking there instead of at the whole scene
    is the difference between walking 60 objects and walking 5000 - the scene
    scan on its own was 2.4 ms, and dragging a slider pays it every frame.

    The one-shot operations further down (locking, selecting, detaching) still
    walk the scene. They run once on a click, so the wider net costs nothing and
    catches anything that ended up outside the collection by hand.
    """
    collection = bpy.data.collections.get(collection_utils.LINKED_CURVE_OBJ_COL)
    if collection is None:
        # nothing has ever been put on a curve in this file
        return bpy.context.scene.objects
    return collection.objects


def get_curve_children_map(objects=None):
    """Group every curve follower by the curve it belongs to, in ONE pass.

    update_curve_children otherwise scans once per curve. Building this map costs
    a single pass no matter how many curves are being rebuilt.

    Args:
        objects (iterable): Objects to scan. Defaults to the follower collection.

    Returns:
        dict: {curve name: [child objects]}
    """
    objects = objects if objects is not None else get_follower_objects()

    children_by_curve = {}
    for obj in objects:
        parent_name = obj.get(Curve.PROP_CURVE_PARENT)
        if parent_name is not None:
            children_by_curve.setdefault(parent_name, []).append(obj)
    return children_by_curve


def update_curves(updated_curves, children_by_curve=None):
    if not updated_curves:
        return

    scene = bpy.context.scene
    properties = scene.nms_properties
    
    # Calculate relative changes (deltas)
    count_delta = properties.active_curve_number_of_objects - properties.prev_curve_number_of_objects
    radius_delta = properties.active_curve_radius_multiplier - properties.prev_curve_radius_multiplier
    
    for curve_obj in updated_curves:
        if curve_obj is None or Curve.PROP_CURVE_ID not in curve_obj:
            continue
        
        try:
            # Get current values for this specific curve
            current_count = curve_obj.get(Curve.PROP_OBJECTS_COUNT, 0)
            current_radius = curve_obj.get(Curve.PROP_RADIUS_MULTIPLIER, 1.0)
            
            new_number_of_objects = max(1, current_count + count_delta)
            new_radius_multiplier = max(0.001, current_radius + radius_delta)  # Prevent zero or negative radius
            
            # Compute total density to dynamically handle weight changes
            total_density = curve_utils.get_total_curve_density(curve_obj, current_count)
            
            # Adjust count vs density step
            if count_delta != 0 or Curve.PROP_DENSITY_STEP not in curve_obj:
                # User changed count manually via UI, store the new density step
                denom = max(1, new_number_of_objects - 1)
                curve_obj[Curve.PROP_DENSITY_STEP] = total_density / denom
            else:
                # Weight changed (no UI count change), dynamically calculate new object count to maintain spacing
                density_step = curve_obj[Curve.PROP_DENSITY_STEP]
                # One follower has no spacing interval. Do not turn the
                # denominator fallback above into an unwanted second object.
                if density_step > 0 and current_count > 1:
                    new_number_of_objects = max(1, int(round((total_density / density_step) + 1)))
                    # Update UI property so it doesn't get out of sync if this is the active curve
                    if bpy.context.active_object == curve_obj:
                        properties.active_curve_number_of_objects = new_number_of_objects
            
            objects_count_changed = new_number_of_objects != current_count

            children = (
                children_by_curve.get(curve_obj.name)
                if children_by_curve is not None else None
            )

            # Update object counts
            if objects_count_changed:
                # This adds or removes followers and reflows what is left on the
                # way out, so the curve is already finished - it used to be sent
                # through update_curve_children a second time with the same
                # arguments, doing the whole rebuild twice.
                duplicate_along_curve(
                    None, curve_obj, new_number_of_objects, new_radius_multiplier,
                    existing_objs=children
                )
                curve_obj[Curve.PROP_OBJECTS_COUNT] = new_number_of_objects
                continue

            # Update children
            update_curve_children(curve_obj, new_radius_multiplier, children)

        except ReferenceError as error:
            print(error)
            continue
            
    # Save states for the next change
    properties.prev_curve_number_of_objects = properties.active_curve_number_of_objects
    properties.prev_curve_radius_multiplier = properties.active_curve_radius_multiplier

# update children on curve
def update_curve_children(curve_obj, new_radius_multier = None, curve_children = None):
    """Refreshes transformations for all objects assigned to this curve."""
    if not curve_obj.get(Curve.PROP_HAS_LINKED_OBJECTS):
        return
    
    val_data = curve_obj.get("val_data",None)
    total_length = curve_obj.get("total_length",None)
    if val_data is None:
        val_data, total_length = curve_utils.build_curve_eval_data(curve_obj, resolution=16)
    
    if new_radius_multier is not None:
        curve_obj[Curve.PROP_RADIUS_MULTIPLIER] = new_radius_multier
    
    if curve_children is None:
        # no prebuilt map handed in, so fall back to scanning for this one curve
        children = [obj for obj in get_follower_objects()
                    if obj.get(Curve.PROP_CURVE_PARENT) == curve_obj.name]
    else:
        children = curve_children

    if not children:
        return
        
    curve_utils.calculate_curve_factors(curve_obj, children)
    # the curve's own scale and multipliers are the same for every child, so
    # they get read here rather than once per object down in the loop
    curve_context = curve_utils.build_curve_context(curve_obj)
    curve_name = curve_obj.name
    for obj in children:
        if obj.get("curve_parent") == curve_name:
            curve_utils.update_obj_transformations(
                obj, curve_obj, val_data, total_length, curve_context
            )
            

def duplicate_along_curve( bpy_object, curve, number_of_duplicates=10, radius_multiplier=1.0, existing_objs=None):
    # Persist the requested count before a depsgraph update can rebuild this
    # curve. Without it the update handler treats a new curve as zero objects.
    curve[Curve.PROP_OBJECTS_COUNT] = number_of_duplicates

    if curve.get(Curve.PROP_HAS_LINKED_OBJECTS, False):
        curve_utils.normalise_curve_scale(curve)
    
    if not curve.get(Curve.PROP_IS_INITIALISED, False):
        curve_utils.half_the_weight_points(curve)
        curve[Curve.PROP_IS_INITIALISED] = True
        
    curve[Curve.PROP_HAS_LINKED_OBJECTS] = True
    curve[Curve.PROP_RADIUS_MULTIPLIER] = radius_multiplier
    
    if Curve.PROP_INITIAL_CURVE_SCALE not in curve:
        curve[Curve.PROP_INITIAL_CURVE_SCALE] = curve.scale.x
    
    if bpy_object is not None:
        if "GroupID" in bpy_object:
            curve[Curve.PROP_DUP_GROUP_ID] = bpy_object[Group.PROP_GROUP_ID]
            curve[Curve.PROP_DUP_IS_GROUP] = True
            curve[Curve.PROP_GROUP_CHILD_CACHE] = bpy_object[Group.PROP_CHILD_CACHE]
            curve[Curve.PROP_ORIGIN_MATRIX] = bpy_object[Group.PROP_ORIGIN_MATRIX]
        else:
            curve[Curve.PROP_DUP_OBJECT_ID] = bpy_object["ObjectID"]
            curve[Curve.PROP_DUP_USER_DATA] = bpy_object["UserData"]
            curve[Curve.PROP_DUP_IS_GROUP] = False
        
    
    # Gather all bpy_objects currently following this curve. A caller that has
    # already grouped the whole scene by curve can hand its list in and skip the
    # scan, which is 2.7 ms on a 5000 part base.
    if existing_objs is None:
        existing_objs = get_all_curve_children(curve)
    if existing_objs is None:
        existing_objs = []
    current_count = len(existing_objs)
    
    # here we check if number of objects needed on curve are more or less than previously duplicated objects.
    # if number objects previously duplicated is more than what we need on curve, we remove extra objects
    if number_of_duplicates < current_count:
        remove_count = current_count - number_of_duplicates
        removeobjects_from_curve(remove_count, existing_objs)
                
    # Add additional obejcts if needed to reach desired number of objects
    elif number_of_duplicates > current_count:
        add_count = number_of_duplicates - current_count
        add_objects_to_curve(add_count,curve, existing_objs,bpy_object)

    update_curve_children(curve, radius_multiplier, existing_objs)
    return existing_objs

def removeobjects_from_curve(number_to_remove, existing_objs):
    """Take the last few followers back off the curve.

    bpy.data.objects.remove costs about 4 ms a call on a big scene because each
    one re-syncs the whole thing. batch_remove does the lot in a single pass -
    dropping 60 objects went from 256 ms to 12 ms - which is what made the count
    slider stutter on the way down.
    """
    if number_to_remove <= 0:
        return

    # trim off the tail, keeping the order of what is left
    keep_count = max(0, len(existing_objs) - number_to_remove)
    doomed = existing_objs[keep_count:]
    del existing_objs[keep_count:]

    if doomed:
        bpy.data.batch_remove(doomed)

def add_objects_to_curve(number_to_add, curve, existing_objs, bpy_object = None):
    linked_curve_obj_col = collection_utils.get_collection(collection_utils.LINKED_CURVE_OBJ_COL)
    for _ in range(number_to_add):
        if len(existing_objs) == 0:
            if bpy_object is not None:
                new_obj = bpy_object.copy()
                # An fbx proxy keeps its colour on the mesh's material, so it
                # needs its own copy - otherwise recolouring the curve would
                # recolour whatever object was picked to seed it. A high res
                # part keeps its colour on the object, so it can stay on the one
                # shared library mesh and every curve made this way stops adding
                # another copy of it to the file.
                if not materials_v2.is_high_res(bpy_object):
                    new_obj.data = bpy_object.data.copy()
                for constraint in list(new_obj.constraints):
                    new_obj.constraints.remove(constraint)
                    
                if curve[Curve.PROP_DUP_IS_GROUP] is True:
                    new_obj[Group.PROP_GROUP_ID] = curve[Curve.PROP_DUP_GROUP_ID]
                    if Curve.PROP_DUP_USER_DATA in curve:
                        new_obj[Part.PROP_USER_DATA] = curve[Curve.PROP_DUP_USER_DATA] 
            else:
                if curve[Curve.PROP_DUP_IS_GROUP] is True:
                    child_cache = curve[Curve.PROP_GROUP_CHILD_CACHE]
                    origin_matrix = Group.str_to_matrix(curve[Curve.PROP_ORIGIN_MATRIX])
                    if origin_matrix is None:
                        origin_matrix = Group.get_default_origin_matrix()
                    
                    new_obj = Group.deserialise_to_group(BUILDER, child_cache, origin_matrix)
                    new_obj[Group.PROP_GROUP_ID] = curve[Curve.PROP_DUP_GROUP_ID]
                    
                    if Curve.PROP_DUP_USER_DATA in curve:
                        new_obj[Part.PROP_USER_DATA] = curve[Curve.PROP_DUP_USER_DATA]
                    
                else:
                    object_id = curve[Curve.PROP_DUP_OBJECT_ID]
                    user_data = curve[Curve.PROP_DUP_USER_DATA]
                    new_item = builder_v2.add_part(
                        object_id, user_data=user_data, builder_object=BUILDER
                    )
                    new_obj = new_item.object
                    
            if Curve.PROP_DUP_USER_DATA in curve:    
                material.restore_material(new_obj, curve[Curve.PROP_DUP_USER_DATA])
                
            constraint = new_obj.constraints.new(type='FOLLOW_PATH')
            constraint.target = curve
            constraint.use_fixed_location = True
            constraint.use_curve_follow = True
            
            new_obj[Curve.PROP_CURVE_PARENT] = curve.name
            new_obj[Curve.PROP_BASE_SCALE] = 1.0
            new_obj.rotation_euler = (math.pi,0,0)
            new_obj.location = (0,0,0)
            new_obj.hide_select = True
            
            collection_utils.move_object_into_collection(linked_curve_obj_col, new_obj)
            
        else :
            new_obj = existing_objs[-1].copy()
            new_obj[Curve.PROP_CURVE_PARENT] = curve.name
            linked_curve_obj_col.objects.link(new_obj)
            
        existing_objs.append(new_obj)


# check if given object is a supported curve or not
def is_bezier_or_nurbs_path(curve):
    if not curve or curve.type != 'CURVE':
        return False
    for spline in curve.data.splines:
        if spline.type in {'BEZIER', 'NURBS'}:
            return True
    return False

        
def apply_curve_transforms_and_detach(curve):
    """
    Bakes the visual transforms created by the FOLLOW_PATH constraint into actual 
    loc/rot/scale data, then deletes the constraint so objects stay in place.
    """
    if not is_bezier_or_nurbs_path(curve):
        raise TypeError("Please provide a valid curve object.")
    
    detached_count = 0
    duplicates = []
    
    # Force Blender to evaluate the scene tree. 
    # If we don't do this, 'obj.matrix_world' might return stale data from before 
    bpy.context.view_layer.update()
    
    unlinked_curve_obj_col = collection_utils.get_collection(collection_utils.UNLINKED_CURVE_OBJ_COL)
    
    child_props_to_delete = [
        Curve.PROP_BASE_SCALE,
        Curve.PROP_CURVE_FACTOR,
        Curve.PROP_RADIUS,
        Curve.PROP_CURVE_PARENT
    ]
    
    for obj in bpy.context.scene.objects:
        if obj.get("curve_parent") == curve.name:
            
            
            # Clean up custom properties
            for prop in child_props_to_delete:
                if prop in obj:
                    del obj[prop]
            
            # Capture the exact 3D space matrix dictated by the constraint
            baked_matrix = obj.matrix_world.copy()
            
            constraints_to_remove = [c for c in obj.constraints if c.type == 'FOLLOW_PATH' and c.target == curve]
            if constraints_to_remove:
                for c in constraints_to_remove:
                    obj.constraints.remove(c)
                    
            # Re-apply the matrix so the object doesn't physically move when the constraint drops
            obj.matrix_world = baked_matrix
            detached_count += 1
            
            #obj.data = obj.data.copy()
            obj.hide_select = False
            obj.lock_location = (False, False, False)
            duplicates.append(obj)
            
            collection_utils.move_object_into_collection(unlinked_curve_obj_col , obj)
    
    
    curve_props_to_delete = [
        Curve.PROP_CURVE_ID,
        Curve.PROP_HAS_LINKED_OBJECTS,
        Curve.PROP_DUP_OBJECT_ID,
        Curve.PROP_DUP_USER_DATA,
        Curve.PROP_RADIUS_MULTIPLIER,
        Curve.PROP_OBJECTS_COUNT,
        Curve.PROP_DENSITY_STEP
    ]
    
    for prop in curve_props_to_delete:
        if prop in curve:
            del curve[prop]
        
    return curve, duplicates

# make all objects linked ao a curve unselectable
def lock_all_objects(curve_obj, lock_location = True):
    for obj in bpy.context.scene.objects:
        if obj.get(Curve.PROP_CURVE_PARENT) == curve_obj.name:
            obj.hide_select = True
            #if lock_location:
                #obj.lock_location = (lock_location, lock_location, lock_location)
            
# make all objects linked to a curve selectable
def unlock_all_objects(curve_obj, lock_location = False):
    for obj in bpy.context.scene.objects:
        if obj.get(Curve.PROP_CURVE_PARENT) == curve_obj.name:
            obj.hide_select = False
            #obj.lock_location = (lock_location, lock_location, lock_location)

# select parent curve of object
# make its children unselectable and make only curve selectable
def select_parent_curve(object):
    parent_curve_name = object.get(Curve.PROP_CURVE_PARENT, None)
    if parent_curve_name is None:
        return
    
    parent_curve = bpy.data.objects.get(parent_curve_name)
    if parent_curve is not None and not parent_curve[Curve.PROP_PARENT_SELECTED]:
        parent_curve.hide_select = False
        parent_curve[Curve.PROP_PARENT_SELECTED] = True
        for obj in bpy.context.scene.objects:
            if obj.get(Curve.PROP_CURVE_PARENT) == parent_curve.name:
                obj.hide_select = True
    return parent_curve
            
# select all children of curve present
# make all children linked to curve selectable and make curve unselectable
def select_children_of_curve(curve):
    if not is_bezier_or_nurbs_path(curve):
        return
    
    children = []
    for obj in bpy.context.scene.objects:
        if obj.get(Curve.PROP_CURVE_PARENT) == curve.name:
            obj.hide_select = False
            children.append(obj)
            
    curve_utils.normalise_curve_scale(curve)
    #curve["initial_curve_scale"] = 1
    
    curve.hide_select = True
    curve[Curve.PROP_PARENT_SELECTED] = False
    #blend_utils.select(children)
    return children
    
def get_all_curve_children(curve_obj):
    if curve_obj is None:
        return None
    
    if Curve.PROP_CURVE_ID not in curve_obj:
        return None
    
    children = [obj for obj in get_follower_objects()
                if obj.get(Curve.PROP_CURVE_PARENT) == curve_obj.name]
    return children
    
# return objects if object is a curve and has lihked objects
# or object is not curve, check if it is part of a curve, and returh curve linked to it
def get_curve_or_linked_curve(obj):
    if obj is None:
        return None
    
    if is_bezier_or_nurbs_path(obj) and obj.get(Curve.PROP_HAS_LINKED_OBJECTS,False):
        return obj
    elif Curve.PROP_CURVE_PARENT in obj:
        return bpy.data.objects.get(obj[Curve.PROP_CURVE_PARENT])
    return None

# delete selected curve and children linked to it
def delete_curve_and_children(curve):
    if curve is None:
        raise TypeError("Selected object is None")
    
    if not is_bezier_or_nurbs_path(curve):
        raise TypeError("Object is not a curve")
    
    if not curve[Curve.PROP_HAS_LINKED_OBJECTS]:
        return TypeError("Object has no linked children")

    # Delete all linked objects first - in one batch, see removeobjects_from_curve
    doomed = [obj for obj in bpy.data.objects
              if obj.get(Curve.PROP_CURVE_PARENT) == curve.name]
    deleted_count = len(doomed)
    if doomed:
        bpy.data.batch_remove(doomed)
    
    # try deleting the curve if it is outside collection
    try:
        bpy.data.objects.remove(curve, do_unlink=True)
    except Exception as e:
        pass

    return deleted_count

# replace curve objects on curve with source object provided
def replace_curve_object(curve_obj, source_obj):
    
    new_curve_obj = curve_obj.copy()
    new_curve_obj.data = curve_obj.data.copy()
    new_curve_obj[Curve.PROP_CURVE_ID] = str(uuid.uuid4())
    
    for collection in curve_obj.users_collection:
        collection.objects.link(new_curve_obj)
    
    
    if Group.PROP_GROUP_ID in source_obj:
        new_curve_obj[Curve.PROP_DUP_GROUP_ID] = source_obj[Group.PROP_GROUP_ID]
        new_curve_obj[Curve.PROP_DUP_IS_GROUP] = True
        new_curve_obj[Curve.PROP_GROUP_CHILD_CACHE] = source_obj[Group.PROP_CHILD_CACHE]
        new_curve_obj[Curve.PROP_ORIGIN_MATRIX] = source_obj[Group.PROP_ORIGIN_MATRIX]
    else:
        new_curve_obj[Curve.PROP_DUP_OBJECT_ID] = source_obj["ObjectID"]
        new_curve_obj[Curve.PROP_DUP_USER_DATA] = source_obj["UserData"]
        new_curve_obj[Curve.PROP_DUP_IS_GROUP] = False
    
    
    sync_curves(new_curve_obj , curve_obj, duping_object_source= source_obj)
    
    return new_curve_obj, curve_obj

# reset a curve to its default stage and delete all clildren on it
def reset_curve(curve):
    if curve is None:
        raise TypeError("curve is None")
    
    if not is_bezier_or_nurbs_path(curve) or Curve.PROP_HAS_LINKED_OBJECTS not in curve:
        raise TypeError("object is not a valid curve")
    
    curve_obj, duplciates = apply_curve_transforms_and_detach(curve)
    if duplciates:
        bpy.data.batch_remove(duplciates)
    return curve_obj

def duplicate_curve(curve_obj):
    
    if curve_obj is None:
        return None
    
    new_curve_obj = curve_obj.copy()
    new_curve_obj.data = curve_obj.data.copy()
    new_curve_obj[Curve.PROP_CURVE_ID] = str(uuid.uuid4())
    parent_collection = collection_utils.get_parent_collection(curve_obj)
    parent_collection.objects.link(new_curve_obj)
    
    sync_curves(new_curve_obj, curve_obj)
    
    return new_curve_obj
    

# mirror a curve and objects dupicated along it
def mirror_curve(build_tool,curve_obj, axis = "Z", center = None, auto_duplicate = False):
    if not is_bezier_or_nurbs_path(curve_obj):
        return None
    
    # Duplicate the object and its data block so they don't share identical vertices
    if auto_duplicate:
        new_curve_obj = curve_obj.copy()
        new_curve_obj.data = curve_obj.data.copy()
        new_curve_obj[Curve.PROP_CURVE_ID] = str(uuid.uuid4())
        parent_collection = collection_utils.get_parent_collection(curve_obj)
        parent_collection.objects.link(new_curve_obj)
    else:
        new_curve_obj = curve_obj
                    
    #Apply the mathematical mirror to curve objects
    curve_utils.mirror_curve(new_curve_obj, axis, center)
    
    if new_curve_obj[Curve.PROP_DUP_IS_GROUP]:
        # All this needs out of the group is two strings - the mirrored child
        # cache and the mirrored origin. It used to get them by building every
        # child as a real object, mirroring those, merging them into a mesh and
        # then deleting the mesh, which is about 60 ms of work thrown away.
        # mirror_cache_data does the same arithmetic straight on the cache.
        child_cache = new_curve_obj[Curve.PROP_GROUP_CHILD_CACHE]
        origin_matrix = Group.str_to_matrix(new_curve_obj[Curve.PROP_ORIGIN_MATRIX])

        new_child_cache, new_origin_matrix = Group.mirror_cache_data(
            child_cache, origin_matrix, axis, center
        )
        if new_child_cache is not None:
            new_curve_obj[Curve.PROP_GROUP_CHILD_CACHE] = new_child_cache
            new_curve_obj[Curve.PROP_ORIGIN_MATRIX] = json.dumps(
                [list(row) for row in new_origin_matrix]
            )

    else:
        # update objectID if mirror part of that object exist
        obj_id = new_curve_obj[Curve.PROP_DUP_OBJECT_ID]
        mirror_obj_id = part.Part.get_mirror_part_id(obj_id)
        mirror_part_exist =  mirror_obj_id in nice_name_dictionary.keys()
        if mirror_part_exist:
            new_curve_obj[Curve.PROP_DUP_OBJECT_ID] = mirror_obj_id
            # An in-place mirror reuses the existing follower objects. Updating
            # only the curve's seed ID left their mesh and exported IDs stale.
            if not auto_duplicate:
                for follower in get_all_curve_children(new_curve_obj):
                    BUILDER.mirror_part(follower)
    
    # syncing curves will make objects duplicating on them have identical transformations
    sync_curves(new_curve_obj, curve_obj, True, axis, from_mirror= True)
    return new_curve_obj


# this function takes two curves as argument
# iterage over objects of source curve and copy transformations of those objects to their alternatives in target curve
# this in a way creates eact copy of these curves no matter how much obects have been manupulated by user
# do_mirror: this argument dictates if child objects need to be mirrored
# asix: this dictates which direction objects need to be mirrored
# last two objects dictate which function is calling them, 
def sync_curves(target_curve, source_curve, do_mirror = False, axis = None, from_mirror = False, duping_object_source = None):

    target_curve[Curve.PROP_CURVE_ID] = str(uuid.uuid4())
    target_is_group =  target_curve.get(Curve.PROP_DUP_IS_GROUP,False)
    
    # all child objects of source curve
    source_dupe_objects = [obj for obj in get_follower_objects()
                           if obj.get(Curve.PROP_CURVE_PARENT) == source_curve.name]
    
    radius_multiplier = target_curve[Curve.PROP_RADIUS_MULTIPLIER]
    number_of_objects = target_curve[Curve.PROP_OBJECTS_COUNT]
    
    if duping_object_source is not None:
        duping_obejct = duping_object_source
    elif len(source_dupe_objects) > 0 and not from_mirror:
        duping_obejct = source_dupe_objects[0]
    else:
        duping_obejct = None
        
    # all child objects of parent curve
    target_dupe_obejcts = duplicate_along_curve(duping_obejct, target_curve, number_of_objects, radius_multiplier)
    
    
    if len(target_dupe_obejcts)>0 and not target_is_group:
        target = target_dupe_obejcts[0]
        material.restore_material(target, target["UserData"])
        
    if Curve.PROP_DUP_USER_DATA in source_curve:
        apply_color(target_curve, source_curve.get(Curve.PROP_DUP_USER_DATA,0))
        
    
    # these curves are almost identical
    # blender stores bpy.context.scene.objects in sorted order, so duplicated objects will alsmo match that order.
    # objects on same index will have save transformations
    for index,source in enumerate(source_dupe_objects):
        if index >= len(target_dupe_obejcts):
            break
        
        target = target_dupe_obejcts[index]
        target.rotation_euler = source.rotation_euler.copy()
        target.scale = source.scale.copy()
        target.location = source.location.copy()
        target[Curve.PROP_BASE_SCALE] = source[Curve.PROP_BASE_SCALE]
            
        if do_mirror:
            target.location.x = -target.location.x
            target.rotation_euler.y = -target.rotation_euler.y
            target.rotation_euler.z = -target.rotation_euler.z
            
            if axis is not None and axis == "Z" and target_is_group:
                target.rotation_euler.x += math.pi
                target.rotation_euler.z += math.pi
                
    

    # Refresh evaluation data for the newly synced children
    # update_curve_children(target_curve, radius_multiplier)
    
# scale of a child object of curve is mix of multiple products
# base scale is scale of object before getting influenced by curve's points
def calculate_base_scale(curve, obj):
    curve_scale_multiplier = curve.scale.x/curve.get("initial_curve_scale", curve.scale.x)
    radius_multiplier = curve[Curve.PROP_RADIUS_MULTIPLIER]
    point_radius = obj.get("radius",1.0)
    return obj.scale.x/( point_radius* radius_multiplier * curve_scale_multiplier )

# change color of objects on curve
def apply_color(curve_obj, user_data):
    
    if curve_obj is None:
        return None
    
    if Curve.PROP_HAS_LINKED_OBJECTS in curve_obj and is_bezier_or_nurbs_path(curve_obj):
        curve_obj[Curve.PROP_DUP_USER_DATA] = user_data
        for child_obj in bpy.context.scene.objects:
            if Curve.PROP_CURVE_PARENT in child_obj and child_obj[Curve.PROP_CURVE_PARENT] == curve_obj.name:
                material.restore_material(child_obj, user_data)
                break
