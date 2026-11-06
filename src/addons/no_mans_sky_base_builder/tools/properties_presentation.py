import bpy
import os
from bpy.types import Panel

from .. import icons, build_metadata
from ..utils import dictionary

nice_name_dictionary = dictionary.get_nice_names_diictionary()

# Base Property Panel ---
class NMS_PT_base_prop_panel(Panel):
    bl_idname = "NMS_PT_base_prop_panel"
    bl_label = "📋 Properties"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "No Mans Sky Base Builder"
    bl_context = "objectmode"

    @classmethod
    def poll(self, context):
        return True

    def draw(self, context):
        layout = self.layout
        scene = context.scene
        nms_tool = scene.nms_main

        properties = context.scene.nms_properties
        icon_pcroll = icons.get_icons_pscroll()

        properties_col = layout.column(align = True)
        properties_box = properties_col.box()
        properties_column = properties_box.column(align=False)
        properties_column_row = properties_column.row(align = True)
        properties_column_row.label(text = "Base Properties", **icons.ui_icon("HOME"))
        properties_column_row.operator("object.nms_curve_break_apart", **icons.ui_icon("UNLINKED"),text = "Import from clipboard")
        base_prop_split = properties_column.split(factor = 0.3)
        base_label_col = base_prop_split.column(align = True)
        base_label_col.label(text = "Base Name :")
        base_label_col.label(text = "User Data :")
        base_field_col = base_prop_split.column(align = True)
        build_metadata.draw_name(base_field_col, scene.nms_base_tool)
        base_field_col.prop(scene.nms_base_tool, "string_userdata", text = "")

        #properties_col.separator()
        active_object = properties.active_object
        #curve tools
        if properties.show_gap_edit_field and active_object is not None: # and properties.active_curve_is_highlighted()
            active_curve_box = properties_col.box()
            active_curve_box_col = active_curve_box.column(align = False)
            active_curve_box_col.label(text = "Edit Active-Curve Parameters", **icons.ui_icon("NORMALIZE_FCURVES"))

            active_curve_box_col.separator()
            active_curve_box_col_label_split = active_curve_box_col.split(factor = 0.7)
            active_curve_box_col_label, active_curve_box_col_delete = (active_curve_box_col_label_split.column(), active_curve_box_col_label_split.column())
            active_curve_box_col_label.label(text = f"Target : {properties.active_curve_name}")
            active_curve_box_col_delete.operator("object.nms_curve_delete", **icons.ui_icon("TRASH"),text = "Delete Curve and Children")
            #active_curve_box_col.separator()

            if properties.selected_curve_object_is_parent:
                curve_params_split = active_curve_box_col.split(factor=0.5)
                curve_gap_row, curve_radius_row = (curve_params_split.column(align = True), curve_params_split.column(align = True))
                curve_gap_row.label(text = "Number of Objects")
                curve_gap_row.label(text = "Objects Size")
                #Text fields for editing curv related params
                curve_radius_row.prop(properties,"active_curve_number_of_objects",text = "")
                curve_radius_row.prop(properties,"active_curve_radius_multiplier",text = "")
                active_curve_box_col.separator()

                show_box_buttons_row = active_curve_box_col.row(align = True)
                show_box_buttons_row.operator("object.nms_curve_break_apart", **icons.ui_icon("UNLINKED"),text = "Unlink Curve")
                show_box_buttons_row.operator("object.nms_select_children_of_curve", **icons.ui_icon("MOD_OUTLINE"),text = "Select Children")

            else :
                show_box_buttons_row = active_curve_box_col.row(align = True)
                show_box_buttons_row.operator("object.nms_selecte_object_parent_curve", **icons.ui_icon("MOD_ENVELOPE"),text = "Select Parent")

class NMS_PT_advannced_base_prop_panel(Panel):
    bl_idname = "NMS_PT_advanced_base_prop_panel"
    bl_label = "Advanced Properties"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "No Mans Sky Base Builder"
    bl_context = "objectmode"

    @classmethod
    def poll(self, context):
        return True

    def draw(self, context):
        layout = self.layout
        scene = context.scene
        nms_tool = scene.nms_main

        main_col = layout.column(align = True)
        main_col.label(text = "Position")




def draw_compact_transforms(layout, context):
    properties = context.scene.nms_properties
    active_object = context.active_object
    if active_object is None or not active_object.select_get():
        return
    transformations_box_column = layout.column(align = True)
    transformations_box = transformations_box_column.box()

    transformations_block = transformations_box.column(align = True)
    transformations_row = transformations_block.row(align = True)
    pos_rot_title_col = transformations_row.column(align = True)
    pos_rot_scale_col = transformations_row.column(align = True)
    pos_rot_scale_col.scale_x = 1.5
    paste_col = transformations_row.column().column(align = True)

    pos_rot_title_col.label(text = "Position")#, icon = "OBJECT_ORIGIN")
    pos_col = pos_rot_scale_col.row(align = True)
    pos_col.prop(active_object, "location", index=0, text = "")
    pos_col.prop(active_object, "location", index=1, text = "")
    pos_col.prop(active_object, "location", index=2, text = "")
    paste_col.operator("object.nms_paste_location", **icons.ui_icon("PASTEDOWN"),text = "")

    pos_rot_title_col.label(text = "Rotation")#, icon = "ORIENTATION_GIMBAL")
    rot_col = pos_rot_scale_col.row(align = True)
    rot_col.prop(active_object, "rotation_euler", index=0, text = "")
    rot_col.prop(active_object, "rotation_euler", index=1, text = "")
    rot_col.prop(active_object, "rotation_euler", index=2, text = "")
    paste_col.operator("object.nms_paste_rotation", **icons.ui_icon("PASTEDOWN"),text = "")

    pos_rot_title_col.label(text = "Scale")
    scale_row = pos_rot_scale_col.row(align = True)
    scale_row.prop(properties, "uniform_scale",text = "")
    paste_col.operator("object.nms_paste_scale", **icons.ui_icon("PASTEDOWN"),text = "")

    pos_rot_scale_col.separator()
    copy_transformations_row = pos_rot_scale_col.row(align = True)
    copy_transformations_row.operator("object.nms_copy_transformations", **icons.ui_icon("COPYDOWN"),text = "Copy")
    copy_transformations_row.operator("object.nms_paste_transformations", **icons.ui_icon("PASTEDOWN"),text = "Paste")
    copy_transformations_row.operator("object.nms_reset_transformations", **icons.ui_icon("DECORATE_OVERRIDE"),text = "Reset")



class NMS_PT_transformation_panel(Panel):
    bl_idname = 'NMS_PT_transformation_panel'
    bl_label = 'Curve Tools'
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'No Mans Sky Base Builder'
    bl_options = {'DEFAULT_CLOSED'}
    bl_context = 'objectmode'

    @classmethod
    def poll(cls, context):
        return context.mode == 'OBJECT'

    def draw_header(self, context):
        self.layout.label(text='', icon='CURVE_BEZCURVE')

    def draw(self, context):
        from ..curve_tools import draw_controls
        draw_controls(self.layout, context)
