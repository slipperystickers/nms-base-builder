import bpy
import json
from .. import icons
from ..utils import asset_browser_utils
from ..utils.asset_browser_utils import (get_grid_settings, get_preferences,
                                         resolve_sub_categories)
ADDON_ID = asset_browser_utils.ADDON_ID

OP_OBJECT_SELECTED = "object.nms_asset_browser_object_selected"
OP_MORE_OPTIONS = "object.nms_asset_browser_more_options"


def _preview_icon(asset_icon_value):
    if asset_icon_value is not None:
        return asset_icon_value
    return bpy.types.UILayout.bl_rna.functions['label'].parameters['icon'].enum_items["MONKEY"].value


def _place_button(layout, object_id, is_preset, icon_value=None, *, text="", emboss=False):
    kwargs = {"text": text, "emboss": emboss}
    if icon_value is not None:
        kwargs["icon_value"] = _preview_icon(icon_value)
    button = layout.operator(OP_OBJECT_SELECTED, **kwargs)
    button.object_id = object_id
    button.is_preset = is_preset
    button.has_variants = False
    return button


def _variant_button(layout, object_id, variants):
    button = layout.operator(OP_OBJECT_SELECTED, text="", icon="PAUSE", emboss=False)
    button.object_id = object_id
    button.has_variants = True
    button.variants = json.dumps([object_id, *variants])


def _more_options_button(layout, object_id, is_fav):
    button = layout.operator(OP_MORE_OPTIONS, text="", icon="COLLAPSEMENU", emboss=False)
    button.object_id = object_id
    button.is_fav = is_fav


def draw_sub_category(pcoll , container, label, elements_list, number_of_columns, icon_size, grid_type = "Grid", show_title = True ):
            
    sub_category_column = container.column(align = True)
    sub_cat_label_row = sub_category_column.row()
    
    if show_title:
        sub_cat_label_row.label(text = label)
    
    subcategory_row = None

    for index,(obj_id,part_data) in enumerate(elements_list.items()):
        asset_icon_id = pcoll[obj_id].icon_id if obj_id in pcoll else None
        if index%number_of_columns == 0:
            subcategory_row = sub_category_column.row(align = True)
        
        drawing_function = draw_list_element if grid_type == "List" else draw_grid_element
        drawing_function(
            grid = subcategory_row,
            grid_icon_size = icon_size,
            object_id = obj_id,
            part_data = part_data,
            asset_icon_value = asset_icon_id,
        )
        
    remaining_rows = number_of_columns - len(elements_list)%number_of_columns
    if subcategory_row and remaining_rows != number_of_columns:
        for _ in range(remaining_rows):
            subcategory_row.column(align = True).label(text = "")

def draw_grid_element( 
        grid, 
        grid_icon_size, 
        object_id,
        part_data,
        asset_icon_value = None, 
    ):
    
    asset_name = part_data["name"]
    variants = part_data.get("variants",None)
    
    has_variants = bool(variants)
    is_fav = part_data.get("is_fav",False)
    is_preset = part_data.get("is_preset",False)
    
    if not asset_name:
        return
    
    asset_column = grid.box().column(align=True)
    controls = asset_column.split(factor=0.5, align=True)
    left = controls.row(align=True)
    left.alignment = 'LEFT'
    if not is_preset:
        _more_options_button(left, object_id, is_fav)
    else:
        left.label(text='')
    right = controls.row(align=True)
    right.alignment = 'RIGHT'
    if has_variants:
        _variant_button(right, object_id, variants)
    else:
        right.label(text='')
    image = asset_column.row(align=True)
    image.alignment = 'CENTER'
    image.template_icon(icon_value=_preview_icon(asset_icon_value), scale=grid_icon_size)

    # Keep the name as an operator, including Blender's right-click menu for
    # Quick Favorites. The separate pause button opens variants.
    _place_button(asset_column.row(align=True), object_id, is_preset, text=asset_name)
    
    
def draw_quick_access_element(layout, object_id, part_data, asset_icon_value=None):
    """Compact, clickable icon/name row for the BBE header popover."""
    if not part_data.get('name'):
        return
    row = layout.row(align=True)
    row.scale_y = 1.25
    _place_button(row, object_id, part_data.get('is_preset', False),
                  _preview_icon(asset_icon_value), text=part_data['name'], emboss=True)
    if part_data.get('variants'):
        _variant_button(row, object_id, part_data['variants'])
    if not part_data.get('is_preset'):
        _more_options_button(row, object_id, part_data.get('is_fav', False))


def draw_list_element( 
        grid, 
        grid_icon_size, 
        object_id, 
        part_data,
        asset_icon_value = None, 
    ):
    
    
    asset_name = part_data["name"]
    variants = part_data.get("variants",None)
    
    has_variants = bool(variants)
    is_fav = part_data.get("is_fav",False)
    is_preset = part_data.get("is_preset",False)
    
    element_row = grid.box().row(align=True)
    if not is_preset:
        _more_options_button(element_row, object_id, is_fav)
    image = element_row.column(align=True)
    image.template_icon(icon_value=_preview_icon(asset_icon_value), scale=grid_icon_size)
    _place_button(element_row.row(align=True), object_id, is_preset, text=asset_name)
    if has_variants:
        _variant_button(element_row, object_id, variants)
    


def draw_asset_browser(context, asset_browser_box, scene):
    
    asset_browser = scene.nms_asset_browser
    grid_type = asset_browser.enum_asset_browser_mode
    
    ab_category = asset_browser.asset_browser_caterogies
    ab_sub_category = asset_browser.asset_browser_sub_caterogies
    
    if grid_type == "List":
        icon_size, number_of_columns = get_grid_settings(
            context, "asset_browser_icon_size_list",
            "asset_browser_number_of_columns_list")
    else:
        icon_size, number_of_columns = get_grid_settings(
            context, "asset_browser_icon_size",
            "asset_browser_number_of_columns")
    
    
    show_serch_results = asset_browser.check_display_search_results
    
    pcoll = icons.get_asset_icons_pcoll()
    categories_data = asset_browser.get_categories_data()
    
    search_row = asset_browser_box.row(align=True)
    search_row.prop(asset_browser, "asset_broser_search_query", text="", icon='VIEWZOOM')
    search_row.separator()
    grid_options_row = search_row.row(align = True)
    grid_options_row.scale_x = 0.3
    grid_options_row.prop(asset_browser,"enum_asset_browser_mode", text = "View type", expand = True)
    setting_button = search_row.operator("object.nms_asset_browser_list_settings", icon = "SETTINGS", text = "")
    setting_button.grid_type = grid_type
    
    if grid_type == "Other":
        main_split = asset_browser_box.split(factor=0.13)
        left_col = main_split.column(align=True)
        right_box = main_split.column(align = True)
        
        left_col.label(text = "Asset Browser", icon='ASSET_MANAGER')
        left_col.separator()
        
        categories_col = left_col.column(align = True)
        categories_col.enabled = not asset_browser.check_display_search_results
        categories_col.label(text="Categories" )
        categories_col.prop(asset_browser,"asset_browser_caterogies", expand = True)
        categories_col.scale_y = 1.5
        
    else:
        right_box = asset_browser_box.column(align = True)
    
    right_box.separator()
    top_category_row = right_box.row(align = True)
    
    if show_serch_results:
        sub_cat_dict = asset_browser.get_search_results()
    else:
        sub_cat_dict = resolve_sub_categories(
            categories_data, ab_category, ab_sub_category)
    
    if show_serch_results:
        right_box.separator()
        result_row = right_box.row(align = True)
        if sub_cat_dict:
            result_row.alert = False
            result_row.label(text = f"Showing search results ( {len(sub_cat_dict)} found ) ...")
        else:
            result_row.alert = True
            result_row.label(text = f"No matching parts found")
    else:
        if grid_type == "Grid":
            top_category_column = top_category_row.column(align = True)
            top_category_column.label(text = "Categories")
            cats_per_row = 4
            cat_row = None
            for index, category_element in enumerate(asset_browser.get_enum_categories_list()):
                category = category_element[0]
                if index % cats_per_row == 0:
                    cat_row = top_category_column.row(align = True)
                cat_button = cat_row.operator(
                    "object.nms_asset_browser_category_selected",
                    text = category,
                    depress = category == ab_category
                )
                cat_button.category = category
            remaining_rows = cats_per_row - len(categories_data)%cats_per_row
            if cat_row and remaining_rows != cats_per_row:
                for _ in range(remaining_rows):
                    cat_row.column(align = True).label(text = "")
            
            top_category_column.separator()
            top_category_column.label(text = "Sub-Categories")
            cat_row = None
            sub_cats_enum = asset_browser.get_enum_sub_categories_list()
            for index, sub_cat in enumerate(sub_cats_enum):
                sub_category = sub_cat[0]
                if index % cats_per_row == 0:
                    cat_row = top_category_column.row(align = True)
                cat_button = cat_row.operator(
                    "object.nms_asset_browser_sub_category_selected",
                    text = sub_category,
                    depress = sub_category == ab_sub_category
                )
                cat_button.sub_category = sub_category
            remaining_rows = cats_per_row - len(sub_cats_enum)%cats_per_row
            if cat_row and remaining_rows != cats_per_row:
                for _ in range(remaining_rows):
                    cat_row.column(align = True).label(text = "")
        elif grid_type == "List":
            top_category_column = top_category_row.column(align = True)
            top_category_column.label(text = "Category")
            top_categories_row = top_category_column.row(align = True)
            top_categories_row.prop(asset_browser,"asset_browser_caterogies", expand = False, text = "" ) 
            sub_category_column = top_category_row.column(align = True)
            sub_category_column.label(text = "Sub-Category")
            sub_categories_row = sub_category_column.row(align = True)
            sub_categories_row.prop( asset_browser, "asset_browser_sub_caterogies", expand = False, text = "" )

    
    for subcategories, object_ids in sub_cat_dict.items():
        right_box.separator()
        draw_sub_category(
            pcoll = pcoll, 
            container = right_box, 
            label = subcategories,
            elements_list = object_ids, 
            number_of_columns = number_of_columns,
            icon_size = icon_size,
            grid_type = grid_type
        )
        

class NMS_UL_asset_browser_category_order(bpy.types.UIList):
    """Rows for reordering categories, with an up/down button per row.

    Favourites and non-favourites are kept in separate contiguous blocks by
    AssetBrowser.move_category, so a plain up/down swap here can never let a
    row cross into the other block - see asset_browser_utils.move_category.
    """

    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index):
        row = layout.row(align=True)
        row.label(text=item.category_name)

        controls_row = row.row(align=True)
        controls_row.alignment = "RIGHT"

        fav_button = controls_row.operator(
            "object.nms_asset_browser_category_favourite",
            text="",
            icon="PINNED" if item.is_fav else "UNPINNED",
            emboss=False,
        )
        fav_button.category = item.category_name

        controls_row.separator()

        up_button = controls_row.operator(
            "object.nms_asset_browser_category_move", text="", icon="TRIA_UP", emboss=False
        )
        up_button.category = item.category_name
        up_button.direction = "UP"
        down_button = controls_row.operator(
            "object.nms_asset_browser_category_move", text="", icon="TRIA_DOWN", emboss=False
        )
        down_button.category = item.category_name
        down_button.direction = "DOWN"
        
        
class NMS_UL_asset_browser_category(bpy.types.UIList):
    
    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index):
        asset_browser = data
        category = item.category_name
        ab_category = asset_browser.asset_browser_caterogies
        is_active = category == ab_category
        display_what = asset_browser.enum_asset_browser_what_to_display
        
        row = layout.row(align=True)
        row.label(text=item.category_name)
        
        
        #cat_button = row.operator(
        #    "object.nms_asset_browser_category_selected",
        #    text = item.category_name,
        #    emboss = False,
        #    icon = "TRIA_DOWN" if is_active and display_what == "asset" else "BLANK1" #"RIGHTARROW_THIN"
        #)
        #cat_button.category = category
        controls_row = row.row(align=True)
        controls_row.alignment = "RIGHT"
        fav_button = controls_row.operator(
            "object.nms_asset_browser_category_favourite",
            text="",
            icon="PINNED" if item.is_fav else "UNPINNED",
            emboss=False,
        )
        fav_button.category = item.category_name


def draw_asset_browser_left_options(context, asset_browser_box, scene):
    asset_browser = scene.nms_asset_browser
    prefs = get_preferences(context)
    display_what = asset_browser.enum_asset_browser_what_to_display

    ab_category = asset_browser.asset_browser_caterogies
    ab_sub_category = asset_browser.asset_browser_sub_caterogies
    fav_cats = asset_browser.get_favourite_categories()


    search_column= asset_browser_box.column(align=True)
    search_column.scale_y = 1.4
    from ..save_editor.function_help import corner_help
    heading = search_column.row(align=True)
    heading.label(text = "Search")
    corner_help(heading, 'ASSETS')
    search_column.prop(asset_browser, "asset_broser_search_query", text="", icon='VIEWZOOM')

    asset_browser_box.separator()
    if prefs is not None:
        size_column = asset_browser_box.column(align = True)
        size_column.prop(prefs, "asset_browser_icon_size_other",text = "Icon Size")
        size_column.prop(prefs, "asset_browser_number_of_columns_other", text = "Columns")
    asset_browser_box.separator()

    def draw_button(parent,operator ,label, what_type ,icon = "LEFT"):
        cat_element_row = parent.box().row(align = True)
        cat_element_row.scale_y = 0.7
        cat_container_row = cat_element_row.row(align = True)
        cat_row = cat_container_row.row(align = True)
        cat_row.alignment = "LEFT"
        cat_row.operator(
            operator,
            text = label,
            emboss = False,
            icon = "TRIA_RIGHT" if what_type == display_what else "BLANK1"#"RIGHTARROW_THIN"
        )

    cats_col = asset_browser_box.column(align = True)
    cats_header_row = cats_col.row(align = True)
    cats_header_row.label(text="Categories" )
    reorder_row = cats_header_row.row(align = True)
    reorder_row.alignment = "RIGHT"
    reorder_row.operator( "object.nms_asset_browser_category_reorder_popup", text = "Reorder", icon = "SORTSIZE" )
    cats_col.separator()
    draw_button(cats_col,"object.nms_asset_browser_show_fav_items", "Favourite Items", icon = "FUND", what_type= "fav")
    draw_button(cats_col,"object.nms_asset_browser_show_recent_items", "Recent Items", icon = "RECOVER_LAST", what_type= "recent")
    draw_button(cats_col,"object.nms_asset_browser_show_presets", "Presets", icon = "ASSET_MANAGER", what_type = "preset")
    cats_col.separator()

    # created either way: it used to exist only when there were favourites, so
    # anything that reached the favourite branch without them raised
    # UnboundLocalError
    
    
    fav_cats_col = cats_col.column(align = True)

    categories_col = cats_col.column(align = True)
    for category_element in asset_browser.get_enum_categories_list():
        category = category_element[0]

        is_active = category == ab_category
        is_expanded = (is_active and display_what == "asset"
                       and asset_browser.category_expanded)
        is_fav = fav_cats and category in fav_cats

        if is_fav:
            cat_element_col = fav_cats_col.box().column(align = True)
        else:
            cat_element_col = categories_col.box().column(align = True)

        cat_container_row = cat_element_col.row(align = True)
        cat_container_row.scale_y = 0.7
        cat_row = cat_container_row.row(align = True)
        cat_row.alignment = "LEFT"
        cat_button = cat_row.operator(
            "object.nms_asset_browser_category_selected",
            text = category,
            depress = is_active,
            emboss = is_active,
            icon = "TRIA_DOWN" if is_expanded else "TRIA_RIGHT"
        )
        cat_button.category = category

        cat_fav_button_row = cat_container_row.row(align = True)
        cat_fav_button_row.alignment = "RIGHT"
        fav_button = cat_fav_button_row.row(align = True).operator(
            "object.nms_asset_browser_category_favourite",
            text = "",
            icon = "PINNED" if is_fav else "UNPINNED",
            emboss = False
        )
        fav_button.category = category

        if is_expanded:
            sub_cat_main_row = cat_element_col.row(align = True)
            sub_cat_main_row.scale_y = 0.8
            sub_cat_gap_col = sub_cat_main_row.column(align = True)
            sub_cat_gap_col.scale_x = 0.8
            sub_cat_gap_col.label(text = "", icon = "BLANK1")
            sub_cat_col = sub_cat_main_row.column(align = True)
            sub_cat_col.separator()
            for sub_cat in asset_browser.get_enum_sub_categories_list():
                sub_category = sub_cat[0]
                is_sub_active = sub_category == ab_sub_category

                sub_cat_row = sub_cat_col.row(align = True)
                sub_cat_row.alignment = "LEFT"
                sub_cat_button = sub_cat_row.operator(
                    "object.nms_asset_browser_sub_category_selected",
                    text = sub_category,
                    depress = is_sub_active,
                    emboss = is_sub_active,
                    icon = "TRIA_RIGHT" if is_sub_active else "BLANK1"
                )
                sub_cat_button.sub_category = sub_category



def draw_asset_browser_right_options(context,asset_browser_box, scene, grid_type = "Grid"):
    asset_browser = scene.nms_asset_browser
    
    ab_category = asset_browser.asset_browser_caterogies
    ab_sub_category = asset_browser.asset_browser_sub_caterogies
    
    icon_size, number_of_columns = get_grid_settings(
        context, "asset_browser_icon_size_other",
        "asset_browser_number_of_columns_other")
    show_serch_results = asset_browser.check_display_search_results
    
    display_what = asset_browser.enum_asset_browser_what_to_display
    
    pcoll = icons.get_asset_icons_pcoll()
    categories_data = asset_browser.get_categories_data()
    
    
    if display_what == "search":
        sub_cat_dict = asset_browser.get_search_results()
    elif display_what == "fav":
        fav_data = asset_browser.get_favourite_objects_data()
        sub_cat_dict = {"Favourite Objects": fav_data}
    elif display_what == "recent":
        recent_data = asset_browser.get_recent_objects_data()
        sub_cat_dict = {"Recent Objects": recent_data}
    elif display_what == "preset":
        preset_data = asset_browser.get_preset_data()
        sub_cat_dict = {"Presets": preset_data}
    else:
        sub_cat_dict = resolve_sub_categories(
            categories_data, ab_category, ab_sub_category)
    
    for subcategories, object_ids in sub_cat_dict.items():
        asset_browser_box.separator()
        draw_sub_category(
            pcoll = pcoll, 
            container = asset_browser_box, 
            label = subcategories,
            elements_list = object_ids, 
            number_of_columns = number_of_columns,
            icon_size = icon_size,
            grid_type = grid_type
        )

class NMS_PT_asset_browser_panel(bpy.types.Panel):
    bl_label       = "Asset Browser"
    bl_idname      = "MY_PT_asset_browser_panel"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "NMS Asset Browser"
    bl_context = "objectmode"

    def draw_header(self, context):
        from .asset_browser_sidebar import panel_visibility
        panel_visibility(context, False)
    
    def draw(self, context):
        from .asset_browser_sidebar import panel_visibility
        panel_visibility(context, True)
        layout = self.layout     
        scene = context.scene
        browser = scene.nms_asset_browser
        row = layout.row(align=True)
        row.prop(browser, 'asset_broser_search_query', text='', icon='VIEWZOOM')
        settings = row.operator('object.nms_asset_browser_list_settings', text='', icon='SETTINGS')
        settings.grid_type = 'Grid'
        from ..save_editor.function_help import corner_help
        row.operator('object.nms_launch_asset_browser_window', text='', icon='WINDOW')
        corner_help(row, 'ASSETS')

        mode = browser.enum_asset_browser_what_to_display
        row = layout.row(align=True)
        for operator, label, icon, value in (
            ('object.nms_asset_browser_show_fav_items', 'Favorites', 'HEART', 'fav'),
            ('object.nms_asset_browser_show_recent_items', 'Recent', 'RECOVER_LAST', 'recent'),
            ('object.nms_asset_browser_show_presets', 'Presets', 'ASSET_MANAGER', 'preset'),
        ):
            row.operator(operator, text=label, icon=icon, depress=mode == value)

        layout.prop(browser, 'asset_browser_caterogies', text='Category')
        layout.prop(browser, 'asset_browser_sub_caterogies', text='Group')
        layout.label(text='Click an image to place; right-click for options')
        # The thumbnails are drawn over this native row. Keeping the panel's
        # content as tall as the visible picker lets Blender's own resize zone
        # follow the sidebar's left edge beside the thumbnails as well.
        scale = max(.75, context.preferences.system.ui_scale)
        picker_space = layout.row()
        picker_space.scale_y = max(1.0, (context.region.height - 180 * scale) / (20 * scale))
        picker_space.label(text=' ')


class NMS_PT_asset_browser_properties_panel(bpy.types.Panel):
    bl_label       = "Asset Browser"
    bl_idname      = "MY_PT_asset_browser_properties_panel"
    bl_space_type  = 'PROPERTIES'
    bl_region_type = 'WINDOW'
    bl_context     = 'modifier'
    bl_order       = 0 
    
    def draw(self, context):
        layout = self.layout     
        scene = context.scene
        draw_asset_browser_right_options(context, layout, scene)
        
        
class NMS_PT_asset_browser_new_window_panel_left(bpy.types.Panel):
    bl_label       = "Asset Browser"
    bl_idname      = "MY_PT_asset_browser_new_window_panel_left"
    bl_space_type  = 'PROPERTIES'
    bl_region_type = 'WINDOW'
    bl_context     = 'constraint'
    bl_order       = 0 
    
    def draw(self, context):
        layout = self.layout     
        scene = context.scene
        draw_asset_browser_left_options(context, layout, scene)
        
classes = (
    NMS_UL_asset_browser_category_order,
    NMS_UL_asset_browser_category,
    
    NMS_PT_asset_browser_properties_panel,
    NMS_PT_asset_browser_panel,
    NMS_PT_asset_browser_new_window_panel_left
)
        
