import bpy
from bpy.types import Panel

from .. import icons


# Base Property Panel ---
class NMS_PT_batch_tools_panel(Panel):
    bl_idname = "NMS_PT_batch_tools_panel"
    bl_label = 'Batch Tools'
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "No Mans Sky Base Builder"
    bl_context = "objectmode"
    bl_options = {'DEFAULT_CLOSED'} 

    @classmethod
    def poll(self, context):
        return True

    def draw_header(self, context):
        icons.draw_panel_icon(self.layout, 'batch')

    def draw(self, context):
        layout = self.layout
        scene = context.scene
        batch_tool = scene.nms_batch_tool
        
        batch_column = layout.column(align = True)
        top_row = batch_column.row(align = True)
        select_box = top_row.box()
        select_col = select_box.column(align = True)
        select_col.label(text = "Select objects with")
        select_color_row = select_col.row(align = True)
        select_color_row.operator("object.nms_select_same_colors", text = "Same Colour", **icons.ui_icon("MOD_SOFT"))
        select_color_row.operator("object.nms_select_all_same_colors", text = "", **icons.ui_icon("TEXTURE"))
        select_col.operator("object.nms_select_same_objects", text = "Same ObjectID", **icons.ui_icon("CON_SIZELIKE"))
        select_col.operator("object.nms_select_all_groups", text = "Select all Groups", **icons.ui_icon("OUTLINER_OB_GROUP_INSTANCE") )
        
        
        more_options_box =  top_row.box()
        more_options_column = more_options_box.column(align = True)
        from ..save_editor.function_help import corner_help
        heading = more_options_column.row(align=True)
        heading.label(text = "Selection Tools",)
        corner_help(heading, 'BATCH')
        more_options_column.operator("object.nms_select_duplicates", text = "Find Duplicates", **icons.ui_icon("BRUSH_DATA"))
        more_options_column.operator("object.nms_batch_select_random", text = "Select Random", **icons.ui_icon("MOD_NOISE"))
        more_options_column.operator("object.nms_batch_select_pattern", text = "Select Pattern", **icons.ui_icon("MOD_OCEAN"))
        
        batch_replace_box = batch_column.box().column(align = True)
        batch_replace_box.label(text = "Batch Replace")
        batch_replace_box.operator("object.nms_batch_replace_target", text = "Batch Replace", **icons.ui_icon("GROUP_VERTEX") )# icon = "CON_FOLLOWPATH"
        
        #more_selection_tools_box = batch_column.row(align = True)
        #more_selection_tools_column = more_selection_tools_box.box().column(align = True)
        #more_selection_tools_column.label(text = "More Selction Tools")
        #more_selection_tools_column.operator("object.nms_batch_replace_target", text = "Select Wires", icon = "MOD_OFFSET" )
        
        
        #more_selection_tools_box.column(align = True).label(text = "")