"""Configurable NMS menus in the Viewport's second (tool header) row."""
from .. import i18n

import bpy
from types import FunctionType
from bpy.app.handlers import persistent

from .base_builder_menu_presentation import (
    BBE_PG_quick_favourite, BBE_UL_quick_favourites, sync_native_favourites,
    VIEW3D_PT_nms_base_builder, VIEW3D_PT_nms_io_panel,
    VIEW3D_PT_bbe_project_recovery, TOOLBAR_GROUPS,
)
from .. import icons
from .. import bbe_themes

TOOLBAR_ITEMS = (
    ('proxies', 'BBE', VIEW3D_PT_nms_base_builder.bl_idname, 'MESH_MONKEY'),
    ('recovery', 'Recovery', VIEW3D_PT_bbe_project_recovery.bl_idname, 'RECOVER_LAST'),
    ('io', 'I/O', VIEW3D_PT_nms_io_panel.bl_idname, 'IMPORT'),
    ('transforms', 'Transform', 'VIEW3D_PT_bbe_transform_values', 'OBJECT_ORIGIN'),
    ('color', 'Color', 'VIEW3D_PT_bbe_toolbar_color', 'COLOR'),
    ('builder', 'Builder', 'VIEW3D_PT_bbe_toolbar_builder_tools', 'TOOL_SETTINGS'),
    ('transform', 'Curve Tools', 'VIEW3D_PT_bbe_toolbar_transform', 'CURVE_BEZCURVE'),
    ('shapes', 'Shapes', 'VIEW3D_PT_bbe_shapes', 'MESH_ICOSPHERE'),
    ('batch', 'Batch', 'VIEW3D_PT_bbe_toolbar_batch', 'MOD_ARRAY'),
    ('parts', 'Prefabs', 'VIEW3D_PT_bbe_toolbar_parts', 'ASSET_MANAGER'),
    ('cables', 'Logic', 'VIEW3D_PT_bbe_toolbar_cables', 'CURVE_PATH'),
    ('lighting', 'Lighting', 'VIEW3D_PT_bbe_toolbar_lighting', 'LIGHT'),
    ('chat', 'Chat', 'VIEW3D_PT_bbe_chat', 'TEXT'),
)
_ITEMS = {item[0]: item for item in TOOLBAR_ITEMS}
_side_polls = {}
_enabled = False
_original_visibility = {}
_original_tool_settings = None
_layout_order_signature = None


def _preferences(context):
    addon = context.preferences.addons.get(__package__.rsplit('.', 1)[0])
    return addon.preferences if addon else None


def toolbar_state(context):
    prefs = _preferences(context)
    order = []
    for key in (prefs.bbe_toolbar_order.split(',') if prefs else []):
        if key in _ITEMS and key not in order:
            order.append(key)
    # Introduce the new menu beside BBE without reordering saved menu choices.
    if 'recovery' not in order and 'proxies' in order:
        order.insert(order.index('proxies') + 1, 'recovery')
    if 'transform' in order and 'shapes' not in order:
        order.insert(order.index('transform')+1,'shapes')
    order.extend(key for key in _ITEMS if key not in order)
    hidden = set(prefs.bbe_toolbar_hidden.split(',')) & _ITEMS.keys() if prefs else set()
    return order, hidden


def _redraw(context):
    for window in context.window_manager.windows:
        for area in window.screen.areas:
            if area.type == 'VIEW_3D':
                area.tag_redraw()


SIDE_LABELS = {'proxies':'BBE','recovery':'Project Recovery','io':'Import/Export','saves':'Save Manager',
 'transforms':'Transform','color':'Colour & Materials','builder':'Builder Tools','transform':'Curve Tools','shapes':'Shapes',
 'batch':'Batch Tools','parts':'Prefabs','cables':'Cables & Logic','lighting':'Lighting & Scenes','support':'Updates & Support'}

def sidebar_order(context):
    pref = _preferences(context)
    saved = getattr(pref,'bbe_sidebar_order','').split(',')
    order = list(dict.fromkeys(k for k in saved if k in SIDE_LABELS))
    # Older saved layouts predate Shapes. Insert it beside the curve tools
    # without moving any panel the user has already placed.
    if 'transform' in order and 'shapes' not in order:
        order.insert(order.index('transform')+1, 'shapes')
    return order + [key for key in SIDE_LABELS if key not in order]

def apply_sidebar_order(context):
    from ..workspace_controls import order_panels
    order_panels(list(_side_polls), {key:i for i,key in enumerate(sidebar_order(context))}, sidebar_key)

class BBE_OT_toolbar_menu(bpy.types.Operator):
    bl_idname = 'bbe.toolbar_menu'
    bl_label = 'Customize Menus'
    bl_description = 'Show or hide this menu, or change its position in the selected list'
    bl_options = {'INTERNAL'}
    menu: bpy.props.StringProperty()
    target: bpy.props.StringProperty()
    after: bpy.props.BoolProperty()
    surface: bpy.props.EnumProperty(items=[('TOP','Top bar',''),('SIDE','Sidebar','')])
    action: bpy.props.EnumProperty(items=[('TOGGLE','Show / Hide',''),('UP','Move Up',''),('DOWN','Move Down',''),('MOVE','Move beside menu',''),('RESET','Reset','')])
    def execute(self, context):
        prefs = _preferences(context)
        if prefs is None:return {'CANCELLED'}
        if self.surface == 'SIDE':
            order, hidden = sidebar_order(context), set(prefs.bbe_sidebar_hidden.split(','))
            defaults = list(SIDE_LABELS)
        else:
            order, hidden = toolbar_state(context)
            defaults = list(_ITEMS)
        if self.action == 'RESET':order,hidden=defaults,(set() if self.surface=='SIDE' else {'transforms'})
        elif self.menu not in order:return {'CANCELLED'}
        elif self.action == 'TOGGLE':hidden.symmetric_difference_update({self.menu})
        elif self.action == 'MOVE':
            if self.target not in order or self.target == self.menu:
                return {'CANCELLED'}
            original = order.copy()
            order.remove(self.menu)
            order.insert(order.index(self.target) + int(self.after), self.menu)
            if order == original:
                return {'FINISHED'}
        else:
            index=order.index(self.menu);target=index+(-1 if self.action=='UP' else 1)
            if 0<=target<len(order):order[index],order[target]=order[target],order[index]
        if self.surface=='SIDE':
            prefs.bbe_sidebar_order=','.join(order);prefs.bbe_sidebar_hidden=','.join(sorted(hidden))
            if self.action!='TOGGLE':apply_sidebar_order(context)
        else:
            prefs.bbe_toolbar_order=','.join(order);prefs.bbe_toolbar_hidden=','.join(sorted(hidden))
        _redraw(context)
        return {'FINISHED'}

def draw_toolbar_settings(layout, context, surface='TOP'):
    side=surface=='SIDE'
    order,hidden=(sidebar_order(context),set(_preferences(context).bbe_sidebar_hidden.split(','))) if side else toolbar_state(context)
    layout.label(text='Sidebar menus' if side else 'Top bar menus')
    layout.label(text='Show/hide with the checkbox. Use arrows to reorder.')
    for index,key in enumerate(order):
        row=layout.row(align=True)
        op=row.operator('bbe.toolbar_menu',text='',icon='CHECKBOX_DEHLT' if key in hidden else 'CHECKBOX_HLT')
        op.menu,op.action,op.surface=key,'TOGGLE',surface
        row.label(text=SIDE_LABELS[key] if side else _ITEMS[key][1])
        for action,icon,enabled in [('UP','TRIA_UP',index>0),('DOWN','TRIA_DOWN',index<len(order)-1)]:
            cell=row.row(align=True);cell.enabled=enabled
            op=cell.operator('bbe.toolbar_menu',text='',icon=icon)
            op.menu,op.action,op.surface=key,action,surface
    row=layout.row(align=True)
    op=row.operator('bbe.toolbar_menu',text='Reset this list',icon='LOOP_BACK');op.action,op.surface='RESET',surface
    row.operator('wm.save_userpref',text='Save Layout',icon='FILE_TICK')


class VIEW3D_PT_bbe_transform_values(bpy.types.Panel):
    bl_idname='VIEW3D_PT_bbe_transform_values'
    bl_label='Transform'
    bl_space_type='VIEW_3D'
    bl_region_type='HEADER'
    bl_ui_units_x=20
    def draw(self,context):
        from ..tools.properties_presentation import draw_compact_transforms
        from ..save_editor.function_help import corner_help
        corner_help(self.layout, 'TRANSFORM')
        if context.active_object is None or not context.active_object.select_get():self.layout.label(text='Select a part to edit its transform.')
        else:draw_compact_transforms(i18n.localized_layout(self.layout),context,show_reset=False)


class VIEW3D_PT_bbe_transform_sidebar(bpy.types.Panel):
    bl_label='Transform'
    bl_space_type='VIEW_3D'
    def draw_header(self,context):
        from .. import sidebar_builder
        sidebar_builder.begin_header(self, context, 'transforms')
        icons.draw_panel_icon(self.layout, 'transform')
    def draw(self,context):
        from .. import sidebar_builder
        if not sidebar_builder.draw_inline(self, context, 'transforms'):
            VIEW3D_PT_bbe_transform_values.draw(self,context)
    bl_idname='VIEW3D_PT_bbe_transform_sidebar'
    bl_region_type='UI'
    bl_category='No Mans Sky Base Builder'
    bl_options={'DEFAULT_CLOSED'}
    @classmethod
    def poll(cls,context):
        pref=_preferences(context)
        return 'transforms' not in getattr(pref,'bbe_sidebar_hidden','').split(',')


def connector_header(self,context):
    # BBE+ supplies its own visibility setting when its objects/sidebar own the
    # view. Read public scene/object markers without importing that extension.
    if hasattr(context.scene,'bbeplus_show_connectors'):
        obj=context.active_object
        if obj and any(key in obj for key in ('bbeplus_part_json','bbeplus_pattern','bbeplus_easy_curve','bbeplus_group')):
            return
        area=context.area
        if area and area.type=='VIEW_3D' and area.spaces.active.show_region_ui:
            side=next((r for r in area.regions if r.type=='UI'),None)
            if side and side.active_panel_category in {'BBE+','BBE+ Assets'}:
                return
    if hasattr(context.scene,'bbe_show_connectors'):
        from ..workspace_controls import draw_connectors
        draw_connectors(self.layout, context.scene, 'bbe_show_connectors', 'BBE')


def connectors_changed(scene,context):
    if not scene.bbe_show_connectors:
        from .. import cable_targets
        cable_targets.cancel(context)
    _redraw(context)


def sidebar_key(panel):
    return {'BBE':'proxies','Project Recovery':'recovery','Import/Export':'io','Save Manager':'saves',
      'Curve Tools':'transform','Shapes':'shapes','Transform':'transforms','Colour & Materials':'color','Cables & Logic':'cables',
      'Builder Tools':'builder','Batch Tools':'batch','Prefabs':'parts','Lighting & Scenes':'lighting',
      'Updates & Support':'support'}.get(getattr(panel,'bl_label',''))


def _sidebar_poll(original, key):
    # RNA callbacks must expose exactly (cls, context). Captured values belong
    # in a closure, never extra defaulted arguments in the registered signature.
    def visible(panel, context):
        pref = _preferences(context)
        allowed = (context.region is None or context.region.type != 'UI' or
                   not pref or key not in pref.bbe_sidebar_hidden.split(','))
        return allowed and (original(panel, context) if original else True)
    return classmethod(visible)


def bind_sidebar_visibility(panel_classes):
    """Compose Python polls before RNA registration, never through RNA proxies.

    getattr(registered_panel, 'poll') can expose Blender's native dispatch proxy.
    Saving that proxy and replacing poll makes forwarding enter the replacement
    again. Keep only original Python function objects and register the final
    callback once, including panels that previously had no poll.
    """
    for cls in panel_classes:
        if not isinstance(cls,type) or not issubclass(cls,bpy.types.Panel):continue
        key=sidebar_key(cls)
        if not key or cls in _side_polls or getattr(cls,'bl_region_type','')!='UI' or getattr(cls,'bl_category','')!='No Mans Sky Base Builder':continue
        if 'bl_rna' in cls.__dict__:
            raise RuntimeError('Sidebar visibility must be composed before registering '+cls.__name__)
        original=None
        for base in cls.__mro__:
            descriptor=base.__dict__.get('poll')
            if descriptor is None:continue
            if isinstance(descriptor,classmethod) and isinstance(descriptor.__func__,FunctionType):
                original=descriptor.__func__
            break
        cls.bl_order = sidebar_order(bpy.context).index(key)
        cls.workspace_panel_order = cls.bl_order
        _side_polls[cls]=cls.__dict__.get('poll')
        cls.poll = _sidebar_poll(original, key)
        from .. import sidebar_state
        sidebar_state.bind(cls, key)


def restore_sidebar_visibility():
    """Restore source descriptors only after every wrapped panel is unregistered."""
    for cls,original in _side_polls.items():
        if 'bl_rna' in cls.__dict__:
            raise RuntimeError('Unregister sidebar panel before restoring '+cls.__name__)
        if original is None:delattr(cls,'poll')
        else:cls.poll=original
    _side_polls.clear()


class VIEW3D_PT_bbe_toolbar_settings(bpy.types.Panel):
    bl_idname = 'VIEW3D_PT_bbe_toolbar_settings'
    bl_translation_context = "BBEExtendedInterface"
    bl_label = 'Toolbar Settings'
    bl_description = 'Choose which Base Builder menus are visible and reorder them'
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'HEADER'
    bl_ui_units_x = 18

    def draw(self, context):
        draw_toolbar_settings(i18n.localized_layout(self.layout), context)


class VIEW3D_PT_bbe_toolbar_color(bpy.types.Panel):
    bl_idname = 'VIEW3D_PT_bbe_toolbar_color'
    bl_translation_context = "BBEExtendedInterface"
    bl_label = 'Color & Materials'
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'HEADER'
    bl_ui_units_x = 22

    def draw(self, context):
        from .. import draw_colour_palette
        draw_colour_palette(i18n.localized_layout(self.layout), context)


class VIEW3D_PT_bbe_toolbar_lighting(bpy.types.Panel):
    bl_idname = 'VIEW3D_PT_bbe_toolbar_lighting'
    bl_translation_context = "BBEExtendedInterface"
    bl_label = 'Lighting & Scenes'
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'HEADER'
    bl_ui_units_x = 14

    def draw(self, context):
        from ..stages import BBE_PT_stage
        BBE_PT_stage.draw(self, context)


def draw_toolbar(self, context):
    if not hasattr(context.scene, 'nms_main'):
        return
    layout = i18n.localized_layout(self.layout)
    # Blender draws its own flexible spacer after draw_tool_settings. Pair it
    # with this one to center our group between the native controls.
    layout.separator_spacer()
    order, hidden = toolbar_state(context)
    row = layout.row(align=True)
    ui_icons = icons.get_icons_pscroll()
    row.operator('object.nms_launch_asset_browser_window', text='Assets',emboss=False,
                 icon_value=ui_icons['toolbar_assets'].icon_id)
    for key in order:
        if key in hidden:
            continue
        _, label, panel, icon = _ITEMS[key]
        from .. import menu_surface,menu_backend
        if key=='chat':
            from .. import bbe_chat
            if bbe_chat._chat_enabled:bbe_chat.draw_native_toolbar(row,context,styled=True);continue
            artwork={'icon_value':bbe_chat._chat_icon()}
        elif key=='shapes':
            from ..shapes import preview_icon
            artwork={'icon_value':preview_icon('BOX')}
        elif key=='transform':artwork={'icon':'CURVE_BEZCURVE'}
        else:artwork={'icon_value':ui_icons['plugin_icon' if key=='proxies' else 'toolbar_transform' if key=='transforms' else 'toolbar_'+key].icon_id}
        menu_surface.toolbar_button(row,menu_backend.KEYS[key],label,**artwork)
    from .. import menu_surface
    menu_surface.toolbar_button(row,'SETTINGS','',icon_value=ui_icons['toolbar_settings'].icon_id)



def attach_toolbar(header):
    previous = header.draw_tool_settings
    state = {'enabled': True}
    def draw(owner, context):
        previous(owner, context)
        if state['enabled']:
            from .. import toolbar_surface
            toolbar_surface.record(draw_toolbar, owner, context)
    header.draw_tool_settings = draw
    def detach():
        state['enabled'] = False
        if header.draw_tool_settings is draw:
            header.draw_tool_settings = previous
    return detach


def _ensure_toolbar():
    global _layout_order_signature
    if not _enabled:
        return None
    from ..viewport_defaults import apply_relationship_default
    prefs=_preferences(bpy.context)
    if prefs and not prefs.bbe_optional_menus_initialized:
        prefs.bbe_toolbar_hidden=','.join(filter(None,[prefs.bbe_toolbar_hidden,'transforms']))
        prefs.bbe_optional_menus_initialized=True
    signature=tuple(sidebar_order(bpy.context))
    if _layout_order_signature != signature:
        apply_sidebar_order(bpy.context)
        _layout_order_signature=signature
    from .. import menu_hint
    menu_hint.maybe_show()
    # Deferred until after addon_utils.enable has left restricted registration.
    # Scan only spaces, once a second; never read saves or assets here. Newly
    # opened workspaces get the row too. A user's later visibility choice wins.
    for screen in bpy.data.screens:
        for area in screen.areas:
            if area.type != 'VIEW_3D':
                continue
            space = area.spaces.active
            apply_relationship_default(space)
            pointer = space.as_pointer()
            if pointer not in _original_visibility:
                _original_visibility[pointer] = space.show_region_tool_header
                space.show_region_tool_header = True
    return 1.0


@persistent
def _load_toolbar(_dummy):
    _original_visibility.clear()
    if _enabled and not bpy.app.timers.is_registered(_ensure_toolbar):
        bpy.app.timers.register(_ensure_toolbar, first_interval=0.1)


classes = (
    BBE_PG_quick_favourite, BBE_UL_quick_favourites,
    VIEW3D_PT_bbe_transform_values, VIEW3D_PT_bbe_transform_sidebar,
    VIEW3D_PT_nms_base_builder, VIEW3D_PT_nms_io_panel, VIEW3D_PT_bbe_project_recovery,
    *(panel for panel, _icon in TOOLBAR_GROUPS),
    BBE_OT_toolbar_menu, VIEW3D_PT_bbe_toolbar_settings, VIEW3D_PT_bbe_toolbar_color,
    VIEW3D_PT_bbe_toolbar_lighting,
    bbe_themes.VIEW3D_PT_bbe_themes, bbe_themes.BBE_OT_apply_theme,
    bbe_themes.BBE_OT_custom_theme, bbe_themes.BBE_OT_load_custom_theme, bbe_themes.BBE_OT_button_style,
)


def register_menu():
    from .. import logic_dropdown
    logic_dropdown.register()
    global _enabled, _detach_toolbar, _detach_connectors, _layout_order_signature
    _layout_order_signature = None
    from .. import menu_hint
    menu_hint.register()
    wm = bpy.types.WindowManager
    wm.bbe_quick_favourites = bpy.props.CollectionProperty(type=BBE_PG_quick_favourite, options={'SKIP_SAVE'})
    wm.bbe_quick_favourite_active = bpy.props.IntProperty(default=0, options={'SKIP_SAVE'})
    wm.bbe_quick_favourite_offset = bpy.props.IntProperty(default=0, min=0, options={'SKIP_SAVE'})
    wm.enum_assets_quick_access_view_mode = bpy.props.EnumProperty(translation_context="BBEExtendedInterface", 
        name='View Mode', description='Quick access assets',
        items=[('fav', 'Favourites', 'Favourite parts', 'HEART', 0),
               ('recent', 'Recent', 'Recently used parts', 'MOD_TIME', 1),
               ('search', 'Search', 'Find a part', 'VIEWZOOM', 2)],
        default='recent', options={'SKIP_SAVE'},
    )
    bpy.types.Scene.bbe_show_connectors=bpy.props.BoolProperty(name='Show Connectors',description='Show or hide snap and cable targets; starting a connection tool shows them again',default=True,update=connectors_changed)
    from .. import workspace_controls
    _detach_connectors = workspace_controls.attach_header(connector_header)
    from .. import menu_surface
    menu_surface.register()
    header = bpy.types.VIEW3D_HT_tool_header
    _detach_toolbar = attach_toolbar(header)
    _enabled = True
    if _load_toolbar not in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.append(_load_toolbar)
    if not bpy.app.timers.is_registered(_ensure_toolbar):
        bpy.app.timers.register(_ensure_toolbar, first_interval=0.1)


def unregister_menu():
    from .. import menu_surface
    menu_surface.unregister()
    from .. import logic_dropdown
    logic_dropdown.unregister()
    global _enabled
    _enabled = False
    from .. import menu_hint
    menu_hint.unregister()
    _detach_connectors()
    if hasattr(bpy.types.Scene,'bbe_show_connectors'):del bpy.types.Scene.bbe_show_connectors
    if bpy.app.timers.is_registered(_ensure_toolbar):
        bpy.app.timers.unregister(_ensure_toolbar)
    if _load_toolbar in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.remove(_load_toolbar)
    header = bpy.types.VIEW3D_HT_tool_header
    _detach_toolbar()
    # Region visibility invokes native area/workspace initialization. During
    # Blender shutdown _on_exit disables add-ons after the active window has
    # been cleared (notably when a file browser is still open). Updating a
    # region then dereferences a null window in WM_window_get_active_workspace;
    # a Python try/except cannot catch that access violation. Restore the UI
    # only while a live window context exists, as on ordinary add-on disable.
    window = getattr(bpy.context, 'window', None)
    can_restore = window is not None and window.workspace is not None and window.screen is not None
    for screen in getattr(bpy.data, 'screens', ()) if can_restore else ():
        for area in screen.areas:
            if area.type == 'VIEW_3D':
                space = area.spaces.active
                previous = _original_visibility.get(space.as_pointer())
                if previous is not None:
                    space.show_region_tool_header = previous
    _original_visibility.clear()
    if bpy.app.timers.is_registered(sync_native_favourites):
        bpy.app.timers.unregister(sync_native_favourites)
    for key in ('enum_assets_quick_access_view_mode', 'bbe_quick_favourite_offset',
                'bbe_quick_favourite_active', 'bbe_quick_favourites'):
        delattr(bpy.types.WindowManager, key)
