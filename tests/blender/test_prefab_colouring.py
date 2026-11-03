"""Prefab colour, texture and Scene Preview regressions using the reported project."""
from pathlib import Path
import hashlib
import json
import sys
import time

sys.path.insert(0, str(Path(__file__).parent))
from test_support import *

preset = module('preset')
stage = module('stages')
effects = module('stage_effects')
materials = module('utils.materials_v2')
userdata = module('utils.userdata')
select = module('utils.blend_utils').select
source = Path(r'G:\nmships\big wheel.blend')
digest = hashlib.sha256(source.read_bytes()).hexdigest()
repair = preset.restore_legacy_appearance
preset.restore_legacy_appearance = lambda scene: 0
bpy.ops.wm.open_mainfile(filepath=str(source), use_scripts=False)
preset.restore_legacy_appearance = repair
scene = bpy.context.scene


def records():
    return {o.name: addon.BUILDER.get_builder_object_from_bpy_object(o).serialise()
            for o in scene.objects if 'ObjectID' in o}


def paint(objects, index):
    select(objects)
    assert bpy.ops.object.nms_apply_colour(colour_index=index) == {'FINISHED'}


def displayed_material(obj):
    mat = obj.material_slots[0].material
    return mat.get('bbe_stage_source') or mat


before = records()
ring = [o for o in scene.objects if o.get('ObjectID') == 'B_DECO_R']
assert len(ring) > 1
assert all(not materials.is_high_res(o) for o in ring)
# Proxy recolouring must be visible immediately, before any refresh timer runs.
paint(ring[:2], 5)
for obj in ring[:2]:
    assert displayed_material(obj) == obj.data.materials[0]
    assert userdata.get_colour(int(obj['UserData'])) == 5
assert records()[ring[2].name] == before[ring[2].name]
effects.build(scene)
assert all(displayed_material(o) == o.data.materials[0] for o in ring[:2])
for obj in ring[:2]:
    module('utils.material').restore_material(obj, before[obj.name]['UserData'])

# An edited mesh must not be replaced merely because it retains a library tag.
edited = ring[-1]
edited.data = edited.data.copy()
edited.data.vertices[0].co.x += .125
edited_mesh = edited.data
custom = ring[-2]
effects.restore_object_materials(custom)
custom.data = custom.data.copy()
custom_material = bpy.data.materials.new('Builder custom shader')
custom.data.materials[0] = custom_material
custom_mesh = custom.data
start = time.perf_counter()
repair(scene)
elapsed = time.perf_counter() - start
assert records() == before, 'Appearance migration changed export records'
assert edited.data == edited_mesh
assert custom.data == custom_mesh and custom.data.materials[0] == custom_material
assert all(materials.is_high_res(o) for o in ring[:-2])
engine = scene.objects['engine block']
children = [o for o in engine.children_recursive if 'ObjectID' in o]
assert len(children) == 13 and all(materials.is_high_res(o) for o in children)
assert all(materials.is_colourable(o) for o in ring[:-2])
meshes = {o: o.data for o in children}
transforms = {o: o.matrix_world.copy() for o in children}
paint(engine, 5)
assert set(bpy.context.selected_objects) == {engine}
assert all(userdata.get_colour(int(o['UserData'])) == 5 for o in children)
assert all(o.data == meshes[o] and o.matrix_world == transforms[o] for o in children)
assert records()[ring[0].name] == before[ring[0].name]
assert all(tuple(o['nms_p']) == tuple(materials.get_palette(o['UserData'])['p']) for o in children)
select(engine)
scene.nms_main.color_picker = ring[0]
assert all(o['UserData'] == ring[0]['UserData'] for o in children)
presplit = records()
assert preset.Preset.split_to_parts(engine['PresetID']) >= len(children)
assert records() == presplit
paint(children, 9)
assert all(userdata.get_colour(int(o['UserData'])) == 9 for o in children)
assert all(o.parent is None and not o.hide_select for o in children)

# New prefabs follow the chosen model quality and retain colours on creation.
directory = QA / 'prefab_colour_fixtures'
directory.mkdir(exist_ok=True)
data = {'Objects': [{'ObjectID': '^B_DECO_R', 'UserData': 5,
                    'Position': [0, 0, 0], 'Up': [0, 1, 0], 'At': [0, 0, 1]}]}
(directory / 'colour.nmsprefab').write_text(json.dumps(data))
preset.Preset.PRESET_PATH = str(directory)
for detailed in (False, True):
    scene.nms_main.new_file()
    scene.bbe_detailed_proxies = detailed
    first = preset.Preset(preset_id='colour', builder_object=addon.BUILDER)
    child = first.control.children[0]
    assert materials.is_high_res(child) == detailed
    assert child['UserData'] == '5'
    assert all(not m.name.startswith('preset_material') for m in child.data.materials if m)
    second = first.duplicate()
    select(first.control)
    bpy.ops.object.nms_apply_default_colour()
    assert second.control.children[0]['UserData'] == '5'
    if not detailed:
        assert child.data is not second.control.children[0].data
    paint(first.control, 9)
    assert userdata.get_colour(int(child['UserData'])) == 9
    assert second.control.children[0]['UserData'] == '5'
    assert all(not m.name.startswith('preset_material') for m in second.control.children[0].data.materials if m)
    select(first.control)
    bpy.ops.object.nms_apply_default_colour()
    assert userdata.get_colour(int(child['UserData'])) == 0
    assert second.control.children[0]['UserData'] == '5'

assert hashlib.sha256(source.read_bytes()).hexdigest() == digest
report('prefab_colouring', dict(passed=True, blender=bpy.app.version_string,
       originalUnchanged=True, nativeRecordsPreserved=True, migrationSeconds=elapsed,
       intactAndSplit=True, hdAndSimple=True, immediatePreview=True,
       editedGeometryPreserved=True, independentCopies=True))
print('PREFAB_COLOURING_PASS', flush=True)
