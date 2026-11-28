"""Resolve station-only material slots from the shared packed image library."""
import bpy


def attach(meshes, library):
    slots = [(mesh, i, mat, mat.get('bbe_station_slot')) for mesh in set(meshes)
             for i, mat in enumerate(mesh.materials) if mat and mat.get('bbe_station_slot')]
    keys = {key for _, _, _, key in slots}
    ready = {mat.get('bbe_station_surface_key'): mat for mat in bpy.data.materials
             if mat.get('bbe_station_surface_key') in keys}
    missing = sorted(keys - ready.keys())
    if missing:
        with bpy.data.libraries.load(str(library)) as (source, target):
            if set(missing).difference(source.materials):
                raise ValueError('The station surface library is incomplete')
            target.materials = list(missing)
        ready.update(zip(missing, target.materials))
    for mesh, i, _, key in slots:
        mesh.materials[i] = ready[key]
    for placeholder in {mat for _, _, mat, _ in slots}:
        if placeholder.users == 0:
            bpy.data.materials.remove(placeholder)
