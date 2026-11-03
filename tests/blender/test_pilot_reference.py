"""Reference lifecycle and native export/selection/transform regression."""
from pathlib import Path
import sys, json, time, math
import bpy
from mathutils import Matrix, Vector
sys.path.insert(0,str(Path(__file__).resolve().parent))
from test_support import module, QA
p=module('pilot_reference')
builder=module('builder')
original_asset_path=p.asset_path
def staged_asset(race,detailed):
    if detailed:
        return Path(p.__file__).parent/'resources/hd_additions/pilot_references'/f'{race}.blend'
    return original_asset_path(race,detailed)
p.asset_path=staged_asset
assert module('hd_library').available(), 'The installed model pack is needed for the global toggle test'
bpy.context.scene.bbe_detailed_proxies=False

bpy.ops.object.select_all(action='SELECT');bpy.ops.object.delete(use_global=False)
test_mesh=bpy.data.meshes.new('Test cockpit mesh')
test_mesh.from_pydata([(0,0,0),(1,0,0),(0,1,0)],[],[(0,1,2)])
cockpit=bpy.data.objects.new('Test cockpit',test_mesh)
bpy.context.collection.objects.link(cockpit)
cockpit['ObjectID']='B_COK_D'
cockpit['UserData']='0'
cockpit['Timestamp']='0'
cockpit['order']=7
cockpit.scale=(1,)*3
cockpit.select_set(True);bpy.context.view_layer.objects.active=cockpit
bpy.context.view_layer.update()
assert p.BBE_GGT_pilot_reference.poll(bpy.context)
assert not p.references(bpy.context.scene,cockpit), 'Selection must not populate a reference'
second=bpy.data.objects.new('AAA trigger cockpit',test_mesh)
bpy.context.collection.objects.link(second)
second['ObjectID']='B_COK_A';second['order']=19
second['Timestamp']='0';second['UserData']='0'
cockpit.select_set(False);second.select_set(True);bpy.context.view_layer.objects.active=second
assert p.target(bpy.context) is None and not p.BBE_GGT_pilot_reference.poll(bpy.context)
try:p.choose(bpy.context,'GEK_DEFAULT')
except ValueError:pass
else:raise AssertionError('Secondary cockpit accepted a pilot')
second.select_set(False);cockpit.select_set(True);bpy.context.view_layer.objects.active=cockpit
assert bpy.ops.bbe.choose_pilot_reference(race='GEK_DEFAULT')=={'FINISHED'}
model=p.preview(bpy.context)
assert model and len(model.users_collection)==1
assert model.users_collection[0].get('bbe_pilot_collection')
assert not model.hide_select and all(model.lock_location) and all(model.lock_rotation) and all(model.lock_scale)
model.select_set(True);cockpit.select_set(False);bpy.context.view_layer.objects.active=model
assert p.target(bpy.context)==cockpit and p.BBE_GGT_pilot_reference.poll(bpy.context)
for race,label in p.RACES:
    assert bpy.ops.bbe.choose_pilot_reference(race=race)=={'FINISHED'}
    assert p.preview(bpy.context)==model and len(p.references(bpy.context.scene,cockpit))==1
    assert model[p.RACE]==race
    before=model.matrix_world.copy()
    assert bpy.ops.object.nms_switch_proxies_to_high()=={'FINISHED'}
    assert model[p.DETAIL]
    assert model.matrix_world==before
    assert model.data.materials and any(getattr(node,'image',None) for mat in model.data.materials for node in mat.node_tree.nodes)
    assert bpy.ops.bbe.choose_pilot_reference(race=race)=={'FINISHED'}
    assert model[p.DETAIL], 'New choices must inherit global quality'
    assert bpy.ops.object.nms_switch_proxies_to_low()=={'FINISHED'}
    assert not model[p.DETAIL]
    assert len(model.data.materials)==1
    assert not any(getattr(node,'image',None) for node in model.data.materials[0].node_tree.nodes)
# Texture images are shared across appended models, and all portable files decode.
images=[im for im in bpy.data.images if im.get('bbe_pilot_texture')]
assert len(images)==len({im['bbe_pilot_texture'] for im in images})
assert all(Path(im.filepath).is_file() and 0<max(im.size)<=1024 for im in images)
# A shared project can contain another user's absolute texture path.
images[0].filepath='C:/missing-other-computer/pilot-texture.webp'
assert module('hd_library').relink_texture_images()>=1
assert Path(images[0].filepath).is_file() and max(images[0].size)>0
# An older HD pack must preserve a usable lightweight reference with an explanation.
def unavailable(race,detailed):
    if detailed:raise ValueError('Test missing HD asset')
    return staged_asset(race,detailed)
cached=p.mesh_for('ASTRO_DEFAULT',True)
cached['bbe_pilot_asset']='test_uncached'
p.asset_path=unavailable
fallback,actual,warning=p.resolved_mesh('ASTRO_DEFAULT',True)
assert not actual and warning and fallback==p.mesh_for('ASTRO_DEFAULT',False)
p.asset_path=staged_asset
cached['bbe_pilot_asset']='ASTRO_DEFAULT:1:colour2'
mesh=model.data
def expected_position(cockpit):
    scale=cockpit.matrix_world.to_scale().y
    native_y=p.NATIVE[p.cockpit_id(cockpit)][1]
    offset=Vector((0,scale*native_y,scale*p.NATIVE[p.cockpit_id(cockpit)][2]))
    return cockpit.matrix_world.translation+cockpit.matrix_world.to_quaternion()@offset
started=time.perf_counter()
for i in range(100):
    scale=.001+i*.001
    cockpit.scale=(scale,)*3
    cockpit.location=(i*.03,2,3)
    cockpit.rotation_euler=(.2,.3,.4)
    bpy.context.view_layer.update()
    expected=expected_position(cockpit)
    # Blender can flush driven translations smaller than about 0.1 mm to zero.
    tolerance=1e-4 if scale<.002 else 1e-5
    assert (model.matrix_world.translation-expected).length<tolerance, (i, tuple(expected), tuple(model.matrix_world.translation))
    assert all(abs(s-1)<1e-5 for s in model.matrix_world.to_scale())
    assert model.data==mesh
elapsed=time.perf_counter()-started
# The measured ruler cockpit scales retain a full-size pilot and the
# native locator translation.
for scale in (.0539835,.35):
    cockpit.scale=(scale,)*3
    cockpit.location=(-.027369,.189233,.170690)
    cockpit.rotation_euler=(math.pi/2,0,0)
    bpy.context.view_layer.update()
    assert (model.matrix_world.translation-expected_position(cockpit)).length<1e-5
    assert abs(model.location.y-(scale*.390375))<1e-5
    assert abs(model.location.z-(scale*1.951858))<1e-5
    assert all(abs(s-1)<1e-5 for s in model.matrix_world.to_scale())
# U.S.O.'s flight cockpit is below one-thousandth scale. The player stays
# full-size and the scaled locator and full-size reference remain active.
cockpit.scale=(.0007690901402384043,)*3
cockpit.location=(0,-.2682647109031677,-.19321931898593903)
cockpit.rotation_euler=(0,0,0)
bpy.context.view_layer.update()
assert (model.matrix_world.translation-expected_position(cockpit)).length<1e-4
assert abs(model.location.y-(.0007690901402384043*.390375))<1e-4
assert abs(model.location.z-(.0007690901402384043*1.951858))<1e-5
assert all(abs(s-1)<1e-5 for s in model.matrix_world.to_scale())
# Independent read-only runtime sample from the user's supplied micro-cockpit
# scene: validate the attachment and both hip/wrist positions, not a photo fit.
runtime=json.loads((Path(__file__).resolve().parents[1]/'fixtures/pilot-runtime-micro-cockpit.json').read_text())
tolerance=runtime['validation_tolerance_m']
assert (model.matrix_world.translation-cockpit.location-Vector(runtime['runtime_player_model_unscaled_cockpit_xyz'])).length<tolerance
for landmark in runtime['landmarks'].values():
    native=Vector(landmark['native_ckpit_y180_xyz'])
    asset=Vector((-native.x,native.z,native.y))
    predicted=model.matrix_world@asset-cockpit.location
    observed=Vector(landmark['runtime_position_unscaled_cockpit_xyz'])
    assert (predicted-observed).length<tolerance, (tuple(predicted),tuple(observed))
model.location=(200,300,400);model.rotation_euler=(2,3,4);model.scale=(8,)*3
bpy.context.view_layer.update()
assert (model.matrix_world.translation-expected_position(cockpit)).length<1e-4, 'Direct edits overrode the attachment'
assert all(abs(s-1)<1e-5 for s in model.matrix_world.to_scale())
layer=bpy.context.view_layer.layer_collection.children[model.users_collection[0].name]
layer.hide_viewport=True;bpy.context.view_layer.update();assert not model.visible_get()
layer.hide_viewport=False;bpy.context.view_layer.update();assert model.visible_get()
native=builder.Builder().get_all_parts()
assert cockpit in native and model not in native and model.parent not in native
for options in ({},{'get_presets':True},{'as_prefab':True}):
    exported=builder.Builder().serialise(**options)
    records=exported.get('Objects',exported.get('Prefab'))
    assert len(records)==2 and records[0]['ObjectID']=='^B_COK_D'
# Explicit cockpit role changes keep the single pilot on the exported first cockpit.
cockpit['order'],second['order']=second['order'],cockpit['order']
p.sync_flight_reference(bpy.context);bpy.context.view_layer.update()
assert model[p.TARGET]==second and model.parent[p.TARGET]==second
expected=expected_position(second)
assert (model.matrix_world.translation-expected).length<1e-5
cockpit['order'],second['order']=second['order'],cockpit['order']
p.sync_flight_reference(bpy.context);bpy.context.view_layer.update()
# Invalid choices must preserve the current model.
old_mesh=model.data
old_path=p.asset_path
try:
    # A fresh race/detail cache key is not guaranteed; exercise validation directly.
    try:p.choose(bpy.context,'MISSING_RACE')
    except ValueError:pass
    else:raise AssertionError('Unknown race accepted')
    assert model.data==old_mesh and len(p.references(bpy.context.scene,cockpit))==1
finally:p.asset_path=old_path
file=QA/'pilot-reference-roundtrip.blend'
# Simulate a project saved by the rejected geometry-snapping experiment.
model['bbe_pilot_pose_version']=5
model['bbe_pilot_seat_root_up']=.3
model['bbe_pilot_seat_root_forward']=.015
model['bbe_pilot_seat_lift_m']=.324
for axis,value in enumerate((0.0,0.0,.05)):
    p.constant_driver(model,'location',axis,repr(value))
bpy.ops.wm.save_as_mainfile(filepath=str(file))
bpy.ops.wm.open_mainfile(filepath=str(file))
module('pilot_pose').update_scene(bpy.context.scene,force=True)
bpy.context.view_layer.update()
model=next(o for o in bpy.context.scene.objects if o.get(p.TAG))
cockpit=model[p.TARGET]
assert cockpit.name=='Test cockpit' and p.target(bpy.context)==cockpit
assert model['bbe_pilot_pose_version']==8, 'Saved pilot pose was not upgraded on load'
assert not any(key.startswith('bbe_pilot_seat_') for key in model.keys()), 'Rejected seat offsets survived reload'
cockpit.location.x+=10;bpy.context.view_layer.update()
expected=expected_position(cockpit)
assert (model.matrix_world.translation-expected).length<1e-4
p.remove(bpy.context)
assert not p.references(bpy.context.scene,cockpit)
assert not [c for c in bpy.data.collections if c.get('bbe_pilot_collection')]
assert bpy.context.active_object==cockpit
# Real imported object lists must choose the first listed cockpit, not the
# alphabetically first ID, last imported/active object, or largest scale.
for obj in list(bpy.context.scene.objects):bpy.data.objects.remove(obj,do_unlink=True)
payload={'BaseVersion':8,'Objects':[
    {'ObjectID':'^B_COK_D','Position':[0,0,0],'Up':[0,.05,0],'At':[0,0,.05],'UserData':0,'Timestamp':0},
    {'ObjectID':'^B_COK_A','Position':[3,0,0],'Up':[0,1,0],'At':[0,0,1],'UserData':0,'Timestamp':0}]}
module('builder_v2').deserialise_from_data(payload)
imported=builder.Builder().get_all_parts()
assert [p.cockpit_id(o) for o in imported]==['B_COK_D','B_COK_A']
assert p.first_cockpit(bpy.context.scene)==imported[0]
for index,obj in enumerate(imported):
    for other in bpy.context.selected_objects:other.select_set(False)
    obj.select_set(True);bpy.context.view_layer.objects.active=obj
    assert p.BBE_GGT_pilot_reference.poll(bpy.context)==(index==0)
for other in bpy.context.selected_objects:other.select_set(False)
imported[0].select_set(True);bpy.context.view_layer.objects.active=imported[0]
assert bpy.ops.bbe.choose_pilot_reference(race='ASTRO_DEFAULT')=={'FINISHED'}
assert p.preview(bpy.context)[p.TARGET]==imported[0]
bpy.context.view_layer.update()
model=p.preview(bpy.context)
assert (model.matrix_world.translation-expected_position(imported[0])).length<1e-5
# Every supported cockpit uses its native vertical locator.
for part_id in p.NATIVE:
    imported[0]['ObjectID']=part_id
    assert p.target(bpy.context)==imported[0]
    p.set_pose_drivers(model,imported[0]);bpy.context.view_layer.update()
    assert (model.matrix_world.translation-expected_position(imported[0])).length<1e-5
imported[0]['ObjectID']='B_COK_D'
p.set_pose_drivers(model,imported[0]);bpy.context.view_layer.update()
hit,local,_,_=model.ray_cast((0,0,-.5),(0,0,1),distance=2)
assert hit
butt=model.matrix_world@local
seat_mesh=bpy.data.meshes.new('Synthetic seat support')
z=butt.z+.25
seat_mesh.from_pydata([(butt.x+dx,butt.y+dy,z) for dx,dy in ((-2,-2),(2,-2),(2,2),(-2,2))],[],[(0,1,2,3)])
seat=bpy.data.objects.new('Synthetic seat support',seat_mesh)
bpy.context.collection.objects.link(seat);seat['ObjectID']='S_CEMENTBAG'
# Arbitrary proxy vertices must not fit the butt or change cockpit attachment.
# Supported profiles may deform through native collider data, tested separately.
# Repeat a character choice after moving the surface and scaling the cockpit.
for scale in (.00076909,.025,.05,.107967,.35,1.0,5.0):
    imported[0].scale=(scale,)*3
    for height in (z,z+.1,z-.1):
        seat.location.z=height-z
        for race,_ in p.RACES:
            assert p.choose(bpy.context,race)==model
            bpy.context.view_layer.update()
            assert (model.matrix_world.translation-expected_position(imported[0])).length<1e-5
bpy.data.objects.remove(seat,do_unlink=True)
p.choose(bpy.context,'ASTRO_DEFAULT');bpy.context.view_layer.update()
assert (model.matrix_world.translation-expected_position(imported[0])).length<1e-5
report={'status':'PASS','reference_variants':len(p.RACES),'motion_updates':100,'motion_seconds':elapsed,'save_reload':True,'export_part_filter':True,
        'first_cockpit_only':True,'full_scale_picker':True,'role_swap':True,'import_order':True,
        'native_locator_cockpits':list(p.NATIVE),'attachment_independent_of_proxy_vertices':True,'seat_experiment_migration':True,
        'runtime_attachment_hips_wrists':True,
        'scale_accuracy':'native scaled locator; micro B_COK_D runtime attachment and joints sampled; other cockpit runtime checks pending'}
(QA/'pilot-reference-test.json').write_text(json.dumps(report,indent=2));print('PILOT_REFERENCE_PASS',json.dumps(report),flush=True)
