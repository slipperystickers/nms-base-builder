"""Exercise scenery switching without rebuilding the ship's lighting rig."""
import sys
from pathlib import Path
from unittest.mock import patch

import bpy

sys.path.insert(0, str(Path(__file__).parent))
from test_support import module

stage = module('stages')
scene = bpy.context.scene
settings = scene.bbe_stage
original_world = scene.world
original_sampling = (scene.eevee.use_taa_reprojection, scene.eevee.shadow_ray_count, scene.eevee.ray_tracing_method)
settings.environment = 'SPACE'
settings.ship_lights = False
settings.enabled = True
assert settings.sun_object.data.type == "SUN"
with patch.object(stage.stage_effects, 'build', side_effect=AssertionError('rebuilt ship effects')):
    for cycle in range(2):
        for env in ('HANGAR', 'ORBITAL', 'OUTPOST', 'FROST', 'MESA', 'STATION', 'OUTPOST', 'SPACE'):
            settings.environment = env
            objects = [o for o in settings.collection.objects if o.get(stage.SCENERY)]
            expected = int(env in stage.PAD_FOR) + len(stage.LANDSCAPES.get(env, ()))
            assert len(objects) == expected, env
            assert all(o.hide_select and 'ObjectID' not in o for o in objects)
            for obj in objects:
                for mat in obj.data.materials:
                    if mat and mat.node_tree:
                        for node in mat.node_tree.nodes:
                            if node.type == 'TEX_IMAGE':
                                assert node.image and node.image.packed_file, (env, mat.name)
            assert settings.world.probe_resolution == ('128' if env == 'HANGAR' else settings.world.bl_rna.properties['probe_resolution'].default)
            if env == 'HANGAR':
                assert objects[0].data.name.startswith('Dock 5')
                assert not settings.world.node_tree.nodes.get('BBE Environment Panorama')
                mesh = objects[0].data
                assert len(mesh.polygons) < 100_000
                assert mesh.get('bbe_dock_revision') == 5
                # A magenta cuboid from the source station used to enclose this empty space.
                assert not objects[0].ray_cast((-150, 170, 100), (0, 0, -1))[0]
                assert mesh['station_reference'] == 'Native Type B / square launch tube'
                assert mesh.uv_layers.get('Native') and mesh.uv_layers.get('Dock tile scale')
                # The old distant LOD dropped these ribs. Rays crossed the
                # empty space and hit the outer hull at x=65 instead.
                for y in (-165, -405, -525):
                    hit, point, _, _ = objects[0].ray_cast((0, y, 10), (1, 0, 0))
                    assert hit and abs(point.x - 48.28) < .25, (y, point)
                for mat in mesh.materials:
                    assert mat.node_tree.nodes.get('Dock 5 cutaway')
                    sampler = next(n for n in mat.node_tree.nodes if n.type == 'TEX_IMAGE')
                    assert sampler.image.size[0] == 2048
                assert any(n.type == 'TEX_IMAGE' and tuple(n.image.size) == (2048, 4096)
                           for mat in mesh.materials for n in mat.node_tree.nodes)
                settings.glow = not settings.glow
                settings.ray_tracing = not settings.ray_tracing
                assert objects[0].data == mesh and settings.sun_object is None
                assert scene.eevee.use_raytracing == settings.ray_tracing
            if env == 'ORBITAL':
                image = settings.world.node_tree.nodes['BBE Environment Panorama'].image
                assert image.packed_file and image.size[0] >= 2048
                hub = next(o for o in objects if o.data.name.startswith('Orbital Concourse'))
                # Archived hub atlases also contained the opaque central glow cylinder.
                assert not hub.ray_cast((2, -19, -39), (0, 1, 0), distance=10)[0]
                assert not hub.ray_cast((-41.71, 63.64, 10), (0, 0, -1), distance=7)[0]
            lamps = [o for o in settings.collection.objects if o.get(stage.RIG_LIGHT)]
            if env in stage.STATION_LIGHTING:
                assert settings.sun_object is None
                assert len(lamps) == 5 and all(o.data.type == 'AREA' for o in lamps)
                assert len([o for o in lamps if o.location.z < 1]) == 4
                poses = [(o.location.copy(), o.rotation_euler.copy()) for o in lamps]
                settings.sun_azimuth += 1
                assert poses == [(o.location, o.rotation_euler) for o in lamps]
            elif env in ('OUTPOST', 'ORBITAL'):
                field = next(o for o in objects if 'uplight_positions' in o.data)
                assert field.data.uv_layers.active and field.data.get('outpost_revision') == 4
                assert [m.name.split('.')[0] for m in field.data.materials] == ['Outpost / Reflective decking', 'Outpost / Landing target']
                pad_mesh = next(o.data for o in objects if o.data.name.startswith('BBE Native Pad / Outpost'))
                used_slots = {f.material_index for f in pad_mesh.polygons}
                surfaces = {pad_mesh.materials[i].name.split(' / ')[-1].split('.')[0] for i in used_slots}
                assert 'SSRSHEET_MAT' in surfaces and surfaces.isdisjoint({'CONTACT', 'SCROLLINGCHEVRON1'})
                effects = next(o.data for o in objects if o.data.name.startswith('Outpost Projections'))
                for slot, material in enumerate(effects.materials):
                    nodes = material.node_tree.nodes
                    assert any(n.type == 'ADD_SHADER' for n in nodes) and any(n.type == 'BSDF_TRANSPARENT' for n in nodes)
                    gain = next(n for n in nodes if n.type == 'MATH' and n.operation == 'MULTIPLY')
                    mask = gain.inputs[0].links[0]
                    heights = [f.center.z for f in effects.polygons if f.material_index == slot]
                    if material.name.startswith('Outpost / Subsurface field'):
                        assert mask.from_socket.name == 'Alpha'
                        assert -.3 < min(heights) <= max(heights) < 0
                    else:
                        assert material.name.startswith('Outpost / Chevron glow') and -45 < min(heights) < -40 and -4 < max(heights) < -2
                        assert mask.from_node.operation == 'ABSOLUTE'
                        assert 0 < gain.inputs[1].default_value < .15
                        # Rounded, disconnected loops leave open sky between levels.
                        faces = [f for f in effects.polygons if f.material_index == slot]
                        assert all(f.use_smooth and len(f.vertices) == 4 for f in faces)
                        assert max(max(effects.vertices[v].co.z for v in f.vertices) -
                                   min(effects.vertices[v].co.z for v in f.vertices) for f in faces) < .15
                        assert min(f.normal.z for f in faces) < -.85 and max(f.normal.z for f in faces) > .85
                opacity = next(n.color_ramp for n in field.data.materials[0].node_tree.nodes if n.type == 'VALTORGB')
                assert max(stop.color[0] for stop in opacity.elements) < .5
                assert any(n.type == 'BSDF_TRANSPARENT' for n in field.data.materials[0].node_tree.nodes)
                marking_vertices = {v for face in field.data.polygons if face.material_index == 1 for v in face.vertices}
                assert marking_vertices and max(field.data.vertices[i].co.length for i in marking_vertices) < 9.3
                positions = list(field.data['uplight_positions'])
                uplights = [o for o in lamps if o.data.type == 'AREA']
                assert len(lamps) == 5 and settings.sun_object in lamps
                assert {tuple(o.location) for o in uplights} == {tuple(positions[i:i+3]) for i in range(0,12,3)}
                assert all(not o.data.use_shadow and o.data.energy > 0 for o in uplights)
            else:
                assert lamps == [settings.sun_object] and lamps[0].data.type == 'SUN'
                settings.sun_azimuth += 1
                assert settings.sun_object == lamps[0]
        counts = (len(bpy.data.meshes), len(bpy.data.materials), len(bpy.data.images))
        if cycle:
            assert counts == first_counts, (first_counts, counts)
        first_counts = counts
settings.environment = 'HANGAR'
dock = next(o for o in settings.collection.objects if o.get(stage.SCENERY))
stage.apply(scene, commit=True)
assert any(o == dock for o in settings.collection.objects)
for mode, method in (('EDIT', 'PROBE'), ('PHOTO', 'SCREEN')):
    settings.quality = mode
    assert not scene.eevee.use_taa_reprojection and scene.eevee.shadow_ray_count == 2
    assert scene.eevee.ray_tracing_method == method
settings.enabled = False
assert original_sampling == (scene.eevee.use_taa_reprojection, scene.eevee.shadow_ray_count, scene.eevee.ray_tracing_method)
assert not any(o.get(stage.TAG) for o in scene.objects)
assert scene.world == original_world
print('ENVIRONMENT SWITCH PASS', flush=True)
