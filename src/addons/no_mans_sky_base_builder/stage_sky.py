"""Preview palettes from the game's planet weather and solar system sky tables."""
import json
import math
from functools import lru_cache
from pathlib import Path

from mathutils import Vector

SKIES = [
    ('STUDIO', 'Stage Default', 'Use the original stage lighting'),
    ('DAY', 'Planet · Clear Day', 'Daylight palettes'),
    ('DUSK', 'Planet · Dusk', 'Dusk palette'),
    ('NIGHT', 'Planet · Night', 'Night palette'),
    ('NIGHT_DARK', 'Planet · Dark Night', 'Dark night palette'),
    ('FIRE', 'Planet · Firestorm', 'Firestorm palettes'),
    ('GRAVITY', 'Planet · Gravity Storm', 'Gravity storm palettes'),
    ('SYSTEM', 'Space · System', 'Space sky palettes'),
    ('RARE', 'Space · Rare', 'Rare space sky palettes'),
]


@lru_cache(maxsize=1)
def tables():
    return json.loads(Path(__file__).with_name('resources').joinpath('stage_skies.json').read_bytes())


BIOMES = [('DEFAULT', 'General', 'Use the general sky palette'),
          ('FROZEN', 'Frozen', ''), ('SWAMP', 'Swamp', ''), ('LAVA', 'Lava', ''),
          ('GASGIANT', 'Gas Giant', ''), ('LUSH', 'Lush', '')]


def palette_rows(settings):
    table = tables()
    return table.get(settings.sky + '_' + settings.sky_biome, table.get(settings.sky, ()))


def palette(settings):
    if settings.sky == 'STUDIO':
        default = {'FROST': 'DAY_FROZEN', 'MESA': 'DUSK'}.get(settings.environment)
        if default:
            return tables()[default][0]
    rows = palette_rows(settings)
    return rows[min(settings.sky_palette, len(rows)) - 1] if rows else None


def direction(settings):
    az, el = map(math.radians, (settings.sun_azimuth, settings.sun_elevation))
    return Vector((math.cos(az) * math.cos(el), math.sin(az) * math.cos(el), math.sin(el)))


def lighting(scene, radius):
    settings = scene.bbe_stage
    key = settings.sun_object
    if not key or not key.get('bbe_stage_owned') or key.name not in scene.objects:
        return
    vector = direction(settings)
    key.location = vector * radius * 1.27
    aim = -vector if key.data.type == 'SUN' else Vector((0, 0, radius * .15)) - key.location
    key.rotation_euler = aim.to_track_quat('-Z', 'Y').to_euler()
    if settings.world and settings.world.node_tree:
        dot = settings.world.node_tree.nodes.get('BBE Sun Direction')
        if dot:
            dot.inputs[1].default_value = vector


def backdrop(tree, settings, background, ambient):
    """Colour the world by elevation and draw the disk at the key light's direction."""
    nodes, link = tree.nodes, tree.links.new
    coord = nodes.new('ShaderNodeTexCoord').outputs['Generated']
    colours = palette(settings)
    socket = background.inputs['Color']
    original = socket.links[0].from_socket if socket.is_linked else None
    if colours:
        horizon, middle, zenith, sun = colours
        ambient.inputs['Color'].default_value = (*middle, 1)
        height = nodes.new('ShaderNodeSeparateXYZ')
        link(coord, height.inputs[0])
        ramp = nodes.new('ShaderNodeValToRGB')
        elements = ramp.color_ramp.elements
        elements[0].color = (*horizon, 1)
        elements[1].color = (*zenith, 1)
        elements.new(.4).color = (*middle, 1)
        link(height.outputs['Z'], ramp.inputs[0])
        sky = ramp.outputs[0]
        if settings.sky in {'SYSTEM', 'RARE'} and original:
            stars = nodes.new('ShaderNodeMixRGB')
            stars.blend_type = 'ADD'
            stars.inputs[0].default_value = .7
            link(sky, stars.inputs[1])
            link(original, stars.inputs[2])
            sky = stars.outputs[0]
    else:
        sky = original
        sun = (1, .94, .78)
    dot = nodes.new('ShaderNodeVectorMath')
    dot.name = 'BBE Sun Direction'
    dot.operation = 'DOT_PRODUCT'
    link(coord, dot.inputs[0])
    dot.inputs[1].default_value = direction(settings)
    disk = nodes.new('ShaderNodeMath')
    disk.operation = 'GREATER_THAN'
    link(dot.outputs['Value'], disk.inputs[0])
    disk.inputs[1].default_value = math.cos(math.radians(1.15))
    mix = nodes.new('ShaderNodeMixRGB')
    mix.inputs[1].default_value = socket.default_value
    if sky:
        link(sky, mix.inputs[1])
    mix.inputs[2].default_value = (*[max(.02, c) * 4 for c in sun], 1)
    link(disk.outputs[0], mix.inputs[0])
    link(mix.outputs[0], socket)
