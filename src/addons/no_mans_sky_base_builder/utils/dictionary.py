import os
import csv
import re
from . import python as python_utils

FILE_PATH = os.path.dirname(os.path.realpath(__file__))

RESOURCES_DIR = os.path.realpath(
    os.path.join(os.path.dirname(__file__),"..", "resources")
)

NICE_JSON = os.path.join(RESOURCES_DIR,"nice_names.json")
nice_name_dictionary = {}

PLACEMENT_HELP = {
    'B_HOP_A': (
        'Hopper Module: native B_HOP_A geometry, retained with its original export ID. '
        'The game supplies no localized name and its product icon depicts a different shape; '
        'BBE shows a preview rendered from the actual Hopper model.'
    ),
    'PIPE': (
        'Automatic pipe: NMS changes its shape to match nearby connections. '
        'BBE currently shows a straight preview. Use Pipe — Fixed to keep a straight pipe.'
    ),
    'PIPESHAPE': (
        'Fixed straight pipe: keeps its shape in NMS regardless of nearby connections. '
        'Use Curved Pipe for a fixed bend.'
    ),
    'CURVEPIPESHAPE': (
        'Fixed curved pipe: keeps its 90-degree bend in NMS regardless of nearby connections.'
    ),
    'B_DECO_U': (
        'Deathwrought Amplifier: the current NMS 7.10 game files assign this part '
        'the same native geometry as Aeron Pyramid. BBE keeps the correct '
        'Deathwrought part ID for export and shows the geometry the game supplies.'
    ),
    'B_LAN_B': (
        'Heavy Landing Gear is a hidden native landing-bay shell in NMS 7.10, '
        'not the deployable landing legs. It is absent from the normal game build menu. '
        'Use Landing Gear or Hydraulic Legs for the visible landing-leg parts.'
    ),
    'B_STR_AM_NE': (
        'Marrow Cap is a native part hidden from the normal NMS 7.10 build menu. '
        'It remains available in BBE and exports using its original game ID.'
    ),
    'B_STR_AN_NE': (
        'Bonespur Cap is a native part hidden from the normal NMS 7.10 build menu. '
        'It remains available in BBE and exports using its original game ID.'
    ),
    'B_STR_AB_NE': (
        'Hidden Hull Plating AB: NMS 7.10 supplies this model but no localized name. '
        'Its native thumbnail copies Argonaut Aerofoil; the actual model is different. '
        'It is hidden from the normal game build menu and retains its original export ID.'
    ),
    'B_STR_AA_NE': (
        'This hidden AA variant uses the same native geometry as Argonaut Aerofoil. '
        'It is grouped with the Argonaut variants and retains its original export ID.'
    ),
}


PART_DEFINITION = os.path.join(RESOURCES_DIR, "DT_PartDefinition.csv")
part_definition_dictionary = {}

def to_title_case(text):
    parts = re.split(r'(\([^)]*\))', text)
    return ''.join(
        part if part.startswith('(') else part.title()
        for part in parts
    )

def get_nice_names_diictionary():
    global nice_name_dictionary
    
    if not nice_name_dictionary:
        nice_name_dictionary = python_utils.load_dictionary(NICE_JSON)
        
    return nice_name_dictionary

def get_parts_definition():
    global part_definition_dictionary
    
    if not part_definition_dictionary:
        with open(PART_DEFINITION, "r", encoding="utf-16") as csv_file:
            csv_reader = csv.reader((x.replace("\0", "") for x in csv_file), delimiter=",")
            for index, row in enumerate(csv_reader):
                if not row or index == 0:
                    continue
                
                m_obj_id = row[0]
                part_definition_dictionary[m_obj_id] = row
                
    return part_definition_dictionary

def get_category_vise_objects():
    categories_list = {}
    part_definition = get_parts_definition()
    
    for _, part in part_definition.items():
        
        object_id = part[0].replace("^","")
        category = part[2]
        sub_category = part[4]
        nice_name = part[7]
        varaint_of = part[9].replace("^","")
        
        if not object_id or not nice_name:
            continue
        
        if object_id not in nice_name_dictionary:
            continue
        
        nice_name = to_title_case(nice_name)
        
        if category not in categories_list:
            categories_list[category] = {}
        if sub_category not in categories_list[category]:
            categories_list[category][sub_category] = {}
            
        sub_cat = categories_list[category][sub_category]
        
        
        if varaint_of == "None":
            if object_id not in sub_cat:
                sub_cat[object_id] = {}

            sub_cat[object_id]["name"] = nice_name
            
        else:
            if varaint_of not in sub_cat:
                sub_cat[varaint_of] = {
                    "name" : nice_name
                }
                
            if "variants" not in sub_cat[varaint_of]:
                sub_cat[varaint_of]["variants"] = []
            sub_cat[varaint_of]["variants"].append(object_id)
            
            
    return categories_list
        
    
