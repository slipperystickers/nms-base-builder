"""Convenient methods to perform common blender related tasks."""

import math

import addon_utils
import bmesh
import bpy


def load_plugin(plugin_name):
    """Load a blender plugin."""
    is_enabled, _ = addon_utils.check(plugin_name)
    if not is_enabled:
        addon_utils.enable(plugin_name)


def add_to_scene(item, collection_name="Collection"):
    """Add an item to the main blender collection.

    A Collection is a concept introduced in Blender 2.8. Which can be seen
    as a group/scene of items.

    By default we should add all new items to the default "Collection".

    Args:
        item (bpy_types.Object): The blender object.
        collection_name(str): The name of the collection to place the item in.
    """
    if collection_name == "Collection":
        station_parts = next((c for c in bpy.context.scene.collection.children
                              if c.get("nms_station_player_parts")), None)
        if station_parts is not None:
            collection_name = station_parts.name
    from .collection_utils import get_collection
    # Another scene may already own this name after clearing the current build.
    object_set = get_collection(collection_name).objects
    if item.name not in object_set:
        object_set.link(item)


def get_item_by_name(item_name):
    """Get a Blender object by specifying the name of the object.

    Args:
        item_name (str): The name of the item.

    Returns:
        bpy_types.Object: The Blender object.
    """
    return bpy.data.objects[item_name]


def item_exists_by_name(item_name):
    """Check for a Blender object by specifying the name of the object.

    Args:
        item_name (str): The name of the item.

    Returns:
        bool: True iff object exists.
    """
    return item_name in bpy.data.objects


def remove_object(name):
    """Remove an item from the scene by specifying it's name.

    Args:
        name (str): The name of the object to remove.
    """
    objs = bpy.data.objects
    if name in objs:
        objs.remove(objs[name], do_unlink=True)


# Force refresh of scene so the matrix values are correct.
def scene_refresh():
    """Force the dependency graph to update.

    This is sometimes required when adding and removing constraints on
    certain objects.
    """
    layer = bpy.context.view_layer
    layer.update()


def set_active_item(item):
    """Set the item to be the active item.

    This is similar to the selected state.

    Args:
        item (bpy_types.Object): The item to set as active.
    """
    bpy.context.view_layer.objects.active = item


def deselect_all():
    """Clear the selection without going through bpy.ops."""
    for item in list(bpy.context.selected_objects):
        item.select_set(False)


def select(selection, add=False):
    """Select an item.

    The add flag determines if the item is appended to the current selection
    or if we should only select that particular item.

    Args:
        selection (bpy_types.Object, list): The item to be selected.
            This can be a singular object or a list of objects.
        add (bool): Appends the selection if `True` else select by itself.
    """
    # Deselect all.
    if not add:
        # By hand rather than bpy.ops.object.select_all(action="DESELECT"):
        # the operator walks the whole scene and pushes an undo step, which
        # costs about 150 ms on a big base against 0.01 ms for this, and it
        # needs Object mode to poll where select_set() does not.
        deselect_all()
        set_active_item(None)

    # Ensure List.
    if not isinstance(selection, list):
        selection = [selection]

    for item in selection:
        # Check if item exists in the active view layer before selecting
        if item is not None and item.name in bpy.context.view_layer.objects:
            item.select_set(True)

    # Make the last item the active one (only if valid)
    if selection and selection[-1] is not None:
        if selection[-1].name in bpy.context.view_layer.objects:
            selection[-1].select_set(True)
            set_active_item(selection[-1])

    # The select_all operator this used to call flushed the depsgraph on its way
    # through, and callers came to rely on that - move an object, select it, and
    # its matrix_world was current by the time anything read it. select_set()
    # does not flush, so do it here. It costs nothing when nothing is dirty.
    scene_refresh()


def get_current_selection():
    """Get the current selected item.

    Returns:
        bpy_types.Object: The selected item.
    """
    selected_objects = [o for o in bpy.context.scene.objects if o.select_get()]
    if selected_objects:
        return selected_objects[-1]


def get_distance_between(matrix1, matrix2):
    """Get the distance between two matrices.

    Args:
        matrix1: First matrix input.
        matrix2: Second matrix input.

    Returns:
        float: The distance between the two.
    """
    translate1 = matrix1.decompose()[0]
    translate2 = matrix2.decompose()[0]
    return math.sqrt(
        (translate2.x - translate1.x) ** 2
        + (translate2.y - translate1.y) ** 2
        + (translate2.z - translate1.z) ** 2
    )


def delete(bpy_object):
    """Remove the item and everything below it."""
    # Deselect all
    #bpy.ops.object.select_all(action="DESELECT")

    # Parent items to control.
    for part in bpy_object.children:
        bpy.data.objects.remove(part, do_unlink=True)

    bpy.data.objects.remove(bpy_object, do_unlink=True)
    
    
# Two faces count as facing the same way when their normals agree at least
# this closely. Well above anything a rounding difference produces, and well
# below the angle a genuine back face sits at.
FACING_TOLERANCE = 0.9


def remove_duplicate_faces(mesh, precision=5):
    """Drop faces that sit exactly on top of another face pointing the same way.

    A lot of the models-high-res library was built by joining two source meshes
    without merging where they overlapped - T_WALL_Q_H1 ships 76 such pairs,
    B_WNG_B nearly 20,000. Two faces at the same depth are a coin flip for a ray
    tracer, and because the duplicates carry their own custom split normals the
    losing pick shades black: the part renders with black patches in Cycles
    while the viewport and EEVEE, whose rasteriser breaks the tie consistently,
    look perfectly fine.

    Only exact duplicates go: the same set of vertex positions AND facing the
    same way. Faces that coincide but point in opposite directions are how
    decals, holograms, foliage and glass are modelled all through the library -
    BLD_PLANET_HOLO is 16,848 of them against 96 real duplicates - and those
    have to survive untouched.

    Positions rather than vertex indices, because the joined halves bring their
    own vertices: the duplicated faces in T_WALL_Q_H1 sit on 820 coincident but
    separate vertices, so nothing about the indices gives the overlap away.

    Args:
        mesh (bpy.types.Mesh): The mesh to clean, edited in place.
        precision (int): Decimal places a position is compared at.

    Returns:
        int: How many faces were removed.
    """
    polygon_count = len(mesh.polygons)
    if polygon_count < 2:
        return 0

    import numpy as np

    # Compare packed rows in bulk. Quantize each vertex once, even when it is
    # shared by many faces. Float64 preserves the old Python multiplication
    # and truncation, including coordinates beyond the int64 range.
    coords = np.empty((len(mesh.vertices), 3), dtype=np.float32)
    mesh.vertices.foreach_get("co", coords.ravel())
    positions = np.trunc(coords.astype(np.float64) * (10 ** precision))
    positions[positions == 0] = 0.0  # canonicalize signed zero for byte comparison

    def row_keys(rows):
        return rows.view(np.dtype((np.void, rows.strides[0]))).ravel()

    _, vertex_ids = np.unique(row_keys(positions), return_inverse=True)
    loop_starts = np.empty(polygon_count, dtype=np.int32)
    mesh.polygons.foreach_get("loop_start", loop_starts)
    loop_totals = np.empty_like(loop_starts)
    mesh.polygons.foreach_get("loop_total", loop_totals)
    loop_vertices = np.empty(len(mesh.loops), dtype=np.int32)
    mesh.loops.foreach_get("vertex_index", loop_vertices)
    loop_ids = vertex_ids.ravel()[loop_vertices]
    normals = None
    doomed = []
    for size in np.unique(loop_totals):
        faces = np.flatnonzero(loop_totals == size)
        if len(faces) < 2:
            continue
        corners = loop_starts[faces, None] + np.arange(size)
        keys = row_keys(np.sort(loop_ids[corners], axis=1))
        _, groups, counts = np.unique(keys, return_inverse=True, return_counts=True)
        groups = groups.ravel()
        repeated = np.flatnonzero(counts[groups] > 1)
        if not len(repeated):
            continue
        if normals is None:
            values = np.empty((polygon_count, 3), dtype=np.float32)
            mesh.polygons.foreach_get("normal", values.ravel())
            normals = values.astype(np.float64)
        kept_normals = {}
        for index in repeated:
            face = int(faces[index])
            kept = kept_normals.setdefault(groups[index], [])
            normal = normals[face]
            if any(normal @ other > FACING_TOLERANCE for other in kept):
                doomed.append(face)
            else:
                kept.append(normal)

    if not doomed:
        return 0

    bm = bmesh.new()
    bm.from_mesh(mesh)
    bm.faces.ensure_lookup_table()
    # 'FACES' takes the vertices and edges left behind with them, so the
    # duplicated halves stop costing memory as well as rendering wrong
    bmesh.ops.delete(bm, geom=[bm.faces[i] for i in sorted(doomed)], context='FACES')
    bm.to_mesh(mesh)
    bm.free()

    return len(doomed)


def find_duplicates(decimals = 4):
    """
    Removes duplicate objects based on:
        - name
        - world location
        - world rotation
        - world scale

    Keeps the first found object unselected and select subsequent duplicates.
    """

    seen_objects = {}
    duplicates = []

    for obj in bpy.context.view_layer.objects:
        location_vector, rotation_quaternion, scale_vector = obj.matrix_world.decompose()
        
        location = (
            round(location_vector.x,decimals),
            round(location_vector.y,decimals),
            round(location_vector.z,decimals)
        )
        
        rotation_euler = rotation_quaternion.to_euler("XYZ")
        rotation = (
            round(rotation_euler.x, decimals),
            round(rotation_euler.y, decimals),
            round(rotation_euler.z, decimals)
        )
        
        scale = round(scale_vector.x, decimals)
        object_key = (
            obj.get("ObjectID",obj.name),
            location,
            rotation,
            scale,
        )
        
        if object_key in seen_objects:
            duplicates.append(obj.get("object", obj))
        else:
            seen_objects[object_key] = obj

    # select duplicates
    for obj in duplicates:
            select(duplicates)

    print(f"Selected {len(duplicates)} duplicate objects")
    return len(duplicates)

def duplicate_part(target):
    """ Duplicate an object and place it in same collection as original object
        Return duplicated object
    """
    new_item = target.copy()
    if new_item.data:
        new_item.data = target.data.copy()
    for collection in target.users_collection:
        collection.objects.link(new_item)
    return new_item

def parent_objects(parent, children):
    """
    Parent one or more objects to a parent object without moving them.
    Args:
        parent (bpy.types.Object):
            The parent object.
        children (bpy.types.Object | Iterable[bpy.types.Object]):
            A single object or a list of objects to parent.
    """

    # Allow a single object to be passed.
    if isinstance(children, bpy.types.Object):
        children = [children]

    for child in children:

        # Skip the parent itself.
        if child == parent:
            continue

        # Save the current world transform.
        world_matrix = child.matrix_world.copy()

        # Set the parent.
        child.parent = parent

        # Keep the child in the same position.
        child.matrix_parent_inverse = parent.matrix_world.inverted()
        child.matrix_world = world_matrix
        
def unparent_objects(parent):
    """
    Unparent all direct children of an object without moving them.
    Args:
        parent (bpy.types.Object): The parent object.
    Returns:
        list[bpy.types.Object]: A list of the objects that were unparented.
    """
    # Force evaluation of children into a static list.
    # Otherwise, modifying child.parent alters parent.children mid-loop!
    children_list = list(parent.children)

    for child in parent.children:
        # Save the current world transform so it doesn't jump
        world_matrix = child.matrix_world.copy()

        # Clear the parent
        child.parent = None

        # Reapply the world transform in global space
        child.matrix_world = world_matrix

    return children_list
        
def change_object_visibility(objects, is_visibe = False):
    """
    Hide or show one or more objects in the viewport and renders.

    Args:
        objects (bpy.types.Object | Iterable[bpy.types.Object]):
            A single object or a list of objects.

        hide (bool):
            True to hide the objects, False to show them.
    """

    # Allow a single object to be passed.
    if isinstance(objects, bpy.types.Object):
        objects = [objects]

    for obj in objects:
        obj.hide_set(not is_visibe)      # Hide in viewport
        obj.hide_render = not is_visibe  # Hide in renders
        
def _needs_operator_join(objects):
    """True when an object carries something a bmesh merge would quietly drop.

    Vertex groups and shape keys live on the object rather than in the mesh's
    vertex data, and an object-linked material slot is not on the mesh at all.
    This is not hypothetical - a handful of the rigged parts (SHIPARMS,
    GARAGE_L) really do have vertex groups - so those go the long way round,
    which is slower but is exactly what the plugin always did.

    Args:
        objects (list[bpy.types.Object]): The objects about to be merged.

    Returns:
        bool: True to use the operator path.
    """
    for obj in objects:
        if obj.vertex_groups or obj.data.shape_keys:
            return True
        for slot in obj.material_slots:
            if slot.link != 'DATA':
                return True
    return False


def _select_only(item):
    """Leave `item` as the sole selection, the way bpy.ops.object.join() did."""
    deselect_all()
    view_layer = bpy.context.view_layer
    if item.name in view_layer.objects:
        item.select_set(True)
        view_layer.objects.active = item


# Above roughly this much geometry the operator wins again - it carries a fixed
# cost of about 360 ms on a 5000 object scene but then scales better than
# bmesh's mesh-to-mesh round trip. Measured on a 5000 part base:
#
#     verts      operator     bmesh
#      2 336      368 ms       9 ms
#     20 407      361 ms      39 ms
#     71 235      418 ms     147 ms
#    105 294      496 ms     428 ms      <- they meet about here
#    137 072      579 ms     809 ms
#    290 054      800 ms   1 738 ms
BMESH_MERGE_VERT_LIMIT = 110000


def _merge_objects_with_bmesh(objects, object_name):
    """Join the meshes directly, without going through bpy.ops.

    The operator route costs about 360 ms on a 5000 part base almost regardless
    of how much geometry is involved - the cost is scene-sized, not mesh-sized,
    because select_all, duplicate and join each walk the whole scene. Building
    the mesh here does the same work in 9 ms for two parts.

    The result is the same object: same vertex order, same materials in the same
    slot order, same UVs, sharp edges, seams and custom split normals, and the
    same world matrix - the first object's, which is where bpy.ops.object.join()
    leaves the origin.

    Each mesh is copied and moved with Mesh.transform rather than by walking its
    vertices here. That is not just faster, it is the only version that is
    correct: custom split normals have to be rotated along with the geometry,
    and a python loop over vertex coordinates leaves them pointing the old way.

    Args:
        objects (list[bpy.types.Object]): Mesh objects to merge, first one wins
            the origin.
        object_name (str): Name for the merged object.

    Returns:
        bpy.types.Object
    """
    base = objects[0]
    base_inverse = base.matrix_world.inverted()

    # slots are pooled by material across every object, in first seen order
    materials = []
    material_indices = {}

    bm = bmesh.new()
    for obj in objects:
        slot_map = []
        for slot in obj.material_slots:
            material = slot.material
            if material is None:
                slot_map.append(0)
                continue
            index = material_indices.get(material.name)
            if index is None:
                index = len(materials)
                material_indices[material.name] = index
                materials.append(material)
            slot_map.append(index)

        needs_remap = slot_map != list(range(len(slot_map)))

        if obj is base and not needs_remap:
            # the first object is already in the space we are building in, and
            # its slots are the ones everything else is being mapped onto, so
            # there is nothing to change and no copy to make
            bm.from_mesh(obj.data)
            continue

        # bring this object's geometry into the first object's local space,
        # which is the space join() leaves everything in
        mesh_copy = obj.data.copy()
        if obj is not base:
            mesh_copy.transform(base_inverse @ obj.matrix_world)

        # the faces still point at this object's own slots
        if needs_remap:
            last_slot = len(slot_map) - 1
            indices = [0] * len(mesh_copy.polygons)
            mesh_copy.polygons.foreach_get("material_index", indices)
            mesh_copy.polygons.foreach_set(
                "material_index",
                [slot_map[i if i <= last_slot else last_slot] for i in indices],
            )

        bm.from_mesh(mesh_copy)
        bpy.data.meshes.remove(mesh_copy)

    mesh = bpy.data.meshes.new(object_name)
    bm.to_mesh(mesh)
    bm.free()

    # join() keeps the active object's mesh datablock, custom properties and
    # all, and materials_v2 reads the nms_high_res_id marker off the mesh to
    # decide whether a group can still be recoloured - so carry them across
    for key, value in base.data.items():
        mesh[key] = value

    for material in materials:
        mesh.materials.append(material)

    merged = bpy.data.objects.new(object_name, mesh)
    for collection in base.users_collection:
        collection.objects.link(merged)
    merged.matrix_world = base.matrix_world.copy()
    return merged


def _merge_objects_with_operator(objects, object_name):
    """The original bpy.ops route, kept for whatever the fast path cannot do."""
    context = bpy.context
    view_layer = context.view_layer

    bpy.ops.object.select_all(action='DESELECT')

    for obj in objects:
        obj.select_set(True)

    view_layer.objects.active = objects[0]

    # Duplicate and join. duplicate() leaves the copy of the active object
    # active, which is what we want to join into - this used to re-point active
    # at selected_objects[0] instead, and that list comes back in view layer
    # order rather than selection order, so the merged object's origin landed on
    # whichever part happened to sort first.
    meshes_before = set(bpy.data.meshes)
    bpy.ops.object.duplicate(linked=False)
    bpy.ops.object.join()

    merged = view_layer.objects.active
    merged.name = object_name

    # duplicate(linked=False) copies a mesh per object and join() keeps only
    # the active one's, so every other copy is left in the file with nothing
    # pointing at it. They are full copies of high res parts, so a handful of
    # groups is hundreds of megabytes of them - and until now they sat there
    # for the rest of the session, piling up another set every time a group was
    # rebuilt.
    orphans = [
        mesh for mesh in bpy.data.meshes
        if mesh.users == 0 and mesh not in meshes_before
    ]
    if orphans:
        bpy.data.batch_remove(orphans)

    # delete unnecessary custom properties
    for key in list(merged.keys()):
        del merged[key]

    return merged


def merge_objects(objects, object_name):
    """
    Using Blender's APIs merge the given mesh objects into a new object while leaving the originals
    untouched.

    Parameters:
        objects (list[bpy.types.Object]): Objects to merge.
        object_name (str): Name of the merged object.

    Returns:
        bpy.types.Object | None
    """

    # Filter mesh objects
    objects = [obj for obj in objects if obj and obj.type == 'MESH']

    if not objects:
        print("No objects to merge")
        return None

    try:
        total_verts = sum(len(obj.data.vertices) for obj in objects)
        if _needs_operator_join(objects) or total_verts > BMESH_MERGE_VERT_LIMIT:
            merged = _merge_objects_with_operator(objects, object_name)
        else:
            merged = _merge_objects_with_bmesh(objects, object_name)

        # Force Blender to update the viewport and geometry cache
        merged.data.update()
        _select_only(merged)
        print("Group created : ", merged.name)
        return merged

    except Exception as error:
        print("Error Occured while grouping objects : ", str(error))
        return None 
