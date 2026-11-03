"""Character pack controls placed references independently of ship proxy quality."""
from pathlib import Path
import sys
import bpy

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'src/addons'))
import no_mans_sky_base_builder as addon
from no_mans_sky_base_builder import character_references as refs, hd_library

addon.register()
scene = bpy.context.scene
scene.bbe_detailed_proxies = False
objects = []
for index, (race, _) in enumerate(refs.RACES):
    scene.cursor.location = (index * 2, 0, 1)
    obj = refs.add(bpy.context, refs.asset_id(race, 'STANDING'))
    obj.rotation_euler = (0.1, 0.2, 0.3)
    obj.scale = (1.2, 0.8, 1.1)
    assert obj['bbe_character_detailed'], 'Installed pack must colour new references even in simple ship mode'
    if bpy.context.area and bpy.context.area.type == 'VIEW_3D':
        assert bpy.context.area.spaces.active.shading.type == 'MATERIAL'
    # Simulate a reference saved before the separate HD pack was installed.
    obj.data = refs.mesh_for(race, 'STANDING', False)
    obj['bbe_character_detailed'] = False
    objects.append(obj)
bpy.context.view_layer.update()
matrices = {obj.name: obj.matrix_world.copy() for obj in objects}
assert not scene.bbe_detailed_proxies
refs.load_post(None)
pack_sha = hd_library.characters_specification()['content_sha256']
for obj in objects:
    assert obj['bbe_character_detailed']
    assert obj.data.get('bbe_character_pack_sha256') == pack_sha
    assert len(obj.data.materials) > 1
    assert len({tuple(material.diffuse_color) for material in obj.data.materials if material}) > 1
    assert obj.matrix_world == matrices[obj.name]
old_mesh = objects[0].data
old_mesh['bbe_character_pack_sha256'] = 'older-pack'
refs.load_post(None)
assert objects[0].data != old_mesh
assert objects[0].data.get('bbe_character_pack_sha256') == pack_sha
assert objects[0].matrix_world == matrices[objects[0].name]
print('CHARACTER_AUTO_UPGRADE_OK', len(objects), 'colored HD meshes; transforms preserved')
addon.unregister()
