"""Rebuild a variant part out of the asset it is a variant of.

Most of the corvette variants shipped in models-high-res are the wrong mesh -
the id says (Y_N) and the asset is something else. What is not wrong is the
relationship between a variant and its root: resources/objects_map.json records,
for every variant, the rigid transform that turns the root's mesh into the
variant's, measured off the assets themselves.

So rather than trusting the variant's own asset, we take the root's asset and
apply that transform to a copy of its mesh. Only variants flagged
``reproducible`` are handled here - the wall tier variants ((BASE)/(MID)/(TOP))
carry a best fit transform that is genuinely a different mesh, and those keep
the asset they ship with.

The transform is in the asset's own stored space (Y up - the library carries a
baked -90 about X), so it applies straight to the mesh, before any of the
object level rotation the builder puts on top.
"""

import json
import os
import re

import mathutils

RESOURCES_DIR = os.path.realpath(
    os.path.join(os.path.dirname(__file__), "..", "resources")
)

OBJECTS_MAP = os.path.join(RESOURCES_DIR, "objects_map.json")

# Keys in the json that are metadata rather than object ids.
META_PREFIX = "_"

# The wall tier suffix a nice name can carry. A variant whose tier differs from
# its root's is a different mesh however good the fit looks - the mid tier of a
# wall has its own detailing, it is not the base tier moved. objects_map.json
# flags most of these ``reproducible: false`` already, but 97 of them slipped
# through with a near identity transform and a residual up to 2%, so they are
# caught here by name instead. With this guard the worst residual left in the
# table is 1.2%, and that one is a genuine mirror pair.
TIER_SUFFIX = re.compile(r"\((BASE|MID|TOP)\)\s*$")

# The four NW fuel-pod rim assets have their own correctly oriented HD meshes.
# Their historical root transforms do not reproduce those meshes, so loading
# the asset is safer than rebuilding it from the NE part.
OWN_ASSET_VARIANTS = {'B_STR_T_NWTB', 'B_STR_T_NWTB1',
                      'B_STR_T_NWTB2', 'B_STR_T_NWTB3',
                      'B_WNG_O_0_R'}


def _tier(nice_name):
    match = TIER_SUFFIX.search(nice_name or "")
    return match.group(1) if match else None

# {variant id: (root id, 4x4 mesh space matrix)}, built once per session.
_rebuild_table = None


def _build_table():
    """Read objects_map.json into the only shape this module needs.

    Returns:
        dict: {variant id: (root id, mathutils.Matrix)}. Empty when the
            resource is missing or unreadable, which just means nothing gets
            rebuilt and every id is served by its own asset.
    """
    table = {}

    if not os.path.isfile(OBJECTS_MAP):
        return table

    try:
        with open(OBJECTS_MAP, "r") as map_file:
            document = json.load(map_file)
    except (IOError, ValueError):
        return table

    patterns = document.get("%spatterns" % META_PREFIX, {})

    for object_id, record in document.items():
        if object_id.startswith(META_PREFIX):
            continue
        if not record.get("is_variant") or not record.get("reproducible"):
            continue
        if object_id in OWN_ASSET_VARIANTS:
            continue

        # recreate_from, not variant_of: where a variant is a variant of a
        # variant the transform is measured against the root, so this never
        # has to be rebuilt in stages
        root_id = record.get("recreate_from") or record.get("variant_of")
        pattern = patterns.get(record.get("pattern"))
        if not root_id or pattern is None:
            continue

        root_record = document.get(root_id)
        if root_record is None:
            continue
        if _tier(record.get("nice_name")) != _tier(root_record.get("nice_name")):
            continue

        rotation = pattern.get("matrix")
        if rotation is None:
            continue

        # absent when it is zero
        translation = record.get("translation") or [0.0, 0.0, 0.0]

        matrix = mathutils.Matrix.Identity(4)
        for row in range(3):
            for column in range(3):
                matrix[row][column] = float(rotation[row][column])
            matrix[row][3] = float(translation[row])

        table[object_id] = (root_id, matrix)

    # Native placement locators take precedence over historical mesh fits.
    # These Vesper transforms were audited against the installed game's
    # placement entities and part-style mapping (including NE/NW swaps).
    native_path = os.path.join(RESOURCES_DIR, "native_variant_transforms.json")
    if os.path.isfile(native_path):
        with open(native_path, "r") as handle:
            for object_id, entry in json.load(handle).items():
                table[object_id] = (entry["root"], mathutils.Matrix(entry["matrix"]))
    return table


def get_rebuild_table(rebuild=False):
    global _rebuild_table

    if _rebuild_table is None or rebuild:
        _rebuild_table = _build_table()

    return _rebuild_table


def get_rebuild(object_id):
    """How to rebuild one id from another part's mesh.

    Args:
        object_id (str): The part being placed.

    Returns:
        tuple: (root object id, 4x4 mathutils.Matrix to apply to a copy of the
            root's mesh), or None when this id is not a reproducible variant
            and should be served by its own asset.
    """
    return get_rebuild_table().get(object_id.replace("^", ""))
