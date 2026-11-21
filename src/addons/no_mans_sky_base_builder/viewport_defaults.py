"""First-party viewport defaults shared by FuriousFurby's builder tools."""
import bpy


_KEY = 'FuriousFurby.relationship_line_defaults.v1'


def apply_relationship_default(space):
    """Hide native dependency lines once per viewport, honoring later UI changes.

    Blender clears driver_namespace on file load. Sharing only integer viewport
    identities keeps the two builders from overriding each other's/user choices
    without retaining RNA objects or depending on either editor implementation.
    """
    if space is None or space.type != 'VIEW_3D':
        return
    seen = bpy.app.driver_namespace.setdefault(_KEY, set())
    pointer = space.as_pointer()
    if pointer not in seen:
        space.overlay.show_relationship_lines = False
        seen.add(pointer)
