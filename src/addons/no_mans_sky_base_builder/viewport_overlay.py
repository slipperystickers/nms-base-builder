import bpy
import blf
import re
from .utils import dictionary
from .part import Part
from . import part_counts

nice_name_dictionary = dictionary.get_nice_names_diictionary()

ADDON_ID = __package__

# Store the handler globally so we can remove it later if needed
if "draw_handler" not in globals():
    draw_handler = None
    
def to_title_case(text):
    parts = re.split(r'(\([^)]*\))', text)
    return ''.join(
        part if part.startswith('(') else part.title()
        for part in parts
    )
        

def draw_text( font_id, text, start_x = 0, start_y = 0):
    blf.position(font_id, start_x, start_y, 0)
    blf.draw(font_id, text)

def draw_table(font_id,title, data_dict, start_x, start_y, line_spacing=15, column_padding=5):
    if not data_dict:
        return

    max_key_width = max(blf.dimensions(font_id, str(key))[0] for key in data_dict.keys())
    value_x = start_x + max_key_width + column_padding

    current_y = start_y
    
    for key, value in reversed(list(data_dict.items())):
        key_str = str(key) + " |"
        key_width = blf.dimensions(font_id, key_str)[0]
        key_x = value_x - column_padding - key_width

        blf.position(font_id, key_x + 6, current_y, 0)
        blf.draw(font_id, key_str)

        blf.position(font_id, value_x + 6, current_y, 0)
        blf.draw(font_id, str(value))

        current_y += line_spacing
        
    if title is not None:
        draw_text(font_id, title, start_x, current_y + 3)

def display_base_status(font_id, start_x = 20, start_y = 20):
    
    nms_base_tool = bpy.context.scene.nms_base_tool
    part_count = part_counts.displayed(bpy.context.scene)
    
    base_data = {}
    
    if nms_base_tool.string_base and nms_base_tool.string_address:
        #base_type = nms_base_tool.string_base_type
        #base_type_string = "Corvette" if base_type == "PlayerShipBase" else "Base"
        #title = f"{base_type_string} imported :"
        
        title= None
        base_data["Name"] = nms_base_tool.string_base
        #base_data["Base Type"] = base_type_string
        start_y -= 20
    else:
        title = "No Base/Corvette imported :"
        
    base_data["Part Count"] = str(part_count)
    
    draw_table(
        font_id=font_id, 
        data_dict=base_data,
        title = title,
        start_x=start_x, 
        start_y=start_y,
    )
    
        
def display_active_object_prop(font_id, start_x=10, start_y=100 ):
    
    active_object = bpy.context.active_object
    selected_objects = bpy.context.selected_objects
    
    if active_object is None:
        return
    
    if active_object not in selected_objects or "ObjectID" not in active_object:
        return
    
    object_id = active_object[Part.PROP_OBJECT_ID]
    
    object_table_data = {"Part ID" : object_id}
    if object_id in nice_name_dictionary:
        object_table_data["Part Name"] = to_title_case(nice_name_dictionary.get(object_id))
    object_table_data["Colour"] = f"{active_object.get('readonly:Colour')}"
    object_table_data["Material"] = f"{active_object.get('readonly:Material')}"
    
    draw_table(
        font_id=font_id, 
        data_dict=object_table_data,
        title = "Active-Object Properties :",
        start_x=start_x, 
        start_y=start_y,
    )
    
    

def draw_callback_px(self, context):
    prefs = bpy.context.preferences.addons[ADDON_ID].preferences
    if prefs.nms_check_show_part_count or prefs.nms_check_show_active_object_properties:
        try:
            
            # Set the font ID (0 is the default Blender font)
            font_id  = 0
            blf.size(font_id, 11) # Font size
            blf.color(font_id, 1.0, 1.0, 1.0, 1.0) # RGBA (White)
            blf.enable(font_id, blf.SHADOW)
            blf.shadow(font_id, 3, 0, 0, 0, 1.0)
            blf.shadow_offset(font_id, 0, -1)
            region = bpy.context.region
            if prefs.nms_check_show_part_count:
                if prefs.nms_part_count_position == "Bottom":
                    base_prop_x_pos = 20
                    base_prop_y_pos = 40
                else:
                    base_prop_x_pos = 65 
                    base_prop_y_pos = region.height - 150
                display_base_status(font_id, start_x=base_prop_x_pos, start_y=base_prop_y_pos)
            
            if prefs.nms_check_show_active_object_properties:
                if prefs.nms_active_object_properties_position == "Bottom":
                    if prefs.nms_part_count_position == "Bottom":
                        prop_x_pos = 25
                        prop_y_pos = 90
                    else :
                        prop_x_pos = 25
                        prop_y_pos = 20
                else:
                    if prefs.nms_part_count_position == "Bottom":
                        prop_x_pos = 65 
                        prop_y_pos = region.height - 215
                    else:
                        prop_x_pos = 65 
                        prop_y_pos = region.height - 280
                display_active_object_prop(font_id, start_x=prop_x_pos, start_y=prop_y_pos )
                
        except AttributeError as error:
            print(error)
            pass
        

def register_draw():
    global draw_handler
    unregister_draw()
    if draw_handler is None:
        # Add the draw handler to the 3D Viewport ('POST_PIXEL' draws 2D text over the 3D scene)
        draw_handler = bpy.types.SpaceView3D.draw_handler_add(
            draw_callback_px, (None, None), 'WINDOW', 'POST_PIXEL'
        )
        # Force a redraw of the viewport to see the changes immediately
        for area in getattr(bpy.context.screen, 'areas', ()):
            if area.type == 'VIEW_3D':
                area.tag_redraw()

def unregister_draw():
    global draw_handler
    if draw_handler is not None:
        bpy.types.SpaceView3D.draw_handler_remove(draw_handler, 'WINDOW')
        draw_handler = None
        
        # Shutdown can clear the screen before add-ons are unregistered.
        for area in getattr(bpy.context.screen, 'areas', ()):
            if area.type == 'VIEW_3D':
                area.tag_redraw()
