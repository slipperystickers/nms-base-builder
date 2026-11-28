"""Assemble the station's selected native geometry in the player's build frame."""
import json
import re

import bpy
from mathutils import Matrix

from . import station_address
from . import station_reference as ref


def matching_rows(groups, selected):
    for required, rows in groups:
        if all(re.sub(r'LOD\d$', '', option) in selected for option in required):
            yield from rows


def assemble(context, seed):
    selected = station_address.descriptors(seed)
    family = next(label for key, label, _ in ref.FAMILIES if key.upper() in selected)
    tube = next(label for key, label, _ in ref.CORRIDORS if key.upper() in selected)
    layout = json.loads((ref.ASSETS / 'address_geometry.json').read_bytes())
    exterior = list(matching_rows(layout['outside'], selected))
    interior = list(matching_rows(layout['inside'], selected))
    if not exterior or not interior:
        raise ValueError('Station layout has no matching hull or interior')

    old_roots = [c for c in context.scene.collection.children if c.get(ref.TAG)]
    saved_eyes = {}
    for layer in context.view_layer.layer_collection.children:
        if layer.collection in old_roots and layer.collection.get('system_address') == str(seed):
            for child in layer.children:
                saved_eyes[child.name] = child.hide_viewport
                for section in child.children:
                    saved_eyes[section.name] = section.hide_viewport
    names = sorted({key for key, _ in exterior} | {key for _, key in interior})
    meshes = {}
    appended_names = []
    root = None
    try:
        with bpy.data.libraries.load(str(ref.ASSETS / 'station_address.blend')) as (source, target):
            if set(names).difference(source.meshes):
                raise ValueError('Station geometry library is incomplete')
            target.meshes = list(names)
        meshes = dict(zip(names, target.meshes))
        appended_names = [mesh.name for mesh in meshes.values() if mesh]
        from .station_surfaces import attach
        attach(meshes.values(), ref.ASSETS / "station_surfaces.blend")
        root = ref.collection('Station Reference', context.scene.collection)
        root['appearance_source'] = 'GalacticAddress'
        root['station_surface_version'] = 1
        root['system_address'] = str(seed)
        outside = ref.collection('Outside', root)
        inside = ref.collection('Inside', root)
        colours = dict(zip(('hull', 'accent'), station_address.hull_colours(seed)))
        for key, flat in exterior:
            role = layout['materials'][key]
            obj = ref.make_object(meshes[key], 'Station ' + role, outside)
            obj.matrix_world = Matrix((flat[:4], flat[4:8], flat[8:], (0, 0, 0, 1)))
            if role in colours:
                obj.color = colours[role]
        sections = {}
        for name, key in interior:
            if name not in sections:
                sections[name] = ref.collection(name, inside)
            obj = ref.make_object(meshes[key], name, sections[name])
            obj.color = colours['accent']

        context.view_layer.update()
        layer = next(c for c in context.view_layer.layer_collection.children if c.collection == root)
        inner = next(c for c in layer.children if c.collection == inside)
        inner.hide_viewport = saved_eyes.get('Inside', False)
        for section in inner.children:
            if section.collection == sections.get(ref.CUTS[0][0]):
                section.hide_viewport = True
                section.collection.hide_render = True
            label = next(key for key, value in sections.items() if value == section.collection)
            section.hide_viewport = saved_eyes.get(label, section.hide_viewport)
        outer = next(c for c in layer.children if c.collection == outside)
        outer.hide_viewport = saved_eyes.get('Outside', True)  # Keep the interior accessible, as in the manual reference.
    except Exception:
        if root:
            ref.remove_tree(root)
        # Appending a mesh can succeed even if building a later instance fails.
        for name in appended_names:
            mesh = bpy.data.meshes.get(name)
            if mesh and mesh.users == 0:
                bpy.data.meshes.remove(mesh)
        ref.cleanup_palette()
        raise

    for old in old_roots:
        ref.remove_tree(old)
    root.name = 'Station Reference'
    inside.name, outside.name = 'Inside', 'Outside'
    for name, section in sections.items():
        section.name = name
    return f'{family} hull · {tube} launch tube'
