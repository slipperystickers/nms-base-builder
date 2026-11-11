"""Colouring for the models-high-res asset library.

The old material system (utils/material.py) paints a part by swapping a flat
coloured material into slot 0. That works for the flat FBX proxies, but it
throws away the real game textures and it forces one material - and therefore
one mesh datablock - per (ObjectID, UserData) pair.

The high-res library works the other way round. Every colourable material in
models-high-res/assets carries an "NMS_Colourise" node group whose four palette
slots are Attribute nodes of type OBJECT, reading the object custom properties
nms_p / nms_s / nms_t / nms_q. So the colour lives on the OBJECT, not on the
material, and colouring a part is four property writes - no material is touched
and nothing has to be duplicated.

That is what makes the whole thing cheap: a thousand placements of the same
part share ONE mesh and ONE set of materials and can still each be a different
colour. Never copy a mesh or a material just to recolour something here.

UserData layout (the same bitfield utils/userdata.py already implements):

    colour index = UserData & 0xFFFFFF      bits 8, 16, 17 are reserved
    finish index = (UserData >> 24) & 0xFF  material/finish, not colour

The colour index indexes resources/colour_palette_by_index.json, extracted from
the game's own basebuildingobjectstable and cross-checked 84/84 against
resources/DT_Palettes.csv. The JSON is the wider of the two - all 151 palettes
with all four slots, against the CSV's 120 with two. The Cosmos update
appended STATION0..35 at 115..150 for the space station parts (palette group
STATIONBASE) and left every earlier index where it was.

The finish index is handled too, out of resources/finishes.json - but read
the note at the top of that file before trusting what it looks like. The finish
names are the game's, the surface values are ours.
"""

import contextlib
import json
import os

import bpy

from ..utils import material
from ..utils import userdata
from . import corvette_trim

FILE_PATH = os.path.dirname(os.path.realpath(__file__))
RESOURCES_PATH = os.path.join(FILE_PATH, "..", "resources")

PALETTE_JSON = os.path.join(RESOURCES_PATH, "colour_palette_by_index.json")
FINISHES_JSON = os.path.join(RESOURCES_PATH, "finishes.json")

# The four object properties the NMS_Colourise node group reads, in slot order
# (primary, secondary, ternary, quaternary). These names are baked into the
# node group inside every asset file, so they cannot be renamed here alone.
SLOT_PROPS = ("nms_p", "nms_s", "nms_t", "nms_q")

# Name prefix of the colourise node group carried by every asset file.
COLOURISE_GROUP = "NMS_Colourise"

# Object properties carrying the surface finish, read by the nodes
# ensure_finish_nodes() splices into each colourable material. Both are
# offsets onto whatever the part's own texture maps say, so 0 - which is what
# an Attribute node reports for an object that has neither - means "exactly as
# the textures have it". That keeps every part that predates this unchanged.
PROP_FINISH_ROUGHNESS = "nms_finish_rough"
PROP_FINISH_METALLIC = "nms_finish_metal"

# How much of the part's own roughness to take away, 0..1.
#
# The library drives roughness from (1 - MASKS.red), and those maps are rough:
# sampled across the trims the median texel lands between 0.38 and 0.78. An
# offset can only ever add to that, so no amount of tuning the offsets could
# make a "gloss" or "polished" finish read as glossy, and a metallic finish
# came out as grey plastic - metal with no sharp reflection has very little
# else to show. This multiplies instead:
#
#     roughness = texture * (1 - polish) + offset
#
# Stored as the amount to REMOVE rather than a factor to multiply by, so that a
# missing property - which an Attribute node reports as 0 - still means "leave
# it exactly as the textures have it", the same invariant the offsets and the
# tint keep.
PROP_FINISH_POLISH = "nms_finish_polish"

# A colour the finish multiplies over the part, and how strongly.
# Kept as two properties rather than one RGBA so the "no tint" default needs
# no assumption about what an Attribute node reports for a missing alpha:
# a missing mix reads as 0, which is no tint at all.
PROP_FINISH_TINT = "nms_finish_tint"
PROP_FINISH_TINT_MIX = "nms_finish_tint_mix"

# Marks a material whose node tree has already had the finish nodes spliced
# in, so a second import does not stack a second copy on top. The value is the
# version below rather than True.
FINISH_NODES_TAG = "nms_finish_nodes"

# Bumped whenever the spliced network changes shape. A material carrying an
# older one - a scene saved before the change, whose materials came back with
# the file - is torn down and re-spliced rather than left on the old network.
FINISH_NODES_VERSION = 2

# Every node the splice adds is labelled with this, which is what lets the
# teardown find them again.
FINISH_NODE_LABEL = "NMS Finish"

# What each finish does to a part's look lives in resources/finishes.json,
# keyed on the readable finish label. It is data rather than code because the
# values are ours - see the note at the top of that file - and tuning them is
# meant to be a matter of editing a resource, not the module.
#
# Keys in the JSON that start with this are notes, not finish labels.
FINISH_META_PREFIX = "_"

# The fields a finish entry may carry, and how to read each one. Anything else
# in an entry is ignored, and an absent field means "leave that alone".
FINISH_SCALARS = ("roughness", "metallic", "tint_mix", "polish")

# The palette slots in their normal order, and under an inverting finish.
SLOT_ORDER = ("p", "s", "t", "q")
SLOT_ORDER_INVERTED = ("s", "p", "q", "t")

# Used for a finish that is not in the table - leaves the part exactly as its
# textures make it. Also what the whole table falls back to when the resource
# is missing or unreadable, so a bad edit costs the finishes and never the
# colours.
FINISH_NEUTRAL = {}

# Written onto every mesh appended from models-high-res, holding the object id
# it came from. It marks a part as belonging to the new colour system, which is
# what the old material code checks before deciding to paint a flat material
# over it. It lives here rather than in builder_v2 so that utils/material.py can
# read it without importing the importer.
MESH_TAG = "nms_high_res_id"

# Readable labels, so the viewport overlay keeps showing colour/material names.
PROP_READONLY_COLOUR = "readonly:Colour"
PROP_READONLY_MATERIAL = "readonly:Material"

# Loaded on first use rather than at import time - the addon registers a lot of
# modules and there is no point reading 47KB of JSON for a session that never
# imports a base.
_palette_by_index = None
_colour_labels = None
_finish_labels = None
_finish_table = None
_finish_stamp = None


# Palette data ---
def _load_palettes():
    """Load and cache the palette table and the readable labels.

    Both labels come from DT_Palettes.csv where it has them, because it is what
    the rest of the addon already displays and its names are the real English
    ones. The palette JSON only resolved the 16 LEGACY names when it was
    extracted - the other 99 are still internal keys like SET_FREIGHTER_7 - so
    it is the fallback for the 31 palettes the CSV doesn't cover, not the
    first choice.

    The finish label HAS to come from the CSV. In the game's own material table
    the finish index is only unique within a material group - index 1 is "Rust"
    for the legacy group and "Builders C" for the builders group - and UserData
    carries no group id to tell them apart. The CSV is keyed on the colour AND
    finish index together, which resolves it.

    Returns:
        tuple: (palette by colour index, colour label by colour index,
            finish label by (colour index, finish index))
    """
    global _palette_by_index, _colour_labels, _finish_labels
    if _palette_by_index is not None:
        return _palette_by_index, _colour_labels, _finish_labels

    with open(PALETTE_JSON, "r", encoding="utf-8") as palette_file:
        raw = json.load(palette_file)
    _palette_by_index = {int(key): value for key, value in raw.items()}

    # material.BAKED_COLOURS is the CSV, already parsed once at import time.
    _colour_labels = {}
    _finish_labels = {}
    for row in material.BAKED_COLOURS:
        try:
            colour_index = int(row[3])
            _colour_labels[colour_index] = row[5]
            _finish_labels[(colour_index, int(row[4]))] = row[2]
        except (IndexError, ValueError):
            continue

    return _palette_by_index, _colour_labels, _finish_labels


def decode_user_data(user_data_value):
    """Split a UserData value into its colour and finish indices.

    Args:
        user_data_value: The packed UserData value, int or numeric string.

    Returns:
        tuple: (colour index, finish index), or None if the value isn't a number.
    """
    try:
        value = int(user_data_value)
    except (TypeError, ValueError):
        return None
    return userdata.get_colour(value), userdata.get_material(value)


def get_palette(user_data_value):
    """Resolve a UserData value to its palette entry.

    Args:
        user_data_value: The packed UserData value.

    Returns:
        dict: {id, name_en, p, s, t, q} or None if the colour index is unknown.
    """
    indices = decode_user_data(user_data_value)
    if indices is None:
        return None
    palettes = _load_palettes()[0]
    return palettes.get(indices[0])


def get_nice_names(user_data_value):
    """Get the readable colour and finish names for a UserData value.

    Args:
        user_data_value: The packed UserData value.

    Returns:
        tuple: (colour name, finish name). Either can be None.
    """
    indices = decode_user_data(user_data_value)
    if indices is None:
        return None, None

    palettes, colour_labels, finish_labels = _load_palettes()
    colour_name = colour_labels.get(indices[0])
    if colour_name is None:
        palette = palettes.get(indices[0])
        colour_name = palette.get("name_en") if palette else None

    return colour_name, finish_labels.get(indices)


# Applying colour ---
def _read_finish(raw):
    """Read one entry of finishes.json into the shape apply_palette() wants.

    Forgiving on purpose: an entry with a bad field loses that field rather
    than the whole finish, and a bad finish loses itself rather than the file.
    This is a hand edited resource, and a typo in it should cost a preview, not
    the ability to colour a base at all.

    Args:
        raw (dict): One label's entry, straight from the JSON.

    Returns:
        dict: The fields that read cleanly. Possibly empty, never None.
    """
    if not isinstance(raw, dict):
        return {}

    finish = {}

    for field in FINISH_SCALARS:
        if field in raw:
            try:
                finish[field] = float(raw[field])
            except (TypeError, ValueError):
                pass

    tint = raw.get("tint")
    if isinstance(tint, (list, tuple)) and len(tint) >= 3:
        try:
            finish["tint"] = tuple(float(channel) for channel in tint[:3])
        except (TypeError, ValueError):
            pass

    if raw.get("invert"):
        finish["invert"] = True

    return finish


def _finish_file_stamp():
    """What the resource looked like on disk, for spotting an edit.

    Returns:
        tuple: (mtime, size), or None when it cannot be read.
    """
    try:
        info = os.stat(FINISHES_JSON)
    except OSError:
        return None
    return (info.st_mtime, info.st_size)


def _load_finishes():
    """Load and cache resources/finishes.json.

    Re-reads it by itself when the file has changed on disk. Tuning a finish is
    meant to be a matter of editing the resource and looking at the result, and
    a cache that had to be cleared by hand made it far too easy to edit the
    file, see no change, and conclude the value did nothing.

    Returns:
        dict: {finish label: finish entry}. Empty when the resource is missing
            or unreadable, which leaves every part looking exactly as its own
            textures make it - the colours still apply, only the surface
            previews are lost.
    """
    global _finish_table, _finish_stamp

    stamp = _finish_file_stamp()
    if _finish_table is not None and stamp == _finish_stamp:
        return _finish_table
    _finish_stamp = stamp

    try:
        with open(FINISHES_JSON, "r", encoding="utf-8") as finishes_file:
            raw = json.load(finishes_file)
    except (IOError, OSError, ValueError):
        # A half written or malformed file keeps the last good table rather
        # than blanking every finish mid edit.
        _finish_table = _finish_table or {}
        return _finish_table

    _finish_table = {
        label: _read_finish(entry)
        for label, entry in raw.items()
        if not label.startswith(FINISH_META_PREFIX)
    }
    return _finish_table


def get_finish_table(reload=False):
    """The finish table, loading it on first use.

    An edit to finishes.json is picked up on its own, so this rarely needs
    its argument. The new values reach parts already in the scene the next
    time they are recoloured.

    Args:
        reload (bool): Force a re-read even if the file looks unchanged.

    Returns:
        dict: {finish label: finish entry}.
    """
    global _finish_table
    if reload:
        _finish_table = None
    return _load_finishes()


def get_finish(user_data_value):
    """The finish behaviour for a UserData value.

    Args:
        user_data_value: The packed UserData value.

    Returns:
        dict: An entry from finishes.json, or FINISH_NEUTRAL. Never None.
    """
    finish_name = get_nice_names(user_data_value)[1]
    return get_finish_table().get(finish_name, FINISH_NEUTRAL)


def apply_palette(bpy_object, palette, finish=None, finish_name=None):
    """Write the four palette slots and the surface finish onto an object.

    Args:
        bpy_object (bpy.types.Object): The object to colour.
        palette (dict): A palette entry with p/s/t/q RGBA lists.
        finish (dict): An entry from finishes.json. Defaults to neutral.
        finish_name (str): Name used to select a native Corvette texture layer.
    """
    finish = finish if finish is not None else FINISH_NEUTRAL

    slots = SLOT_ORDER_INVERTED if finish.get("invert") else SLOT_ORDER
    primary = tuple(palette[slots[0]])
    if (bpy_object.get('ObjectID') in corvette_trim.GEOMETRY and
            bpy_object.data is not None and bpy_object.data.get(corvette_trim.TAG)):
        native = finish_name in corvette_trim.FINISHES
        bpy_object[corvette_trim.LAYER] = float(corvette_trim.FINISHES.index(finish_name) if native else 0)
        if native:
            # These maps already contain the material response and inverted mask.
            slots = SLOT_ORDER
            finish = FINISH_NEUTRAL
    for prop_name, slot in zip(SLOT_PROPS, slots):
        bpy_object[prop_name] = tuple(palette[slot])

    # Offsets rather than absolute values, so a part keeps the surface detail
    # its own maps give it. 0 is "unchanged", which is also what the shader
    # reads for an object that has never been given a finish.
    bpy_object[PROP_FINISH_ROUGHNESS] = float(finish.get("roughness", 0.0))
    bpy_object[PROP_FINISH_METALLIC] = float(finish.get("metallic", 0.0))
    bpy_object[PROP_FINISH_POLISH] = float(finish.get("polish", 0.0))
    bpy_object[PROP_FINISH_TINT] = tuple(finish.get("tint", (0.0, 0.0, 0.0)))
    bpy_object[PROP_FINISH_TINT_MIX] = float(finish.get("tint_mix", 0.0))

    # Solid viewport shading set to Object colour draws this, so parts can still
    # be told apart at a glance without waiting for textures. The old flat
    # material system did the same job through material.diffuse_color, but a
    # high res part shares its materials with every other placement of that id,
    # so the viewport colour has to live on the object - the same reason the
    # palette slots do. Primary is the part's body colour, so it is the one
    # that reads as "what colour is this part".
    bpy_object.color = primary


def apply(bpy_object, user_data_value, tag=True):
    """Colour a single object from a UserData value.

    Args:
        bpy_object (bpy.types.Object): The object to colour.
        user_data_value: The packed UserData value.
        tag (bool): Flag the object for a depsgraph re-evaluation. Skip this
            while bulk building - one view layer update at the end is enough.

    Returns:
        dict: The palette that was applied, or None if it didn't resolve, in
            which case the object is left untouched.
    """
    palette = get_palette(user_data_value)
    if palette is None:
        return None

    colour_name, finish_name = get_nice_names(user_data_value)
    apply_palette(bpy_object, palette, get_finish_table().get(finish_name), finish_name)
    bpy_object[PROP_READONLY_COLOUR] = colour_name or ""
    bpy_object[PROP_READONLY_MATERIAL] = finish_name or ""
    if tag:
        bpy_object.update_tag()
    return palette


def apply_many(pairs, tag=False, update=False):
    """Colour a lot of objects at once.

    Each distinct UserData value is resolved once and reused, so the per object
    cost is just the four property writes.

    Args:
        pairs (iterable): An iterable of (bpy object, UserData value).
        tag (bool): Flag each object for re-evaluation as it goes.
        update (bool): Push a single view layer update when finished.

    Returns:
        tuple: (number coloured, number whose UserData didn't resolve)
    """
    cache = {}
    applied = 0
    unresolved = 0

    for bpy_object, user_data_value in pairs:
        key = str(user_data_value)
        if key not in cache:
            names = get_nice_names(key)
            cache[key] = (get_palette(key), names,
                          get_finish_table().get(names[1], FINISH_NEUTRAL))
        palette, names, finish = cache[key]

        if palette is None:
            unresolved += 1
            continue

        apply_palette(bpy_object, palette, finish, names[1])
        bpy_object[PROP_READONLY_COLOUR] = names[0] or ""
        bpy_object[PROP_READONLY_MATERIAL] = names[1] or ""
        if tag:
            bpy_object.update_tag()
        applied += 1

    if update:
        bpy.context.view_layer.update()

    return applied, unresolved


def recolour(objects, colour_index=None, material_index=None, tag=True):
    """Repaint objects, writing the new indices into their UserData first.

    This is the replacement for material.assign_material on a high res part.
    Nothing is copied and no material is touched, so a hundred selected parts
    stay on the meshes they were already sharing - which is the whole point of
    the object property approach.

    Every bit of UserData outside the colour and finish fields is preserved,
    including the reserved ones, exactly as utils/userdata.py intends.

    Args:
        objects (iterable): The objects to repaint.
        colour_index (int): The new colour index, or None to leave it alone.
        material_index (int): The new finish index, or None to leave it alone.
        tag (bool): Flag each object for a depsgraph re-evaluation.

    Returns:
        tuple: (number coloured, number whose UserData didn't resolve)
    """
    pairs = []
    for bpy_object in objects:
        try:
            current = int(bpy_object.get("UserData", 0) or 0)
        except (TypeError, ValueError):
            current = 0

        value = userdata.update_colour_material(
            current, colour_index=colour_index, material_index=material_index
        )
        bpy_object["UserData"] = str(value)
        pairs.append((bpy_object, value))

    # A base saved before finishes were handled has materials with no finish
    # nodes in them, so the offsets below would land on nothing. Cheap to call
    # again - materials that already have them carry a marker - so the first
    # recolour after opening such a file quietly brings it up to date.
    ensure_finish_nodes(_object_materials(obj for obj, _ in pairs))

    return apply_many(pairs, tag=tag)


def recolour_from_user_data(objects, user_data_value, tag=True):
    """Repaint objects to an exact UserData value.

    The replacement for material.restore_material on a high res part - used
    when the value is already known, such as the colour picker copying one
    part's look onto another.

    A value that doesn't resolve to a palette - None, or an index outside the
    table - leaves every object completely untouched, rather than stamping an
    unusable value into their UserData.

    Args:
        objects (iterable): The objects to repaint.
        user_data_value: The packed UserData value to apply wholesale.
        tag (bool): Flag each object for a depsgraph re-evaluation.

    Returns:
        tuple: (number coloured, number whose UserData didn't resolve)
    """
    objects = list(objects)

    # one value for all of them, so resolve it once and bail if it is no good
    palette = get_palette(user_data_value)
    if palette is None:
        return 0, len(objects)

    colour_name, finish_name = get_nice_names(user_data_value)
    finish = get_finish_table().get(finish_name, FINISH_NEUTRAL)
    value = str(user_data_value)

    # see recolour() - keeps an older file working the moment it is touched
    ensure_finish_nodes(_object_materials(objects))

    for bpy_object in objects:
        bpy_object["UserData"] = value
        apply_palette(bpy_object, palette, finish, finish_name)
        bpy_object[PROP_READONLY_COLOUR] = colour_name or ""
        bpy_object[PROP_READONLY_MATERIAL] = finish_name or ""
        if tag:
            bpy_object.update_tag()

    return len(objects), 0


def clear(bpy_object):
    """Strip the colour properties, returning an object to its raw textures.

    An absent slot property reads as black inside the node group, so removing
    them also clears any stale colour rather than leaving it half applied.

    Args:
        bpy_object (bpy.types.Object): The object to clear.
    """
    for prop in SLOT_PROPS:
        if prop in bpy_object:
            del bpy_object[prop]
    bpy_object.update_tag()


def use_object_colour_in_viewport(enable=True, only_solid=True):
    """Point Solid viewport shading at the per object colour.

    Blender's Solid mode defaults to colouring by MATERIAL, which is what made
    the old flat material system readable - every part had its own material
    carrying its diffuse_color. High res parts share their materials, so under
    MATERIAL they all draw the same and the scene turns into one grey mass.
    OBJECT reads object.color instead, which both libraries now set.

    Textured and Rendered shading are unaffected either way - this only changes
    what Solid mode paints with.

    Args:
        enable (bool): True for OBJECT colour, False back to MATERIAL.
        only_solid (bool): Skip viewports that aren't in Solid shading, so a
            viewport somebody has deliberately put in Material Preview or
            Rendered is left alone.

    Returns:
        int: How many viewports were changed. Zero in background mode, which
            has no windows.
    """
    colour_type = "OBJECT" if enable else "MATERIAL"
    changed = 0

    window_manager = getattr(bpy.context, "window_manager", None)
    if window_manager is None:
        return 0

    for window in window_manager.windows:
        for area in window.screen.areas:
            if area.type != "VIEW_3D":
                continue
            for space in area.spaces:
                if space.type != "VIEW_3D":
                    continue
                shading = space.shading
                if only_solid and shading.type != "SOLID":
                    continue
                if shading.color_type != colour_type:
                    shading.color_type = colour_type
                    changed += 1
    return changed


def is_high_res(bpy_object):
    """Check whether an object came out of the models-high-res library.

    This is the test the old material code uses to decide whether it may paint
    a flat material over something. It asks where the part came from rather
    than whether it happens to be colourable, because a high res part with no
    colourable material still must not be flattened - in game those parts just
    cannot be recoloured.

    Args:
        bpy_object (bpy.types.Object): The object to test.

    Returns:
        bool: True if its mesh carries the high res marker.
    """
    data = getattr(bpy_object, "data", None)
    return data is not None and MESH_TAG in data


def is_colourable(bpy_object):
    """Check whether an object actually responds to the colour properties.

    Args:
        bpy_object (bpy.types.Object): The object to test.

    Returns:
        bool: True if any of its materials carries the colourise node group.
    """
    for slot in bpy_object.material_slots:
        material_data = slot.material
        if material_data is None or material_data.node_tree is None:
            continue
        for node in material_data.node_tree.nodes:
            if node.type != "GROUP" or node.node_tree is None:
                continue
            if node.node_tree.name.startswith(COLOURISE_GROUP):
                return True
    return False


# Datablock sharing ---
#
# Appending is per file, and Blender has no idea that two asset files reference
# the same texture on disk or carry the same node group - it just appends both
# copies and renames the second one .001. Over a whole base that is the single
# biggest source of wasted memory, because textures are ~98% of the scene.
#
# Measured on 100 distinct assets / 6000 placed parts:
#   without dedupe   692 images, 67 node groups, 2580 MB, 6.96s to load textures
#   with dedupe      333 images,  1 node group,  1092 MB, 2.51s to load textures
#
# So it is worth roughly 2.4x the RAM and 2.8x the texture load time, for about
# a second of work at the end of an import. Materials are deliberately left
# alone - they are cheap once they share their images, and two same named
# materials from different assets are not guaranteed to be identical.
def _splice_finish_roughness(node_tree, socket):
    """Let a finish both polish and roughen whatever already feeds Roughness.

    Roughness gets a proportional term as well as an offset - see
    PROP_FINISH_POLISH for why an offset alone could not produce a gloss:

        roughness = texture * (1 - polish) + offset

    clamped back into 0..1. With both properties absent, which is what an
    Attribute node reports for an object that has never been given a finish,
    this is texture * 1 + 0 - exactly the value the maps carry.

    Args:
        node_tree (bpy.types.NodeTree): The material's node tree.
        socket (bpy.types.NodeSocket): The Principled Roughness input.
    """
    nodes = node_tree.nodes
    links = node_tree.links
    origin = socket.node.location

    polish = nodes.new("ShaderNodeAttribute")
    polish.attribute_type = 'OBJECT'
    polish.attribute_name = PROP_FINISH_POLISH
    polish.label = FINISH_NODE_LABEL + " Polish"
    polish.location = (origin.x - 900, origin.y - 400)

    # (1 - polish), so the stored 0 means "keep all of it"
    keep = nodes.new("ShaderNodeMath")
    keep.operation = 'SUBTRACT'
    keep.label = FINISH_NODE_LABEL + " Polish"
    keep.location = (origin.x - 620, origin.y - 400)
    keep.inputs[0].default_value = 1.0
    links.new(polish.outputs["Fac"], keep.inputs[1])

    offset = nodes.new("ShaderNodeAttribute")
    offset.attribute_type = 'OBJECT'
    offset.attribute_name = PROP_FINISH_ROUGHNESS
    offset.label = FINISH_NODE_LABEL + " Roughness"
    offset.location = (origin.x - 620, origin.y - 620)

    # texture * keep + offset. inputs are (Value, Multiplier, Addend), all
    # named "Value", so they go by index.
    combine = nodes.new("ShaderNodeMath")
    combine.operation = 'MULTIPLY_ADD'
    combine.use_clamp = True
    combine.label = FINISH_NODE_LABEL + " Roughness"
    combine.location = (origin.x - 300, origin.y - 400)

    existing = socket.links[0].from_socket if socket.is_linked else None
    if existing is not None:
        links.new(existing, combine.inputs[0])
    else:
        combine.inputs[0].default_value = socket.default_value

    links.new(keep.outputs["Value"], combine.inputs[1])
    links.new(offset.outputs["Fac"], combine.inputs[2])
    links.new(combine.outputs["Value"], socket)


def _is_finish_node(node):
    """True for a node the splice added."""
    return (node.label or "").startswith(FINISH_NODE_LABEL)


def _unsplice(socket):
    """Put back whatever fed `socket` before the finish nodes went in.

    Every node the splice puts in front of a Principled input takes the
    original on its first usable input - inputs[0] on a Math node, "A" on the
    Mix - so undoing one is a matter of reading that back out. The nodes
    themselves are left for the caller to remove once every socket is done.

    Args:
        socket (bpy.types.NodeSocket): The Principled input to restore.
    """
    if not socket.is_linked:
        return

    spliced = socket.links[0].from_node
    if not _is_finish_node(spliced):
        return

    carried = spliced.inputs["A" if spliced.bl_idname == "ShaderNodeMix" else 0]
    node_tree = socket.node.id_data
    node_tree.links.remove(socket.links[0])

    if carried.is_linked:
        node_tree.links.new(carried.links[0].from_socket, socket)
    else:
        socket.default_value = carried.default_value


def _clear_finish_nodes(node_tree, principled):
    """Strip a previous version's finish network out of a material.

    Args:
        node_tree (bpy.types.NodeTree): The material's node tree.
        principled (bpy.types.Node): Its Principled BSDF.
    """
    for name in ("Roughness", "Metallic", "Base Color"):
        _unsplice(principled.inputs[name])

    for node in [n for n in node_tree.nodes if _is_finish_node(n)]:
        node_tree.nodes.remove(node)


def _splice_finish_offset(node_tree, socket, attribute_name, label):
    """Add an object attribute onto whatever already feeds `socket`.

    The Principled BSDF's Roughness and Metallic are driven by the part's own
    texture maps, and those maps are shared by every placement of that part - so
    the finish cannot be baked into them any more than the colour can. This adds
    the object property on top instead, the same trick the colour slots use, and
    clamps the result back into 0..1.

    Args:
        node_tree (bpy.types.NodeTree): The material's node tree.
        socket (bpy.types.NodeSocket): The Principled input to drive.
        attribute_name (str): The object property carrying the offset.
        label (str): Label for the added nodes, so they are findable by hand.
    """
    nodes = node_tree.nodes
    links = node_tree.links

    attribute = nodes.new("ShaderNodeAttribute")
    attribute.attribute_type = 'OBJECT'
    attribute.attribute_name = attribute_name
    attribute.label = label
    attribute.location = (socket.node.location.x - 600,
                          socket.node.location.y - 400)

    add = nodes.new("ShaderNodeMath")
    add.operation = 'ADD'
    add.use_clamp = True
    add.label = label
    add.location = (socket.node.location.x - 300,
                    socket.node.location.y - 400)

    # whatever was feeding the socket becomes the first term - a texture, or the
    # value that was typed into it if nothing was linked
    existing = socket.links[0].from_socket if socket.is_linked else None
    if existing is not None:
        links.new(existing, add.inputs[0])
    else:
        add.inputs[0].default_value = socket.default_value

    links.new(attribute.outputs["Fac"], add.inputs[1])
    links.new(add.outputs["Value"], socket)


def _splice_finish_tint(node_tree, socket):
    """Wash a finish colour over whatever already feeds Base Color.

    Rust is a colour as much as a roughness, and the part's own diffuse map
    cannot carry it - that map is shared by every placement. So the tint goes
    on as a mix at the end of the chain, driven by two object properties, the
    same way the palette and the roughness are.

    Args:
        node_tree (bpy.types.NodeTree): The material's node tree.
        socket (bpy.types.NodeSocket): The Principled Base Color input.
    """
    nodes = node_tree.nodes
    links = node_tree.links

    colour = nodes.new("ShaderNodeAttribute")
    colour.attribute_type = 'OBJECT'
    colour.attribute_name = PROP_FINISH_TINT
    colour.label = FINISH_NODE_LABEL + " Tint"
    colour.location = (socket.node.location.x - 900, socket.node.location.y + 300)

    amount = nodes.new("ShaderNodeAttribute")
    amount.attribute_type = 'OBJECT'
    amount.attribute_name = PROP_FINISH_TINT_MIX
    amount.label = FINISH_NODE_LABEL + " Tint Mix"
    amount.location = (socket.node.location.x - 900, socket.node.location.y + 120)

    mix = nodes.new("ShaderNodeMix")
    mix.data_type = 'RGBA'
    # MULTIPLY, not MIX. Mixing towards a flat colour washes the panel lines,
    # decals and paint straight off the part - 60% towards a rust brown turned
    # a hull into a smooth terracotta shape. Multiplying darkens and shifts the
    # hue while every bit of that detail survives underneath.
    mix.blend_type = 'MULTIPLY'
    mix.clamp_factor = True
    mix.label = FINISH_NODE_LABEL + " Tint"
    mix.location = (socket.node.location.x - 300, socket.node.location.y + 220)

    existing = socket.links[0].from_socket if socket.is_linked else None
    if existing is not None:
        links.new(existing, mix.inputs["A"])
    else:
        mix.inputs["A"].default_value = socket.default_value

    links.new(amount.outputs["Fac"], mix.inputs["Factor"])
    links.new(colour.outputs["Color"], mix.inputs["B"])
    links.new(mix.outputs["Result"], socket)


# Bulk builds ---
#
# dedupe_appended_data() and the no-argument form of ensure_finish_nodes() both
# walk every material node tree in the file. That is the right cost to pay once
# at the end of an import, and the wrong one to pay per part: builder_v2's
# add_part() calls all of them for every single part it places, so a scene wide
# rebuild - a proxy quality switch, a batch replace - spends most of its time
# rescanning a library that only the last pass could have changed.
#
# Inside defer_shared_data() they record that they were wanted and return
# immediately, and leaving the block runs each of them once.
_defer_depth = 0
_defer_pending = False
_relink_pending = False


@contextlib.contextmanager
def defer_shared_data():
    """Collapse the whole-library passes inside a bulk build into one each.

    Nests: only the outermost block runs the deferred passes, so a caller can
    wrap a batch without caring whether something inside it does the same.

    Nothing is deferred that a caller asked for explicitly - passing a
    materials list to ensure_finish_nodes() still does exactly that work, since
    that form is already scoped to what changed.
    """
    global _defer_depth, _defer_pending
    _defer_depth += 1
    try:
        yield
    finally:
        _defer_depth -= 1
        if _defer_depth == 0 and _defer_pending:
            _defer_pending = False
            # dedupe first, so the surviving shared materials are the ones
            # that get the finish nodes rather than copies about to be thrown
            # away - the same order deserialise_from_data uses.
            dedupe_appended_data()
            ensure_finish_nodes()


def _defer():
    """Record that a deferred pass was wanted. True if it should be skipped."""
    global _defer_pending
    if not _defer_depth:
        return False
    _defer_pending = True
    return True


def note_appended_data():
    """Record that an asset was appended, for whatever tidy up comes next.

    Appending brings its own copies of the asset's textures and of the
    colourise node group with it, and both have to be collapsed onto the ones
    already in the file before the finish nodes are spliced in. Inside
    defer_shared_data() this is what schedules that single pass at the end.

    Outside one it deliberately does nothing: the callers that append without
    deferring - builder_v2.add_part, builder_v2.deserialise_from_data - already
    run the passes themselves, and running them here as well would put the per
    asset cost back that deferring exists to remove.
    """
    global _relink_pending
    _relink_pending = True
    _defer()


def _object_materials(objects):
    """Only touched objects need finish upgrades; preserve object slot overrides."""
    return {slot.material for obj in objects for slot in obj.material_slots
            if slot.material is not None}


def ensure_finish_nodes(materials=None):
    """Give materials the nodes that let a finish change their surface.

    Idempotent and cheap to call again: a material that already carries the
    nodes is skipped by its marker, so re-importing an asset does not stack a
    second copy of them.

    Args:
        materials (iterable): Materials to fix up. Defaults to all of them.

    Returns:
        int: How many materials were changed.
    """
    if materials is None and _defer():
        return 0

    materials = materials if materials is not None else bpy.data.materials

    changed = 0
    for mat in materials:
        if mat is None or not mat.node_tree:
            continue

        # Older building assets connected the gloss channel directly to
        # Roughness. Repair it independently of finish-network version so
        # existing .blend files receive the same fix as newly appended parts.
        repaired_roughness = _repair_building_roughness(mat)
        version = mat.get(FINISH_NODES_TAG)
        if version == FINISH_NODES_VERSION:
            changed += int(repaired_roughness)
            continue

        # Only the materials that carry the colourise group. That keeps this off
        # the flat proxy materials and off anything of the user's own, and it
        # also leaves a part's non-paintable materials - its lights and its glass
        # - alone, which is right: a weathered finish should dull the hull, not
        # the lamps set into it.
        if not any(node.type == 'GROUP' and node.node_tree
                   and node.node_tree.name.startswith(COLOURISE_GROUP)
                   for node in mat.node_tree.nodes):
            continue

        principled = next((node for node in mat.node_tree.nodes
                           if node.type == 'BSDF_PRINCIPLED'), None)
        if principled is None:
            # not a shaded material - nothing a finish could act on
            continue

        # A material carrying an older network - almost always one that came
        # back with a saved scene - is stripped before being rebuilt, so the
        # new shape replaces it instead of stacking on top of it.
        if version:
            _clear_finish_nodes(mat.node_tree, principled)

        _splice_finish_roughness(mat.node_tree, principled.inputs["Roughness"])
        _splice_finish_offset(mat.node_tree, principled.inputs["Metallic"],
                              PROP_FINISH_METALLIC,
                              FINISH_NODE_LABEL + " Metallic")
        _splice_finish_tint(mat.node_tree, principled.inputs["Base Color"])

        mat[FINISH_NODES_TAG] = FINISH_NODES_VERSION
        changed += 1

    return changed


def _repair_building_roughness(mat):
    """Restore verified building materials' gloss-to-roughness conversion.

    The shipped interior and alloy floor assets use MASKS.red directly, although the
    material's roughness is (1 - red) * gMaterialParamsVec4.x. The current
    InteriorTiling multiplier is 1.0; the alloy floor and stair use 0.9.
    Preserve an existing multiplier and the object's finish adjustments.

    Match the native material and the actual unmodified input connection,
    rather than a Blender material name. This fixes every shared/copy instance
    while leaving custom networks, other materials and finish choices alone.
    """
    path = str(mat.get("nms_material_path", "")).replace("\\", "/").upper()
    verified_materials = {
        "/CUBEROOM_INNERWALL/INTERIORTILING_MAT2.MATERIAL.MBIN":
            "INTERIORTILINGTEXTURE.MASKS",
        "/FIBREGLASS/BASIC_FLOOR/KITBASHMETALTRIMMAT.MATERIAL.MBIN":
            "FIBERGLASSTRIM.MASKS",
        "/FIBREGLASS/BASIC_RAMP_THIN/METALTRIMMAT.MATERIAL.MBIN":
            "FIBERGLASSTRIM.MASKS",
    }
    texture_name = next((name for suffix, name in verified_materials.items()
                         if path.startswith("MODELS/") and path.endswith(suffix)), None)
    if texture_name is None:
        return False
    principled = next((n for n in mat.node_tree.nodes
                       if n.type == 'BSDF_PRINCIPLED'), None)
    if principled is None:
        return False
    target = principled.inputs["Roughness"]
    # Finish nodes carry the original surface value on their first input.
    # Change that original only; user-selected finish offsets still apply.
    while target.is_linked and _is_finish_node(target.links[0].from_node):
        target = target.links[0].from_node.inputs[0]
    # The native .9 alloy multiplier was correctly retained by the asset
    # generator. Invert the texture before it, without changing the scale.
    if target.is_linked:
        scaled = target.links[0].from_node
        if scaled.type == 'MATH' and scaled.operation == 'MULTIPLY':
            if scaled.inputs[1].is_linked:
                return False
            target = scaled.inputs[0]
    if not target.is_linked:
        return False
    source = target.links[0].from_socket
    separate = source.node
    if separate.type not in {'SEPARATE_COLOR', 'SEPRGB'} or source.name not in {'Red', 'R'}:
        return False
    if not separate.inputs[0].is_linked:
        return False
    texture = separate.inputs[0].links[0].from_node
    image = getattr(texture, "image", None)
    if image is None:
        return False
    filename = os.path.basename(image.filepath.replace("\\", "/")).upper()
    if filename not in {texture_name + '.WEBP', texture_name + '.DDS'}:
        return False
    invert = mat.node_tree.nodes.new("ShaderNodeMath")
    invert.operation = 'SUBTRACT'
    invert.label = "NMS Building Gloss to Roughness"
    invert.location = (separate.location.x + 180, separate.location.y - 160)
    invert.inputs[0].default_value = 1.0
    mat.node_tree.links.new(source, invert.inputs[1])
    mat.node_tree.links.new(invert.outputs[0], target)
    return True


def dedupe_appended_data(*, only_if_pending=False):
    """Collapse the datablocks the appends duplicated.

    Call this once, after a whole batch of assets is appended, never per asset
    - the cost is one walk over every material node tree, so doing it once for
    100 assets is 100x cheaper than doing it as they arrive.

    Returns:
        tuple: (images removed, node groups removed)
    """
    if only_if_pending and not _relink_pending:
        return 0, 0
    if _defer():
        return 0, 0

    image_map = _plan_image_dedupe()
    group_map = _plan_node_group_dedupe()

    if image_map or group_map:
        _repoint_nodes(image_map, group_map)

    # one batch_remove for both - see _remove_dead
    dead_images = _collect_dead(image_map)
    dead_groups = _collect_dead(group_map)
    if dead_images or dead_groups:
        bpy.data.batch_remove(dead_images + dead_groups)
    dedupe_native_materials()
    return len(dead_images), len(dead_groups)
# Compare actual shader state, never only its native filename: builders may
# have edited a material, and two native parts can use different parameters.
_SIGNATURE_UI = {'name', 'name_full', 'label', 'location', 'width', 'height',
                 'dimensions', 'select', 'show_options', 'show_preview',
                 'show_texture', 'hide', 'use_custom_color', 'color'}


def _shader_settings(value):
    result = []
    for prop in value.bl_rna.properties:
        name = prop.identifier
        if name in _SIGNATURE_UI or prop.is_readonly:
            continue
        if prop.type in {'BOOLEAN', 'INT', 'FLOAT', 'STRING', 'ENUM'}:
            setting = getattr(value, name)
            if getattr(prop, 'is_array', False):
                setting = tuple(setting)
            elif isinstance(setting, set):
                setting = frozenset(setting)
            result.append((name, setting))
    return tuple(result)


def _native_material_signature(mat):
    tree = mat.node_tree
    if not tree or mat.animation_data or tree.animation_data:
        return None
    # Keep unsupported/custom graph features separate instead of guessing.
    nodes = list(tree.nodes)
    indices = {node: i for i, node in enumerate(nodes)}
    description = []
    for node in nodes:
        pointers = []
        for prop in node.bl_rna.properties:
            if prop.type != 'POINTER' or prop.identifier in {'rna_type', 'parent'}:
                continue
            value = getattr(node, prop.identifier)
            if value is None:
                pointers.append((prop.identifier, None))
            elif isinstance(value, bpy.types.ID):
                pointers.append((prop.identifier, value.as_pointer()))
            elif prop.identifier in {'texture_mapping', 'image_user'}:
                pointers.append((prop.identifier, _shader_settings(value)))
            elif prop.identifier == 'color_mapping' and not value.use_color_ramp:
                pointers.append((prop.identifier, _shader_settings(value)))
            else:
                return None
        defaults = []
        for socket in list(node.inputs) + list(node.outputs):
            value = getattr(socket, 'default_value', None)
            if value is not None and not isinstance(value, (bool, int, float, str)):
                try:
                    value = tuple(value)
                except TypeError:
                    return None
            defaults.append((socket.identifier, value))
        description.append((node.bl_idname, _shader_settings(node), tuple(pointers),
                            tuple(defaults), repr(sorted(node.id_properties_ensure().to_dict().items()))))
    links = tuple(sorted((indices[x.from_node], x.from_socket.identifier,
                          indices[x.to_node], x.to_socket.identifier)
                         for x in tree.links))
    return (_shader_settings(mat), repr(sorted(mat.id_properties_ensure().to_dict().items())),
            repr(sorted(tree.id_properties_ensure().to_dict().items())),
            tuple(description), links)


def dedupe_native_materials():
    """Share byte-equivalent shader settings; keep geometry and textures intact."""
    families = {}
    for mat in bpy.data.materials:
        path = mat.get('nms_material_path')
        if path and mat.use_nodes and not mat.library:
            families.setdefault(path, []).append(mat)
    duplicates = {}
    for candidates in families.values():
        if len(candidates) < 2:
            continue
        # Normalize older/newly appended finish nodes before comparing graphs.
        ensure_finish_nodes(candidates)
        by_signature = {}
        for mat in candidates:
            key = _native_material_signature(mat)
            if key is None:
                continue
            canonical = by_signature.get(key)
            if canonical is None:
                by_signature[key] = mat
            else:
                duplicates[mat] = canonical
    return _remove_dead(duplicates)


def dedupe_images():
    """Collapse image datablocks that point at the same file on disk.

    Returns:
        int: How many duplicate image datablocks were removed.
    """
    image_map = _plan_image_dedupe()
    if not image_map:
        return 0
    _repoint_nodes(image_map, None)
    return _remove_dead(image_map)


def dedupe_node_groups():
    """Collapse every appended copy of the colourise node group into one.

    Every asset file carries its own copy, so appending N assets leaves
    NMS_Colourise.001 ... .00N behind. They are identical by construction.

    Returns:
        int: How many duplicate groups were removed.
    """
    group_map = _plan_node_group_dedupe()
    if not group_map:
        return 0
    _repoint_nodes(None, group_map)
    return _remove_dead(group_map)


def _plan_image_dedupe():
    """Build {duplicate image: canonical image} for images sharing a file."""
    global _relink_pending
    if _relink_pending:
        from .. import hd_library
        hd_library.relink_texture_images()
        _relink_pending = False
    canonical_by_path = {}
    duplicates = {}

    for image in bpy.data.images:
        filepath = image.filepath
        if not filepath:
            continue
        key = os.path.normcase(bpy.path.abspath(filepath))
        canonical = canonical_by_path.get(key)
        if canonical is None:
            canonical_by_path[key] = image
        else:
            duplicates[image] = canonical

    return duplicates


def _plan_node_group_dedupe(prefix=COLOURISE_GROUP):
    """Build {duplicate group: canonical group} for the colourise copies."""
    groups = sorted(
        (group for group in bpy.data.node_groups if group.name.startswith(prefix)),
        key=lambda group: group.name,
    )
    if len(groups) < 2:
        return {}

    canonical = groups[0]
    return {group: canonical for group in groups[1:]}


def _repoint_nodes(image_map, group_map):
    """Swap every duplicate reference in every material for its canonical.

    One pass handles images and node groups together, because the walk itself
    is the expensive part - the node trees of a hundred appended assets are a
    few thousand nodes and every attribute read crosses into Blender.
    """
    for material_data in bpy.data.materials:
        node_tree = material_data.node_tree
        if node_tree is None:
            continue
        for node in node_tree.nodes:
            node_type = node.type
            if image_map and node_type == "TEX_IMAGE":
                canonical = image_map.get(node.image)
                if canonical is not None:
                    node.image = canonical
            elif group_map and node_type == "GROUP":
                canonical = group_map.get(node.node_tree)
                if canonical is not None:
                    node.node_tree = canonical


def _collect_dead(duplicate_map):
    """List the duplicates nothing points at any more.

    Anything the node walk didn't reach - a fake user, a reference from
    somewhere outside the material trees - is handed to user_remap first, so a
    datablock is never dropped while something still needs it.
    """
    dead = []
    for duplicate, canonical in duplicate_map.items():
        if duplicate.users:
            duplicate.user_remap(canonical)
        if duplicate.users == 0:
            dead.append(duplicate)
    return dead


def _remove_dead(duplicate_map):
    """Drop every duplicate nothing points at any more.

    batch_remove() rather than a remove() per datablock: removing one at a time
    rescans the whole file for users each time, which costs 0.54s for the ~400
    duplicates a 100 asset base leaves behind, against 0.006s for the batch.

    Returns:
        int: How many datablocks were removed.
    """
    if not duplicate_map:
        return 0
    dead = _collect_dead(duplicate_map)
    bpy.data.batch_remove(dead)
    return len(dead)
