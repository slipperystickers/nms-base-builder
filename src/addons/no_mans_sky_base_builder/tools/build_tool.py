from ..utils import mirror_utils
import bpy
import os
import uuid
import json
from ..utils import blend_utils, curve, dictionary, material
from .. import builder, builder_v2, part, group
from ..utils.mirror_utils import ShowMessageBox

from ..group import Group
from ..utils.curve import Curve

from mathutils import Vector,Matrix

nice_name_dictionary = dictionary.get_nice_names_diictionary()
BUILDER = builder.get_builder()

class BuildTool(bpy.types.PropertyGroup):
    
    # checkbox to hide/show advanced mirroring options
    check_show_advanced_options: bpy.props.BoolProperty(
        name="Show advanved options",
        description = "Show/Hide advanced mirroring options.",
        default=False,
        options={'SKIP_SAVE'}
    )
    
    # if checked true, auto duplication of objects during mirroring will occur
    check_auto_duplicate: bpy.props.BoolProperty(
        name="Auto duplicate",
        description = (
            "if checked, Perform Mirror button will auto duplicate objects before mirroring action. \n"
            "Helps skip duplication action before mirroring."
            ),
        default=False,
        options={'SKIP_SAVE'}
    )
    
    # direction for mirror in advanced mirroring options
    # There can only be three options X,Y and Z
    mirror_direction: bpy.props.EnumProperty(
        name="Mirror Direction",
        description = "Direction in which mirroring will occur",
        items = [
            ("X", "X", "mirror in X direction"),
            ("Y", "Y", "mirror in Y direction"),
            ("Z", "Z", "mirror in Z direction"),
        ],
        options={'SKIP_SAVE'},
        default = 'X'
    )
    
    # for selecting center of reflection
    # world origin will always be 0,0,0
    # 3d curson can be changed at any time with shift + right click
    # Object can be any object and it's origin will be take in to account for center of reflection
    center_of_reflection: bpy.props.EnumProperty(
        name="Reflection Center",
        description = "Select center of reflection, a point arround which mirroring will take place",
        items = [
            ("World Origin", "World Origin", "World origin will always be 0,0,0","OBJECT_ORIGIN",0),
            ("3D cursor", "3D cursor", "3d curson can be changed at any time with shift + right click","CURSOR",1)
        ],
        options={'SKIP_SAVE'},
        default = 'World Origin'
    )
    
    # when object is selected in advanced mirroring options
    # this stores reference to that object
    target_object: bpy.props.PointerProperty(
        name="Target Object",
        type=bpy.types.Object,
        options={'SKIP_SAVE'},
        description = "This object's origin will be take in to account for center of reflection"
    )
    
    
    def mirror(self, axis = None, center = None, change_orientation = False, auto_duplicate = False, objects_to_mirror = None):
        """Mirror the object acording to parameters provided"""
        # Store selection and validate.
        selected_objects = bpy.context.selected_objects if objects_to_mirror is None else objects_to_mirror
        if not selected_objects:
            ShowMessageBox(
                message="Make sure you have an item selected.", 
                title="Mirror"
            )
            return
        
        hierarchy_data = {}
        hierarchy_results = []
        if objects_to_mirror is None and not auto_duplicate:
            for obj in selected_objects:
                if obj is not None and curve.Curve.PROP_CURVE_PARENT in obj:
                    continue
                
                if obj.parent:
                    # Native counterpart swaps rename parts. Keep identity,
                    # not the old name, when restoring their parent link.
                    hierarchy_data[obj.as_pointer()] = (obj.parent, obj.matrix_parent_inverse.copy())
                    current_world_matrix = obj.matrix_world.copy()
                    obj.parent = None
                    obj.matrix_world = current_world_matrix
        
        existing_groups = Group.get_all_groups() if objects_to_mirror is None else []

        # Get Selected item.
        new_items = []
        for target in selected_objects:
            target_key = target.as_pointer()
            result_start = len(new_items)
            # Part
            if "ObjectID" in target :
                object_id = target["ObjectID"]
                mirror_id = part.Part.get_mirror_part_id(object_id)
                if not change_orientation:
                    from ..utils import mirror_pivot
                    mirror_pivot.ensure_object(target)
                
                if auto_duplicate and not change_orientation:
                    new_item = blend_utils.duplicate_part(target)
                else :
                    new_item = target
                
                # If mirror part exist for an object, like for a corvette part,
                mirror_part_exist =  mirror_id in nice_name_dictionary.keys()
                if mirror_part_exist:
                    # mirror_part owns the mesh policy now - it either points the
                    # object at the twin's own library mesh, which is meant to be
                    # shared, or flips a private copy. Copying again here would
                    # give every mirrored part its own duplicate of the library.
                    new_item = BUILDER.mirror_part(new_item)
                     
                if not change_orientation:
                    old_world = new_item.matrix_world.copy()
                    mirrored_matrix_world = mirror_utils.mirror_matrix_world_universal(
                        object_id, 
                        new_item.matrix_world.copy(), 
                        axis,center, 
                        mirror_part_exist = mirror_part_exist
                    )
                    if object_id == 'BASE_BUBPIPE':
                        from .. import bubble_preview
                        bubble_preview.mirror_openings(new_item, old_world, mirrored_matrix_world, axis)
                    new_item.matrix_world = mirrored_matrix_world
                else :
                    mirrored_matrix_world = mirror_utils.change_orientation(object_id,new_item.matrix_world.copy(), axis, mirror_part_exist)
                    new_item.matrix_world = mirrored_matrix_world
                        
                if hasattr(new_item, "object"):
                    new_items.append(new_item.object)
                else:
                    new_items.append(new_item)
                   
            # mirror if object is a custom nms curve
            elif curve.is_bezier_or_nurbs_path(target) and "has_linked_objects" in target:
                if not target["has_linked_objects"]:
                    continue
                
                should_auto_duplicate = auto_duplicate and not change_orientation
                new_curve_obj = curve.mirror_curve( self, target, axis, center, should_auto_duplicate)
                if new_curve_obj is not None:
                    new_items.append(new_curve_obj)
            
            # mirror if object is a nms group
            elif Group.PROP_GROUP_ID in target and objects_to_mirror is None: 
                is_target_mirror = target.get(Group.PROP_IS_MIRROR, False)   
                found_match = Group.find_mirror_group(target, existing_groups)
                if change_orientation:
                    # The orientation buttons have no world reflection center.
                    # Work in the group's frame, then restore that frame, so
                    # every child is mirrored about the same local plane.
                    group_matrix = target.matrix_world.copy()
                    local_axis = {'X': 'X', 'Z': 'Y', 'Y': 'Z'}[axis]
                    children = Group.ungroup_objects(BUILDER, target)
                    for child in children:
                        child.matrix_world = group_matrix.inverted_safe() @ child.matrix_world
                    bpy.context.view_layer.update()
                    children = self.mirror(local_axis, Vector((0, 0, 0)), objects_to_mirror=children)
                    for child in children:
                        child.matrix_world = group_matrix @ child.matrix_world
                    bpy.context.view_layer.update()
                    mirrored_group = Group.group_objects(children, group_matrix)
                    # These local planes need not match the cached world-X twin.
                    # A fresh identity prevents a later mirror reusing that twin.
                    mirrored_group[Group.PROP_GROUP_ID] = str(uuid.uuid4())
                    mirrored_group[Group.PROP_IS_MIRROR] = False
                elif found_match is None:
                    # if there is no mirror present for target object 
                    # create a mirror by ungrouping -> mirroring ungrouped objects -> grouping them again
                    new_obj = blend_utils.duplicate_part(target) if auto_duplicate else target
                    old_group_id = new_obj[Group.PROP_GROUP_ID]
                    
                    group_matrix_world = new_obj.matrix_world.copy()
                    group_matrix_world = mirror_utils.mirror_matrix_world_universal(None, group_matrix_world, axis,center)
                    
                    # split group into objects
                    ungrouped_objects = Group.ungroup_objects(BUILDER,new_obj)
                    
                    # mirror all objects normally
                    if ungrouped_objects:
                        ungrouped_objects = self.mirror( axis, center, objects_to_mirror = ungrouped_objects)
                    
                    # regroup objects into a group
                    mirrored_group = Group.group_objects(ungrouped_objects, group_matrix_world)
                    # restore GroupID
                    mirrored_group[Group.PROP_GROUP_ID] = old_group_id
                    # flip boolean that describes which side of mirror group belongs
                    mirrored_group[Group.PROP_IS_MIRROR] = not is_target_mirror
                else:
                    # un-grouping and re-grouping is an expeisive task, it can be optimised by reusing existing mirrors
                    # if a mirroed group already exist, use it's mesh and data to mirror target
                    
                    # duplicate existing mirror group
                    mirrored_group = blend_utils.duplicate_part(found_match)
                    
                    # assign that duplicate a mirrored matrix world of target
                    old_matrix_world = target.matrix_world.copy()
                    new_matrix_world = mirror_utils.mirror_matrix_world_universal(None, old_matrix_world, axis,center)
                    mirrored_group.matrix_world = new_matrix_world
                    
                    # delete target if auto duplicate is not checked
                    if not auto_duplicate:
                        group_name = target.name
                        bpy.data.objects.remove(target, do_unlink=True)
                        mirrored_group.name = group_name
                        
                # append newly generated morrors to existing_groups list for optimised search operations
                existing_groups.append(mirrored_group)
                new_items.append(mirrored_group)
                
            else:
                if target is not None:
                    if auto_duplicate:
                        new_item = blend_utils.duplicate_part(target)
                    else:
                        new_item = target
                    new_item.matrix_world = (mirror_utils.change_orientation(None, new_item.matrix_world, axis)
                                            if change_orientation else
                                            mirror_utils.mirror_matrix_world_universal(None, new_item.matrix_world, axis,center))
                    new_items.append(new_item)
            if target_key in hierarchy_data:
                parent, inverse = hierarchy_data[target_key]
                hierarchy_results.extend((obj, parent, inverse) for obj in new_items[result_start:])
        
        if hierarchy_data:
            bpy.context.view_layer.update()
            restored = [(obj, parent, inverse, obj.matrix_world.copy())
                        for obj, parent, inverse in hierarchy_results]
            for obj, parent, inverse, world in restored:
                obj.parent = parent
                obj.matrix_parent_inverse = inverse
                obj.matrix_world = world
        
        #material.optimise_materials()
        
        # filter out deleted objects
        new_items = [obj for obj in new_items if obj is not None]
        if new_items:
            blend_utils.select(new_items)
        return new_items
    
    # called my Perform Mirror button in advanced mirroring options
    def advanced_mirror(self):
        mirror_direction = self.mirror_direction
        auto_duplicate = self.check_auto_duplicate
        # Only mirroring direction is needed if world origin is take as center of reflection
        if self.center_of_reflection == "World Origin":
            self.mirror(axis = mirror_direction, center = Vector((0,0,0)), auto_duplicate = auto_duplicate)
        # gather location of active object and use that as center of reflection
        elif self.center_of_reflection == "3D cursor":
            cursor_location = bpy.context.scene.cursor.location
            center = Vector((
                cursor_location.x,
                cursor_location.y,
                cursor_location.z
            ))
            self.mirror(axis = mirror_direction, center = center, auto_duplicate = auto_duplicate)
        # target object's origin will be passed here for center of reflection
        elif self.center_of_reflection == "Object":
            if self.target_object:
                center = Vector((
                    self.target_object.location.x,
                    self.target_object.location.y,
                    self.target_object.location.z
                ))
                self.mirror(axis = mirror_direction, center = center, auto_duplicate = auto_duplicate)
            else:
                ShowMessageBox(
                    message="Make sure you have target object selected", title="Object Mirror"
                )
                
    def flip(self):
        """Mirror the object along X axis (if possible)."""
        # Store selection.
        selected_objects = bpy.context.selected_objects
        new_items = []
        # Validate
        if not selected_objects:
            ShowMessageBox(message="Make sure you have an item selected.", title="Flip")
            return

        # Get Selected item.
        for target in selected_objects:
            # Part
            if "ObjectID" in target:
                object_id = target["ObjectID"]
                mirror_id = part.Part.get_flip_part_id(object_id)
                new_item = target
                if mirror_id in nice_name_dictionary.keys():
                    # Build Item.
                    new_item = BUILDER.flip_part(target)
                    new_items.append(new_item)

                if hasattr(new_item, "object"):
                    new_items.append(new_item.object)
                else:
                    new_items.append(new_item)

        blend_utils.select(new_items)
        
    def duplicate_along_curve(self, number_of_objects, radius_multiplier = 1.0):
        """Follow the curve, calibrated to the selected seed's starting pose."""
        bpy.context.view_layer.update()
        selected_objects = bpy.context.selected_objects

        curve_object, seeds = curve.duplication_selection(selected_objects)
        if not seeds:
            curve.show_duplicate_selection_help(bpy.context)
            return {"CANCELLED"}
        if len(seeds) == 1:
            dup_object = seeds[0]
        else:
            active = bpy.context.active_object
            pivot = active.matrix_world if active in seeds else None
            dup_object = Group.group_objects(seeds, pivot, flatten_groups=True)
            if dup_object is None:
                return {"CANCELLED"}

        from ..curve_studio import prepare_frame
        if not curve_object.get("has_linked_objects"):
            prepare_frame(curve_object)

        if "has_linked_objects" in curve_object:
            new_curve_object, old_curve_object = curve.replace_curve_object(
                curve_object, dup_object, number_of_objects, radius_multiplier
            )
            blend_utils.delete(old_curve_object)
            curve_object = new_curve_object
        
        else :
            alignment = curve.get_source_curve_alignment(curve_object, dup_object)
            curve.set_source_curve_alignment(curve_object, alignment)
            curve_object[Curve.PROP_CURVE_ID] = str(uuid.uuid4())
            curve_object["parent_selected"] = True
            curve_object.show_in_front = True
            properties = bpy.context.scene.nms_properties
            properties.active_curve_radius_multiplier = radius_multiplier
            properties.prev_curve_radius_multiplier = radius_multiplier
            properties.active_curve_number_of_objects = number_of_objects
            properties.prev_curve_number_of_objects = number_of_objects
            
            print("duplicating along curve")
            # Perform duplication along curve.
            curve.duplicate_along_curve( dup_object, curve_object, number_of_objects, radius_multiplier )
            
            # lock all objects on curve so that only curve is selectable
            curve.lock_all_objects(curve_object)
            
        blend_utils.select(curve_object)
        properties = bpy.context.scene.nms_properties
        properties.set_active_obect(curve_object)
        

    def delete(self):
        """Delete the selected object and everything below."""
        # Store selection.
        selected_objects = bpy.context.selected_objects
        # Validate
        if not selected_objects:
            ShowMessageBox(
                message="Select an item to delete from the scene.", title="Delete"
            )
            return
        # Removing a guide can also remove selected followers.
        names = [obj.name for obj in selected_objects]
        deleted_count = 0
        for name in names:
            item = bpy.context.scene.objects.get(name)
            if item is None:
                continue
            if curve.is_bezier_or_nurbs_path(item):
                deleted_count += curve.delete_curve_and_children(item)
            else:
                blend_utils.delete(item)
            deleted_count += 1
        return deleted_count

    def duplicate(self):
        """Snaps one object to another based on selection."""
        # Store selection.
        selected_objects = bpy.context.selected_objects
        
        # Validate
        if not selected_objects:
            ShowMessageBox(
                message="Make sure you have an item selected.", title="Duplicate"
            )
            return

        # Get Selected item.
        #target = blend_utils.get_current_selection()
        duplicates = []
        for target in selected_objects:
            
            if "ObjectID" not in target and "PresetID" not in target and "CurveID" not in target:
                message = (
                    "This item can not be duplicated via the No Man's Sky tool. "
                    "Try using Blender hotkey instead (Shift-D)."
                )
                ShowMessageBox(message=message, title="Duplicate")
                return
            if "CurveID" in target:
                new_item = curve.duplicate_curve(target)
                duplicates.append(new_item)
            else:
                # Part
                if "ObjectID" in target:
                    object_id = target["ObjectID"]
                    user_data = target["UserData"]
                    # Build Item.
                    new_item = builder_v2.add_part(
                        object_id, user_data=user_data, builder_object=BUILDER
                    )
                    duplicates.append(new_item.object)
                elif "PresetID" in target:
                    preset_id = target["PresetID"]
                    # Build Item.
                    new_item = BUILDER.add_preset(preset_id)
                    duplicates.append(new_item.control)
                else:
                    new_item = None

                if new_item is not None:
                    # Build Rig if need to.
                    if hasattr(new_item, "build_rig"):
                        new_item.build_rig()
                    # Snap.
                    target = BUILDER.get_builder_object_from_bpy_object(target)
                    new_item.snap_to(target)
                    
        return duplicates
        
        
    def snap(
        self, next_source=False, prev_source=False, next_target=False, prev_target=False
    ):
        """Snaps one object to another based on selection."""
        selected_objects = bpy.context.selected_objects

        source = None
        target = None
        # If only one item is selected, see if it has a snapped to variable to
        # use.
        if len(selected_objects) == 1:
            source = bpy.context.view_layer.objects.active
            if source is not None and "snapped_to" in source:
                target = bpy.context.scene.objects.get(source["snapped_to"])
            if target is None:
                message = (
                    "This item has not been snapped to anything. Please select "
                    "the item you want to snap it to"
                )
                ShowMessageBox(message=message, title="Snap")
                return {"CANCELLED"}

        # If 2 are selected, use them as the snapping items.
        elif len(selected_objects) == 2:
            target = bpy.context.view_layer.objects.active
            source = [obj for obj in selected_objects if obj != target][0]

        # If otherwise, we should skip and warn the user.
        else:
            message = (
                "Select the item to move first, then select its target last."
            )
            ShowMessageBox(message=message, title="Snap")
            return {"CANCELLED"}

        # Perform Snap
        source = BUILDER.get_builder_object_from_bpy_object(source)
        target = BUILDER.get_builder_object_from_bpy_object(target)
        if source and target:
            # A terminal/wall pair has an unambiguous moving part. Accept
            # either selection order without ever moving the wall.
            if (getattr(target, 'object_id', None) == 'BUILDTERMINAL'
                    and target.get_snap_pair_options(source)):
                source, target = target, source
            snapped = source.snap_to(
                target,
                next_source=next_source,
                prev_source=prev_source,
                next_target=next_target,
                prev_target=prev_target,
            )
            if snapped is not False:
                source.select()
                if (len(selected_objects) == 2 and hasattr(source, 'object') and hasattr(target, 'object')
                        and not any((next_source, prev_source, next_target, prev_target))):
                    from .. import snap_markers
                    snap_markers.start(bpy.context, source.object, target.object)
                return {"FINISHED"}
        ShowMessageBox(
            message="These parts do not have a compatible BBE snap connection.",
            title="Snap",
        )
        return {"CANCELLED"}
        
    def get_part_count(self):
        from .. import part_counts
        return part_counts.count(self.id_data)
