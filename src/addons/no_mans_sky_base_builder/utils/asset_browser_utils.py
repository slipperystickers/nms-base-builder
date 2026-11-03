"""Helpers behind the asset browser.

Everything in here is plain data work - reading the addon preferences, keeping
the favourites and recents file, turning the parts definition into a category
tree, filtering, sorting, and working out which slice of it a panel should
show. None of it touches the AssetBrowser property group, which is left to
hold the Blender state and call in here.

Keeping the two apart matters for more than tidiness: most of this runs from
enum item callbacks and panel draw code, where an unhandled exception means a
panel silently renders nothing, so these functions are written to return
something usable rather than to raise.
"""

import json
import os
import sys
import tempfile

import bpy

from . import dictionary

# The addon key in bpy.context.preferences.addons. Both this package and tools/
# sit one level under the addon, so the same expression works from either.
ADDON_ID = __package__.rsplit(".", 1)[0]

# How many recently used parts to remember. The list is rewritten every time a
# part is added, so it cannot be allowed to grow forever.
RECENTS_LIMIT = 5

# Used when the preferences cannot be reached, so a panel still draws something
# instead of throwing and leaving the region blank.
FALLBACK_ICON_SIZE = 3
FALLBACK_COLUMNS = 3

# Favourites and recents are kept in a file of our own rather than in the addon
# preferences. Blender stores preferences per version, under the addon that
# wrote them, so anything kept there is lost when the addon is reinstalled or
# when a new Blender version is set up. This file sits outside all of that.
APP_DIRECTORY_NAME = "NoMansSkyBaseBuilder"
STORE_DIRECTORY_NAME = "asset_browser"
STORE_FILE_NAME = "asset_browser.json"
STORE_VERSION = 1

# Point this at a folder to keep the store somewhere else - a synced drive, or
# a scratch folder while testing.
DATA_DIRECTORY_ENV = "NMS_BASE_BUILDER_DATA_DIR"

# What the store holds. These were preference names first, and the keys were
# kept the same so the migration is a straight copy.
STORE_KEYS = ("favourite_objects", "favourite_categories", "recent_objects", "category_order")

# The file is read on every redraw through the panels, so it is held in memory
# and only re-read when it changes underneath us - another Blender running at
# the same time, or the user editing it by hand.
_store_cache = None
_store_mtime = None

# Which preference holds the icon size and column count for each view mode.
GRID_SIZE_PROPERTIES = {
    "Grid": ("asset_browser_icon_size", "asset_browser_number_of_columns"),
    "List": ("asset_browser_icon_size_list", "asset_browser_number_of_columns_list"),
    "Other": ("asset_browser_icon_size_other", "asset_browser_number_of_columns_other"),
}


# --- preferences -------------------------------------------------------------

def get_preferences(context=None):
    """The addon preferences, or None when they are not available.

    Every read used to be a bare
    ``bpy.context.preferences.addons[ADDON_ID].preferences``. That raises
    KeyError whenever the addon is not registered through the addon system -
    while it is still registering, when the module is loaded directly for
    development, or before the user has enabled it - and several of those sit
    inside enum item callbacks and panel draw code, where one exception stops
    the whole browser from drawing.

    Args:
        context: Context to read from. Defaults to the current one.

    Returns:
        The preferences, or None.
    """
    context = context if context is not None else bpy.context
    addon = context.preferences.addons.get(ADDON_ID)
    return addon.preferences if addon is not None else None


def load_json_preference(name):
    """Read one of the json list preferences, whatever state it is in.

    Args:
        name (str): The preference attribute to read.

    Returns:
        list: The decoded list, empty if it is missing or unreadable.
    """
    prefs = get_preferences()
    if prefs is None:
        return []

    raw = getattr(prefs, name, "")
    if not raw:
        return []
    try:
        value = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return []
    return value if isinstance(value, list) else []


def save_preferences():
    """Flush the preferences to disk, without making a fuss if it fails.

    Nothing important is lost when this does not work - Blender writes the
    preferences out on exit anyway when auto-save is on - and it is not worth
    failing an operator over.
    """
    try:
        bpy.ops.wm.save_userpref()
    except RuntimeError:
        pass


def push_recent(recent_ids, object_id, limit=RECENTS_LIMIT):
    """Move `object_id` to the front of a most-recently-used list.

    Args:
        recent_ids (list): The current list, oldest last.
        object_id (str): The part just used.
        limit (int): How many to keep.

    Returns:
        list: A new list, most recent first, no longer than `limit`.
    """
    return list(dict.fromkeys([object_id, *recent_ids]))[:limit]


def _limited_recents(entries):
    """Keep the five newest distinct parts when reading an older store."""
    return list(dict.fromkeys(entries))[:RECENTS_LIMIT]


# --- the on disk store -------------------------------------------------------

def get_user_data_directory():
    """The folder holding everything that has to outlive the addon.

    Windows puts it in %APPDATA%, macOS in Application Support and Linux in
    $XDG_DATA_HOME, which is where each platform expects an application to keep
    this sort of thing. None of them are inside Blender's per-version
    configuration, which is the whole point.

    Returns:
        str: The directory path. It may not exist yet.
    """
    override = os.environ.get(DATA_DIRECTORY_ENV)
    if override:
        return override

    if sys.platform == "win32":
        root = os.environ.get("APPDATA") or os.path.expanduser("~")
    elif sys.platform == "darwin":
        root = os.path.join(os.path.expanduser("~"), "Library", "Application Support")
    else:
        root = (os.environ.get("XDG_DATA_HOME")
                or os.path.join(os.path.expanduser("~"), ".local", "share"))

    return os.path.join(root, APP_DIRECTORY_NAME)


def get_store_path():
    """Full path of the asset browser store file."""
    return os.path.join(get_user_data_directory(), STORE_DIRECTORY_NAME,
                        STORE_FILE_NAME)


def _empty_store():
    store = {"version": STORE_VERSION}
    store.update({key: [] for key in STORE_KEYS})
    return store


def _read_store_file(path):
    """Load the store from disk, or None if there is nothing usable there."""
    try:
        with open(path, "r", encoding="utf-8") as store_file:
            data = json.load(store_file)
    except (OSError, json.JSONDecodeError, ValueError):
        return None

    if not isinstance(data, dict):
        return None

    # a hand edited or truncated file should not be able to break the browser,
    # so anything that is not a list of strings is quietly dropped
    store = _empty_store()
    for key in STORE_KEYS:
        value = data.get(key)
        if isinstance(value, list):
            store[key] = [entry for entry in value if isinstance(entry, str)]
    return store


def _migrate_from_preferences():
    """Bring across whatever the preferences were holding, once.

    Anyone who used the browser before it kept its own file has their
    favourites and recents sitting in the addon preferences. This is the only
    thing that still reads them.
    """
    store = _empty_store()
    for key in STORE_KEYS:
        store[key] = load_json_preference(key)
    return store


def read_store():
    """The store, from memory when it has not changed on disk.

    Returns:
        dict: The store contents. Always has every key in STORE_KEYS.
    """
    global _store_cache, _store_mtime

    path = get_store_path()
    try:
        mtime = os.path.getmtime(path)
    except OSError:
        mtime = None

    if _store_cache is not None and mtime == _store_mtime:
        return _store_cache

    store = _read_store_file(path)
    if store is not None:
        limited = _limited_recents(store['recent_objects'])
        if limited != store['recent_objects']:
            store['recent_objects'] = limited
            if write_store(store):
                return _store_cache
    if store is None:
        # nothing on disk yet: either a first run, or an upgrade from the
        # version that kept all this in the preferences
        store = _migrate_from_preferences()
        store['recent_objects'] = _limited_recents(store['recent_objects'])
        if any(store[key] for key in STORE_KEYS):
            if write_store(store):
                return _store_cache

    _store_cache = store
    _store_mtime = mtime
    return store


def write_store(store):
    """Save the store, without risking the old one if the write fails.

    Args:
        store (dict): The contents to write.

    Returns:
        bool: True if it reached the disk.
    """
    global _store_cache, _store_mtime

    path = get_store_path()
    directory = os.path.dirname(path)
    temp_path = None
    try:
        os.makedirs(directory, exist_ok=True)
        # written beside the real file and moved into place, so a crash part way
        # through cannot leave a half written store behind
        handle, temp_path = tempfile.mkstemp(dir=directory, suffix=".tmp")
        with os.fdopen(handle, "w", encoding="utf-8") as temp_file:
            json.dump(store, temp_file, indent=2)
        os.replace(temp_path, path)
        temp_path = None
    except OSError as error:
        print("No Man's Sky Base Builder: could not save %s (%s)" % (path, error))
        if temp_path is not None:
            try:
                os.remove(temp_path)
            except OSError:
                pass
        return False

    _store_cache = store
    try:
        _store_mtime = os.path.getmtime(path)
    except OSError:
        _store_mtime = None
    return True


def clear_store_cache():
    """Forget the in-memory copy, so the next read comes off the disk."""
    global _store_cache, _store_mtime
    _store_cache = None
    _store_mtime = None


def load_stored_list(name):
    """One of the stored lists.

    Args:
        name (str): One of STORE_KEYS.

    Returns:
        list: A copy, so callers cannot edit the cache by accident.
    """
    return list(read_store().get(name, ()))


def save_stored_list(name, value):
    """Replace one of the stored lists and write the file.

    Args:
        name (str): One of STORE_KEYS.
        value (list): The list to store.

    Returns:
        bool: True if it reached the disk.
    """
    store = dict(read_store())
    store[name] = _limited_recents(value) if name == 'recent_objects' else list(value)
    return write_store(store)


def toggle_stored_list(name, value):
    """Add `value` to a stored list, or take it out if it is already there.

    Args:
        name (str): One of STORE_KEYS.
        value (str): The entry to toggle.

    Returns:
        list: The list as it now stands.
    """
    entries = load_stored_list(name)
    if value in entries:
        entries.remove(value)
    else:
        entries.append(value)

    save_stored_list(name, entries)
    return entries


# --- grid sizing -------------------------------------------------------------

def get_grid_size_properties(view_mode):
    """The preference names holding the icon size and columns for a view mode.

    Args:
        view_mode (str): "Grid", "List" or "Other".

    Returns:
        tuple: (icon size property name, column count property name)
    """
    return GRID_SIZE_PROPERTIES.get(view_mode, GRID_SIZE_PROPERTIES["Grid"])


def get_grid_settings(context, icon_size_prop, columns_prop):
    """Icon size and column count, or sane defaults if preferences are missing.

    Args:
        context: Context to read the preferences from.
        icon_size_prop (str): Preference holding the icon size.
        columns_prop (str): Preference holding the column count.

    Returns:
        tuple: (icon size, number of columns)
    """
    prefs = get_preferences(context)
    if prefs is None:
        return FALLBACK_ICON_SIZE, FALLBACK_COLUMNS
    return (getattr(prefs, icon_size_prop, FALLBACK_ICON_SIZE),
            getattr(prefs, columns_prop, FALLBACK_COLUMNS))


# --- the category tree -------------------------------------------------------

def build_category_tree(favourite_ids=None, nice_names=None):
    """Turn the parts definition into categories, sub categories and parts.

    Variants (a part marked as a variant of another) are folded into their
    parent's entry rather than getting one of their own.

    Args:
        favourite_ids (list): Part ids to mark as favourites. Read from the
            preferences when not given.
        nice_names (dict): The nice name lookup, to skip parts that cannot be
            built. Read from the dictionary when not given.

    Returns:
        dict: {category: {sub category: {object id: part data}}}
    """
    favourite_ids = (favourite_ids if favourite_ids is not None
                     else load_stored_list("favourite_objects"))
    nice_names = (nice_names if nice_names is not None
                  else dictionary.get_nice_names_diictionary())

    categories_list = {}
    part_definition = dictionary.get_parts_definition()

    for _, part in part_definition.items():

        object_id = part[0].replace("^", "")
        category = part[2]
        sub_category = part[4]
        nice_name = part[7]
        varaint_of = part[9].replace("^", "")

        if not object_id or not nice_name:
            continue

        if object_id not in nice_names:
            continue

        nice_name = dictionary.to_title_case(nice_name)
        if object_id == 'BASE_BUBPIPE_L':
            nice_name = 'Curved Bubble Duct'

        sub_cat = categories_list.setdefault(category, {}).setdefault(sub_category, {})

        if varaint_of == "None":
            entry = sub_cat.setdefault(object_id, {})
            entry["name"] = nice_name
            entry["is_fav"] = object_id in favourite_ids
        else:
            parent = sub_cat.setdefault(varaint_of, {"name": nice_name})
            parent.setdefault("is_fav", varaint_of in favourite_ids)
            parent.setdefault("variants", []).append(object_id)

    from .. import character_references
    categories_list['Character References'] = character_references.category_entries(favourite_ids)
    return categories_list


def order_categories(categories, favourite_categories, stored_order=None):
    """All category names, favourites first, each group in its saved order.

    A category that has never been placed - a new one, or the very first time
    this runs - is appended to its group in `categories`'s own order, so
    nothing goes missing just because it predates a reorder.

    Args:
        categories (iterable): Every category name that currently exists.
        favourite_categories (iterable): Names currently marked favourite.
        stored_order (list): The last saved order. Read from disk when None.

    Returns:
        list: Category names, favourites first.
    """
    if stored_order is None:
        stored_order = load_stored_list("category_order")

    valid_categories = list(categories)
    valid_set = set(valid_categories)
    favourite_set = set(favourite_categories)

    known_order = [name for name in stored_order if name in valid_set]
    known_set = set(known_order)
    full_order = known_order + [name for name in valid_categories if name not in known_set]

    favourites = [name for name in full_order if name in favourite_set]
    others = [name for name in full_order if name not in favourite_set]
    return favourites + others


def move_category(categories, favourite_categories, category, direction):
    """Move a category up or down within its favourite/other group.

    A move is refused rather than crossing into the other group - favourites
    stay above everything else no matter how far either side is nudged.

    Args:
        categories (iterable): Every category name that currently exists.
        favourite_categories (iterable): Names currently marked favourite.
        category (str): The category to move.
        direction (str): "UP" or "DOWN".

    Returns:
        list: The resulting order. Saved to disk when the move happened.
    """
    order = order_categories(categories, favourite_categories)
    if category not in order:
        return order

    favourite_set = set(favourite_categories)
    is_fav = category in favourite_set
    index = order.index(category)
    target = index + (-1 if direction == "UP" else 1)

    if target < 0 or target >= len(order):
        return order
    if (order[target] in favourite_set) != is_fav:
        return order

    order[index], order[target] = order[target], order[index]
    save_stored_list("category_order", order)
    return order


def build_enum_entries(names):
    """Blender enum entries for a list of names.

    Args:
        names (iterable): The names.

    Returns:
        list: [(name, name, name), ...]
    """
    return [(name, name, name) for name in names]


def build_sub_category_entries(categories_data, category):
    """Sub category enum entries for one category, "All" first.

    Args:
        categories_data (dict): The category tree.
        category (str): The category to list.

    Returns:
        list: [(name, name, name), ...]
    """
    entries = [("All", "All", "All")]
    entries.extend(build_enum_entries(categories_data.get(category, ())))
    return entries


def resolve_sub_categories(categories_data, category, sub_category):
    """The slice of the tree a panel should draw for a selection.

    These were plain dict lookups in the panels. An enum holds on to whatever
    string it last had, so an empty value on the very first draw, a category
    that has gone away since, or a sub category left over from a different
    category all raised KeyError and took the panel down with them.

    Args:
        categories_data (dict): The category tree.
        category (str): The selected category, which may be stale or empty.
        sub_category (str): The selected sub category, same.

    Returns:
        dict: {sub category: {object id: part data}}
    """
    if not categories_data:
        return {}

    if category not in categories_data:
        # fall back to the first real category rather than showing nothing
        category = next(iter(categories_data))

    sub_categories = categories_data[category]
    if (not sub_category or sub_category == "All"
            or sub_category not in sub_categories):
        return sub_categories

    return {sub_category: sub_categories[sub_category]}


# --- searching and slicing ---------------------------------------------------

def filter_objects(categories_data, search_filter):
    """Parts whose id or name contains `search_filter`, grouped by category.

    The ids and names are compared in lower case, so the query is lowered too -
    typing a capital letter used to return nothing at all ("wall" found 137
    parts, "Wall" found none).

    Args:
        categories_data (dict): The category tree.
        search_filter (str): What the user typed.

    Returns:
        dict: {category: {object id: part data}}
    """
    search_filter = (search_filter or "").strip().lower()
    if not search_filter:
        return {}

    search_results = {}
    for category, sub_categories in categories_data.items():
        for _, objects_list in sub_categories.items():
            for obj_id, obj_data in objects_list.items():

                obj_id_lower = obj_id.lower()
                name_lower = str(obj_data.get("name", "")).lower()

                if search_filter in obj_id_lower or search_filter in name_lower:
                    search_results.setdefault(category, {})[obj_id] = obj_data
    return search_results


def iter_all_parts(categories_data):
    """Every part in the tree, as (object id, part data) pairs.

    Args:
        categories_data (dict): The category tree.

    Yields:
        tuple: (object id, part data)
    """
    for sub_categories in categories_data.values():
        for objects_list in sub_categories.values():
            for obj_id, obj_data in objects_list.items():
                yield obj_id, obj_data


def apply_favourites(categories_data, favourite_ids):
    """Stamp `is_fav` across the tree and collect the favourites.

    Args:
        categories_data (dict): The category tree, modified in place.
        favourite_ids (list): The part ids marked as favourite.

    Returns:
        dict: {object id: part data} for the favourites.
    """
    favourites = {}
    for obj_id, obj_data in iter_all_parts(categories_data):
        is_fav = obj_id in favourite_ids
        obj_data["is_fav"] = is_fav
        if is_fav:
            favourites[obj_id] = obj_data
    return favourites


def collect_recent_objects(categories_data, recent_ids):
    """The part data for a list of recently used ids, in that order.

    Ids that are no longer in the tree are dropped rather than raising.

    Args:
        categories_data (dict): The category tree.
        recent_ids (list): Part ids, most recent first.

    Returns:
        dict: {object id: part data}
    """
    all_objects = dict(iter_all_parts(categories_data))
    return {obj_id: all_objects[obj_id]
            for obj_id in _limited_recents(recent_ids)
            if obj_id in all_objects}


def build_presets_data():
    """The presets, shaped like the part entries so the same drawing code works.

    Returns:
        dict: {preset name: preset data}
    """
    # imported here rather than at the top: preset pulls in part and the material
    # utils, and this module is imported from inside utils itself
    from ..preset import Preset

    return {
        preset_name: {
            "name": preset_name,
            "link": preset_link,
            "is_preset": True,
        }
        for preset_name, preset_link in Preset.get_presets().items()
    }
