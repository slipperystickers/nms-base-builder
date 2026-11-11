"""Build waste unit wall variants from authored NMS scenes; no replacement geometry."""
from pathlib import Path
import ast,sys,hashlib
R=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(R/'tests/blender'))
# Reuse the native geometry/normal/material decoder without running its catalog batch.
p=R/'tests/blender/build_forsaken_assets.py'
tree=ast.parse(p.read_text());nodes=[]
for node in tree.body:
 if isinstance(node,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='manifest_path' for t in node.targets):break
 nodes.append(node)
ns={'__file__':str(p),'__name__':'waste_native_builder'}
exec(compile(ast.Module(body=nodes,type_ignores=[]),str(p),'exec'),ns)
bpy=ns['bpy'];Matrix=ns['Matrix'];texture_root=ns['OUT']/'textures'
from functools import lru_cache
@lru_cache(None)
def image(name,data):
 # Reuse the installed pack's existing texture quality and artwork.
 packed_name=Path(name.split('_',1)[1]).with_suffix('.webp').name.upper()
 library=ns['module']('hd_library').library_root()/'textures'
 textures={p.name.upper():p for p in library.iterdir() if p.is_file()}
 source=textures.get(packed_name)
 im=bpy.data.images.load(str(source or texture_root/name),check_existing=False)
 im.colorspace_settings.name='Non-Color' if data else 'sRGB'
 if source:
  im.filepath='//models-high-res/textures/'+source.name
 else:
  im.pack()
 return im
ns['image']=image

def native_black_materials(scene):
    # Exterior B panels multiply the diffuse texture by a black vertex stream.
    # C uses the same diffuse texture without vertex shading.
    import numpy as np
    root=ns['scene'](scene)
    geom,raw,meta=ns['geometry'](root.attributes['GEOMETRY'])
    paths=set()
    for node in root.iter():
        attrs=node.attributes
        path=attrs.get('MATERIAL','')
        if node.Type!='MESH' or attrs.get('LODLEVEL','0')!='0' or not path:continue
        if '_F21_VERTEXCUSTOM' not in ns['MATERIALS'][ns['norm'](path)]['flags']:continue
        stream=meta[node.Name.upper()]
        layout=geom.VertexLayout
        e=next(e for e in layout.VertexElements if e.SemanticID==4)
        assert e.Type==5121 and e.Size==4
        count=stream.VertexPositionDataSize//geom.PositionVertexLayout.Stride
        rgba=np.ndarray((count,4),np.uint8,raw,stream.VertexDataOffset+e.Offset,(layout.Stride,1))
        assert not rgba[:,:3].any(), (scene,node.Name)
        paths.add(ns['norm'](path))
    return paths

out=R/'tests/.artifacts/waste-native-build'
for folder in ('assets','simple'):(out/folder).mkdir(exist_ok=True,parents=True)
ns['OUT']=out
for obj in list(bpy.data.objects):bpy.data.objects.remove(obj,do_unlink=True)
dest=R/'src/addons/no_mans_sky_base_builder/resources/waste_walls';dest.mkdir(exist_ok=True)
meshes=set()
for style in ('A','B','C'):
    scene='MODELS/COMMON/SPACECRAFT/BIGGS/MODULES/PARTS/WALL_EW_'+style+'_TOILET0.SCENE.MBIN'
    pid='WASTE_EW_'+style
    result=ns['build'](dict(id=pid,placementScene=scene,components=[dict(scene=scene,locator=ns['scene'](scene).Name,entity='')]))
    print(pid,result['polygons'],flush=True)
    black=native_black_materials(scene)
    for quality,folder in [('detailed','assets'),('simple','simple')]:
        with bpy.data.libraries.load(str(out/folder/(pid+'.blend'))) as (src,dst):dst.meshes=list(src.meshes)
        mesh=dst.meshes[0];mesh.name=f'BBE Waste Wall {style} {quality}'
        for mat in mesh.materials:
            mat.use_backface_culling=True
            if ns['norm'](mat.get('nms_material_path','')) in black:
                base=mat.node_tree.nodes.get('Principled BSDF').inputs['Base Color']
                for link in list(base.links):mat.node_tree.links.remove(link)
                base.default_value=(0,0,0,1)
        meshes.add(mesh)

# B and C use many of the same textures. Share identical packed images in the library.
images={}
for mesh in meshes:
    for im in ns['module']('builder_v2')._mesh_texture_images(mesh):
        if not im.packed_file:continue
        key=(im.colorspace_settings.name,hashlib.sha256(im.packed_file.data).digest())
        if key in images and images[key]!=im:
            im.user_remap(images[key])
        else:
            images[key]=im
for quality in ('simple', 'detailed'):
    folder = dest if quality == 'simple' else dest.parent / 'hd_additions/waste_walls'
    folder.mkdir(exist_ok=True)
    bpy.data.libraries.write(str(folder / (quality + '.blend')), {m for m in meshes if m.name.endswith(' ' + quality)},
                             path_remap='NONE', fake_user=True, compress=True)
