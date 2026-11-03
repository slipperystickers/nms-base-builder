"""Disposable visual harness; no user projects, saves or chat accounts."""
from pathlib import Path
import json
import sys
import traceback
import bpy

sys.path.insert(0, str(Path(__file__).parent))
from test_support import addon, module, QA

bpy.context.preferences.view.show_splash = False
bpy.data.batch_remove(list(bpy.context.scene.objects))
props = bpy.context.scene.nms_base_tool
props.new_file()
props.deserialise_from_data({'Name': 'Interface QA - disposable build',
    'Owner': {'USN': 'Example Builder', 'UID': '123456789', 'LID': '',
              'PTK': 'ST', 'TS': 1234567890},
    'LastEditedByUsername': 'Example Editor', 'LastEditedById': '987654321'})
bpy.ops.wm.save_as_mainfile(filepath=str(QA / 'catalog-metadata36-qa.blend'))

def setup():
    try:
        bpy.ops.bbe.build_metadata('INVOKE_DEFAULT')
        print('METADATA36_DIALOG_OPEN', flush=True)
    except Exception:
        traceback.print_exc()
    return None

bpy.app.timers.register(setup, first_interval=2)

def commands():
    marker = QA / 'catalog_metadata36_command.json'
    if marker.exists():
        data = json.loads(marker.read_text())
        marker.unlink()
        if data.get('quit'):
            bpy.ops.wm.quit_blender()
            return None
        if data.get('browser'):
            browser = bpy.context.scene.nms_asset_browser
            browser.asset_browser_caterogies = 'Corvette'
            browser.asset_broser_search_query = data.get('search', 'Venom')
            bpy.ops.object.nms_launch_asset_browser_window()
        elif 'search' in data:
            bpy.context.scene.nms_asset_browser.asset_broser_search_query = data['search']
        if data.get('metadata'):
            bpy.ops.bbe.build_metadata('INVOKE_DEFAULT')
    return .5

bpy.app.timers.register(commands, first_interval=3)
