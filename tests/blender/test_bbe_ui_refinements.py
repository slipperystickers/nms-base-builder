import sys
from pathlib import Path
import bpy
sys.path.insert(0,str(Path(__file__).resolve().parent))
from test_support import addon,module,QA
c=module('bubble_controls'); u=module('utils.userdata'); m=module('utils.material')
obj=bpy.data.objects.new('Color selection test',None);bpy.context.scene.collection.objects.link(obj)
obj['ObjectID']='BASE_BUBPIPE'
rows=[m.BAKED_COLOURS[0], next(r for r in m.BAKED_COLOURS if r[4]!=m.BAKED_COLOURS[0][4] and r[3]!=m.BAKED_COLOURS[0][3])]
bpy.ops.object.select_all(action='DESELECT');obj.select_set(True);bpy.context.view_layer.objects.active=obj
for row in rows:
    obj['UserData']=u.update_colour_material(1<<16,colour_index=int(row[3]),material_index=int(row[4]))
    before=obj['UserData'];addon.sync_selected_palette(bpy.context)
    assert addon.selected_colour_row(bpy.context)[3:5]==row[3:5]
    assert bpy.context.scene.nms_main.material_switch==f'{row[4]}_{row[2]}'
    assert obj['UserData']==before
obj.select_set(False);addon.sync_selected_palette(bpy.context)
assert addon.selected_colour_row(bpy.context) is None
vp=(16,24,1300,800); box=(400,200,700,500)
pos,anchor=c.fixed_panel_position(None,box,[box],vp,(330,260))
for bounds,size in [((900,600,1100,700),(330,340)),((20,40,200,220),(330,200))]:
    nextpos,nextanchor=c.fixed_panel_position(anchor,bounds,[bounds],vp,size)
    assert nextanchor==anchor and nextpos[0]==pos[0]
f=module('save_editor.save_editor_presentation')
assert f.needs_save_refresh('The save changed. Refresh the save list before continuing.')
assert not f.needs_save_refresh('Could not refresh save counts: permission denied')
assert not f.needs_save_refresh('No account selected')
from types import SimpleNamespace
original=f.get_save_data;called=[];generation=f._refresh_generation
f.get_save_data=lambda context:SimpleNamespace(get_current_slot_data=lambda:{'test':True}, refresh_bases_list=lambda:called.append(True))
try:
    assert bpy.ops.bbe.refresh_save_counts()=={'FINISHED'}
    assert called==[True] and f._refresh_generation==generation+1
    notice=SimpleNamespace()
    dialog=[]
    context=SimpleNamespace(window_manager=SimpleNamespace(
        invoke_props_dialog=lambda operator, **kwargs: (dialog.append(kwargs) or {'RUNNING_MODAL'})))
    assert f.BBE_OT_save_refresh_notice.invoke(notice,context,None)=={'RUNNING_MODAL'}
    assert dialog[0]['confirm_text']=='REFRESH SAVE' and dialog[0]['cancel_default'] is True
    assert f.BBE_OT_save_refresh_notice.execute(notice,bpy.context)=={'FINISHED'}
    assert called==[True,True] and f._refresh_generation==generation+2
    # A different refresh while the dialog is open must not refresh again.
    assert f.BBE_OT_save_refresh_notice.execute(notice,bpy.context)=={'FINISHED'}
    assert called==[True,True]
finally:f.get_save_data=original
geo=module('bbe_chat')._viewport_geometry()
assert geo is None or len(geo)==4
print('BBE_UI_REFINEMENTS_PASS',bpy.app.version_string,flush=True)
