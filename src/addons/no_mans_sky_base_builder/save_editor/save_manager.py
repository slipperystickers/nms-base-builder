import bpy
import json
from bpy.app.handlers import persistent
from .. import builder, builder_v2, progress_ui
from . import save_editor_dependencies
from . import save_editor_utils, station_reference
from .save_editor_utils import BaseType, BaseData

BUILDER = builder.get_builder()

# A game-save destination belongs to this Blender session, not to a .blend
# received from another user. Keep only values here: RNA dies on file load.
_project_session = None
_restoring_session = False


def _build_identity(base):
    if base is None:
        return None
    return (base.save_context, base.base_type, base.user_data,
            base.galactic_address, base.base_name,
            getattr(base, "base_position", None) if base.base_type in BaseType.LOCATED_BASES else None)


@persistent
def capture_before_load(_dummy=None):
    global _project_session
    _project_session = None
    data = getattr(bpy.context.scene, 'nms_save_data', None)
    if data is not None and data.check_plugin_enabled:
        _project_session = dict(account=data.nms_account_selected,
                                slot=data.nms_save_slot, kind=data.nms_base_type,
                                build=_build_identity(data.get_current_base_identifiers()))


def restore_after_load():
    """Re-read the local destination after loading project geometry and UI."""
    global _project_session, _restoring_session
    previous, _project_session = _project_session, None
    _restoring_session = True
    try:
        SaveManager.enum_accounts_list = [('Default', 'Select Account', '')]
        SaveManager.enum_save_slots_list = [('Default', 'Select Save Slot', '')]
        SaveManager.data_save_slot = []
        SaveManager.extracted_base_data = {}
        SaveManager.save_data_loaded = False
        SaveManager.is_base_selected = False
        SaveManager.selected_base_type_tabs = dict.fromkeys(SaveManager.selected_base_type_tabs, 'Default')
        SaveManager.enum_base_list = [('Default', 'Select Corvette', '')]
        for scene in bpy.data.scenes:
            data = scene.nms_save_data
            data.check_plugin_enabled = False
            data.nms_account_selected = data.nms_save_slot = data.nms_base_index = 'Default'
            data.last_account_selected = data.last_slot_selected = 'Default'
            data.nms_base_type = BaseType.CORVETTE
            data.session_status = ''
        if not previous:
            return
        data = bpy.context.scene.nms_save_data
        data.check_plugin_enabled = True
        try:
            SaveManager.enum_accounts_list = data.get_accounts_enum_list(bpy.context)
            if previous['account'] not in {item[0] for item in SaveManager.enum_accounts_list}:
                data.session_status = 'Choose a local account and save slot to continue.'
                return
            data.nms_account_selected = data.last_account_selected = previous['account']
            SaveManager.enum_save_slots_list = data.get_save_slots_list()
            if previous['slot'] not in {item[0] for item in SaveManager.enum_save_slots_list}:
                data.session_status = 'Previous save slot is unavailable. Choose a save slot.'
                return
            data.nms_save_slot = data.last_slot_selected = previous['slot']
            slot = data.get_current_slot_data()
            SaveManager.extracted_base_data = save_editor_utils.extract_bases_list_from_save(slot['saves'])
            SaveManager.save_data_loaded = True
            data.nms_base_type = previous['kind']
            SaveManager.enum_base_list = data.get_bases_enum_list(SaveManager.extracted_base_data)
            # Index ordinals may change. Only restore an unambiguous match to
            # the same build; never choose a different ship as a fallback.
            matches = [base for base in SaveManager.extracted_base_data.get(data.get_base_type_key(), [])
                       if previous['build'] is not None and _build_identity(base) == previous['build']]
            if len(matches) == 1:
                base = matches[0]
                data.nms_base_index = f'Season:{base.base_index}' if base.save_context == 'Season' else str(base.base_index)
                SaveManager.selected_base_type_tabs[data.nms_base_type] = data.nms_base_index
                SaveManager.is_base_selected = True
            elif previous['build'] is not None:
                data.session_status = 'Previous build changed or is unavailable. Select the destination again.'
        except Exception as exc:
            data.reset_base_list()
            data.session_status = 'Could not reload the save. Choose the save slot again or refresh.'
            print(f'BBE Save Manager: project-load refresh failed: {exc}')
    finally:
        _restoring_session = False

#save data to persist within blend files.
class SaveManager(bpy.types.PropertyGroup):
    
    #array to populate accounts list
    enum_accounts_list = [('Default', 'Select Account', '')]
    #enum property list to display cave slots list
    
    enum_save_slots_list = [('Default', 'Select Save Slot', '')]
    #this stores data related to save slot like paths
    data_save_slot = []
    
    #this stores data for displaying list
    enum_base_list = [('Default', 'Select Corvette', '')]
    #this stores list of bases, in seperate arrays for both corvetets and normal bases 
    extracted_base_data = {}
    
    #These will track state of UI for easy access
    save_data_loaded= False
    is_base_selected = False
    is_base_list_load_first_time = True
    
    
    # for self.nms_base_type
    # stores index of selected base in alternative tab when tabs are switched
    selected_base_type_tabs = {
        BaseType.CORVETTE : "Default",
        BaseType.BASE : "Default",
        BaseType.SPACE_BASE : "Default",
        BaseType.STATION : "Default",
        BaseType.EXTERNAL_BASE : "Default"
    }
    
    # A toggle button at top of Save Editor section
    check_plugin_enabled: bpy.props.BoolProperty(
        name="Open save editor",
        description="Enable/disbale Plugin, \nClicking will check for dependencies, \nWill take few seconds to load for first time",
        default=False,
        update = lambda self, context: self.on_check_plugin_enabled(context),
        options={'SKIP_SAVE'}
    )

    # List to display miltiple accounts on same device
    nms_account_selected: bpy.props.EnumProperty(translation_context="BBEExtendedInterface", 
        name="",
        description="Account from which save file will be loaded",
        items = lambda self, context: SaveManager.enum_accounts_list,
        update = lambda self, context: self.on_account_list_change(),
        options={'SKIP_SAVE'}
    )
    
    #list of save slots form an account
    nms_save_slot: bpy.props.EnumProperty(translation_context="BBEExtendedInterface", 
        name="",
        description="Choose a save slot, \nThere can be multiple save slots within an account",
        items = lambda self, context: SaveManager.enum_save_slots_list,
        update = lambda self, context: self.on_save_slot_list_change(),
        options={'SKIP_SAVE'}
    )
    
    # this will display list of corvettes/bases after importing
    # This is index of base inside PersistentPlayerBase array
    # we store index so that it is easier to accress data later
    nms_base_index : bpy.props.EnumProperty(translation_context="BBEExtendedInterface", 
        name="base index",
        description="Base in the save file.",
        items = lambda self, context: SaveManager.enum_base_list,
        options={'SKIP_SAVE'},
        update = lambda self, context: self.on_base_selected()
    )
    
    # for radio button to select between corvette and base
    nms_base_type: bpy.props.EnumProperty(translation_context="BBEExtendedInterface", 
        name="base type",
        description="Type of the base, it can be a corvette and a normal planet base.",
        items = [
            (BaseType.CORVETTE, "Corvette", "Show saved Corvettes",'AUTO',0),
            (BaseType.BASE, "Planet", "show list of bases",'HOME',1),
            (BaseType.SPACE_BASE, "Space", "show list of space bases",'LIGHT_SUN',2),
            (BaseType.STATION, "Station", "Show owned station bases",'WORLD',4),
            (BaseType.EXTERNAL_BASE, "", "show list of External",'INTERNET',3),
        ],
        update = lambda self, context: self.on_base_type_selected(),
        options={'SKIP_SAVE'},
        default = BaseType.CORVETTE
    )
    
    station_key: bpy.props.StringProperty(default="")
    station_choices_json: bpy.props.StringProperty(default="{}")
    station_status: bpy.props.StringProperty(default="")
    station_transfer_reference: bpy.props.BoolProperty(default=False, options={'HIDDEN'})
    station_group: bpy.props.EnumProperty(translation_context="BBEExtendedInterface", name="Shape group", items=station_reference.group_items, update=station_reference.group_changed)
    station_option: bpy.props.EnumProperty(translation_context="BBEExtendedInterface", name="Option", items=station_reference.option_items, update=station_reference.option_changed)

    #these properties will store data of changes made in account and save slot
    last_account_selected:bpy.props.StringProperty(
        name="acocount_selected", default = "Default", options={'SKIP_SAVE'}
    )
    
    last_slot_selected:bpy.props.StringProperty(
        name="slot_selected", default = "Default", options={'SKIP_SAVE'}
    )
    session_status: bpy.props.StringProperty(default='', options={'SKIP_SAVE'})
    
    # this section stores parameters for pinned base which will persist within a blend file
    
    # A check to see if a base is pinned or not
    pinned_save_context: bpy.props.StringProperty(default='')

    pinned_base_check:bpy.props.BoolProperty(
        name="base suer_data", default = False
    )
    
    # meta data realated to base goes here and for some fields below
    pinned_base_name:bpy.props.StringProperty(
        name="base name", default = "None"
    )
    
    pinned_base_user_data:bpy.props.IntProperty(
        name="base user_data", default = -1
    )
    
    pinned_base_type:bpy.props.StringProperty(
        name="base type", default = "None"
    )
    
    pinned_base_index:bpy.props.IntProperty(
        name="base index", default =  -1
    )
    
    pinned_base_save_1:bpy.props.StringProperty(
        name="base save line 1", default = "None"
    )
    
    pinned_save_account:bpy.props.StringProperty(
        name="account number", default = "None"
    )
    
    pinned_save_slot_name:bpy.props.StringProperty(
        name="slot name", default = "None"
    )
    
    pinned_base_save_2:bpy.props.StringProperty(
        name="base save link 2", default = "None"
    )
    
    pinned_galactic_address:bpy.props.StringProperty(
        name="galactic address", default = "1"
    )
    
    # A toggle button at top of Save Editor section
    check_also_update_name: bpy.props.BoolProperty(
        name=" Also update name",
        description="Use 'Base Name' from Base Properties section as name for this.",
        default=False,
    )
    
    
    #this is called after clicking enable save editor button
    def on_check_plugin_enabled(self,context):
        if _restoring_session or not self.check_plugin_enabled:
            return
        save_editor_dependencies.installDependencies()
        if self.nms_base_type != BaseType.CORVETTE:
            self.nms_base_type = BaseType.CORVETTE
        SaveManager.enum_accounts_list = self.get_accounts_enum_list(context)
        
        # set value of accounts from values from last changes
        # check if stored account is present in newly generated list, if yes updated current list's index to it
        for account in SaveManager.enum_accounts_list:
            if account[0] == self.last_account_selected:
                self.nms_account_selected = self.last_account_selected
                break

    #function runs after an account is selected
    def on_account_list_change(self):
        if _restoring_session:
            return
        self.session_status = ''
        #store save slots list for easy access
        SaveManager.enum_save_slots_list = self.get_save_slots_list()
        
        # these values being eaqual means changes has been made using UI and not due to loading of data
        if self.last_account_selected != self.nms_account_selected :
            #clear any previous records
            self.reset_save_slot()
            self.reset_base_list()
        else :
            # set value of save slot from values from last changes
            # check if stored slot data is present in newly generated list, if yes updated current list's index to it
            for slot in SaveManager.enum_save_slots_list:
                if slot[0] == self.last_slot_selected:
                    self.nms_save_slot = self.last_slot_selected
                    break
        
        # store account selected so that it can be used as default values next time this feature is enabled
        self.last_account_selected = self.nms_account_selected
        
    # function that generates list of accounts to populate UI
    # this is called when save editor is enabled
    def get_accounts_enum_list(self,context):
        default_account_list_item = ("Default", "Select Account", "No account selected")
        accounts_list = save_editor_utils.get_accounts_list(context)
        accounts_enum_list = []
        for account in accounts_list:
            folder = account["folder"]
            steam_persona = account["steam_persona"]
            label = folder.name if steam_persona is None else f"{steam_persona} ( {folder.name[-3:]} )"
            accounts_enum_list.append((str(folder), label, ""))
        accounts_enum_list.insert(0, default_account_list_item)
        return accounts_enum_list
    
    # Called when an update happens Save Slots list UI
    # Extraction of base list from save file happens here
    def on_save_slot_list_change(self):
        if _restoring_session:
            return
        self.session_status = ''
        self.reset_base_list()
        # Start each selected save on the Corvette tab, without selecting a
        # Corvette from the list or enabling its import/export controls.
        if self.nms_base_type != BaseType.CORVETTE:
            self.nms_base_type = BaseType.CORVETTE
        current_slot_data = self.get_current_slot_data()
        
        if current_slot_data is not None:
            #extract list of corvettes and bases for display in UI
            SaveManager.extracted_base_data = save_editor_utils.extract_bases_list_from_save(current_slot_data["saves"])
            #convert that list to data that can be used by UI
            SaveManager.enum_base_list = self.get_bases_enum_list(SaveManager.extracted_base_data)
            SaveManager.save_data_loaded = True
            self.nms_base_index = "Default"
        
        self.last_slot_selected = self.nms_save_slot 
            
    # Called when account is selected
    # creates List of data for UI of save slots
    def get_save_slots_list(self):
        default_save_slot_list_item = ("Default", "Select Save Slot", "No save slot selected")
        account_selected = self.nms_account_selected
        
        #get list of save slots under selected account
        SaveManager.data_save_slot = save_editor_utils.get_save_slots_list(account_selected)
        
        #convert that list into something that UI can use
        enum_save_slots_list = []
        for slot in SaveManager.data_save_slot:
            save_name = slot["save_name"] 
            slot_list_name = "Slot "+str(slot["slot"])
            if save_name is not None:
                slot_list_name += " : "+save_name
            slot_element = (str(slot["slot"]), slot_list_name, "save slot for importing base/corvette")
            enum_save_slots_list.append(slot_element)
        
        #add a default value at top of the list    
        enum_save_slots_list.insert(0, default_save_slot_list_item)
        return enum_save_slots_list
    
    # Called when radio buttons that represent base type are clicked
    def on_base_type_selected(self):
        if _restoring_session:
            return
        cache = SaveManager.extracted_base_data if self.get_current_slot_data() is not None else {}
        SaveManager.enum_base_list = self.get_bases_enum_list(cache)
        # Rebuilds can remove the remembered build or leave a tab empty.
        # Restore its identifier only when it is still a selectable item;
        # inheriting an enum ordinal could silently select a different build.
        remembered = SaveManager.selected_base_type_tabs.get(self.nms_base_type, "Default")
        available = {item[0] for item in SaveManager.enum_base_list if item[0]}
        self.nms_base_index = remembered if remembered in available else "Default"
            

    # called either after base type is selected or save slot is changed
    def get_bases_enum_list(self, extracted_base_data):
        # default item to represent top of list, also acts ac propmt for user to interact with
        default_base_list_item = (
            "Default", 
            "Select " + self.get_base_type_string(), 
            "No base selected"
        )
        
        enum_bases = [default_base_list_item]
        key = self.get_base_type_key(self.nms_base_type)
        entries = list(extracted_base_data.get(key, []))
        for ctx in ('Main', 'Season'):
            selected = [b for b in entries if b.save_context == ctx]
            if not selected:
                continue
            enum_bases.append(('', 'Main save' if ctx == 'Main' else 'Expedition', ''))
            for base in selected:
                prefix = f'{base.user_data}. ' if base.base_type == BaseType.CORVETTE else ''
                ident = str(base.base_index) if ctx == 'Main' else f'Season:{base.base_index}'
                enum_bases.append((ident, f'{prefix}{base.base_name} [{base.parts_count} parts]',
                                   'Main save' if ctx == 'Main' else 'Expedition save'))

        return enum_bases
    
    # this is called when a base is selected from UI
    # this updates state values accourding to which element of list is selected
    def on_base_selected(self):
        if _restoring_session:
            return
        SaveManager.selected_base_type_tabs[self.nms_base_type] = self.nms_base_index
        SaveManager.is_base_selected = self.has_selected_base()

    def has_selected_base(self):
        """Use this scene's current save and tab, never the shared last selection."""
        return (self.is_base_data_loaded()
                and self.nms_base_index not in ('', 'Default')
                and self.get_current_base_identifiers() is not None)
    
    
    # called from a button to imprt selected bas into scene
    def import_base_from_save_file(self,context):
        base_index = self.nms_base_index
        
        # validate base index
        if not str(base_index).split(':')[-1].isdigit(): return 
        if int(str(base_index).split(':')[-1]) < 0: return
        
        # validate save slots
        current_slot_data = self.get_current_slot_data()
        if current_slot_data is None:
            print("Current slot data is None")
            return
        
        # validate parameters that identify a base within savefile
        base_identifiers = self.get_current_base_identifiers()
        if base_identifiers is None:
            print("Base Identifiers are None")
            return
        
        print("importing base")
        return self.import_base(context,base_identifiers,current_slot_data["saves"])
        
    # called to import objects into scene after validating
    # can be called from anywhere provided correct parameters
    def import_base(self, context, base_identifiers, save_links):
        
        #try to import json data from savefile and return error if data was not found
        with progress_ui.Activity('Reading save for import') as progress:
            progress.update(.08, 'Loading selected save point')
            imported_source = save_editor_utils.import_paticular_base_from_save(
                base_identifiers, save_links, progress=progress, with_ship_source=True)
            newly_imported_base, ship_source, source_error = imported_source or (None, None, '')
            progress.update(1.0, 'Importing models')
        if newly_imported_base is None:
            return "Error Importing base, base data is None"
        
        try:
            # convert imported base data to json
            nms_import_data = json.dumps(newly_imported_base)
            nms_base_json = json.loads(nms_import_data)
        except:
            return "Could not import base data, Incorrect json"
        source_count = len(nms_base_json.get('Objects', []))
        if not source_count:
            return 'Error importing base: the selected save entry has no parts'
            
        # Import json into scene
        nms_tools = context.scene.nms_main
        nms_tools.deserialise_from_data(nms_base_json)
        from .. import _store_build_source
        if ship_source is not None:
            _store_build_source(context.scene, ship_source, '.nmsship')
        elif source_error:
            context.scene['bbe_ship_source_error'] = source_error
        #BUILDER.deserialise_from_data(nms_base_json)
        previous_objects = set(context.scene.objects)
        builder_v2.deserialise_from_data(nms_base_json)
        imported = [o for o in context.scene.objects if o not in previous_objects and 'ObjectID' in o]
        if source_count and not imported:
            raise RuntimeError(f'The save contains {source_count} parts, but none appeared in the active scene ({context.scene.name}).')
        from .. import build_timer
        if getattr(base_identifiers, 'base_position', None) is None:
            base_identifiers.base_position = nms_base_json.get('Position')
        build_timer.bind(context.scene, build_timer.base_key(base_identifiers, save_links))
        if base_identifiers.base_type == BaseType.CORVETTE:
            from .corvette_actions import remember_ship_source
            remember_ship_source(context.scene, save_links, base_identifiers.save_context,
                                 base_identifiers.user_data, base_identifiers.base_name)
        is_station = nms_base_json.get("BaseType", {}).get("PersistentBaseTypes") == BaseType.STATION
        if is_station:
            station_reference.imported_station(context, nms_base_json, imported)
        build_timer.mark_saved(context.scene, build_timer.base_key(base_identifiers, save_links))
        from .. import import_view
        import_view.finish(context, imported)
        if is_station:
            return "Station parts and reference imported; choose the exterior with the Outliner eyes"
        #return a string for operators for status message
        if source_error:
            return f'Imported {len(imported)} parts. Ship package export unavailable: {source_error}'
        if len(imported) < source_count:
            return f'Imported {len(imported)} of {source_count} parts (some source parts have no available model)'
        return f'Imported {len(imported)} parts into {context.scene.name}'
    
    # called from operators/UI to export objects in scene to save file
    def export_base_to_save_file(self,context):
        self.refresh_before_export()
        
        # validate save slots
        current_slot_data = self.get_current_slot_data()
        if current_slot_data is None:
            raise ValueError('Select a save slot before exporting.')
        
        #collect base identifiers
        base_identifiers = self.get_current_base_identifiers()
        if base_identifiers is None:
            raise ValueError('Select the destination base before exporting.')
        
        # provide data to real export function
        return self.export_base(context, base_identifiers, current_slot_data["saves"],
                                selected_source=SaveManager.extracted_base_data)
        
    # collect data from scene and export it to save file
    def export_base(self, context, base_identifiers, save_links, selected_source=None):
        with progress_ui.Activity('Exporting to Save') as progress:
            progress.update(.02, 'Collecting scene parts')
            nms_tools = context.scene.nms_main
            serialised_base_objects_data = nms_tools.serialise(
                objects_only=True, for_save=True, progress=progress, progress_range=(.02, .13))
            prefs = context.scene.nms_base_tool
            new_base_name = prefs.string_base
            if not new_base_name or not new_base_name.strip():
                new_base_name = None

            from ..build_metadata import save_owner
            owner_override = save_owner(prefs)
            progress.update(.15, 'Preparing save points')
            result = save_editor_utils.save_base_to_save_file(
                serialised_base_objects_data, base_identifiers, save_links,
                base_name=new_base_name, progress=progress, owner_override=owner_override,
                selected_source=selected_source)

            from .. import build_timer
            build_timer.bind(context.scene, build_timer.base_key(base_identifiers, save_links))
            if result:
                build_timer.mark_saved(context.scene, build_timer.base_key(base_identifiers, save_links))
            progress.update(.95, 'Refreshing base list')
            self.refresh_bases_list()
            progress.update(1.0, 'Complete' if result else 'Base not found; nothing written')
            if result and base_identifiers.base_type == BaseType.CORVETTE:
                from .ship_repair import cockpit_warning
                if cockpit_warning(serialised_base_objects_data):
                    result += ' â€” ' + cockpit_warning(serialised_base_objects_data)
            return result
      
    # This functin collects data realated to base so that it can be identified in save file
    # since there is no unique property to identify a base, we prepare a fingerprint of that base with collection of properties
    def get_current_base_identifiers(self):
        if self.get_current_slot_data() is None:
            return None
        value = self.nms_base_index
        ctx = 'Season' if value.startswith('Season:') else 'Main'
        raw_index = value.split(':')[-1]
        if not raw_index.isdigit():
            return None
        entries = list(SaveManager.extracted_base_data.get(self.get_base_type_key(), []))
        return next((b for b in entries if b.base_index == int(raw_index) and b.save_context == ctx), None)

    # Fucntion for UI to check if base list should be displayed or not
    def is_base_data_loaded(self):
        return (self.get_current_slot_data() is not None
                and len(SaveManager.enum_base_list) > 0
                and SaveManager.save_data_loaded)
      
    # called to get data related to save slot selected
    def get_current_slot_data(self):
        if self.nms_account_selected != 'Default' and self.nms_save_slot != 'Default':
            for slot in SaveManager.data_save_slot:
                if str(slot["slot"]) == self.nms_save_slot:
                    return slot
        return None
    
    # called to reset values of save slot
    def reset_save_slot(self):
        SaveManager.save_data_loaded = False
        if SaveManager.enum_save_slots_list is not None:
            if len(SaveManager.enum_save_slots_list) > 0:
                if len(SaveManager.enum_save_slots_list[0][0]) > 0:
                    self.nms_save_slot = "Default"

    # called to reset values for base list
    def reset_base_list(self):
        SaveManager.is_base_selected = False
        SaveManager.save_data_loaded = False
        SaveManager.extracted_base_data = {}
        SaveManager.selected_base_type_tabs = {
            BaseType.CORVETTE: "Default",
            BaseType.BASE: "Default",
            BaseType.EXTERNAL_BASE: "Default",
            BaseType.SPACE_BASE: "Default",
            BaseType.STATION: "Default"
        }
        
        SaveManager.enum_base_list = self.get_bases_enum_list({})
        self.nms_base_index = "Default"
    
    #called by ui to display type of base
    def get_base_type_string(self,base_type = None):
        if base_type is None:
            base_type = self.nms_base_type
            
        return {BaseType.CORVETTE: "Corvette", BaseType.FREIGHTER: "Freighter", BaseType.STATION: "Station", BaseType.SPACE_BASE: "Space Base"}.get(base_type, "Base")
        
        
    # called when update base name is checked
    # To update name of base from 'Base Name' field in Base properties panel
    def update_base_name(self, new_base_name):
        
        if not new_base_name:
            return
        
        if not self.pinned_base_check:
            return
        
        #update name of pinned base
        old_base_name = self.pinned_base_name
        self.pinned_base_name = new_base_name
        
        # update name of base in UI lists without reading save file again
        # Changes made with this will be almost identical as reimporting bases list
        # this will improve speed of updating base
        t1 = (old_base_name, self.pinned_base_type, self.pinned_galactic_address)
        if SaveManager.save_data_loaded:
            base_type_key = self.get_base_type_key(self.pinned_base_type)
            base_list = SaveManager.extracted_base_data[base_type_key]
            for base in base_list:
                base:BaseData
                t2 = (base.base_name,base.base_type,base.galactic_address)
                if t1 == t2:
                    base.base_name= new_base_name
                    break
            SaveManager.enum_base_list = self.get_bases_enum_list(SaveManager.extracted_base_data)
        
        
                
    # called from operator to pin a base and save its metadata to persist within a blend file
    # it provides easy access to update button for users
    def pin_base(self):
        save_slot_name = self.nms_save_slot
        for slot in SaveManager.enum_save_slots_list:
            if slot[0] == self.nms_save_slot:
                save_slot_name = slot[1]
                break
        
        #collect all the deta form selected base and store it
        identifiers = self.get_current_base_identifiers()
        save_slot = self.get_current_slot_data()
        self.pinned_base_check = True
        self.pinned_base_name = identifiers.base_name
        self.pinned_save_context = identifiers.save_context or ''
        self.pinned_base_index = identifiers.base_index
        self.pinned_base_user_data = identifiers.user_data
        self.pinned_base_type = identifiers.base_type
        self.pinned_galactic_address = str(identifiers.galactic_address)
        self.pinned_save_account = self.nms_account_selected
        self.pinned_save_slot_name = save_slot_name
        self.pinned_base_save_1 = save_slot["saves"][0]
        self.pinned_base_save_2 = save_slot["saves"][1]
      
    # called from operators to unpin a pinned base
    def unpin_base(self):
        self.pinned_base_check = False
        self.pinned_base_name = "None"
        
    # called from operators to import a pinned base into scene
    def import_pinned_base(self,context):
        base_identifiers = self.get_pinned_base_identifiers()
        if base_identifiers is None:
            print("Pinned base identifiers are none")
            return
        self.import_base(context,base_identifiers, base_identifiers.save_slot)
    
    # called to save scene data to save file
    def export_pinned_base(self, context):
        base_identifiers = self.get_pinned_base_identifiers()
        
        if base_identifiers is None:
            raise ValueError('Pin the destination base before exporting.')
        
        result = self.export_base(context, base_identifiers, base_identifiers.save_slot)
            
        return result
        
    # collect data of pinned base and return it
    def get_pinned_base_identifiers(self):
        if self.pinned_base_check == False:
            return None
        
        if self.pinned_base_name == "None":
            return None
        
        save_links = [ 
            self.pinned_base_save_1, 
            self.pinned_base_save_2 
        ]
        
        base_data = BaseData()
        base_data.save_context = self.pinned_save_context or None
        base_data.base_index = self.pinned_base_index
        base_data.base_name = self.pinned_base_name
        base_data.user_data = int(self.pinned_base_user_data)
        base_data.galactic_address = self.pinned_galactic_address
        base_data.base_type = self.pinned_base_type
        base_data.save_slot = save_links
        
        return base_data

    #function for UI to display metadata realated to pinned base
    def get_pinned_base_location_details(self):
        if self.pinned_base_check:
            return f"{self.pinned_save_slot_name}, acc: ...{self.pinned_save_account[-3:]}"
        return None
        
    # for pinned backup button operator to call, will make backup of pinned base/corvette
    def backup_pinned_save_files(self):
        save_1 = self.pinned_base_save_1
        save_2 = self.pinned_base_save_2
        save_links = [save_1,save_2]
        save_editor_utils.backup_save_files(save_links)
        
    # for backup button operator to call, will make backup of selected save slot
    def backup_save_files(self):
        save_slot = self.get_current_slot_data()
        if save_slot is not None:
            save_links = save_slot["saves"]
            save_editor_utils.backup_save_files(save_links)
            
    def open_backup_folder_in_explorer(self):
        save_slot = self.get_current_slot_data()
        if save_slot is not None:
            save_links = save_slot["saves"]
            save_editor_utils.open_backup_folder_in_explorer(save_links)
        
    # called to check if savefolder path is valid or not 
    def validate_save_folder(self,save_folder):
        return save_editor_utils.validate_save_folder(save_folder)
    
    def get_base_type_key(self,base_type = None):
        basetype = base_type if base_type is not None else self.nms_base_type
        match basetype:
            case BaseType.CORVETTE:
                return "corvettes"
            case BaseType.FREIGHTER:
                return "corvettes"
            case BaseType.BASE: 
                return "bases"
            case BaseType.EXTERNAL_BASE:
                return "external"
            case BaseType.SPACE_BASE:
                return "space"
            case BaseType.SPACESTATION_BASE:
                return "spacestation"
        return "bases"
    
    def get_total_parts_count(self):
        return str(SaveManager.extracted_base_data["total_parts_count"])
    
    # returns pinned base data extracted from save file
    def get_pinned_base_data(self):
        identifiers = self.get_pinned_base_identifiers()
        save_slot = identifiers.save_slot
        pinned_base = save_editor_utils.import_paticular_base_from_save(identifiers, save_slot)
        return pinned_base
    
    def refresh_before_export(self):
        """Refresh the destination list if the game has written a newer or different save."""
        from . import ship_files
        slot = self.get_current_slot_data()
        if not slot:
            raise ValueError('Select an account and save slot before exporting.')
        latest = save_editor_utils.get_lastes_save_file_location(slot['saves'])
        cache = SaveManager.extracted_base_data
        if (str(latest) == cache.get('source_path')
                and ship_files.hashes([latest])[str(latest)] == cache.get('source_hash')):
            return False

        had_selection = self.get_current_base_identifiers() is not None
        self.refresh_bases_list()
        if had_selection and self.get_current_base_identifiers() is None:
            raise ValueError('Save list refreshed. The previous destination changed or is missing. Select the destination again.')
        return True

    # refresh list of bases/corvettes by importing fresh data form save file
    def refresh_bases_list(self):
        current_slot_data = self.get_current_slot_data()
        if current_slot_data is None:
            self.reset_base_list()
            return
        # Array positions are not identities: deletions/reordering in the game
        # can put an entirely different ship under the same enum identifier.
        previous = {}
        for kind, value in SaveManager.selected_base_type_tabs.items():
            if kind == self.nms_base_type:
                value = self.nms_base_index
            entries = SaveManager.extracted_base_data.get(self.get_base_type_key(kind), [])
            matches = [b for b in entries if
                       (f'Season:{b.base_index}' if b.save_context == 'Season' else str(b.base_index)) == value]
            previous[kind] = _build_identity(matches[0]) if len(matches) == 1 else None
        with progress_ui.Activity('Loading save list') as progress:
            progress.update(.08, 'Reading save points')
            SaveManager.extracted_base_data = save_editor_utils.extract_bases_list_from_save(
                current_slot_data["saves"], progress=progress)
            progress.update(1.0, 'Save list ready')
        SaveManager.save_data_loaded = True
        self.session_status = ''
        for kind, identity in previous.items():
            entries = SaveManager.extracted_base_data.get(self.get_base_type_key(kind), [])
            matches = [b for b in entries if identity is not None and _build_identity(b) == identity]
            value = 'Default'
            if len(matches) == 1:
                base = matches[0]
                value = f'Season:{base.base_index}' if base.save_context == 'Season' else str(base.base_index)
            elif identity is not None and kind == self.nms_base_type:
                self.session_status = 'Previous build changed or is unavailable. Select the destination again.'
            SaveManager.selected_base_type_tabs[kind] = value
        self.on_base_type_selected()
