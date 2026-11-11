"""Small, self-contained Blender interface themes chosen explicitly by users."""

import json
import os
from pathlib import Path

import bpy


# name, surface, raised surface, accent, text, viewport background
PALETTES = (
    ('SLATE', 'Slate', '#252b34', '#35404d', '#6589b5', '#e8eef6', '#292e36'),
    ('MIDNIGHT', 'Midnight', '#151c2b', '#26354c', '#578ada', '#e9f1ff', '#172033'),
    ('OCEAN', 'Ocean', '#17313b', '#274a55', '#40a8bf', '#eaf8fa', '#19323c'),
    ('FOREST', 'Forest', '#203028', '#344739', '#71ab76', '#ebf5e9', '#23342a'),
    ('EMBER', 'Ember', '#35261f', '#50382e', '#d58b4e', '#fff0df', '#32251f'),
    ('VIOLET', 'Violet', '#29243a', '#403653', '#9c80d1', '#f2ebff', '#29243b'),
    ('ROSE', 'Rose', '#382830', '#533b48', '#ce7899', '#fff0f5', '#382a33'),
    ('SAND', 'Sand', '#342e27', '#51463a', '#c8a771', '#faf1df', '#393329'),
)

THEME_ITEMS = (('BLENDER_DARK', 'Blender Dark', 'Restore Blender\'s dark theme'),
               ('BLENDER_LIGHT', 'Blender Light', 'Use Blender\'s light theme')) + tuple(
    (item[0], item[1], 'Apply the ' + item[1] + ' interface colors') for item in PALETTES)


def _rgb(value):
    if not isinstance(value, str):
        return tuple(value)
    return tuple(int(value[i:i + 2], 16) / 255 for i in (1, 3, 5))


def _paint_widgets(ui, surface, raised, accent, text):
    for name in ('wcol_regular', 'wcol_tool', 'wcol_toolbar_item', 'wcol_radio',
                 'wcol_text', 'wcol_option', 'wcol_toggle', 'wcol_num',
                 'wcol_numslider', 'wcol_box', 'wcol_curve', 'wcol_menu',
                 'wcol_pulldown', 'wcol_menu_back', 'wcol_pie_menu',
                 'wcol_tooltip', 'wcol_menu_item', 'wcol_scroll',
                 'wcol_progress', 'wcol_list_item', 'wcol_tab'):
        widget = getattr(ui, name)
        widget.inner = (*(_rgb(surface if name in ('wcol_menu', 'wcol_menu_back', 'wcol_box') else raised)), 1)
        widget.inner_sel = (*_rgb(accent), 1)
        widget.text = _rgb(text)
        widget.text_sel = (0, 0, 0) if sum(_rgb(accent)) > 1.8 else (1, 1, 1)
    ui.panel_back = (*_rgb(surface), 1)
    ui.panel_header = (*_rgb(raised), 1)
    ui.panel_text = _rgb(text)


def apply_theme(identifier):
    if identifier == 'BLENDER_DARK':
        bpy.ops.preferences.reset_default_theme()
        return
    if identifier == 'BLENDER_LIGHT':
        paths = bpy.utils.preset_paths('interface_theme')
        from pathlib import Path
        path = next((Path(directory) / 'Blender_Light.xml' for directory in paths
                     if (Path(directory) / 'Blender_Light.xml').is_file()), None)
        if path is None:
            raise RuntimeError('Blender Light theme is unavailable')
        bpy.ops.script.execute_preset(filepath=str(path), menu_idname='USERPREF_MT_interface_theme_presets')
        return
    palette = next((item for item in PALETTES if item[0] == identifier), None)
    if palette is None:
        raise ValueError('Unknown theme')
    _, _, surface, raised, accent, text, background = palette
    bpy.ops.preferences.reset_default_theme()
    apply_colors(surface, raised, accent, text, background,
                 background_type='RADIAL',
                 gradient_end=tuple(c * 0.28 for c in _rgb(background)),
                 grid=tuple(c * 0.45 for c in _rgb(accent)))


def apply_colors(surface, raised, accent, text, background, *,
                 background_type='SINGLE_COLOR', gradient_end=None, grid=None):
    theme = bpy.context.preferences.themes[0]
    _paint_widgets(theme.user_interface, surface, raised, accent, text)
    for name in ('view_3d', 'properties', 'outliner', 'text_editor', 'node_editor',
                 'image_editor', 'file_browser', 'preferences', 'dopesheet_editor',
                 'topbar', 'statusbar'):
        editor = getattr(theme, name, None)
        if editor is None:
            continue
        space = getattr(editor, 'space', None)
        if space is not None:
            if hasattr(space, 'back'):
                space.back = _rgb(surface)
            space.text = _rgb(text)
            space.text_hi = _rgb(accent)
            space.title = _rgb(text)
            space.header = (*_rgb(raised), 1)
            space.header_text = _rgb(text)
            space.header_text_hi = _rgb(accent)
    theme.regions.sidebars.back = (*_rgb(surface), 1)
    theme.regions.sidebars.tab_back = (*_rgb(surface), 1)
    # Dropdown chrome follows the viewport; selections retain their accent.
    for name in ('wcol_pulldown', 'wcol_menu', 'wcol_menu_back', 'wcol_menu_item', 'wcol_toolbar_item'):
        getattr(theme.user_interface, name).inner = (*_rgb(background), 1)
    theme.regions.scrubbing.back = (*_rgb(surface), 1)
    theme.regions.scrubbing.text = _rgb(text)
    theme.regions.channels.back = _rgb(surface)
    theme.regions.channels.text = _rgb(text)
    theme.regions.channels.text_selected = _rgb(accent)
    theme.regions.asset_shelf.back = (*_rgb(surface), 1)
    theme.regions.asset_shelf.header_back = (*_rgb(raised), 1)
    theme.common.anim.playhead = _rgb(accent)
    gradients = theme.view_3d.space.gradients
    gradients.background_type = background_type
    gradients.high_gradient = _rgb(background)
    gradients.gradient = _rgb(gradient_end if gradient_end is not None else background)
    if grid is not None:
        theme.view_3d.grid = (*_rgb(grid), theme.view_3d.grid[3])
    theme.view_3d.object_active = _rgb(accent)
    theme.view_3d.object_selected = _rgb(accent)


class BBE_OT_apply_theme(bpy.types.Operator):
    bl_idname = 'bbe.apply_theme'
    bl_label = 'Apply BBE Theme'
    bl_description = 'Change Blender interface colors; use Preferences > Themes to customize them'
    bl_options = {'INTERNAL'}

    theme: bpy.props.EnumProperty(items=THEME_ITEMS)

    def execute(self, context):
        try:
            apply_theme(self.theme)
        except (RuntimeError, ValueError, AttributeError) as exc:
            self.report({'ERROR'}, str(exc))
            return {'CANCELLED'}
        refresh_theme(context)
        return {'FINISHED'}


def refresh_theme(context):
    from . import bbe_chat
    bbe_chat.sync_theme()
    for window in context.window_manager.windows:
        for area in window.screen.areas:
            if area.type == 'VIEW_3D':
                area.spaces.active.shading.background_type = 'THEME'
            area.tag_redraw()


def _custom_path():
    return Path(bpy.utils.user_resource('CONFIG', path='bbe', create=True)) / 'custom_themes.json'


def custom_themes():
    try:
        data = json.loads(_custom_path().read_text(encoding='utf-8'))
        if not isinstance(data, dict):
            return {}
        return {name: preset for name, preset in data.items()
                if isinstance(name, str) and 0 < len(name) <= 40
                and _valid_preset(preset)}
    except (OSError, ValueError):
        return {}


def _valid_color(color):
    return (isinstance(color, list) and len(color) == 3
            and all(isinstance(v, (int, float)) and 0 <= v <= 1 for v in color))


def _valid_preset(preset):
    # Keep five-color presets from earlier BBE releases readable and unchanged.
    colors = preset.get('colors') if isinstance(preset, dict) else preset
    if not (isinstance(colors, list) and len(colors) == 5
            and all(_valid_color(color) for color in colors)):
        return False
    return not isinstance(preset, dict) or (
        preset.get('background_type') in {'SINGLE_COLOR', 'LINEAR', 'RADIAL'}
        and _valid_color(preset.get('gradient_end'))
        and _valid_color(preset.get('grid')))


def apply_preset(preset):
    if isinstance(preset, list):
        apply_colors(*preset)
    else:
        apply_colors(*preset['colors'], background_type=preset['background_type'],
                     gradient_end=preset['gradient_end'], grid=preset['grid'])


class BBE_OT_custom_theme(bpy.types.Operator):
    bl_idname = 'bbe.custom_theme'
    bl_label = 'Customize Theme'
    bl_description = 'Choose colors starting from your current theme and save a reusable preset'
    bl_options = {'INTERNAL'}

    name: bpy.props.StringProperty(name='Preset name', default='My Theme', maxlen=40)
    surface: bpy.props.FloatVectorProperty(name='Interface background', subtype='COLOR_GAMMA', size=3, min=0, max=1)
    raised: bpy.props.FloatVectorProperty(name='Buttons and headers', subtype='COLOR_GAMMA', size=3, min=0, max=1)
    accent: bpy.props.FloatVectorProperty(name='Accent and selection', subtype='COLOR_GAMMA', size=3, min=0, max=1)
    text: bpy.props.FloatVectorProperty(name='Text', subtype='COLOR_GAMMA', size=3, min=0, max=1)
    background: bpy.props.FloatVectorProperty(name='Viewport background', subtype='COLOR_GAMMA', size=3, min=0, max=1)
    background_type: bpy.props.EnumProperty(name='Viewport effect', default='SINGLE_COLOR', items=(
        ('SINGLE_COLOR', 'Solid', 'One background color'),
        ('LINEAR', 'Vertical gradient', 'Blend two colors from top to bottom'),
        ('RADIAL', 'Vignette', 'Blend from the center toward the edges')))
    gradient_end: bpy.props.FloatVectorProperty(name='Second color', subtype='COLOR_GAMMA', size=3, min=0, max=1)
    grid: bpy.props.FloatVectorProperty(name='Grid lines', subtype='COLOR_GAMMA', size=3, min=0, max=1, default=(0.25, 0.25, 0.25))


    def invoke(self, context, event):
        theme = context.preferences.themes[0]
        ui = theme.user_interface
        self.surface = ui.panel_back[:3]
        self.raised = ui.wcol_regular.inner[:3]
        self.accent = ui.wcol_regular.inner_sel[:3]
        self.text = ui.wcol_regular.text[:3]
        self.background = theme.view_3d.space.gradients.high_gradient[:3]
        self.background_type = theme.view_3d.space.gradients.background_type
        self.gradient_end = theme.view_3d.space.gradients.gradient[:3]
        self.grid = theme.view_3d.grid[:3]
        return context.window_manager.invoke_props_dialog(self, width=430, confirm_text='Save & Apply')

    def draw(self, context):
        layout = self.layout
        layout.use_property_split = True
        layout.prop(self, 'name')
        for key in ('surface', 'raised', 'accent', 'text'):
            layout.prop(self, key)
        layout.separator()
        layout.prop(self, 'background_type')
        label = {'SINGLE_COLOR': 'Viewport background', 'LINEAR': 'Top color', 'RADIAL': 'Center color'}
        layout.prop(self, 'background', text=label[self.background_type])
        if self.background_type != 'SINGLE_COLOR':
            layout.prop(self, 'gradient_end', text='Bottom color' if self.background_type == 'LINEAR' else 'Edge color')
        layout.prop(self, 'grid')
        layout.separator()
        layout.label(text='An existing preset with this name will be replaced.', icon='INFO')
        layout.label(text='Chat follows these colors automatically.')

    def execute(self, context):
        name = self.name.strip()
        if not name:
            self.report({'ERROR'}, 'Enter a preset name')
            return {'CANCELLED'}
        colors = [list(getattr(self, key)) for key in ('surface', 'raised', 'accent', 'text', 'background')]
        presets = custom_themes()
        preset = dict(colors=colors, background_type=self.background_type,
                      gradient_end=list(self.gradient_end), grid=list(self.grid))
        presets[name] = preset
        try:
            path = _custom_path()
            temp = path.with_suffix('.tmp')
            temp.write_text(json.dumps(presets, indent=2), encoding='utf-8')
            os.replace(temp, path)
        except OSError as exc:
            self.report({'ERROR'}, 'Could not save theme: ' + str(exc))
            return {'CANCELLED'}
        apply_preset(preset)
        refresh_theme(context)
        self.report({'INFO'}, 'Saved theme: ' + name)
        return {'FINISHED'}


class BBE_OT_load_custom_theme(bpy.types.Operator):
    bl_idname = 'bbe.load_custom_theme'
    bl_label = 'Apply Custom Theme'
    bl_description = 'Apply your saved interface colors'
    bl_options = {'INTERNAL'}

    name: bpy.props.StringProperty()

    def execute(self, context):
        colors = custom_themes().get(self.name)
        if colors is None:
            self.report({'ERROR'}, 'This saved theme is unavailable')
            return {'CANCELLED'}
        apply_preset(colors)
        refresh_theme(context)
        return {'FINISHED'}


class VIEW3D_PT_bbe_themes(bpy.types.Panel):
    bl_idname = 'VIEW3D_PT_bbe_themes'
    bl_label = 'BBE Themes'
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'HEADER'
    bl_ui_units_x = 17

    def draw(self, context):
        layout = self.layout
        layout.operator_context = 'INVOKE_DEFAULT'
        from .save_editor.function_help import corner_help
        heading = layout.row(align=True)
        heading.operator('bbe.custom_theme', text='Customize Colors & Gradients...', icon='PREFERENCES')
        corner_help(heading, 'THEMES')
        presets = custom_themes()
        if presets:
            layout.label(text='My themes')
            for name in sorted(presets, key=str.casefold):
                layout.operator('bbe.load_custom_theme', text=name, icon='COLOR').name = name
        layout.separator()
        layout.label(text='Blender theme')
        for identifier, name, _description in THEME_ITEMS:
            layout.operator('bbe.apply_theme', text=name, icon='COLOR').theme = identifier
        layout.separator()
        layout.label(text='Save in Preferences to keep it after restart.', icon='INFO')
