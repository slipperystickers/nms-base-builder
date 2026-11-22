"""Isolated Blender test setup. Never writes to the user's settings or saves."""
from pathlib import Path
import os,sys,zipfile,json,importlib
import bpy,addon_utils
R=Path(__file__).resolve().parents[2]
D=Path(os.environ.get('NMS_KUMA_TEST_ADDON',str(R/'src/addons/no_mans_sky_base_builder')))
installed_profile=os.environ.get('BBE_TEST_INSTALLED_PROFILE')
QA=Path(os.environ.get('BBE_TEST_ARTIFACTS',str(R/'tests/.artifacts')));QA.mkdir(parents=True,exist_ok=True)
(QA/'tmp').mkdir(exist_ok=True)
bpy.context.preferences.filepaths.temporary_directory=str(QA/'tmp')
os.environ['NMS_BASE_BUILDER_DATA_DIR']=str(QA/'browser_data')
if installed_profile:
    profile=Path(installed_profile).resolve()
    assert Path(bpy.utils.user_resource('CONFIG')).resolve().is_relative_to(profile)
    D=profile/'extensions/user_default/no_mans_sky_base_builder'
    name='bl_ext.user_default.no_mans_sky_base_builder'
    assert addon_utils.check(name)==(True, True), 'Extension did not stay enabled on restart'
else:
    site=QA/'python_dependencies';site.mkdir(exist_ok=True)
    for path in (D/'wheels').glob('*.whl'):
        marker=site/(path.name+'.extracted')
        if not marker.exists():
            with zipfile.ZipFile(path) as z:z.extractall(site)
            marker.touch()
    sys.path.insert(0,str(site));sys.path.insert(0,str(D.parent))
    name='no_mans_sky_base_builder'
    addon_utils.enable(name,default_set=True,persistent=False)
addon=importlib.import_module(name)
assert Path(addon.__file__).resolve()==(D/'__init__.py').resolve()
ref=importlib.import_module(name+'.save_editor.station_reference')
ref.profile_file=lambda:QA/'appearance_profiles.json'
def module(suffix):return importlib.import_module(name+'.'+suffix)
def report(name,data):
    (QA/(name+'.json')).write_text(json.dumps(data,indent=2))
    print(name.upper(),json.dumps(data),flush=True)
