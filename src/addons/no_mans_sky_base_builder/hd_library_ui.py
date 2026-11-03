"""One-click detailed proxies, with a one-time download when needed."""
from .furby_errors import report_error
import textwrap
from pathlib import Path
import bpy
from bpy.app.handlers import persistent
from . import hd_library

_pending_scene = None


def cancel_activation():
    global _pending_scene
    _pending_scene = None


def enable_installed(context):
    relink_legacy_textures()
    return bpy.ops.object.nms_switch_proxies_to_high()


def request_download(context, archive=None):
    global _pending_scene
    if hd_library.ready():
        return enable_installed(context)
    if archive is None and not bpy.app.online_access:
        return {'CANCELLED'}
    _pending_scene = context.scene
    hd_library.start(archive)
    return {'FINISHED'}


class BBE_OT_hd_library(bpy.types.Operator):
    bl_idname = "bbe.hd_library"
    bl_label = "Download Detailed Proxies?"
    bl_description = "Download all detailed models once, then enable them automatically"
    allow_online: bpy.props.BoolProperty(default=False, options={'HIDDEN', 'SKIP_SAVE'})

    def invoke(self, context, event):
        if hd_library.ready():
            return enable_installed(context)
        if hd_library.STATE['busy']:
            self.report({'INFO'}, 'Detailed models are downloading. Progress is shown in the sidebar.')
            return {'CANCELLED'}
        self.allow_online = not bpy.app.online_access and not bpy.app.online_access_override
        if not bpy.app.online_access and bpy.app.online_access_override:
            return context.window_manager.invoke_popup(self, width=480)
        return context.window_manager.invoke_props_dialog(
            self, width=480,
            title='Update HD Asset Packs?' if hd_library.available() else 'Download Detailed Proxies?',
            confirm_text="Enable Online Access & Download" if self.allow_online else "Download & Enable",
            cancel_default=True)

    def draw(self, context):
        layout = self.layout
        size = sum(spec['download_bytes'] for spec in hd_library.pending_specs())
        label = 'Download missing HD asset packs' if hd_library.available() else 'Download detailed models, scenes, effects and characters'
        amount = ('%.1f MB' % (size / 1e6)) if size < 1e9 else ('%.2f GB' % (size / 1e9))
        layout.label(text=label + ' (' + amount + ')?')
        if hd_library.available():
            layout.label(text='Detailed models are already installed.')
            layout.label(text='Only missing packs will be added, including the separate character pack.')
        layout.label(text="They stay installed through future BBE updates.")
        if not hd_library.available():
            layout.label(text="Detailed Proxies will turn on when the download finishes.")
        if not bpy.app.online_access and bpy.app.online_access_override:
            layout.separator()
            layout.label(text="Blender was started in offline mode.", icon='INFO')
            layout.label(text="Restart Blender without --offline-mode to download.")
        elif self.allow_online:
            layout.separator()
            layout.label(text="This also enables Blender's global Online Access setting.", icon='INFO')
            layout.label(text="Other add-ons may then access the internet too.")
        if hd_library.STATE['error']:
            for line in textwrap.wrap(hd_library.STATE['error'], 58):
                layout.label(text=line, icon='ERROR')

    def execute(self, context):
        if not hd_library.ready() and not bpy.app.online_access:
            if self.allow_online and not bpy.app.online_access_override:
                # Only reached after the user confirms the explicitly labelled dialog.
                context.preferences.system.use_online_access = True
            else:
                if not bpy.app.background:
                    return bpy.ops.bbe.hd_library('INVOKE_DEFAULT')
                return {'CANCELLED'}
        return request_download(context)


class BBE_OT_hd_download(bpy.types.Operator):
    # Retain the operator identifier for existing shortcuts.
    bl_idname = 'bbe.hd_download'
    bl_label = 'Download & Enable Detailed Proxies'

    def execute(self, context):
        return bpy.ops.bbe.hd_library('INVOKE_DEFAULT')


class BBE_OT_hd_install_zip(bpy.types.Operator):
    # Offline/support fallback, available via operator search rather than the
    # normal Detailed Proxies prompt.
    bl_idname = 'bbe.hd_install_zip'
    bl_label = 'Install Detailed Proxies from ZIP (Offline)'
    filepath: bpy.props.StringProperty(subtype='FILE_PATH')
    filter_glob: bpy.props.StringProperty(default='*.zip', options={'HIDDEN'})

    def invoke(self, context, event):
        context.window_manager.fileselect_add(self)
        return {'RUNNING_MODAL'}

    def execute(self, context):
        return request_download(context, self.filepath)


class BBE_OT_hd_cancel(bpy.types.Operator):
    bl_idname = 'bbe.hd_cancel'
    bl_label = 'Cancel Download'

    def execute(self, context):
        cancel_activation()
        hd_library.CANCEL.set()
        return {'FINISHED'}


class BBE_OT_hd_remove(bpy.types.Operator):
    bl_idname = 'bbe.hd_remove'
    bl_label = 'Delete HD Proxy Pack?'
    bl_description = 'Remove the downloaded HD pack; download it again with Detailed Proxies'

    @classmethod
    def poll(cls, context):
        try:
            return hd_library.removable_root() is not None
        except ValueError:
            return False

    def invoke(self, context, event):
        root = hd_library.removable_root()
        if root is None:
            return {'CANCELLED'}
        self._confirmed_root = str(root.resolve())
        return context.window_manager.invoke_props_dialog(
            self, width=460, confirm_text='Delete HD Pack', cancel_default=True)

    def draw(self, context):
        self.layout.label(text='Remove downloaded HD models, scenes, effects and characters?')
        self.layout.label(text='All scenes in this file will switch to Simple Proxies.')
        self.layout.label(text='Other files and Blender versions sharing this pack are affected.')
        self.layout.label(text='Detailed Proxies will offer to download the pack again.')
        self.layout.label(text='This disk deletion cannot be undone.', icon='INFO')

    def execute(self, context):
        confirmed = getattr(self, '_confirmed_root', None)
        if not confirmed:
            return {'CANCELLED'}  # Direct EXEC calls must not bypass confirmation.
        self._confirmed_root = None
        if hd_library.STATE['busy']:
            return {'CANCELLED'}
        from . import builder_v2
        from .tools_menu.base_builder_menu_operators import _switch_scene_proxies
        try:
            root = hd_library.removable_root()
            if root is None or str(root.resolve()) != confirmed:
                raise ValueError('The HD library changed. Please confirm deletion again.')
            cancel_activation()
            for scene in bpy.data.scenes:
                with context.temp_override(scene=scene, view_layer=scene.view_layers[0]):
                    parts, groups, skipped = _switch_scene_proxies(bpy.context, False)
                if skipped:
                    raise ValueError('Some parts could not switch to Simple Proxies. The HD pack was kept.')
                scene.bbe_detailed_proxies = False
                scene.bbe_stage.enabled = False
            hd_library.remove_installed(confirmed)
            builder_v2.get_asset_index(rebuild=True)
        except (OSError, ValueError, RuntimeError) as exc:
            report_error(self, {'ERROR'}, str(exc))
            return {'CANCELLED'}
        self.report({'INFO'}, 'HD pack deleted. Click Detailed Proxies to download it again.')
        redraw()
        return {'FINISHED'}


class BBE_PT_hd_library(bpy.types.Panel):
    bl_label = 'Detailed Proxies Download'
    bl_idname = 'BBE_PT_hd_library'
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'No Mans Sky Base Builder'

    @classmethod
    def poll(cls, context):
        return bool(hd_library.STATE['busy'] or hd_library.STATE['error'])

    def draw(self, context):
        state = hd_library.STATE
        layout = self.layout
        if state['busy']:
            draw_progress(layout)
            layout.operator('bbe.hd_cancel', icon='CANCEL')
        else:
            for line in textwrap.wrap(state['error'], 44):
                layout.label(text=line)
            layout.operator('bbe.hd_library', text='Retry Download', icon='IMPORT')


classes = (BBE_OT_hd_library, BBE_OT_hd_download, BBE_OT_hd_install_zip,
           BBE_OT_hd_cancel, BBE_OT_hd_remove, BBE_PT_hd_library)


def detailed_enabled(scene):
    return bool(scene.bbe_detailed_proxies and hd_library.available())


def draw_progress(layout):
    state = hd_library.STATE
    layout.label(text=state['message'])
    layout.progress(factor=state['progress'], type='BAR',
                    text="HD models: %.0f%%" % (state['progress'] * 100))


def draw_status(self, context):
    if hd_library.STATE['busy']:
        row = self.layout.row(align=True)
        row.label(text=hd_library.STATE['message'])
        bar = row.row()
        bar.ui_units_x = 8
        bar.progress(factor=hd_library.STATE['progress'], type='BAR',
                     text="HD: %.0f%%" % (hd_library.STATE['progress'] * 100))
        row.operator('bbe.hd_cancel', text='', icon='CANCEL')


def relink_legacy_textures():
    """Repair texture paths in loaded scenes and appended HD parts."""
    return hd_library.relink_texture_images()


def _saved_hd_needs_simple_proxies(scene):
    """Detect detailed meshes with texture files unavailable on this machine."""
    from . import builder_v2
    from .part import Part
    from .group import Group
    from .utils import materials_v2
    seen_meshes = set()
    for obj in scene.objects:
        if (obj.type != 'MESH' or not materials_v2.is_high_res(obj)
                or (Part.PROP_OBJECT_ID not in obj and Group.PROP_GROUP_ID not in obj)):
            continue
        if obj.data in seen_meshes:
            continue
        seen_meshes.add(obj.data)
        for image in builder_v2._mesh_texture_images(obj.data):
            if image.source == 'FILE' and not image.packed_file:
                if not Path(bpy.path.abspath(image.filepath, library=image.library)).is_file():
                    return True
    return False


def _show_texture_fallback():
    if not bpy.app.background and bpy.context.window_manager.windows:
        def draw(self, _context):
            self.layout.label(text='This file uses detailed parts with unavailable textures.')
            self.layout.label(text='BBE switched them to Simple Proxies. Check or install the HD pack.')
        bpy.context.window_manager.popup_menu(draw, title='Detailed Proxies', icon='INFO')
    return None


def _repair_saved_hd_textures(*, before_draw=False):
    """Show simple proxies when a shared file's detailed textures are absent."""
    from .tools_menu.base_builder_menu_operators import _switch_scene_proxies
    repaired = False
    for scene in bpy.data.scenes:
        if scene.library or not _saved_hd_needs_simple_proxies(scene):
            continue
        try:
            with bpy.context.temp_override(scene=scene, view_layer=scene.view_layers[0]):
                parts, groups, skipped = _switch_scene_proxies(bpy.context, False, show_progress=not before_draw)
            scene.bbe_detailed_proxies = False
            repaired = repaired or bool(parts or groups)
            message = (f'Detailed textures missing: showing {parts} part(s) and {groups} group(s) '
                       'with Simple Proxies.')
            if skipped:
                message += f' {skipped} could not switch; install the HD pack.'
            print('BBE: ' + message)
        except (ReferenceError, RuntimeError, ValueError) as exc:
            print(f'BBE: Could not show simple proxies for {scene.name}: {exc}')
    if repaired and not bpy.app.background:
        if before_draw:
            if not bpy.app.timers.is_registered(_show_texture_fallback):
                bpy.app.timers.register(_show_texture_fallback, first_interval=0.0)
        else:
            _show_texture_fallback()
    return None


@persistent
def after_load(_unused):
    cancel_activation()
    relink_legacy_textures()
    # A deferred conversion (or progress redraw during it) exposes unresolved
    # materials to the viewport. Complete the data repair before the first draw;
    # only the informational popup needs to wait for the UI event loop.
    _repair_saved_hd_textures(before_draw=True)
    from .part_overrides.fossil_models import refresh_scene
    from .utils import room_glass, light_fissure
    for scene in bpy.data.scenes:
        with bpy.context.temp_override(scene=scene, view_layer=scene.view_layers[0]):
            refresh_scene(scene)
            room_glass.refresh_scene(scene)
            light_fissure.refresh_scene(scene)


_last_message = None
_last_scenes_root = None


def refresh_marker_proxies():
    """Replace legacy marker cages when effects become available, even unlit."""
    global _last_scenes_root
    root = hd_library.scenes_root()
    if root == _last_scenes_root:
        return
    _last_scenes_root = root
    if root is None:
        return
    from . import builder_v2
    for scene in bpy.data.scenes:
        if not scene.bbe_detailed_proxies:
            continue
        with bpy.context.temp_override(scene=scene):
            for obj in scene.objects:
                pid = obj.get('ObjectID', '').lstrip('^')
                if obj.type == 'MESH' and pid in {'SET_CLASS_A', 'SET_CLASS_B', 'SET_CLASS_S'}:
                    if obj.data.get(builder_v2.MESH_REVISION_TAG) != builder_v2.MESH_REVISIONS[pid]:
                        mesh = builder_v2.load_high_res_mesh(pid)
                        if mesh is not None:
                            obj.data = mesh


def finish_download():
    """Only the main thread may change Blender data after the worker finishes."""
    global _pending_scene
    state = hd_library.STATE
    if state['busy'] or _pending_scene is None:
        return
    scene = _pending_scene
    _pending_scene = None
    if state.get('result') not in {'installed', 'partial'} or hd_library.CANCEL.is_set():
        return
    try:
        if scene.name not in bpy.data.scenes or not hd_library.available():
            return
        with bpy.context.temp_override(scene=scene, view_layer=scene.view_layers[0]):
            relink_legacy_textures()
            result = bpy.ops.object.nms_switch_proxies_to_high()
        if result == {'FINISHED'}:
            state['message'] = ('Detailed Proxies enabled.' if hd_library.ready() else
                                'Detailed Proxies enabled; HD scenes/effects need a retry.')
        else:
            state['error'] = 'Models are installed. Click Detailed Proxies to enable them.'
    except ReferenceError:
        pass  # The scene was closed while the download was running.
    except Exception:
        state['error'] = 'Models are installed. Click Detailed Proxies to enable them.'


def redraw():
    global _last_message
    finish_download()
    refresh_marker_proxies()
    message = hd_library.STATE['message']
    changed = message != _last_message
    if changed and not hd_library.STATE['busy']:
        relink_legacy_textures()
    _last_message = message
    if hd_library.STATE['busy'] or changed:
        for window in bpy.context.window_manager.windows:
            for area in window.screen.areas:
                area.tag_redraw()
                for region in area.regions:
                    region.tag_redraw()
    return 0.5


def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.types.Scene.bbe_detailed_proxies = bpy.props.BoolProperty(name='Detailed Proxies', default=True)
    bpy.app.handlers.load_post.append(after_load)
    bpy.app.timers.register(redraw, persistent=True)
    bpy.types.VIEW3D_HT_header.prepend(draw_status)


def unregister():
    cancel_activation()
    hd_library.CANCEL.set()
    bpy.types.VIEW3D_HT_header.remove(draw_status)
    if bpy.app.timers.is_registered(redraw):
        bpy.app.timers.unregister(redraw)
    if bpy.app.timers.is_registered(_repair_saved_hd_textures):
        bpy.app.timers.unregister(_repair_saved_hd_textures)
    if bpy.app.timers.is_registered(_show_texture_fallback):
        bpy.app.timers.unregister(_show_texture_fallback)
    if after_load in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.remove(after_load)
    del bpy.types.Scene.bbe_detailed_proxies
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
