"""Native standing/seated dummies: browser, quality, transforms and export boundary."""
from pathlib import Path
import io
import json
import sys
import zipfile
import bpy
from mathutils import Matrix

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_support import module, QA, report
c = module('character_references')
assert c.load_post in bpy.app.handlers.load_post
b = module('builder').Builder()
interchange = module('interchange')
bpy.ops.object.select_all(action='SELECT')
bpy.ops.object.delete(use_global=False)
bpy.context.scene.bbe_detailed_proxies = False
mesh = bpy.data.meshes.new('Export sentinel')
mesh.from_pydata([(0,0,0),(1,0,0),(0,1,0)],[],[(0,1,2)])
part = bpy.data.objects.new('Export sentinel',mesh)
bpy.context.collection.objects.link(part)
part['ObjectID']='B_COK_D';part['UserData']='0';part['Timestamp']='0';part['order']=0
baseline = [b.serialise(**options) for options in ({},{'get_presets':True},{'as_prefab':True})]
tree = module('utils.asset_browser_utils').build_category_tree(favourite_ids=[])
assert set(tree['Character References'])=={'Standing','Seated'}
assert sum(map(len,tree['Character References'].values()))==14
references=[]
for pose in c.POSES:
    for race,label in c.RACES:
        identifier=c.asset_id(race,pose)
        assert identifier in module('icons').get_asset_icons_pcoll()
        bpy.context.scene.cursor.location=(len(references)*.25,1.5,2.5)
        obj=c.add(bpy.context,identifier)
        references.append(obj)
        assert obj.location==bpy.context.scene.cursor.location
        assert not obj.hide_select and not any(tuple(obj.lock_location)+tuple(obj.lock_rotation)+tuple(obj.lock_scale))
        assert not obj.parent and not obj.constraints and not obj.animation_data
        assert not {'ObjectID','SnapID','PresetID'}.intersection(obj.keys())
        assert abs(min(v.co.z for v in obj.data.vertices))<.003, (race,pose,'ungrounded')
        obj.location=(len(references)*.3,-2,1)
        obj.rotation_euler=(.2,.4,.6)
        obj.scale=(1.4,.9,1.1)
bpy.context.view_layer.update()
matrices={obj.name:obj.matrix_world.copy() for obj in references}
assert bpy.ops.object.nms_switch_proxies_to_high()=={'FINISHED'}
for obj in references:
    assert obj.matrix_world==matrices[obj.name]
    assert obj['bbe_character_detailed']
    assert any(getattr(node,'image',None) for mat in obj.data.materials if mat and mat.use_nodes for node in mat.node_tree.nodes)
images=[image for image in bpy.data.images if image.get('bbe_character_texture')]
assert images and len(images)==len({(im['bbe_character_texture'],im.colorspace_settings.name) for im in images})
assert all(Path(im.filepath).is_file() for im in images)
images[0].filepath='C:/missing-on-this-computer/texture.webp'
assert module('hd_library').relink_texture_images()>=1 and Path(images[0].filepath).is_file()
assert bpy.ops.object.nms_switch_proxies_to_low()=={'FINISHED'}
assert all(obj.matrix_world==matrices[obj.name] for obj in references)
assert [b.serialise(**options) for options in ({},{'get_presets':True},{'as_prefab':True})]==baseline
assert b.get_all_parts(include_lines=True)==[part]
assert not b.get_all_presets()
# All public standalone formats consume the same filtered part list.
formats=['.json','.txt','.nmsbase','.nmsprefab']
for suffix in formats:
    doc=baseline[2] if suffix=='.nmsprefab' else baseline[0]
    parsed=interchange.BuildFile.from_bytes(json.dumps(doc).encode(),suffix)
    assert len(parsed.objects)==1 and parsed.objects[0]['ObjectID']=='^B_COK_D'
stream=io.BytesIO()
with zipfile.ZipFile(stream,'w') as archive:
    archive.writestr('objects.json','[]')
    archive.writestr('so.json','{"Name":"Reference export regression"}')
template=interchange.BuildFile.from_bytes(stream.getvalue(),'.nmsship')
ship=template.ship_bytes(baseline[0]['Objects'])
assert len(interchange.BuildFile.from_bytes(ship,'.nmsship').objects)==1
assert b'BBE_CHARACTER' not in ship
# Exercise the same operator used by list, thumbnail grid and search.
assert bpy.ops.object.nms_asset_browser_object_selected(object_id=c.asset_id('GEK_DEFAULT','STANDING'))=={'FINISHED'}
assert bpy.context.active_object.get(c.TAG)
path=QA/'character-references-roundtrip.blend'
bpy.ops.wm.save_as_mainfile(filepath=str(path))
bpy.ops.wm.open_mainfile(filepath=str(path))
assert len([obj for obj in bpy.context.scene.objects if obj.get(c.TAG)])==15
for name,matrix in matrices.items():
    assert bpy.data.objects[name].matrix_world==matrix
assert b.serialise()==baseline[0]
report('character-references',dict(status='PASS',models=14,browser_operator=True,
       quality_preserves_transforms=True,shared_textures=len(images),save_reload=True,
       excluded_formats=formats+['.nmsship','project JSON','clipboard/native Objects']))
