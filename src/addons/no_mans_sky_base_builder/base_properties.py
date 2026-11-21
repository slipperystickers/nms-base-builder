import bpy
import json
from . import build_metadata
from .utils import python as python_utils

from bpy.props import (BoolProperty, EnumProperty, FloatProperty, IntProperty,
                       PointerProperty, StringProperty)
from bpy.types import Panel, PropertyGroup

class NMSBaseProperties(PropertyGroup):
    """
    Store Metadata related to imported base
    
    """
    
    metadata_source_json: StringProperty(default='', options={'HIDDEN'})
    metadata_baseline_json: StringProperty(default='', options={'HIDDEN'})
    metadata_owner_to_save: BoolProperty(default=False, options={'HIDDEN', 'SKIP_SAVE'})
    metadata_owner_reviewed: StringProperty(default='', options={'HIDDEN', 'SKIP_SAVE'})

    string_base: StringProperty(
        name="Base Name",
        description=("Name for the current Blender ship or base, saved with the project and applied when exporting. "
                     "Editing this field does not write to the game save. "
                     "Leave blank to keep the destination's saved name when overwriting it"),
        default="",
        maxlen=1024,
    )

    string_address: StringProperty(
        name="Galactic Address",
        description="The galactic address.",
        default="",
        maxlen=1024,
    )

    string_userdata: StringProperty(
        name="User Data",
        description="User Data - important for corvette bases.",
        default="",
        maxlen=1024,
    )

    string_base_type: bpy.props.EnumProperty(translation_context="BBEExtendedInterface", 
        name="The base type",
        description="Planet or Freighter.",
        items = [
            ("PlayerShipBase", "Corvette", "Base type is a corvette"),
            ("HomePlanetBase", "Base", "Base type is normal base"),
            ("FreighterBase", "Freighter", "Base type is freighter"),
            ("ExternalPlanetBase", "External", "Base type is External"),
            ("PlayerSpaceBase", "Space Base", "Base type is Space Base"),
            ("PlayerSpaceStationBase", "SpaceStation Base", "Base type is a Space Station"),
        ]
    )

    string_usn: StringProperty(
        name="USN", description="The username attribute.", default="", maxlen=1024
    )

    string_uid: StringProperty(
        name="UID", description="A user ID.", default="", maxlen=1024
    )

    string_lid: StringProperty(
        name="LID", description="Not sure what this is.", default="", maxlen=1024
    )

    string_ptk: StringProperty(
        name="PTK", description="Not sure what this is.", default="", maxlen=1024
    )

    string_ts: StringProperty(
        name="TS",
        description="Timestamp.",
        default="",
        maxlen=1024,
    )

    string_last_ts: StringProperty(
        name="LastUpdatedTimestamp",
        description="Timestamp - last updated timestamp.",
        default="",
        maxlen=1024,
    )

    float_pos_x: FloatProperty(
        name="X", description="The X position of the base in planet space.", default=0.0
    )

    float_pos_y: FloatProperty(
        name="Y", description="The Y position of the base in planet space.", default=0.0
    )

    float_pos_z: FloatProperty(
        name="Z", description="The Z position of the base in planet space.", default=0.0
    )

    float_ori_x: FloatProperty(
        name="X",
        description="The X orientation vector of the base in planet space.",
        default=0.0,
    )

    float_ori_y: FloatProperty(
        name="Y",
        description="The Y orientation vector of the base in planet space.",
        default=0.0,
    )

    float_ori_z: FloatProperty(
        name="Z",
        description="The Z orientation vector of the base in planet space.",
        default=0.0,
    )

    # Unimportant details...
    LastEditedById: StringProperty(
        name="LastEditedByID",
        description="LastEditedByID.",
        default="",
        maxlen=1024,
    )
    LastEditedByUsername_value: StringProperty(
        name="LastEditedByUsername",
        description="LastEditedByUsername.",
        default="",
        maxlen=1024,
    )
    original_base_version: IntProperty(
        name="OriginalBaseVersion", description="OriginalBaseVersion.", default=3
    )

    screenshot_at_x: FloatProperty(
        name="SAX",
        description="The X orientation vector of the screenshot.",
        default=1.0,
    )

    screenshot_at_y: FloatProperty(
        name="SAY",
        description="The Y orientation vector of the screenshot.",
        default=0.0,
    )

    screenshot_at_z: FloatProperty(
        name="SAZ",
        description="The Z orientation vector of the screenshot.",
        default=0.0,
    )

    screenshot_pos_x: FloatProperty(
        name="SPX",
        description="The X pos vector of the screenshot.",
        default=1.0,
    )

    screenshot_pos_y: FloatProperty(
        name="SPY",
        description="The Y pos vector of the screenshot.",
        default=1.0,
    )

    screenshot_pos_z: FloatProperty(
        name="SUZ",
        description="The Z pos vector of the screenshot.",
        default=0.0,
    )

    game_mode: StringProperty(
        name="GameMode", description="GameMode.", default="Unspecified"
    )

    platform_token: StringProperty(
        name="PlatformToken", description="PlatformToken.", default=""
    )

    is_reported: BoolProperty(
        name="IsReported", description="Is Reported.", default=False
    )

    is_featured: BoolProperty(
        name="IsFeatured", description="Is Featured.", default=False
    )

    difficulty_flags: IntProperty(
        name="DifficultyFlags", description="DifficultyFlags.", default=0
    )

    difficulty_preset: StringProperty(
        name="DifficultyPresetType",
        description="DifficultyPresetType.",
        default="Creative",
    )

    auto_power_setting: StringProperty(
        name="AutoPowerSetting", description="AutoPowerSetting.", default="UseDefault"
    )
    
    # extract base properties from json data provided and store them in fields
    def deserialise_from_data(self, nms_data):
        # Start bringing the data in.
        if "GalacticAddress" in nms_data:
            self.string_address = str(nms_data["GalacticAddress"])
        if "UserData" in nms_data:
            self.string_userdata = str(nms_data["UserData"])
        if "BaseType" in nms_data:
            self.string_base_type = str(nms_data["BaseType"]["PersistentBaseTypes"])
        if "Position" in nms_data:
            self.float_pos_x = nms_data["Position"][0]
            self.float_pos_y = nms_data["Position"][1]
            self.float_pos_z = nms_data["Position"][2]
        if "Forward" in nms_data:
            self.float_ori_x = nms_data["Forward"][0]
            self.float_ori_y = nms_data["Forward"][1]
            self.float_ori_z = nms_data["Forward"][2]
        if "Name" in nms_data:
            self.string_base = str(nms_data["Name"])
        if "LastUpdateTimestamp" in nms_data:
            self.string_last_ts = str(nms_data["LastUpdateTimestamp"])
        if isinstance(nms_data.get("Owner"), dict):
            Owner_details = nms_data["Owner"]
            self.string_uid = str(Owner_details.get("UID", ""))
            self.string_ts = str(Owner_details.get("TS", ""))
            self.string_lid = str(Owner_details.get("LID", ""))
            self.string_usn = str(Owner_details.get("USN", ""))
            self.string_ptk = str(Owner_details.get("PTK", ""))
        # Extras/Unimportant
        if "LastEditedById" in nms_data:
            self.LastEditedById = str(nms_data["LastEditedById"])
        if "LastEditedByUsername" in nms_data:
            self.LastEditedByUsername_value = str(nms_data["LastEditedByUsername"])
        if "OriginalBaseVersion" in nms_data:
            self.original_base_version = nms_data["OriginalBaseVersion"]
        if "ScreenshotAt" in nms_data:
            self.screenshot_at_x = nms_data["ScreenshotAt"][0]
            self.screenshot_at_y = nms_data["ScreenshotAt"][1]
            self.screenshot_at_z = nms_data["ScreenshotAt"][2]
        if "ScreenshotPos" in nms_data:
            self.screenshot_pos_x = nms_data["ScreenshotPos"][0]
            self.screenshot_pos_y = nms_data["ScreenshotPos"][1]
            self.screenshot_pos_z = nms_data["ScreenshotPos"][2]
        if "GameMode" in nms_data:
            self.game_mode = nms_data["GameMode"]["PresetGameMode"]
        if "PlatformToken" in nms_data:
            self.platform_token = nms_data["PlatformToken"]
        if "IsReported" in nms_data:
            self.is_reported = nms_data["IsReported"]
        if "IsFeatured" in nms_data:
            self.is_featured = nms_data["IsFeatured"]
        if "AutoPowerSetting" in nms_data:
            auto_power_container = nms_data.get("AutoPowerSetting", {})
            self.auto_power_setting = auto_power_container.get(
                "BaseAutoPowerSetting", "UseDefault"
            )
        if "Difficulty" in nms_data:
            difficulty_container = nms_data.get("Difficulty", {})
            sub_difficulty_container = difficulty_container.get("DifficultyPreset")
            self.difficulty_preset = sub_difficulty_container.get(
                "DifficultyPresetType", "Creative"
            )
            self.difficulty_flags = difficulty_container.get(
                "PersistentBaseDifficultyFlags", 0
            )
    
        # Preserve fields this version cannot display, including Owner types.
        self.metadata_source_json = build_metadata.encode(build_metadata.wrapper(nms_data))
        self.metadata_baseline_json = build_metadata.encode(self._serialise_fields())
        self.metadata_owner_to_save = False
        self.metadata_owner_reviewed = ''

    def serialise(self):
        current = self._serialise_fields()
        if not self.metadata_source_json:
            return current
        return build_metadata.merge_preserved(json.loads(self.metadata_source_json),
            json.loads(self.metadata_baseline_json), current)

    # Convert all the visible metadata into a dict.
    def _serialise_fields(self):
        # Try making the address an int, if not it should be a string.
        data = {
            "BaseVersion": 5,
            "OriginalBaseVersion": self.original_base_version,
            "GalacticAddress": python_utils.prefer_int(self.string_address),
            "Position": [self.float_pos_x, self.float_pos_y, self.float_pos_z],
            "Forward": [self.float_ori_x, self.float_ori_y, self.float_ori_z],
            "UserData": python_utils.prefer_int(self.string_userdata),
            "LastUpdateTimestamp": python_utils.prefer_int(self.string_last_ts),
            "RID": "",
            "Owner": {
                "UID": self.string_uid,
                "LID": self.string_lid,
                "USN": self.string_usn,
                "PTK": self.string_ptk,
                "TS": python_utils.prefer_int(self.string_ts),
            },
            "Name": self.string_base,
            "BaseType": {"PersistentBaseTypes": self.string_base_type},
            "LastEditedById": self.LastEditedById,
            "LastEditedByUsername": self.LastEditedByUsername_value,
            "ScreenshotAt": [
                self.screenshot_at_x,
                self.screenshot_at_y,
                self.screenshot_at_z,
            ],
            "ScreenshotPos": [
                self.screenshot_pos_x,
                self.screenshot_pos_y,
                self.screenshot_pos_z,
            ],
            "GameMode": {"PresetGameMode": self.game_mode},
            "PlatformToken": self.platform_token,
            "IsReported": self.is_reported,
            "IsFeatured": self.is_featured,
            "Difficulty": {
                "DifficultyPreset": {"DifficultyPresetType": self.difficulty_preset},
                "PersistentBaseDifficultyFlags": self.difficulty_flags,
            },
            "AutoPowerSetting": {"BaseAutoPowerSetting": self.auto_power_setting},
        }
        
        return data
    
    # Reset all fields
    def new_file(self):
        self.metadata_source_json = ''
        self.metadata_baseline_json = ''
        self.metadata_owner_to_save = False
        self.metadata_owner_reviewed = ''
        self.string_address = ""
        self.string_userdata = ""
        self.string_base = ""
        self.string_lid = ""
        self.string_ts = ""
        self.string_uid = ""
        self.string_usn = ""
        self.string_ptk = ""
        self.float_pos_x = 0
        self.float_pos_y = 0
        self.float_pos_z = 0
        self.float_ori_x = 0
        self.float_ori_y = 0
        self.float_ori_z = 0
        self.string_last_ts = ""
        self.LastEditedById = ""
        self.original_base_version = 3
        self.LastEditedByUsername_value = ""
        self.screenshot_at_x = 1
        self.screenshot_at_y = 0
        self.screenshot_at_z = 0
        self.screenshot_up_x = 0
        self.screenshot_up_y = 1
        self.screenshot_up_z = 0
        self.game_mode = "Unspecified"
        self.platform_token = ""
        self.is_reported = False
        self.is_featured = False
        self.difficulty_preset = "Creative"
        self.difficulty_flags = 0
        self.auto_power_setting = "UseDefault"
