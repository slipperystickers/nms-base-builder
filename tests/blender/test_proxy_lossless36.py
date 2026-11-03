"""Lossless shared shader cleanup and placement scope regression."""
from pathlib import Path
import sys,hashlib,json
from unittest.mock import patch
import bpy,numpy as np
sys.path.insert(0,str(Path(__file__).parent))
from test_support import module,addon,report
builder=module('builder_v2');mat=module('utils.materials_v2')
ids=['B_COK_C1','B_COK_C4','B_COK_C7','B_COK_E','B_HAB_D','B_CON_16','B_WNG_Y','B_WNG_S','B_WNG_T','B_WNG_U','B_STR_AC_NE','B_TRU_H']
with patch.object(mat,'dedupe_native_materials',return_value=0):
    with mat.defer_shared_data():
        for pid in ids:builder.add_part(pid,user_data=0,build_rigs=False)
objects=[o for o in bpy.context.scene.objects if o.get('ObjectID') in ids]
def mesh_digest(mesh):
    h=hashlib.sha256()
    for collection,key,width,dtype in [(mesh.vertices,'co',3,np.float32),(mesh.loops,'vertex_index',1,np.int32),(mesh.polygons,'loop_start',1,np.int32),(mesh.polygons,'loop_total',1,np.int32),(mesh.polygons,'material_index',1,np.int32),(mesh.corner_normals,'vector',3,np.float32)]:
        data=np.empty(len(collection)*width,dtype=dtype);collection.foreach_get(key,data);h.update(data.tobytes())
    for uv in mesh.uv_layers:
        data=np.empty(len(uv.data)*2,dtype=np.float32);uv.data.foreach_get('uv',data);h.update(data.tobytes())
    return h.hexdigest()
before_meshes={o.name:mesh_digest(o.data) for o in objects}
before_export=addon.BUILDER.serialise()['Objects']
before_materials=len(bpy.data.materials);before_images=len(bpy.data.images)
removed=mat.dedupe_native_materials()
assert removed>=150,(removed,before_materials)
assert len(bpy.data.images)==before_images
assert before_meshes=={o.name:mesh_digest(o.data) for o in objects}
assert before_export==addon.BUILDER.serialise()['Objects']
# Repaint an instance independently without separating shared geometry.
a=builder.add_part('B_COK_C1',user_data=0,build_rigs=False).object
b=builder.add_part('B_COK_C1',user_data=0,build_rigs=False).object
mat.recolour([b],colour_index=2)
assert a.data is b.data and a['UserData']!=b['UserData']
# Cached placements must not run library indexing or scene-wide cleanup.
with patch.object(builder,'get_asset_index',side_effect=AssertionError('cached index scan')):
    assert builder.load_high_res_mesh('B_COK_C1') is a.data
with patch.object(mat,'_plan_image_dedupe',side_effect=AssertionError('unnecessary cleanup')):
    assert builder.add_part('B_COK_C1',user_data=0,build_rigs=False)
# Identical native copies share; user shader edits, mapping, constants and metadata do not.
base=bpy.data.materials.new('Native test');base.use_nodes=True;base['nms_material_path']='TEST/NATIVE.MATERIAL.MBIN'
tex=base.node_tree.nodes.new('ShaderNodeTexImage');const=base.node_tree.nodes.new('ShaderNodeRGB')
base.node_tree.links.new(const.outputs[0],base.node_tree.nodes.get('Principled BSDF').inputs['Base Color'])
copy=base.copy();copy.name='Identical'
variants=[]
for index in range(6):
    changed=base.copy();changed.name='Edited '+str(index)
    if index==0:changed.node_tree.nodes.get('Principled BSDF').inputs['Roughness'].default_value=.123
    elif index==1:changed.node_tree.nodes.get(tex.name).texture_mapping.translation=(1,2,3)
    elif index==2:changed.node_tree.nodes.get(const.name).outputs[0].default_value=(.2,.3,.4,1)
    elif index==3:changed['custom_vector']=[1.,2.,3.]
    elif index==4:changed.node_tree.nodes.get(tex.name).color_mapping.use_color_ramp=True
    else:changed.node_tree['builder_note']='Keep my separate shader metadata'
    variants.append(changed)
holders=[]
for material in [base,copy]+variants:
    mesh=bpy.data.meshes.new('holder');mesh.materials.append(material);holders.append(mesh)
assert mat.dedupe_native_materials()==1
assert holders[0].materials[0] is holders[1].materials[0]
assert len({mesh.materials[0].as_pointer() for mesh in holders[1:]})==7
report('proxy_lossless36_'+str(bpy.app.version[1]),dict(materialsBefore=before_materials,materialsAfter=before_materials-removed,removed=removed,geometryUVNormalsExact=True,texturesUnchanged=True,exportExact=True,editedShadersPreserved=True,recolourIndependent=True,cachedPlacementScoped=True))
