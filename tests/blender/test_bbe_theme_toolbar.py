"""Run in Blender background mode on both supported profiles."""

from pathlib import Path
import sys
import tempfile
import json

import bpy

root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(root / 'src/addons'))
import no_mans_sky_base_builder as addon

addon.register()
try:
    from no_mans_sky_base_builder import bbe_themes
    from no_mans_sky_base_builder.tools_menu import base_builder_menu
    assert len(bbe_themes.THEME_ITEMS) == 10
    for file in ('__init__.py', 'tools_menu/base_builder_menu_presentation.py'):
        assert 'Join Selected Bubble Ducts' not in (root / 'src/addons/no_mans_sky_base_builder' / file).read_text(encoding='utf-8')
    assert 'DOWNARROW_HLT' not in base_builder_menu.draw_toolbar.__code__.co_consts
    assert bpy.ops.object.nms_launch_asset_browser_window.get_rna_type()
    for identifier, _name, _description in bbe_themes.THEME_ITEMS:
        bbe_themes.apply_theme(identifier)
        assert bpy.context.preferences.themes[0].user_interface.wcol_regular.text[0] >= 0
    from no_mans_sky_base_builder import bbe_chat
    with tempfile.TemporaryDirectory() as directory:
        original_custom = bbe_themes._custom_path
        bbe_themes._custom_path = lambda: Path(directory) / 'themes.json'
        original = bbe_chat._settings_path
        bbe_chat._settings_path = lambda: Path(directory) / 'settings.json'
        try:
            colors = {'surface': (0.1, 0.15, 0.2), 'raised': (0.2, 0.25, 0.3),
                      'accent': (0.8, 0.4, 0.2), 'text': (0.9, 0.95, 1),
                      'background': (0.05, 0.1, 0.15)}
            assert bpy.ops.bbe.custom_theme(name='My Ocean', **colors) == {'FINISHED'}
            assert 'My Ocean' in bbe_themes.custom_themes()
            bbe_themes.apply_theme('BLENDER_DARK')
            assert bpy.ops.bbe.load_custom_theme(name='My Ocean') == {'FINISHED'}
            theme = bpy.context.preferences.themes[0]
            assert all(abs(a-b)<1/255+1e-5 for a,b in zip(theme.user_interface.wcol_regular.inner_sel[:3], colors['accent']))
            assert all(abs(a-b)<1/255+1e-5 for a,b in zip(theme.view_3d.space.gradients.high_gradient[:3], colors['background']))
            for editor in ('dopesheet_editor', 'statusbar', 'topbar', 'properties'):
                space = getattr(theme, editor).space
                assert all(abs(a-b)<1/255+1e-5 for a,b in zip(space.back[:3], colors['surface']))
                assert all(abs(a-b)<1/255+1e-5 for a,b in zip(space.header[:3], colors['raised']))
            assert all(abs(a-b)<1/255+1e-5 for a,b in zip(theme.regions.scrubbing.back[:3], colors['surface']))
            from no_mans_sky_base_builder.tools.asset_browser_grid import browser_palette
            palette = browser_palette(bpy.context)
            assert all(abs(a-b)<1/255+1e-5 for a,b in zip(palette['background'][:3], colors['surface']))
            assert all(abs(a-b)<1/255+1e-5 for a,b in zip(palette['card'][:3], colors['raised']))
            assert all(abs(a-b)<1/255+1e-5 for a,b in zip(palette['hover'][:3], colors['accent']))
            assert bpy.ops.bbe.custom_theme(name='Second Theme', **colors) == {'FINISHED'}
            assert len(bbe_themes.custom_themes()) == 2
            assert bpy.ops.bbe.custom_theme(name='My Ocean', **colors) == {'FINISHED'}
            assert len(bbe_themes.custom_themes()) == 2
            # Legacy presets must survive saving new gradient presets.
            saved = bbe_themes.custom_themes()
            saved['Legacy'] = [list(colors[k]) for k in ('surface', 'raised', 'accent', 'text', 'background')]
            bbe_themes._custom_path().write_text(json.dumps(saved))
            for mode in ('LINEAR', 'RADIAL', 'SINGLE_COLOR'):
                assert bpy.ops.bbe.custom_theme(name='Effects', background_type=mode,
                    gradient_end=(0.01, 0.02, 0.03), grid=(0.21, 0.31, 0.41), **colors) == {'FINISHED'}
                bbe_themes.apply_theme('BLENDER_DARK')
                assert bpy.ops.bbe.load_custom_theme(name='Effects') == {'FINISHED'}
                assert theme.view_3d.space.gradients.background_type == mode
                for actual, expected in ((theme.view_3d.space.gradients.gradient, (0.01, 0.02, 0.03)),
                                         (theme.view_3d.grid, (0.21, 0.31, 0.41)),
                                         (theme.regions.sidebars.back, colors['surface']),
                                         (theme.regions.sidebars.tab_back, colors['surface']),
                                         (theme.user_interface.wcol_menu_back.inner, colors['background'])):
                    assert all(abs(a-b)<1/255+1e-5 for a,b in zip(actual, expected))
            assert bpy.ops.bbe.load_custom_theme(name='Legacy') == {'FINISHED'}
            assert theme.view_3d.space.gradients.background_type == 'SINGLE_COLOR'
            assert bbe_themes.custom_themes()['Legacy'] == saved['Legacy']
            bbe_themes._custom_path().write_text('{broken')
            assert bbe_themes.custom_themes() == {}
            bbe_chat.sync_theme()
            assert 'theme' in json.loads(bbe_chat._settings_path().read_text(encoding='utf-8'))
        finally:
            bbe_chat._settings_path = original
            bbe_themes._custom_path = original_custom
finally:
    addon.unregister()
print('BBE_THEME_TOOLBAR_OK')

