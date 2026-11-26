"""Durable UI defaults, independent of .blend files and game-save destinations.

Only addon preferences and the reviewed tool settings below are remembered.
Object transforms, imported metadata, destination IDs and modal operations are
deliberately outside this store. Both builders use separate local files.
"""
import json
import os
from pathlib import Path
import bpy
from bpy.app.handlers import persistent

PLUS = __package__.endswith('bbe_plus')
PREFIX = 'bbeplus' if PLUS else 'bbe'
SCENE_FIELDS = (
    'bbeplus_hd', 'bbeplus_auto_snap', 'bbeplus_cable',
    'bbeplus_solid_textures', 'bbeplus_solid_decals', 'bbeplus_quick',
    'bbeplus_plane', 'bbeplus_export_format', 'bbeplus_copy_full',
    'bbeplus_material', 'bbeplus_curve_helper', 'bbeplus_mirror_options',
    'bbeplus_mirror_duplicate', 'bbeplus_mirror_axis', 'bbeplus_mirror_center',
    'bbeplus_save_enabled', 'bbeplus_base_type', 'bbeplus_category',
    'bbeplus_group', 'bbeplus_browse_mode', 'bbeplus_boundary_mode',
) if PLUS else (
    'bbe_detailed_proxies', 'bbe_solid_decals', 'bbe_curve_helper',
    'bbe_curve_plane', 'bbe_boundary_mode',
)
GROUP_FIELDS = {} if PLUS else {
    'bbe_cutaway': ('shown',),
    'nms_main': ('line_switch', 'material_switch', 'check_export_objects_only'),
    'nms_build_tool': ('check_show_advanced_options', 'check_auto_duplicate',
                       'mirror_direction', 'center_of_reflection'),
    'nms_batch_tool': ('nms_batch_replace_type', 'object_id'),
    'nms_asset_browser': ('enum_asset_browser_mode', 'enum_asset_browser_what_to_display',
                          'asset_browser_caterogies', 'asset_browser_sub_caterogies',
                          'category_expanded'),
    'nms_save_data': ('check_plugin_enabled', 'nms_base_type', 'check_also_update_name'),
}
STAGE_FIELDS = ('environment', 'quality', 'ray_tracing', 'ship_lights', 'light_strength',
                'glow', 'pad_radius', 'brightness', 'sun_azimuth', 'sun_elevation', 'enabled')
GROUP_FIELDS['bbeplus_stage' if PLUS else 'bbe_stage'] = STAGE_FIELDS
_state = {}
_baseline = None
_scene = None
_ready = False
_loading = False
_applying = False
_owner = object()
_reported = set()


def path():
    return Path(bpy.utils.user_resource('CONFIG', create=True)) / (PREFIX+'-settings.json')


def preferences():
    addon = bpy.context.preferences.addons.get(__package__)
    return addon.preferences if addon else None


def preference_fields(pref):
    if pref is None:
        return ()
    # These controls save Blender preferences on click. Older snapshots must
    # not overwrite them at startup or when opening another project.
    return tuple(p.identifier for p in pref.bl_rna.properties
                 if p.identifier not in {'rna_type', 'bl_idname', 'shape_use_blender_tools', 'decal_projection_disabled'}
                 and p.type in {'BOOLEAN', 'INT', 'FLOAT', 'STRING', 'ENUM'}
                 and not p.is_readonly and p.subtype != 'PASSWORD')


def bindings(scene):
    yield '', scene, SCENE_FIELDS
    for group, fields in GROUP_FIELDS.items():
        obj = getattr(scene, group, None)
        if obj is not None:
            yield group, obj, fields


def values(obj, fields):
    result = {}
    for name in fields:
        try:
            value = getattr(obj, name)
            if isinstance(value, (str, bool, int, float)):
                result[name] = value
        except (AttributeError, ReferenceError, TypeError):
            pass
    return result


def snapshot():
    pref = preferences()
    return {'preferences': values(pref, preference_fields(pref)),
            'scene': {group: values(obj, fields)
                      for group, obj, fields in bindings(bpy.context.scene)}}


def report(key, error):
    if key not in _reported:
        print(f'{PREFIX} settings memory: {key}: {error}')
        _reported.add(key)


def assign(obj, fields, saved):
    if not isinstance(saved, dict):
        return
    for name in fields:
        if name not in saved:
            continue
        try:
            current = getattr(obj, name)
            value = saved[name]
            if not isinstance(value, type(current)):
                continue
            if current != value:
                setattr(obj, name, value)
        except (AttributeError, ReferenceError, TypeError, ValueError, RuntimeError) as error:
            # Removed dynamic choices must not prevent the other settings loading.
            report(name, error)


def write():
    temp = path().with_suffix(f'.{os.getpid()}.tmp')
    try:
        temp.write_text(json.dumps({'version': 1, **_state}, indent=2), encoding='utf8')
        temp.replace(path())
        return True
    except OSError as error:
        report('write', error)
        return False


def flush():
    """Capture UI changes, without treating a new scene as a new preference."""
    global _baseline
    if not _ready or _loading or _applying or bpy.context.scene is None:
        return
    if bpy.context.scene.as_pointer() != _scene:
        restore(scene_only=True)
        return
    current = snapshot()
    if current == _baseline:
        return
    for section in ('preferences', 'scene'):
        if section == 'preferences':
            _state.setdefault(section, {}).update(current[section])
        else:
            for group, entries in current[section].items():
                _state.setdefault(section, {}).setdefault(group, {}).update(entries)
    if write():
        _baseline = current


def restore(scene_only=False, reset_connectors=False):
    global _applying, _baseline, _scene, _ready
    scene = bpy.context.scene
    if scene is None:
        return
    _applying = True
    try:
        if not scene_only:
            pref = preferences()
            assign(pref, preference_fields(pref), _state.get('preferences', {}))
        saved = _state.get('scene', {})
        stage_changed = False
        for group, obj, fields in bindings(scene):
            previous = values(obj, fields) if group.endswith('_stage') else None
            assign(obj, fields, saved.get(group, {}))
            if previous is not None:
                stage_changed = previous != values(obj, fields)
        if stage_changed:
            from . import stages
            stages.apply(scene, show_progress=False)
        if reset_connectors:
            for item in bpy.data.scenes:
                if hasattr(item, PREFIX+'_show_connectors'):
                    setattr(item, PREFIX+'_show_connectors', True)
        _scene = scene.as_pointer()
        _baseline = snapshot()
        _ready = True
        subscribe()
    finally:
        _applying = False


def subscribe():
    bpy.msgbus.clear_by_owner(_owner)
    pref = preferences()
    objects = [(pref, preference_fields(pref))]
    objects.extend((obj, fields) for _, obj, fields in bindings(bpy.context.scene))
    for obj, fields in objects:
        if obj is None:
            continue
        for name in fields:
            if hasattr(obj, name):
                bpy.msgbus.subscribe_rna(key=(type(obj), name), owner=_owner,
                                        args=(), notify=flush)


@persistent
def before_load(*_):
    global _loading
    flush()
    _loading = True


@persistent
def after_load(*_):
    global _loading, _ready
    _loading = False
    _ready = False


@persistent
def before_save(*_):
    flush()


def tick():
    if _loading:
        return .5
    try:
        if not _ready:
            restore(reset_connectors=True)
        else:
            flush()
    except (AttributeError, ReferenceError, RuntimeError) as error:
        report('refresh', error)
    return .5


def register():
    global _state, _baseline, _scene, _ready, _loading
    try:
        data = json.loads(path().read_text(encoding='utf8'))
        _state = {k: data[k] for k in ('preferences', 'scene') if isinstance(data.get(k), dict)}
    except (OSError, ValueError, TypeError, AttributeError):
        _state = {}
    _baseline = None
    _scene = None
    _ready = _loading = False
    for handlers, fn in ((bpy.app.handlers.load_pre, before_load),
                         (bpy.app.handlers.load_post, after_load),
                         (bpy.app.handlers.save_pre, before_save)):
        if fn not in handlers:
            handlers.append(fn)
    bpy.app.timers.register(tick, first_interval=.2, persistent=True)


def unregister():
    global _ready
    flush()
    _ready = False
    bpy.msgbus.clear_by_owner(_owner)
    if bpy.app.timers.is_registered(tick):
        bpy.app.timers.unregister(tick)
    for handlers, fn in ((bpy.app.handlers.load_pre, before_load),
                         (bpy.app.handlers.load_post, after_load),
                         (bpy.app.handlers.save_pre, before_save)):
        if fn in handlers:
            handlers.remove(fn)
