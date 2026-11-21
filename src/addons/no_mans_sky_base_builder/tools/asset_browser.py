
import bpy
from .. import i18n
from ..utils import asset_browser_utils
from ..utils.mirror_utils import ShowMessageBox


ADDON_ID = asset_browser_utils.ADDON_ID
RECENTS_LIMIT = asset_browser_utils.RECENTS_LIMIT

# Re-exported so the panels and operators can keep importing them from here.
get_preferences = asset_browser_utils.get_preferences
load_json_preference = asset_browser_utils.load_json_preference
load_stored_list = asset_browser_utils.load_stored_list


class NMSCategoryOrderItem(bpy.types.PropertyGroup):
    """One row of the category reorder list."""

    category_name: bpy.props.StringProperty()
    is_fav: bpy.props.BoolProperty()


class AssetBrowser(bpy.types.PropertyGroup):
    """The asset browser's Blender state.

    The data work - building the category tree, searching it, and keeping the
    favourites and recents file - lives in utils/asset_browser_utils.py. This
    holds what Blender needs: the properties, the enum callbacks and the caches
    those callbacks read from.
    """

    enum_categories = []
    enum_sub_categories = []
    view_revision = 0

    def invalidate_view(self):
        AssetBrowser.view_revision += 1
        from . import asset_browser_grid, asset_browser_sidebar
        asset_browser_grid.request_redraw()
        asset_browser_sidebar.request_redraw()

    check_display_search_results: bpy.props.BoolProperty(
        name = "Display Search Results",
        default = False
    )

    asset_broser_search_query: bpy.props.StringProperty(
        name="Search",
        default="",
        options={'TEXTEDIT_UPDATE'},
        update = lambda self, context: self.on_search_entered()
    )

    asset_browser_caterogies: bpy.props.EnumProperty(translation_context="BBEExtendedInterface", 
        name="Categories",
        description="Catagories",
        items = lambda self, context: self.get_categories(),
        update = lambda self, context: self.on_category_selected(),
        default = 0
    )

    asset_browser_sub_caterogies: bpy.props.EnumProperty(translation_context="BBEExtendedInterface", 
        name="Subcategory",
        description="Subcategory",
        # asked for directly rather than read off a class attribute that update
        # callbacks reassign, so the entries always match the chosen category
        items = lambda self, context: self.extract_enum_sub_categories(),
        update=lambda self, context: self.on_sub_category_selected(),
    )

    enum_asset_browser_mode: bpy.props.EnumProperty(translation_context="BBEExtendedInterface", 
        name="View Mode",
        description="Asset Browser View Mode",
        items = [
            ("List", "List", "List","ALIGN_LEFT", 0),
            ("Grid", "Grid", "Grid","LIGHTPROBE_VOLUME",1)
        ],
        default = "Grid"
    )

    enum_asset_browser_what_to_display: bpy.props.EnumProperty(translation_context="BBEExtendedInterface", 
        name="Dislay What",
        description="Choose what type of data to display",
        items = [
            ("asset", "asset", "asset"),
            ("search", "search", "search"),
            ("fav", "fav", "fav"),
            ("recent", "recent", "recent"),
            ("preset", "preset", "preset")
        ],
        default = "asset",
        update = lambda self, context: self.invalidate_view()
    )

    category_order_list: bpy.props.CollectionProperty(type=NMSCategoryOrderItem)
    category_order_list_index: bpy.props.IntProperty()
    
    category_list: bpy.props.CollectionProperty(type=NMSCategoryOrderItem)
    category_list_index: bpy.props.IntProperty()

    category_expanded: bpy.props.BoolProperty(
        name="Expand category", default=True,
        update=lambda self, context: self.invalidate_view())

    favourite_categories = []
    favourite_objects_data = {}
    recent_objects_data = {}
    presets_data = {}

    categories_data = {}
    search_results = {}
    # Sub category enum entries, kept per category. Blender needs the strings a
    # dynamic enum hands back to stay alive for as long as it might use them, so
    # the same list object is returned every time rather than a fresh one.
    sub_categories_by_category = {}

    def initialise_asset_browser(self):
        self.get_categories_data()
        self.refresh_categories()

        AssetBrowser.sub_categories_by_category.clear()

        AssetBrowser.presets_data = self.get_presets_data()
        AssetBrowser.enum_sub_categories = self.extract_enum_sub_categories()

        if self.enum_asset_browser_what_to_display == "search":
            search_text = self.asset_broser_search_query
            search_results = self.filter_objects_with_string(search_text)
            AssetBrowser.search_results = search_results

        self.invalidate_view()

    def refresh_categories(self):
        """Rebuild the category enum, favourites first in their saved order.

        Called on first use and again whenever a category's favourite state or
        order changes, so the categories enum and the reorder list stay in
        sync with what is actually stored.

        Note:
            Rebuilt in place rather than appended to. The class attribute
            outlives unregister, so running this again after an addon
            disable/enable used to leave the category list doubled - 16
            categories became 32.
        """
        categories_data = self.get_categories_data()
        favourite_categories = self.get_favourite_categories()
        AssetBrowser.pinned_categories = frozenset(favourite_categories)
        ordered_categories = asset_browser_utils.order_categories(
            categories_data.keys(), favourite_categories
        )
        # Dynamic enums are stored as integers in .blend files. Seed the IDs
        # from the previous release's display order before sorting any rows.
        ids = asset_browser_utils.load_stored_list('category_enum_ids')
        if not ids:
            old = asset_browser_utils.load_stored_list('category_order')
            old.extend(name for name in categories_data if name not in old)
            ids = sorted(dict.fromkeys(name for name in old if name in categories_data),
                         key=lambda name: name not in favourite_categories)
            asset_browser_utils.save_stored_list('category_enum_ids', ids)
        missing = [name for name in ordered_categories if name not in ids]
        if missing:
            ids.extend(missing)
            asset_browser_utils.save_stored_list('category_enum_ids', ids)
        AssetBrowser.enum_categories[:] = [
            (name, name, name, ids.index(name)) for name in ordered_categories
        ]


    def get_grid_size_prop_string(self):
        return asset_browser_utils.get_grid_size_properties(
            self.enum_asset_browser_mode
        )


    def get_grid_sizes(self):
        """Icon size and column count for the current view mode.

        These live on the addon preferences. This used to read them off self,
        where they do not exist, so any call raised AttributeError.
        """
        icon_size_prop, number_of_columns_prop = self.get_grid_size_prop_string()
        return asset_browser_utils.get_grid_settings(
            bpy.context, icon_size_prop, number_of_columns_prop
        )


    def get_categories(self):
        if not AssetBrowser.enum_categories:
            self.initialise_asset_browser()
        return AssetBrowser.enum_categories

    def on_category_selected(self):
        self.clear_search()
        self.category_expanded = True
        self.enum_asset_browser_what_to_display = "asset"
        AssetBrowser.enum_sub_categories = self.extract_enum_sub_categories()
        self.asset_browser_sub_caterogies = "All"
        self.invalidate_view()


    def on_sub_category_selected(self):
        self.clear_search()
        self.enum_asset_browser_what_to_display = "asset"
        AssetBrowser.enum_sub_categories = self.extract_enum_sub_categories()

        self.invalidate_view()

    def get_enum_sub_categories(self):
        return self.extract_enum_sub_categories()

    def extract_enum_sub_categories(self):
        """Sub category enum entries for the category that is selected.

        This is on the enum item callback path, so it runs on every redraw. It
        used to rebuild the whole category tree from the parts definition each
        time - 4.7 ms a call against 0.0007 ms for the cached lookup - and hand
        back a brand new list of strings every time, which is exactly what a
        dynamic enum is not supposed to do.
        """
        prop_caterogies = self.asset_browser_caterogies

        cached = AssetBrowser.sub_categories_by_category.get(prop_caterogies)
        if cached is not None:
            return cached

        sub_categories = asset_browser_utils.build_sub_category_entries(
            self.get_categories_data(), prop_caterogies
        )

        AssetBrowser.sub_categories_by_category[prop_caterogies] = sub_categories
        return sub_categories

    def get_categories_data(self):
        if not AssetBrowser.categories_data:
            AssetBrowser.categories_data = self.get_category_vise_objects()
            self.set_favourite_objects(
                asset_browser_utils.load_stored_list("favourite_objects")
            )
            self.set_recent_objects(
                asset_browser_utils.load_stored_list("recent_objects")
            )

        return AssetBrowser.categories_data

    def get_enum_categories_list(self):
        return AssetBrowser.enum_categories

    def get_enum_sub_categories_list(self):
            return AssetBrowser.enum_sub_categories

    def clear_search(self):
        if self.asset_broser_search_query:
            self.asset_broser_search_query = ""

    def toggle_category(self, category):
        was_open = (self.asset_browser_caterogies == category
                    and self.category_expanded
                    and self.enum_asset_browser_what_to_display == "asset"
                    and not self.asset_broser_search_query)
        self.clear_search()
        if self.asset_browser_caterogies != category:
            self.asset_browser_caterogies = category
        self.enum_asset_browser_what_to_display = "asset"
        self.category_expanded = not was_open

    def on_search_entered(self):
        search_filter = self.asset_broser_search_query
        if search_filter and len(search_filter) > 2:
            self.check_display_search_results = True
            self.enum_asset_browser_what_to_display = "search"
            search_results = self.filter_objects_with_string(search_filter)
            AssetBrowser.search_results = search_results
        else:
            self.check_display_search_results = False
            self.enum_asset_browser_what_to_display = "asset"
            AssetBrowser.search_results = {}

        self.invalidate_view()

    def filter_objects_with_string(self,search_filter):
        return asset_browser_utils.filter_objects(
            self.get_categories_data(), search_filter, i18n.part_names()
        )

    def get_search_results(self):
        return AssetBrowser.search_results


    def get_category_vise_objects(self):
        return asset_browser_utils.build_category_tree()

    def set_favourite_categories(self, favourite_categories):
        AssetBrowser.favourite_categories = favourite_categories
        self.refresh_categories()
        # Cheap enough to always keep in sync, so the reorder popup reflects a
        # favourite toggled from either the popup itself or the main panel.
        self.refresh_category_order_list()

    def get_favourite_categories(self, context = None):
        # the default used to be bpy.context itself, which binds whatever context
        # happened to exist at import time rather than the live one
        if not AssetBrowser.favourite_categories:
            AssetBrowser.favourite_categories = (
                asset_browser_utils.load_stored_list("favourite_categories")
            )
        return AssetBrowser.favourite_categories

    def refresh_category_order_list(self):
        """Rebuild the reorder list rows from the current category order."""
        favourite_categories = self.get_favourite_categories()
        self.category_order_list.clear()
        for category_element in AssetBrowser.enum_categories:
            category = category_element[0]
            item = self.category_order_list.add()
            item.category_name = category
            item.is_fav = category in favourite_categories

    def move_category(self, category, direction):
        categories_data = self.get_categories_data()
        favourite_categories = self.get_favourite_categories()
        asset_browser_utils.move_category(
            categories_data.keys(), favourite_categories, category, direction
        )
        self.refresh_categories()
        self.refresh_category_order_list()

    def set_favourite_objects(self, new_favourite_objects):
        AssetBrowser.favourite_objects_data = asset_browser_utils.apply_favourites(
            self.get_categories_data(), new_favourite_objects
        )
        self.invalidate_view()


    def get_favourite_objects_data(self):
        return AssetBrowser.favourite_objects_data

    def show_favourite_obejcts(self):
        self.clear_search()
        self.enum_asset_browser_what_to_display = "fav"


    def set_recent_objects(self, new_recent_objects):
        AssetBrowser.recent_objects_data = (
            asset_browser_utils.collect_recent_objects(
                self.get_categories_data(), new_recent_objects
            )
        )
        self.invalidate_view()

    def get_recent_objects_data(self):
            return AssetBrowser.recent_objects_data

    def show_recent_objects(self):
        self.clear_search()
        self.enum_asset_browser_what_to_display = "recent"

    def add_to_recents_list(self, object_id):
        recent_objs = asset_browser_utils.push_recent(
            asset_browser_utils.load_stored_list("recent_objects"), object_id
        )
        asset_browser_utils.save_stored_list("recent_objects", recent_objs)
        self.set_recent_objects(recent_objs)

    def get_presets_data(self):
        return asset_browser_utils.build_presets_data()

    def show_presets(self):
        self.clear_search()
        self.enum_asset_browser_what_to_display = "preset"

    def get_preset_data(self):
        return AssetBrowser.presets_data
