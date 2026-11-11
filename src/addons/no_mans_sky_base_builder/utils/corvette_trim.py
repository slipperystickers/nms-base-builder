"""Restore the Forsaken gun and generator's native vertex shading and trim atlas."""
import hashlib
import zlib

import bpy
import numpy as np

from .. import hd_library
# Identifies the prepared mesh's native vertex order, including removed degenerates.
GEOMETRY = {
    'B_TUR_F': (20728, 'a5146a577d8c8a020bd16e043349e52277ea519615317da3d072db0be04e2747', '/GUN_F/'),
    'B_GEN_5': (214992, 'a45c5ed848e06a16943cbc0124b2273c8f939ce76f035dead84e6984137ef18c', '/GENERATOR_1X1_5/'),
}
TAG = 'bbe_native_trim_v1'
SHADE = 'bbe_native_trim_shade'
LAYER = 'bbe_native_trim_layer'
FINISHES = ('Corvette - Gloss Finish', 'Corvette - Inverted Gloss Finish',
            'Corvette - Weathered Finish', 'Corvette - Metallic Finish')


def atlas_image(name, resource):
    filename = 'BBE Corvette Trim ' + name
    image = next((im for im in bpy.data.images if im.get(TAG) == name), None)
    if image is None:
        image = bpy.data.images.load(str(resource / (name + '.png')), check_existing=False)
        image.name = filename
        image.colorspace_settings.name = 'sRGB' if name == 'diffuse' else 'Non-Color'
        image[TAG] = name
        image.pack()
    return image


def detail_material(original, resource):
    mat = original.copy()
    mat.name = original.name + ' (native trim)'
    nodes, link = mat.node_tree.nodes, mat.node_tree.links.new
    uv = nodes.new('ShaderNodeTexCoord')
    remap = nodes.new('ShaderNodeVectorMath')
    remap.operation = 'MULTIPLY_ADD'
    # All used UVs fit inside [0,7/16] x [3/4,7/8]. Four cropped mip-zero
    # DDS slices are stacked bottom to top. The UV margin avoids filtering seams.
    remap.inputs[1].default_value = (16/7, 2, 1)
    remap.inputs[2].default_value = (0, -1.5, 0)
    link(uv.outputs['UV'], remap.inputs[0])
    layer = nodes.new('ShaderNodeAttribute')
    layer.attribute_type = 'OBJECT'
    layer.attribute_name = LAYER
    tile = nodes.new('ShaderNodeVectorMath')
    tile.operation = 'SCALE'
    tile.inputs[0].default_value = (0,.25,0)
    link(layer.outputs['Fac'], tile.inputs['Scale'])
    coord = nodes.new('ShaderNodeVectorMath')
    coord.operation = 'ADD'
    link(remap.outputs[0], coord.inputs[0])
    link(tile.outputs[0], coord.inputs[1])
    for node_name, atlas in (('gDiffuseMap','diffuse'), ('gMasksMap','masks'), ('gNormalMap','normal'),
                             ('colourise','colourisemask'), ('gColouriseMaskMap','colourisemask')):
        node = nodes.get(node_name)
        if node is not None:
            node.image = atlas_image(atlas, resource)
            link(coord.outputs[0], node.inputs['Vector'])

    paint = next(n for n in nodes if n.type == 'GROUP' and n.node_tree and n.node_tree.name.startswith('NMS_Colourise'))
    shade = nodes.new('ShaderNodeAttribute')
    shade.attribute_name = SHADE
    multiply = nodes.new('ShaderNodeMixRGB')
    multiply.label = 'Native vertex shading'
    multiply.blend_type = 'MULTIPLY'
    multiply.inputs[0].default_value = 1
    link(nodes['gDiffuseMap'].outputs['Color'], multiply.inputs[1])
    link(shade.outputs['Fac'], multiply.inputs[2])
    link(multiply.outputs[0], paint.inputs['Diffuse'])
    mat[TAG] = True
    return mat


def correct(mesh, pid):
    spec = GEOMETRY.get(pid)
    if spec is None or mesh.get(TAG) or len(mesh.vertices) != spec[0] or len(mesh.materials) != 1:
        return
    original = mesh.materials[0]
    if original is None or spec[2] not in original.get('nms_material_path', '').upper().replace('\\','/'):
        return
    if not original.node_tree:
        return
    nodes = original.node_tree.nodes
    textures = [nodes.get(name) for name in ('gDiffuseMap', 'gMasksMap', 'colourise', 'gNormalMap')]
    if any(n is None or n.inputs['Vector'].is_linked for n in textures):
        return  # Keep custom material mappings intact.
    paint = next((n for n in nodes if n.type == 'GROUP' and n.node_tree and
                  n.node_tree.name.startswith('NMS_Colourise')), None)
    if (paint is None or not paint.inputs['Diffuse'].links or
            paint.inputs['Diffuse'].links[0].from_node != textures[0]):
        return
    root = hd_library.additions_root(allow_previous=False)
    if root is None:
        return  # Keep the previous material until the optional pack is ready.
    resource = root / 'corvette_trim'
    xyz = np.empty((len(mesh.vertices),3), dtype='<f4')
    mesh.vertices.foreach_get('co',xyz.ravel())
    if hashlib.sha256(xyz.tobytes()).hexdigest() != spec[1]:
        return
    values = np.frombuffer(zlib.decompress((resource / (pid + '.zlib')).read_bytes()), dtype=np.uint8)
    if len(values) != len(xyz):
        raise ValueError('Incorrect native vertex shading data for ' + pid)
    material = detail_material(original, resource)
    attribute = mesh.attributes.get(SHADE) or mesh.attributes.new(SHADE, 'FLOAT', 'POINT')
    attribute.data.foreach_set('value', values.astype(np.float32) / 255)
    mesh.materials[0] = material
    mesh[TAG] = True
    mesh.update()


def refresh_scene(scene):
    from . import materials_v2
    for obj in scene.objects:
        pid = obj.get('ObjectID')
        if pid in GEOMETRY and materials_v2.is_high_res(obj):
            correct(obj.data, pid)
            if obj.data.get(TAG) and LAYER not in obj:
                materials_v2.apply(obj, obj.get('UserData', 0))
