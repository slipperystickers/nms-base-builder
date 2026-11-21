"""Keep Base Builder Extended and Charon Forge from running together.

An extension cannot execute while Blender is copying its ZIP. The first safe
point for a BBE preflight is register(), before any overlapping UI, operators,
or Scene properties are registered. Blender restricts context during register,
so the confirmation is deferred to the next window event-loop tick.
"""
from . import i18n

import sys
import traceback

import bpy

_pending = False
_asking = False
_watching = False
_late_reported = False


def active_charon():
    """Names of enabled Forge modules; an installed but disabled copy is safe."""
    return [name for name, module in tuple(sys.modules.items())
            if name.rsplit('.', 1)[-1] == 'charon_forge'
            and getattr(module, '__addon_enabled__', False)]


def configured_charon():
    """Forge modules saved as enabled, including ones not loaded yet on startup."""
    return [addon.module for addon in bpy.context.preferences.addons
            if addon.module.rsplit('.', 1)[-1] == 'charon_forge']


def conflicting_charon():
    return set(active_charon()) | set(configured_charon())


def _notice(lines, title='BBE and Charon Forge', icon='ERROR'):
    if bpy.app.background:
        print(title + ': ' + ' '.join(lines), flush=True)
        return
    def draw(self, _context):
        for line in lines:
            i18n.localized_layout(self.layout).label(text=line)
    try:
        bpy.context.window_manager.popup_menu(draw, title=title, icon=icon)
    except (AttributeError, RuntimeError):
        print(title + ': ' + ' '.join(lines), flush=True)


class BBE_OT_resolve_charon_conflict(bpy.types.Operator):
    bl_idname = 'bbe.resolve_charon_conflict'
    bl_translation_context = "BBEExtendedInterface"
    bl_label = 'Charon Forge is incompatible with BBE'
    bl_description = 'Disable Charon Forge and finish enabling Base Builder Extended'

    def draw(self, _context):
        col = i18n.localized_layout(self.layout).column()
        col.label(text='Charon Forge is currently enabled.')
        col.label(text='Its controls, placement, proxies and lighting conflict with BBE.')
        col.separator()
        col.label(text='Continue: disable Charon Forge and enable BBE.')
        col.label(text='Cancel: keep Charon Forge and leave BBE disabled.')

    def invoke(self, context, _event):
        return context.window_manager.invoke_props_dialog(
            self, width=500, confirm_text='Disable Charon and Enable BBE',
            cancel_default=True,
        )

    def execute(self, _context):
        if not _pending:
            return {'CANCELLED'}
        bpy.app.timers.register(_accept, first_interval=0.05)
        return {'FINISHED'}

    def cancel(self, _context):
        if _pending:
            bpy.app.timers.register(_decline, first_interval=0.05)


def _prompt():
    global _asking
    if not _pending or _asking:
        return None
    for window in bpy.context.window_manager.windows:
        area = next((a for a in window.screen.areas if a.type == 'VIEW_3D'), None)
        if area is None:
            area = window.screen.areas[0] if window.screen.areas else None
        if area is None:
            continue
        try:
            with bpy.context.temp_override(window=window, area=area):
                result = bpy.ops.bbe.resolve_charon_conflict('INVOKE_DEFAULT')
            if 'RUNNING_MODAL' in result:
                _asking = True
                return None
        except (AttributeError, RuntimeError) as error:
            print('BBE compatibility prompt waiting for a window: ' + str(error), flush=True)
    return 1.0


def begin_preflight():
    global _pending, _asking
    _pending = True
    _asking = False
    if not bpy.app.timers.is_registered(_prompt):
        bpy.app.timers.register(_prompt, first_interval=0.2)


def _decline():
    global _pending, _asking
    _pending = _asking = False
    import addon_utils
    import sys
    addon_utils.disable(__package__, default_set=True)
    return None


def _disable_charon():
    import addon_utils
    for name in conflicting_charon():
        addon_utils.disable(name, default_set=True)
    return not conflicting_charon()


def _reset_host_hooks():
    # Forge 0.1.2's incomplete fossil hook can leave its provider installed
    # even after unregister. Restore BBE's own objects before full registration.
    from . import builder
    from .utils import material
    builder.set_builder(None)
    material.set_material_provider(None)


def _accept():
    global _pending, _asking
    if not _pending:
        return None
    try:
        if not _disable_charon():
            raise RuntimeError('Charon Forge is still enabled')
        _reset_host_hooks()
        from . import register_core
        register_core()
        _pending = _asking = False
        watch()
    except Exception:
        traceback.print_exc()
        _notice(('Could not finish enabling BBE safely.',
                 'Save your work, close Blender and restart with Charon disabled.'))
    return None


def _late_conflict():
    _notice(('Charon Forge was enabled after BBE; this session is incompatible.',
             'Save your work and restart Blender. BBE will ask which add-on to use.'))
    return None


def _watch():
    global _late_reported
    if not _watching:
        return None
    if active_charon() and not _late_reported:
        # Forge has already registered and replaced BBE classes at this point.
        # Unregistering either one while both are live can crash Blender, so
        # never attempt automatic in-session repair of this reverse order.
        _late_reported = True
        _late_conflict()
    return 1.0


def watch():
    global _watching
    _watching = True
    if not bpy.app.timers.is_registered(_watch):
        bpy.app.timers.register(_watch, first_interval=1.0, persistent=True)


def register():
    bpy.utils.register_class(BBE_OT_resolve_charon_conflict)


def unregister():
    global _pending, _asking, _watching, _late_reported
    _pending = _asking = _watching = False
    _late_reported = False
    for callback in (_prompt, _accept, _decline, _watch):
        if bpy.app.timers.is_registered(callback):
            bpy.app.timers.unregister(callback)
    if getattr(BBE_OT_resolve_charon_conflict, 'bl_rna', None) is not None:
        bpy.utils.unregister_class(BBE_OT_resolve_charon_conflict)
