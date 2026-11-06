"""Native doorway frames merged into temporary hab display meshes."""
import json
from pathlib import Path
from functools import lru_cache
import bpy
import numpy as np
from mathutils import Matrix

ROOT=Path(__file__).parent/'resources'

@lru_cache(None)
def frames():
    return json.loads((ROOT/'hab_doorway_frames.json').read_text())

def doorway_mesh(style,axis,detailed):
    key=axis+'_'+style+(' detailed' if detailed else ' simple')
    mesh=next((m for m in bpy.data.meshes if m.get('bbe_doorway_asset')==key),None)
    if mesh is None:
        with bpy.data.libraries.load(str(ROOT/'hab_doorways.blend'),link=False) as (a,b):
            b.meshes=['BBE Doorway '+key]
        mesh=b.meshes[0]
    return mesh

def add_frames(base,pid,slots,detailed):
    locators=frames()['hab' if pid.startswith('B_HAB_') else 'walkway']
    pieces=[(base,Matrix.Identity(4))]
    for slot in sorted(slots):
        axis='NS' if slot[4] in 'NS' else 'EW'
        pieces.append((doorway_mesh(pid[-1],axis,detailed),Matrix(locators[slot])))
    vertices=[];faces=[];indices=[];smooth=[];normals=[];materials=list(base.materials)
    uv_names=set(uv.name for mesh,_ in pieces for uv in mesh.uv_layers)
    uvs={name:[] for name in uv_names}
    for mesh,transform in pieces:
        offset=len(vertices)
        coords=np.empty(len(mesh.vertices)*3,dtype=np.float32)
        mesh.vertices.foreach_get('co',coords)
        coords=coords.reshape(-1,3)@np.asarray(transform.to_3x3()).T+np.asarray(transform.translation)
        vertices.extend(coords.tolist())
        faces.extend([offset+i for i in face.vertices] for face in mesh.polygons)
        mapping=[]
        for mat in mesh.materials:
            if mat not in materials:materials.append(mat)
            mapping.append(materials.index(mat))
        indices.extend(mapping[p.material_index] if mapping else 0 for p in mesh.polygons)
        smooth.extend(p.use_smooth for p in mesh.polygons)
        n=np.empty(len(mesh.loops)*3,dtype=np.float32);mesh.corner_normals.foreach_get('vector',n)
        n=n.reshape(-1,3)@np.asarray(transform.to_3x3().inverted_safe().transposed()).T
        n/=np.maximum(np.linalg.norm(n,axis=1,keepdims=True),1e-12);normals.extend(n.tolist())
        for name in uv_names:
            values=np.zeros(len(mesh.loops)*2,dtype=np.float32)
            if name in mesh.uv_layers:mesh.uv_layers[name].data.foreach_get('uv',values)
            uvs[name].extend(values)
    result=bpy.data.meshes.new(base.name+' / doorways')
    result.from_pydata(vertices,[],faces)
    for mat in materials:result.materials.append(mat)
    result.polygons.foreach_set('material_index',indices)
    result.polygons.foreach_set('use_smooth',smooth)
    for name,values in uvs.items():result.uv_layers.new(name=name).data.foreach_set('uv',values)
    result.normals_split_custom_set(normals)
    for name,value in base.items():result[name]=value
    result.update()
    return result
