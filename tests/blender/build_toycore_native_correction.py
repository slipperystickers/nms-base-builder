"""Reassemble the existing detailed Pocket Reality Generator asset.

The downloaded source already has the correct textures and parts. Its base and
needle sit at Y=0..tip, while the orb effects were mistakenly left at Y=0.
Move only those effects to the tip and discard the two GalaxyHalo billboard
cards that draw the unwanted thin blue outline. Adapt the flat shell and core
effects onto spherical geometry with the original textures, so they remain
visible from every viewing direction in Blender.
"""
import json
import os
import math
from pathlib import Path

import bmesh
import bpy
from mathutils import Matrix


if not bpy.app.background:
    raise RuntimeError('Build the correction in an isolated background Blender process')

addon = Path(__file__).resolve().parents[2] / 'src/addons/no_mans_sky_base_builder'
spec = json.loads((addon / 'resources/hd_library.json').read_text(encoding='utf-8'))
storage = Path(os.environ.get('BBE_ASSET_LIBRARY_ROOT') or
               Path(os.environ['LOCALAPPDATA']) / 'BaseBuilderExtended/asset-libraries')
source = storage / spec['id'] / 'assets/BASE_TOYCORE.blend'
output = addon / 'resources/hd_corrections/BASE_TOYCORE.blend'
if not source.is_file():
    raise FileNotFoundError('Install the original Detailed Proxies pack first: ' + str(source))

for obj in list(bpy.data.objects):
    bpy.data.objects.remove(obj, do_unlink=True)
with bpy.data.libraries.load(str(source), link=False) as (original, loaded):
    loaded.meshes = list(original.meshes)
meshes = [mesh for mesh in loaded.meshes if mesh]
if len(meshes) != 1:
    raise ValueError('Expected one native BASE_TOYCORE mesh')
mesh = meshes[0]
names = [mat.name.split('.')[0] if mat else '' for mat in mesh.materials]
if len(names) < 10 or names[1] != 'CoreBeam' or names[8] != 'StarGlow_Mat2' or names[9] != 'GalaxyHalo_Mat':
    raise ValueError('Native BASE_TOYCORE material layout changed; review before rebuilding')

beam = {vertex for face in mesh.polygons if face.material_index == 1
        for vertex in face.vertices}
orb = {vertex for face in mesh.polygons if 3 <= face.material_index <= 8
       for vertex in face.vertices}
outline = {vertex for face in mesh.polygons if face.material_index == 9
           for vertex in face.vertices}
if beam & (orb | outline) or len(beam) < 100 or len(orb) < 100:
    raise ValueError('Native beam and orb are no longer separate components')
tip = max(mesh.vertices[index].co.y for index in beam)
if not 1.7 < tip < 1.9:
    raise ValueError('Unexpected needle height: ' + str(tip))
for index in orb:
    mesh.vertices[index].co.y += tip

work = bmesh.new()
work.from_mesh(mesh)
to_remove = [face for face in work.faces if face.material_index == 9]
if len(to_remove) != 8:
    raise ValueError('Expected eight GalaxyHalo outline triangles')
bmesh.ops.delete(work, geom=to_remove, context='FACES')
# The exported shell/plasma/core effects are flat cards. Give these radial
# effects actual spherical surfaces, retaining the native extent and artwork.
for material_index in (6, 7, 8):
    faces = [face for face in work.faces if face.material_index == material_index]
    vertices = {v for face in faces for v in face.verts}
    radius = max(abs(v.co.x) for v in vertices)
    bmesh.ops.delete(work, geom=faces, context='FACES')
    before = set(work.faces)
    bmesh.ops.create_uvsphere(work, u_segments=64, v_segments=32,
                             radius=radius, matrix=Matrix.Translation((0, tip, 0)))
    for face in set(work.faces) - before:
        face.material_index = material_index
        face.smooth = True
    material = mesh.materials[material_index]
    tree = material.node_tree
    geometry = tree.nodes.new('ShaderNodeNewGeometry')
    transform = tree.nodes.new('ShaderNodeVectorTransform')
    transform.vector_type = 'NORMAL'
    transform.convert_from = 'WORLD'
    transform.convert_to = 'CAMERA'
    tree.links.new(geometry.outputs['Normal'], transform.inputs['Vector'])
    scale = tree.nodes.new('ShaderNodeVectorMath')
    scale.operation = 'SCALE'
    scale.inputs['Scale'].default_value = .5
    tree.links.new(transform.outputs['Vector'], scale.inputs[0])
    offset = tree.nodes.new('ShaderNodeVectorMath')
    offset.operation = 'ADD'
    offset.inputs[1].default_value = (.5, .5, 0)
    tree.links.new(scale.outputs['Vector'], offset.inputs[0])
    texture = tree.nodes.get('Diffuse')
    tree.links.new(offset.outputs['Vector'], texture.inputs['Vector'])
    # Sample the original circular artwork across the visible hemisphere;
    # suppress its rear surface so translucent layers are not doubled.
    front = tree.nodes.new('ShaderNodeMath')
    front.operation = 'SUBTRACT'
    front.inputs[0].default_value = 1
    tree.links.new(geometry.outputs['Backfacing'], front.inputs[1])
    alpha = tree.nodes.new('ShaderNodeMath')
    alpha.operation = 'MULTIPLY'
    tree.links.new(front.outputs[0], alpha.inputs[0])
    tree.links.new(texture.outputs['Alpha'], alpha.inputs[1])
    tree.links.new(alpha.outputs[0], tree.nodes.get('Principled BSDF').inputs['Alpha'])
    material.surface_render_method = 'BLENDED'
# Trim only the galaxy card's transparent corners behind the shell. Bisect
# interpolates native UVs, leaving the interior galaxy artwork undistorted.
shell_radius = max(abs(v.co.x) for f in work.faces if f.material_index == 8 for v in f.verts)
for step in range(64):
    angle = math.tau * step / 64
    normal = (math.cos(angle), 0, math.sin(angle))
    faces = [f for f in work.faces if f.material_index == 3]
    edges = {e for f in faces for e in f.edges}
    vertices = {v for f in faces for v in f.verts}
    radius = shell_radius * .995
    bmesh.ops.bisect_plane(work, geom=list(vertices) + list(edges) + faces,
                          dist=1e-7, plane_co=(normal[0] * radius, tip, normal[2] * radius),
                          plane_no=normal, clear_outer=True, clear_inner=False)
work.to_mesh(mesh)
work.free()
mesh.update()
mesh.name = 'BASE_TOYCORE'
mesh['bbe_toycore_assembly'] = 'native-spherical-effects-20261105'
# These layered native cards are intentional. The generic duplicate-face
# cleanup would remove hundreds of their faces on append.
mesh['bbe_duplicate_faces_prepared'] = 1

obj = bpy.data.objects.new('BASE_TOYCORE', mesh)
bpy.context.collection.objects.link(obj)
bpy.context.preferences.filepaths.save_version = 0
output.parent.mkdir(parents=True, exist_ok=True)
bpy.ops.wm.save_as_mainfile(filepath=str(output), check_existing=False)
print('TOYCORE_NATIVE_CORRECTION', str(output),
      'tip', round(tip, 5), 'vertices', len(mesh.vertices),
      'faces', len(mesh.polygons), flush=True)
