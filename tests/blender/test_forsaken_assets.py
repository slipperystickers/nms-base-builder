"""Native catalog, proxy/HD loading, portability, colour and export regression."""
from pathlib import Path
import sys,json,math
from unittest.mock import patch
import bpy
sys.path.insert(0,str(Path(__file__).parent))
from test_support import addon,module,D,QA,report
library=module('builder_v2');hd=module('hd_library');materials=module('utils.materials_v2')
manifest=json.loads((D/'resources/forsaken_assets.json').read_text())
definitions=module('asset_browser.utils.parts_definition').ROWS
results=[]
bpy.data.batch_remove(list(bpy.context.scene.objects));addon.BUILDER.clear_caches()
for entry in manifest['assets']:
    pid=entry['id'];assert '^'+pid in definitions
    assert (D/'images/asset_icons'/(pid+'.png')).is_file()
    if entry['parent']:assert '^'+entry['parent'] in definitions
    obj=library.add_part(pid,user_data=0).object
    assert obj['ObjectID']==pid and materials.is_high_res(obj),pid
    assert len(obj.data.vertices)>8 and len(obj.data.polygons)>6,pid
    assert all(math.isfinite(v) for row in obj.matrix_world for v in row)
    images=library._mesh_texture_images(obj.data)
    assert all(i.packed_file or Path(bpy.path.abspath(i.filepath)).is_file() for i in images),pid
    materials.apply(obj,0) if hasattr(materials,'apply') else None
    # A project from another machine must resolve the bundled native textures.
    image=next((i for i in images if i.get('bbe_native_texture')),None)
    if image:
        image.filepath='C:/OtherBuilder/absent/'+image['bbe_native_texture']
        assert library._relink_mesh_textures(obj.data)
        assert Path(image.filepath).is_relative_to(hd.additions_root() / 'textures'),(pid,image.filepath)
        assert Path(image.filepath).is_file(),pid
    simple=module('simple_library').load_mesh(pid)
    # New cockpits keep their structural surfaces: deeper reduction tears them.
    budget=30000 if pid.startswith('B_COK_C') or pid=='B_COK_E' else 6000
    assert simple and len(simple.vertices)>8 and 0<len(simple.polygons)<=budget,(pid,len(simple.polygons))
    if pid in library.NEW_COCKPITS:
        assert simple.get('bbe_forsaken_revision')==library.COCKPIT_BASE_REVISION,pid
    results.append(dict(id=pid,polygons=len(obj.data.polygons),proxyPolygons=len(simple.polygons),textures=len(images)))
export=addon.BUILDER.serialise()['Objects']
assert sorted(o['ObjectID'] for o in export)==sorted('^'+x['id'] for x in results)
for obj in list(bpy.context.scene.objects):bpy.data.objects.remove(obj,do_unlink=True)
addon.BUILDER.clear_caches();bpy.context.scene.bbe_detailed_proxies=False
with patch.object(hd,'library_root',return_value=None),patch.object(hd,'available',return_value=False):
    library.get_asset_index(rebuild=True)
    for pid in ('B_COK_C1','B_STR_AC_Y_NE2','B_HAB_D','GRAV_FLOOR'):
        obj=library.add_part(pid,user_data=0).object
        assert obj and not materials.is_high_res(obj) and len(obj.data.vertices)>8,pid
report('forsaken_assets_'+str(bpy.app.version[1]),dict(build=manifest['gameBuild'],assets=len(results),
       exports=len(export),portableTextures=True,simpleWithoutHDPack=True,results=results))
