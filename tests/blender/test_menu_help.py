"""Exercise the help action on each registered BBE toolbar dropdown."""
from pathlib import Path
import sys
from types import SimpleNamespace
import bpy

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_support import module

toolbar = module('tools_menu.base_builder_menu')
help_ui = module('save_editor.function_help')
topics = dict(proxies='BBE', recovery='RECOVERY', io='IO', color='COLOUR', builder='BUILDER',
              transform='CURVES', batch='BATCH', parts='PREFABS', cables='LOGIC', lighting='LIGHTING', chat='CHAT')
panels = [(panel, topics[key]) for key, _, panel, _ in toolbar.TOOLBAR_ITEMS]
panels.extend([('VIEW3D_PT_bbe_toolbar_settings', 'TOOLBAR'), ('VIEW3D_PT_bbe_themes', 'THEMES'),
               ('BBE_MT_corvette_picker', 'PICK_SHIP'), ('BBE_MT_recovery', 'RECOVERY'),
               ('OBJECT_MT_nms_get_more_presets_menu', 'PREFABS')])


class Layout:
    def __init__(self):
        self.help_buttons = []

    def operator(self, name, **kwargs):
        op = SimpleNamespace()
        if name == 'bbe.function_help' and kwargs.get('text') == '':
            self.help_buttons.append(op)
        return op

    def __getattr__(self, name):
        return lambda *args, **kwargs: self


area = next(a for a in bpy.context.screen.areas if a.type == 'VIEW_3D')
region = next(r for r in area.regions if r.type == 'WINDOW')
with bpy.context.temp_override(area=area, region=region):
    for panel, topic in panels:
        cls = getattr(bpy.types, panel)
        layout = Layout()
        view = SimpleNamespace(layout=layout, toolbar_group=getattr(cls, 'toolbar_group', None))
        cls.draw(view, bpy.context)
        assert sum(button.topic == topic for button in layout.help_buttons) == 1, (panel, layout.help_buttons)
        assert help_ui.TOPICS[topic][1] and bpy.ops.bbe.function_help(topic=topic) == {'FINISHED'}
        help_ui.BBE_OT_function_help.draw(SimpleNamespace(layout=Layout(), topic=topic), bpy.context)
print('MENU HELP PASS', len(panels), bpy.app.version_string)

