"""Scene-derived pilot hands, with deferred Blender writes and private meshes.

The cockpit locator controls attachment. Native foot contacts can change the
whole character. Profiles use each appearance's native rig and metadata;
an unresolved build gets an explicitly labelled baseline preview.
"""
from collections import OrderedDict
import hashlib
import json
from pathlib import Path
import time

import bpy
import numpy as np
from bpy.app.handlers import persistent

from . import pilot_math
from .pilot_math import collisions, agreement

VERSION = 9
PRIVATE = 'bbe_pilot_posed_mesh'
STATUS = 'bbe_pilot_position_status'
WARNING = 'bbe_pilot_pose_warning'
ROOT = Path(__file__).parent
TO_NATIVE = np.array(((1,0,0,0),(0,0,1,0),(0,-1,0,0),(0,0,0,1)), float)
_resources = OrderedDict()
_solves = OrderedDict()
_vertices = OrderedDict()
_signatures = {}
_dirty = True
_due = 0.
_busy = False


class UnresolvedContact(ValueError):
    def __init__(self, query):
        super().__init__('Native collision geometry is unresolved at the pilot’s feet')
        self.diagnostics = query


def _bounded(cache, key, make, limit):
    if key not in cache:
        cache[key] = make()
        while len(cache) > limit:
            cache.popitem(last=False)
    cache.move_to_end(key)
    return cache[key]


def _json(path):
    stamp = (str(path), path.stat().st_mtime_ns, path.stat().st_size)
    return _bounded(_resources, stamp, lambda: json.loads(path.read_text(encoding='utf-8')), 16)


def _profile(race):
    path = ROOT / 'resources/pilot_profiles' / (race + '.json')
    return pilot_math.derive_foot_baselines(_json(path)) if path.is_file() else None


def _asset(race, detailed, base):
    from . import pilot_reference as reference
    adjacent = reference.asset_path(race, detailed).with_suffix('.skin.npz')
    bundled = ROOT / ('resources/hd_additions' if detailed else 'resources') / 'pilot_references' / adjacent.name
    path = adjacent if adjacent.is_file() else bundled
    stamp = (str(path), path.stat().st_mtime_ns, path.stat().st_size)
    def read():
        with np.load(path, allow_pickle=False) as packed:
            asset = {name: packed[name] for name in packed.files}
        # External HD packs may precede skin data. Accept the bundled skin only
        # when its complete baseline surface matches this exact mesh topology.
        baseline = pilot_math.blender_coordinates(pilot_math.skin(asset, pilot_math.apply_solver_pose(asset)))
        points = np.empty(len(base.vertices)*3, np.float64)
        base.vertices.foreach_get('co', points)
        if baseline.shape != (len(base.vertices),3) or np.max(np.abs(points.reshape(-1,3)-baseline)) > 2e-5:
            raise ValueError('Pilot model and hand calibration assets do not match')
        return asset
    return stamp, _bounded(_resources, ('skin',)+stamp, read, 16)


def scene_placements(scene, cockpit):
    """Use export's Y-scale and At direction, including hidden ObjectID parts."""
    from . import pilot_reference as reference
    parts = sorted((obj for obj in scene.objects if obj.get('ObjectID')),
                   key=lambda obj: obj.get('order', 0))
    placements = []
    target_index = None
    for index, obj in enumerate(parts):
        raw = TO_NATIVE @ np.asarray(obj.matrix_world, dtype=float)
        up, at = raw[:3,1], raw[:3,2]
        lengths = np.linalg.norm(raw[:3,:3], axis=0)
        if not np.isfinite(raw).all() or min(lengths[1:]) <= 0:
            raise ValueError('A build part has an invalid export transform')
        if abs(float(up @ at)) > lengths[1]*lengths[2]*1e-5:
            raise ValueError('A sheared build transform needs to be resolved before hand calibration')
        if obj == cockpit:
            if min(lengths) <= 0 or np.ptp(lengths) > max(lengths)*1e-4 or np.linalg.det(raw[:3,:3]) <= 0:
                raise ValueError('Pilot references require a positive, uniform cockpit scale')
            axes = raw[:3,:3]/lengths
            if np.max(np.abs(axes.T@axes-np.eye(3))) > 1e-5:
                raise ValueError('A sheared cockpit transform needs to be resolved before hand calibration')
            target_index = index
        matrix = collisions.exported_transform({'Position':raw[:3,3], 'Up':up, 'At':at})
        placements.append({'part_id':reference.cockpit_id(obj), 'part_index':index,
                           'user_data':int(obj.get('UserData',0)), 'matrix':matrix})
    if target_index is None:
        raise ValueError('First cockpit is missing from the build')
    unit = placements[target_index]['matrix'].copy()
    unit[:3,:3] /= np.linalg.norm(unit[:3,1])
    inverse = np.linalg.inv(unit)
    for placement in placements:
        placement['matrix'] = inverse @ placement['matrix']
    return placements, target_index


def solve_build(placements, target_index, locator, settings):
    catalog = _json(ROOT / 'resources/pilot_profiles/colliders.json')
    instances, _ = collisions.instantiate_transforms(catalog, placements)
    model = collisions.pilot_model_transform(placements[target_index]['matrix'], locator)
    # Preset size belongs to the character, independently of cockpit scale.
    # Keep the solver in native rig units and perform collision queries through
    # this outer transform. The skin libraries already contain preset size.
    appearance_scale = float(settings.get('appearance_scale', 1.))
    if not np.isfinite(appearance_scale) or appearance_scale <= 0:
        raise ValueError('Pilot appearance has an invalid native scale')
    model[:3,:3] *= appearance_scale
    feet = [c['settings'] for c in settings['constraints'] if c['kind']=='foot' and c['enabled']]
    extent = feet[0]['character_extent']
    _, pose = pilot_math.initial_pose(settings)
    profile_key = hashlib.sha256(json.dumps(settings,sort_keys=True).encode()).hexdigest()
    previous = None
    for iteration in range(16):
        rays = collisions.foot_ray_segments([pose[f['bone'],3,:3] for f in feet], model, extent)
        query = agreement.conservative_foot_corrections(rays, instances, model, extent,
                                                        model_y_scale=appearance_scale)
        corrections = query['corrections']
        if corrections is None:
            raise UnresolvedContact(query)
        key = (profile_key, np.asarray(corrections,np.float32).tobytes())
        solved = _bounded(_solves, key, lambda: pilot_math.solve_pilot(settings,
                          foot_corrections=corrections, foot_slopes=[0.]*len(feet)), 32)
        if previous is not None and np.max(np.abs(np.asarray(corrections)-previous)) < 1e-7:
            return {'solver':solved, 'solve_key':key, 'corrections':corrections,
                    'model_to_cockpit':model, 'iterations':iteration+1,
                    'conditions':query['conditions']}
        pose = solved['global_matrices']
        previous = np.asarray(corrections)
    raise ValueError('Pilot contact calculation did not settle')


def _replace_mesh(model, mesh):
    old = model.data
    model.data = mesh
    if old != mesh and old.get(PRIVATE) and old.users == 0:
        bpy.data.meshes.remove(old)


def _baseline(model, base, message):
    _replace_mesh(model, base)
    model[STATUS] = 'Baseline only · hand alignment unverified'
    model[WARNING] = message
    model.pop('bbe_pilot_contact_conditions',None)
    for key in ('bbe_pilot_foot_corrections', 'bbe_pilot_hand_positions'):
        model.pop(key, None)
    return {'status':'baseline', 'warning':message}


def update_model(scene, model, base_mesh=None):
    """Explicit actions may calculate synchronously; handlers only schedule."""
    from . import pilot_reference as reference, undo_guard
    undo_guard.track_generated_preview()
    race = model.get(reference.RACE,'')
    detailed = bool(model.get(reference.DETAIL,False))
    base = base_mesh if base_mesh is not None else reference.mesh_for(race,detailed)
    model['bbe_pilot_pose_version'] = VERSION
    model.pop('bbe_pilot_contact_diagnostics',None)
    try:
        if len(model.users_scene) > 1:
            return _baseline(model,base,'This pilot object is shared between scenes; make it single-user')
        settings = _profile(race)
        cockpit = reference.first_cockpit(scene)
        if settings is None:
            return _baseline(model,base,'This character has no calibrated hand profile yet')
        if reference.cockpit_id(cockpit) != 'B_COK_D':
            return _baseline(model,base,'Hand calibration currently covers the compact cockpit')
        placements,index = scene_placements(scene,cockpit)
        result = solve_build(placements,index,reference.NATIVE[reference.cockpit_id(cockpit)],settings)
        stamp,asset = _asset(race,detailed,base)
        solved = result['solver']
        key = (stamp,result['solve_key'])
        appearance_scale = float(settings.get('appearance_scale',1.))
        asset_scale = float(asset.get('appearance_scale',1.))
        if abs(appearance_scale-asset_scale) > 1e-6:
            raise ValueError('Pilot rig and mesh appearance scales do not match')
        local = solved['local_matrices'].copy()
        local[:,3,:3] *= appearance_scale
        points = _bounded(_vertices,key,lambda: pilot_math.blender_coordinates(pilot_math.skin(asset,
                         pilot_math.apply_solver_pose(asset,solved['names'],local))),8)
        if model.data.users > 1 or not model.data.get(PRIVATE) or model.data.get('bbe_pilot_base_asset') != base.get('bbe_pilot_asset'):
            private = base.copy()
            private.pop('bbe_pilot_asset',None)
            private[PRIVATE] = True
            private['bbe_pilot_base_asset'] = base.get('bbe_pilot_asset','')
            _replace_mesh(model,private)
        model.data.vertices.foreach_set('co',points.ravel())
        model.data.update()
        captured = settings.get('provenance',{}).get('kind') == 'saved_runtime_input_semantics'
        status = 'calibrated' if captured else 'source-derived'
        model[STATUS] = ('Calibrated hands · native build contacts' if captured else
                         'Native pilot math · source character profile')
        model[WARNING] = ('' if captured else
                          'This appearance uses its native rig and settings; its hand alignment has not been independently sampled in game')
        model['bbe_pilot_contact_conditions'] = json.dumps(result['conditions'],sort_keys=True)
        model['bbe_pilot_foot_corrections'] = list(result['corrections'])
        hands = {name:collisions.point(result['model_to_cockpit'],value).tolist()
                 for name,value in solved['positions'].items() if 'Wrist' in name}
        model['bbe_pilot_hand_positions'] = json.dumps(hands,sort_keys=True)
        return {'status':status,'hands':hands,'corrections':result['corrections'],
                'iterations':result['iterations'],'conditions':result['conditions']}
    except (ValueError,OSError,KeyError,NotImplementedError) as exc:
        if hasattr(exc,'diagnostics'):
            model['bbe_pilot_contact_diagnostics'] = json.dumps(exc.diagnostics,sort_keys=True)
        return _baseline(model,base,str(exc))


def _signature(scene, models, cockpit):
    placements,index = scene_placements(scene,cockpit)
    return (cockpit.name_full,index,
            tuple((p['part_id'],p['user_data'],tuple(np.round(p['matrix'].ravel(),9))) for p in placements),
            tuple((m.name_full,m.get('bbe_pilot_race'),bool(m.get('bbe_pilot_detail')),
                   m.get('bbe_pilot_pose_version'),m.parent.name_full if m.parent else None,
                   m.get('bbe_pilot_locator_id')) for m in models))


def update_scene(scene, force=False):
    from . import pilot_reference as reference, undo_guard
    models = [obj for obj in scene.objects if obj.get(reference.TAG)]
    if not models:
        return []
    undo_guard.track_generated_preview()
    cockpit = reference.first_cockpit(scene)
    key = scene.as_pointer()
    try:
        signature = _signature(scene,models,cockpit)
    except ValueError as exc:
        signature = ('invalid',str(exc),tuple(m.name_full for m in models))
    if not force and _signatures.get(key) == signature:
        return []
    reports = []
    for model in models:
        try:
            if cockpit is not None and (model.get(reference.TARGET) != cockpit or
                                      model.get('bbe_pilot_locator_id') != reference.cockpit_id(cockpit) or
                                      model.get('bbe_pilot_pose_version') != VERSION or
                                      model.parent is None or not model.parent.get(reference.ROOT_TAG)):
                reference.retarget_reference(model,cockpit)
            reports.append(update_model(scene,model))
        except (ValueError,OSError,RuntimeError) as exc:
            try:
                base = reference.mesh_for(model[reference.RACE],bool(model.get(reference.DETAIL)))
                reports.append(_baseline(model,base,str(exc)))
            except (ValueError,OSError,RuntimeError):
                model[STATUS] = 'Pilot unavailable · remove and choose again'
                model[WARNING] = str(exc)
                reports.append({'status':'unavailable','warning':str(exc)})
    try:
        _signatures[key] = _signature(scene,models,cockpit)
    except ValueError:
        _signatures[key] = signature
    return reports


@persistent
def invalidate(*_):
    global _dirty,_due
    _signatures.clear()
    _dirty = True
    _due = time.monotonic()+.2


@persistent
def on_depsgraph(scene,depsgraph):
    global _dirty,_due
    from . import undo_guard
    if _busy or not undo_guard.history_ready():
        return
    for update in depsgraph.updates:
        item = update.id.original
        if isinstance(item,bpy.types.Object):
            if item.get('bbe_pilot_reference') or item.get('bbe_pilot_root'):
                continue
            relevant = item.type not in {'CAMERA','LIGHT'}
        elif isinstance(item,bpy.types.Mesh):
            relevant = not (item.get(PRIVATE) or item.get('bbe_pilot_asset'))
        else:
            relevant = isinstance(item,(bpy.types.Scene,bpy.types.Collection))
        if relevant:
            _dirty = True
            _due = time.monotonic()+.2
            break


def tick():
    global _dirty,_busy
    from . import undo_guard
    if not _dirty or _busy or time.monotonic() < _due or not undo_guard.history_ready():
        return .2
    if bpy.app.is_job_running('RENDER') or bpy.context.mode != 'OBJECT':
        return .2
    _dirty = False
    _busy = True
    try:
        for scene in bpy.data.scenes:
            update_scene(scene)
    except (ReferenceError,RuntimeError) as exc:
        print('BBE pilot refresh:',exc)
        _dirty = True
    finally:
        _busy = False
    return .2


_HANDLERS = ((bpy.app.handlers.depsgraph_update_post,on_depsgraph),
             (bpy.app.handlers.load_pre,invalidate),(bpy.app.handlers.load_post,invalidate),
             (bpy.app.handlers.undo_pre,invalidate),(bpy.app.handlers.undo_post,invalidate),
             (bpy.app.handlers.redo_pre,invalidate),(bpy.app.handlers.redo_post,invalidate))


def register():
    invalidate()
    for handlers,callback in _HANDLERS:
        if callback not in handlers:
            handlers.append(callback)
    if not bpy.app.timers.is_registered(tick):
        bpy.app.timers.register(tick,first_interval=.25,persistent=True)


def unregister():
    if bpy.app.timers.is_registered(tick):
        bpy.app.timers.unregister(tick)
    for handlers,callback in _HANDLERS:
        if callback in handlers:
            handlers.remove(callback)
    _signatures.clear()
    _resources.clear()
    _solves.clear()
    _vertices.clear()
