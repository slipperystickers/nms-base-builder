"""Compare optimized ordinary-decal geometry with shipped 18.2.15 on XE2."""
import hashlib, sys, types, zipfile
from pathlib import Path
import bpy, numpy as np
from mathutils.kdtree import KDTree
sys.path.insert(0,str(Path(__file__).resolve().parent))
from test_support import module, addon, report
d=module('decals')
path=Path(bpy.data.filepath); digest=hashlib.sha256(path.read_bytes()).hexdigest()
with zipfile.ZipFile(Path(__file__).resolve().parents[2]/'dist/no_mans_sky_base_builder-18.2.15.zip') as z:
    code=z.read('decals.py').decode('utf-8')
old=types.ModuleType(addon.__name__+'.previous_decals'); old.__package__=addon.__name__
exec(compile(code,'18.2.15/decals.py','exec'),old.__dict__)
items=[o for o in bpy.context.scene.objects if d.is_decal(o)]
receivers=[o for o in bpy.context.scene.objects if o.type=='MESH' and o.get('ObjectID') and not d.is_decal(o) and not o.hide_render and not o.hide_viewport]
def corners(obj):
    mesh=obj.data; uv=mesh.uv_layers.active.data
    rows=np.array([(*mesh.vertices[loop.vertex_index].co,*uv[loop.index].uv) for loop in mesh.loops])
    return rows.reshape(-1,3,5)
def equivalent(expected,actual):
    # Batching reorders triangles. Match complete oriented triangles and UVs,
    # allowing only Blender float32 rounding, without relying on sort ties.
    tree=KDTree(len(expected))
    for i, tri in enumerate(expected): tree.insert(tri[:,:3].mean(axis=0),i)
    tree.balance(); used=set()
    for tri in actual:
        matches=tree.find_range(tri[:,:3].mean(axis=0),4e-5)
        for _,i,_ in matches:
            if i not in used and any(np.allclose(tri,np.roll(expected[i],k,axis=0),atol=2e-5,rtol=0) for k in range(3)):
                used.add(i); break
        else: return False
    return len(used)==len(expected)
old_cache={}; new_cache={}; checked=[]
for obj in items:
    matrix=obj.matrix_world.copy()
    old.project(obj,receivers,old_cache)
    expected=corners(obj); names=set(obj.data.get('bbe_decal_receivers',[]))
    d.project(obj,receivers,new_cache)
    actual=corners(obj)
    assert actual.shape==expected.shape,(obj.name,actual.shape,expected.shape)
    assert equivalent(expected,actual),obj.name
    assert set(obj.data.get('bbe_decal_receivers',[]))==names,obj.name
    assert obj.matrix_world==matrix,obj.name
    checked.append(obj.name)
assert hashlib.sha256(path.read_bytes()).hexdigest()==digest
report('decal_batch_equivalence',{'blender':bpy.app.version_string,'decals':checked,'source_unchanged':True})
print('DECAL_BATCH_EQUIVALENCE_PASS',flush=True)
