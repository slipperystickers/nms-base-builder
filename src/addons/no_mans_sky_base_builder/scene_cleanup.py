"""Clear the current build without resetting Blender's workspace or other scenes."""
import bpy


def clear(scene):

    objects = list(scene.objects)
    pending = list(scene.collection.children)
    collections = set()
    while pending:
        collection = pending.pop()
        if collection in collections:
            continue
        collections.add(collection)
        pending.extend(collection.children)

    for obj in list(scene.collection.objects):
        scene.collection.objects.unlink(obj)
    for collection in list(scene.collection.children):
        scene.collection.children.unlink(collection)

    # Delete only now-unused containers from this scene. Collections shared
    # with other scenes, library assets or collection instances remain intact.
    while collections:
        unused = [c for c in collections if c.users == 0 and c.library is None]
        if not unused:
            break
        collections.difference_update(unused)
        bpy.data.batch_remove(ids=unused)
    remaining = set(objects)
    while remaining:
        unused = [obj for obj in remaining if obj.users == 0 and obj.library is None]
        if not unused:
            break
        remaining.difference_update(unused)
        bpy.data.batch_remove(ids=unused)

    # Keep a clean destination for manual building as well as the next import.
    from .utils.collection_utils import get_collection
    with bpy.context.temp_override(scene=scene):
        collection = get_collection('Collection')
    for view_layer in scene.view_layers:
        view_layer.active_layer_collection = view_layer.layer_collection.children[collection.name]

