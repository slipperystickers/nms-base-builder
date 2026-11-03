from pathlib import Path
import sys, copy
import bpy
sys.path.insert(0, str(Path(__file__).parent))
from test_support import module, QA
sys.path.insert(0, str(Path(__file__).parents[1]))
from test_ship_link_resilience import fixture, TEMPLATE
core=module('save_editor.ship_core'); files=module('save_editor.ship_files'); ui=module('build_metadata_ui')
root=fixture(); p=core.player(root,'Main')
p['PersistentPlayerBases'][0]['Owner']=dict(USN='Example Builder',UID='example-user',LID='example-local',PTK='ST',TS=12345)
p['PersistentPlayerBases'][0]['Name']='Donor Corvette'
path=QA/'tmp'/'ownership38-ui-save.hg'
save=files.SaveFile(path);save.json_data=root;save.save()
ui.selected_save_paths=lambda context:[str(path)]
props=bpy.context.scene.nms_base_tool
props.new_file();props.deserialise_from_data(dict(Name='Ownership UI Test',Owner=dict(USN='',UID='test-id',LID='test-local',PTK='ST',TS=123)))
bpy.context.preferences.view.show_splash=False
bpy.ops.wm.save_as_mainfile(filepath=str(QA/'ownership38-ui.blend'))
def show():
 bpy.ops.bbe.build_metadata('INVOKE_DEFAULT')
 return None
bpy.app.timers.register(show,first_interval=2)
