"""Read-only native electrical connector audit and reproducible socket catalogue.

Extract with system Python; build with Blender Python (mathutils matrices).
"""
from pathlib import Path
import argparse, collections, hashlib, json, re, subprocess, sys
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor

WORK = Path(r'C:\Users\kengo\OneDrive\Desktop\NMS')
DEFAULT_OUT = WORK / 'outputs/electrical-sockets-20261105'
TABLE = 'metadata/reality/tables/basebuildingobjectstable.mbin'
norm = lambda p: p.replace('\\', '/').lower()

def value(node, key):
    p = node.find(f"Property[@name='{key}']")
    return p.get('value', '') if p is not None else ''

def extract(out):
    sys.path[:0] = [str(WORK/'fusion_nms_base_builder/.tools/hgpaktool'), str(WORK/'_tools/hgpak_py')]
    from hgpaktool import HGPAKFile
    steam = Path(r'C:\Program Files (x86)\Steam\steamapps')
    game = steam / "common/No Man's Sky/GAMEDATA/PCBANKS"
    build = re.search(r'"buildid"\s+"(\d+)"', (steam/'appmanifest_275850.acf').read_text()).group(1)
    index = {}
    for archive in sorted(game.glob('*.pak')):
        if 'audio' in archive.name.lower(): continue
        with HGPAKFile(archive) as pak:
            index.update({norm(n): (archive, n) for n in pak.filenames
                          if n.lower().endswith('.scene.mbin') or norm(n) == TABLE})
    out.mkdir(parents=True, exist_ok=True)
    dest = out/'native'
    hashes, missing = {}, set()
    compiler = WORK/'furby_mod_deck/resources/compiler/MBINCompiler.exe'
    def fetch(names):
        groups = collections.defaultdict(list)
        for name in names:
            if name not in index: missing.add(name); continue
            archive, native = index[name]
            groups[archive].append(native)
        refs = set()
        for archive, names in groups.items():
            with HGPAKFile(archive) as pak:
                for name, data in pak.extract(names):
                    name = norm(name); path = dest/name
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_bytes(data)
                    hashes[name] = hashlib.sha256(data).hexdigest()
                    refs.update(norm(r.decode('ascii')) for r in re.findall(rb'(?i)(MODELS[/\\][A-Z0-9_./\\-]+?\.SCENE\.MBIN)', data))
        return refs
    def convert(name):
        path = dest/name
        p = subprocess.run([str(compiler), 'convert', '-y', str(path)], capture_output=True)
        if p.returncode or not path.with_suffix('.MXML').exists():
            raise RuntimeError((name, p.stdout[-500:], p.stderr[-500:]))
    fetch({TABLE}); convert(TABLE)
    root = ET.parse((dest/TABLE).with_suffix('.MXML')).getroot()
    objects = {}
    for row in root.find("Property[@name='Objects']"):
        p = row.find("Property[@name='PlacementScene']/Property[@name='Filename']")
        if p is not None and p.get('value'):
            objects[value(row, 'ID')] = dict(placementScene=norm(p.get('value')))
    (out/'objects.json').write_text(json.dumps(objects, indent=2))
    pending = {r['placementScene'] for r in objects.values()}
    while pending:
        pending = fetch(pending) - hashes.keys() - missing
        print('EXTRACT', len(hashes), 'next', len(pending), flush=True)
    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(convert, sorted(set(hashes)-{TABLE})))
    (out/'audit.json').write_text(json.dumps(dict(game_build=build, hashes=hashes, missing=sorted(missing)), indent=2))
    print('EXTRACTED', len(objects), 'parts', len(hashes), 'files; missing', sorted(missing), flush=True)

def build(out):
    import math
    from functools import lru_cache
    from mathutils import Matrix, Euler, Vector
    repo = Path(__file__).resolve().parents[1]
    resources = repo/'src/addons/no_mans_sky_base_builder/resources'
    old = json.loads((resources/'snapping_info.json').read_text())
    objects = json.loads((out/'objects.json').read_text())
    audit = json.loads((out/'audit.json').read_text())
    visiting = set()
    def transform(node):
        t = {p.get('name'): float(p.get('value')) for p in node.find("Property[@name='Transform']")}
        return Matrix.Translation([t['Trans'+a] for a in 'XYZ']) @ Euler([math.radians(t['Rot'+a]) for a in 'XYZ']).to_matrix().to_4x4() @ Matrix.Diagonal([t['Scale'+a] for a in 'XYZ']+[1])
    @lru_cache(None)
    def collect(scene):
        if scene in visiting: raise ValueError('Scene cycle: '+scene)
        visiting.add(scene)
        root = ET.parse((out/'native'/scene).with_suffix('.MXML')).getroot()
        points = []
        def walk(node, parent, trail):
            world = parent @ transform(node)
            name = value(node, 'Name')
            trail = trail + '/' + name
            # Pylon_Out is the wire-compatible snap socket, unlike internal
            # LINKSOCKET locators used for room-to-room power propagation.
            if re.fullmatch(r'Pylon_Out\d*_', name):
                points.append(dict(position=list(world.translation), locator=trail, scene=scene))
            if value(node, 'Type') == 'REFERENCE':
                attrs = {value(a, 'Name'): value(a, 'Value') for a in node.find("Property[@name='Attributes']")}
                for point in collect(norm(attrs['SCENEGRAPH'])):
                    points.append(dict(point, position=list(world @ Vector(point['position'])), locator=trail+point['locator']))
            children = node.find("Property[@name='Children']")
            for child in children if children is not None else []: walk(child, world, trail)
        walk(root, Matrix.Identity(4), '')
        visiting.remove(scene)
        return points
    parts = {}
    for pid, row in sorted(objects.items()):
        points = collect(row['placementScene'])
        unique = {}
        for point in points: unique.setdefault(tuple(round(v,5) for v in point['position']),point)
        points = list(unique.values())
        previous = next((g for g in old.values() if pid in g.get('parts',())), {})
        previous = {k: Matrix(v['matrix']).translation for k,v in previous.get('snap_points',{}).items() if k.startswith('POWER')}
        # Retain names at matching positions so existing attached controls
        # keep their identifiers. New points get deterministic unused names.
        assigned = {}
        for distance, key, index in sorted(((Vector(p['position'])-pos).length,k,i) for k,pos in previous.items() for i,p in enumerate(points)):
            if distance < .05 and key not in assigned and index not in assigned.values(): assigned[key] = index
        for i in range(len(points)):
            if i not in assigned.values():
                n = 1
                while f'POWER_NATIVE_{n}' in assigned: n += 1
                assigned[f'POWER_NATIVE_{n}'] = i
        parts[pid] = {k: dict(points[i], position=[round(v,7) for v in points[i]['position']]) for k,i in assigned.items()}
    exclusions = {'U_POWERLINE': 'Cable endpoint, not a device socket',
                  'U_MINIPORTAL_CV': 'Inherits base teleporter placement scene but Corvette teleporter has no electrical socket; preserve typed SRT behavior'}
    for pid in exclusions: parts[pid] = {}
    result = dict(game_build=audit['game_build'], source='Native placement graphs: Pylon_Out wire sockets; internal LINKSOCKET locators excluded', exclusions=exclusions,
                  parts=parts, placement_scenes={k:v['placementScene'] for k,v in objects.items()}, scene_sha256=audit['hashes'])
    (resources/'electrical_sockets.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    summary = {pid:len(points) for pid,points in parts.items() if points}
    (out/'coverage.json').write_text(json.dumps(summary,indent=2))
    print('ELECTRICAL_COVERAGE',len(parts),'audited',len(summary),'wired parts',sum(summary.values()),'sockets',flush=True)
    print(json.dumps(summary),flush=True)

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, default=DEFAULT_OUT)
    parser.add_argument('--extract', action='store_true')
    args = parser.parse_args(sys.argv[sys.argv.index('--')+1:] if '--' in sys.argv else None)
    if args.extract: extract(args.out)
    else: build(args.out)
