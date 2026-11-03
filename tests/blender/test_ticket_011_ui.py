"""Disposable save UI for manual review of the native export dialogs."""
from pathlib import Path
code=(Path(__file__).with_name('test_ticket_011_exports.py')).read_text(encoding='utf8')
exec(compile(code.split('\ntry:\n',1)[0], __file__, 'exec'))
bpy.context.scene.nms_main.new_file()
for i,part in enumerate(('B_COK_A','BUILDFLATPANEL','BUILDWALL')):
    obj=builder.add_part(part,high_res=False,user_data=0).object;obj.location=(i*4,0,0)
bpy.context.scene.nms_base_tool.string_base='Spaceman'
write(fixture());d=select();d.nms_base_index='Default'
actions.remember_ship_source(bpy.context.scene,paths,'Main',2,'Spaceman')
# Keep this QA process visibly distinct and retain all patches until exit.
bpy.ops.wm.save_as_mainfile(filepath=str(folder/'BBE-export-review-TEST-ONLY.blend'))
def show():
    area=next(a for a in bpy.context.screen.areas if a.type=='VIEW_3D')
    with bpy.context.temp_override(area=area,region=next(r for r in area.regions if r.type=='WINDOW')):
        bpy.ops.bbe.optimizer_export('INVOKE_DEFAULT')
    return None
bpy.app.timers.register(show,first_interval=3)
