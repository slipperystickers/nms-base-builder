"""LOD0 smoothing, saved-cache migration and per-user discovery regression."""
from pathlib import Path
import importlib, json, math, os, sys, tempfile
import bpy
sys.path.insert(0,str(Path(__file__).parent))
from test_support import module, D, QA, report

builder = module('builder_v2')
assert module('tools.asset_browser_sidebar').BBE_OT_sidebar_asset_grid.new_border is module('tools.asset_browser_grid').BBE_OT_asset_grid.new_border
markers = module('utils.new_assets')
manifest = json.loads((D/'resources/forsaken_assets.json').read_text())['assets']
checked = []
for row in manifest:
    pid = row['id']
    mesh = builder.load_high_res_mesh(pid)
    assert mesh and mesh.has_custom_normals, pid
    assert all(p.use_smooth for p in mesh.polygons), pid
    for poly in list(mesh.polygons)[::max(1,len(mesh.polygons)//200)]:
        for i in poly.loop_indices:
            length = mesh.corner_normals[i].vector.length
            assert math.isfinite(length) and (1e-6 < length <= 1.002 or poly.area<1e-8), (pid,poly.index,poly.area,length)
    assert mesh.get('bbe_forsaken_revision') == 2, pid
    checked.append(pid)

# Mimic a project saved with the previous cached proxy. Only display data changes.
obj = builder.add_part('B_WNG_Y',user_data=0).object
obj.location = (3,4,5)
obj.rotation_euler.z = .7
obj.scale = (2,2,2)
obj['UserData'] = 42
bpy.context.view_layer.update()
before = obj.matrix_world.copy()
old = obj.data
old[builder.MESH_REVISION_TAG] = '18.2.33'
builder.refresh_forsaken_proxies(bpy.context.scene)
assert obj.data != old and obj.data.has_custom_normals
assert obj.matrix_world == before and obj['UserData'] == 42 and obj['ObjectID'] == 'B_WNG_Y'

with tempfile.TemporaryDirectory() as temporary:
    os.environ['NMS_BASE_BUILDER_DATA_DIR'] = temporary
    importlib.reload(markers)
    assert markers.is_new('B_WNG_Y') and not markers.is_new('B_COK_A')
    assert markers.mark_viewed('B_WNG_Y') and not markers.is_new('B_WNG_Y')
    assert markers.is_new('B_WNG_X')  # Clicking one tile must not clear the batch.
    importlib.reload(markers)
    assert not markers.is_new('B_WNG_Y') and markers.is_new('B_WNG_X')
    assert not markers.mark_viewed('B_COK_A')

report('forsaken_quality_34',dict(smoothNativeAssets=len(checked),cacheMigration=True,
                                transformsPreserved=True,newMarkersPersist=True))
