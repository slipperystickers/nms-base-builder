"""Small, temporary progress overlay for synchronous Blender scene work.

Blender data must be edited on the main thread. Redrawing between bounded
batches lets the viewport and status bar show real completed work without
running unsafe bpy calls from a worker thread.
"""
import math
import time

import bpy
from bpy.app.handlers import persistent


_active = None


def finish_shading(scene=None):
    activity = _active
    if activity and activity._shading_scene and (scene is None or scene == activity._shading_scene):
        activity._shading_scene = None
        activity.__exit__(None, None, None)


@persistent
def before_load(_):
    finish_shading()


def _shading_tick():
    activity = _active
    if not activity or not activity._shading_scene:
        return None
    now = time.monotonic()
    if bpy.app.is_job_running('SHADER_COMPILATION'):
        activity._quiet_since = now
    if (activity._shaded_draws >= 2 and now - activity._quiet_since > .75
            or now - activity._started > 120 or not activity._shading_scene.bbe_stage.enabled):
        finish_shading()
        return None
    activity._redraw()
    return .12


def _rectangle(shader, batch_for_shader, x, y, width, height, color):
    points = ((x, y), (x + width, y), (x + width, y + height),
              (x, y), (x + width, y + height), (x, y + height))
    shader.bind()
    shader.uniform_float('color', color)
    batch_for_shader(shader, 'TRIS', {'pos': points}).draw(shader)


def _draw():
    activity = _active
    if activity is None:
        return
    try:
        import blf
        import gpu
        from gpu_extras.batch import batch_for_shader

        region = bpy.context.region
        if region is None or region.type != 'WINDOW':
            return
        shading = activity._shading_scene
        if shading:
            if bpy.context.scene != shading or bpy.context.space_data.shading.type not in {'MATERIAL', 'RENDERED'}:
                return
            activity._shaded_draws += 1
        width = min(360, region.width - 32)
        x = max(16, (region.width - width) // 2)
        # Header popovers can remain visible while Blender processes a UI
        # change. Keep progress near the bottom of the viewport so they do not
        # cover it, including for scene preview and proxy quality changes.
        y = 40
        shader = gpu.shader.from_builtin('UNIFORM_COLOR')
        gpu.state.blend_set('ALPHA')
        try:
            _rectangle(shader, batch_for_shader, x, y, width, 72, (.035, .045, .065, .94))
            _rectangle(shader, batch_for_shader, x + 12, y + 12, width - 24, 8,
                       (.16, .19, .24, 1))
            track = width - 24
            if shading:
                # Blender exposes a shader job flag but no percentage.
                offset = (.5 - .5 * math.cos(time.monotonic() * 3)) * track * .7
                _rectangle(shader, batch_for_shader, x + 12 + offset, y + 12,
                           track * .3, 8, (.22, .67, .94, 1))
            else:
                _rectangle(shader, batch_for_shader, x + 12, y + 12,
                           track * activity.fraction, 8, (.22, .67, .94, 1))
            blf.size(0, 15)
            blf.color(0, .94, .96, 1, 1)
            blf.position(0, x + 12, y + 43, 0)
            blf.draw(0, activity.title)
            blf.size(0, 12)
            blf.color(0, .72, .78, .85, 1)
            blf.position(0, x + 12, y + 26, 0)
            blf.draw(0, activity.detail)
            blf.position(0, x + width - 48, y + 26, 0)
            if not shading:
                blf.draw(0, f'{activity.fraction:.0%}')
        finally:
            gpu.state.blend_set('NONE')
    except (AttributeError, RuntimeError, ValueError):
        # A workspace can close or change editor type during an import.
        return


class Range:
    """Map a subtask onto its parent's visible progress without another overlay."""
    def __init__(self, parent, start, end):
        self.parent, self.start, self.end = parent, start, end

    def update(self, fraction, detail=None):
        fraction = min(1.0, max(0.0, float(fraction)))
        self.parent.update(self.start + (self.end - self.start) * fraction, detail)


class Activity:
    """Context-managed progress with cleanup on success and failure."""

    def __init__(self, title, detail='Preparing…', *, visible=True, deferred_redraw=False):
        self.title = title
        self.detail = detail
        self.fraction = 0.0
        self._handle = None
        self._wm = None
        self._owns_ui = False
        self._last_draw = 0.0
        self._shading_scene = None
        self._shaded_draws = 0
        self._visible = visible
        self._deferred_redraw = deferred_redraw

    def __enter__(self):
        global _active
        if self._visible:
            finish_shading()
        if not self._visible or bpy.app.background or _active is not None:
            return self
        wm = bpy.context.window_manager
        if wm is None or not wm.windows:
            return self
        self._wm = wm
        _active = self
        self._owns_ui = True
        try:
            self._handle = bpy.types.SpaceView3D.draw_handler_add(
                _draw, (), 'WINDOW', 'POST_PIXEL')
            wm.progress_begin(0, 1000)
            self._redraw(force=True)
        except Exception:
            self.__exit__(None, None, None)
        return self

    def present(self):
        if self._owns_ui:
            self._redraw(force=True, swap=True)

    def wait_for_shading(self, scene):
        if self._owns_ui:
            self.detail = 'Shading viewport…'
            self._shading_scene = scene
            self._started = self._quiet_since = time.monotonic()
            self._redraw(force=True)
            if not bpy.app.timers.is_registered(_shading_tick):
                bpy.app.timers.register(_shading_tick, first_interval=.12)

    def update(self, fraction, detail=None):
        self.fraction = min(1.0, max(0.0, float(fraction)))
        if detail is not None:
            self.detail = detail
        if self._owns_ui:
            self._wm.progress_update(round(self.fraction * 1000))
            self._redraw()

    def batch(self, completed, total, start=0.0, end=1.0, label='Items'):
        total = max(1, total)
        self.update(start + (end - start) * min(completed, total) / total,
                    f'{label}: {min(completed, total):,} / {total:,}')

    def _redraw(self, force=False, swap=False):
        now = time.monotonic()
        if not force and now - self._last_draw < .18:
            return
        self._last_draw = now
        for window in self._wm.windows:
            for area in window.screen.areas:
                if area.type == 'VIEW_3D':
                    area.tag_redraw()
        if self._deferred_redraw and not swap:
            return
        try:
            bpy.ops.wm.redraw_timer(type='DRAW_WIN_SWAP', iterations=1)
        except (RuntimeError, AttributeError):
            pass

    def __exit__(self, _type, _value, _traceback):
        global _active
        if not self._owns_ui or (self._shading_scene and _type is None):
            return False
        try:
            if self._wm is not None:
                self._wm.progress_end()
        finally:
            if self._handle is not None:
                bpy.types.SpaceView3D.draw_handler_remove(self._handle, 'WINDOW')
            _active = None
            self._owns_ui = False
            if self._wm is not None:
                for window in self._wm.windows:
                    for area in window.screen.areas:
                        if area.type == 'VIEW_3D':
                            area.tag_redraw()
        return False
