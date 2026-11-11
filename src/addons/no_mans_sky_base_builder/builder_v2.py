import bpy
import os
import json
import time
import mathutils
import math
from pathlib import Path
from . import builder, preset, hd_library, simple_library
from .part import Part
from .utils import blend_utils, material, materials_v2, collection_utils, mirror_pivot
from .utils import variant_map
from .part_overrides import parts_override
from .part_overrides.fossil_models import BASE_IDS as FOSSIL_BASE_IDS, resolve_model_id
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
MESH_SOURCE_TAG = 'bbe_hd_asset_source'
MESH_REVISIONS = dict.fromkeys(
    ("B_HAB_A", "B_HAB_B", "B_HAB_C", "B_HAB1_A", "B_HAB1_B", "B_HAB1_C", "B_ALK_C"),
    "18.0.9",
)
MESH_REVISIONS.update(dict.fromkeys(
    ("B_STR_M_Y_" + side + suffix
     for side in ("NE", "NW", "N", "E", "S", "W")
     for suffix in (("", "1", "2", "3") if side in ("NE", "NW") else ("",))),
    "18.1.1",
))
MESH_REVISIONS.update(dict.fromkeys(
    ('B_STR_T_NWTB', 'B_STR_T_NWTB1', 'B_STR_T_NWTB2', 'B_STR_T_NWTB3'),
    '18.1.67',
))

MESH_REVISIONS.update(dict.fromkeys(('SET_CLASS_A', 'SET_CLASS_B', 'SET_CLASS_S'), '18.1.11'))
MESH_REVISIONS.update(dict.fromkeys(('PIPE','FRE_FACE_WALL','FRE_ROOM_IND1','SET_LZ'), '18.1.9'))

# The downloaded pack confused Builders cables with Bazaar fabric hangings.
CABLE_CORRECTIONS = ('B_WALLHANGING1', 'B_WALLHANGING2', 'B_WALLHANGING3')
MESH_REVISIONS.update(dict.fromkeys(CABLE_CORRECTIONS, '18.1.20'))
# The game routes a terminal snapped to a wall to BASETERMINAL. The normal
# BUILDTERMINAL asset remains the freestanding model.
MESH_REVISIONS['BUILDTERMINAL_WALL'] = '18.1.52-wall'
FORSAKEN_PARTS = {r['id'] for r in json.loads((Path(FILE_PATH) / 'resources/forsaken_assets.json').read_text())['assets']}
MESH_REVISIONS.update(dict.fromkeys(FORSAKEN_PARTS, '18.2.34'))
MESH_REVISIONS['B_COK_E'] = '7.13-vantage-closed'
MESH_REVISIONS['GRAV_WALL'] = 'grav-wall-assembly-20261104'
NEW_COCKPITS = {f'B_COK_C{i}' for i in range(1, 10)} | {'B_COK_E'}
COCKPIT_BASE_REVISION = 3
CORRECTED_LEGACY_PARTS = {r['id'] for r in json.loads((Path(FILE_PATH) / 'resources/native_asset_corrections.json').read_text())['assets']}
MESH_REVISIONS.update(dict.fromkeys(CORRECTED_LEGACY_PARTS, '18.2.36'))
REPAIRED_VISUAL_PARTS = {'BASE_TOYCORE'}
MESH_REVISIONS['BASE_TOYCORE'] = 'toycore-native-spherical-effects-20261105'
BYTEBEAT_PARTS = {'BYTEBEAT', 'BYTEBEATSWITCH', 'HOLO_DISCO_0', 'U_BYTEBEATLINE'}

# Set once per session by get_asset_index().
_asset_index = None
_asset_root = None


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

    from . import progress_ui
    with progress_ui.Activity('Importing models') as progress:
        return _deserialise_from_data(data, progress)


def _deserialise_from_data(data, progress):
    progress.update(.02, 'Preparing scene')

    from . import stages
    stages.prepare_import(bpy.context.scene)

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
        total = len(objects_data)
        for order, part_data in enumerate(objects_data):
            if order % 16 == 0:
                progress.batch(order, total, .06, .87, 'Models')
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
            native_world = deserialise_matrix_world(part_data)
            normalized = (bpy_object.type == 'MESH' and
                          bpy_object.data.get(mirror_pivot.MESH_TAG) == object_id)
            bpy_object.matrix_world = (mirror_pivot.display_matrix(native_world, object_id)
                                       if normalized else native_world)
            if normalized:
                bpy_object[mirror_pivot.OBJECT_TAG] = object_id

            # provide order
            bpy_object[Part.PROP_ORDER] = order

        progress.batch(total, total, .06, .87, 'Models')
        progress.update(.89, 'Applying materials')
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

    # A native BASE_BUBPIPE is one placement node. Its visible straight or
    # elbow is chosen by the connected nodes, not by a different save ID.
    from . import bubble_preview
    bubble_preview.inspect_loaded_tubes(bpy.context.scene)

    # Reconstruct presets.
    progress.update(.94, 'Building presets and connections')
    for preset_data in data.get("Presets", []):
        preset.Preset.deserialise_from_data(
            preset_data, BUILDER, compensate_normal=True
        )

    # Build Rigs.
    BUILDER.build_rigs()
    # Optimise control points.
    BUILDER.optimise_control_points()
    from . import cable_connections
    cable_connections.bind_imported(bpy.context.scene)
    progress.update(1.0, 'Import complete')


def placement_from_target(object_id, target):
    if target is None or not target.select_get():
        return None
    matrix = target.matrix_world.copy()
    if object_id in FORSAKEN_PARTS and not str(target.get('ObjectID', '')).startswith('B_'):
        location, rotation, scale = matrix.decompose()
        return mathutils.Matrix.Translation(location) @ X_ROT_90 @ mathutils.Matrix.Diagonal((*scale, 1.0))
    return matrix


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
    placement_matrix = placement_from_target(object_id, active_object)

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
    # Only a new library append can duplicate shared shader data. Repeated
    # placements reuse the same mesh and need no whole-scene cleanup pass.
    materials_v2.dedupe_appended_data(only_if_pending=True)
    materials_v2.recolour_from_user_data([bpy_object], user_data)

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
    global _asset_index, _asset_root
    root = hd_library.library_root()
    high_res_path = str(root / "assets") if root else ""

    if _asset_index is not None and not rebuild and (high_res_path, str(hd_library.scenes_root()), str(hd_library.additions_root())) == _asset_root:
        return _asset_index

    # The native detailed mesh is reassembled in this bundled correction; its
    # original textures still come from the downloaded HD pack.
    toycore = os.path.join(FILE_PATH, 'resources', 'hd_corrections', 'BASE_TOYCORE.blend')
    _asset_index = {'BASE_TOYCORE': toycore} if root else {}
    _asset_root = (high_res_path, str(hd_library.scenes_root()), str(hd_library.additions_root()))
    if not os.path.isdir(high_res_path):
        return _asset_index

    # collect every candidate first, then resolve the styled ones, so the
    # answer doesn't depend on the order the folder happens to list in
    candidates = {}
    for filename in os.listdir(high_res_path):
        if not filename.endswith(".blend"):
            continue
        object_id, separator, style = filename[:-6].partition("__")
        candidates.setdefault(object_id, []).append(
            (style if separator else None, os.path.join(high_res_path, filename))
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

    # Small native replacements are available only with the HD library.
    # Keep the distinct S_WALLHANGING fabric parts mapped to their own assets.
    for cable in CABLE_CORRECTIONS:
        _asset_index[cable] = os.path.join(FILE_PATH, 'resources', 'hd_corrections', cable + '.blend')

    # Native additions are a separate, verified component of Detailed Proxies.
    # Old core packs reused several of these IDs for unrelated meshes. An
    # incomplete HD update must use the correct simple proxy, never that mesh.
    for object_id in FORSAKEN_PARTS | CORRECTED_LEGACY_PARTS:
        _asset_index.pop(object_id, None)
    additions_root = hd_library.additions_root()
    additions = additions_root / 'assets' if additions_root else None
    if additions is not None and additions.is_dir():
        _asset_index.update({path.stem: str(path) for path in additions.glob('*.blend')})
        # Compatible older packs still contain the detached gravity-wall rails.
        # Use its repaired base proxy until the current HD update is installed.
        if additions_root.name != hd_library.additions_specification()['id']:
            _asset_index.pop('GRAV_WALL', None)

    # Core corrections do not replace or invalidate the persistent HD pack.
    scenes = hd_library.scenes_root()
    if scenes:
        for marker in ('SET_CLASS_A', 'SET_CLASS_B', 'SET_CLASS_S'):
            _asset_index[marker] = str(scenes / 'display' / (marker + '.blend'))
    if root:
        _asset_index['BASE_TOYCORE'] = toycore
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


def refresh_forsaken_proxies(scene):
    """Replace known flat-shaded display caches, retaining part transforms/data."""
    detailed = getattr(scene, 'bbe_detailed_proxies', True)
    coloured = []
    for obj in list(scene.objects):
        pid = obj.get('ObjectID')
        if (obj.type != 'MESH' or pid not in FORSAKEN_PARTS
                or (obj.data.get(PROXY_MESH_TAG) != pid and
                    not str(obj.data.get(PROXY_PLACEMENT_TAG, '')).startswith(pid + '/'))):
            continue
        old = obj.data
        mesh = load_high_res_mesh(pid) if detailed else None
        if mesh is not None:
            obj.data = mesh
            coloured.append((obj, obj.get('UserData', Part.DEFAULT_USER_DATA)))
        elif (not detailed and (
                (pid in NEW_COCKPITS and old.get('bbe_forsaken_revision') != COCKPIT_BASE_REVISION)
                or (pid == 'GRAV_WALL' and old.get(MESH_REVISION_TAG) != MESH_REVISIONS[pid]))):
            apply_proxy_mesh(obj, pid, obj.get('UserData', Part.DEFAULT_USER_DATA))
        if obj.data != old:
            if old.users == 0:
                bpy.data.meshes.remove(old)
    if coloured:
        materials_v2.apply_many(coloured)
    if not detailed:
        return
    for obj in list(scene.objects):
        pid = obj.get('ObjectID')
        if (obj.type != 'MESH' or pid not in FORSAKEN_PARTS | CORRECTED_LEGACY_PARTS
                or obj.data.get(MESH_TAG) != pid
                or obj.data.get(MESH_REVISION_TAG) == MESH_REVISIONS[pid]):
            continue
        old = obj.data
        mesh = load_high_res_mesh(pid)
        if mesh is not None:
            obj.data = mesh
            if old.users == 0:
                bpy.data.meshes.remove(old)


def refresh_toycore_proxies(scene):
    """Upgrade saved generator displays without changing placement or export data."""
    detailed = getattr(scene, 'bbe_detailed_proxies', True)
    revised = MESH_REVISIONS['BASE_TOYCORE']
    coloured = []
    changed = 0
    for obj in scene.objects:
        if obj.type != 'MESH' or obj.get('ObjectID') != 'BASE_TOYCORE':
            continue
        old = obj.data
        is_hd = old.get(MESH_TAG) == 'BASE_TOYCORE'
        is_proxy = (old.get(PROXY_MESH_TAG) == 'BASE_TOYCORE' or
                    str(old.get(PROXY_PLACEMENT_TAG, '')).startswith('BASE_TOYCORE/'))
        legacy_fbx = len(old.vertices) == 92 and len(old.polygons) == 104
        if not (is_hd or is_proxy or legacy_fbx):
            continue
        if old.get(MESH_REVISION_TAG) == revised and (is_hd if detailed else is_proxy):
            continue
        if detailed:
            mesh = load_high_res_mesh('BASE_TOYCORE')
            if mesh is None:
                continue
            obj.data = mesh
            coloured.append((obj, obj.get('UserData', Part.DEFAULT_USER_DATA)))
        elif not apply_proxy_mesh(obj, 'BASE_TOYCORE',
                                  obj.get('UserData', Part.DEFAULT_USER_DATA)):
            continue
        if obj.data != old:
            changed += 1
            if old.users == 0:
                bpy.data.meshes.remove(old)
    if coloured:
        materials_v2.apply_many(coloured)
    return changed


def refresh_bytebeat_proxies(scene):
    """Repair old HD scenes whose specialized importers kept simple meshes."""
    if not getattr(scene, 'bbe_detailed_proxies', True):
        return 0
    from . import cable_connections
    to_colour = []
    for obj in scene.objects:
        pid = obj.get('ObjectID')
        if obj.type != 'MESH' or pid not in BYTEBEAT_PARTS:
            continue
        if materials_v2.is_high_res(obj):
            correct_hd_display(obj.data, pid)
            if pid == cable_connections.BYTEBEAT:
                cable_connections.style(obj)
            continue
        mesh = load_high_res_mesh(pid)
        if mesh is not None:
            obj.data = mesh
            to_colour.append((obj, obj.get('UserData', Part.DEFAULT_USER_DATA)))
    if to_colour:
        materials_v2.apply_many(to_colour)
        for obj, _ in to_colour:
            if obj.get('ObjectID') == cable_connections.BYTEBEAT:
                cable_connections.style(obj)
        materials_v2.dedupe_appended_data()
        materials_v2.ensure_finish_nodes()
    return len(to_colour)


# get the shared mesh datablock for an object id, appending it on first use
def correct_hd_display(mesh, object_id):
    """Upgrade HD display data only; placement and export records stay intact."""
    from .utils import room_glass, roof_alignment, light_fissure, corvette_trim
    corvette_trim.correct(mesh, object_id)
    room_glass.correct(mesh, object_id)
    roof_alignment.correct(mesh, object_id)
    light_fissure.correct(mesh, object_id)
    if object_id == 'U_BYTEBEATLINE' and not mesh.get('bbe_beat_glow_revision'):
        # Native crossed ribbons already span local Z=0..1. Feather their
        # width in local coordinates so cable length and endpoints stay exact.
        mat = bpy.data.materials.new('BBE ByteBeat Pink Glow')
        mat.use_nodes = True
        mat.diffuse_color = (1, .04, .3, 1)
        mat.surface_render_method = 'BLENDED'
        mat.use_transparent_shadow = True
        tree = mat.node_tree; tree.nodes.clear()
        def math_node(operation, a, b):
            node = tree.nodes.new('ShaderNodeMath'); node.operation = operation
            for socket, value in zip(node.inputs, (a, b)):
                if isinstance(value, (int, float)): socket.default_value = value
                else: tree.links.new(value, socket)
            return node.outputs[0]
        coord = tree.nodes.new('ShaderNodeTexCoord')
        axes = tree.nodes.new('ShaderNodeSeparateXYZ')
        tree.links.new(coord.outputs['Object'], axes.inputs[0])
        radius = max(max(abs(v.co.x), abs(v.co.y)) for v in mesh.vertices)
        x2 = math_node('MULTIPLY', axes.outputs['X'], axes.outputs['X'])
        y2 = math_node('MULTIPLY', axes.outputs['Y'], axes.outputs['Y'])
        radial = math_node('POWER', math_node('ADD', x2, y2), .5)
        fade = math_node('MAXIMUM', math_node('SUBTRACT', 1, math_node('DIVIDE', radial, radius)), 0)
        fade = math_node('MULTIPLY', math_node('POWER', fade, 2), .65)
        transparent = tree.nodes.new('ShaderNodeBsdfTransparent')
        emission = tree.nodes.new('ShaderNodeEmission')
        emission.inputs['Color'].default_value = (1, .04, .3, 1)
        emission.inputs['Strength'].default_value = 3
        mix = tree.nodes.new('ShaderNodeMixShader')
        tree.links.new(fade, mix.inputs[0]); tree.links.new(transparent.outputs[0], mix.inputs[1])
        tree.links.new(emission.outputs[0], mix.inputs[2])
        output = tree.nodes.new('ShaderNodeOutputMaterial')
        tree.links.new(mix.outputs[0], output.inputs['Surface'])
        mesh.materials.clear(); mesh.materials.append(mat)
        for polygon in mesh.polygons: polygon.material_index = 0
        mesh['bbe_beat_glow_revision'] = 1
    if mesh.get('bbe_display_revision') == '18.1.39':
        return
    if object_id in {'SET_CLASS_A', 'SET_CLASS_B', 'SET_CLASS_S'}:
        # Marker scale determines world beam length. FF confirms 31.1 local
        # units for S; the A/B calibration of 16.5 local units keeps the
        # smaller-class emitters inside Vespera's glass housings. The object
        # transform supplies the scale exactly once; no placement-dependent
        # length correction is applied.
        slots = {i for i,m in enumerate(mesh.materials) if m and
                 ('long projection beam' in m.name or 'electrical particles' in m.name)}
        vertices = {v for p in mesh.polygons if p.material_index in slots for v in p.vertices}
        start = 2.0431294441223145
        target_length = 31.1 if object_id == 'SET_CLASS_S' else 16.5
        # Migrate saved previews from the older global lengths and from the
        # placement-specific 18.1.38 copies without changing saved parts.
        previous_length = mesh.get('bbe_marker_beam_length',
                                   7.5 if mesh.get('bbe_display_revision') == '18.1.17'
                                   else 16.5 if mesh.get('bbe_display_revision') == '18.1.18' else 31.1)
        for index in vertices:
            vertex = mesh.vertices[index]
            vertex.co.y = start + (vertex.co.y-start) * (target_length/previous_length)
        mesh['bbe_marker_beam_length'] = target_length
        mesh.update()
    for mat in mesh.materials:
        if (not mat or not mat.use_nodes or mat.get('bbe_glass_revision') == 1
                or mat.get('nms_class') != 'Translucent'
                or 'glass' not in mat.get('nms_material_path', '').lower()):
            continue
        tree = mat.node_tree
        output = next((n for n in tree.nodes if n.type == 'OUTPUT_MATERIAL' and n.is_active_output), None)
        if output is None or not output.inputs['Surface'].is_linked:
            continue
        source = output.inputs['Surface'].links[0].from_socket
        # A transparent surface works without enabling costly refraction.
        # Keep a modest reflective/tinted edge while looking through the pane.
        transparent = tree.nodes.new('ShaderNodeBsdfTransparent')
        fresnel = tree.nodes.new('ShaderNodeFresnel')
        fresnel.inputs['IOR'].default_value = 1.45
        fade = tree.nodes.new('ShaderNodeMapRange')
        fade.inputs['To Min'].default_value = .08
        fade.inputs['To Max'].default_value = .30
        mix = tree.nodes.new('ShaderNodeMixShader'); mix.name = 'BBE Clear Glass'
        tree.links.new(fresnel.outputs[0], fade.inputs['Value'])
        tree.links.new(fade.outputs[0], mix.inputs[0])
        tree.links.new(transparent.outputs[0], mix.inputs[1])
        tree.links.new(source, mix.inputs[2])
        tree.links.new(mix.outputs[0], output.inputs['Surface'])
        mat.surface_render_method = 'BLENDED'
        mat.use_transparent_shadow = True
        mat['bbe_glass_revision'] = 1
    mesh['bbe_display_revision'] = '18.1.39'


def _mesh_texture_images(mesh):
    """Only the images used by this mesh, including nested shader groups."""
    images = set()
    seen = set()
    pending = [mat.node_tree for mat in mesh.materials if mat and mat.use_nodes]
    while pending:
        tree = pending.pop()
        if tree in seen:
            continue
        seen.add(tree)
        for node in tree.nodes:
            if node.type in {'TEX_IMAGE', 'TEX_ENVIRONMENT'} and node.image:
                images.add(node.image)
            elif node.type == 'GROUP' and node.node_tree:
                pending.append(node.node_tree)
    return images


def _relink_mesh_textures(mesh):
    # Library .blend files carry the pack author's absolute texture paths.
    # Resolve them before a progress redraw can show this mesh in a scene.
    images = _mesh_texture_images(mesh)
    hd_library.relink_texture_images(images)
    for image in images:
        if image.source == 'FILE' and not image.packed_file:
            if not Path(bpy.path.abspath(image.filepath, library=image.library)).is_file():
                hd_library.STATE['error'] = (
                    'A detailed texture is missing. Reinstall the HD pack: ' + image.name)
                return False
    return True


def load_high_res_mesh(object_id, asset_index=None, *, force=False):
    if not force and not getattr(bpy.context.scene, "bbe_detailed_proxies", True):
        return None
    asset_index = asset_index if asset_index is not None else get_asset_index()
    protected = object_id in FORSAKEN_PARTS | CORRECTED_LEGACY_PARTS | REPAIRED_VISUAL_PARTS
    source_path = asset_index.get(object_id)
    source_key = str(Path(source_path).resolve()) if source_path else ''
    if protected and not source_path:
        return None
    # the cache lives in bpy.data rather than in a module level dict, so it
    # survives a new file, a module reload and a scene the user already saved
    mesh_name = MESH_PREFIX + object_id
    cached = bpy.data.meshes.get(mesh_name)
    revision = MESH_REVISIONS.get(object_id)
    if object_id in {'SET_CLASS_A', 'SET_CLASS_B', 'SET_CLASS_S'} and hd_library.scenes_root() is None:
        revision += '-base'
    if cached is not None and cached.get(MESH_TAG) == object_id:
        if (not protected or cached.get(MESH_SOURCE_TAG) == source_key) and (revision is None or cached.get(MESH_REVISION_TAG) == revision) and (
                not mirror_pivot.has_pivot(object_id) or
                cached.get(mirror_pivot.MESH_TAG) == object_id):
            correct_hd_display(cached, object_id)
            return cached if _relink_mesh_textures(cached) else None
        cached.name = mesh_name + "_legacy"

    # A reproducible variant is built out of the mesh it is a variant of rather
    # than out of its own asset - most of the corvette variants ship the wrong
    # mesh, and the transform in objects_map.json is measured, so this is the
    # more trustworthy of the two. See utils/variant_map.py.
    if REBUILD_VARIANTS:
        mesh = rebuild_variant_mesh(object_id, asset_index)
        if mesh is not None:
            if protected:
                mesh[MESH_SOURCE_TAG] = source_key
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
    mirror_pivot.normalize_mesh(mesh, object_id)
    mesh[MESH_TAG] = object_id
    if protected:
        mesh[MESH_SOURCE_TAG] = source_key
    if revision is not None:
        mesh[MESH_REVISION_TAG] = revision
    if CLEAN_DUPLICATE_FACES and mesh.get('bbe_duplicate_faces_prepared') != 1:
        blend_utils.remove_duplicate_faces(mesh)
    # The append brought this asset's own copies of its textures and of the
    # colourise node group with it. A caller inside a deferred block is not
    # going to call the collapse itself, so tell it there is now something to
    # collapse - see materials_v2.note_appended_data.
    materials_v2.note_appended_data()
    correct_hd_display(mesh, object_id)
    return mesh if _relink_mesh_textures(mesh) else None


def load_trade_terminal_wall_mesh():
    """The game's snapped wall variant of BUILDTERMINAL."""
    path = os.path.join(FILE_PATH, 'resources', 'hd_corrections', 'BUILDTERMINAL.blend')
    # There is no separate low-resolution wall variant. Reuse the native
    # wall mesh in either quality so a switch cannot restore the kiosk.
    return load_high_res_mesh('BUILDTERMINAL_WALL', {'BUILDTERMINAL_WALL': path}, force=True)


def use_trade_terminal_wall_model(obj):
    """Show the native BASETERMINAL only after a successful BBE wall snap."""
    if obj is None or obj.type != 'MESH' or obj.get('ObjectID') != 'BUILDTERMINAL':
        return False
    mesh = load_trade_terminal_wall_mesh()
    if mesh is None:
        return False
    obj.data = mesh
    obj['bbe_trade_terminal_wall_model'] = True
    return True


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
    mesh = transformed_copy(root_mesh,
        mathutils.Matrix.Translation(mirror_pivot.pivot(object_id)) @ matrix @
        mathutils.Matrix.Translation(-mirror_pivot.pivot(root_id)))
    mesh.name = MESH_PREFIX + object_id
    if mirror_pivot.has_pivot(object_id):
        mesh[mirror_pivot.MESH_TAG] = object_id
    elif mirror_pivot.MESH_TAG in mesh:
        del mesh[mirror_pivot.MESH_TAG]
    mesh[MESH_TAG] = object_id
    if object_id in MESH_REVISIONS:
        mesh[MESH_REVISION_TAG] = MESH_REVISIONS[object_id]
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
        revision = MESH_REVISIONS.get(object_id)
        if (revision is None or cached.get(MESH_REVISION_TAG) == revision) and (
                not mirror_pivot.has_pivot(object_id) or
                cached.get(mirror_pivot.MESH_TAG) == object_id):
            return cached
        cached.name = mesh_name + "_legacy"

    # Same rebuild the high res side does, and for the same reason - the fbx
    # library has the wrong mesh under a lot of the corvette variant ids. The
    # proxies are stored in the same space as the high res assets, so the
    # transform out of objects_map.json applies to them unchanged.
    if REBUILD_VARIANTS:
        mesh = rebuild_variant_proxy_mesh(object_id)
        if mesh is not None:
            return mesh

    # Bundled repairs also cover legacy FBX files that exist but are empty.
    mesh = simple_library.load_mesh(object_id)
    if mesh is not None:
        mesh.name = mesh_name
        mirror_pivot.normalize_mesh(mesh, object_id)
        mesh[PROXY_MESH_TAG] = object_id
        if object_id in MESH_REVISIONS:
            mesh[MESH_REVISION_TAG] = MESH_REVISIONS[object_id]
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
    mirror_pivot.normalize_mesh(mesh, object_id)
    mesh[PROXY_MESH_TAG] = object_id
    if object_id in MESH_REVISIONS:
        mesh[MESH_REVISION_TAG] = MESH_REVISIONS[object_id]
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

    mesh = transformed_copy(root_mesh,
        mathutils.Matrix.Translation(mirror_pivot.pivot(object_id)) @ matrix @
        mathutils.Matrix.Translation(-mirror_pivot.pivot(root_id)))
    mesh.name = PROXY_MESH_PREFIX + object_id
    if mirror_pivot.has_pivot(object_id):
        mesh[mirror_pivot.MESH_TAG] = object_id
    elif mirror_pivot.MESH_TAG in mesh:
        del mesh[mirror_pivot.MESH_TAG]
    mesh[PROXY_MESH_TAG] = object_id
    if object_id in MESH_REVISIONS:
        mesh[MESH_REVISION_TAG] = MESH_REVISIONS[object_id]
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
        revision = MESH_REVISIONS.get(key[0])
        if ((revision is not None and mesh.get(MESH_REVISION_TAG) != revision) or
                (key[0] in NEW_COCKPITS and
                 mesh.get('bbe_forsaken_revision') != COCKPIT_BASE_REVISION) or
                (mirror_pivot.has_pivot(key[0]) and
                 mesh.get(mirror_pivot.MESH_TAG) != key[0])):
            mesh.name += "_legacy"
            return None
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
    if object_id in FOSSIL_BASE_IDS:
        object_id = resolve_model_id({'ObjectID': object_id, 'Message': bpy_object.get('Message', '')})
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


def new_merge_source(object_id, user_data, high_res=True, proxy_cache=None, message=None):
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
    model_id = resolve_model_id({'ObjectID': object_id, 'Message': message or ''})
    if high_res:
        bpy_object = new_high_res_object(model_id)
        if bpy_object is None:
            bpy_object = new_proxy_object(model_id, user_data, cache=proxy_cache)
    else:
        bpy_object = new_proxy_object(model_id, user_data, cache=proxy_cache)
        if bpy_object is None:
            bpy_object = new_high_res_object(model_id)

    if bpy_object is None:
        return None

    bpy_object[Part.PROP_OBJECT_ID] = object_id
    if message is not None:
        bpy_object[Part.PROP_MESSAGE] = message
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
    # Both formats use the same geometry resolver. Missing legacy FBX files
    # must not turn supported station/Corvette parts into tiny cubes.
    native = simple_library.new_object(object_id)
    if native is not None:
        blend_utils.add_to_scene(native)
        return native
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
