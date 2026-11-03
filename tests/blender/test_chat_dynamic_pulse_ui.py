"""Render synthetic native toolbar states without connecting to chat."""
from pathlib import Path
import sys
import traceback
import bpy
sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_support import module, QA

chat = module('bbe_chat')
menu = module('tools_menu.base_builder_menu')
if bpy.app.timers.is_registered(chat._tick):
    bpy.app.timers.unregister(chat._tick)
menu.toolbar_state = lambda context: (['chat'], set())
chat._chat_enabled = True
chat._toolbar_status = dict(preview='Main Room: Latest community message', unread=0, directed=0, online=2, target=None)
phase = {'value':True, 'step':0}
chat.chat_state.pulse_on = lambda seconds: phase['value']

def run():
    try:
        step = phase['step']
        if step == 0:
            for area in bpy.context.screen.areas: area.tag_redraw()
        elif step == 1:
            bpy.ops.screen.screenshot(filepath=str(QA/'chat25-main-native.png'))
            chat._toolbar_status = dict(preview='Zapper: Latest response waiting for you', unread=1, directed=1, online=2, target='zapper')
            chat._redraw(toolbar_only=True)
        elif step == 2:
            bpy.ops.screen.screenshot(filepath=str(QA/'chat25-dm-pulse-on.png'))
            phase['value'] = False
            chat._redraw(toolbar_only=True)
        else:
            bpy.ops.screen.screenshot(filepath=str(QA/'chat25-dm-pulse-off.png'))
            print('CHAT25_NATIVE_PULSE_RENDER_PASS', flush=True)
            bpy.ops.wm.quit_blender()
            return None
        phase['step'] += 1
        return 1.2
    except Exception:
        traceback.print_exc()
        bpy.ops.wm.quit_blender()
        return None

bpy.app.timers.register(run, first_interval=3)
