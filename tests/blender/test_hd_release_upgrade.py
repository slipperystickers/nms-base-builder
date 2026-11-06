"""Exercise the distributed add-on against a real previous-release HD install.

NMS_KUMA_TEST_ADDON must point to an extracted release, BBE_ASSET_LIBRARY_ROOT
to an isolated library, and BBE_TEST_HD_ARCHIVE to the new additions ZIP.
"""
import os
import sys
import time
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import bpy

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_support import D, module, report

assert 'NMS_KUMA_TEST_ADDON' in os.environ
assert 'BBE_ASSET_LIBRARY_ROOT' in os.environ
assert not (D / 'models-high-res').exists()
assert not (D / 'resources/hd_additions').exists()
hd = module('hd_library')
ui = module('hd_library_ui')
builder = module('builder_v2')
old_root = hd.additions_root()
assert old_root and old_root.name != hd.additions_specification()['id']
assert hd.has_installed_content()
assert [s['id'] for s in hd.pending_specs()] == [hd.additions_specification()['id']]

# Use the exact staged release ZIP through the real network/install worker.
spec = dict(hd.additions_specification())
spec['url'] = Path(os.environ['BBE_TEST_HD_ARCHIVE']).resolve().as_uri()
bpy.context.scene.bbe_detailed_proxies = True
before = builder.add_part('B_GEN_5').object
transform = before.matrix_world.copy()
old_mesh = before.data
assert str(old_root) in old_mesh.get(builder.MESH_SOURCE_TAG, '')
gravity = builder.add_part('GRAV_WALL').object
assert gravity.data.get(builder.MESH_TAG) is None  # Repaired simple fallback.
with patch.object(hd, 'additions_specification', return_value=spec), \
        patch.object(ui, 'bpy', SimpleNamespace(app=SimpleNamespace(background=False, online_access=True))):
    assert ui.check_installed_updates()
    deadline = time.monotonic() + 180
    while hd.STATE['busy'] and time.monotonic() < deadline:
        time.sleep(.05)
    assert not hd.STATE['busy'], 'HD worker timed out'
    assert hd.STATE['result'] == 'installed', hd.STATE
    assert hd.ready(), hd.STATE
assert old_root.is_dir(), 'Previous pack was removed'
update = module('update_install')
with patch.object(update, 'wait_reason', return_value=''):
    ui.finish_download()
assert not hd.STATE['error'], hd.STATE
assert before.matrix_world == transform
assert before.data is not old_mesh, 'Existing detailed mesh was not refreshed'
assert spec['id'] in before.data.get(builder.MESH_SOURCE_TAG, '')
assert gravity.data.get(builder.MESH_TAG) == 'GRAV_WALL'
assert not hd.pending_specs()
report('hd_release_upgrade', dict(old=old_root.name, new=spec['id'],
       ready=hd.ready(), existing_mesh_refreshed=True,
       previous_pack_preserved=True, bundled_hd=False))
