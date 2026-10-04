"""Exercise the real colour operator on shared meshes in one collection."""
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_support import *

v2 = module('builder_v2')
materials = module('utils.materials_v2')
select = module('utils.blend_utils').select
baseline = '--baseline' in sys.argv

bpy.context.scene.nms_main.new_file()
parts = [v2.add_part('BUILDFLATPANEL', high_res=False, user_data=0).object
         for _ in range(4)]
for obj in parts[1:]:
    obj.data = parts[0].data
select(parts[:3])
before = tuple(parts[3].color)
assert len(bpy.context.selected_objects) == 3
try:
    assert bpy.ops.object.nms_apply_colour(colour_index=37) == {'FINISHED'}
except RuntimeError as error:
    # The old operator redraws through a GUI-only timer after applying paint.
    assert baseline and 'wm.redraw_timer.poll() failed' in str(error), str(error)
expected = tuple(parts[0].data.materials[0].diffuse_color)
coloured = [obj.name for obj in parts[:3]
            if max(abs(a-b) for a,b in zip(obj.color, expected)) < 0.00001]
data = {'selected': 3, 'visiblyColoured': len(coloured),
        'colours': [list(obj.color) for obj in parts],
        'userdata': [obj['UserData'] for obj in parts],
        'blender': bpy.app.version_string, 'addon': str(D)}
report('batch_colour_baseline' if baseline else 'batch_colour', data)
if baseline:
    assert len(coloured) == 1, data
else:
    assert len(coloured) == 3, data
    assert tuple(parts[3].color) == before and parts[3]['UserData'] == '0'
    assert parts[3].data is not parts[0].data
    assert all(obj.data is parts[0].data for obj in parts[:3])
    assert all(obj['readonly:Colour'] == parts[0]['readonly:Colour'] for obj in parts[:3])
    assert all(obj['readonly:Material'] == parts[0]['readonly:Material'] for obj in parts[:3])

    # The same native ID can have HD and proxy placements in one selection.
    bpy.context.scene.nms_main.new_file()
    proxies = [v2.add_part('BUILDFLATPANEL', high_res=False, user_data=0).object
               for _ in range(3)]
    hd = [v2.add_part('BUILDFLATPANEL', high_res=True, user_data=0).object
          for _ in range(2)]
    userdata = module('utils.userdata')
    reserved = (1 << 8) | (1 << 16) | (1 << 17)
    proxies[1]['UserData'] = str(reserved)
    selected = proxies[:2] + hd
    meshes = [obj.data for obj in hd]
    select(selected)
    transforms = [obj.matrix_world.copy() for obj in selected]
    assert bpy.ops.object.nms_apply_colour(colour_index=37) == {'FINISHED'}
    assert all(materials.is_high_res(obj) and obj.data is mesh for obj,mesh in zip(hd, meshes))
    assert int(proxies[1]['UserData']) & reserved == reserved
    assert int(proxies[0]['UserData']) & reserved == 0
    assert all(userdata.get_colour(int(obj['UserData'])) == 37 for obj in selected)
    assert proxies[2]['UserData'] == '0'
    assert set(bpy.context.selected_objects) == set(selected)
    assert all(obj.matrix_world == transform for obj,transform in zip(selected, transforms))
    for obj in selected:
        exported = module('part').Part.deserialise_from_object(obj, addon.BUILDER).serialise()
        assert int(exported['UserData']) == int(obj['UserData'])
    assert all(max(abs(a-b) for a,b in zip(obj.color, proxies[0].color)) < 0.00001
               for obj in selected)

    # Picking a colour must also update the object colour of every proxy copy.
    select(proxies)
    assert bpy.ops.object.nms_apply_colour(colour_index=45) == {'FINISHED'}
    reference = v2.add_part('BUILDWALL', high_res=False, user_data=0).object
    select(reference)
    assert bpy.ops.object.nms_apply_colour(colour_index=37) == {'FINISHED'}
    select(proxies)
    bpy.context.scene.nms_main.color_picker = reference
    assert all(tuple(obj.color) == tuple(reference.color) for obj in proxies)
    assert all(obj['readonly:Colour'] == reference['readonly:Colour'] for obj in proxies)
    data.update(mixedHDAndProxiesPreserved=True, reservedBitsPreserved=True,
                unselectedUntouched=True, selectionAndTransformsPreserved=True,
                exportedColoursVerified=True, colourPickerUpdatesEveryCopy=True)
    report('batch_colour', data)
