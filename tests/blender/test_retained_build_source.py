"""Retain a large JSON build and an opaque ship attachment through .blend I/O."""
import io
import json
from pathlib import Path
import sys
import tempfile
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_support import QA, addon, bpy


objects = [{'ObjectID': '^W_FLOOR', 'Position': [x, 0, 0]} for x in range(4096)]
original = json.dumps({'Objects': objects}, indent=2).encode('utf-8')
package = io.BytesIO()
with zipfile.ZipFile(package, 'w', zipfile.ZIP_STORED) as archive:
    archive.writestr('objects.json', original)
    archive.writestr('so.json', '{}')
    archive.writestr('custom/attachment.bin', bytes(range(256)))

sources = {'.json': original, '.nmsship': package.getvalue()}
for suffix, data in sources.items():
    scene = bpy.data.scenes.new('Retained' + suffix)
    build = addon.interchange.BuildFile.from_bytes(data, suffix)
    addon._store_build_source(scene, build, suffix)

with tempfile.TemporaryDirectory(dir=QA) as directory:
    path = str(Path(directory) / 'retained.blend')
    bpy.ops.wm.save_as_mainfile(filepath=path)
    bpy.ops.wm.open_mainfile(filepath=path)
    for suffix, data in sources.items():
        restored = addon._restore_build_source(bpy.data.scenes['Retained' + suffix])
        assert restored.source_bytes == data, suffix
