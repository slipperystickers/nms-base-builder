"""Rebuild native character geometry, painted textures, icons, and HD ZIP.

Run with system Python (Pillow and NumPy) and Blender 5.1+ available. This is
the supported entrypoint; build_character_references.py alone writes gray
intermediate assets before this pipeline applies fixed example palettes.
"""
import argparse
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / 'tools'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--research-root', required=True, type=Path)
    parser.add_argument('--blender', type=Path, default=shutil.which('blender'))
    parser.add_argument('--release-tag')
    args = parser.parse_args()
    if not args.blender or not Path(args.blender).is_file():
        raise ValueError('Pass --blender with the Blender 5.1+ executable path')
    if not args.research_root.is_dir():
        raise ValueError('Research root is missing')
    subprocess.run([str(args.blender), '--background', '--factory-startup', '--python',
                    str(TOOLS / 'build_character_references.py'), '--',
                    '--research-root', str(args.research_root.resolve())], check=True)
    subprocess.run([sys.executable, str(TOOLS / 'build_character_colour_textures.py')], check=True)
    subprocess.run([str(args.blender), '--background', '--factory-startup', '--python',
                    str(TOOLS / 'recolour_character_references.py'), '--',
                    '--gray-list', str(TOOLS / 'character_paintable_diffuse.json')], check=True)
    command = [sys.executable, str(TOOLS / 'build_hd_characters.py')]
    if args.release_tag:
        command.extend(('--release-tag', args.release_tag))
    subprocess.run(command, check=True)


if __name__ == '__main__':
    main()
