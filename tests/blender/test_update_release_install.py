"""Install the published .43 ZIP and upgrade it through Blender's native installer.

Run with every BLENDER_USER_* directory redirected beneath BBE_INSTALL_TEST_ROOT
(a directory named update-install-45) and an isolated BBE_ASSET_LIBRARY_ROOT.
"""
import importlib
import importlib.util
import os
from pathlib import Path
import sys

import bpy

root = Path(os.environ['BBE_INSTALL_TEST_ROOT']).resolve()
assert root.name == 'update-install-45'
for kind, name in [('CONFIG', 'config'), ('SCRIPTS', 'scripts'), ('DATAFILES', 'datafiles'), ('EXTENSIONS', 'extensions')]:
    assert Path(os.environ['BLENDER_USER_' + kind]).resolve() == root / name
assert Path(bpy.utils.user_resource('CONFIG')).resolve() == root / 'config'
assert Path(os.environ['BBE_ASSET_LIBRARY_ROOT']).resolve() == root / 'hd'
repo = Path(__file__).resolve().parents[2]
path = repo / 'src/addons/no_mans_sky_base_builder/update_install.py'
spec = importlib.util.spec_from_file_location('release_installer', path)
helper = importlib.util.module_from_spec(spec)
spec.loader.exec_module(helper)
extension_dir = root / 'extensions/test_repo'
extension_dir.mkdir(parents=True, exist_ok=True)
bpy.context.preferences.extensions.repos.new(name='Native release upgrade test', module='release_test',
                                             custom_directory=str(extension_dir))
package = 'bl_ext.release_test.no_mans_sky_base_builder'
bpy.context.scene['update_preservation'] = 'keep'
bpy.ops.mesh.primitive_cube_add(location=(8, 3, 7))
sentinel = bpy.context.object
sentinel.name = 'Update preservation check'
sentinel['test_value'] = 917
for version in ('18.2.43', '18.2.45'):
    helper.install(str(repo / f'dist/no_mans_sky_base_builder-{version}.zip'), package)
    addon = importlib.import_module(package)
    assert addon._core_registered and addon.__addon_enabled__
    assert addon.ADDON_VERSION == version
    assert package in bpy.context.preferences.addons
    assert hasattr(bpy.types.Scene, 'nms_main')
    assert bpy.context.scene['update_preservation'] == 'keep'
    assert bpy.data.objects['Update preservation check']['test_value'] == 917
    assert tuple(bpy.data.objects['Update preservation check'].location) == (8, 3, 7)
    assert Path(bpy.app.tempdir).is_dir()
    print('NATIVE_RELEASE_INSTALL_PASS', version, bpy.app.version_string, flush=True)
hd = importlib.import_module(package + '.hd_library')
assert not hd.has_installed_content()
assert hd.additions_specification()['url'].endswith('/v18.2.44/bbe-hd-additions-1.zip')
assert not (Path(addon.__file__).parent / 'resources/hd_additions').exists()
print('NATIVE_43_TO_45_UPGRADE_PASS_SCENE_AND_HD_SETTINGS_PRESERVED', flush=True)
