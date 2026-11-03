"""Disposable GUI harness for the new native asset browser entries."""
from pathlib import Path
import sys,json,traceback
import bpy
sys.path.insert(0,str(Path(__file__).parent))
from test_support import addon,module,QA
bpy.context.preferences.view.show_splash=False
bpy.data.batch_remove(list(bpy.context.scene.objects))
bpy.context.scene.name='Forsaken Asset QA'
def setup():
    try:
        browser=bpy.context.scene.nms_asset_browser
        browser.asset_browser_caterogies='Corvette'
        browser.asset_broser_search_query='Hornet'
        assert bpy.ops.object.nms_launch_asset_browser_window()=={'FINISHED'}
        print('FORSAKEN_BROWSER_OPEN',flush=True)
    except Exception:traceback.print_exc()
    return None
bpy.app.timers.register(setup,first_interval=2)
def commands():
    marker=QA/'forsaken_gui_command.json'
    if marker.exists():
        data=json.loads(marker.read_text());marker.unlink()
        if data.get('quit'):bpy.ops.wm.quit_blender();return None
        if 'search' in data:bpy.context.scene.nms_asset_browser.asset_broser_search_query=data['search']
        if data.get('report'):
            objects=[o for o in bpy.context.scene.objects if o.get('ObjectID')]
            (QA/'forsaken_gui_result.json').write_text(json.dumps({'objects':[o['ObjectID'] for o in objects],
                'source':addon.__file__,'version':list(bpy.app.version),'selected':[o.name for o in bpy.context.selected_objects]},indent=2))
    return .5
bpy.app.timers.register(commands,first_interval=3)
