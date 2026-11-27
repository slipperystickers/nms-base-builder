from .. import i18n
import bpy
from bpy.types import Panel
from .. import icons


# Snap Panel ---
class NMS_PT_tools_panel(Panel):
    bl_idname = "NMS_PT_snap_panel"
    bl_translation_context = "BBEExtendedInterface"
    bl_label = 'Builder Tools'
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "No Mans Sky Base Builder"
    bl_context = "objectmode"
    bl_options = {'DEFAULT_CLOSED'}

    @classmethod
    def poll(self, context):
        return True

    def draw_header(self, context):
        from .. import sidebar_builder
        sidebar_builder.begin_header(self, context)
        icons.draw_panel_icon(i18n.localized_layout(self.layout), 'builder')

    def draw_header_preset(self, context):
        from .. import part_counts
        region = context.region
        left = region.view2d.region_to_view(0, 0)[0]
        width = (region.view2d.region_to_view(region.width, 0)[0] - left) / context.preferences.system.ui_scale
        count = str(part_counts.displayed(context.scene))
        self.layout.label(text=(i18n.interface('Part count')+' '+count) if width >= 245 else '# '+count)

    def draw(self, context):
        from .. import sidebar_builder
        if not sidebar_builder.draw_inline(self, context):
            NMS_PT_tools_panel.draw_controls(self, context)

    def draw_controls(self, context):
        layout = i18n.localized_layout(self.layout)
        from ..save_editor.corvette_optimizer import draw_cockpit_controls
        scene = context.scene
        nms_tool = scene.nms_main
        build_tool = context.scene.nms_build_tool
        selected_tube = context.active_object
        is_tube = selected_tube is not None and selected_tube.get('ObjectID') == 'BASE_BUBPIPE'
        # Split into two columns of equal widths.
        #split = layout.split(factor=0.5)
        #tools_column, snap_column = (split.column(align = True), split.column(align = True))
        build_tools_col = layout.column(align = True)
        tools_row = build_tools_col.row(align = True)
        snap_column = tools_row.column(align = True)
        tools_column = tools_row.column(align = True)#tools_column
        snap_column.scale_x = 1.5
        
        # Create Snapping box.
        snap_box = tools_column.box()
        snap_col = snap_box.column(align=True)
        from ..utils.asset_browser_utils import auto_snap_enabled
        enabled = auto_snap_enabled()
        snap_col.operator('bbe.toggle_auto_snap', text='Auto-Snap',
                          icon='CHECKBOX_HLT' if enabled else 'CHECKBOX_DEHLT', depress=enabled)
        
        snap_button_row = snap_col.row(align = True)
        snap_button_split = snap_button_row.split(factor=0.277777)
        snap_label_col, snap_button_container = (snap_button_split.column(align = True), snap_button_split.column(align = True))
        
        snap_label_col.label(text="Snap")
        snap_label_col.label(text="Target")
        snap_label_col.label(text="Source")
        
        snap_op = snap_button_container.operator("object.nms_snap", **icons.ui_icon("SNAP_ON"))

        target_source_column = snap_button_container.column(align=True)
        target_row = target_source_column.row(align=True)
        source_row = target_source_column.row(align=True)
        
        snap_target_prev = target_row.operator( "object.nms_snap", **icons.ui_icon("TRIA_LEFT"), text="Prev" )
        snap_target_next = target_row.operator( "object.nms_snap", **icons.ui_icon("TRIA_RIGHT"), text="Next" )
        
        snap_source_prev = source_row.operator( "object.nms_snap", **icons.ui_icon("TRIA_LEFT"), text="Prev")
        snap_source_next = source_row.operator("object.nms_snap", **icons.ui_icon("TRIA_RIGHT"), text="Next")
        repeats=snap_column.box().column(align=True);repeats.label(text='Duplication');repeats.operator_context='INVOKE_DEFAULT'
        repeats.operator('object.nms_duplicate',text='Duplicate',icon='DUPLICATE')
        repeats.operator('bbe.duplicate_edge_path',icon='CURVE_BEZCURVE')
        repeats.operator('bbe.duplicate_axis',icon='MOD_ARRAY')
        tools_box = snap_column.box()
        tools_col = tools_box.column(align = True)
        title=tools_col.row(align=True);title.label(text='Common Tools')
        from ..save_editor.function_help import corner_help
        corner_help(title,'BUILDER')
        draw_cockpit_controls(tools_col)
        tools_col.operator('bbe.repair_bubble_tubes', icon='FILE_REFRESH')
        #tools_col.separator()
        tools_dup_row = tools_col.column(align = False)
        align=tools_col.row();align.operator_context='INVOKE_DEFAULT';align.operator('bbe.align_geometry',text='Align',icon='SNAP_ON')
        tools_dup_row.operator("object.nms_delete", **icons.ui_icon("TRASH"))
        tools_col.separator()
        #tools_col.label(text="Curve")
        tools_col.separator()
        #presets_v2_col = tools_box.column(align = True)
        tools_col.label(text = "Grouping")
        presets_v2_row = tools_col.row(align = True)
        presets_v2_row.operator("object.nms_group_objects", text = "Group", **icons.ui_icon("OUTLINER_OB_POINTCLOUD") )
        presets_v2_row.operator("object.nms_ungroup_objects", text = "Ungroup",  **icons.ui_icon("OUTLINER_DATA_POINTCLOUD"))
        # Object orientation for corvette parts, mirror can work for non corvette parts too
        #orientation_box = tools_column.box()
        # mirror_col = orientation_box.column(align=True)
        
        tools_col.separator()
        mirror_col = tools_col
        mirror_col.label(text="Orientation") # icon = "ORIENTATION_GIMBAL"
        mirror_col_row = mirror_col.row(align = True)
        mirror_col_row.operator("object.nms_mirror", **icons.ui_icon("ARROW_LEFTRIGHT"))
        mirror_col_row.operator("object.nms_flip", **icons.ui_icon("DECORATE_OVERRIDE"))
        
                    
        # Mirroring tools
        mirroring_box = tools_column.box()
        mirroring_box_column = mirroring_box.column(align = True)
        
        
        if not build_tool.check_show_advanced_options:
            mirroring_box_column_label_row = mirroring_box_column.row(align = True)
            mirroring_box_column_label_row.label(text = "Mirror", **icons.ui_icon("MOD_MIRROR"))
            mirroring_box_column.prop(build_tool,"check_show_advanced_options", text = "Show more options") # icon = "OPTIONS"
            mirroring_box_column.separator()
            mirroring_box_column.operator( "object.nms_universal_mirror_x", **icons.ui_icon("ARROW_LEFTRIGHT") , text = "Mirror across X" )
        
        else :
            mirroring_box_column_label_row = mirroring_box_column.row(align = True)
            mirroring_box_column_label_row.label(text = "Mirror", **icons.ui_icon("MOD_MIRROR"))
            mirroring_box_column_label_row.prop(build_tool,"check_show_advanced_options", text = "", **icons.ui_icon("TRIA_UP")) # icon = "OPTIONS"
            
            mirroring_box_column.separator()
            mirroring_options_col = mirroring_box_column.column(align = True)
            mirroring_options_col.row(align = True).prop(build_tool,"center_of_reflection",expand=True)
            mirroring_options_col.row(align = True).prop(build_tool,"mirror_direction",expand=True)
            
            mirroring_box_column.separator()
            mirroring_box_column.prop(build_tool,"check_auto_duplicate")
            mirroring_box_column.operator("object.nms_advanced_mirror", **icons.ui_icon("MOD_MIRROR"), text = "Perform Mirror")
            
            

        from .. import build_analysis
        mirroring_box_column.operator("bbe.analyze_build", text=build_analysis.button(context), icon="COLOR")

        # Set Snap Operator assignments.
        # Default
        snap_op.prev_source = False
        snap_op.next_source = False
        snap_op.prev_target = False
        snap_op.next_target = False
        # Previous Target.
        snap_target_prev.prev_source = False
        snap_target_prev.next_source = False
        snap_target_prev.prev_target = True
        snap_target_prev.next_target = False
        # Next Target.
        snap_target_next.prev_source = False
        snap_target_next.next_source = False
        snap_target_next.prev_target = False
        snap_target_next.next_target = True
        # Previous Source.
        snap_source_prev.prev_source = True
        snap_source_prev.next_source = False
        snap_source_prev.prev_target = False
        snap_source_prev.next_target = False
        # Next Source.
        snap_source_next.prev_source = False
        snap_source_next.next_source = True
        snap_source_next.prev_target = False
        snap_source_next.next_target = False

