"""Real proxies: reversible cutaways, exact beam filtering, browser and quick snapping."""
from pathlib import Path
import sys,json,hashlib,bpy
sys.path.insert(0,str(Path(__file__).parent))
from test_support import module,QA,report
v=module('builder_v2');controls=module('part_controls');snaps=module('snap_markers')
def evaluated(obj):
    bpy.context.view_layer.update()
    return obj.evaluated_get(bpy.context.evaluated_depsgraph_get()).data

def signature(obj):
    return (obj.data.as_pointer(),len(obj.data.vertices),len(obj.data.polygons),tuple(v for row in obj.matrix_world for v in row),obj.get('ObjectID'))

for obj in tuple(bpy.context.scene.objects):bpy.data.objects.remove(obj,do_unlink=True)
results={}
for pid in ['B_MAG_1X1','B_MAG_1X2','B_HAB_A','B_COK_A','MAINROOM','FRE_ROOM_B']:
    item=v.add_part(pid);obj=item.object;bpy.context.view_layer.update();original=signature(obj);exported=item.serialise();total=len(obj.data.polygons)
    if pid in controls.BEAM_IDS:
        controls.update_beam(obj)
        mats={i for i,m in enumerate(obj.data.materials) if m in controls.beam_materials(obj)}
        removed=sum(p.material_index in mats for p in obj.data.polygons)
        hidden=len(evaluated(obj).polygons)
        assert removed==480 and hidden==total-removed,(pid,total,hidden,removed)
        obj.bbe_show_magnetic_beam=True
        assert len(evaluated(obj).polygons)==total
        obj.bbe_show_magnetic_beam=False
        assert len(evaluated(obj).polygons)==total-removed
        results[pid]={'total':total,'hidden_beam_faces':removed}
    else:
        assert controls.enclosed(obj)
        obj.bbe_hide_ceiling=True
        cut=len(evaluated(obj).polygons)
        assert total*.15<cut<total*.99,(pid,cut,total)
        obj.bbe_ceiling_height=.5;lower=len(evaluated(obj).polygons)
        assert lower<=cut,(pid,lower,cut)
        assert not obj.modifiers[controls.ROOF].show_render
        obj.bbe_hide_ceiling=False
        assert len(evaluated(obj).polygons)==total
        results[pid]={'total':total,'cutaway':cut,'lower_cutaway':lower}
    assert signature(obj)==original,(pid,signature(obj),original)
    assert item.serialise()==exported,(pid,'export changed')

area=next(a for a in bpy.context.screen.areas if a.type=='VIEW_3D')
region=next(r for r in area.regions if r.type=='WINDOW')
with bpy.context.temp_override(area=area,region=region):
    for obj in tuple(bpy.context.selected_objects):obj.select_set(False)
    target=v.add_part('W_FLOOR').object
    for obj in tuple(bpy.context.selected_objects):obj.select_set(False)
    target.select_set(True);bpy.context.view_layer.objects.active=target
    assert bpy.ops.object.nms_asset_browser_object_selected(object_id='W_FLOOR')=={'FINISHED'}
    source,actual=snaps.objects(bpy.context)
    assert actual==target and bpy.context.active_object==target
    choices=snaps.options(source,target);assert len(choices)>1
    engine=snaps.native_engine(source,target)
    assert engine.CACHE[source.name,target.name][0]==choices[0][0]
    assert bpy.ops.bbe.click_snap_point(target_key=choices[-1][0])=={'FINISHED'}
    assert engine.CACHE[source.name,target.name][0]==choices[-1][0]
    before=engine.CACHE[source.name,target.name]
    bpy.ops.bbe.click_snap_point(target_key=choices[-1][0])
    assert engine.CACHE[source.name,target.name]!=before
    snaps.SESSION.clear();source.location.x+=7;bpy.context.view_layer.update()
    assert snaps.selected_pair(bpy.context)==(source,target)
    assert bpy.ops.bbe.quick_snap()=={'FINISHED'}
    assert snaps.objects(bpy.context)==(source,target)
    results['snapping']={'browser_auto':True,'target_switch':True,'source_cycle':True,'quick_button':True}

hab=next(o for o in bpy.context.scene.objects if o.get('ObjectID')=='B_HAB_A')
hab.bbe_hide_ceiling=True
bpy.ops.wm.save_as_mainfile(filepath=str(QA/'Part-Controls-Test.blend'))
bpy.ops.wm.open_mainfile(filepath=str(QA/'Part-Controls-Test.blend'))
for obj in bpy.context.scene.objects:
    if obj.get('ObjectID') in controls.BEAM_IDS:
        assert not obj.bbe_show_magnetic_beam
        assert len(evaluated(obj).polygons)==len(obj.data.polygons)-480
hab=next(o for o in bpy.context.scene.objects if o.get('ObjectID')=='B_HAB_A')
assert hab.bbe_hide_ceiling and len(evaluated(hab).polygons)<len(hab.data.polygons)
results['reload_preserves_beam_default_and_cutaway']=True
report('part_controls',results)
