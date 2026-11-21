"""Render local prefab thumbnails off the Blender UI thread, without opening a scene."""
import json
import math
import os
from pathlib import Path
import struct
import sys
import zipfile
import zlib

import numpy as np


def unit(v):
    return v / np.linalg.norm(v)


EYE = unit(np.array([1.4, 1.25, 2.0]))
RIGHT = unit(np.cross([0, 1, 0], EYE))
VIEW = np.column_stack((RIGHT, -np.cross(EYE, RIGHT), EYE))
LIGHT = unit(np.array([-1., 2., 3.])) @ VIEW
SIZE = 256


def mesh(archive, key, cache):
    if key not in cache:
        try:
            blob = archive.read(key)
        except KeyError:
            cache[key] = None
        else:
            low, span = np.frombuffer(blob, '<f4', 6).reshape(2, 3)
            count, = struct.unpack_from('<I', blob, 24)
            points = np.frombuffer(blob, 'u1', count*3, 28).reshape(-1, 3)
            faces = np.frombuffer(blob, '<u2', offset=28+count*3).reshape(-1, 3)
            cache[key] = (low+points*(span/255), faces)
    return cache[key]


def rasterize(triangles, depth, shade):
    # Fill horizontal spans in bulk and keep the nearest surface at each pixel.
    a, b, c = triangles.transpose(1, 0, 2)
    n = np.cross(b-a, c-a)
    valid = abs(n[:, 2]) > 1e-8
    if not valid.any():
        return
    triangles, a, n = triangles[valid], a[valid], n[valid]
    colors = (.38 + .62*np.maximum(0, (n @ LIGHT)*np.sign(n[:, 2])/np.linalg.norm(n,axis=1)))
    lo = triangles[:,:,1].min(axis=1)
    hi = triangles[:,:,1].max(axis=1)
    for y in range(max(0, math.ceil(lo.min()-.5)), min(SIZE, math.ceil(hi.max()-.5))):
        py = y + .5
        ids = np.flatnonzero((lo <= py) & (hi > py))
        if not len(ids):
            continue
        corners = triangles[ids]
        left = np.full(len(ids), np.inf)
        right = -left
        for k in range(3):
            p, q = corners[:, k], corners[:, (k+1)%3]
            cross = (p[:, 1] > py) != (q[:, 1] > py)
            t = np.divide(py-p[:, 1], q[:, 1]-p[:, 1], out=np.zeros(len(ids)), where=cross)
            x = p[:, 0]+t*(q[:, 0]-p[:, 0])
            left[cross] = np.minimum(left[cross], x[cross])
            right[cross] = np.maximum(right[cross], x[cross])
        starts = np.clip(np.ceil(left-.5), 0, SIZE).astype(int)
        ends = np.clip(np.ceil(right-.5), 0, SIZE).astype(int)
        lengths = np.maximum(0, ends-starts)
        rows = np.repeat(ids, lengths)
        if not len(rows):
            continue
        xs = np.arange(len(rows))+np.repeat(starts-(np.cumsum(lengths)-lengths), lengths)
        zs = a[rows,2] - ((xs+.5-a[rows,0])*n[rows,0]+(py-a[rows,1])*n[rows,1])/n[rows,2]
        np.maximum.at(depth[y], xs, zs)
        visible = zs >= depth[y, xs]
        shade[y, xs[visible]] = colors[rows[visible]]


def render(source, archive, cache):
    with open(source, encoding='utf-8-sig') as stream:
        data = json.load(stream)
    parts = data if isinstance(data, list) else data.get('Prefab', data.get('Objects', []))
    compensate = isinstance(data, dict) and data.get("BaseVersion", 4) >= 5
    instances = []
    low = np.full(3, np.inf)
    high = -low
    for part in parts:
        if not isinstance(part, dict):
            continue
        shell = mesh(archive, str(part.get('ObjectID','')).lstrip('^'), cache)
        if shell is None:
            continue
        try:
            position, up, at = np.asarray([part['Position'],part['Up'],part['At']], dtype=float)
            if position.shape != (3,) or not np.isfinite([position,up,at]).all():
                continue
            scale = np.linalg.norm(up)
            right = np.cross(up, at)
            if not scale or not np.linalg.norm(right):
                continue
        except (KeyError, TypeError, ValueError):
            continue
        points, faces = shell
        if part['ObjectID'].lstrip('^') in {'U_POWERLINE','U_PORTALLINE','U_BYTEBEATLINE','U_PIPELINE'}:
            length = np.linalg.norm(at) - int(compensate)
            axes = [unit(right)*np.sign(length), up, unit(at)*length]
        else:
            axes = [unit(right)*scale, up, unit(at)*scale]
        basis = np.array(axes) @ VIEW
        offset = position @ VIEW
        projected = points @ basis + offset
        low = np.minimum(low, projected.min(axis=0))
        high = np.maximum(high, projected.max(axis=0))
        instances.append((points, faces, basis, offset))
    if not instances:
        raise ValueError('No supported part geometry')
    zoom = SIZE*.9/max(1e-8, max((high-low)[:2]))
    center = (high+low)/2
    depth = np.full((SIZE,SIZE), -np.inf)
    shade = np.zeros_like(depth)
    for start in range(0, len(instances), 96):
        chunk = []
        for points, faces, basis, offset in instances[start:start+96]:
            p = (points @ basis + (offset-center))*zoom
            p[:,:2] += SIZE/2
            chunk.append(p[faces])
        rasterize(np.concatenate(chunk), depth, shade)
    mask = np.isfinite(depth)
    # Downsample with coverage to give edges a transparent antialiased fringe.
    def average(v):
        return v.reshape(SIZE//2,2,SIZE//2,2).mean(axis=(1,3))
    alpha = average(mask)
    light = np.divide(average(shade), alpha, out=np.zeros_like(alpha), where=alpha>0)
    rgba = np.dstack((light*154, light*212, light*228, alpha*255)).astype('u1')
    if not mask.any():
        raise ValueError('No visible surfaces')
    return rgba


def save_png(path, rgba):
    def chunk(kind, data):
        return struct.pack('>I',len(data))+kind+data+struct.pack('>I',zlib.crc32(kind+data))
    h,w,_ = rgba.shape
    scanlines = b''.join(b'\0'+row.tobytes() for row in rgba)
    png = (b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('>IIBBBBB',w,h,8,6,0,0,0))+
           chunk(b'IDAT',zlib.compress(scanlines,3))+chunk(b'IEND',b''))
    tmp = path.with_suffix(f'.{os.getpid()}.tmp')
    try:
        tmp.write_bytes(png)
        tmp.replace(path)
    finally:
        tmp.unlink(missing_ok=True)


if __name__ == '__main__':
    with zipfile.ZipFile(Path(__file__).parent/'resources/prefab_shells.bin') as archive:
        cache = {}
        for src, dest in zip(sys.argv[1::2], sys.argv[2::2]):
            try:
                save_png(Path(dest), render(src, archive, cache))
            except (OSError, ValueError, TypeError, AttributeError, OverflowError) as error:
                print(f'Prefab preview: {Path(src).name}: {error}', file=sys.stderr)

