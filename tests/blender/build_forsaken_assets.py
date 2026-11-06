"""Reproducible native 7.10 assets, with placement-rule matrices and shared textures."""
from pathlib import Path
import sys, json, re, math, traceback, os, hashlib
import xml.etree.ElementTree as ET
from types import SimpleNamespace
from functools import lru_cache
sys.path.insert(0,str(Path(__file__).parent))
from test_support import *
import numpy as np
from mathutils import Matrix
WORK=Path(r'C:\Users\kengo\OneDrive\Desktop\NMS')
ROOT=WORK/'outputs/nms-update-20261028'
SOURCE=ROOT/'native'; OUT=ROOT/'built'
sys.path.insert(0,str(WORK/'fusion_nms_base_builder/.tools/NMSDK/src/addon'))
sys.path.insert(0,str(WORK/'fusion_nms_base_builder/.tools/hgpaktool'))
from nmsdk.serialization.NMS_Structures import MBINHeader,TkSceneNodeData,TkGeometryData
from nmsdk.ModelImporter.SceneNodeData import SceneNodeData
from nmsdk.serialization.formats import np_read_int_2_10_10_10_rev
from native_geometry_normals import read_normals
MATERIALS=json.loads((OUT/'materials.json').read_text())
for folder in ('assets','simple'):(OUT/folder).mkdir(exist_ok=True)
def norm(path):return path.replace('\\','/').lower()
def component_matrix(node, path):
    # GRAV_WALL has compound rotations on its rail copies. The generic
    # importer uses XYZ and leaves its top rail detached and a side rail low.
    # Its authored component frames compose X @ Y @ Z (Blender ZYX).
    if norm(path).endswith('/meshes/grav_wall.scene.mbin'):
        from mathutils import Euler
        t=node.Transform
        return (Matrix.Translation(t['Trans']) @ Euler(t['Rot'], 'ZYX').to_matrix().to_4x4()
                @ Matrix.Diagonal((*t['Scale'], 1)))
    return node.matrix_local
@lru_cache(None)
def scene(path):
    def val(e,name):return e.find(f"Property[@name='{name}']").get('value','')
    def node(e):
        return SimpleNamespace(Name=val(e,'Name'),Type=val(e,'Type'),
            Transform=SimpleNamespace(**{p.get('name'):float(p.get('value')) for p in e.find("Property[@name='Transform']")}),
            Attributes=[SimpleNamespace(Name=val(p,'Name'),Value=val(p,'Value')) for p in e.find("Property[@name='Attributes']")],
            Children=[node(p) for p in e.find("Property[@name='Children']")])
    return SceneNodeData(node(ET.parse((SOURCE/norm(path)).with_suffix('.MXML')).getroot()))
@lru_cache(maxsize=24)
def geometry(path):
    p=SOURCE/(norm(path)+'.pc')
    with p.open('rb') as f:MBINHeader.read(f);g=TkGeometryData.read(f)
    raw=p.with_name(p.name.replace('.geometry.','.geometry.data.')).read_bytes()
    return g,raw,{m.IdString.upper():m for m in g.StreamMetaDataArray}

# Reuse the shipped, tested per-object palette group, including its mask decoding.
module('builder_v2').load_high_res_mesh('B_COK_A')
colour_group=bpy.data.node_groups['NMS_Colourise']
used_textures=set()
@lru_cache(None)
def image(name, data):
    im=bpy.data.images.load(str(OUT/'textures'/name),check_existing=False)
    im.colorspace_settings.name='Non-Color' if data else 'sRGB'
    im['bbe_native_texture']=name
    im.filepath='//../textures/'+name
    used_textures.add(name)
    return im
@lru_cache(None)
def material(path):
    spec=MATERIALS[norm(path)]
    mat=bpy.data.materials.new(spec['name']);mat.use_nodes=True
    mat['nms_material_path']=path.upper();mat['nms_class']=spec['materialClass'];mat['nms_flags']=spec['flags']
    nodes=mat.node_tree.nodes;links=mat.node_tree.links;bs=nodes.get('Principled BSDF')
    uniforms=spec['uniforms'];params=uniforms.get('gMaterialParamsVec4',[.5,0,0,1])
    bs.inputs['Base Color'].default_value=uniforms.get('gMaterialColourVec4',[1,1,1,1])
    bs.inputs['Roughness'].default_value=max(0,min(1,params[0]));bs.inputs['Metallic'].default_value=max(0,min(1,params[1]))
    textures={}
    for key,filename in spec['images'].items():
        if not filename:continue
        t=nodes.new('ShaderNodeTexImage');t.name=key;t.image=image(filename,key not in ('gDiffuseMap','gDiffuse2Map','gDiffuseMap2'))
        textures[key]=t
    diffuse=textures.get('gDiffuseMap');flags=spec['flags'];base=diffuse.outputs['Color'] if diffuse else None
    if '_F53_COLOURISABLE' in flags and base:
        mask=textures.get('colourise')
        if mask:
            group=nodes.new('ShaderNodeGroup');group.node_tree=colour_group
            separate=nodes.new('ShaderNodeSeparateColor');links.new(mask.outputs['Color'],separate.inputs[0])
            links.new(base,group.inputs['Diffuse']);links.new(separate.outputs['Red'],group.inputs['Mask']);base=group.outputs[0]
        else:
            attr=nodes.new('ShaderNodeAttribute');attr.attribute_type='OBJECT';attr.attribute_name='["nms_p"]'
            mult=nodes.new('ShaderNodeMixRGB');mult.blend_type='MULTIPLY';mult.inputs[0].default_value=1
            links.new(base,mult.inputs[1]);links.new(attr.outputs['Color'],mult.inputs[2]);base=mult.outputs[0]
    if base:links.new(base,bs.inputs['Base Color'])
    masks=textures.get('gMasksMap')
    if masks:
        separate=nodes.new('ShaderNodeSeparateColor');links.new(masks.outputs['Color'],separate.inputs[0])
        inv=nodes.new('ShaderNodeMath');inv.operation='SUBTRACT';inv.inputs[0].default_value=1
        links.new(separate.outputs['Red'],inv.inputs[1]);links.new(inv.outputs[0],bs.inputs['Roughness'])
        links.new(separate.outputs['Green'],bs.inputs['Metallic'])
    normal=textures.get('gNormalMap')
    if normal:
        # NMS uses BC5 normals: reconstruct positive Z from the stored R/G.
        separate=nodes.new('ShaderNodeSeparateColor');links.new(normal.outputs['Color'],separate.inputs[0])
        def math_node(op,a,b=None):
            n=nodes.new('ShaderNodeMath');n.operation=op
            for i,v in enumerate((a,b)):
                if v is None:continue
                if isinstance(v,(int,float)):n.inputs[i].default_value=v
                else:links.new(v,n.inputs[i])
            return n.outputs[0]
        x=math_node('SUBTRACT',math_node('MULTIPLY',separate.outputs['Red'],2),1)
        y=math_node('SUBTRACT',math_node('MULTIPLY',separate.outputs['Green'],2),1)
        z=math_node('SQRT',math_node('MAXIMUM',math_node('SUBTRACT',1,math_node('ADD',math_node('MULTIPLY',x,x),math_node('MULTIPLY',y,y))),0))
        combine=nodes.new('ShaderNodeCombineColor');links.new(separate.outputs['Red'],combine.inputs['Red']);links.new(separate.outputs['Green'],combine.inputs['Green'])
        links.new(math_node('ADD',math_node('MULTIPLY',z,.5),.5),combine.inputs['Blue'])
        n=nodes.new('ShaderNodeNormalMap');links.new(combine.outputs[0],n.inputs['Color']);links.new(n.outputs[0],bs.inputs['Normal'])
    if '_F07_UNLIT' in flags:
        if base:links.new(base,bs.inputs['Emission Color'])
        else:bs.inputs['Emission Color'].default_value=uniforms.get('gMaterialColourVec4',[0,0,0,1])
        bs.inputs['Emission Strength'].default_value=1
    if diffuse and (spec['materialClass'] in ('Cutout','GlowTranslucent','Translucent') or '_F09_TRANSPARENT' in flags or '_F11_ALPHACUTOUT' in flags):
        links.new(diffuse.outputs['Alpha'],bs.inputs['Alpha']);mat.surface_render_method='DITHERED'
    return mat

def nodes_in_scene(path,parent=None,depth=0):
    assert depth<24,('Reference cycle',path)
    parent=Matrix.Identity(4) if parent is None else parent
    def walk(node,world):
        matrix=world@node.matrix_local
        yield node,matrix
        if node.Type=='REFERENCE':yield from nodes_in_scene(node.attributes['SCENEGRAPH'],matrix,depth+1)
        for child in node.children:yield from walk(child,matrix)
    yield from walk(scene(norm(path)),parent)

def build(row):
    pid=row['id'];objects=[];audit=[]
    placement=list(nodes_in_scene(row['placementScene']))
    locators={n.Name:m for n,m in placement}
    entities={norm(v):m for n,m in placement for v in n.attributes.values() if str(v).upper().endswith('.ENTITY.MBIN')}
    def walk_scene(path,parent,depth=0):
        assert depth<24
        if norm(path).startswith('models/effects/'):return
        root=scene(norm(path));geo=root.attributes.get('GEOMETRY')
        def walk(node,matrix):
            world=matrix@component_matrix(node,path);a=node.attributes;name=node.Name
            lod=re.search(r'LOD(\d+)',name,re.I)
            if lod and int(lod.group(1))>0:return
            if node.Type=='REFERENCE':walk_scene(a['SCENEGRAPH'],world,depth+1)
            if node.Type=='MESH' and 'MATERIAL' in a and int(a.get('LODLEVEL','0'))==0:
                if any(token in a['MATERIAL'].upper() for token in ('COLLISION','LIGHTBLOCK','TERRAINEDIT','WATERPROXY','EXCLUSIONVOLUME','SHADOWONLY','CANOPYFADE','DEPTHMASK')):return
                g,raw,meta=geometry(geo);m=meta[name.upper()];layout=g.PositionVertexLayout;count=m.VertexPositionDataSize//layout.Stride
                if not count:return
                def semantic(semantic_id):
                    ve=next((v for v in layout.VertexElements if v.SemanticID==semantic_id),None)
                    if ve is None:return None
                    dtype={5131:np.float16,5126:np.float32}[ve.Type]
                    return np.ndarray((count,ve.Size),dtype=dtype,buffer=raw,offset=m.VertexPositionDataOffset+ve.Offset,strides=(layout.Stride,np.dtype(dtype).itemsize)).astype(np.float32)
                points=semantic(0)[:,:3];uv=semantic(1)
                ic=int(a['BATCHCOUNT']);stride=m.IndexDataSize//ic;assert stride in (2,4),(path,name,stride)
                indices=np.frombuffer(raw,dtype=np.uint16 if stride==2 else np.uint32,count=ic,offset=m.VertexDataOffset+m.IndexDataOffset).astype(np.int32)
                assert indices.max()<count and np.isfinite(points).all(),(path,name)
                mesh=bpy.data.meshes.new(name);mesh.from_pydata(points,[],indices.reshape(-1,3));mesh.materials.append(material(a['MATERIAL']))
                if uv is not None:
                    uv=uv[:,:2];uv[:,1]=1-uv[:,1];mesh.uv_layers.new(name='UVMap').data.foreach_set('uv',uv[indices].ravel())
                normals=read_normals(g,m,raw,count,np_read_int_2_10_10_10_rev)
                # Placement locators may scale components nonuniformly. Transform
                # the normals with the inverse transpose, then normalize, after
                # transforming positions (Mesh.transform does not normalize them).
                mesh.transform(world)
                normals=normals@np.asarray(world.to_3x3().inverted_safe().transposed()).T
                normals/=np.maximum(np.linalg.norm(normals,axis=1,keepdims=True),1e-12)
                for poly in mesh.polygons:poly.use_smooth=True
                mesh.normals_split_custom_set_from_vertices(normals.tolist())
                mesh.update();obj=bpy.data.objects.new(name,mesh);bpy.context.scene.collection.objects.link(obj);objects.append(obj)
                audit.append(dict(scene=path,node=name,vertices=count,triangles=ic//3,joints=len(g.JointBindings),nativeNormals=True))
            for child in node.children:walk(child,world)
        walk(root,parent)
    for component in row['components']:
        transform=locators[component['locator']] if component['locator'] else entities[norm(component['entity'])]
        walk_scene(component['scene'],transform)
    assert objects,('Empty native asset',pid)
    module('utils.blend_utils').select(objects);bpy.ops.object.join();obj=bpy.context.active_object;obj.name=pid;obj.data.name=pid
    module('utils.blend_utils').remove_duplicate_faces(obj.data)
    assert obj.data.has_custom_normals and all(p.use_smooth for p in obj.data.polygons), pid
    obj.data['bbe_forsaken_revision']=2
    obj['bbe_native_build']=26271400;obj['bbe_native_assembly']='7.10 native placement conditions and locator matrices'
    bounds=[[min(v.co[a] for v in obj.data.vertices) for a in range(3)],[max(v.co[a] for v in obj.data.vertices) for a in range(3)]]
    bpy.data.libraries.write(str(OUT/'assets'/(pid+'.blend')),{obj},path_remap='NONE',fake_user=True,compress=True)
    high_polys=len(obj.data.polygons)
    proxy=obj.copy();proxy.data=obj.data.copy();bpy.context.scene.collection.objects.link(proxy)
    module('utils.blend_utils').select([proxy])
    if pid in {f'B_COK_C{i}' for i in range(1, 10)} | {'B_COK_E'}:
        # These cockpits have thousands of disconnected interior fragments. A
        # global decimator collapses their shells into scattered shards. Keep
        # the sizeable native surfaces as their base proxies instead.
        import bmesh
        reduced=bmesh.new();reduced.from_mesh(proxy.data)
        bmesh.ops.remove_doubles(reduced,verts=list(reduced.verts),dist=0.000001)
        visited=set();small=[];minimum_area=10 if pid=='B_COK_E' else 5
        for vertex in reduced.verts:
            if vertex in visited:continue
            pending=[vertex];visited.add(vertex);component=[]
            while pending:
                current=pending.pop();component.append(current)
                for edge in current.link_edges:
                    other=edge.other_vert(current)
                    if other not in visited:
                        visited.add(other);pending.append(other)
            faces={face for point in component for face in point.link_faces}
            if sum(face.calc_area() for face in faces)<minimum_area:
                small.extend(component)
        bmesh.ops.delete(reduced,geom=small,context='VERTS')
        reduced.to_mesh(proxy.data);reduced.free();proxy.data.update()
        proxy.data['bbe_forsaken_revision']=3
    elif high_polys>3500:
        # Native UV/normal seams split vertices. Weld only the plain low-detail
        # proxy before reduction so disconnected seam triangles do not block
        # the decimator; never change the detailed mesh or its shading data.
        import bmesh
        reduced=bmesh.new();reduced.from_mesh(proxy.data)
        bmesh.ops.remove_doubles(reduced,verts=list(reduced.verts),dist=0.000001)
        reduced.to_mesh(proxy.data);reduced.free()
        dec=proxy.modifiers.new('Native proxy reduction','DECIMATE');dec.ratio=3500/high_polys
        bpy.ops.object.modifier_apply(modifier=dec.name)
        if len(proxy.data.polygons)>3500:
            dec=proxy.modifiers.new('Native proxy budget','DECIMATE')
            dec.ratio=3400/len(proxy.data.polygons)
            bpy.ops.object.modifier_apply(modifier=dec.name)
    proxy.data.materials.clear();proxy.name=pid;proxy.data.name=pid
    bpy.data.libraries.write(str(OUT/'simple'/(pid+'.blend')),{proxy.data},path_remap='NONE',fake_user=True,compress=True)
    result=dict(id=pid,bounds=bounds,polygons=high_polys,proxyPolygons=len(proxy.data.polygons),components=audit)
    for o in list(bpy.context.scene.objects):bpy.data.objects.remove(o,do_unlink=True)
    return result

manifest_path=Path(os.environ.get('BBE_NATIVE_MANIFEST',str(ROOT/'new-objects.json')))
rows=json.loads(manifest_path.read_text())
audit_prefix=os.environ.get('BBE_NATIVE_AUDIT_PREFIX','')
ids=os.environ.get('BBE_NATIVE_IDS','').split(',')
if ids!=['']:rows=[r for r in rows if r['id'] in ids]
report_data={};failures={}
for row in rows:
    if row['id'] in ('B_LND_D','B_TRU_I'):continue  # Missing in the installed native archives.
    try:
        report_data[row['id']]=build(row)
        print('BUILT',row['id'],report_data[row['id']]['polygons'],flush=True)
    except Exception:
        failures[row['id']]=traceback.format_exc();print('FAILED',row['id'],failures[row['id']],flush=True)
        for o in list(bpy.context.scene.objects):bpy.data.objects.remove(o,do_unlink=True)
    (OUT/(audit_prefix+'asset-audit.json')).write_text(json.dumps(report_data,indent=2))
    (OUT/(audit_prefix+'asset-failures.json')).write_text(json.dumps(failures,indent=2))
    (OUT/(audit_prefix+'used-textures.json')).write_text(json.dumps(sorted(used_textures),indent=2))
assert not failures,failures.keys()
