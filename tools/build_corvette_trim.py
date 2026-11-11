"""Build the two HD material corrections from extracted native files (Python, Pillow, NumPy).

Pass the root containing models/ and textures/. Vertex stream offsets were read from
the matching TkGeometryData. The prepared generator drops nine vertices during
BBE's duplicate-face cleanup; their indices were checked by carrying a source ID
attribute through the same Blender cleanup as the HD pack.
"""
import argparse
import hashlib
import io
from pathlib import Path
import struct
import zlib

import numpy as np
from PIL import Image


def build(root, destination):
    destination.mkdir(parents=True, exist_ok=True)
    models = root / 'models/common/spacecraft/biggs/modules/parts'
    for pid, stem, digest, offset, count, removed in (
        ('B_TUR_F', 'gun_f', 'e1a59ea674d7f504db126a1cf71226d289f2a385cc0411f0db199c921ac572f3',
         126, 20728, ()),
        ('B_GEN_5', 'generators/generator_1x1_5', 'd8d94ed8401eb94dc354ffe94b52e26b577df89fa2f13dc0afa5a0220c19e176',
         127, 215001, (43191, 43192, 56503, 75578, 75580, 81485, 124818, 164748, 179931)),
    ):
        data = (models / (stem + '.geometry.data.mbin.pc')).read_bytes()
        if hashlib.sha256(data).hexdigest() != digest:
            raise ValueError(f'{pid} geometry changed. Recheck the vertex stream and prepared topology.')
        rgba = np.ndarray((count, 4), np.uint8, data, offset, (8, 1))
        if not np.all(rgba[:, :3] == rgba[:, :1]) or not np.all(rgba[:, 3] == 255):
            raise ValueError(f'{pid} no longer has opaque grayscale vertex shading')
        shade = np.delete(rgba[:, 0], list(removed)) if removed else rgba[:, 0]
        (destination / (pid + '.zlib')).write_bytes(zlib.compress(shade.tobytes(), 9))

    for name, mode in [('diffuse', 'RGBA'), ('normal', 'RGB'), ('masks', 'RGB'), ('colourisemask', 'L')]:
        filename = 'biggstrim' + ('' if name == 'diffuse' else '.' + name) + '.dds'
        dds = (root / 'textures/multitextures/biggs' / filename).read_bytes()
        header = bytearray(dds[:148])
        if header[84:88] != b'DX10' or struct.unpack_from('<I', header, 140)[0] != 4:
            raise ValueError(f'Expected a four-layer DDS array in {filename}')
        struct.pack_into('<I', header, 140, 1)
        layer_bytes, remainder = divmod(len(dds) - 148, 4)
        if remainder:
            raise ValueError(f'Invalid DDS payload in {filename}')
        tiles = []
        for layer in range(4):
            start = 148 + layer * layer_bytes
            with Image.open(io.BytesIO(header + dds[start:start+layer_bytes])) as image:
                w, h = image.size
                tiles.append(image.crop((0, h//8, w*7//16, h//4)).convert(mode))
        width, height = tiles[0].size
        atlas = Image.new(mode, (width, 4*height))
        for layer, tile in enumerate(tiles):
            atlas.paste(tile, (0, (3-layer)*height))
        atlas.save(destination / (name + '.png'), optimize=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('native_root', type=Path)
    parser.add_argument('destination', type=Path)
    args = parser.parse_args()
    build(args.native_root, args.destination)
