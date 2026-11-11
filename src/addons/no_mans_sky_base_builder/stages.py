"""BBE presentation stages, authored for BBE, October 2026 (GPL-3.0).

An original, bounded-cost scene rig. No Charon Forge implementation or sky
tables are used. Generated scenery is display-only and has no ObjectID.
"""
from pathlib import Path
import json
import math
import bpy
from mathutils import Vector
from bpy.app.handlers import persistent
from bpy.props import BoolProperty, EnumProperty, FloatProperty, PointerProperty
from . import stage_effects, hd_library, icons

TAG = 'bbe_stage_owned'
STATE = 'bbe_stage_restore'
_signatures = {}
SLIDERS = ('brightness', 'light_strength', 'pad_radius', 'sun_azimuth', 'sun_elevation')


def views(scene):
    for window in bpy.context.window_manager.windows:
        if window.scene == scene:
            for area in window.screen.areas:
                if area.type == 'VIEW_3D':
                    yield window.screen, area, area.spaces.active


def migrate(scene):
    """Retire only the rig identified by the previous BBE integration."""
    old = scene.get('bbe_lighting')
    if old is None:
        return
    saved = scene.get('bbe_lighting_saved')
    if saved:
        previous = old.get('previous_world')
        if isinstance(previous, bpy.types.World) or previous is None:
            scene.world = previous
        for prop in ('view_transform', 'look', 'exposure', 'gamma'):
            if prop in saved:
                try:
                    setattr(scene.view_settings, prop, saved[prop])
                except (TypeError, ValueError):
                    pass
        del scene['bbe_lighting_saved']
    sun = old.get('managed_sun')
    for obj in scene.objects:
        if obj.type == 'LIGHT' and (obj.get('bbe_game_light') is not None or obj == sun):
            # Keep the datablocks for old-file recovery; they no longer render.
            obj.hide_render = obj.hide_viewport = True
    old['enabled'] = False


def snapshot(scene):
    s = scene.bbe_stage
    s.previous_world = scene.world
    if hasattr(scene, 'compositing_node_group'):
        s.previous_compositor = scene.compositing_node_group
    settings = {'engine': scene.render.engine,
                'use_compositing': scene.render.use_compositing,
                'view': {p: getattr(scene.view_settings, p) for p in ('view_transform', 'look', 'exposure', 'gamma')},
                'eevee': {}, 'views': []}
    for p in ('taa_samples', 'taa_render_samples', 'use_raytracing', 'use_fast_gi', 'use_shadow_jitter_viewport'):
        if hasattr(scene.eevee, p):
            settings['eevee'][p] = getattr(scene.eevee, p)
    for screen, area, space in views(scene):
        settings['views'].append({'screen': screen.name, 'area': list(screen.areas).index(area),
            'shading': {p: getattr(space.shading, p) for p in ('type', 'use_scene_world', 'use_scene_lights', 'use_scene_world_render', 'use_scene_lights_render', 'use_compositor')},
            'overlay': {p: getattr(space.overlay, p) for p in ('show_floor', 'show_axis_x', 'show_axis_y', 'show_axis_z', 'show_extras', 'show_relationship_lines')}})
    scene[STATE] = json.dumps(settings)


def restore(scene):
    s = scene.bbe_stage
    saved = json.loads(scene.get(STATE, '{}'))
    if not saved:
        return
    scene.world = s.previous_world
    if hasattr(scene, 'compositing_node_group'):
        scene.compositing_node_group = s.previous_compositor
    scene.render.use_compositing = saved.get('use_compositing', True)
    scene.render.engine = saved['engine']
    for p, v in saved['view'].items():
        setattr(scene.view_settings, p, v)
    for p, v in saved['eevee'].items():
        setattr(scene.eevee, p, v)
    for screen, area, space in views(scene):
        row = next((r for r in saved['views'] if r['screen'] == screen.name and r['area'] == list(screen.areas).index(area)), None)
        if row:
            for p, v in row['shading'].items():
                setattr(space.shading, p, v)
            for p, v in row['overlay'].items():
                setattr(space.overlay, p, v)
    del scene[STATE]
    s.previous_world = None
    s.previous_compositor = None


def clear(scene):
    coll = scene.bbe_stage.collection
    if not coll:
        stage_effects.restore_materials(scene)
        return
    # A duplicated scene can share collection pointers. Never destroy its rig.
    if any(s != scene and s.bbe_stage.collection == coll for s in bpy.data.scenes):
        if coll.name in scene.collection.children:
            scene.collection.children.unlink(coll)
        scene.bbe_stage.collection = None
        return
    stage_effects.restore_materials(scene)
    for obj in list(coll.objects):
        if obj.get(TAG):
            data = obj.data
            kind = obj.type
            bpy.data.objects.remove(obj, do_unlink=True)
            if data and data.users == 0:
                if kind == 'MESH':
                    bpy.data.meshes.remove(data)
                elif kind == 'LIGHT':
                    bpy.data.lights.remove(data)
    # Leave any user-added objects in the collection alone.


def prepare_import(scene):
    """Stop preview work before a bulk import or scene reset touches parts.

    Disabling shading alone leaves the effects timer active. Stop that timer's
    work first, restore the original materials, then keep every viewport Solid
    until the user explicitly enables Scene Preview again.
    """
    def solid():
        for window in bpy.context.window_manager.windows:
            if window.scene != scene:
                continue
            for area in window.screen.areas:
                for space in area.spaces:
                    if space.type == 'VIEW_3D':
                        space.shading.type = 'SOLID'
                        space.shading.use_compositor = 'DISABLED'
                area.tag_redraw()

    settings = scene.bbe_stage
    # Bypass the update callback so rendering stops before material cleanup.
    settings['enabled'] = False
    _signatures.pop(scene.as_pointer(), None)
    solid()
    try:
        clear(scene)
        restore(scene)
    finally:
        # Restoring the user's previous view can restore Material/Rendered too.
        solid()


def pad(coll, environment):
    # Version the cache: old saved previews can contain the former gravity shell.
    name = 'BBE Native Pad 18.1.7 / ' + environment
    mesh = bpy.data.meshes.get(name)
    if mesh is None:
        source = hd_library.scenes_root() / 'display' / (environment + '.blend')
        with bpy.data.libraries.load(str(source), link=False) as (_, target):
            target.objects = [environment]
        obj = target.objects[0]
        mesh = obj.data
        bpy.data.objects.remove(obj)
        mesh.name = name
        mesh.use_fake_user = True
    obj = bpy.data.objects.new(name, mesh)
    obj[TAG] = True
    obj.hide_select = True
    coll.objects.link(obj)


def world(scene):
    s = scene.bbe_stage
    w = s.world
    if not w or any(other != scene and other.bbe_stage.world == w for other in bpy.data.scenes):
        w = bpy.data.worlds.new('BBE Stage World')
        s.world = w
    w.use_nodes = True
    nt = w.node_tree
    nt.nodes.clear()
    def node(kind): return nt.nodes.new(kind)
    output = node('ShaderNodeOutputWorld')
    ambient = node('ShaderNodeBackground')
    ambient.inputs['Color'].default_value = (.16,.20,.27,1)
    ambient.inputs['Strength'].default_value = .35
    background = node('ShaderNodeBackground')
    background.inputs['Strength'].default_value = .7
    background.inputs['Color'].default_value = (.008,.016,.03,1)
    if s.environment in {'SPACE', 'OUTPOST'}:
        image_path = hd_library.scenes_root() / 'display' / 'space.png'
        backdrop = node('ShaderNodeTexEnvironment')
        backdrop.image = bpy.data.images.load(str(image_path), check_existing=True)
        nt.links.new(backdrop.outputs['Color'], background.inputs['Color'])
    path = node('ShaderNodeLightPath')
    mix = node('ShaderNodeMixShader')
    nt.links.new(path.outputs['Is Camera Ray'], mix.inputs[0])
    nt.links.new(ambient.outputs[0], mix.inputs[1])
    nt.links.new(background.outputs[0], mix.inputs[2])
    nt.links.new(mix.outputs[0], output.inputs[0])
    scene.world = w


def configure_views(scene):
    saved = json.loads(scene.get(STATE, '{}'))
    for screen, area, space in views(scene):
        # Upgrade snapshots saved before relationship overlays were managed.
        row = next((r for r in saved.get('views', []) if r['screen'] == screen.name and r['area'] == list(screen.areas).index(area)), None)
        if row:
            row['overlay'].setdefault('show_relationship_lines', space.overlay.show_relationship_lines)
        space.shading.type = 'MATERIAL'
        for p in ('use_scene_world','use_scene_lights','use_scene_world_render','use_scene_lights_render'):
            setattr(space.shading,p,True)
        space.shading.use_compositor = 'ALWAYS' if scene.bbe_stage.glow else 'DISABLED'
        for p in ('show_floor','show_axis_x','show_axis_y','show_axis_z','show_extras','show_relationship_lines'):
            setattr(space.overlay,p,False)
        area.tag_redraw()
    if saved:
        scene[STATE] = json.dumps(saved)


def build(scene, progress=None):
    s = scene.bbe_stage
    if progress:
        progress.update(.04, 'Clearing previous preview')
    clear(scene)
    coll = s.collection
    if not coll:
        coll = bpy.data.collections.new('BBE Display Stage')
        scene.collection.children.link(coll)
        s.collection = coll
    world(scene)
    radius = stage_effects.preview_value(scene, 'pad_radius')
    if s.environment in {'STATION', 'OUTPOST'}:
        pad(coll, s.environment)
    if progress:
        progress.update(.14, 'Setting up lighting')
    # Viewer-style cool key, teal rim and warm fill. Only the key casts shadows.
    for name, xyz, color, energy, shadow in (
        ('Key',(-.5,-.4,1.1),(.72,1,1),1800,True),
        ('Fill',(.75,-.3,.6),(1,.65,.38),800,False),
        ('Rim',(0,.7,.85),(.2,.85,.8),1800,False)):
        data = bpy.data.lights.new('BBE '+name,'AREA')
        data.energy = energy * (radius/10)**2 * stage_effects.preview_value(scene, 'brightness')
        data.color = color
        data.shape = 'DISK'
        data.size = radius*.65
        data.use_shadow = shadow
        obj = bpy.data.objects.new(data.name,data)
        coll.objects.link(obj)
        obj[TAG] = True
        obj.hide_select = True
        obj.location = Vector(xyz)*radius
        if name == 'Key':
            azimuth = math.radians(stage_effects.preview_value(scene, 'sun_azimuth'))
            elevation = math.radians(stage_effects.preview_value(scene, 'sun_elevation'))
            distance = Vector(xyz).length * radius
            obj.location = Vector((math.cos(azimuth)*math.cos(elevation),
                                   math.sin(azimuth)*math.cos(elevation), math.sin(elevation))) * distance
        obj.rotation_euler = (Vector((0,0,radius*.15))-obj.location).to_track_quat('-Z','Y').to_euler()
    stage_effects.build(scene, progress=progress)
    if progress:
        progress.update(.93, 'Finishing glow and viewport')
    stage_effects.compositor(scene)
    _signatures[scene.as_pointer()] = part_signature(scene)
    scene.render.engine = 'BLENDER_EEVEE' if bpy.app.version >= (5, 0, 0) else 'BLENDER_EEVEE_NEXT'
    # Blender 5 uses BLENDER_EEVEE; retain compatibility with earlier versions.


def apply(scene, commit=False, *, show_progress=True):
    s = scene.bbe_stage
    if not s.enabled or hd_library.scenes_root() is None:
        clear(scene)
        restore(scene)
        return
    from . import progress_ui
    with progress_ui.Activity('Loading scene preview', visible=show_progress) as progress:
        _apply_enabled(scene, commit, progress)


def _apply_enabled(scene, commit, progress):
    s = scene.bbe_stage
    progress.update(.02, 'Preparing preview settings')
    migrate(scene)
    if STATE not in scene:
        snapshot(scene)
    if commit or 'bbe_stage_applied' not in scene:
        scene['bbe_stage_applied'] = {p: getattr(s, p) for p in SLIDERS}
    else:
        # Older saved scenes have no committed sun coordinates yet.
        for p in SLIDERS:
            if p not in scene['bbe_stage_applied']:
                scene['bbe_stage_applied'][p] = getattr(s, p)
    build(scene, progress=progress)
    scene.eevee.use_raytracing = s.ray_tracing
    scene.eevee.use_fast_gi = False
    scene.eevee.use_shadow_jitter_viewport = False
    scene.eevee.taa_samples = 16 if s.quality == 'EDIT' else 64
    scene.eevee.taa_render_samples = 64
    scene.view_settings.view_transform = 'AgX'
    scene.view_settings.look = 'None'
    scene.view_settings.exposure = 0
    scene.view_settings.gamma = 1
    configure_views(scene)
    progress.update(1.0, 'Scene preview ready')


def update(self, context):
    apply(self.id_data)


class BBEStageSettings(bpy.types.PropertyGroup):
    enabled: BoolProperty(name='Scene Preview', default=False, update=update)
    environment: EnumProperty(name='Scene', items=[('STATION','Station Corvette Pad','Native station pad with build surface at Z=0'),('OUTPOST','Space Outpost Pad','Native orbital outpost pad against a static space backdrop'),('SPACE','Deep Space','Clean star backdrop without a floor')], default='STATION', update=update)
    quality: EnumProperty(name='Preview', items=[('EDIT','Smooth','16 samples, up to 32 ship lights, one shadow light'),('PHOTO','Photo','64 samples, up to 64 ship lights, one shadow light')], default='PHOTO', update=update)
    ray_tracing: BoolProperty(name='Ray Tracing', description='Enable EEVEE ray tracing independently of preview quality', default=True, update=update)
    ship_lights: BoolProperty(name='Object Lights', description='Emissive surfaces, local lights and supported animated effects for NMS parts', default=True, update=update)
    light_strength: FloatProperty(name='Light Spill', description='Applied with Refresh Scene Preview', default=2.0964910984039307, min=0, max=5)
    glow: BoolProperty(name='Glow', default=True, update=update)
    pad_radius: FloatProperty(name='Light Rig Size', description='Applied with Refresh Scene Preview', default=23.730003356933594,min=4,max=300,subtype='DISTANCE')
    brightness: FloatProperty(name='Lighting', description='Applied with Refresh Scene Preview', default=0.8065788745880127,min=.1,max=5)
    sun_azimuth: FloatProperty(name='Sun Direction', description='Degrees around the ship; apply with Refresh Scene Preview', default=-62.39282989501953,min=-180,max=180)
    sun_elevation: FloatProperty(name='Sun Height', description='Degrees above the horizon; apply with Refresh Scene Preview', default=37.43157958984375,min=-85,max=85)
    collection: PointerProperty(type=bpy.types.Collection)
    world: PointerProperty(type=bpy.types.World)
    previous_world: PointerProperty(type=bpy.types.World)
    compositor: PointerProperty(type=bpy.types.NodeTree)
    previous_compositor: PointerProperty(type=bpy.types.NodeTree)


class BBE_OT_stage_refresh(bpy.types.Operator):
    bl_idname = 'bbe.stage_refresh'
    bl_label = 'Refresh Scene Preview'
    bl_description = 'Apply lighting slider changes and refresh the preview'
    def execute(self,context):
        apply(context.scene, commit=True)
        return {'FINISHED'}


class BBE_PT_stage(bpy.types.Panel):
    bl_label = 'Lighting & Scenes'
    bl_idname = 'BBE_PT_stage'
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'No Mans Sky Base Builder'
    bl_options = {'DEFAULT_CLOSED'}
    def draw_header(self, context):
        icons.draw_panel_icon(self.layout, 'lighting')

    def draw(self, context):
        layout = self.layout
        s = context.scene.bbe_stage
        from .save_editor.function_help import corner_help
        header = layout.row(align=True)
        if hd_library.scenes_root() is None:
            header.label(text='Scenes and effects are included with HD proxies.')
            corner_help(header, 'LIGHTING')
            layout.operator('bbe.hd_library', text='Download & Enable HD', **icons.ui_icon('IMPORT'))
            return
        header.prop(s,'enabled',toggle=True,**icons.ui_icon('SHADING_RENDERED'))
        corner_help(header, 'LIGHTING')
        if not s.enabled:
            return
        layout.prop(s,'environment',text='')
        layout.row().prop(s,'quality',expand=True)
        layout.prop(s,'ray_tracing',toggle=True)
        layout.prop(s,'brightness',slider=True)
        layout.prop(s,'sun_azimuth',slider=True)
        layout.prop(s,'sun_elevation',slider=True)
        row = layout.row(align=True)
        row.prop(s,'ship_lights',toggle=True)
        row.prop(s,'glow',toggle=True)
        if s.ship_lights:
            layout.prop(s,'light_strength',slider=True)
        layout.prop(s,'pad_radius')
        if s.environment != 'SPACE':
            layout.label(text='Pad surface fixed at Z = 0')
        if any(abs(getattr(s, p) - stage_effects.preview_value(context.scene, p)) > 1e-5
               for p in SLIDERS):
            layout.label(text='Slider changes ready to apply', **icons.ui_icon('INFO'))
        layout.operator('bbe.stage_refresh',**icons.ui_icon('FILE_REFRESH'))


@persistent
def on_load(_):
    _signatures.clear()
    from .utils import roof_alignment
    for scene in bpy.data.scenes:
        roof_alignment.refresh_scene(scene)
        migrate(scene)
        # Preserve the previous quality-dependent setting in existing files.
        if not scene.bbe_stage.is_property_set('ray_tracing'):
            scene.bbe_stage['ray_tracing'] = scene.bbe_stage.quality == 'PHOTO'
        # Refresh corrected display meshes embedded in saved HD scenes.
        from . import builder_v2
        with bpy.context.temp_override(scene=scene):
            from . import preset
            preset.restore_legacy_appearance(scene)
            builder_v2.refresh_bytebeat_proxies(scene)
            builder_v2.refresh_forsaken_proxies(scene)
            builder_v2.refresh_toycore_proxies(scene)
            for obj in scene.objects:
                if (obj.type == 'MESH' and obj.get('ObjectID') == 'BUILDTERMINAL'
                        and obj.get('bbe_trade_terminal_wall_model')):
                    builder_v2.use_trade_terminal_wall_model(obj)
        if getattr(scene, 'bbe_detailed_proxies', True) and hd_library.scenes_root():
            with bpy.context.temp_override(scene=scene):
                revised = {'SET_CLASS_A', 'SET_CLASS_B', 'SET_CLASS_S',
                           *builder_v2.CABLE_CORRECTIONS}
                rim_variants = {'B_STR_T_NWTB', 'B_STR_T_NWTB1',
                                'B_STR_T_NWTB2', 'B_STR_T_NWTB3'}
                for obj in list(scene.objects):
                    pid = obj.get('ObjectID')
                    if (obj.type == 'MESH' and pid in {'SET_CLASS_A','SET_CLASS_B','SET_CLASS_S'}
                            and obj.data.get('bbe_marker_instance')):
                        old = obj.data
                        mesh = builder_v2.load_high_res_mesh(pid)
                        if mesh:
                            obj.data = mesh
                            if old.users == 0:
                                bpy.data.meshes.remove(old)
                    if obj.type == 'MESH' and obj.data.get(builder_v2.MESH_TAG):
                        builder_v2.correct_hd_display(obj.data, pid)
                    if (obj.type == 'MESH' and pid in revised | rim_variants
                            and (pid in revised or obj.data.get(builder_v2.MESH_TAG) == pid)):
                        if obj.data.get(builder_v2.MESH_REVISION_TAG) != builder_v2.MESH_REVISIONS[pid]:
                            old = obj.data
                            mesh = builder_v2.load_high_res_mesh(pid)
                            if mesh:
                                obj.data = mesh
                                if old.users == 0:
                                    bpy.data.meshes.remove(old)
        elif not getattr(scene, 'bbe_detailed_proxies', True):
            rim_variants = {'B_STR_T_NWTB', 'B_STR_T_NWTB1',
                            'B_STR_T_NWTB2', 'B_STR_T_NWTB3'}
            cache = {}
            with bpy.context.temp_override(scene=scene):
                for obj in list(scene.objects):
                    pid = obj.get('ObjectID')
                    if (obj.type != 'MESH' or pid not in rim_variants
                            or not obj.data.get(builder_v2.PROXY_PLACEMENT_TAG)):
                        continue
                    if obj.data.get(builder_v2.MESH_REVISION_TAG) == builder_v2.MESH_REVISIONS[pid]:
                        continue
                    old = obj.data
                    if builder_v2.apply_proxy_mesh(
                            obj, pid, obj.get('UserData'), cache=cache) and old.users == 0:
                        bpy.data.meshes.remove(old)
        if scene.bbe_stage.enabled:
            # Older previews have no compositor backup yet.
            saved = json.loads(scene.get(STATE, '{}'))
            if saved and 'use_compositing' not in saved:
                saved['use_compositing'] = scene.render.use_compositing
                if hasattr(scene, 'compositing_node_group'):
                    scene.bbe_stage.previous_compositor = scene.compositing_node_group
                scene[STATE] = json.dumps(saved)
            # load_post runs before Blender finishes initializing its tools.
            # A progress redraw here initializes the saved Move/Rotate/Scale
            # gizmo early; the remaining file-load cleanup clears its runtime
            # without requesting another initialization. Keep this load-time
            # rebuild silent. Interactive preview changes still show progress.
            apply(scene, show_progress=False)


def part_signature(scene):
    # Projected decals replace their display mesh after hull updates. That is
    # not a new lighting source and must not restart the effects rebuild.
    return tuple((o.as_pointer(), o.get('bbe_decal_source', o.data).as_pointer(), o.get('ObjectID'), o.hide_render, o.hide_get(), tuple(round(v, 5) for v in o.matrix_world.to_scale()),
                    tuple(round(v, 5) for row in o.matrix_world for v in row))
                 for o in scene.objects if o.type == 'MESH' and 'ObjectID' in o)


def refresh_parts():
    # Parent transforms move lamps immediately; only changed part membership,
    # visibility or proxy meshes need a rebuild. No per-frame mesh traversal.
    from . import undo_guard
    if not undo_guard.history_ready():
        return 1.0
    for scene in bpy.data.scenes:
        if scene.bbe_stage.enabled and hd_library.scenes_root():
            signature = part_signature(scene)
            if signature != _signatures.get(scene.as_pointer()):
                stage_effects.build(scene)
                _signatures[scene.as_pointer()] = signature
    return 1.0


CLASSES = (BBEStageSettings, BBE_OT_stage_refresh, BBE_PT_stage)


def register():
    for cls in CLASSES:
        bpy.utils.register_class(cls)
    bpy.types.Scene.bbe_stage = PointerProperty(type=BBEStageSettings)
    bpy.app.handlers.load_post.append(on_load)
    bpy.app.timers.register(deferred_migration, first_interval=.1)
    bpy.app.timers.register(refresh_parts, first_interval=1.0, persistent=True)


def deferred_migration():
    on_load(None)
    return None


def unregister():
    if bpy.app.timers.is_registered(refresh_parts):
        bpy.app.timers.unregister(refresh_parts)
    _signatures.clear()
    if bpy.app.timers.is_registered(deferred_migration):
        bpy.app.timers.unregister(deferred_migration)
    if on_load in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.remove(on_load)
    for scene in bpy.data.scenes:
        if scene.bbe_stage.enabled:
            scene.bbe_stage.enabled = False
    del bpy.types.Scene.bbe_stage
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)
