import bpy
import math

class ResetTransformations(bpy.types.Operator):
    """Reset Scale and Rotation of an object"""

    bl_idname = "object.nms_reset_transformations"
    bl_translation_context = "BBEExtendedInterface"
    bl_label = "Reset Transformations"
    bl_options = {"UNDO", "REGISTER"}

    def execute(self, context):
        selected_objects = bpy.context.selected_objects
                
        bpy.ops.object.rotation_clear(clear_delta=False)
        bpy.ops.object.scale_clear(clear_delta=False)
        
        if selected_objects is None or len(selected_objects) == 0:
            self.report({'WARNING'}, f"Please select atleast one object first")
        else :
            for obj in selected_objects:
                if "ObjectID" in obj:
                    obj.rotation_euler.x = math.pi/2
        return {"FINISHED"}
    
class CopyTransformations(bpy.types.Operator):
    """Copy Transformation of active object"""

    bl_idname = "object.nms_copy_transformations"
    bl_translation_context = "BBEExtendedInterface"
    bl_label = "Copy Transformations"
    

    def execute(self, context):
                
        scene = context.scene
        proeprties = scene.nms_properties
        
        active_object = bpy.context.active_object
        if active_object is None:
            self.report({'WARNING'}, f"Please select an object first")
        else:
            proeprties.copied_position = active_object.location
            proeprties.copied_rotation = active_object.rotation_euler
            proeprties.copied_scale = active_object.scale
    
            self.report({'INFO'}, f"Copied Transformations")
            
        
        return {"FINISHED"}
    
class PasteTransformations(bpy.types.Operator):
    """Paste Copied transformations"""

    bl_idname = "object.nms_paste_transformations"
    bl_translation_context = "BBEExtendedInterface"
    bl_label = "Paste Transformations"
    bl_options = {"UNDO", "REGISTER"}

    def execute(self, context):
        selected_objects = bpy.context.selected_objects
        if selected_objects is None or len(selected_objects) == 0:
            self.report({'WARNING'}, f"Please select atleast one object first")
        else:
            scene = context.scene
            proeprties = scene.nms_properties
            proeprties.paste_transformatinos(paste_location = True, paste_rotation = True, paste_scale = True)
        
        return {"FINISHED"}
    
class PasteLocation(bpy.types.Operator):
    """Paste Copied location"""

    bl_idname = "object.nms_paste_location"
    bl_translation_context = "BBEExtendedInterface"
    bl_label = "Paste Location"
    bl_options = {"UNDO", "REGISTER"}

    def execute(self, context):
        
        selected_objects = bpy.context.selected_objects
        if selected_objects is None or len(selected_objects) == 0:
            self.report({'WARNING'}, f"Please select atleast one object first")
        else:
            scene = context.scene
            proeprties = scene.nms_properties
            proeprties.paste_transformatinos(paste_location = True, paste_rotation = False, paste_scale = False)
        
        return {"FINISHED"}
    
class PasteRotation(bpy.types.Operator):
    """Paste Copied Rotation"""

    bl_idname = "object.nms_paste_rotation"
    bl_translation_context = "BBEExtendedInterface"
    bl_label = "Paste Rotation"
    bl_options = {"UNDO", "REGISTER"}

    def execute(self, context):
        selected_objects = bpy.context.selected_objects
        if selected_objects is None or len(selected_objects) == 0:
            self.report({'WARNING'}, f"Please select atleast one object first")
        else:
            scene = context.scene
            proeprties = scene.nms_properties
            proeprties.paste_transformatinos(paste_location = False, paste_rotation = True, paste_scale = False)
        
        return {"FINISHED"}
    
class PasteScale(bpy.types.Operator):
    """Paste Copied Scale"""

    bl_idname = "object.nms_paste_scale"
    bl_translation_context = "BBEExtendedInterface"
    bl_label = "Paste Scale"
    bl_options = {"UNDO", "REGISTER"}

    def execute(self, context):
        
        selected_objects = bpy.context.selected_objects
        if selected_objects is None or len(selected_objects) == 0:
            self.report({'WARNING'}, f"Please select atleast one object first")
        else:
            scene = context.scene
            proeprties = scene.nms_properties
            proeprties.paste_transformatinos(paste_location = False, paste_rotation = False, paste_scale = True)
        
        return {"FINISHED"}
    
    
classes = (
    ResetTransformations,
    CopyTransformations,
    PasteTransformations,
    
    PasteLocation,
    PasteRotation,
    PasteScale
    
)