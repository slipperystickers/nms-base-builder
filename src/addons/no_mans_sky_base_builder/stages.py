"""BBE presentation stages, authored for BBE, October 2026 (GPL-3.0).

An original, bounded-cost scene rig. No Charon Forge implementation or sky
tables are used. Generated scenery is display-only and has no ObjectID.
"""
from . import i18n
from pathlib import Path
import json
import math
import bpy
from mathutils import Vector
from bpy.app.handlers import persistent
from bpy.props import BoolProperty, EnumProperty, FloatProperty, PointerProperty
from . import stage_effects, hd_library, icons, stage_sky, stage_navigation, progress_ui

TAG = 'bbe_stage_owned'
STATE = 'bbe_stage_restore'
SCENERY = 'bbe_stage_scenery'
SCENE_ART = Path(__file__).with_name('resources') / 'environments'
ENVIRONMENTS = [
    ('STATION', 'Station Pad Only', 'Native station pad with build surface at Z=0'),
    ('OUTPOST', 'Space Outpost Pad', 'Native orbital outpost pad against a static space backdrop'),
    ('SPACE', 'Deep Space', 'Clean star backdrop without a floor'),
    ('HANGAR', 'Station Hangar · Dock 5', 'Square-entrance station reference with cutaway walls around the Corvette berth'),
    ('ORBITAL', 'Deep-Space Outpost', 'Land beside an outpost hub under a nebula and stars'),
    ('FROST', 'Frozen Valley', 'A snowfield surrounded by icy ridges and frost plants'),
    ('MESA', 'Barren Mesas', 'A desert clearing surrounded by rock terraces and cacti'),
]
PAD_FOR = {'STATION': 'STATION', 'OUTPOST': 'OUTPOST', 'ORBITAL': 'OUTPOST'}
OUTPOST_LAYERS = ('Outpost Landing Field', 'Outpost Projections')
LANDSCAPES = {'HANGAR': ('Dock 5',), 'ORBITAL': ('Orbital Concourse', *OUTPOST_LAYERS),
              'OUTPOST': OUTPOST_LAYERS, 'FROST': ('FROST Landscape',), 'MESA': ('MESA Landscape',)}
STATION_LIGHTING = {'HANGAR', 'STATION'}
RIG_LIGHT = 'bbe_stage_environment_light'
_signatures = {}
_preview_before_save = []
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
    for p in ('taa_samples', 'taa_render_samples', 'use_raytracing', 'use_fast_gi', 'use_shadow_jitter_viewport',
              'ray_tracing_method', 'use_taa_reprojection', 'shadow_ray_count'):
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


def clear(scene, keep_scenery=False):
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
        if obj.get(SCENERY):
            if not keep_scenery:
                remove_scenery(obj)
        elif obj.get(TAG):
            data = obj.data
            kind = obj.type
            bpy.data.objects.remove(obj, do_unlink=True)
            if data and data.users == 0:
                if kind == 'MESH':
                    bpy.data.meshes.remove(data)
                elif kind == 'LIGHT':
                    bpy.data.lights.remove(data)
    cached_world = scene.bbe_stage.world
    if cached_world and not any(other != scene and other.world == cached_world for other in bpy.data.scenes):
        release_backdrop(cached_world)
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
    progress_ui.finish_shading(scene)
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
    name = 'BBE Native Pad / Outpost deck v4' if environment == 'OUTPOST' else 'BBE Native Pad 18.1.7 / ' + environment
    mesh = bpy.data.meshes.get(name)
    if mesh is None:
        source = hd_library.scenes_root() / 'display' / (environment + '.blend')
        with bpy.data.libraries.load(str(source), link=False) as (_, target):
            target.objects = [environment]
        obj = target.objects[0]
        mesh = obj.data
        bpy.data.objects.remove(obj)
        if environment == 'OUTPOST':
            # Both the glass and the under-pad glow have preview materials in
            # the orbital library. Remove their opaque duplicates from older HD packs.
            import bmesh
            obsolete = {i for i, mat in enumerate(mesh.materials) if mat and
                        mat.name.split(' / ')[-1].split('.')[0] in {'CONTACT', 'SCROLLINGCHEVRON1'}}
            bm = bmesh.new()
            try:
                bm.from_mesh(mesh)
                bmesh.ops.delete(bm, geom=[f for f in bm.faces if f.material_index in obsolete], context='FACES')
                bm.to_mesh(mesh)
            finally:
                bm.free()
        mesh.name = name
        mesh.use_fake_user = True
    obj = bpy.data.objects.new(name, mesh)
    obj[TAG] = obj[SCENERY] = True
    obj.hide_select = True
    coll.objects.link(obj)
    return obj


def remove_scenery(obj):
    mesh = obj.data
    bpy.data.objects.remove(obj, do_unlink=True)
    if mesh.users:
        return
    materials = {mat for mat in mesh.materials if mat}
    bpy.data.meshes.remove(mesh)
    for mat in materials:
        if mat.users:
            continue
        images = {node.image for node in mat.node_tree.nodes
                  if node.type == 'TEX_IMAGE' and node.image} if mat.node_tree else set()
        bpy.data.materials.remove(mat)
        for image in images:
            if not image.users:
                bpy.data.images.remove(image)


def scenery(collection, environment):
    if environment in PAD_FOR:
        obj = pad(collection, PAD_FOR[environment])
        obj['bbe_stage_location'] = environment
    if environment in LANDSCAPES:
        library = 'ORBITAL' if environment == 'OUTPOST' else environment
        with bpy.data.libraries.load(str(SCENE_ART / (library + '.blend'))) as (_, target):
            target.meshes = list(LANDSCAPES[environment])
        for mesh in target.meshes:
            if environment == 'HANGAR':
                stage_navigation.configure(mesh)
            obj = bpy.data.objects.new(mesh.name, mesh)
            obj['bbe_stage_location'] = environment
            obj[TAG] = obj[SCENERY] = True
            obj.hide_select = True
            collection.objects.link(obj)


def release_backdrop(world):
    if not world or not world.node_tree:
        return
    node = world.node_tree.nodes.get('BBE Environment Panorama')
    if node and node.image:
        image = node.image
        node.image = None
        if not image.users:
            bpy.data.images.remove(image)


def world(scene):
    s = scene.bbe_stage
    w = s.world
    if not w or any(other != scene and other.bbe_stage.world == w for other in bpy.data.scenes):
        w = bpy.data.worlds.new('BBE Stage World')
        s.world = w
    # Dock 5's reflections sample a uniform world colour. Its architectural
    # detail lives on the mesh and does not need a high-resolution world probe.
    w.probe_resolution = '128' if s.environment == 'HANGAR' else w.bl_rna.properties['probe_resolution'].default
    w.use_nodes = True
    nt = w.node_tree
    release_backdrop(w)
    nt.nodes.clear()
    def node(kind): return nt.nodes.new(kind)
    output = node('ShaderNodeOutputWorld')
    ambient = node('ShaderNodeBackground')
    ambient.inputs['Color'].default_value = (.16,.20,.27,1)
    ambient.inputs['Strength'].default_value = .35
    background = node('ShaderNodeBackground')
    background.inputs['Strength'].default_value = .7
    background.inputs['Color'].default_value = (.008,.016,.03,1)
    image_path = None
    if s.environment == 'ORBITAL':
        image_path = SCENE_ART / 'orbital.jpg'
        background.inputs['Strength'].default_value = 1.1
    elif s.environment in {'SPACE', 'OUTPOST'} or (s.environment != 'HANGAR' and s.sky in {'SYSTEM', 'RARE'}):
        image_path = hd_library.scenes_root() / 'display' / 'space.png'
    if image_path:
        backdrop = node('ShaderNodeTexEnvironment')
        backdrop.image = bpy.data.images.load(str(image_path), check_existing=True)
        if image_path.parent == SCENE_ART:
            backdrop.name = 'BBE Environment Panorama'
            if not backdrop.image.packed_file:
                backdrop.image.pack()
        nt.links.new(backdrop.outputs['Color'], background.inputs['Color'])
    if s.environment in STATION_LIGHTING:
        ambient.inputs['Color'].default_value = (.65, .73, .83, 1)
        ambient.inputs['Strength'].default_value = stage_effects.preview_value(scene, 'brightness') * .8
    else:
        stage_sky.backdrop(nt, s, background, ambient)
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
    coll = s.collection
    expected = int(s.environment in PAD_FOR) + len(LANDSCAPES.get(s.environment, ()))
    present = [o for o in coll.objects if o.get(SCENERY)] if coll else []
    reuse = (len(present) == expected and
             all(o.get('bbe_stage_location') == s.environment and
                 (s.environment != 'HANGAR' or o.data.get('bbe_dock_revision', 0) >= 5)
                 for o in present))
    clear(scene, keep_scenery=reuse)
    reuse = reuse and s.collection == coll
    coll = s.collection
    if not coll:
        coll = bpy.data.collections.new('BBE Display Stage')
        scene.collection.children.link(coll)
        s.collection = coll
    world(scene)
    if not reuse:
        scenery(coll, s.environment)
    if progress:
        progress.update(.14, 'Setting up lighting')
    environment_lights(scene)
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
        progress_ui.finish_shading(scene)
        clear(scene)
        restore(scene)
        return
    with progress_ui.Activity('Loading scene preview', visible=show_progress, deferred_redraw=True) as progress:
        progress.present()
        _apply_enabled(scene, commit, progress)
        progress.wait_for_shading(scene)


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
    # Avoid smearing previous poses into the moving view. Smooth uses probes
    # instead of noisy screen-space reflections; Photo retains screen tracing.
    scene.eevee.use_taa_reprojection = False
    scene.eevee.shadow_ray_count = 2
    scene.eevee.ray_tracing_method = 'PROBE' if s.quality == 'EDIT' else 'SCREEN'
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



def update(self, context):
    from . import settings_memory
    if not settings_memory._applying:
        apply(self.id_data)


def display_update(self, context):
    """Glow and ray tracing change the viewport without rebuilding ship materials."""
    from . import settings_memory
    if settings_memory._applying or not self.enabled:
        return
    scene = self.id_data
    if self.collection and self.world and scene.world == self.world:
        scene.eevee.use_raytracing = self.ray_tracing
        stage_effects.compositor(scene)
        configure_views(scene)


def change_environment(self, context):
    from . import settings_memory
    if settings_memory._applying or not self.enabled:
        return
    scene = self.id_data
    coll = self.collection
    if (not coll or scene.world != self.world
            or any(other != scene and other.bbe_stage.collection == coll for other in bpy.data.scenes)):
        apply(scene)
        return
    # Ship lights and material effects are independent of the selected location.
    for obj in list(coll.objects):
        if obj.get(SCENERY) or (obj.get(TAG) and obj.type == 'MESH'
                                and obj.data.name.startswith('BBE Native Pad ')):
            remove_scenery(obj)
    scenery(coll, self.environment)
    world(scene)
    environment_lights(scene)
    for _, area, _ in views(scene):
        area.tag_redraw()


def environment_lights(scene):
    settings = scene.bbe_stage
    collection = settings.collection
    for obj in list(collection.objects):
        if obj.get(RIG_LIGHT):
            light = obj.data
            bpy.data.objects.remove(obj, do_unlink=True)
            if not light.users:
                bpy.data.lights.remove(light)
    settings.sun_object = None

    def lamp(name, kind):
        data = bpy.data.lights.new(name, kind)
        obj = bpy.data.objects.new(name, data)
        obj[TAG] = obj[RIG_LIGHT] = True
        obj.hide_select = True
        collection.objects.link(obj)
        return obj

    brightness = stage_effects.preview_value(scene, 'brightness')
    positions = ()
    outpost = PAD_FOR.get(settings.environment) == 'OUTPOST'
    if outpost:
        field = next(o.data for o in collection.objects if o.get(SCENERY) and 'uplight_positions' in o.data)
        xyz = iter(field['uplight_positions'])
        positions = zip(xyz, xyz, xyz)
    elif settings.environment in STATION_LIGHTING:
        positions = ((x, y, .55) for x in (-9, 9) for y in (-12, 12))
    for position in positions:
        obj = lamp('BBE Pad Uplight', 'AREA')
        obj.location = position
        obj.rotation_euler = (Vector((0, 0, 4)) - obj.location).to_track_quat('-Z', 'Y').to_euler()
        obj.data.shape = 'DISK'
        obj.data.size = 4
        obj.data.energy = (4400 if outpost else 1850) * brightness
        obj.data.color = (.86, .94, 1)
        obj.data.specular_factor = .22
        obj.data.use_shadow = False
    if settings.environment in STATION_LIGHTING:
        canopy = lamp('BBE Station Ceiling', 'AREA')
        canopy.location = (0, 0, 38)
        canopy.data.size = 4
        canopy.data.shadow_filter_radius = .5
        canopy.data.energy = 27000 * brightness
        canopy.data.specular_factor = .35
        return
    settings.sun_object = lamp('BBE Sun', 'SUN')
    configure_sun(scene)


def configure_sun(scene):
    settings = scene.bbe_stage
    if not settings.sun_object:
        return
    lamp = settings.sun_object.data
    colours = stage_sky.palette(settings)
    lamp.color = colours[-1] if colours else (1, .94, .78)
    lamp.energy = 3 * stage_effects.preview_value(scene, 'brightness')
    lamp.angle = math.radians(2.3)
    stage_sky.lighting(scene, stage_effects.preview_value(scene, 'pad_radius'))


def sun_update(self, context):
    scene = self.id_data
    if not self.enabled:
        return
    applied = scene.get('bbe_stage_applied')
    if applied is not None:
        for name in ('sun_azimuth', 'sun_elevation'):
            applied[name] = getattr(self, name)
    stage_sky.lighting(scene, stage_effects.preview_value(scene, 'pad_radius'))


def sky_update(self, context):
    from . import settings_memory
    if settings_memory._applying:
        return
    rows = stage_sky.palette_rows(self)
    if rows and self.sky_palette > len(rows):
        self.sky_palette = len(rows)
        return
    scene = self.id_data
    if self.enabled and self.sun_object and scene.world == self.world:
        world(scene)
        configure_sun(scene)


class BBEStageSettings(bpy.types.PropertyGroup):
    enabled: BoolProperty(name='Scene Preview', default=False, options={'SKIP_SAVE'}, update=update)
    environment: EnumProperty(translation_context="BBEExtendedInterface", name='Scene', items=ENVIRONMENTS, default='HANGAR', update=change_environment)
    sky: EnumProperty(name='NMS Sky', items=stage_sky.SKIES, default='STUDIO', update=sky_update)
    sky_biome: EnumProperty(name='Biome', description='Uses the general palette when the game has no override for this biome', items=stage_sky.BIOMES, default='DEFAULT', update=sky_update)
    sky_palette: bpy.props.IntProperty(name='Sky Palette', min=1, max=48, default=1, update=sky_update)
    sun_object: PointerProperty(type=bpy.types.Object)
    quality: EnumProperty(translation_context="BBEExtendedInterface", name='Preview', items=[('EDIT','Smooth','16 samples, probe reflections, up to 32 ship lights'),('PHOTO','Photo','64 samples, screen-space reflections, up to 64 ship lights')], default='PHOTO', update=update)
    ray_tracing: BoolProperty(name='Ray Tracing', description='Enable EEVEE ray tracing independently of preview quality', default=True, update=display_update)
    ship_lights: BoolProperty(name='Object Lights', description='Emissive surfaces, local lights and supported animated effects for NMS parts', default=True, update=update)
    light_strength: FloatProperty(name='Light Spill', description='Applied with Refresh Scene Preview', default=2.0964910984039307, min=0, max=5)
    glow: BoolProperty(name='Glow', default=True, update=display_update)
    pad_radius: FloatProperty(name='Light Rig Size', description='Applied with Refresh Scene Preview', default=23.730003356933594,min=4,max=300,subtype='DISTANCE')
    brightness: FloatProperty(name='Lighting', description='Applied with Refresh Scene Preview', default=0.8065788745880127,min=.1,max=5)
    sun_azimuth: FloatProperty(name='Sun Direction', description='Move the sun around the build in real time', default=-62.39282989501953,min=-180,max=180,update=sun_update)
    sun_elevation: FloatProperty(name='Sun Height', description='Move the sun above or below the horizon in real time', default=37.43157958984375,min=-90,max=90,update=sun_update)
    collection: PointerProperty(type=bpy.types.Collection)
    world: PointerProperty(type=bpy.types.World)
    previous_world: PointerProperty(type=bpy.types.World)
    compositor: PointerProperty(type=bpy.types.NodeTree)
    previous_compositor: PointerProperty(type=bpy.types.NodeTree)


class BBE_OT_aim_stage_sun(bpy.types.Operator):
    bl_idname = 'bbe.aim_stage_sun'
    bl_label = 'Point Sun in Viewport'
    bl_description = 'Aim the sun with the mouse, click to keep it, or press Esc to restore it'
    bl_options = {'UNDO', 'BLOCKING'}

    def invoke(self, context, event):
        if not context.scene.bbe_stage.sun_object or not context.scene.bbe_stage.enabled or not context.area or context.area.type != 'VIEW_3D':
            return {'CANCELLED'}
        settings = context.scene.bbe_stage
        self.original = (settings.sun_azimuth, settings.sun_elevation)
        self.area = context.area
        self.area.header_text_set('Aim at the sky · Click to place sun · Esc to cancel')
        context.window.cursor_modal_set('CROSSHAIR')
        context.window_manager.modal_handler_add(self)
        return {'RUNNING_MODAL'}

    def cancel(self, context):
        settings = context.scene.bbe_stage
        settings.sun_azimuth, settings.sun_elevation = self.original
        self.area.header_text_set(None)
        context.window.cursor_modal_restore()

    def modal(self, context, event):
        from bpy_extras.view3d_utils import region_2d_to_vector_3d
        if event.type in {'ESC', 'RIGHTMOUSE', 'WINDOW_DEACTIVATE'} or not context.scene.bbe_stage.enabled:
            self.cancel(context)
            return {'CANCELLED'}
        region = next((r for r in self.area.regions if r.type == 'WINDOW' and
                       r.x <= event.mouse_x < r.x+r.width and r.y <= event.mouse_y < r.y+r.height), None)
        if region and (event.type == 'MOUSEMOVE' or (event.type == 'LEFTMOUSE' and event.value == 'PRESS')):
            rv = self.area.spaces.active.region_3d
            x, y = event.mouse_x-region.x, event.mouse_y-region.y
            direction = region_2d_to_vector_3d(region, rv, (x, y))
            if not rv.is_perspective:
                # In an orthographic view all camera rays are parallel. Use a virtual sky dome.
                scale = max(1, min(region.width, region.height) / 2)
                u, v = (x-region.width/2)/scale, (y-region.height/2)/scale
                direction = rv.view_rotation @ Vector((u, v, -math.sqrt(max(0, 1-u*u-v*v)))).normalized()
            settings = context.scene.bbe_stage
            settings.sun_azimuth = math.degrees(math.atan2(direction.y, direction.x))
            settings.sun_elevation = math.degrees(math.asin(max(-1, min(1, direction.z))))
            if event.type == 'LEFTMOUSE':
                self.area.header_text_set(None)
                context.window.cursor_modal_restore()
                return {'FINISHED'}
        return {'RUNNING_MODAL'}


class BBE_OT_stage_graphics_backend(bpy.types.Operator):
    bl_idname = 'bbe.stage_graphics_backend'
    bl_label = 'Viewport Graphics Backend'
    bl_description = 'Choose the graphics backend for the next Blender launch'

    def invoke(self, context, event):
        return context.window_manager.invoke_popup(self, width=330)

    def draw(self, context):
        import gpu
        layout = self.layout
        layout.label(text=f"Running now: {gpu.platform.backend_type_get()}")
        layout.prop(context.preferences.system, 'gpu_backend', text='Next launch')
        layout.label(text='Restart Blender to use your selection.')
        if not context.preferences.use_preferences_save:
            layout.label(text='Save Preferences to keep this change.')

    def execute(self, context):
        return {'FINISHED'}


class BBE_OT_stage_refresh(bpy.types.Operator):
    bl_idname = 'bbe.stage_refresh'
    bl_translation_context = "BBEExtendedInterface"
    bl_label = 'Refresh Scene Preview'
    bl_description = 'Apply lighting slider changes and refresh the preview'
    def execute(self,context):
        apply(context.scene, commit=True)
        return {'FINISHED'}


class BBE_PT_stage(bpy.types.Panel):
    bl_translation_context = "BBEExtendedInterface"
    bl_label = 'Lighting & Scenes'
    bl_idname = 'BBE_PT_stage'
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'No Mans Sky Base Builder'
    bl_options = {'DEFAULT_CLOSED'}
    def draw_header(self, context):
        from . import sidebar_builder
        sidebar_builder.begin_header(self, context, 'lighting')
        icons.draw_panel_icon(i18n.localized_layout(self.layout), 'lighting')

    def draw(self, context):
        from . import sidebar_builder
        if sidebar_builder.draw_inline(self, context, 'lighting'):
            return
        layout = i18n.localized_layout(self.layout)
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
        if hasattr(context.preferences.system, 'gpu_backend'):
            layout.operator('bbe.stage_graphics_backend', text='Viewport Graphics Backend', icon='PREFERENCES')
        if not s.enabled:
            return
        layout.prop(s,'environment',text='')
        if s.environment not in STATION_LIGHTING:
            layout.prop(s, 'sky')
            if s.sky in {'DAY', 'DUSK', 'NIGHT', 'FIRE', 'GRAVITY'}:
                layout.prop(s, 'sky_biome')
            if len(stage_sky.palette_rows(s)) > 1:
                layout.prop(s, 'sky_palette')
        layout.row().prop(s,'quality',expand=True)
        layout.prop(s,'ray_tracing',toggle=True)
        layout.prop(s,'brightness',slider=True)
        if s.environment not in STATION_LIGHTING:
            layout.prop(s,'sun_azimuth',slider=True)
            layout.prop(s,'sun_elevation',slider=True)
            layout.operator('bbe.aim_stage_sun', text='Point Sun in Viewport', icon='LIGHT_SUN')
        row = layout.row(align=True)
        row.prop(s,'ship_lights',toggle=True)
        row.prop(s,'glow',toggle=True)
        if s.ship_lights:
            layout.prop(s,'light_strength',slider=True)
        if s.environment in PAD_FOR or s.environment == 'HANGAR':
            layout.label(text='Pad surface fixed at Z = 0')
        elif s.environment in {'FROST', 'MESA'}:
            layout.label(text='Landing clearing at Z = 0')
        if any(abs(getattr(s, p) - stage_effects.preview_value(context.scene, p)) > 1e-5
               for p in SLIDERS):
            layout.label(text='Slider changes ready to apply', **icons.ui_icon('INFO'))
        layout.operator('bbe.stage_refresh',**icons.ui_icon('FILE_REFRESH'))


@persistent
def suspend_for_save(_):
    # Save the actual build in its original world and shading. This also makes
    # the file inexpensive to open on a machine without the extension enabled.
    _preview_before_save.clear()
    for scene in bpy.data.scenes:
        if scene.bbe_stage.enabled:
            _preview_before_save.append(scene)
            scene.bbe_stage['enabled'] = False
            apply(scene, show_progress=False)


@persistent
def resume_after_save(_):
    pending = _preview_before_save[:]
    _preview_before_save.clear()
    for scene in pending:
        scene.bbe_stage['enabled'] = True
        apply(scene, show_progress=False)


@persistent
def on_load(_):
    _signatures.clear()
    _preview_before_save.clear()
    migrate_loaded_scenes()


def migrate_loaded_scenes():
    from .utils import roof_alignment
    for scene in bpy.data.scenes:
        # Older projects and recovery files can contain the fully active preview.
        # Stop it before any migrations touch materials or Blender draws a window.
        if scene.as_pointer() not in _signatures and (scene.bbe_stage.enabled or STATE in scene):
            prepare_import(scene)
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
        if scene.bbe_stage.enabled and scene.bbe_stage.ship_lights and scene.bbe_stage.collection:
            signature = part_signature(scene)
            if signature != _signatures.get(scene.as_pointer()) and hd_library.scenes_root():
                stage_effects.build(scene)
                _signatures[scene.as_pointer()] = signature
    return 1.0


CLASSES = (BBEStageSettings, BBE_OT_stage_graphics_backend, BBE_OT_stage_refresh, BBE_OT_aim_stage_sun, BBE_PT_stage)


def register():
    from .tools_menu import base_builder_menu
    base_builder_menu.bind_sidebar_visibility(CLASSES)
    for cls in CLASSES:
        bpy.utils.register_class(cls)
    bpy.types.Scene.bbe_stage = PointerProperty(type=BBEStageSettings)
    bpy.app.handlers.load_pre.append(progress_ui.before_load)
    bpy.app.handlers.load_post.append(on_load)
    bpy.app.handlers.save_pre.append(suspend_for_save)
    bpy.app.handlers.save_post.append(resume_after_save)
    bpy.app.handlers.save_post_fail.append(resume_after_save)
    bpy.app.timers.register(deferred_migration, first_interval=.1)
    bpy.app.timers.register(refresh_parts, first_interval=1.0, persistent=True)


def deferred_migration():
    migrate_loaded_scenes()
    return None


def unregister():
    progress_ui.finish_shading()
    _preview_before_save.clear()
    for handlers, callback in ((bpy.app.handlers.save_pre, suspend_for_save),
                               (bpy.app.handlers.save_post, resume_after_save),
                               (bpy.app.handlers.save_post_fail, resume_after_save)):
        if callback in handlers:
            handlers.remove(callback)
    if bpy.app.timers.is_registered(refresh_parts):
        bpy.app.timers.unregister(refresh_parts)
    _signatures.clear()
    if bpy.app.timers.is_registered(deferred_migration):
        bpy.app.timers.unregister(deferred_migration)
    if progress_ui.before_load in bpy.app.handlers.load_pre:
        bpy.app.handlers.load_pre.remove(progress_ui.before_load)
    if on_load in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.remove(on_load)
    for scene in bpy.data.scenes:
        if scene.bbe_stage.enabled:
            scene.bbe_stage.enabled = False
    del bpy.types.Scene.bbe_stage
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)
