"""Build native snap data from decompiled, read-only game placement scenes.

Run with Blender --background --factory-startup --python-exit-code 1 --python
this_file -- --objects objects.json --scenes extracted_dir --build BUILD
--output corvette_snapping.json. objects.json maps IDs to placementScene paths.
The extraction must include every referenced SCENE.MBIN, converted to .MXML.
"""
import argparse
from functools import lru_cache
import hashlib
import json
import math
from pathlib import Path
import sys
import xml.etree.ElementTree as ET

from mathutils import Euler, Matrix


def value(node, key):
    prop = node.find(f"Property[@name='{key}']")
    return prop.get('value', '') if prop is not None else ''


def transform(node):
    values = {p.get('name'): float(p.get('value'))
              for p in node.find("Property[@name='Transform']")}
    return (Matrix.Translation([values['Trans'+a] for a in 'XYZ']) @
            Euler([math.radians(values['Rot'+a]) for a in 'XYZ']).to_matrix().to_4x4() @
            Matrix.Diagonal([values['Scale'+a] for a in 'XYZ']+[1]))


def build(objects, scenes, game_build):
    dependencies = {}
    visiting = set()

    @lru_cache(None)
    def collect(scene):
        scene = scene.replace('\\', '/').lower()
        if scene in visiting:
            raise ValueError('Recursive placement scene: ' + scene)
        visiting.add(scene)
        path = (scenes / scene).with_suffix('.MXML')
        data = path.read_bytes()
        dependencies[scene] = hashlib.sha256(data).hexdigest()
        root = ET.fromstring(data)
        points = []

        def walk(node, parent):
            world = parent @ transform(node)
            children = node.find("Property[@name='Children']")
            children = [] if children is None else children
            if value(node, 'Name').startswith('SnapPoint'):
                point = dict(name=value(node, 'Name'), matrix=world,
                             sockets=[value(c, 'Name') for c in children])
                # Some stairs rotate individual sockets; several connectors
                # also translate them. The parent locator alone is not enough.
                frames = {value(c, 'Name'): [list(r) for r in transform(c)] for c in children
                          if max(abs(v) for row in transform(c)-Matrix.Identity(4)
                                 for v in row) > 1e-6}
                if frames:
                    point['socket_matrices'] = frames
                points.append(point)
            if value(node, 'Type') == 'REFERENCE':
                attrs = {value(a, 'Name'): value(a, 'Value')
                         for a in node.find("Property[@name='Attributes']")}
                points.extend(dict(p, matrix=world @ p['matrix'])
                              for p in collect(attrs['SCENEGRAPH']))
            for child in children:
                walk(child, world)

        walk(root, Matrix.Identity(4))
        visiting.remove(scene)
        return points

    parts = {pid: [dict(p, matrix=[list(r) for r in p['matrix']])
                   for p in collect(row['placementScene'])]
             for pid, row in sorted(objects.items())}
    return dict(game_build=game_build,
                source='Native placement scenes and referenced snap scenes, including socket transforms',
                parts=parts, placement_scenes={k: v['placementScene'] for k, v in sorted(objects.items())},
                scene_sha256=dict(sorted(dependencies.items())))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--objects', type=Path, required=True)
    parser.add_argument('--scenes', type=Path, required=True)
    parser.add_argument('--build', type=int, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(sys.argv[sys.argv.index('--')+1:])
    result = build(json.loads(args.objects.read_text()), args.scenes, args.build)
    args.output.write_text(json.dumps(result, indent=2)+'\n', encoding='utf-8')
    print('NATIVE_SNAP_DATA', len(result['parts']), 'parts',
          sum(map(len, result['parts'].values())), 'points', len(result['scene_sha256']), 'scenes')
