"""Compare sidebar and header panel actions without reading or writing a game save."""
from pathlib import Path
import sys
from types import SimpleNamespace
from unittest.mock import patch

import bpy

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_support import addon, module

menu = module('tools_menu.base_builder_menu_presentation')
manager = module('save_editor.save_editor_presentation')


class Layout:
    def __init__(self):
        self.actions = []

    def __getattr__(self, name):
        def draw(*args, **kwargs):
            if name in ('operator', 'menu', 'popover', 'prop_with_menu'):
                self.actions.append((name, args[0] if name != 'popover' else kwargs['panel']))
            if name == 'operator':
                return SimpleNamespace()
            return self
        return draw


def actions(panels, context):
    layout = Layout()
    panel = SimpleNamespace(layout=layout)
    for panel_type in panels:
        panel_type.draw(panel, context)
    return layout.actions


class Save:
    check_plugin_enabled = False
    nms_account_selected = '1'
    nms_save_slot = '1'
    session_status = ''
    extracted_base_data = {}
    nms_base_type = manager.BaseType.CORVETTE

    def validate_save_folder(self, path):
        return True

    def is_base_data_loaded(self):
        return True

    def get_current_slot_data(self):
        return {}

    def get_base_type_string(self, kind):
        return kind

    def get_total_parts_count(self):
        return 35

    def has_selected_base(self):
        return False

    def get_current_base_identifiers(self):
        return None


save = Save()
sidebar_panels = (addon.NMS_PT_file_buttons_panel, manager.NMS_PT_save_editor_panel)
with patch.object(manager, 'get_save_data', return_value=save), patch.object(manager, 'get_save_folder_path', return_value='fixture'):
    for enabled in (False, True):
        save.check_plugin_enabled = enabled
        for kind in (manager.BaseType.CORVETTE, manager.BaseType.BASE, manager.BaseType.EXTERNAL_BASE):
            save.nms_base_type = kind
            header = actions((menu.VIEW3D_PT_nms_io_panel,), bpy.context)
            for width in (300, 600):
                context = SimpleNamespace(scene=bpy.context.scene, preferences=SimpleNamespace(system=SimpleNamespace(ui_scale=1.0)),
                                          region=SimpleNamespace(type='UI', width=width))
                sidebar = actions(sidebar_panels, context)
                assert sidebar == header, (kind, width, sidebar, header)
                ops = [name for action, name in sidebar if action == 'operator']
                assert ops.count('object.nms_new_file') == 1
                copy = 'object.nms_export_nms_data_objects'
                paste = 'object.nms_import_nms_data'
                assert ops.count(copy) == ops.count(paste) == 1
                assert ops[ops.index(copy) + 1] == paste
                assert ops.count('bbe.export_ship_file') == ops.count('bbe.export_base_file') == 1
                assert ('bbe.io_add_minimal_corvette' in ops) == (enabled and kind == manager.BaseType.CORVETTE)
                assert ('bbe.optimizer_export' in ops) == (enabled and kind == manager.BaseType.CORVETTE)
                assert ('bbe.raw_save_json' in ops) == enabled

header = actions((menu.VIEW3D_PT_nms_base_builder,), bpy.context)
area = next(area for area in bpy.context.screen.areas if area.type == 'VIEW_3D')
region = next(region for region in area.regions if region.type == 'UI')
with bpy.context.temp_override(area=area, region=region), patch.object(addon.icons, 'draw_sidebar_brand'):
    for enabled in (False, True):
        with patch.object(module('bbe_chat'), '_chat_enabled', enabled):
            sidebar = actions((addon.NMS_PT_hero_panel,), bpy.context)
            assert ('operator', 'bbe.chat_open') not in sidebar
            assert ('popover', 'VIEW3D_PT_bbe_chat') not in sidebar
            assert ('popover', 'VIEW3D_PT_bbe_toolbar_settings') in sidebar
assert ('popover', 'VIEW3D_PT_bbe_themes') in header
assert ('operator', 'object.nms_switch_proxies_to_high') in header
assert all(control in sidebar for control in header)
build_tools = module('tools.build_tool_presentation').NMS_PT_tools_panel
tools = actions((build_tools,), bpy.context)
assert ('operator', 'bbe.toggle_auto_snap') in tools
assert ('operator', 'object.nms_paste_position') not in tools
print('SIDEBAR PARITY PASS', bpy.app.version_string)

