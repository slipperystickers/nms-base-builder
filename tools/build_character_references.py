"""Build gray intermediate standing/seated dummy libraries and thumbnails.

Run with factory-startup background Blender, passing --research-root after --.
Requires extracted native sources and the full native skin assets. Existing
pilot libraries and user Blender projects are read only.
Use rebuild_coloured_characters.py for a release-ready coloured rebuild.
"""
from pathlib import Path
import argparse
import copy
import json
import math
import shutil
import sys
import bpy
import numpy as np
from mathutils import Vector

parser = argparse.ArgumentParser()
parser.add_argument('--research-root', type=Path, required=True)
args = parser.parse_args(sys.argv[sys.argv.index('--')+1:])
assert bpy.app.background
ROOT = args.research_root.resolve()
ADDON = Path(__file__).resolve().parents[1]/'src/addons/no_mans_sky_base_builder'
LIGHT = ADDON/'resources/character_references'
DETAIL = ADDON/'resources/hd_additions/character_references'
ICONS = ADDON/'images/asset_icons'
for folder in (LIGHT, DETAIL, DETAIL/'textures', ICONS):
    folder.mkdir(parents=True, exist_ok=True)
sys.path.insert(0, str(ADDON/'pilot_math'))
from skinning import skin, blender_coordinates
source = ROOT/'build_seated_references.py'
ns = {'__file__': str(source)}
source_text = source.read_text()
exec(compile(source_text.split("bpy.ops.object.select_all(action='SELECT')", 1)[0], str(source), 'exec'), ns)
standing_source = source_text[source_text.index('def pose('):source_text.index('\ndef chosen(')]
standing_source = standing_source.replace('def pose(', 'def standing_pose(')
standing_source = standing_source.replace("filename='cockpit_sit_loop'+('_gek' if gek else '')+'.anim.MXML'",
                                        "filename='idles/0h_idle_weight_shift_heads.anim.MXML'")
standing_source = standing_source.replace("P/'anims/interaction/cockpit'/filename", "P/'anims'/filename")
exec(compile(standing_source, str(source), 'exec'), ns)
armoured = copy.deepcopy(ns['preset_map']['ASTRO_DEFAULT'])
desc = ns['prop'](armoured, 'DescriptorGroups'); desc[:] = []
for group in ('ASTRONAUT_BASE','HEAD_SWARM','TORSO_SWARM','ARMOUR_DIVING','GLOVES_SWARM',
              'LEGS_DIVING','BOOTS_DIVING','BACKPACK_ATLAS','CAPE_NULL'):
    ns['E'].SubElement(desc, 'Property', {'value': group})
ns['preset_map']['ASTRO_ARMOURED'] = armoured
RACES = [('ASTRO_DEFAULT','Anomaly',(.22,.43,.6)), ('GEK_DEFAULT','Gek',(.45,.57,.23)),
         ('KORVAX_DEFAULT','Korvax',(.55,.35,.15)), ('VYKEEN_DEFAULT',"Vy'keen",(.5,.25,.16)),
         ('FOURTH_DEFAULT','Traveller',(.4,.25,.55)), ('BUI_DEFAULT','Autophage',(.35,.4,.45)),
         ('ASTRO_ARMOURED','Armoured Anomaly',(.32,.38,.45))]


def clear_scene():
    for obj in list(bpy.context.scene.objects):
        bpy.data.objects.remove(obj, do_unlink=True)


def thumbnail(obj, destination):
    scene = bpy.context.scene
    scene.render.engine = 'BLENDER_WORKBENCH'
    scene.render.resolution_x = scene.render.resolution_y = 256
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = 'PNG'
    scene.render.film_transparent = True
    scene.display.shading.light = 'STUDIO'
    scene.display.shading.color_type = 'MATERIAL'
    scene.display.shading.show_shadows = True
    scene.display.shading.show_cavity = True
    scene.display.shading.cavity_type = 'BOTH'
    scene.display.shading.show_specular_highlight = True
    points = np.array([v.co[:] for v in obj.data.vertices])
    low, high = points.min(axis=0), points.max(axis=0)
    target = Vector((low+high)/2)
    cam = bpy.data.objects.new('Reference thumbnail camera', bpy.data.cameras.new('Reference thumbnail camera'))
    scene.collection.objects.link(cam)
    cam.location = target+Vector((3.6,6,2.2))
    cam.rotation_euler = (target-cam.location).to_track_quat('-Z','Y').to_euler()
    cam.data.type = 'ORTHO'
    cam.data.ortho_scale = max(2.15, float(np.max(high-low))*1.18)
    scene.camera = cam
    scene.render.filepath = str(destination)
    bpy.ops.render.render(write_still=True)
    bpy.data.objects.remove(cam, do_unlink=True)


clear_scene()
report = {'schema':'bbe_character_references_v1',
          'scope':'Fixed scale references; no cockpit locator, collision correction or game export identity.',
          'standing_source':'Player entity default 0H_IDLE_WEIGHT_SHIFT_HEADS, frame 0, appearance morphs applied.',
          'grounding':'Translate mesh vertically by minus its lowest visible vertex; retain native horizontal origin and scale.',
          'models':[]}
for race, label, colour in RACES:
    path = ADDON/'resources/hd_additions/pilot_references'/f'{race}.skin.npz'
    with np.load(path, allow_pickle=False) as loaded:
        asset = {key:loaded[key] for key in loaded.files}
    standing_world, animation = ns['standing_pose'](race=='GEK_DEFAULT', race)
    standing_globals = np.array([np.array(standing_world[str(name)]).T for name in asset['names']])
    # Source skin joint-local points already contain the appearance scale;
    # apply the same scale to pose translations, never to rotation bases.
    standing_globals[:,3,:3] *= float(asset.get('appearance_scale', 1.0))
    standing_points = skin(asset, standing_globals)
    for pose in ('STANDING','SEATED'):
        clear_scene()
        library = ADDON/'resources/hd_additions/pilot_references'/f'{race}.blend'
        with bpy.data.libraries.load(str(library), link=False) as (src,dst):
            dst.objects = list(src.objects)
        objects = [obj for obj in dst.objects if obj and obj.type=='MESH']
        assert len(objects)==1, (race,len(objects))
        obj = objects[0]
        bpy.context.scene.collection.objects.link(obj)
        bpy.context.view_layer.objects.active = obj
        obj.select_set(True)
        mesh = obj.data
        points = np.empty(len(mesh.vertices)*3)
        mesh.vertices.foreach_get('co', points)
        points = points.reshape(-1,3)
        if pose=='STANDING':
            assert len(points)==len(standing_points), (race,len(points),len(standing_points))
            points = blender_coordinates(standing_points)
        raw_low, raw_high = points.min(axis=0), points.max(axis=0)
        ground_offset = -float(raw_low[2])
        points[:,2] += ground_offset
        mesh.vertices.foreach_set('co', points.reshape(-1))
        mesh.update()
        obj.location = obj.rotation_euler = (0,0,0)
        obj.scale = (1,1,1)
        obj.name = label+' — '+pose.title()+' Reference'
        mesh.name = obj.name
        for key in list(obj.keys()):
            del obj[key]
        for key in list(mesh.keys()):
            del mesh[key]
        obj['bbe_character_reference'] = True
        obj['bbe_character_race'] = race
        obj['bbe_character_pose'] = pose
        obj['reference_only'] = obj['excluded_from_nms_export'] = True
        obj['native_pose'] = animation if pose=='STANDING' else ('cockpit_sit_loop_gek' if race=='GEK_DEFAULT' else 'cockpit_sit_loop')
        obj['native_frame'] = 0
        obj['ground_offset_m'] = ground_offset
        for material in mesh.materials:
            if material and material.use_nodes:
                for node in material.node_tree.nodes:
                    image = getattr(node,'image',None)
                    if image is None:
                        continue
                    name = image.get('bbe_pilot_texture') or image.get('bbe_character_texture')
                    if name:
                        assert Path(name).name==name
                        source_texture = library.parent/'textures'/name
                        destination = DETAIL/'textures'/name
                        if not destination.is_file():
                            shutil.copy2(source_texture,destination)
                        image.pop('bbe_pilot_texture',None)
                        image['bbe_character_texture'] = name
                        image.filepath = '//textures/'+name
        filename = race+'_'+pose+'.blend'
        bpy.data.libraries.write(str(DETAIL/filename),{obj},fake_user=True,compress=True)
        full_vertices = len(mesh.vertices)
        full_triangles = sum(len(poly.vertices)-2 for poly in mesh.polygons)
        mesh.materials.clear()
        material = bpy.data.materials.new('Reference · '+label)
        material.diffuse_color = (*colour,1)
        material.use_nodes = True
        material.node_tree.nodes.get('Principled BSDF').inputs['Base Color'].default_value = (*colour,1)
        material.node_tree.nodes.get('Principled BSDF').inputs['Roughness'].default_value = .65
        mesh.materials.append(material)
        if full_triangles>12000:
            modifier = obj.modifiers.new('Lightweight reference','DECIMATE')
            modifier.ratio = 12000/full_triangles
            bpy.ops.object.modifier_apply(modifier=modifier.name)
        for poly in obj.data.polygons:
            poly.use_smooth = True
        bpy.data.libraries.write(str(LIGHT/filename),{obj},fake_user=True,compress=True)
        thumbnail(obj, ICONS/('BBE_CHARACTER_'+pose+'_'+race+'.png'))
        row = dict(race=race,pose=pose,native_animation=obj['native_pose'],frame=0,
                   raw_blender_bounds=[raw_low.tolist(),raw_high.tolist()],ground_offset_m=ground_offset,
                   detailed_vertices=full_vertices,detailed_triangles=full_triangles,
                   light_vertices=len(obj.data.vertices),light_triangles=sum(len(p.vertices)-2 for p in obj.data.polygons))
        if pose=='STANDING':
            row['raw_native_bounds'] = [standing_points.min(axis=0).tolist(),standing_points.max(axis=0).tolist()]
            row['native_y_extent_m'] = float(np.ptp(standing_points[:,1]))
        report['models'].append(row)
        (LIGHT/'manifest.json').write_text(json.dumps(report,indent=2))
        (DETAIL/'manifest.json').write_text(json.dumps(report,indent=2))
        print('CHARACTER_BUILT',race,pose,flush=True)
print('CHARACTER_REFERENCE_BUILD_COMPLETE',len(report['models']),flush=True)
