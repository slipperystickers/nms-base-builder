"""Package base and freighter placement sockets from build_corvette_snapping output.

Usage: python tools/build_base_snapping.py --native all-native-snapping.json
       --table BASEBUILDINGOBJECTSTABLE.MXML --output base_snapping.json
No game files are modified. Identical placement scenes share one socket list.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import xml.etree.ElementTree as ET


def build(native, table):
    parts, scenes, no_points = {}, {}, []
    for row in ET.fromstring(table).find("Property[@name='Objects']"):
        values = {p.get('name'): p.get('value') for p in row}
        pid = values.get('ID')
        base = values.get('BuildableOnPlanetBase') == 'true'
        freighter = values.get('BuildableOnFreighter') == 'true'
        if not (base or freighter) or pid not in native['parts']:
            continue
        scene = native['placement_scenes'][pid]
        points = []
        for point in native['parts'][pid]:
            # Electrical and teleport cables have their own endpoint system.
            sockets = [s for s in point['sockets']
                       if re.fullmatch(r'.+_(?:In|Out)(?:_.*)?', s)
                       and not s.startswith(('Pylon_', 'Teleport_', 'ByteBeatWire_',
                                             'PortalSocket_', 'Junction_'))]
            if sockets:
                points.append(dict(point, sockets=sockets))
        if not points:
            no_points.append(pid)
            continue
        scenes[scene] = points
        parts[pid] = dict(scene=scene, base=base, freighter=freighter)
    return dict(game_build=native['game_build'],
                source='Installed game placement scenes, with referenced and child transforms',
                table_sha256=hashlib.sha256(table).hexdigest(),
                scene_sha256=native['scene_sha256'],
                parts=dict(sorted(parts.items())), scenes=dict(sorted(scenes.items())),
                without_structural_sockets=sorted(no_points))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('native', 'table', 'output'):
        parser.add_argument('--'+name, required=True, type=Path)
    args = parser.parse_args()
    result = build(json.loads(args.native.read_text()), args.table.read_bytes())
    args.output.write_text(json.dumps(result, separators=(',', ':'))+'\n', encoding='utf-8')
    print(json.dumps(dict(parts=len(result['parts']), scenes=len(result['scenes']),
                         base=sum(p['base'] for p in result['parts'].values()),
                         freighter=sum(p['freighter'] for p in result['parts'].values()),
                         no_points=len(result['without_structural_sockets']))))
