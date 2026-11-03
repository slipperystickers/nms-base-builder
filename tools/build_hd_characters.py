"""Package optional character meshes/textures separately from the main add-on.

Rebuild with --release-tag when preparing a public release. This tool only
creates local files; it never uploads or publishes a release.
"""
import argparse
import hashlib
import json
from pathlib import Path
import tomllib
import zipfile

ROOT = Path(__file__).resolve().parents[1]
ADDON = ROOT / 'src/addons/no_mans_sky_base_builder'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--release-tag')
    args = parser.parse_args()
    version = tomllib.loads((ADDON / 'blender_manifest.toml').read_text())['version']
    tag = args.release_tag or 'v' + version
    source = ADDON / 'resources/hd_additions'
    target = ROOT / 'dist/bbe-hd-characters-1.zip'
    target.parent.mkdir(exist_ok=True)
    files = {}
    # NPZ payloads are required by the native full-skin pilot solver.
    for folder in ('pilot_references', 'character_references'):
        for path in sorted((source / folder).rglob('*')):
            if path.is_file() and path.suffix in ('.blend', '.png', '.webp', '.npz'):
                with path.open('rb') as stream:
                    files[path.relative_to(source).as_posix()] = {
                        'bytes': path.stat().st_size,
                        'sha256': hashlib.file_digest(stream, 'sha256').hexdigest()}
    for race in ('ASTRO_DEFAULT', 'ASTRO_ARMOURED', 'GEK_DEFAULT', 'VYKEEN_DEFAULT',
                 'KORVAX_DEFAULT', 'FOURTH_DEFAULT', 'BUI_DEFAULT'):
        assert f'pilot_references/{race}.blend' in files
        assert f'pilot_references/{race}.skin.npz' in files
    assert sum(n.endswith('.blend') and n.startswith('character_references/') for n in files) == 14
    with zipfile.ZipFile(target, 'w', zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for name in files:
            archive.write(source / name, name)
    content = hashlib.sha256(json.dumps(files, sort_keys=True).encode()).hexdigest()
    with target.open('rb') as stream:
        digest = hashlib.file_digest(stream, 'sha256').hexdigest()
    spec = dict(id='hd-characters-1-' + content[:12], content_sha256=content, files=files,
                download_bytes=target.stat().st_size, archives={digest: {'prefix': ''}},
                url=f'https://github.com/slipperystickers/nms-base-builder/releases/download/{tag}/{target.name}')
    (ADDON / 'resources/hd_characters.json').write_text(json.dumps(spec, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(dict(path=str(target), files=len(files), bytes=target.stat().st_size, sha256=digest)))


if __name__ == '__main__':
    main()
