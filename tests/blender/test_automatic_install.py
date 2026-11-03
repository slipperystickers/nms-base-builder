"""Exercise real Blender installation in a disposable profile only."""
import bpy,addon_utils,tempfile,sys,zipfile,importlib.util
from pathlib import Path
root=Path(tempfile.mkdtemp(prefix='bbe-install-test-'))
module_path=Path(__file__).resolve().parents[2]/'src/addons/no_mans_sky_base_builder/update_install.py'
spec=importlib.util.spec_from_file_location('install_test',module_path)
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
repo=root/'repo';repo.mkdir()
bpy.context.preferences.extensions.repos.new(name='Isolated update test',module='update_test',custom_directory=str(repo))
name='bbe_updater_fixture'
for version in ('1.0.0','1.0.1'):
 p=root/(version+'.zip')
 with zipfile.ZipFile(p,'w') as z:
  z.writestr('blender_manifest.toml',f'''schema_version = "1.0.0"
id = "{name}"
version = "{version}"
name = "Update test"
tagline = "Test automatic installation"
maintainer = "Test"
type = "add-on"
blender_version_min = "4.2.0"
license = ["SPDX:GPL-3.0-or-later"]
''')
  z.writestr('__init__.py',f"from .value import VERSION\ndef register():pass\ndef unregister():pass\n")
  z.writestr('value.py',f'VERSION = "{version}"\n')
 m.install(str(p),'bl_ext.update_test.'+name)
 loaded=sys.modules['bl_ext.update_test.'+name]
 assert loaded.VERSION==version,(loaded.VERSION,version)
print('AUTOMATIC_NATIVE_INSTALL_AND_UPGRADE_PASS',bpy.app.version_string,flush=True)
