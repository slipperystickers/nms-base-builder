"""Synthetic, offline toolbar fixture for native visual inspection."""
import sys
from pathlib import Path
import bpy
sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_support import module, QA
chat = module('bbe_chat')
menu = module('tools_menu.base_builder_menu')
menu.toolbar_state = lambda context: (['chat'], set())
if bpy.app.timers.is_registered(chat._tick):
    bpy.app.timers.unregister(chat._tick)
chat._chat_enabled = True
chat._toolbar_status = {'preview':'Builder: Reply to your snapshot','unread':1,'directed':1,'online':5}
bpy.ops.wm.save_as_mainfile(filepath=str(QA/'Chat22-Toolbar-Preview.blend'))
for area in bpy.context.screen.areas: area.tag_redraw()
print('CHAT22_NATIVE_FIXTURE_READY', flush=True)
