"""Exercise both native trim proxies, all Corvette finishes, and save/reopen."""
from pathlib import Path
import sys
import zlib
from tempfile import TemporaryDirectory

import bpy
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_support import addon, module

builder = module('builder_v2')
trim = module('utils.corvette_trim')
materials = module('utils.materials_v2')
select = module('utils.blend_utils').select
scene = bpy.context.scene
scene.nms_main.new_file()
scene.bbe_detailed_proxies = True
names = []
records = {}
for pid, (count, _, _) in trim.GEOMETRY.items():
    first = builder.add_part(pid, high_res=True).object
    mesh = first.data
    assert materials.is_high_res(first) and mesh.get(trim.TAG)
    attributes = np.empty(count, np.float32)
    mesh.attributes[trim.SHADE].data.foreach_get('value', attributes)
    expected = np.frombuffer(zlib.decompress(((module('hd_library').additions_root() / 'corvette_trim') / (pid + '.zlib')).read_bytes()), np.uint8)
    assert np.array_equal(attributes, expected.astype(np.float32) / 255) and np.ptp(attributes) == 1
    shader = mesh.materials[0]
    assert shader.get(trim.TAG)
    samplers = {'gDiffuseMap':'diffuse', 'gNormalMap':'normal', 'gMasksMap':'masks', 'colourise':'colourisemask'}
    for node_name, map_name in samplers.items():
        node = shader.node_tree.nodes[node_name]
        assert node.image.get(trim.TAG) == map_name and node.image.packed_file
        assert tuple(node.image.size) == (896,2048) and node.inputs['Vector'].is_linked
    shade = next(n for n in shader.node_tree.nodes if getattr(n,'attribute_name','') == trim.SHADE)
    assert shade.outputs['Fac'].is_linked
    for index, name in enumerate(trim.FINISHES):
        obj = first if index == 0 else builder.add_part(pid).object
        select(obj)
        scene.nms_main.material_switch = f'{index}_{name}'
        assert bpy.ops.object.nms_apply_colour(colour_index=99) == {'FINISHED'}
        assert obj[trim.LAYER] == index and obj.data is mesh
        assert all(abs(v-w)<1e-5 for v,w in zip(obj['nms_p'],materials.get_palette(99)['p']))
        assert int(obj['UserData']) == (index << 24) + 99
        names.append(obj.name)
        records[obj.name] = addon.BUILDER.get_builder_object_from_bpy_object(obj).serialise()
    assert [bpy.data.objects[n][trim.LAYER] for n in names[-4:]] == [0,1,2,3]
assert len([im for im in bpy.data.images if im.get(trim.TAG)]) == 4
unrelated = builder.add_part('B_GEN_4').object
assert not unrelated.data.get(trim.TAG)
with TemporaryDirectory() as tmp:
    bpy.ops.wm.save_as_mainfile(filepath=str(Path(tmp)/'native-trim.blend'))
    bpy.ops.wm.open_mainfile(filepath=str(Path(tmp)/'native-trim.blend'))
    for name in names:
        obj = bpy.data.objects[name]
        assert obj.data.get(trim.TAG) and all(im.packed_file for im in bpy.data.images if im.get(trim.TAG))
        assert addon.BUILDER.get_builder_object_from_bpy_object(obj).serialise() == records[name]
print('NATIVE TRIM PASS', bpy.app.version_string, flush=True)

