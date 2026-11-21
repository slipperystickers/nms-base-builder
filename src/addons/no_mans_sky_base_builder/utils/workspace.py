
import bpy


# Workspace Cleanup
def cleanup_workspace(context) -> None:
    
    new_workspace_name = "No Man's Sky Base & Corvette Builder"
    
    layout_ws = bpy.data.workspaces.get("Layout")
    if layout_ws is None:
        return

    # Snapshot list before iterating because collection changes during deletion
    other_workspaces = [ws for ws in bpy.data.workspaces if ws != layout_ws]
    for ws in other_workspaces:
        with bpy.context.temp_override(workspace=ws):
            bpy.ops.workspace.delete()

    # switch to Layout and rename it
    win = context.window
    win.workspace = layout_ws
    layout_ws.name = new_workspace_name
    
    # active screen after the workspace switch
    screen = win.screen
    
    # take a snapshot of the areas we want to close in one pass
    areas_to_close = [
        area for area in screen.areas 
        if area.type == "PROPERTIES" or 
        (area.type == "DOPESHEET_EDITOR" and area.spaces.active.mode == "TIMELINE")
    ]
    
    # close areas
    for area in areas_to_close:
        with bpy.context.temp_override(window=win, screen=screen, area=area):
            bpy.ops.screen.area_close()
            
    # Hide status bar
    for s in bpy.data.screens:
        s.show_statusbar = False

    # Trim the viewport toolbar down to what base building actually uses.
    hide_viewport_tools(context)
        


# Toolbar Cleanup
# Tools stripped out of the 3D viewport toolbar when the workspace is
# simplified - none of them are useful for base building and they only make the
# toolbar harder to read.
HIDDEN_VIEW3D_TOOLS = {
    "builtin.annotate",
    "builtin.annotate_line",
    "builtin.annotate_polygon",
    "builtin.annotate_eraser",
    "builtin.measure",
    "builtin.primitive_cube_add",
    "builtin.primitive_cone_add",
    "builtin.primitive_cylinder_add",
    "builtin.primitive_uv_sphere_add",
    "builtin.primitive_ico_sphere_add",
}

# Blender's own VIEW3D_PT_tools_active.tools_from_context, kept so the toolbar
# can be put back exactly as it shipped.
_ORIGINAL_TOOLS_FROM_CONTEXT = None


def _strip_tool_items(items):
    """Drop every hidden tool from one entry list of a toolbar `_tools` dict.

    Entries are either `None` (a separator), a `ToolDef`, a tuple of `ToolDef`
    forming a fallback group, or a callable that builds a group at draw time.
    `ToolDef` is itself a namedtuple, so it has to be tested before tuples.
    """
    result = []
    for item in items:
        if item is None:
            # Only keep a separator that follows something we kept.
            if result and result[-1] is not None:
                result.append(None)
            continue

        if hasattr(item, "idname"):
            if item.idname not in HIDDEN_VIEW3D_TOOLS:
                result.append(item)
            continue

        if isinstance(item, (tuple, list)):
            kept = _strip_tool_items(item)
            if kept:
                result.append(type(item)(kept))
            continue

        # Callables generate their tools at draw time - leave them be.
        result.append(item)

    # A trailing separator would draw a gap at the bottom of the toolbar.
    while result and result[-1] is None:
        result.pop()

    return result


def _view3d_tool_panel():
    from bl_ui.space_toolsystem_toolbar import VIEW3D_PT_tools_active

    return VIEW3D_PT_tools_active


def _redraw_toolbars() -> None:
    window_manager = bpy.data.window_managers[0] if bpy.data.window_managers else None
    if window_manager is None:
        return
    for window in window_manager.windows:
        for area in window.screen.areas:
            if area.type == "VIEW_3D":
                area.tag_redraw()


def _reset_hidden_active_tools(context=None) -> None:
    """Move any window sitting on a now-hidden tool back to the select tool.

    The toolbar would otherwise have no button to highlight. `context.workspace`
    is not dependable straight after the workspace shuffle, so every window is
    resolved from the window manager instead.
    """
    window_manager = bpy.data.window_managers[0] if bpy.data.window_managers else None
    if window_manager is None:
        return

    mode = getattr(context or bpy.context, "mode", None) or "OBJECT"

    for window in window_manager.windows:
        workspace = window.workspace
        if workspace is None:
            continue

        active = workspace.tools.from_space_view3d_mode(mode, create=False)
        if active is None or active.idname not in HIDDEN_VIEW3D_TOOLS:
            continue

        area = next(
            (a for a in window.screen.areas if a.type == "VIEW_3D"), None
        )
        if area is None:
            continue

        with bpy.context.temp_override(
            window=window, screen=window.screen, area=area
        ):
            bpy.ops.wm.tool_set_by_id(
                name="builtin.select_box", space_type="VIEW_3D"
            )


def hide_viewport_tools(context=None) -> None:
    """Remove the annotate, measure and add-primitive tools from the toolbar.

    This wraps `tools_from_context` - the run-time hook Blender documents as
    "may filter out tools to display" - rather than rewriting the panel's
    `_tools` table. That table stays canonical, so `bpy.utils.register_tool`
    and `unregister_tool` keep working normally while the workspace is
    simplified, and a tool registered after this point is filtered on its way
    to the toolbar instead of being lost.
    """
    global _ORIGINAL_TOOLS_FROM_CONTEXT

    panel = _view3d_tool_panel()

    if _ORIGINAL_TOOLS_FROM_CONTEXT is None:
        _ORIGINAL_TOOLS_FROM_CONTEXT = panel.tools_from_context.__func__
        original = _ORIGINAL_TOOLS_FROM_CONTEXT

        def tools_from_context(cls, context, mode=None):
            items=original(cls, context, mode)
            yield from _strip_tool_items(items) if (context.screen.get("bbe_simple_screen_owner") or context.workspace.get("furby_simple_owner")) == "BBE" else items

        panel.tools_from_context = classmethod(tools_from_context)

    if context is None:return
    if context.workspace and context.workspace.get('furby_simple_origin'):
        _reset_hidden_active_tools(context)
    _redraw_toolbars()


def restore_viewport_tools() -> None:
    """Put the stock Blender toolbar back."""
    global _ORIGINAL_TOOLS_FROM_CONTEXT

    if _ORIGINAL_TOOLS_FROM_CONTEXT is None:
        return

    _view3d_tool_panel().tools_from_context = classmethod(
        _ORIGINAL_TOOLS_FROM_CONTEXT
    )
    _ORIGINAL_TOOLS_FROM_CONTEXT = None

    _redraw_toolbars()
