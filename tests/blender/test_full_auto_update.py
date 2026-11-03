"""Run only with all BLENDER_USER_* directories redirected to test folders."""
import bpy,sys,os,importlib,importlib.util,zipfile,tempfile
from pathlib import Path
repo=Path(__file__).resolve().parents[2]
assert 'auto_full' in os.environ['BLENDER_USER_EXTENSIONS']
assert Path(bpy.utils.user_resource('CONFIG')).resolve()==Path(os.environ['BLENDER_USER_CONFIG']).resolve()
spec=importlib.util.spec_from_file_location('install_test',repo/'src/addons/no_mans_sky_base_builder/update_install.py')
helper=importlib.util.module_from_spec(spec);spec.loader.exec_module(helper)
root=Path(os.environ['BLENDER_USER_EXTENSIONS'])/'test_repo';root.mkdir(parents=True,exist_ok=True)
bpy.context.preferences.extensions.repos.new(name='Full isolated update',module='auto_full',custom_directory=str(root))
package='bl_ext.auto_full.no_mans_sky_base_builder'
bpy.context.scene['auto_update_preserve_test']='keep'
bpy.ops.mesh.primitive_cube_add(location=(8,3,7))
sentinel=bpy.context.object
sentinel.name='Update preservation check'
sentinel['test_value']=917
for version in ('18.2.38','18.2.39'):
 helper.install(str(repo/f'dist/no_mans_sky_base_builder-{version}.zip'),package)
 addon=importlib.import_module(package)
 assert addon._core_registered
 assert bpy.context.scene['auto_update_preserve_test']=='keep'
 assert bpy.data.objects['Update preservation check']['test_value']==917
 assert tuple(bpy.data.objects['Update preservation check'].location)==(8,3,7)
 print('BBE_INSTALL_OK',version,flush=True)
hd=importlib.import_module(package+'.hd_library')
assert not (Path(addon.__file__).parent/'resources/hd_additions').exists()
os.environ['BBE_ASSET_LIBRARY_ROOT']=tempfile.mkdtemp(prefix='bbe-hd-install-check-')
assert hd.additions_root() is None
hd.install_archive(repo/'dist/bbe-hd-additions-1.zip',hd.additions_specification())
assert hd.additions_root() is not None
assert all((hd.additions_root()/name).exists() for name in hd.additions_specification()['files'])
print('OPTIONAL_HD_ADDITIONS_INSTALLED',flush=True)
nmscribe=Path(r'C:\Users\kengo\OneDrive\Desktop\NMS\nms-text-generator')
for version in ('2.4.2','2.4.3'):
 helper.install(str(nmscribe/f'dist/NMS_Text_Generator_{version}.zip'),'nms_text_generator')
 n=importlib.import_module('nms_text_generator')
 assert n.bl_info['version']==tuple(map(int,version.split('.')))
 print('NMSCRIBE_INSTALL_OK',version,flush=True)
assert n.release_updates._client.installed=='2.4.3'
from nms_text_generator import shape_ui as ui
import time
s=bpy.context.scene.nms_shape_settings
s.max_parts=180;s.preset='OBLATE';s.dimensions=(18,18,8)
ui.start_preview(bpy.context,False)
state=ui._states[bpy.context.scene.as_pointer()]
deadline=time.monotonic()+60
while 'job' in state:
 ui.poll_jobs()
 assert time.monotonic()<deadline,s.status
 time.sleep(.05)
assert 'result' in state,s.status
assert bpy.ops.nms_shape.generate()=={'FINISHED'}
root=ui.selected(bpy.context)
assert 0<len(ui.export_data(root)['Objects'])<=180
assert bpy.data.objects['Update preservation check']['test_value']==917
print('NMSCRIBE_NATIVE_GENERATION_PASS',flush=True)
print('FULL_AUTO_UPDATE_PASS',bpy.app.version_string,flush=True)
