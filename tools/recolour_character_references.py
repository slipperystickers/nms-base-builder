"""Attach baked native mask colour textures and render detailed character icons.

Run in background Blender. The mesh positions, UVs, normals and weights are
untouched. The native gray diffuse detail was coloured by
build_character_colour_textures.py; already-coloured diffuse maps stay native.
"""
import argparse
import json
from pathlib import Path
import sys

import bpy
from mathutils import Vector

ROOT = Path(__file__).resolve().parents[1]
ADDON = ROOT / 'src/addons/no_mans_sky_base_builder'
HD = ADDON / 'resources/hd_additions/character_references'
ICONS = ADDON / 'images/asset_icons'
PALETTES = {
    'ASTRO_DEFAULT': ((.20, .50, .78), (.82, .86, .89)),
    'ASTRO_ARMOURED': ((.49, .27, .76), (.22, .19, .35)),
    'GEK_DEFAULT': ((.78, .42, .18), (.34, .55, .22)),
    'KORVAX_DEFAULT': ((.18, .61, .70), (.64, .43, .22)),
    'VYKEEN_DEFAULT': ((.70, .25, .16), (.35, .40, .46)),
    'FOURTH_DEFAULT': ((.46, .31, .71), (.66, .57, .40)),
    'BUI_DEFAULT': ((.24, .59, .56), (.56, .42, .27)),
}


def tint_material(material, race, primary, gray_images):
    if not material or not material.use_nodes:
        return False
    nodes, links = material.node_tree.nodes, material.node_tree.links
    diffuse = nodes.get('gDiffuseMap')
    if diffuse is None or diffuse.image is None:
        return False
    original = diffuse.image.get('bbe_character_texture') or Path(diffuse.image.filepath).name
    if material.get('bbe_character_palette_revision') == 2 and original.startswith(race + '_'):
        return True
    if original not in gray_images:
        return False
    shader = nodes.get('Principled BSDF')
    if shader is None:
        return False
    painted = HD / 'textures' / f'{race}_{original}'
    if not painted.is_file():
        raise FileNotFoundError(painted)
    image = bpy.data.images.load(str(painted), check_existing=True)
    image['bbe_character_texture'] = painted.name
    image.colorspace_settings.name = 'sRGB'
    diffuse.image = image
    links.new(diffuse.outputs['Color'], shader.inputs['Base Color'])
    for name in ('BBE native paint mask palette', 'BBE textured outfit colour'):
        node = nodes.get(name)
        if node:
            nodes.remove(node)
    material.diffuse_color = (*primary, 1)
    material['bbe_character_palette_revision'] = 2
    return True


def icon(obj, target):
    scene = bpy.context.scene
    scene.render.engine = 'BLENDER_EEVEE'
    scene.render.resolution_x = scene.render.resolution_y = 256
    scene.render.resolution_percentage = 100
    scene.render.film_transparent = True
    scene.render.image_settings.file_format = 'PNG'
    scene.view_settings.view_transform = 'Standard'
    bounds = [Vector(vertex.co) for vertex in obj.data.vertices]
    low = Vector(tuple(min(point[i] for point in bounds) for i in range(3)))
    high = Vector(tuple(max(point[i] for point in bounds) for i in range(3)))
    centre, size = (low + high) / 2, high - low
    cam_data = bpy.data.cameras.new('Icon camera')
    cam = bpy.data.objects.new('Icon camera', cam_data)
    scene.collection.objects.link(cam)
    cam.location = centre + Vector((size.x * 1.8, size.y * 2.5, size.z * 1.1))
    cam.rotation_euler = (centre - cam.location).to_track_quat('-Z', 'Y').to_euler()
    cam_data.type = 'ORTHO'
    cam_data.ortho_scale = max(size.x, size.y, size.z) * 1.35
    scene.camera = cam
    for name, offset, power in (('Key', (2, -3, 4), 850), ('Fill', (-3, -1, 2), 450)):
        lamp_data = bpy.data.lights.new(name, 'AREA')
        lamp_data.energy, lamp_data.size = power, 4
        lamp = bpy.data.objects.new(name, lamp_data)
        scene.collection.objects.link(lamp)
        lamp.location = centre + Vector(offset)
        lamp.rotation_euler = (centre - lamp.location).to_track_quat('-Z', 'Y').to_euler()
    scene.render.filepath = str(target)
    bpy.ops.render.render(write_still=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--gray-list', type=Path, required=True)
    args = parser.parse_args(sys.argv[sys.argv.index('--') + 1:])
    gray_images = set(json.loads(args.gray_list.read_text(encoding='utf-8')))
    ICONS.mkdir(exist_ok=True)
    for race, (primary, secondary) in PALETTES.items():
        for pose in ('STANDING', 'SEATED'):
            bpy.ops.wm.read_factory_settings(use_empty=True)
            path = HD / f'{race}_{pose}.blend'
            with bpy.data.libraries.load(str(path), link=False) as (source, target):
                target.objects = list(source.objects)
            obj = next(obj for obj in target.objects if obj and obj.type == 'MESH')
            bpy.context.scene.collection.objects.link(obj)
            changed = sum(tint_material(mat, race, primary, gray_images)
                          for mat in obj.data.materials)
            if not changed:
                raise RuntimeError(f'No gray native material was coloured: {path.name}')
            bpy.data.libraries.write(str(path), {obj}, fake_user=True, compress=True)
            icon(obj, ICONS / f'BBE_CHARACTER_{pose}_{race}.png')
            print('COLOURED_CHARACTER', race, pose, changed, flush=True)


if __name__ == '__main__':
    main()
