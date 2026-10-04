from ..utils import mirror_utils
import bpy
import os
import uuid
from ..utils import blend_utils, curve, material, materials_v2, dictionary
from .. import builder, builder_v2, part
from ..group import Group
from ..utils.mirror_utils import ShowMessageBox


nice_name_dictionary = dictionary.get_nice_names_diictionary()
BUILDER = builder.get_builder()

class BatchTool(bpy.types.PropertyGroup):

    nms_batch_replace_type: bpy.props.EnumProperty(
        name="Swap With",
        description="Replace all selected objects with another object of choosing",
        items = [
            ("target", "Target Object", "Replace selected objects with target object chosen"),
            ("object_id", "ObjectId", "Replace selected objects with target ObjectId"),
        ],
        options={'SKIP_SAVE'},
        default = "target"
    )

    object_id: bpy.props.StringProperty(
        name="ObjectID",
        description="Enter ObjectID of object you want selections to be replaced with",
        default="",
        maxlen=1024,
    )

    target_object: bpy.props.PointerProperty(
        name="Target Object",
        type=bpy.types.Object,
        options={'SKIP_SAVE'},
        description = "This object's origin will be take in to account for center of reflection"
    )

    color_picker: bpy.props.PointerProperty(
        name="Colour Picker",
        type=bpy.types.Object,
        options={'SKIP_SAVE'},
        description = "Pick an object to use are reference for colouring",
        update = lambda self, context: self.on_color_picked()
    )



    def on_color_picked(self):
        target_object = self.color_picker
        if target_object is None:
            return

        if "UserData" in target_object:
            target_userdata = target_object["UserData"]
            selected_objects = bpy.context.selected_objects
            for obj in selected_objects:
                material.restore_material(obj, target_userdata)
        self.color_picker = None


    def batch_replace_with_target_object(self):
        """Replace all selected objects with duplicates of the target object."""

        selected_objects = list(bpy.context.selected_objects)
        blend_utils.deselect_all()

        if not selected_objects:
            title="Batch Replace Objects"
            message="Make sure you have an item selected."
            ShowMessageBox( message= message, title=title )
            return 0

        if self.nms_batch_replace_type == "target" and not self.target_object:
            title="Batch Replace Objects"
            message="Choose valid a target object to replace the selection with."
            ShowMessageBox( message= message, title=title )
            return 0
        elif self.nms_batch_replace_type == "object_id" and self.object_id not in nice_name_dictionary:
            title="Batch Replace Objects"
            message="Enter a valid ObjectID to replace the selection with."
            ShowMessageBox( message= message, title=title )
            return 0

        replaced_ojects = []
        if self.nms_batch_replace_type == "target":
            target_object = self.target_object
            if "ObjectID" not in target_object and 'GroupID' not in target_object:
                title="Batch Replace Objects"
                message="Target Object is Invalid"
                ShowMessageBox(message=message, title=title )
                return 0
            else:
                replaced_ojects = self.batch_replace(target_object, selected_objects)
        else :
            # create a temp object if "ObjectID" is provided
            replaced_ojects = self.batch_replace_with_object_id(self.object_id, selected_objects)

        if not replaced_ojects:
            return 0

        # Select the new objects
        try:
            if len(replaced_ojects) > 0:
                blend_utils.select(replaced_ojects)
        except ReferenceError as error:
            print(error)

        return len(replaced_ojects)

    def batch_replace_with_object_id(self, target_object_id, objects_to_replace):
        # create a temp object if "ObjectID" is provided
        object_id = target_object_id
        new_obj = builder_v2.add_part(object_id, builder_object=BUILDER)
        target_object = new_obj.object

        replaced_objects = self.batch_replace(target_object, objects_to_replace)
        bpy.data.objects.remove(target_object, do_unlink=True)

        return replaced_objects


    def batch_replace(self, target_object, objects_to_replace):
        replaced_objects_list = []
        objects_to_delete = []

        # Get the current active collection to link the new objects to
        current_collection = bpy.context.collection

        # Worked out once: it is a property of the target, not of each source.
        # is_high_res covers a merged group of high res parts too, because the
        # merge carries the marker across from the parts' mesh.
        needs_own_mesh = not materials_v2.is_high_res(target_object)

        for source_object in objects_to_replace:
            if source_object == target_object:
                continue

            if source_object is None:
                continue

            # A group carries no ObjectID - its part list and colour live in its
            # own properties - so it used to miss every branch here and be
            # silently skipped, leaving the group sitting where it was while
            # everything else in the selection got replaced.
            if "ObjectID" in source_object or Group.PROP_GROUP_ID in source_object:
                # This create a linked duplicate
                replaced_object = target_object.copy()
                if needs_own_mesh and replaced_object.data:
                    # an fbx proxy keeps its colour on the mesh's material, so
                    # each replacement needs its own. A high res part or a group
                    # of them keeps colour on the object, and copying there would
                    # give every replacement its own copy of the library mesh.
                    replaced_object.data = replaced_object.data.copy()

                # Copy transforms
                replaced_object.matrix_world = source_object.matrix_world.copy()
                # Link the new object to the scene
                current_collection.objects.link(replaced_object)

                replaced_objects_list.append(replaced_object)
                objects_to_delete.append(source_object)
            elif "has_linked_objects" in source_object and source_object.get("has_linked_objects", False):
                new_curve, old_curve = curve.replace_curve_object(source_object, target_object)
                replaced_objects_list.append(new_curve)
                objects_to_delete.append(old_curve)

        # Delete old objects - in one batch, a remove() per object re-syncs the
        # whole scene each time
        if objects_to_delete:
            bpy.data.batch_remove(objects_to_delete)

        return replaced_objects_list


    def select_same_colored_objects(self, with_same_object_id = False):
        """Selects objects with same UserData, for easy experimentation with colors"""

        selected_objects = bpy.context.selected_objects

        if not selected_objects:
            ShowMessageBox(
                message="Make sure you have an item selected.", title="Find Objects with same Color"
            )
            return 0

        #Gather unique keys from selected obejcts
        keys_to_find = []
        for obj in selected_objects:
            if "ObjectID" not in obj:
                continue

            obj_id = obj["ObjectID"]
            user_data = obj["UserData"]
            if (obj_id,user_data) not in keys_to_find:
                keys_to_find.append((obj_id,user_data))

        #Iterate through all objects to collect matches with keys_to_find
        found_matches = []
        for obj in bpy.context.view_layer.objects:
            if "ObjectID" not in obj:
                continue

            obj_id = obj["ObjectID"]
            user_data = obj["UserData"]

            new_key = (obj_id, user_data)
            if new_key in keys_to_find:
                found_matches.append(obj)

        if len(found_matches) > 0:
            blend_utils.select(found_matches)

        return len(found_matches) - len(keys_to_find)

    def select_all_same_colored_objects(self):
        """Selects objects with same UserData, for easy experimentation with colors"""

        selected_objects = bpy.context.selected_objects

        if not selected_objects:
            ShowMessageBox(
                message="Make sure you have an item selected.", title="Find Objects with same Color"
            )
            return 0

        #Gather unique keys from selected obejcts
        keys_to_find = []
        for obj in selected_objects:
            if "ObjectID" not in obj:
                continue

            user_data = obj["UserData"]
            if user_data not in keys_to_find:
                keys_to_find.append(user_data)

        #Iterate through all objects to collect matches with keys_to_find
        found_matches = []
        for obj in bpy.context.view_layer.objects:
            if "ObjectID" not in obj:
                continue

            user_data = obj["UserData"]
            if user_data in keys_to_find:
                found_matches.append(obj)

        if len(found_matches) > 0:
            blend_utils.select(found_matches)

        return len(found_matches) - len(keys_to_find)


    def select_same_objects(self):
        """Selects objects with same ObjectIDs"""

        selected_objects = bpy.context.selected_objects

        if not selected_objects:
            ShowMessageBox(
                message="Make sure you have an item selected.", title="Select same Objects"
            )
            return 0

        #Gather unique keys from selected obejcts
        keys_to_find = []
        for obj in selected_objects:
            obj_id = None
            if "ObjectID" in obj:
                obj_id = obj["ObjectID"]
            elif "GroupID" in obj:
                obj_id = obj["GroupID"]
            else:
                obj_id = None

            if obj_id is not None and obj_id not in keys_to_find:
                keys_to_find.append(obj_id)

        #Iterate through all objects to collect matches with keys_to_find
        found_matches = []
        for obj in bpy.context.view_layer.objects:
            if "ObjectID" in obj:
                obj_id = obj["ObjectID"]
            elif "GroupID" in obj:
                obj_id = obj["GroupID"]
            else:
                obj_id = None

            if obj_id is not None and obj_id in keys_to_find:
                found_matches.append(obj)

        if len(found_matches) > 0:
            blend_utils.select(found_matches)

        return len(found_matches) - len(keys_to_find)

    def select_all_groups(self):
        #Iterate through all objects to collect matches with keys_to_find
        found_matches = []
        for obj in bpy.context.view_layer.objects:
            if "GroupID" in obj:
                found_matches.append(obj)
        if len(found_matches) > 0:
            blend_utils.select(found_matches)
        return len(found_matches)

