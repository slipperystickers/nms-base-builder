"""Shared HD dummies fall back without modifying user placement or native data."""
from pathlib import Path
import sys
import bpy
sys.path.insert(0,str(Path(__file__).parent))
from test_support import module,QA,report
c=module('character_references')
bpy.data.batch_remove(list(bpy.context.scene.objects))
scene=bpy.context.scene
scene.bbe_detailed_proxies=True
objects=[]
for index,(race,pose) in enumerate((('ASTRO_ARMOURED','STANDING'),('GEK_DEFAULT','SEATED'))):
    obj=c.add(bpy.context,c.asset_id(race,pose))
    assert obj['bbe_character_detailed']
    obj.location=(index*3.2,-1.25,2.5)
    obj.rotation_euler=(.2,-.4,.7)
    obj.scale=(1.4,.8,1.1)
    obj['user_note']='Keep this custom property'
    objects.append(obj)
scene.bbe_detailed_proxies=False
light=c.add(bpy.context,c.asset_id('FOURTH_DEFAULT','STANDING'))
light.location=(-3,2,4)
scene.bbe_detailed_proxies=True
bpy.context.view_layer.update()
expected={obj.name:dict(matrix=obj.matrix_world.copy(),race=obj['bbe_character_race'],
                       pose=obj['bbe_character_pose'],note=obj['user_note']) for obj in objects}
light_name=light.name;light_matrix=light.matrix_world.copy()
fixture=QA/'character-missing-pack-fixture.blend'
bpy.ops.wm.save_as_mainfile(filepath=str(fixture))
original_roots=c.detailed_roots
missing=QA/'simulated-other-computer-no-character-pack'
c.detailed_roots=lambda:[missing]
try:
    bpy.ops.wm.open_mainfile(filepath=str(fixture))
    assert bpy.context.scene.bbe_detailed_proxies, 'Fallback changed global preference'
    for name,record in expected.items():
        obj=bpy.data.objects[name]
        assert not obj['bbe_character_detailed'] and obj['bbe_character_asset_warning']
        assert obj.matrix_world==record['matrix']
        assert obj['bbe_character_race']==record['race'] and obj['bbe_character_pose']==record['pose']
        assert obj['user_note']==record['note'] and obj.get(c.TAG)
        assert len(obj.data.materials)==1 and not {'ObjectID','PresetID','SnapID'}.intersection(obj.keys())
    light=bpy.data.objects[light_name]
    assert not light['bbe_character_detailed'] and light.matrix_world==light_matrix
finally:
    c.detailed_roots=original_roots
assert bpy.ops.object.nms_switch_proxies_to_high()=={'FINISHED'}
for name,record in expected.items():
    obj=bpy.data.objects[name]
    assert obj['bbe_character_detailed'] and not obj['bbe_character_asset_warning']
    assert obj.matrix_world==record['matrix'] and obj['user_note']==record['note']
assert not module('builder').Builder().get_all_parts()
report('character-reference-missing-pack',dict(status='PASS',restored_detailed_models=2,
       preserved_transforms=True,preserved_source_and_user_tags=True,preserved_scene_quality=True,
       existing_light_reference_unchanged=True,actual_pack_untouched=True))
