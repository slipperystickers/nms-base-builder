"""Bake fixed example outfit palettes into the native gray diffuse maps.

The diffuse detail and native paint mask remain the source of every pixel.
This is a visual scale reference palette, not the user's saved appearance.
"""
import json
from pathlib import Path
from PIL import Image
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
TEXTURES = ROOT / 'src/addons/no_mans_sky_base_builder/resources/hd_additions/character_references/textures'
DIFFUSE_MASKS = json.loads((ROOT / 'tools/character_material_sources.json').read_text(encoding='utf-8'))
PALETTES = {
    'ASTRO_DEFAULT': ((.20, .50, .78), (.82, .86, .89)),
    'ASTRO_ARMOURED': ((.49, .27, .76), (.22, .19, .35)),
    'GEK_DEFAULT': ((.78, .42, .18), (.34, .55, .22)),
    'KORVAX_DEFAULT': ((.18, .61, .70), (.64, .43, .22)),
    'VYKEEN_DEFAULT': ((.70, .25, .16), (.35, .40, .46)),
    'FOURTH_DEFAULT': ((.46, .31, .71), (.66, .57, .40)),
    'BUI_DEFAULT': ((.24, .59, .56), (.56, .42, .27)),
}

paintable = []
for name, mask_name in DIFFUSE_MASKS.items():
    if not mask_name:
        continue
    image = np.asarray(Image.open(TEXTURES / name).convert('RGB').resize((64, 64)), dtype=np.int16)
    difference = np.abs(image[:, :, 0] - image[:, :, 1]).mean() + np.abs(image[:, :, 0] - image[:, :, 2]).mean()
    if difference < 8:
        paintable.append((name, mask_name))

for race, (primary, secondary) in PALETTES.items():
    for name, mask_name in paintable:
        source = Image.open(TEXTURES / name).convert('RGB')
        mask = Image.open(TEXTURES / mask_name).convert('RGB').resize(source.size, Image.Resampling.BILINEAR)
        values = np.asarray(source, dtype=np.float32)
        select = np.asarray(mask, dtype=np.float32)[:, :, 2:3] / 255
        colour = (1 - select) * np.array(secondary) + select * np.array(primary)
        result = np.uint8(np.clip(values * (.35 + 2.4 * colour), 0, 255))
        output = TEXTURES / f'{race}_{name}'
        Image.fromarray(result, 'RGB').save(output, quality=92, method=4)
    print('CHARACTER_PAINT_TEXTURES', race, len(paintable))

(ROOT / 'tools/character_paintable_diffuse.json').write_text(
    json.dumps(sorted(name for name, _ in paintable), indent=2) + '\n', encoding='utf-8')
