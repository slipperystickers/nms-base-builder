import bpy
import os
import time
import mathutils
import math
from . import builder, preset
from .part import Part
from .utils import blend_utils, material, materials_v2, collection_utils
from .utils import variant_map
from .part_overrides import parts_override
from .utils import python as python_utils

BUILDER = builder.get_builder()

# This is to compensate blender's Z up axis.
X_ROT_90 = mathutils.Matrix.Rotation(math.radians(90.0), 4, "X")

# name of collection to import objects to
IMPORT_COLLECTION_NAME = "Collection"

FILE_PATH = os.path.dirname(os.path.realpath(__file__))

# The high resolution library. One .blend per object id, each holding exactly
# one mesh object with the real game materials and textures on it.
# Textures are referenced relatively from assets/ into textures/, so the whole
# models-high-res folder has to move as a unit.
HIGH_RES_PATH = os.path.join(FILE_PATH, "models-high-res", "assets")

# An earlier build of the library shipped some ids as several style variants,
# named <ID>__<STYLE>.blend, because two styles cannot live in one file without
# breaking the one-object-per-file rule. The current library is flat - one file
# per id, no suffixes - so nothing hits this any more, but it is kept so a
# styled file dropped into the folder still resolves instead of being ignored.
# Order of preference, chosen by matching each variant's bounding box against
# the fbx proxy: Builders won 16 of the 17 pairs tested, Exterior all 3 corvette
# cockpits. An id whose styles are all outside this list is left out of the
# index on purpose and falls back to the fbx proxy - that was the FRE_ROOM_*
# room kits, where no single piece is the room and picking one would be wrong.
STYLE_PRIORITY = ("Builders", "Exterior")

# Appended meshes are cached in bpy.data under this prefix so a second import in
# the same session (or after a reload) reuses them instead of touching the disk.
# The tag written alongside it is what marks a part as belonging to the new
# colour system - it lives in materials_v2 so the old material code can read it.
MESH_PREFIX = "NMS_HR_"
MESH_TAG = materials_v2.MESH_TAG

# These corrected assets must also replace caches embedded in older .blend
# scenes. Keep occupied old datablocks intact; a quality switch opts each
# placed object into the corrected mesh without touching its saved record.
MESH_REVISION_TAG = "nms_asset_revision"
MESH_REVISIONS = dict.fromkeys(
    ("B_HAB_A", "B_HAB_B", "B_HAB_C", "B_HAB1_A", "B_HAB1_B", "B_HAB1_C", "B_ALK_C"),
    "18.0.9",
)

# Set once per session by get_asset_index().
_asset_index = None


# An optimised way to import objects,
# First exclude view layer from outliner
# then share as much data as possible between the objects we create
#
# Parts that come from the high res library share ONE mesh datablock (and with
# it one set of materials) across every placement of that object id, whatever
# their UserData, because colour lives on the object as four custom properties
# rather than on the material - see utils/materials_v2.py.
# Parts that still fall back to an fbx proxy keep the old behaviour, where the
# mesh has to be copied per (ObjectID, UserData) pair because the colour is
# baked into a flat material.
def deserialise_from_data(data):

    if data is None:
        return

    # High res meshes, keyed by object id. Shared by every placement.
    unique_meshes = {}
    # Fbx fallback objects and their per (object id, user data) mesh copies.
    unique_objects = {}
    unique_materials = {}
    # (object, user data) pairs to colour in one pass at the end.
    to_colour = []
    order = 0

    # Use these only an object requires special steps to be imported
    classes_dict = parts_override.get_override_classes()
    asset_index = get_asset_index()

    # exclude view layer from blender
    # so that importing and updating scene with new objects doesnt get reflected
    # immediately after each disk I/O or object creation
    import_collection = collection_utils.get_collection(IMPORT_COLLECTION_NAME)
    collection_utils.set_collection_visibility(import_collection.name, visible=False)

    # wrapped so a bad part can never leave the collection excluded from the
    # outliner - that would look like the import silently did nothing
    try:
        # local lookups, this loop runs once per placed part
        link_object = import_collection.objects.link
        new_object = bpy.data.objects.new

        objects_data = data.get("Objects", [])
        for order, part_data in enumerate(objects_data):
            raw_object_id = part_data.get(Part.PROP_OBJECT_ID, None)
            if raw_object_id is None:
                continue

            object_id = raw_object_id.replace("^", "")
            user_data = part_data.get(Part.PROP_USER_DATA, 0)

            # use override classes only when needed, these are left untouched
            if object_id in classes_dict and not getattr(classes_dict[object_id], "HIGH_RES_COMPATIBLE", False):
                use_class = classes_dict[object_id]
                imported_part = use_class.deserialise_from_data(
                    part_data, BUILDER, compensate_normal=True
                )
                imported_part.object[Part.PROP_ORDER] = order
                continue

            # import object_id from disk when visiting it first time
            if object_id not in unique_meshes:
                unique_meshes[object_id] = load_high_res_mesh(object_id, asset_index)
            high_res_mesh = unique_meshes[object_id]

            if high_res_mesh is not None:
                # a plain new object over the cached mesh - no copy, no ops,
                # and every instance of this id points at the same mesh
                bpy_object = new_object(object_id, high_res_mesh)
                link_object(bpy_object)
                to_colour.append((bpy_object, user_data))
            else:
                bpy_object = build_fbx_part(
                    object_id,
                    user_data,
                    import_collection,
                    unique_objects,
                    unique_materials,
                )
                if bpy_object is None:
                    continue

            # restore matrix world
            restore_params(bpy_object, part_data, object_id)
            bpy_object.matrix_world = deserialise_matrix_world(part_data)

            # provide order
            bpy_object[Part.PROP_ORDER] = order

        # colour every high res part in one pass, so each distinct UserData is
        materials_v2.apply_many(to_colour)
        materials_v2.dedupe_appended_data()
        # dedupe so the shared materials are the ones that get the nodes,
        materials_v2.ensure_finish_nodes()
        materials_v2.use_object_colour_in_viewport()

    finally:
        # include import collection to outliner and update view layer
        collection_utils.set_collection_visibility(import_collection.name, visible=True)
        bpy.context.view_layer.update()

    # Reconstruct presets.
    for preset_data in data.get("Presets", []):
        preset.Preset.deserialise_from_data(
            preset_data, BUILDER, compensate_normal=True
        )

    # Build Rigs.
    BUILDER.build_rigs()
    # Optimise control points.
    BUILDER.optimise_control_points()


def add_part(
    object_id, user_data=None, build_rigs=True, high_res=True, builder_object=None
):
    """Add a single part, the way the asset browser and the build tools do it.

    A drop in replacement for builder.Builder.add_part - it hands back the same
    Part wrapper, so .object, .select(), .snap_to() and .build_rig() all still
    work on the result.

    Args:
        object_id (str): The part to build.
        user_data: The packed UserData value, or None for the part default.
        build_rigs (bool): Passed through to the part class.
        high_res (bool): True to place the models-high-res asset when the id
            has one, False to always place the old fbx proxy instead.
        builder_object (Builder): The builder whose part cache this belongs in.
            Defaults to this module's. Pass the caller's own instance to keep
            its cache the one that gets filled.

    Returns:
        Part: The new part, or whatever the old builder returns for it.
    """
    object_id = object_id.replace("^", "")
    builder_object = builder_object or BUILDER

    # matched before the part exists, same as the old builder, so a new part
    # lands on whatever was selected rather than on itself
    active_object = bpy.context.active_object
    placement_matrix = (active_object.matrix_world.copy()
                        if active_object is not None and active_object.select_get() else None)

    # Use these only when an object requires special steps to be imported.
    # Same override table deserialise_from_data reads, so a part built here and
    # the same part loaded from a save come out of the same class. Checked
    # first, because these parts need their class whether or not the caller
    # asked for the high res library.
    classes_dict = parts_override.get_override_classes()
    if object_id in classes_dict and not getattr(classes_dict[object_id], "HIGH_RES_COMPATIBLE", False):
        use_class = classes_dict[object_id]
        item = use_class(
            object_id=object_id,
            builder_object=builder_object,
            user_data=user_data,
            build_rigs=build_rigs,
        )
        if placement_matrix is not None:
            item.object.matrix_world = placement_matrix
        return item

    # with high_res off the caller is explicitly asking for the old proxy, which
    # is the old builder's job - it behaves exactly as it always has
    if not high_res:
        return builder_object.add_part(
            object_id, user_data=user_data, build_rigs=build_rigs
        )

    # ids the high res library doesn't cover fall back to the proxy too
    bpy_object = new_high_res_object(object_id)
    if bpy_object is None:
        return builder_object.add_part(
            object_id, user_data=user_data, build_rigs=build_rigs
        )

    # the same properties Part sets when it builds one from scratch
    bpy_object.hide_select = False
    bpy_object[Part.PROP_OBJECT_ID] = object_id
    bpy_object[Part.PROP_SNAP_ID] = object_id
    bpy_object[Part.PROP_TIMESTAMP] = str(int(time.time()))
    bpy_object[Part.PROP_BELONGS_TO_PRESET] = Part.DEFAULT_BELONGS_TO_PRESET
    bpy_object[Part.PROP_ORDER] = len(bpy.data.objects)

    # colour by object property, so this placement goes on sharing the mesh
    if user_data is None:
        user_data = Part.DEFAULT_USER_DATA
    materials_v2.recolour_from_user_data([bpy_object], user_data)

    # if the asset was appended just now it brought its own copies of textures
    # and of the colourise node group with it. Cheap to call either way - with
    # nothing to collapse this is a scan of bpy.data.images and no more
    materials_v2.dedupe_appended_data()
    materials_v2.ensure_finish_nodes()

    # wrap it so callers get the interface they expect from builder.add_part
    use_class = classes_dict.get(object_id, Part)
    item = use_class(
        bpy_object=bpy_object, builder_object=builder_object, build_rigs=build_rigs
    )
    item.reset_transforms()

    if placement_matrix is not None:
        item.object.matrix_world = placement_matrix

    return item


# build the {object_id: blend file} lookup for the high res library, once
def get_asset_index(rebuild=False):
    global _asset_index

    if _asset_index is not None and not rebuild:
        return _asset_index

    _asset_index = {}
    if not os.path.isdir(HIGH_RES_PATH):
        return _asset_index

    # collect every candidate first, then resolve the styled ones, so the
    # answer doesn't depend on the order the folder happens to list in
    candidates = {}
    for filename in os.listdir(HIGH_RES_PATH):
        if not filename.endswith(".blend"):
            continue
        object_id, separator, style = filename[:-6].partition("__")
        candidates.setdefault(object_id, []).append(
            (style if separator else None, os.path.join(HIGH_RES_PATH, filename))
        )

    for object_id, styles in candidates.items():
        if len(styles) == 1 and styles[0][0] is None:
            _asset_index[object_id] = styles[0][1]
            continue

        # a multi style id is only usable if one of its styles is one we chose
        for preferred in STYLE_PRIORITY:
            for style, path in styles:
                if style == preferred:
                    _asset_index[object_id] = path
                    break
            if object_id in _asset_index:
                break

    return _asset_index


def new_high_res_object(object_id, asset_index=None):
    """Make a bare object over the shared high res mesh for an id.

    Everything the high res library places goes through here, including the
    fossil bones, which build their own object rather than going through
    add_part - see part_overrides/bone.py.

    No properties are set and nothing is coloured; that is the caller's job,
    because Part sets its own when it builds one and add_part sets them itself.

    Args:
        object_id (str): The part to build.
        asset_index (dict): Optional prebuilt index, to skip the lookup.

    Returns:
        bpy.types.Object: The new object, or None when the library doesn't
            cover the id, so the caller can fall back to the fbx proxy.
    """
    mesh = load_high_res_mesh(object_id, asset_index)
    if mesh is None:
        return None

    # a plain new object over the shared mesh - adding the tenth copy of a part
    # costs an object datablock and nothing else
    bpy_object = bpy.data.objects.new(object_id, mesh)
    blend_utils.add_to_scene(bpy_object)
    return bpy_object


# get the shared mesh datablock for an object id, appending it on first use
def load_high_res_mesh(object_id, asset_index=None):
    asset_index = asset_index if asset_index is not None else get_asset_index()

    # the cache lives in bpy.data rather than in a module level dict, so it
    # survives a new file, a module reload and a scene the user already saved
    mesh_name = MESH_PREFIX + object_id
    cached = bpy.data.meshes.get(mesh_name)
    revision = MESH_REVISIONS.get(object_id)
    if cached is not None and cached.get(MESH_TAG) == object_id:
        if revision is None or cached.get(MESH_REVISION_TAG) == revision:
            return cached
        cached.name = mesh_name + "_legacy"

    # A reproducible variant is built out of the mesh it is a variant of rather
    # than out of its own asset - most of the corvette variants ship the wrong
    # mesh, and the transform in objects_map.json is measured, so this is the
    # more trustworthy of the two. See utils/variant_map.py.
    if REBUILD_VARIANTS:
        mesh = rebuild_variant_mesh(object_id, asset_index)
        if mesh is not None:
            return mesh

    blend_path = asset_index.get(object_id)
    if blend_path is None:
        return None

    # every library file holds exactly one mesh object. We only want its mesh -
    # the object datablock is thrown away and each placement gets a fresh one
    with bpy.data.libraries.load(blend_path, link=False) as (source, target):
        target.objects = list(source.objects)

    mesh = None
    for appended_object in target.objects:
        if appended_object is None:
            continue
        if mesh is None and appended_object.type == "MESH":
            mesh = appended_object.data
        bpy.data.objects.remove(appended_object)

    if mesh is None:
        return None

    mesh.name = mesh_name
    mesh[MESH_TAG] = object_id
    if revision is not None:
        mesh[MESH_REVISION_TAG] = revision
    if CLEAN_DUPLICATE_FACES:
        blend_utils.remove_duplicate_faces(mesh)
    # The append brought this asset's own copies of its textures and of the
    # colourise node group with it. A caller inside a deferred block is not
    # going to call the collapse itself, so tell it there is now something to
    # collapse - see materials_v2.note_appended_data.
    materials_v2.note_appended_data()
    return mesh


# False places every id from its own asset again, the way the addon did before
# the variant map existed. Kept as a switch because it is the one thing to turn
# off if a rebuilt part ever looks worse than the asset it replaced.
REBUILD_VARIANTS = True

# Strip the doubled geometry a lot of the library ships with as each asset is
# appended - see blend_utils.remove_duplicate_faces for what it is and why it
# only shows up in Cycles. Done here rather than in the asset files because the
# library is generated: fixing the blends by hand would last until the next
# extraction run, and this also covers whatever is generated next. Runs once
# per part per session, on the shared mesh every placement then points at.
CLEAN_DUPLICATE_FACES = True


def rebuild_variant_mesh(object_id, asset_index=None):
    """Build a variant's mesh by transforming the mesh of its root part.

    Only reproducible variants come back with anything - for everything else
    this returns None and the caller loads the id's own asset as usual. The
    result is cached and tagged exactly like an appended mesh, so from here on
    it is shared across placements and picked up by the cache in
    load_high_res_mesh like any other.

    Args:
        object_id (str): The variant to build.
        asset_index (dict): Optional prebuilt index, to skip the lookup.

    Returns:
        bpy.types.Mesh: The rebuilt mesh, or None when the id is not a
            reproducible variant or its root has no asset to build from.
    """
    rebuild = variant_map.get_rebuild(object_id)
    if rebuild is None:
        return None

    root_id, matrix = rebuild
    # guards a map that ever names an id as its own root - the recursion below
    # would otherwise never reach an asset
    if root_id == object_id:
        return None

    root_mesh = load_high_res_mesh(root_id, asset_index)
    if root_mesh is None:
        return None

    # Materials come across with the copy as references, so the variant paints
    # from the root's and the palette properties still work.
    mesh = transformed_copy(root_mesh, matrix)
    mesh.name = MESH_PREFIX + object_id
    mesh[MESH_TAG] = object_id
    return mesh


def transformed_copy(mesh, matrix):
    """A copy of a mesh with a mesh space matrix baked into it.

    Always a copy - the mesh being read here is the shared datablock every
    placement of the root part is pointing at, and transforming that in place
    would move every one of them.

    Args:
        mesh (bpy.types.Mesh): The mesh to copy.
        matrix (mathutils.Matrix): 4x4, in the mesh's own space.

    Returns:
        bpy.types.Mesh: The new mesh. Unnamed and untagged - the caller owns
            both, because the two libraries name their caches differently.
    """
    copied = mesh.copy()
    copied.transform(matrix)

    # a mirrored transform turns the mesh inside out
    if matrix.to_3x3().determinant() < 0.0:
        copied.flip_normals()

    return copied


# The old fbx proxies, cached the way the high res meshes are - one base mesh
# per object id, appended once and kept in bpy.data under this prefix so a
# second pass over the same id in the same session never touches the disk.
#
# Unlike a high res mesh this one cannot be shared by the parts that use it: a
# proxy's colour is a flat material in slot 0, so a placement needs its own copy
# of the mesh per UserData. What the cache saves is the fbx import itself, which
# is by far the expensive half.
PROXY_MESH_PREFIX = "NMS_LR_"
PROXY_MESH_TAG = "nms_proxy_id"

# Written onto each per (ObjectID, UserData) copy taken off a base mesh, so a
# later pass can find the one it made last time instead of taking another. A
# scene switched back to high res leaves all of these with no users, and
# without this every switch back down would copy a whole fresh set.
PROXY_PLACEMENT_TAG = "nms_proxy_placement"


def load_proxy_mesh(object_id):
    """Get the uncoloured fbx proxy mesh for an id, importing it on first use.

    The mesh comes back with no materials on it - the caller is expected to
    copy it per UserData and let utils.material.restore_material paint the copy.

    Args:
        object_id (str): The part to load.

    Returns:
        bpy.types.Mesh: The base mesh, or None when models/ has no fbx for the
            id, in which case the caller should leave whatever it has alone
            rather than substituting anything.
    """
    mesh_name = PROXY_MESH_PREFIX + object_id
    cached = bpy.data.meshes.get(mesh_name)
    if cached is not None and cached.get(PROXY_MESH_TAG) == object_id:
        return cached

    # Same rebuild the high res side does, and for the same reason - the fbx
    # library has the wrong mesh under a lot of the corvette variant ids. The
    # proxies are stored in the same space as the high res assets, so the
    # transform out of objects_map.json applies to them unchanged.
    if REBUILD_VARIANTS:
        mesh = rebuild_variant_proxy_mesh(object_id)
        if mesh is not None:
            return mesh

    fbx_path = BUILDER.get_obj_path(object_id)
    if not fbx_path or not os.path.isfile(fbx_path):
        return None

    # Every new object the import brought in, not just the one it happened to
    # hand back: an fbx that carries an armature or an empty alongside its mesh
    # would otherwise leave the extras behind in the scene.
    objects_before = set(bpy.data.objects)
    bpy.ops.import_scene.fbx(filepath=fbx_path)
    imported = [item for item in bpy.data.objects if item not in objects_before]

    mesh = None
    for item in imported:
        if mesh is None and item.type == "MESH":
            mesh = item.data
            mesh.materials.clear()
        bpy.data.objects.remove(item, do_unlink=True)

    if mesh is None:
        return None

    mesh.name = mesh_name
    mesh[PROXY_MESH_TAG] = object_id
    return mesh


def rebuild_variant_proxy_mesh(object_id):
    """Build a variant's fbx proxy by transforming its root part's proxy.

    The proxy twin of rebuild_variant_mesh - same table, same transform, only
    the cache it lands in differs. Comes back with no materials on it, like
    every other base proxy mesh, so the caller still copies and paints it per
    UserData.

    Args:
        object_id (str): The variant to build.

    Returns:
        bpy.types.Mesh: The rebuilt base mesh, or None when the id is not a
            reproducible variant or models/ has no fbx for its root.
    """
    rebuild = variant_map.get_rebuild(object_id)
    if rebuild is None:
        return None

    root_id, matrix = rebuild
    if root_id == object_id:
        return None

    root_mesh = load_proxy_mesh(root_id)
    if root_mesh is None:
        return None

    mesh = transformed_copy(root_mesh, matrix)
    mesh.name = PROXY_MESH_PREFIX + object_id
    mesh[PROXY_MESH_TAG] = object_id
    return mesh


# The custom properties utils.material.assign_material writes onto an object
# when it paints a proxy. They belong to the (ObjectID, UserData) pair rather
# than to the placement, so a second placement of the same pair can be given
# them wholesale instead of running the whole paint again.
PROXY_CARRIED_PROPS = (
    Part.PROP_USER_DATA,
    materials_v2.PROP_READONLY_COLOUR,
    materials_v2.PROP_READONLY_MATERIAL,
)


def _find_proxy_placement_mesh(key):
    """The proxy mesh already cut for one (ObjectID, UserData), if there is one.

    Matched on the tag rather than on the name alone, so a mesh of the user's
    own that happens to be called CUBEROOM_1 is never mistaken for one of ours.

    Args:
        key (tuple): (object id, UserData as a string).

    Returns:
        bpy.types.Mesh: The existing copy, or None.
    """
    mesh = bpy.data.meshes.get("%s_%s" % key)
    if mesh is not None and mesh.get(PROXY_PLACEMENT_TAG) == "%s/%s" % key:
        return mesh
    return None


def apply_proxy_mesh(bpy_object, object_id, user_data, cache=None):
    """Point an existing object at the fbx proxy mesh for one (id, UserData).

    A proxy carries its colour in a flat material in slot 0, so unlike a high
    res part it cannot share one mesh across every placement - the most sharing
    the old colour system allows is one mesh per (ObjectID, UserData) pair,
    which is exactly what utils.material.optimise_materials goes back and
    restores after the fact. Passing a `cache` dict across a batch gets that
    sharing first time round instead, and pays for the paint once per pair
    rather than once per placement.

    Nothing but the mesh and the colour is touched, so this is also the whole
    of what it takes to turn a placed high res part back into a proxy.

    Args:
        bpy_object (bpy.types.Object): The object to point at the proxy.
        object_id (str): The part it is a placement of.
        user_data: The packed UserData value for this placement.
        cache (dict): Optional {(object id, UserData): (mesh, properties,
            colour)} carried across a batch of placements.

    Returns:
        bool: False when models/ has no fbx for the id, in which case the
            object is left exactly as it was.
    """
    if user_data is None:
        user_data = Part.DEFAULT_USER_DATA
    key = (object_id, str(user_data))
    entry = cache.get(key) if cache is not None else None

    if entry is not None:
        mesh, carried, colour = entry
        bpy_object.data = mesh
        # the palette properties drive the high res colourise node group and
        # mean nothing to a flat material, so an object that keeps them reads
        # as half converted to anything that inspects it afterwards
        materials_v2.clear(bpy_object)
        for name, value in carried.items():
            bpy_object[name] = value
        bpy_object.color = colour
        return True

    mesh = _find_proxy_placement_mesh(key)
    if mesh is None:
        base_mesh = load_proxy_mesh(object_id)
        if base_mesh is None:
            return False

        # a private copy per pair, because painting it writes into its slot 0
        mesh = base_mesh.copy()
        mesh.name = "%s_%s" % key
        # the copy is a placement mesh, not the cached import it came from -
        # it must not answer to load_proxy_mesh's tag
        if PROXY_MESH_TAG in mesh:
            del mesh[PROXY_MESH_TAG]
        mesh[PROXY_PLACEMENT_TAG] = "%s/%s" % key

    bpy_object.data = mesh
    materials_v2.clear(bpy_object)
    # paints slot 0 of the copy, and writes UserData and the readable labels
    material.restore_material(bpy_object, key[1])

    if cache is not None:
        cache[key] = (
            mesh,
            {
                name: bpy_object[name]
                for name in PROXY_CARRIED_PROPS
                if name in bpy_object
            },
            tuple(bpy_object.color),
        )

    return True


def new_proxy_object(object_id, user_data, cache=None):
    """Make a bare object over an fbx proxy mesh, coloured for one UserData.

    No part properties are set beyond the ones painting writes - that is the
    caller's job, the same as for new_high_res_object.

    Args:
        object_id (str): The part to build.
        user_data: The packed UserData value for this placement.
        cache (dict): Optional, carried across a batch - see apply_proxy_mesh.

    Returns:
        bpy.types.Object: The new object, or None when models/ has no fbx for
            the id, so the caller can decide what to do about it.
    """
    # The object has to be born over some mesh before it can be pointed at the
    # right one - an object made with no data is an Empty, and an Empty cannot
    # be given a mesh afterwards. load_proxy_mesh is cached, so asking for the
    # base here and again inside apply_proxy_mesh costs one dict lookup.
    base_mesh = load_proxy_mesh(object_id)
    if base_mesh is None:
        return None

    bpy_object = bpy.data.objects.new(object_id, base_mesh)
    blend_utils.add_to_scene(bpy_object)
    apply_proxy_mesh(bpy_object, object_id, user_data, cache=cache)
    return bpy_object


def new_merge_source(object_id, user_data, high_res=True, proxy_cache=None):
    """Make a bare part object for something that is about to be merged away.

    Rebuilding a group places every child of it only to join them into one mesh
    and throw the children away, so nothing add_part() does around the object
    itself - the part class, the rig, the snapping metadata, the palette
    properties - survives long enough to be read. What does survive the merge
    is the geometry, the material slots and, through
    Group.get_representative_user_data, the ObjectID and UserData properties,
    so those are all this sets.

    Falls back to the other library when the requested one has no model for the
    id, the same way add_part() does, so a group is never rebuilt with holes in
    it.

    Args:
        object_id (str): The part to build.
        user_data: The packed UserData value for this child.
        high_res (bool): True to prefer the models-high-res asset, False to
            prefer the old fbx proxy.
        proxy_cache (dict): Optional, carried across a batch - see
            new_proxy_object.

    Returns:
        bpy.types.Object: The new object, or None when neither library covers
            the id.
    """
    if high_res:
        bpy_object = new_high_res_object(object_id)
        if bpy_object is None:
            bpy_object = new_proxy_object(object_id, user_data, cache=proxy_cache)
    else:
        bpy_object = new_proxy_object(object_id, user_data, cache=proxy_cache)
        if bpy_object is None:
            bpy_object = new_high_res_object(object_id)

    if bpy_object is None:
        return None

    bpy_object[Part.PROP_OBJECT_ID] = object_id
    bpy_object[Part.PROP_USER_DATA] = str(
        user_data if user_data is not None else Part.DEFAULT_USER_DATA
    )
    return bpy_object


# fbx fallback for the 169 ids the high res index doesnt cover yet (of 2090 in
# models/, 1921 are served from models-high-res).
# these still colour by swapping a flat material in, so objects can only share a
# mesh when their ObjectID AND UserData match
def build_fbx_part(
    object_id, user_data, import_collection, unique_objects, unique_materials
):
    material_key = (object_id, user_data)

    # import object from disk when visiting that object_id for first time
    if object_id not in unique_objects:
        bpy_object = improt_fbx_from_disk(object_id)
        if bpy_object is None:
            return None

        collection_utils.move_object_into_collection(import_collection, bpy_object)
        material.restore_material(bpy_object, user_data)

        # store it in temp cache
        unique_objects[object_id] = bpy_object
        unique_materials[material_key] = bpy_object.data
        return bpy_object

    # if object is already visited, check if a same object with same userdata exists
    # this is to avoid creating data block for each object with same object_ids
    bpy_object = unique_objects[object_id].copy()
    import_collection.objects.link(bpy_object)

    # choose to either create new material or use existing one if it exists
    if material_key in unique_materials:
        bpy_object.data = unique_materials[material_key]
    else:
        bpy_object.data = bpy_object.data.copy()
        material.restore_material(bpy_object, user_data)
        unique_materials[material_key] = bpy_object.data

    return bpy_object


def improt_fbx_from_disk(object_id):
    fbx_path = BUILDER.get_obj_path(object_id)

    objects_before = set(bpy.data.objects)
    if fbx_path is None:
        from .save_editor import station_part_models
        native = station_part_models.load(object_id)
        if native is not None:
            return native
        bpy.ops.mesh.primitive_cube_add()
    else:
        bpy.ops.import_scene.fbx(filepath=fbx_path)
    new_objects = list(set(bpy.data.objects) - objects_before)

    if not new_objects:
        return None

    bpy_object = bpy.data.objects[new_objects[0].name]
    bpy_object.name = object_id
    bpy_object.data.materials.clear()
    bpy_object.select_set(False)

    return bpy_object

# copy params from part json to bpy_object
def restore_params(part, part_data, object_id):

    user_data = part_data.get(Part.PROP_USER_DATA, "")
    time_stamp = str(part_data.get(Part.PROP_TIMESTAMP, int(time.time())))
    message = part_data.get(Part.PROP_MESSAGE, None)

    # Apply metadata
    part[Part.PROP_OBJECT_ID] = object_id
    part[Part.PROP_SNAP_ID] = object_id
    part[Part.PROP_USER_DATA] = str(user_data)
    part[Part.PROP_TIMESTAMP] = time_stamp
    part[Part.PROP_BELONGS_TO_PRESET] = False

    if message:
        part[Part.PROP_MESSAGE] = message

    return part

# convert position, up and at to matrix world for blender object
def deserialise_matrix_world(part_data):
    # Get location data.
    pos = part_data.get("Position", [0.0, 0.0, 0.0])
    up = part_data.get("Up", [0.0, 0.0, 0.0])
    at = part_data.get("At", [0.0, 0.0, 0.0])

    # combine three vectors above to constrict matrix world
    return create_matrix_from_vectors(pos, up, at)


def create_matrix_from_vectors(pos, up, at):
    """Create a world space matrix given by an Up and At vector.

    Args:
        pos (list): 3 element list/vector representing the x,y,z position.
        up (list): 3 element list/vector representing the up vector.
        at (list): 3 element list/vector representing the aim vector.
    """
    up_vector = mathutils.Vector(up)
    at_vector = mathutils.Vector(at)

    # Compute right vector and normalize
    right_vector = at_vector.cross(up_vector)
    right_vector.normalize()
    right_vector *= -1

    # Get the up length once
    up_length = up_vector.length
    right_vector.length = up_length
    at_vector.length = up_length

    # Build matrix directly without intermediate list construction
    mat = mathutils.Matrix((
        (right_vector[0], up_vector[0], at_vector[0], pos[0]),
        (right_vector[1], up_vector[1], at_vector[1], pos[1]),
        (right_vector[2], up_vector[2], at_vector[2], pos[2]),
        (0.0, 0.0, 0.0, 1.0),
    ))

    return X_ROT_90 @ mat
