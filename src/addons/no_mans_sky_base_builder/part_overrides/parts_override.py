import os

FILE_PATH = os.path.dirname(os.path.realpath(__file__))
FOSSIL_PARTS_PATH = os.path.join(FILE_PATH,".." ,"models", "fossil_parts")

from . import (bone, bone_replacer, line, locked, message,
                             power_control, turret, u_bytebeatline, u_pipeline,
                             u_portalline, u_powerline)

override_classes = {
    bone_replacer.BONE_REPLACER: [
        "FOS_HEAD",
        "FOS_SKULL",
        "FOS_LIMBS",
        "FOS_TAIL",
        "FOS_BODY",
    ],
    bone.BONE: [
        os.path.splitext(filename)[0] for filename in os.listdir(FOSSIL_PARTS_PATH)
    ],
    turret. TURRET: ["B_TUR_A", "B_TUR_B", "B_TUR_C", "B_TUR_D", "B_TUR_E"],
    u_powerline.U_POWERLINE: ["U_POWERLINE"],
    u_pipeline.U_PIPELINE: ["U_PIPELINE"],
    u_portalline.U_PORTALLINE: ["U_PORTALLINE"],
    u_bytebeatline.U_BYTEBEATLINE: ["U_BYTEBEATLINE"],
    power_control.POWER_CONTROL: ["POWER_CONTROL"],
    locked.LOCKED: [
        "BASE_FLAG",
        "BRIDGECONNECTOR",
        "AIRLCKCONNECTOR",
        "FREIGHTER_CORE",
    ],
    message.MESSAGE: [
        "MESSAGEMODULE",
        "BYTEBEAT",
        "BYTEBEATSWITCH",
        "HOLO_DISCO_0",
        "FOS_BI",
        "FOS_BIRD",
        "FOS_BIRD_DIS",
        "FOS_BI_DIS",
        #"FOS_BODY",
        "FOS_BODY_DISP",
        "FOS_BODY_MNT",
        "FOS_GRUN",
        "FOS_GRUN_DIS",
        #"FOS_LIMBS",
        "FOS_LIMBS_DISP",
        "FOS_LIMBS_MNT",
        "FOS_QUAD",
        "FOS_QUAD_DIS",
        #"FOS_SKULL",
        "FOS_SKULL_DISP",
        "FOS_SKULL_MNT",
        #"FOS_TAIL",
        "FOS_TAIL_DISP",
        "FOS_TAIL_MNT",
        "FOS_WORM",
        "FOS_WORM_DIS",
    ],
}

# Runtime overrides registered by companion add-ons. They are checked before
# the built-in table so an integration can deliberately replace a native
# handler without editing this file's static catalog.
_runtime_overrides = {}


def register_override(class_ref, object_ids):
    for object_id in object_ids:
        _runtime_overrides[object_id] = class_ref


def unregister_override(object_ids):
    for object_id in object_ids:
        _runtime_overrides.pop(object_id, None)


def get_override_class(object_id):
    if object_id in _runtime_overrides:
        return _runtime_overrides[object_id]
    for class_ref, part_list in override_classes.items():
        if object_id in part_list:
            return class_ref
    return None


get_part_class = get_override_class


def get_override_classes():
    classes_dict = {}
    for class_ref, part_list in override_classes.items():
        for part in part_list:
            classes_dict[part] = class_ref
    classes_dict.update(_runtime_overrides)
    return classes_dict
