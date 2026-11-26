"""Ownership tags for editable curve arrays shared through .blend files.

Both builders can evaluate Blender's native Follow Path constraints. Only the
builder that owns the distribution should regenerate their offsets.
"""
import bpy
from bpy.app.handlers import persistent

GUIDE = "bbe_curve_id"
LINKED = "bbe_has_linked_objects"
PARENT = "bbe_curve_parent"


def guide_id(obj):
    return obj.get(GUIDE) or obj.get("CurveID")


def has_followers(obj):
    return obj.get(LINKED) or obj.get("has_linked_objects", False)


def parent_name(obj):
    return obj.get(PARENT) or obj.get("curve_parent")


def link_follower(obj, guide):
    # The seed may itself have been copied from an array with the other format.
    if GUIDE in guide:
        obj.pop("curve_parent", None)
        obj[PARENT] = guide.name
    else:
        obj.pop(PARENT, None)
        obj["curve_parent"] = guide.name


def protect_guide(guide):
    """Adopt a BBE distribution written with the old shared tags."""
    for old, new in (("CurveID", GUIDE), ("has_linked_objects", LINKED)):
        if old in guide:
            guide[new] = guide.pop(old)


@persistent
def protect_legacy_arrays(_unused):
    # Standalone-authored guides have none of these distribution settings.
    # Keep their native editing controls when a user simply resaves in BBE.
    guides = set()
    for guide in bpy.data.objects:
        if (guide.type == 'CURVE' and guide.library is None
                and guide.get("has_linked_objects") and "CurveID" in guide
                and any(key in guide for key in (
                    "dup_curve_start_alignment", "dup_source_transform",
                    "bbe_size_spacing", "bbe_curve_spacing", "bbe_edge_anchor"))):
            protect_guide(guide)
            guides.add(guide.name)
    if guides:
        for obj in bpy.data.objects:
            if obj.library is None and obj.get("curve_parent") in guides:
                obj[PARENT] = obj.pop("curve_parent")
