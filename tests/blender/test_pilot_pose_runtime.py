"""Native pilot runtime lifecycle in isolated Blender; supplied fixtures are read-only.

Run with --background --factory-startup --python this_file. This checks the
Blender integration; real interactive Undo/Redo remains a separate UI check.
BBE_PILOT_RESEARCH may override the existing calibration research directory.
"""
from pathlib import Path
from types import SimpleNamespace
import hashlib
import json
import math
import os
import sys
import time

import bpy
import numpy as np
from mathutils import Matrix

sys.path.insert(0, str(Path(__file__).parent))
from test_support import module, QA

reference = module('pilot_reference')
pose = module('pilot_pose')
guard = module('undo_guard')
builder = module('builder')
research = Path(os.environ.get('BBE_PILOT_RESEARCH',
    r'C:\Users\kengo\OneDrive\Desktop\NMS\cockpit_seating_research'))
bench = research / 'user_bench'
source = bench / 'uso_chair_only/uso_chair_only_research.blend'
grid_file = bench / 'new_uso_grid_audit/geometry.json'
original_hash = hashlib.sha256(source.read_bytes()).hexdigest()
grid_hash = hashlib.sha256(grid_file.read_bytes()).hexdigest()
checks = {}


def coordinates(mesh):
    result = np.empty((len(mesh.vertices), 3), np.float64)
    mesh.vertices.foreach_get('co', result.ravel())
    return result


def fingerprint(mesh):
    return hashlib.sha256(coordinates(mesh).tobytes()).hexdigest()


def activate(scene, obj):
    bpy.context.window.scene = scene
    for other in bpy.context.selected_objects:
        other.select_set(False)
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    bpy.context.view_layer.update()


def native_parts(scene):
    return [obj for obj in scene.objects if obj.get('ObjectID')]


def exported(scene):
    bpy.context.window.scene = scene
    return [builder.Builder().serialise(**options)
            for options in ({}, {'get_presets': True}, {'as_prefab': True})]


def hands(model):
    return json.loads(model['bbe_pilot_hand_positions'])


def hand_error(actual, expected):
    assert set(actual) == set(expected), (actual.keys(), expected.keys())
    return max(float(np.linalg.norm(np.asarray(actual[name])-value))
               for name, value in expected.items())


def expected_hands(local, cockpit):
    # Independent native attachment equation: full-size pose, 180deg native-Y,
    # and the uniformly scaled PLAYERPOSITION translation.
    scale = cockpit.matrix_world.to_scale().y
    offset = np.asarray(reference.NATIVE[reference.cockpit_id(cockpit)])*scale
    return {name: np.asarray(value)*(-1, 1, -1)+offset for name, value in local.items()}


def report_calibrated(scene, model):
    result = pose.update_model(scene, model)
    assert result['status'] == 'calibrated', result
    assert model.data.get(pose.PRIVATE)
    assert not model.data.get('bbe_pilot_asset'), 'Posed mesh entered canonical asset cache'
    assert model['bbe_pilot_pose_version'] == pose.VERSION
    return result


def graph_for(item):
    return SimpleNamespace(updates=[SimpleNamespace(
        id=SimpleNamespace(original=item), is_updated_transform=True,
        is_updated_geometry=True)])


original_asset_path = reference.asset_path
def staged_asset(race, detailed):
    if detailed:
        staged = Path(reference.__file__).parent/'resources/hd_additions/pilot_references'/f'{race}.blend'
        if staged.is_file():
            return staged
    return original_asset_path(race, detailed)
if not os.environ.get('BBE_PILOT_USE_PACKAGED_ASSETS'):
    reference.asset_path = staged_asset

# Load the supplied research COPY, never save over it or the user's project.
bpy.ops.wm.open_mainfile(filepath=str(source), load_ui=False)
# Headless scripts do not yield to the UI timer. End the load recovery delay
# explicitly here; the real guarded path is exercised below with poisoned IDs.
guard._resume_at = 0.
original_scene = bpy.context.scene
original_scene.name = 'QA original USO 302'
for obj in list(original_scene.objects):
    if not obj.get('ObjectID'):
        bpy.data.objects.remove(obj, do_unlink=True)
assert len(native_parts(original_scene)) == 302
original_scene.bbe_detailed_proxies = False
cockpit = reference.first_cockpit(original_scene)
activate(original_scene, cockpit)
original_export = exported(original_scene)
canonical = reference.mesh_for('ASTRO_ARMOURED', False)
canonical_hash = fingerprint(canonical)
original_model = reference.choose(bpy.context, 'ASTRO_ARMOURED')
original_result = report_calibrated(original_scene, original_model)
assert np.max(np.abs(np.asarray(original_result['corrections'])-.4462478756904602)) < 2e-5
fixture = json.loads((bench/'native_pose_audit/original_uso_runtime/blender_scene_hand_validation.json').read_text())
expected = expected_hands(fixture['results'][0]['local_wrist_positions'], cockpit)
checks['original_wrist_max_error_m'] = hand_error(original_result['hands'], expected)
assert checks['original_wrist_max_error_m'] < 3e-5
original_coordinates = coordinates(original_model.data)
assert exported(original_scene) == original_export, 'Preview changed native export'

# Reconstruct the supplied grid's native placements with a dummy visible mesh.
# Native collision must depend on ObjectID/matrix, never this triangle.
grid_scene = bpy.data.scenes.new('QA stripped grid 94')
grid_scene.bbe_detailed_proxies = False
dummy = bpy.data.meshes.new('QA irrelevant proxy triangle')
dummy.from_pydata([(50,50,50),(51,50,50),(50,51,50)], [], [(0,1,2)])
grid_data = json.loads(grid_file.read_text())
for row in grid_data['objects']:
    if not row.get('id'):
        continue
    obj = bpy.data.objects.new(row['name'], dummy)
    grid_scene.collection.objects.link(obj)
    obj['ObjectID'] = row['id']
    obj['UserData'] = str(row.get('properties', {}).get('UserData', 0))
    obj['Timestamp'] = str(row.get('properties', {}).get('Timestamp', 0))
    obj['order'] = row.get('order', 0)
    obj.matrix_world = Matrix(row['matrix'])
assert len(native_parts(grid_scene)) == 94
grid_cockpit = reference.first_cockpit(grid_scene)
activate(grid_scene, grid_cockpit)
grid_export = exported(grid_scene)
grid_model = reference.choose(bpy.context, 'ASTRO_ARMOURED')
grid_result = report_calibrated(grid_scene, grid_model)
assert max(abs(value) for value in grid_result['corrections']) < 2e-5
runtime = bench/'native_pose_audit/original_uso_runtime'
oracle = json.loads((runtime/'offline_solver_oracle_no_hit.json').read_text())
named = json.loads((runtime/'named_pilot_solver_inputs.json').read_text())['joints']
oracle_globals = {}
for joint in named:
    local = np.asarray(oracle['output'][str(joint['native_index'])]).reshape(4,4).copy()
    # Native SIMD output's fourth lane is padding, not affine homogeneous data.
    local[:,3] = (0,0,0,1)
    oracle_globals[joint['name']] = (local if joint['parent'] is None else
                                    local @ oracle_globals[joint['parent']])
oracle_hands = {name:matrix[3,:3] for name,matrix in oracle_globals.items() if 'Wrist' in name}
checks['grid_wrist_oracle_max_error_m'] = hand_error(
    grid_result['hands'], expected_hands(oracle_hands, grid_cockpit))
assert checks['grid_wrist_oracle_max_error_m'] < 3e-5
assert grid_model.data != original_model.data and grid_model.data != canonical
assert np.array_equal(coordinates(original_model.data), original_coordinates)
assert fingerprint(canonical) == canonical_hash
assert exported(grid_scene) == grid_export
checks['private_mesh_and_export_isolation'] = True

# Same input after reconciliation must do no update, not merely produce equal
# coordinates. The [] public result means no update_model/mesh-write occurred.
pose.update_scene(grid_scene, force=True)
private = grid_model.data
private_hash = fingerprint(private)
for _ in range(4):
    assert pose.update_scene(grid_scene) == []
assert grid_model.data == private and fingerprint(private) == private_hash
pose._dirty = False
pose.on_depsgraph(grid_scene, graph_for(private))
assert not pose._dirty, 'Generated private mesh caused a feedback update'
pose.on_depsgraph(grid_scene, graph_for(grid_model))
assert not pose._dirty, 'Generated pilot object caused a feedback update'
checks['stable_input_no_writes'] = True

# A real cockpit-scale change must invalidate automatically. Use nearby micro
# scales with the supplied grid, preserving its independently proven no-hit case.
old_scale = grid_cockpit.scale.copy()
old_hands = hands(grid_model)
grid_cockpit.scale = old_scale*1.1
bpy.context.view_layer.update()
pose.on_depsgraph(grid_scene, graph_for(grid_cockpit))
assert pose._dirty
pose._due = 0.
guard._resume_at = 0.
pose.tick()
scaled_hands = hands(grid_model)
assert hand_error(scaled_hands, old_hands) > 1e-5
assert fingerprint(canonical) == canonical_hash
grid_cockpit.scale = old_scale
bpy.context.view_layer.update()
pose.update_scene(grid_scene, force=True)
assert hand_error(hands(grid_model), old_hands) < 3e-5
checks['automatic_scale_refresh'] = True

# Parent motion exercises the actual world matrices. A rigid movement of the
# whole build changes attachment in world space while preserving local contacts.
parent = bpy.data.objects.new('QA build parent', None)
grid_scene.collection.objects.link(parent)
for obj in native_parts(grid_scene):
    matrix = obj.matrix_world.copy()
    obj.parent = parent
    obj.matrix_world = matrix
parent.location = (2.5,-3.,1.2)
parent.rotation_euler = (.12,.2,-.32)
bpy.context.view_layer.update()
pose._dirty = False
pose.on_depsgraph(grid_scene, graph_for(parent))
assert pose._dirty, 'Parent transform was not observed'
pose.update_scene(grid_scene, force=True)
assert hand_error(hands(grid_model), old_hands) < 4e-5
checks['rigid_parent_invariance'] = True

# Quality/race selection must use canonical data and reapply the current pose.
reference.sync_scene_quality(grid_scene, True)
assert grid_model[reference.DETAIL]
assert grid_model.data.get(pose.PRIVATE)
assert hand_error(hands(grid_model), old_hands) < 4e-5
high_canonical = reference.mesh_for('ASTRO_ARMOURED', True)
high_hash = fingerprint(high_canonical)
reference.sync_scene_quality(grid_scene, False)
assert not grid_model[reference.DETAIL]
assert hand_error(hands(grid_model), old_hands) < 4e-5
activate(grid_scene, grid_cockpit)
reference.choose(bpy.context, 'GEK_DEFAULT')
assert grid_model.data.get(pose.PRIVATE)
assert 'source character profile' in grid_model[pose.STATUS].lower()
assert 'not been independently sampled' in grid_model[pose.WARNING]
assert len(hands(grid_model)) == 2
reference.choose(bpy.context, 'ASTRO_ARMOURED')
assert hand_error(hands(grid_model), old_hands) < 4e-5
assert fingerprint(canonical) == canonical_hash and fingerprint(high_canonical) == high_hash
checks['quality_and_race_restore'] = True

# Missing native catalog must preserve a usable, explicitly unverified baseline.
load_json = pose._json
def missing_catalog(path):
    if path.name == 'colliders.json':
        raise FileNotFoundError('QA missing native collision catalog')
    return load_json(path)
pose._json = missing_catalog
try:
    fallback = pose.update_model(grid_scene, grid_model)
    assert fallback['status'] == 'baseline' and 'missing' in fallback['warning'].lower()
    assert grid_model.data == canonical and 'bbe_pilot_hand_positions' not in grid_model
finally:
    pose._json = load_json
report_calibrated(grid_scene, grid_model)
checks['missing_catalog_safe_baseline'] = True

# Linked object duplicates can share an already posed mesh. Updating the copy
# in another build must first detach its mesh, preserving the original pose.
linked = original_model.copy()
linked.name = 'QA linked posed duplicate'
grid_scene.collection.objects.link(linked)
shared_private = original_model.data
shared_hash = fingerprint(shared_private)
assert linked.data == shared_private and shared_private.users >= 2
linked_result = report_calibrated(grid_scene, linked)
assert linked.data != shared_private
assert original_model.data == shared_private and fingerprint(shared_private) == shared_hash
assert hand_error(linked_result['hands'], old_hands) < 4e-5
linked_private = linked.data
bpy.data.objects.remove(linked, do_unlink=True)
if linked_private.users == 0:
    bpy.data.meshes.remove(linked_private)
checks['linked_private_mesh_detached'] = True

# One Object linked into two scenes cannot hold two independent poses. It must
# explicitly use baseline until made single-scene, then recover calibration.
grid_scene.collection.objects.link(original_model)
try:
    shared_result = pose.update_model(grid_scene, original_model)
    assert shared_result['status'] == 'baseline', shared_result
    assert 'shared between scenes' in shared_result['warning']
    assert original_model.data == canonical and 'bbe_pilot_hand_positions' not in original_model
finally:
    grid_scene.collection.objects.unlink(original_model)
report_calibrated(original_scene, original_model)
assert hand_error(hands(original_model), original_result['hands']) < 3e-5
checks['shared_object_explicit_baseline'] = True

# Mutating the ID on the same cockpit Object must refresh locator drivers even
# when its name, target pointer, and pose version have not changed.
grid_cockpit['ObjectID'] = 'B_COK_B'
bpy.context.view_layer.update()
changed_id = pose.update_scene(grid_scene)[0]
bpy.context.view_layer.update()
assert changed_id['status'] == 'baseline'
assert grid_model['bbe_pilot_locator_id'] == 'B_COK_B'
scale = grid_cockpit.matrix_world.to_scale().y
assert np.max(np.abs(np.asarray(grid_model.location)-
                     np.asarray(reference.NATIVE['B_COK_B'])*scale)) < 1e-5
grid_cockpit['ObjectID'] = 'B_COK_D'
bpy.context.view_layer.update()
assert pose.update_scene(grid_scene)[0]['status'] == 'calibrated'
assert grid_model['bbe_pilot_locator_id'] == 'B_COK_D'
assert hand_error(hands(grid_model), old_hands) < 4e-5
checks['cockpit_id_refreshes_locator'] = True

# Equal axis lengths and orthogonal Up/At do not rule out X-axis shear. Build
# it using a nonuniform parent and rotated child so Blender preserves the
# genuine world shear rather than decomposing a directly assigned matrix.
shear_parent = bpy.data.objects.new('QA nonuniform shear parent', None)
grid_scene.collection.objects.link(shear_parent)
old_parent = grid_cockpit.parent
old_world = grid_cockpit.matrix_world.copy()
old_parent_inverse = grid_cockpit.matrix_parent_inverse.copy()
shear_parent.scale = (1.,2.,math.sqrt(2.5))
grid_cockpit.parent = shear_parent
grid_cockpit.matrix_parent_inverse = Matrix.Identity(4)
grid_cockpit.location = (0.,0.,0.)
grid_cockpit.rotation_euler = (0.,0.,math.pi/4)
grid_cockpit.scale = (scale/math.sqrt(2.5),)*3
bpy.context.view_layer.update()
axes = np.asarray(grid_cockpit.matrix_world)[:3,:3]
lengths = np.linalg.norm(axes, axis=0)
assert np.ptp(lengths) < max(lengths)*1e-5
assert abs(float(axes[:,1] @ axes[:,2])) < lengths[1]*lengths[2]*1e-5
assert abs(float(axes[:,0] @ axes[:,1])) > lengths[0]*lengths[1]*.1
try:
    sheared_result = pose.update_model(grid_scene, grid_model)
    assert sheared_result['status'] == 'baseline', sheared_result
    assert 'sheared cockpit' in sheared_result['warning'].lower(), sheared_result
finally:
    grid_cockpit.parent = old_parent
    grid_cockpit.matrix_parent_inverse = old_parent_inverse
    grid_cockpit.matrix_world = old_world
    bpy.data.objects.remove(shear_parent, do_unlink=True)
    bpy.context.view_layer.update()
report_calibrated(grid_scene, grid_model)
assert hand_error(hands(grid_model), old_hands) < 4e-5
checks['full_gram_shear_rejected'] = True

# History callbacks cannot unwrap RNA/depsgraph IDs, including the delayed guard.
class RestoringGraph:
    @property
    def updates(self):
        raise AssertionError('Read dependency graph during history restoration')
try:
    guard.before_history(None)
    pose.invalidate(RestoringGraph())
    pose.on_depsgraph(None, RestoringGraph())
    assert pose.tick() == .2
    guard.after_history(None)
    pose.on_depsgraph(None, RestoringGraph())
    assert pose.tick() == .2
finally:
    guard._resume_at = time.monotonic()-1
    guard._release()
pose._due = 0.
pose.tick()
assert guard._generated_preview_history
checks['history_callbacks_deferred'] = True

# Remove all surrounding native parts from the original fixture. This is an
# isolated in-memory scene mutation; it must drop the observed raised contact.
activate(original_scene, cockpit)
for obj in list(native_parts(original_scene)):
    if obj != cockpit:
        bpy.data.objects.remove(obj, do_unlink=True)
bpy.context.view_layer.update()
pose._dirty = False
pose.on_depsgraph(original_scene, graph_for(original_scene))
assert pose._dirty, 'Membership/deletion update was not observed'
bare = pose.update_scene(original_scene, force=True)[0]
assert bare['status'] == 'calibrated', bare
assert max(abs(value) for value in bare['corrections']) < 2e-5
assert hand_error(bare['hands'], original_result['hands']) > .20
assert fingerprint(canonical) == canonical_hash
checks['collider_deletion_restores_no_hit'] = True

# Timer/handler idempotence, and deletion while work is pending.
for _ in range(2):
    pose.register()
assert bpy.app.timers.is_registered(pose.tick)
assert all(handlers.count(callback) == 1 for handlers, callback in pose._HANDLERS)
pose.invalidate()
activate(original_scene, cockpit)
reference.remove(bpy.context)
pose._due = 0.
pose.tick()
assert not any(obj.get(reference.TAG) for obj in original_scene.objects)
pose.unregister()
assert not bpy.app.timers.is_registered(pose.tick)
assert all(callback not in handlers for handlers, callback in pose._HANDLERS)
pose.register()
checks['pending_delete_and_registration'] = True

assert hashlib.sha256(source.read_bytes()).hexdigest() == original_hash
assert hashlib.sha256(grid_file.read_bytes()).hexdigest() == grid_hash
reference.asset_path = original_asset_path
result = {'status':'PASS', 'checks':checks,
          'source_fixtures_unchanged':True,
          'addon_path':str(Path(reference.__file__).parent.resolve()),
          'scope':'Headless runtime lifecycle and safe history hooks; interactive undo/redo and visual normals are separate UI checks.'}
report_name = os.environ.get('BBE_PILOT_TEST_REPORT_NAME', 'pilot-pose-runtime-test.json')
assert Path(report_name).name == report_name, 'Report override must be a filename'
(QA/report_name).write_text(json.dumps(result, indent=2)+'\n')
print('PILOT_POSE_RUNTIME_PASS', json.dumps(result), flush=True)
