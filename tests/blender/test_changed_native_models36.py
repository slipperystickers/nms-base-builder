"""Correct current native geometry, complete variants, safe migration and export IDs."""
from pathlib import Path
import json, math, sys
import bpy
sys.path.insert(0,str(Path(__file__).parent))
from test_support import addon,module,D,report

builder=module('builder_v2')
materials=module('utils.materials_v2')
manifest=json.loads((D/'resources/native_asset_corrections.json').read_text())
assert len(manifest['assets'])==27
expected={r['id']:r for r in manifest['assets']}
assert set(expected)==builder.CORRECTED_LEGACY_PARTS
bpy.data.batch_remove(list(bpy.context.scene.objects))
checks=[]
for identity,row in expected.items():
    obj=builder.add_part(identity,user_data=0).object
    mesh=obj.data
    assert obj['ObjectID']==identity and mesh.has_custom_normals,identity
    assert len(mesh.polygons)==row['triangles'],(identity,len(mesh.polygons),row['triangles'])
    assert mesh.get(builder.MESH_REVISION_TAG)=='18.2.36'
    assert all(p.use_smooth for p in mesh.polygons)
    assert mesh.uv_layers and mesh.materials
    assert materials.is_high_res(obj)
    images=builder._mesh_texture_images(mesh)
    assert all(i.packed_file or Path(bpy.path.abspath(i.filepath)).is_file() for i in images),identity
    simple=module('simple_library').load_mesh(identity)
    assert len(simple.polygons)==row['proxyTriangles'] and len(simple.polygons)<=4000,identity
    if identity in ('B_GEN_4','B_GEN_5','B_TUR_F','B_STR_AB_NE'):
        obj.location=(4,8,2);obj.rotation_euler=(.1,.2,.3);obj.scale=(2,2,2)
        obj['UserData']=17;bpy.context.view_layer.update()
        before=obj.matrix_world.copy();old=mesh
        old[builder.MESH_REVISION_TAG]='old-native-proxy'
        builder.refresh_forsaken_proxies(bpy.context.scene)
        assert obj.data is not old and obj.data.get(builder.MESH_REVISION_TAG)=='18.2.36',identity
        assert obj.matrix_world==before and obj['UserData']==17 and obj['ObjectID']==identity
    checks.append(dict(id=identity,triangles=row['triangles'],basicTriangles=row['proxyTriangles']))
export=addon.BUILDER.serialise()['Objects']
assert sorted(x['ObjectID'] for x in export)==sorted('^'+x for x in expected)
report('changed_native_models36_'+str(bpy.app.version[1]),dict(assets=len(checks),exportIdsPreserved=True,
       cachedMeshMigrationPreservesTransforms=True,basicMaximumTriangles=max(x['basicTriangles'] for x in checks),checks=checks))
