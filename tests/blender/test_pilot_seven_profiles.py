"""All native appearance profiles through Blender, with supplied builds read-only."""
from pathlib import Path
import hashlib
import json
import os
import sys
import bpy
import numpy as np
from mathutils import Matrix

sys.path.insert(0, str(Path(__file__).parent))
from test_support import module, QA
reference, pose, guard = (module(x) for x in ('pilot_reference', 'pilot_pose', 'undo_guard'))
research = Path(os.environ.get('BBE_PILOT_RESEARCH', r'C:\Users\kengo\OneDrive\Desktop\NMS\cockpit_seating_research'))
bench = research/'user_bench'
source = bench/'uso_chair_only/uso_chair_only_research.blend'
grid_file = bench/'new_uso_grid_audit/geometry.json'
source_hashes = {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in (source, grid_file)}
addon = Path(reference.__file__).parent
armoured_path = addon/'resources/pilot_profiles/ASTRO_ARMOURED.json'
armoured_hash = hashlib.sha256(armoured_path.read_bytes()).hexdigest()
races = ('ASTRO_ARMOURED', 'ASTRO_DEFAULT', 'GEK_DEFAULT', 'KORVAX_DEFAULT', 'VYKEEN_DEFAULT', 'FOURTH_DEFAULT', 'BUI_DEFAULT')

original_asset_path = reference.asset_path
def asset_path(race, detailed):
    staged = addon/'resources/hd_additions/pilot_references'/f'{race}.blend'
    return staged if detailed and staged.is_file() else original_asset_path(race, detailed)
if not os.environ.get('BBE_PILOT_USE_PACKAGED_ASSETS'):
    reference.asset_path = asset_path

def mesh_hash(mesh):
    values = np.empty(len(mesh.vertices)*3, np.float64)
    mesh.vertices.foreach_get('co', values)
    return hashlib.sha256(values.tobytes()).hexdigest()

def select(scene, obj):
    bpy.context.window.scene = scene
    for selected in bpy.context.selected_objects:
        selected.select_set(False)
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    bpy.context.view_layer.update()

bpy.ops.wm.open_mainfile(filepath=str(source), load_ui=False)
guard._resume_at = 0.
original = bpy.context.scene
for obj in list(original.objects):
    if not obj.get('ObjectID'):
        bpy.data.objects.remove(obj, do_unlink=True)
grid = bpy.data.scenes.new('QA seven profiles stripped grid')
dummy = bpy.data.meshes.new('QA noncollision proxy')
dummy.from_pydata([(50,50,50),(51,50,50),(50,51,50)], [], [(0,1,2)])
for row in json.loads(grid_file.read_text())['objects']:
    if not row.get('id'):
        continue
    obj = bpy.data.objects.new(row['name'], dummy)
    grid.collection.objects.link(obj)
    obj['ObjectID'], obj['order'] = row['id'], row.get('order', 0)
    obj['UserData'] = str(row.get('properties',{}).get('UserData',0))
    obj.matrix_world = Matrix(row['matrix'])

reports = []
for scene, case in ((original,'original302'), (grid,'grid94')):
    cockpit = reference.first_cockpit(scene)
    original_matrix = cockpit.matrix_world.copy()
    select(scene, cockpit)
    native_parts = [obj for obj in scene.objects if obj.get('ObjectID')]
    export_signature = [(o.name, o['ObjectID'], np.asarray(o.matrix_world).copy()) for o in native_parts]
    copied = bpy.data.scenes.new('Unrelated renamed ship '+case)
    copied['shipName'] = 'Copied ship with a different name'
    for i, original_part in enumerate(native_parts):
        duplicate = original_part.copy()
        duplicate.name = 'Renamed component '+str(i)
        duplicate.parent = None
        copied.collection.objects.link(duplicate)
        duplicate.matrix_world = original_part.matrix_world.copy()
    copied_cockpit = reference.first_cockpit(copied)
    for race in races:
        scene.bbe_detailed_proxies = False
        canonical = reference.mesh_for(race, False)
        before = mesh_hash(canonical)
        model = reference.choose(bpy.context, race)
        result = pose.update_model(scene, model)
        assert result['status'] != 'baseline', (case, race, result)
        assert result['status'] == ('calibrated' if race=='ASTRO_ARMOURED' else 'source-derived')
        assert model.data.get(pose.PRIVATE) and model.data != canonical
        assert mesh_hash(canonical) == before
        hands = {k:np.asarray(v) for k,v in result['hands'].items()}
        assert len(hands) == 2 and all(np.isfinite(v).all() for v in hands.values())
        select(copied, copied_cockpit)
        copied.bbe_detailed_proxies = False
        copied_model = reference.choose(bpy.context, race)
        copied_result = pose.update_model(copied, copied_model)
        assert copied_result['status'] == result['status'], copied_result
        assert copied_result['corrections'] == result['corrections']
        assert copied_result['hands'] == result['hands'], (case, race, copied_result, result)
        assert copied_model.data != model.data
        select(scene, cockpit)
        scene.bbe_detailed_proxies = True
        detailed = reference.mesh_for(race, True)
        detailed_before = mesh_hash(detailed)
        reference.sync_scene_quality(scene, True)
        high = pose.update_model(scene, model)
        assert high['status'] == result['status'], (case,race,high)
        assert max(np.linalg.norm(hands[k]-v) for k,v in high['hands'].items()) < 1e-6
        assert mesh_hash(detailed) == detailed_before
        row = dict(case=case, preset=race, status=result['status'], corrections=result['corrections'],
                   detailed_asset_path=str(reference.asset_path(race, True)),
                   hands=result['hands'], light_vertices=len(canonical.vertices), detailed_vertices=len(detailed.vertices),
                   quality_independent_hands=True, canonical_meshes_unchanged=True,
                   renamed_copied_build_identical=True, scales=[])
        settings = pose._profile(race)
        for scale in (1e-5, 1e-4, .001, .01, .05, .1, .25, .5, .75, 1., 1.5, 2., 4.):
            cockpit.scale = (scale,)*3
            bpy.context.view_layer.update()
            placements, index = pose.scene_placements(scene, cockpit)
            try:
                solved = pose.solve_build(placements, index, reference.NATIVE['B_COK_D'], settings)
                assert np.isfinite(solved['solver']['global_matrices']).all()
                row['scales'].append(dict(scale=scale, status='computed', corrections=solved['corrections']))
            except pose.UnresolvedContact as exc:
                row['scales'].append(dict(scale=scale, status='unresolved', diagnostics=exc.diagnostics))
        cockpit.matrix_world = original_matrix
        bpy.context.view_layer.update()
        reports.append(row)
        print('SEVEN_PROFILE_CASE', case, race, result['status'], 'computed scales', sum(s['status']=='computed' for s in row['scales']), flush=True)
    for name, part_id, matrix in export_signature:
        assert scene.objects[name]['ObjectID'] == part_id
        assert np.max(np.abs(np.asarray(scene.objects[name].matrix_world)-matrix)) < 1e-6
    reference.remove(bpy.context)

assert all(hashlib.sha256(Path(path).read_bytes()).hexdigest()==digest for path,digest in source_hashes.items())
assert hashlib.sha256(armoured_path.read_bytes()).hexdigest() == armoured_hash
reference.asset_path = original_asset_path
result = dict(status='PASS', profiles=reports, armoured_profile_sha256=armoured_hash, source_fixtures_unchanged=True,
              addon_path=str(addon), packaged_assets_only=bool(os.environ.get('BBE_PILOT_USE_PACKAGED_ASSETS')),
              scope='Source-derived all-race computational/Blender checks; captured Armoured live validation retained separately. Unresolved collision cases are reported explicitly.')
report_name = os.environ.get('BBE_PILOT_SEVEN_REPORT_NAME', 'pilot-seven-profiles.json')
assert Path(report_name).name == report_name
(QA/report_name).write_text(json.dumps(result, indent=2)+'\n')
print('SEVEN_NATIVE_PROFILES_PASS', len(reports), flush=True)
