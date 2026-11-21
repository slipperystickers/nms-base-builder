"""Reversible simplified workspaces. Original workspaces and scenes are retained."""
import bpy
import json
import uuid
KEY='furby_simple_origin'

STATE = 'bbe_simple_screen_state'
OWNER = 'bbe_simple_screen_owner'


def root_window(window):
    while window.parent:
        window = window.parent
    return window


def is_simple(context):
    return bool(root_window(context.window).screen.get(OWNER) or context.workspace.get(KEY))


def _restore_legacy(context, current, origin):
    target=current.get('bbe_source_workspace') or bpy.data.workspaces.get(origin)
    if target is None:
        raise ValueError('The original workspace was removed or renamed. Choose another workspace tab.')
    window = context.window
    window.workspace = target
    # Dispose only the layout generated for this toggle, after Blender switches.
    # Renamed legacy layouts can contain personal customizations.
    owner = current.get('furby_simple_owner')
    if current.get('bbe_disposable_layout') or (owner in {'BBE', 'BBE+'} and current.name == owner+' Simple'):
        uid = current.session_uid
        def release():
            item = next((w for w in bpy.data.workspaces if w.session_uid == uid), None)
            if item and window in bpy.context.window_manager.windows[:] and window.workspace == item:
                return .05
            if item and all(w.workspace != item for w in bpy.context.window_manager.windows):
                bpy.data.batch_remove(ids=(item,))
            return None
        bpy.app.timers.register(release, first_interval=.1)


def _move_timeline(window, area, delta):
    # Only collapse a bottom timeline sharing a horizontal edge with a viewport.
    x = area.x + area.width // 2
    y = area.y + area.height
    if not any(a.type == 'VIEW_3D' and a.x <= x < a.x + a.width and abs(a.y-y) < 8
               for a in window.screen.areas):
        return
    with bpy.context.temp_override(window=window, area=area):
        if delta and bpy.ops.screen.area_move.poll():
            bpy.ops.screen.area_move(x=x, y=y, delta=delta)


def _simplify_screen(window, token, main):
    screen = window.screen
    state = {'token': token, 'areas': []}
    if main:
        state['status'] = screen.show_statusbar
    for index, area in enumerate(screen.areas):
        space = area.spaces.active
        original = {}
        if area.type == 'PROPERTIES':
            # A material or scene pinned in its own inspector has no Object context.
            if not space.use_pin_id or isinstance(space.pin_id, bpy.types.Object):
                flags = {prop.identifier: getattr(space, prop.identifier)
                         for prop in space.bl_rna.properties if prop.identifier.startswith('show_properties_')}
                original = {'context': space.context, 'flags': flags}
                space.show_properties_object = True
                # Blender selects Object automatically once a part is active in an empty build.
                # Other contexts can also be unavailable in a pinned or special-mode editor.
                if space.use_pin_id or window.view_layer.objects.active:
                    with bpy.context.temp_override(window=window, area=area):
                        try:
                            space.context = 'OBJECT'
                        except TypeError:
                            space.show_properties_object = flags['show_properties_object']
                            continue
                for key in flags:
                    if key != 'show_properties_object':
                        setattr(space, key, False)
        elif main and area.type == 'DOPESHEET_EDITOR' and space.mode == 'TIMELINE':
            original = {'height': area.height}
            _move_timeline(window, area, -max(0, area.height - 25))
        if original:
            state['areas'].append((index, area.type, original))
            area.tag_redraw()
    # Blender rescales split heights when its status bar changes. Keep that
    # boundary fixed while collapsing a timeline so Restore recovers its exact size.
    if main and not any('height' in original for _, _, original in state['areas']):
        screen.show_statusbar = False
    if main or state['areas']:
        screen[STATE] = json.dumps(state)


@bpy.app.handlers.persistent
def _recover_navigation(_file=None):
    # The previous release stored the user's preference before hiding the gizmo.
    for screen in bpy.data.screens:
        if not screen.is_editable or not screen.get(OWNER) or STATE not in screen:
            continue
        state = json.loads(screen[STATE])
        retained = []
        for record in state['areas']:
            index, kind, original = record
            if kind != 'VIEW_3D' or 'navigate' not in original:
                retained.append(record)
                continue
            if 0 <= index < len(screen.areas) and original['navigate']:
                area = screen.areas[index]
                if area.type == kind:
                    area.spaces.active.show_gizmo_navigate = True
                    area.tag_redraw()
        if len(retained) != len(state['areas']):
            state['areas'] = retained
            screen[STATE] = json.dumps(state)


def _refresh_workspace_header(window):
    # Blender's global top bar is outside screen.areas. Its header subscribes
    # to this workspace's tools through the message bus on every layout pass.
    bpy.msgbus.publish_rna(key=window.workspace.path_resolve('tools', False))


def _restore_screen(screen, state, window):
    for index, kind, original in state['areas']:
        if index >= len(screen.areas) or screen.areas[index].type != kind:
            continue
        area = screen.areas[index]
        space = area.spaces.active
        if kind == 'PROPERTIES':
            for key, value in original['flags'].items():
                if hasattr(space, key):
                    setattr(space, key, value)
            # The user may have deleted the object that supplied the original tab.
            if original['context']:
                try:
                    space.context = original['context']
                except TypeError:
                    pass
        elif kind == 'VIEW_3D':
            space.show_gizmo_navigate = original['navigate']
        elif window and space.mode == 'TIMELINE':
            _move_timeline(window, area, original['height'] - area.height)
        area.tag_redraw()
    if 'status' in state:
        screen.show_statusbar = state['status']
    del screen[STATE]
    if OWNER in screen:
        del screen[OWNER]


def toggle(context, label):
    window = root_window(context.window)
    screen = window.screen
    if screen.get(OWNER):
        token = json.loads(screen[STATE])['token']
        windows = {w.screen.as_pointer(): w for w in context.window_manager.windows}
        for item in bpy.data.screens:
            if STATE in item:
                state = json.loads(item[STATE])
                if state['token'] == token:
                    _restore_screen(item, state, windows.get(item.as_pointer()))
        _refresh_workspace_header(window)
        return False
    origin = context.workspace.get(KEY)
    if origin:
        _restore_legacy(context, context.workspace, origin)
        return False
    token = uuid.uuid4().hex
    for member in context.window_manager.windows:
        if root_window(member) == window:
            _simplify_screen(member, token, member == window)
    screen[OWNER] = label
    _refresh_workspace_header(window)
    return True


def draw_workspace(header, context):
    if context.window.parent:
        return False
    owner = context.screen.get(OWNER) or context.workspace.get('furby_simple_owner')
    if owner not in {'BBE', 'BBE+'} or context.screen.show_fullscreen:
        return False
    from bl_ui.space_topbar import TOPBAR_MT_editor_menus
    layout = header.layout
    TOPBAR_MT_editor_menus.draw_collapsible(context, layout)
    layout.separator(type='LINE')
    layout.operator('object.nms_cleanup_workspace', text="Base & Corvette Builder", icon='WORKSPACE',
                    depress=True)
    return True


def register():
    from .utils import workspace
    workspace.hide_viewport_tools()
    from bl_ui.space_topbar import TOPBAR_HT_upper_bar
    from . import browser_headers
    browser_headers.add(TOPBAR_HT_upper_bar, "draw_left", __name__, draw_workspace)
    if _recover_navigation not in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.append(_recover_navigation)
    if not bpy.app.timers.is_registered(_recover_navigation):
        bpy.app.timers.register(_recover_navigation)


def unregister():
    from bl_ui.space_topbar import TOPBAR_HT_upper_bar
    from . import browser_headers
    browser_headers.remove(TOPBAR_HT_upper_bar, "draw_left", __name__)
    if _recover_navigation in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.remove(_recover_navigation)
    if bpy.app.timers.is_registered(_recover_navigation):
        bpy.app.timers.unregister(_recover_navigation)
