import bpy
import bpy.utils.previews
import os
import json
import array
import zlib

import sys
import tempfile
import importlib
from collections.abc import Mapping

preview_collections = {}
_ICONS_REGISTERED = False
_ACTION_ICON_KEYS = {}

def extract_pcoll():
    """Reads the JSON file and loads icons into the Blender preview collection."""
    # Get the directory of the current script
    current_dir = os.path.dirname(os.path.abspath(__file__))
    json_path = os.path.join(current_dir,"resources","icons.json")
    
    # Initialize a new preview collection
    pcoll = bpy.utils.previews.new()
    
    # Load the JSON data
    with open(json_path, 'r') as f:
        data = json.load(f)
        
    icons = data['icons']
    
    # Resolve the absolute path to the icons directory
    icons_dir = os.path.normpath(os.path.join(current_dir,"images","icons"))
    
    # Iterate through the JSON and load each icon
    for icon_name, icon_filename in icons.items():
        icon_path = os.path.join(icons_dir, icon_filename)
        
        # Safety check to ensure the file exists before loading
        if not os.path.exists(icon_path):
            print(f"Warning: Icon not found at {icon_path}")
            continue
            
        # Load the image into the preview collection
        pcoll.load(icon_name, icon_path, 'IMAGE')
        
    icon_dir = os.path.join(os.path.dirname(__file__), "images","plugin_icon.png")
    pcoll.load("plugin_icon", icon_dir, 'IMAGE')
    toolbar_dir = os.path.join(current_dir, 'images', 'toolbar_icons')
    for name in ('io', 'color', 'builder', 'transform', 'batch', 'parts',
                 'cables', 'lighting', 'settings', 'extended_mark',
                 'support', 'save', 'recovery', 'assets'):
        pcoll.load('toolbar_' + name, os.path.join(toolbar_dir, name + '.png'), 'IMAGE')

    pcoll.load('credit_extended', os.path.join(current_dir, 'images',
                                             'bbe_credit_extended.png'), 'IMAGE')
    with open(os.path.join(current_dir, 'resources', 'ui_icon_map.json'), encoding='utf-8') as stream:
        action_map = json.load(stream)
    for name in sorted(set(action_map['actions'].values())):
        pcoll.load('action_' + name, os.path.join(current_dir, 'images',
                                                'action_icons', name + '.png'), 'IMAGE')
    _ACTION_ICON_KEYS.clear()
    _ACTION_ICON_KEYS.update({key: 'action_' + value for key, value in action_map['actions'].items()})
    _ACTION_ICON_KEYS.update({key: 'toolbar_' + value for key, value in action_map['toolbar'].items()})
        
    # Store the collection in our global dictionary under a specific key
    return pcoll


def get_asset_icons_pcol():
    """
    Directly imports the compiled Qt resource module and populates
    a Blender preview collection.
    """
    from . import qt_runtime
    qt_runtime.activate()
    try:
        from PySide6 import QtCore
    except ImportError:
        try:
            from PyQt6 import QtCore
        except ImportError:
            raise ImportError("PySide6 or PyQt6 must be installed in Blender's environment.")
    from .asset_browser.icons import icons
    
    # Extract resource data from Qt's virtual filesystem (:/)
    pcoll = bpy.utils.previews.new()
    addon_cache_dir = os.path.join(tempfile.gettempdir(), "blender_addon_icons")
    os.makedirs(addon_cache_dir, exist_ok=True)
    iterator = QtCore.QDirIterator(":/", QtCore.QDirIterator.IteratorFlag.Subdirectories)

    while iterator.hasNext():
        resource_path = iterator.next()
        if resource_path.startswith(":/qt-project.org") or resource_path.startswith(":/qt/"):
            continue

        qfile = QtCore.QFile(resource_path)
        if qfile.open(QtCore.QIODevice.OpenModeFlag.ReadOnly):
            file_data = qfile.readAll().data()
            qfile.close()

            clean_rel_path = resource_path.lstrip(":/")
            icon_key = os.path.splitext(clean_rel_path)[0].replace("/", "_")
            if not icon_key:
                icon_key = os.path.basename(resource_path).rsplit('.', 1)[0]

            if icon_key in pcoll:
                continue

            cache_file_path = os.path.join(addon_cache_dir, f"{icon_key}.png")
            if not os.path.exists(cache_file_path):
                with open(cache_file_path, "wb") as f:
                    f.write(file_data)

            pcoll.load(icon_key, cache_file_path, 'IMAGE')

    return pcoll

class _AssetIcons(Mapping):
    """Load previews for displayed parts. Listing catalogue IDs never decodes artwork."""
    def __init__(self, previews):
        self.previews = previews
        self.directory = os.path.join(os.path.dirname(__file__), 'images', 'asset_icons')
        self.files = None

    def _files(self):
        if self.files is None:
            try:
                filenames = os.listdir(self.directory)
            except FileNotFoundError:
                filenames = ()
            self.files = {filename[:-4]: filename for filename in filenames if filename.lower().endswith('.png')}
        return self.files

    def __iter__(self):
        return iter(self._files())

    def __len__(self):
        return len(self._files())

    def __contains__(self, key):
        return key in self._files()

    def __getitem__(self, key):
        if key not in self.previews:
            filename = self._files()[key]
            path = os.path.join(self.directory, filename)
            if key.startswith(('SET_', 'S_TOWER')):
                alternate = os.path.join(os.path.dirname(__file__), 'asset_browser', 'icons', filename)
                if os.path.isfile(alternate):
                    path = alternate
            self.previews.load(key, path, 'IMAGE')
        return self.previews[key]


_asset_icons = None


def get_asset_icons_pcoll():
    return _asset_icons


def get_icons_pscroll():
    return preview_collections["ui_icons"]


def draw_panel_icon(layout, name):
    layout.label(text='', icon_value=get_icons_pscroll()['toolbar_' + name].icon_id)


def ui_icon(name):
    """Use shared action artwork, retaining native icons for unmapped UI states."""
    key = _ACTION_ICON_KEYS.get(name)
    pcoll = preview_collections.get('ui_icons')
    if key and pcoll is not None and key in pcoll:
        return {'icon_value': pcoll[key].icon_id}
    return {'icon': name}


def ensure_sidebar_brand():
    pcoll=get_icons_pscroll()
    if 'sidebar_brand' in pcoll:return
    current_dir=os.path.dirname(__file__)
    # Keep the branding at source resolution instead of Blender's thumbnail
    # resolution. These preview pixels never become project datablocks.
    with open(os.path.join(current_dir, 'images', 'bbe_sidebar_brand.rgba.z'), 'rb') as stream:
        pixels = array.array('i', zlib.decompress(stream.read()))
    if len(pixels) != 1080 * 1080:
        raise ValueError('Invalid BBE sidebar branding pixels')
    brand = pcoll.new('sidebar_brand')
    brand.image_size = (1080, 1080)
    brand.image_pixels = pixels


def draw_sidebar_brand(layout, context):
    """Fit the top-aligned native preview to the sidebar's width and zoom."""
    ensure_sidebar_brand()
    region = context.region
    ui_scale = context.preferences.system.ui_scale
    left = region.view2d.region_to_view(0, 0)[0]
    right = region.view2d.region_to_view(region.width, 0)[0]
    scale = max(3.0, min(18.0, abs(right - left) / (20.0 * ui_scale) - 1.8))
    row = layout.row(align=True)
    row.alignment = 'LEFT'
    # The lower part of the square preview is transparent; only reserve the
    # visible banner height so the following controls sit directly beneath it.
    row.ui_units_y = scale * (98.0 / 360.0) + 0.3
    row.template_icon(icon_value=get_icons_pscroll()['sidebar_brand'].icon_id, scale=scale)

    credits = layout.column(align=True)
    first = credits.split(factor=0.40, align=True)
    first.scale_y = 0.8
    prefix = first.row(align=True)
    prefix.alignment = 'RIGHT'
    words = prefix.row(align=True)
    words.ui_units_x = 3.35
    words.alignment = 'RIGHT'
    words.label(text='Base Builder')
    colon = prefix.row(align=True)
    colon.ui_units_x = 0.55
    colon.alignment = 'RIGHT'
    colon.label(text=':')
    first.label(text='DjMonkey')
    credit = credits.split(factor=0.40, align=True)
    prefix = credit.row(align=True)
    prefix.alignment = 'RIGHT'
    word = prefix.row(align=True)
    word.ui_units_y = 1.0
    word.template_icon(icon_value=get_icons_pscroll()['credit_extended'].icon_id,
                       scale=3.35)
    colon = prefix.row(align=True)
    colon.ui_units_x = 0.55
    colon.alignment = 'RIGHT'
    colon.label(text=':')
    credit.label(text='FuriousFurby')

def check_register_icons():
    if not _ICONS_REGISTERED:
        register_icons()

def register_icons():
    global _ICONS_REGISTERED, _asset_icons
    _ICONS_REGISTERED = True
    
    preview_collections['ui_icons'] = extract_pcoll()
    preview_collections['asset_icons'] = bpy.utils.previews.new()
    _asset_icons = _AssetIcons(preview_collections['asset_icons'])


def unregister_icons():
    global _ICONS_REGISTERED, _asset_icons
    for pcoll in preview_collections.values():
        bpy.utils.previews.remove(pcoll)
    preview_collections.clear()
    _asset_icons = None
    _ACTION_ICON_KEYS.clear()
    _ICONS_REGISTERED = False
