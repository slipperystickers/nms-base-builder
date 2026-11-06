from ..furby_errors import report_error
import bpy
import json
import os
from ..utils import blend_utils,dictionary
from ..builder import Builder
from .. import builder_v2
from ..utils import asset_browser_utils
from ..utils.asset_browser_utils import get_preferences
import ctypes
from contextlib import nullcontext
from mathutils import Matrix

try:
    from ctypes import wintypes
except (ImportError, ValueError):
    # ctypes.wintypes only exists on Windows. The window titling below is a
    # Windows only nicety, so the rest of the addon has to survive without it.
    wintypes = None

BUILDER = Builder()
ADDON_ID = asset_browser_utils.ADDON_ID


def browser_pin_object():
    """Provide Properties with a context without touching scene selection."""
    from .asset_browser_grid import _is_browser_pin
    obj = next((item for item in bpy.data.objects if _is_browser_pin(item)), None)
    if obj is None:
        mesh = bpy.data.meshes.new("Asset Browser Window")
        obj = bpy.data.objects.new("Asset Browser Window", mesh)
    # Blender 5.1 omits object contexts (including CONSTRAINT and MODIFIER)
    # for an unlinked pin, leaving a reopened browser as two Scene panels.
    if obj.name not in bpy.context.scene.collection.all_objects:
        bpy.context.scene.collection.objects.link(obj)
    obj.hide_set(True)
    obj.hide_render = True
    obj.hide_select = True
    obj.use_fake_user = True
    obj['bbe_asset_browser_pin'] = True
    return obj


def placement_view(context):
    """Use the user's 3D view, not the pop-out browser's copied view layer."""
    for window in context.window_manager.windows:
        if window.scene != context.scene:
            continue
        for area in window.screen.areas:
            if area.type == 'VIEW_3D':
                region = next((r for r in area.regions if r.type == 'WINDOW'), None)
                if region is not None:
                    return bpy.context.temp_override(window=window, area=area, region=region)
    return nullcontext()


def _get_user32():
    """The user32 handle, or None when we are not on Windows."""
    if wintypes is None or not hasattr(ctypes, "windll"):
        return None

    try:
        user32 = ctypes.windll.user32
    except (AttributeError, OSError):
        return None

    # Declared rather than left to ctypes' int defaults, which truncate a 64
    # bit HWND and silently hand Windows a handle that points at nothing.
    user32.EnumWindows.argtypes = [ctypes.c_void_p, wintypes.LPARAM]
    user32.EnumWindows.restype = wintypes.BOOL
    user32.IsWindowVisible.argtypes = [wintypes.HWND]
    user32.IsWindowVisible.restype = wintypes.BOOL
    user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
    user32.GetWindowThreadProcessId.restype = wintypes.DWORD
    user32.SetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPCWSTR]
    user32.SetWindowTextW.restype = wintypes.BOOL
    user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
    user32.GetWindowRect.restype = wintypes.BOOL
    user32.MoveWindow.argtypes = [
        wintypes.HWND, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, wintypes.BOOL
    ]
    user32.MoveWindow.restype = wintypes.BOOL
    user32.LoadImageW.argtypes = [
        wintypes.HINSTANCE, wintypes.LPCWSTR, wintypes.UINT,
        ctypes.c_int, ctypes.c_int, wintypes.UINT
    ]
    user32.LoadImageW.restype = wintypes.HANDLE
    user32.SendMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
    user32.SendMessageW.restype = wintypes.LPARAM
    user32.GetSystemMetrics.argtypes = [ctypes.c_int]
    user32.GetSystemMetrics.restype = ctypes.c_int
    return user32


def get_process_window_handles():
    """Every visible top level window this Blender process owns.

    Handles come back as plain ints so they can be compared and kept in a set.
    """
    user32 = _get_user32()
    if user32 is None:
        return []

    try:
        pid = ctypes.windll.kernel32.GetCurrentProcessId()
    except (AttributeError, OSError):
        return []

    handles = []
    enum_proc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

    def on_window(hwnd, lparam):
        if user32.IsWindowVisible(hwnd):
            window_pid = wintypes.DWORD()
            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(window_pid))
            if window_pid.value == pid:
                handles.append(int(hwnd))
        return True

    try:
        user32.EnumWindows(enum_proc(on_window), 0)
    except OSError:
        return []

    return handles


def set_window_title(hwnd, title):
    """Rename a window we already found. Returns True when Windows accepted it."""
    user32 = _get_user32()
    if user32 is None or not hwnd:
        return False
    try:
        return bool(user32.SetWindowTextW(wintypes.HWND(hwnd), title))
    except OSError:
        return False


def resize_window(hwnd, width, height):
    """Resize in place, keeping the position Blender gave the window."""
    user32 = _get_user32()
    if user32 is None or not hwnd:
        return False

    handle = wintypes.HWND(hwnd)
    rect = wintypes.RECT()
    try:
        if not user32.GetWindowRect(handle, ctypes.byref(rect)):
            return False
        return bool(user32.MoveWindow(handle, rect.left, rect.top, width, height, True))
    except OSError:
        return False


WINDOW_ICON_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "images",
    "asset_browser_window.ico",
)

# HICONs are process wide GDI handles. They are loaded once and kept alive for
# as long as Blender runs - a window keeps referencing its icon, so destroying
# one after handing it over would blank the title bar.
_window_icon_cache = {}

WM_SETICON = 0x0080
ICON_SMALL = 0
ICON_BIG = 1
IMAGE_ICON = 1
LR_LOADFROMFILE = 0x00000010
SM_CXICON = 11
SM_CXSMICON = 49


def _load_window_icon(user32, size):
    """A HICON at the given pixel size, loaded from the addon's .ico."""
    if size in _window_icon_cache:
        return _window_icon_cache[size]

    handle = None
    if os.path.isfile(WINDOW_ICON_PATH):
        try:
            handle = user32.LoadImageW(
                None, WINDOW_ICON_PATH, IMAGE_ICON, size, size, LR_LOADFROMFILE
            )
        except OSError:
            handle = None

    _window_icon_cache[size] = handle
    return handle


def set_window_icon(hwnd):
    """Give a window the addon's icon in the title bar and in Alt+Tab.

    The taskbar button is not ours to change - Windows groups every window of a
    process under the application icon, so that stays Blender's.
    """
    user32 = _get_user32()
    if user32 is None or not hwnd:
        return False

    handle = wintypes.HWND(hwnd)
    applied = False
    for which, metric in ((ICON_SMALL, SM_CXSMICON), (ICON_BIG, SM_CXICON)):
        try:
            icon = _load_window_icon(user32, user32.GetSystemMetrics(metric))
            if not icon:
                continue
            user32.SendMessageW(handle, WM_SETICON, which, icon)
            applied = True
        except OSError:
            continue

    return applied

    
class LaunchAssetBrowserWindow(bpy.types.Operator):
    bl_idname = "object.nms_launch_asset_browser_window"
    bl_label = "Asset Browser"
    bl_description = "Launch an Asset Browser in new Window"

    target_width: bpy.props.IntProperty(default=1200)
    target_height: bpy.props.IntProperty(default=900)

    def execute(self, context):
        
        scene = context.scene
        # this column count is an addon preference. It used to be assigned to the
        # AssetBrowser property group, which has no such property, so it silently
        # went nowhere and the new window never got its wider layout.
        prefs = get_preferences(context)
        if prefs is not None:
            prefs.asset_browser_number_of_columns_other = 8
        
        # Taken before the window exists so the handle that appears afterwards
        # is unambiguously the one we just asked for.
        handles_before = set(get_process_window_handles())

        bpy.ops.wm.window_new()
        wm = context.window_manager
        if not wm.windows:
            return {'CANCELLED'}
        new_window = wm.windows[-1]
        from . import asset_browser_grid
        asset_browser_grid.mark_window_pending(new_window)
        try:
            areas = new_window.screen.areas
            if not areas:
                asset_browser_grid.unmark_window_pending(new_window)
                return {'CANCELLED'}
            target_area = areas[0]
            target_area.type = 'PROPERTIES'
        except (ReferenceError, RuntimeError, TypeError):
            asset_browser_grid.unmark_window_pending(new_window)
            return {'CANCELLED'}
        
        attempts_count = 0
        setup_state = {'last_error': None}
        
        def get_timeout():
            nonlocal attempts_count
            attempts_count +=1
            if attempts_count >= 200:
                print('BBE Asset Browser: setup timed out; window remains editable')
                asset_browser_grid.unmark_window_pending(new_window)
                return None
            return 0.05
        
        def configure_areas():
            try:
                window_exists = any(w == new_window for w in wm.windows)
                if not window_exists:
                    asset_browser_grid.unmark_window_pending(new_window)
                    return None
                if len(new_window.screen.areas) < 2:
                    return get_timeout()

                areas_sorted = sorted(new_window.screen.areas, key=lambda a: a.x)
                left_area, right_area = areas_sorted[0], areas_sorted[1]

                # A primitive-add operator deselects the placement target.
                # Link the UI pin only while a browser uses it, then reuse it.
                dummy_obj = browser_pin_object()
                
                for area, ctx_type in ((left_area, 'CONSTRAINT'), (right_area, 'MODIFIER')):
                    area.type = 'PROPERTIES'
                    space = area.spaces.active
                    space.use_pin_id = True
                    space.pin_id = dummy_obj
                    space.context = ctx_type
                    space.show_region_header = False
                    
                # Keep the native category controls on the left; the right
                # surface owns its image hit areas and corner controls.
                right_area.type = 'IMAGE_EDITOR'
                right_area.spaces.active.show_region_ui = False
                right_area.spaces.active.show_region_toolbar = False
                right_area.spaces.active.show_region_header = False
                right_area.spaces.active.show_region_tool_header = False
                right_area.spaces.active.show_region_hud = False
                right_area.spaces.active.show_gizmo = False
                region = next((r for r in right_area.regions if r.type == 'WINDOW'), None)
                if region is None:
                    return get_timeout()
                with bpy.context.temp_override(window=new_window, area=right_area, region=region):
                    result = bpy.ops.bbe.asset_grid('INVOKE_DEFAULT')
                    if 'RUNNING_MODAL' not in result:
                        return get_timeout()
                asset_browser_grid.unmark_window_pending(new_window)
                return None
            except (ReferenceError, RuntimeError, TypeError, AttributeError) as error:
                if str(error) != setup_state['last_error']:
                    print(f'BBE Asset Browser: setup will retry: {error}')
                    setup_state['last_error'] = str(error)
                return get_timeout()

        def switch_tab():
            try:
                window_exists = any(w == new_window for w in wm.windows)
                if not window_exists:
                    return None

                # Blender may reuse the previously split screen when a
                # pop-out is closed and reopened. Configure it in place.
                if len(new_window.screen.areas) >= 2:
                    bpy.app.timers.register(configure_areas, first_interval=0.02)
                    return None

                if target_area.type != 'PROPERTIES':
                    return get_timeout()
                space = target_area.spaces.active
                if space is None or space.type != 'PROPERTIES':
                    return get_timeout()

                nav_region = None
                window_region = None
                for region in target_area.regions:
                    if region.type == 'NAVIGATION_BAR':
                        nav_region = region
                    elif region.type == 'WINDOW':
                        window_region = region

                if window_region is None:
                    return get_timeout()

                if nav_region and nav_region.width > 1:
                    with bpy.context.temp_override(window=new_window, area=target_area, region=nav_region):
                        bpy.ops.screen.region_toggle(region_type='NAVIGATION_BAR')

                with bpy.context.temp_override(window=new_window, area=target_area, region=window_region):
                    bpy.ops.screen.area_split(direction='VERTICAL', factor=0.2)

                bpy.app.timers.register(configure_areas, first_interval=0.02)
                return None
            except (ReferenceError, RuntimeError, TypeError, AttributeError) as error:
                if str(error) != setup_state['last_error']:
                    print(f'BBE Asset Browser: split will retry: {error}')
                    setup_state['last_error'] = str(error)
                return get_timeout()

        bpy.app.timers.register(switch_tab, first_interval=0.02)

        # The title used to be pushed onto GetForegroundWindow() the moment
        # window_new() returned. That is the wrong window as often as not - the
        # OS has not always handed focus over yet - so the rename either landed
        # on the main Blender window or went nowhere. The new window is found by
        # diffing the process' window handles instead.
        window_title = "Asset Browser"
        # Read off the operator now - the timer outlives execute, and self is
        # not guaranteed to still be around by the time it runs.
        target_width, target_height = self.target_width, self.target_height
        title_state = {"hwnd": None, "attempts": 0, "reapplies": 0}

        def apply_window_title():
            title_state["attempts"] += 1

            hwnd = title_state["hwnd"]
            if hwnd is None:
                new_handles = [
                    handle for handle in get_process_window_handles()
                    if handle not in handles_before
                ]
                if not new_handles:
                    # The OS window can lag a moment behind wm.window_new().
                    return 0.05 if title_state["attempts"] < 20 else None
                hwnd = new_handles[0]
                title_state["hwnd"] = hwnd
                resize_window(hwnd, target_width, target_height)
                set_window_icon(hwnd)

            if not set_window_title(hwnd, window_title):
                # The handle is no longer valid - the user closed the window.
                return None

            # Blender writes its own title while the window finishes setting
            # itself up, so ours goes back on a few times over the first second.
            title_state["reapplies"] += 1
            if title_state["reapplies"] < 10:
                return 0.1
            return None

        bpy.app.timers.register(apply_window_title, first_interval=0.0)

        return {'FINISHED'}
    
    
class AssetBrowserObjectSelected(bpy.types.Operator):
    bl_idname = "object.nms_asset_browser_object_selected"
    bl_label = "Add Object"
    bl_description = "Click to add this object to the scene"
    bl_options = {'REGISTER', 'UNDO'}

    object_id: bpy.props.StringProperty()
    has_variants : bpy.props.BoolProperty( default = False )
    variants : bpy.props.StringProperty()
    is_preset : bpy.props.BoolProperty( default = False )
    
    @classmethod
    def description(cls, context, properties):
        from .. import character_references
        reference = character_references.decode(properties.object_id)
        if reference:
            return f"Add a movable {reference[2]} {reference[1].lower()} scale reference at the cursor. Excluded from game exports."
        if properties.object_id == 'BASE_BUBPIPE_L':
            return ('DRAFT ELBOW: Keep it selected and add a tube to its free end. '
                    'Grey-blue bands disappear when both ends connect correctly. '
                    'An unfinished elbow appears straight in game. Use the controls beside the selected tube to rotate.')
        if properties.has_variants:
            return f"Choose a variant of {properties.object_id}"
        if properties.object_id in dictionary.PLACEMENT_HELP:
            return dictionary.PLACEMENT_HELP[properties.object_id]
        return f"Place {properties.object_id} in the scene"
    
    
    def execute(self, context):
        from .. import cable_connections
        if self.object_id in cable_connections.KINDS and not self.is_preset:
            with placement_view(context):
                result = bpy.ops.bbe.start_cable_connection('INVOKE_DEFAULT', kind=self.object_id)
            if result in ({'RUNNING_MODAL'}, {'FINISHED'}):
                context.scene.nms_asset_browser.add_to_recents_list(self.object_id)
                self.report({'INFO'}, 'Click two blue teleport targets.' if self.object_id == cable_connections.TELEPORT else 'Click two green electrical targets.')
                return {'FINISHED'}
            return {'CANCELLED'}
        from .. import character_references
        if character_references.decode(self.object_id):
            try:
                with placement_view(context):
                    model = character_references.add(bpy.context, self.object_id)
                context.scene.nms_asset_browser.add_to_recents_list(self.object_id)
                warning = model.get('bbe_character_asset_warning')
                self.report({'WARNING'} if warning else {'INFO'}, warning or 'Character scale reference added; excluded from game exports')
                return {'FINISHED'}
            except Exception as error:
                report_error(self, {'ERROR'}, f'Could not add character reference: {error}')
                return {'CANCELLED'}
        if not self.is_preset:
            from ..utils import new_assets
            if new_assets.mark_viewed(self.object_id):
                for window in context.window_manager.windows:
                    for area in window.screen.areas:
                        area.tag_redraw()
        variants = self.variants
        scene = context.scene
        asset_browser = scene.nms_asset_browser
        
        if self.is_preset:
            item_id = self.object_id
            try:
                new_item = BUILDER.add_preset(item_id)
            except Exception as error:
                report_error(self,{'ERROR'}, f"Could not add preset {item_id}: {error}")
                return {'CANCELLED'}
            if new_item:
                new_item.select()
        elif self.has_variants:
            def draw_popup(self, context):
                layout = self.layout
                nice_names = dictionary.get_nice_names_diictionary()
                layout.label(text="Select Variants")
                variants_list = json.loads(variants)
                for variant_obj_id in variants_list:
                    if variant_obj_id in nice_names:
                        variant_name = nice_names[variant_obj_id]
                        button = layout.operator("object.nms_asset_browser_object_selected", text = variant_name)
                        button.object_id = variant_obj_id
                        button.has_variants = False
            context.window_manager.popup_menu(draw_popup)
        else:
            if self.object_id not in dictionary.get_nice_names_diictionary():
                report_error(self,{'ERROR'}, f"Could not add {self.object_id} to scene")
                return {'CANCELLED'}

            auto_snap=asset_browser_utils.auto_snap_enabled()
            if self.object_id == 'BASE_BUBPIPE_L':
                from .. import bubble_preview
                try:
                    with placement_view(context):
                        selected_target = bpy.context.active_object
                        if selected_target is not None and not selected_target.select_get():
                            selected_target = None
                        item = bubble_preview.add_native_bend_point(
                            BUILDER, target=selected_target if auto_snap else None,
                            cursor=context.scene.cursor.location)
                        if not auto_snap and selected_target is not None:
                            item.object.matrix_world=selected_target.matrix_world.copy()
                    blend_utils.select(item.object)
                    asset_browser.add_to_recents_list(self.object_id)
                    bubble_preview._sync_joint_rotation_guard()
                    self.report({'INFO'}, 'Draft elbow added. Keep it selected and add a tube to its free end.')
                    return {'FINISHED'}
                except Exception as error:
                    report_error(self, {'ERROR'}, f'Could not add native bubble elbow: {error}')
                    return {'CANCELLED'}

            # A part can fail to build - a missing asset, or one of the override
            # classes throwing. This used to go straight to item.object and turn
            # that into an unhandled AttributeError in the operator.
            # Keep the selected target before importing a proxy changes selection.
            try:
                with placement_view(context):
                    selected_target = bpy.context.active_object
                    if selected_target is not None and not selected_target.select_get():
                        selected_target = None
                    if (auto_snap and self.object_id == 'BASE_BUBPIPE'
                            and selected_target is not None
                            and selected_target.get('ObjectID') == 'BASE_BUBPIPE_L'):
                        raise ValueError('This is an old preview-only corner. Convert the route before extending it')
                    if (auto_snap and self.object_id == 'BASE_BUBPIPE'
                            and selected_target is not None
                            and selected_target.get('ObjectID') == 'BASE_BUBPIPE'):
                        from .. import bubble_preview
                        problem = bubble_preview.placement_error(selected_target, context.scene)
                        if problem:
                            raise ValueError(problem)
                    placement_matrix = builder_v2.placement_from_target(self.object_id, selected_target)
                    if not auto_snap and selected_target is not None:
                        placement_matrix=selected_target.matrix_world.copy()
                    item = builder_v2.add_part(self.object_id, builder_object=BUILDER)
                    if self.object_id == 'BASE_BUBPIPE':
                        item.object['bbe_bubble_shape'] = 'STRAIGHT:Y'
            except Exception as error:
                report_error(self,{'ERROR'}, f"Could not add {self.object_id}: {error}")
                return {'CANCELLED'}

            bpy_obj = getattr(item, "object", None)
            if bpy_obj is None:
                report_error(self,{'ERROR'}, f"Could not add {self.object_id} to scene")
                return {'CANCELLED'}

            # The browser can keep a different active object from the main
            # viewport. The user's selection is the only placement source.
            if placement_matrix is None:
                bpy_obj.location = (0.0, 0.0, 0.0)
                bpy_obj.scale = (1.0, 1.0, 1.0)
            else:
                bpy_obj.matrix_world = placement_matrix

            from .. import snap_markers
            with placement_view(context):
                snapped=auto_snap and snap_markers.place_initial(bpy.context,bpy_obj,selected_target)
                if not snapped:
                    if auto_snap and self.object_id=='BASE_BUBPIPE' and selected_target is not None and selected_target.get('ObjectID')=='BASE_BUBPIPE':
                        bpy.data.objects.remove(bpy_obj,do_unlink=True)
                        report_error(self,{'ERROR'},'No safe straight duct placement here. Move nearby ducts farther apart first.')
                        return {'CANCELLED'}
                    blend_utils.select(bpy_obj)
            # The new part stays paired with the target so every compatible
            # green socket is immediately clickable after browser placement.
            asset_browser.add_to_recents_list(self.object_id)
            self.report({'INFO'}, f"Added {self.object_id} to scene")
        return {'FINISHED'}
    
class AssetBrowserObjectMoreOptions(bpy.types.Operator):
    bl_idname = "object.nms_asset_browser_more_options"
    bl_label = "Part Options"
    bl_description = "Open favourites and replace options for this part"

    object_id: bpy.props.StringProperty()
    is_fav : bpy.props.BoolProperty(default = False)
    
    @classmethod
    def description(cls, context, properties):
        return f"Show more options for {properties.object_id}"
    
    
    def execute(self, context):
        scene = context.scene
        asset_browser = scene.nms_asset_browser
        
        is_fav = self.is_fav
        object_id = self.object_id
        
        def draw_popup(self, context):
            layout = self.layout
            layout.label(text=f"{object_id} Options", icon = "COLLAPSEMENU")
            layout.separator()
            layout.separator()
            
            fav_button_label = "Remove from Favourites" if is_fav else "Add to Favourite"
            fav_button_icon = "FUND" if is_fav else "HEART"
            fav_button = layout.operator("object.nms_asset_browser_object_favourite", text = fav_button_label, icon = fav_button_icon)
            fav_button.object_id = object_id
            from .. import character_references
            if character_references.decode(object_id):
                return
            
            replace_button_label = f"Replace Selected Objects"
            replace_button = layout.operator("object.nms_asset_browser_batch_replace", text = replace_button_label, icon = "GROUP_VERTEX")
            replace_button.object_id = object_id
        context.window_manager.popup_menu(draw_popup)
        return {'FINISHED'}
    
class AssetBrowserCategorySelected(bpy.types.Operator):
    bl_idname = "object.nms_asset_browser_category_selected"
    bl_label = "Category Selected"
    bl_description = "Expand or collapse this category; clears the current search"

    category: bpy.props.StringProperty()
    
    def execute(self, context):
        scene = context.scene
        asset_browser = scene.nms_asset_browser
        asset_browser.toggle_category(self.category)
        return {'FINISHED'}
    
class AssetBrowserCategoryFavourite(bpy.types.Operator):
    bl_idname = "object.nms_asset_browser_category_favourite"
    bl_label = "Mark Favourite"
    bl_description = "Mark this category favourite"

    category: bpy.props.StringProperty()

    def execute(self, context):
        scene = context.scene
        asset_browser = scene.nms_asset_browser
        fav_cats = asset_browser_utils.toggle_stored_list(
            "favourite_categories", self.category
        )
        asset_browser.set_favourite_categories(fav_cats)

        for area in context.window.screen.areas:
            area.tag_redraw()

        return {'FINISHED'}


class AssetBrowserCategoryReorderPopup(bpy.types.Operator):
    """Reorder categories, and mark them favourite or not, in a popup window."""

    bl_idname = "object.nms_asset_browser_category_reorder_popup"
    bl_label = "Reorder Categories"
    bl_description = "Reorder categories, and mark them favourite or not"

    def invoke(self, context, event):
        scene = context.scene
        asset_browser = scene.nms_asset_browser
        asset_browser.refresh_category_order_list()
        return context.window_manager.invoke_popup(self, width=280)

    def execute(self, context):
        return {'FINISHED'}

    def draw(self, context):
        scene = context.scene
        asset_browser = scene.nms_asset_browser

        layout = self.layout
        layout.label(text="Reorder Categories", icon="SORTALPHA")
        layout.label(text="Favourites always stay on top", icon="INFO")
        layout.separator()

        row_count = len(asset_browser.category_order_list) + 2
        layout.template_list(
            "NMS_UL_asset_browser_category_order",
            "",
            asset_browser,
            "category_order_list",
            asset_browser,
            "category_order_list_index",
            rows=row_count,
        )


class AssetBrowserCategoryMove(bpy.types.Operator):
    bl_idname = "object.nms_asset_browser_category_move"
    bl_label = "Move Category"
    bl_description = "Move this category up or down among categories with the same favourite state"
    bl_options = {'INTERNAL'}

    category: bpy.props.StringProperty()
    direction: bpy.props.StringProperty(default="UP")

    def execute(self, context):
        scene = context.scene
        asset_browser = scene.nms_asset_browser
        asset_browser.move_category(self.category, self.direction)

        for area in context.window.screen.areas:
            area.tag_redraw()

        return {'FINISHED'}


class AssetBrowserObjectFavourite(bpy.types.Operator):
    bl_idname = "object.nms_asset_browser_object_favourite"
    bl_label = "Mark Favourite"
    bl_description = "Mark this Object favourite"

    object_id: bpy.props.StringProperty()
    
    def execute(self, context):
        scene = context.scene
        asset_browser = scene.nms_asset_browser
        fav_objs = asset_browser_utils.toggle_stored_list(
            "favourite_objects", self.object_id
        )
        asset_browser.set_favourite_objects(fav_objs)

        for area in context.window.screen.areas:
            area.tag_redraw()
        
        return {'FINISHED'}
    
class AssetBrowserCategorySubSelected(bpy.types.Operator):
    bl_idname = "object.nms_asset_browser_sub_category_selected"
    bl_label = "Sub Cagetory Selected"
    bl_description = "Sub Category of Objects"

    sub_category: bpy.props.StringProperty()
    
    def execute(self, context):
        scene = context.scene
        asset_browser = scene.nms_asset_browser
        asset_browser.asset_browser_sub_caterogies = self.sub_category
        return {'FINISHED'}
    
class AssetBrowserCategoryShowFavItems(bpy.types.Operator):
    bl_idname = "object.nms_asset_browser_show_fav_items"
    bl_label = "Favourite Items"
    bl_description = "Show Favourite Items"
    def execute(self, context):
        scene = context.scene
        asset_browser = scene.nms_asset_browser
        asset_browser.show_favourite_obejcts()
        
        for area in context.window.screen.areas:
            area.tag_redraw()
        
        return {'FINISHED'}
    
class AssetBrowserCategoryShowRecentItems(bpy.types.Operator):
    bl_idname = "object.nms_asset_browser_show_recent_items"
    bl_label = "Recent Items"
    bl_description = "Show Recent Items"
    def execute(self, context):
        scene = context.scene
        asset_browser = scene.nms_asset_browser
        asset_browser.show_recent_objects()
        
        for area in context.window.screen.areas:
            area.tag_redraw()
        
        return {'FINISHED'}
    
class AssetBrowserCategoryShowPresets(bpy.types.Operator):
    bl_idname = "object.nms_asset_browser_show_presets"
    bl_label = "Presets"
    bl_description = "Show Presets"
    def execute(self, context):
        scene = context.scene
        asset_browser = scene.nms_asset_browser
        asset_browser.show_presets()
        
        for area in context.window.screen.areas:
            area.tag_redraw()
        
        return {'FINISHED'}
    


class AssetBrowserListSettings(bpy.types.Operator):
    """Adjust size of icons and number of columns"""

    bl_idname = "object.nms_asset_browser_list_settings"
    bl_label = "List Settings"
    
    grid_type : bpy.props.StringProperty(
        default = "Other"
    )
    
    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(
            self,
            title="List Settings",
        )

    def execute(self, context):
        asset_browser_utils.save_preferences()
        return {"FINISHED"}

    def draw(self, context):
        layout = self.layout
        prefs = get_preferences(context)
        if prefs is None:
            layout.label(text="Addon preferences are not available", icon="ERROR")
            return

        icon_size_prop, number_of_columns_prop = (
            asset_browser_utils.get_grid_size_properties(self.grid_type)
        )

        layout.prop(prefs, icon_size_prop,text = "Icon Size")
        layout.separator()
        layout.prop(prefs, number_of_columns_prop, text = "Columns")
        

class AssetBrowserBatchReplace(bpy.types.Operator):
    bl_idname = "object.nms_asset_browser_batch_replace"
    bl_label = "Batch Replace"
    bl_description = "Batch replace selected objects with this item"
    bl_options = {'REGISTER', 'UNDO'}
    
    object_id: bpy.props.StringProperty()
    
    def execute(self, context):
        scene = context.scene
        batch_tool = scene.nms_batch_tool
        selected_objects = list(context.selected_objects)

        if not selected_objects:
            self.report({'WARNING'}, "Select the objects to replace first")
            return {'CANCELLED'}

        # the id comes from the browser, but the browser can be showing a list
        # built before the part dictionary was reloaded
        if self.object_id not in dictionary.get_nice_names_diictionary():
            report_error(self,{'ERROR'}, f"{self.object_id} is not a part that can be built")
            return {'CANCELLED'}

        replaced = batch_tool.batch_replace_with_object_id(
            self.object_id, selected_objects
        )
        self.report({'INFO'}, f"Replaced {len(replaced or [])} objects")
        return {'FINISHED'}
        
        
classes = (
    LaunchAssetBrowserWindow,
    AssetBrowserObjectSelected,
    AssetBrowserListSettings,
    AssetBrowserCategorySelected,
    AssetBrowserCategorySubSelected,
    AssetBrowserCategoryFavourite,
    AssetBrowserCategoryReorderPopup,
    AssetBrowserCategoryMove,
    AssetBrowserCategoryShowFavItems,
    AssetBrowserObjectFavourite,
    AssetBrowserCategoryShowRecentItems,
    AssetBrowserCategoryShowPresets,
    AssetBrowserBatchReplace,
    AssetBrowserObjectMoreOptions
)
