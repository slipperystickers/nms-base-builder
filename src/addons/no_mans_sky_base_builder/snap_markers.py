"""Clickable snap choices for the two selected parts only."""
import math
import bpy
import gpu
from bpy.app.handlers import persistent
from gpu_extras.batch import batch_for_shader
from bpy_extras.view3d_utils import location_3d_to_region_2d
from mathutils import Matrix, Vector
from . import corvette_snapping

SESSION = {}


def objects(context):
    names = SESSION.get(context.scene.name)
    if not names:
        return None
    source, target = (context.scene.objects.get(n) for n in names)
    if source is None or target is None or set(context.selected_objects) != {source, target}:
        return None
    return source, target


def options(source, target):
    native = corvette_snapping.options(source, target)
    if native:
        return list({p[0]: p[2] for p in native}.items())
    if source.get('ObjectID') == 'BASE_BUBPIPE':
        return []
    from .builder import get_builder
    builder = get_builder()
    a, b = (builder.get_builder_object_from_bpy_object(o) for o in (source, target))
    if not a or not b:
        return []
    pairing = a.get_snap_pair_options(b)
    if not pairing:
        return []
    points = b.get_snap_points() or {}
    return [(key.strip(), target.matrix_world @ Matrix(points[key.strip()]['matrix']).translation)
            for key in pairing[0].split(',') if key.strip() in points]


def start(context, source, target):
    if not options(source, target):
        return False
    SESSION[context.scene.name] = (source.name, target.name)
    for area in context.screen.areas:
        if area.type == 'VIEW_3D':
            area.spaces.active.show_gizmo = True
            area.tag_redraw()
    return True


class BBE_OT_click_snap(bpy.types.Operator):
    bl_idname = 'bbe.click_snap_point'
    bl_label = 'Snap to This Connection'
    bl_description = 'Move the first selected part to this connection on the target; click again to cycle its source connection'
    bl_options = {'REGISTER', 'UNDO'}
    target_key: bpy.props.StringProperty()

    def execute(self, context):
        pair = objects(context)
        if not pair:
            return {'CANCELLED'}
        source, target = pair
        choice = corvette_snapping.choose(source, target, self.target_key, cycle_source=True)
        if choice:
            corvette_snapping.apply(source, target, choice)
        else:
            from .builder import get_builder
            builder = get_builder()
            a, b = (builder.get_builder_object_from_bpy_object(o) for o in pair)
            a.SNAP_CACHE.setdefault(target.name, {})['target'] = self.target_key
            if a.snap_to(b) is False:
                return {'CANCELLED'}
        source.select_set(True); target.select_set(True)
        context.view_layer.objects.active = target
        return {'FINISHED'}


class BBE_GT_snap_target(bpy.types.Gizmo):
    bl_idname = 'BBE_GT_snap_target'
    __slots__ = ('radius',)

    def setup(self):
        self.radius = 11

    def draw(self, context):
        x,y = self.matrix_basis.translation[:2]
        points = [(x+math.cos(i*math.tau/32)*self.radius,
                   y+math.sin(i*math.tau/32)*self.radius) for i in range(33)]
        shader = gpu.shader.from_builtin('UNIFORM_COLOR')
        shader.bind();shader.uniform_float('color', (.5,1,.5,1) if self.is_highlight else (.1,.9,.25,.9))
        gpu.state.blend_set('ALPHA')
        batch_for_shader(shader, 'LINE_STRIP', {'pos':points}).draw(shader)
        batch_for_shader(shader, 'LINES', {'pos':[(x-5,y),(x+5,y),(x,y-5),(x,y+5)]}).draw(shader)
        gpu.state.blend_set('NONE')

    def draw_select(self, context, select_id):
        pass

    def test_select(self, context, location):
        return 0 if (Vector(location)-Vector(self.matrix_basis.translation[:2])).length <= self.radius+3 else -1


class BBE_GGT_snap_targets(bpy.types.GizmoGroup):
    bl_idname = 'BBE_GGT_snap_targets'
    bl_label = 'BBE Snap Targets'
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'WINDOW'
    bl_options = {'PERSISTENT', 'SHOW_MODAL_ALL'}

    @classmethod
    def poll(cls, context):
        return context.mode == 'OBJECT' and objects(context) is not None

    def setup(self, context):
        self.targets = []

    def draw_prepare(self, context):
        pair = objects(context)
        choices = options(*pair) if pair else []
        while len(self.targets) < len(choices):
            gizmo = self.gizmos.new('BBE_GT_snap_target')
            gizmo.use_tooltip = True
            self.targets.append(gizmo)
        for i, gizmo in enumerate(self.targets):
            gizmo.hide = True
            if i >= len(choices):
                continue
            key, position = choices[i]
            point = location_3d_to_region_2d(context.region, context.region_data, position)
            if point is None:
                continue
            gizmo.hide = False
            gizmo.matrix_basis = Matrix.Translation((point.x,point.y,0))
            gizmo.target_set_operator('bbe.click_snap_point').target_key = key


CLASSES = (BBE_OT_click_snap, BBE_GT_snap_target, BBE_GGT_snap_targets)

@persistent
def _reset_session(*args):
    SESSION.clear()
    corvette_snapping.CACHE.clear()

@persistent
def _reset_history(*args):
    corvette_snapping.CACHE.clear()

def register():
    for cls in CLASSES:bpy.utils.register_class(cls)
    bpy.app.handlers.load_post.append(_reset_session)
    bpy.app.handlers.undo_post.append(_reset_history)
    bpy.app.handlers.redo_post.append(_reset_history)
def unregister():
    _reset_session()
    if _reset_session in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.remove(_reset_session)
    for handlers in (bpy.app.handlers.undo_post, bpy.app.handlers.redo_post):
        if _reset_history in handlers:handlers.remove(_reset_history)
    for cls in reversed(CLASSES):bpy.utils.unregister_class(cls)
