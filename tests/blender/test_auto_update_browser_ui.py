"""Real event-loop upgrade with the persistent sidebar browser active.

Requires pre-created isolated BLENDER_USER_* directories. Exits its test process.
"""
import bpy, importlib, importlib.util, os, sys, time, hashlib
from pathlib import Path

repo=Path(__file__).resolve().parents[2]
assert 'auto_ui' in os.environ['BLENDER_USER_EXTENSIONS']
assert Path(bpy.utils.user_resource('CONFIG')).resolve()==Path(os.environ['BLENDER_USER_CONFIG']).resolve()
temporary=Path(os.environ['BLENDER_USER_CONFIG'])/'tmp'
temporary.mkdir(exist_ok=True)
bpy.context.preferences.filepaths.temporary_directory=str(temporary)
spec=importlib.util.spec_from_file_location('ui_installer',repo/'src/addons/no_mans_sky_base_builder/update_install.py')
helper=importlib.util.module_from_spec(spec);spec.loader.exec_module(helper)
root=Path(os.environ['BLENDER_USER_EXTENSIONS'])/'test_repo';root.mkdir(parents=True,exist_ok=True)
bpy.context.preferences.extensions.repos.new(name='Isolated UI upgrade',module='auto_ui',custom_directory=str(root))
package='bl_ext.auto_ui.no_mans_sky_base_builder'
helper.install(str(repo/'dist/no_mans_sky_base_builder-18.2.38.zip'),package)
addon=importlib.import_module(package)
for window in bpy.context.window_manager.windows:
    for area in window.screen.areas:
        if area.type=='VIEW_3D':area.spaces.active.show_region_ui=True
client=importlib.import_module(package+'.release_updates')._client
# Keep automatic public network checks off; use the local verified candidate.
client.settings['auto_check']=False
client.settings['auto_update_consent']='declined'
client.downloaded=repo/'dist/no_mans_sky_base_builder-18.2.39.zip'
client.result={'available':True,'version':'18.2.39','asset':{
    'size':client.downloaded.stat().st_size,
    'digest':'sha256:'+hashlib.file_digest(client.downloaded.open('rb'),'sha256').hexdigest()}}
started=time.monotonic();stage=0

def check():
    global stage
    try:
        if time.monotonic()-started>90:raise AssertionError('Update did not finish: '+client.message)
        browser=importlib.import_module(package+'.tools.asset_browser_sidebar')
        if stage==0:
            if not browser._sessions:return .5
            assert any(w.modal_operators for w in bpy.context.window_manager.windows)
            helper.advance(client,package)
            assert helper._pending,'Idle browser prevented update: '+client.message
            stage=1
            print('AUTO_UI_BROWSER_PAUSED',flush=True)
        elif helper._pending is None:
            new=importlib.import_module(package)
            assert new._core_registered
            import tomllib
            manifest=tomllib.loads((Path(new.__file__).parent/'blender_manifest.toml').read_text())
            assert manifest['version']=='18.2.39',client.message
            if not browser._sessions:return .5
            assert browser._enabled
            print('AUTO_UI_INSTALL_BROWSER_RESUMED_PASS',flush=True)
            bpy.ops.wm.quit_blender()
            return None
        return .5
    except Exception:
        import traceback
        traceback.print_exc();sys.stdout.flush();sys.stderr.flush()
        os._exit(1)

bpy.app.timers.register(check,first_interval=3)
