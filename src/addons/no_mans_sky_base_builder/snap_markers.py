"""Clickable snap choices for the two selected parts only."""
import math
import bpy
import gpu
from bpy.app.handlers import persistent
from gpu_extras.batch import batch_for_shader
from bpy_extras.view3d_utils import location_3d_to_region_2d
from mathutils import Matrix, Vector
from . import corvette_snapping, base_snapping

SESSION = {}
_BUBBLE_POINTS = {}


def bubble_pair(source, target):
    return source != target and all(o.get('ObjectID') == 'BASE_BUBPIPE' for o in (source, target))


def bubble_points(source, target):
    """Use fixed duct openings, never the hidden native shape-selecting faces."""
    from . import bubble_preview as bubble
    scene = target.users_scene[0] if target.users_scene else bpy.context.scene
    others = [o for o in bubble._native_objects(scene) if o != source]
    signature = (source.name, target.name, tuple((o.name, tuple(v for row in o.matrix_world for v in row),
                 bubble._visible_sockets(o)) for o in others))
    cached = _BUBBLE_POINTS.get(scene.name)
    if cached is None or cached[0] != signature:
        occupied = bubble._editor_contacts(others).get(target.name, set())
        keys = tuple(k for k in bubble._visible_sockets(target) if k not in occupied)
        _BUBBLE_POINTS[scene.name] = (signature, keys)
    else:
        keys = cached[1]
    return [(k, target.matrix_world @ Vector(bubble._OFFSETS[k])) for k in keys]


def native_engine(source, target):
    return next((engine for engine in (corvette_snapping, base_snapping)
                 if engine.supports(source, target)), None)


def objects(context):
    names = SESSION.get(context.scene.name)
    if not names:
        return None
    source, target = (context.scene.objects.get(n) for n in names)
    if source is None or target is None or set(context.selected_objects) != {source, target}:
        return None
    return source, target


def options(source, target):
    if bubble_pair(source, target):
        return bubble_points(source, target)
    engine = native_engine(source, target)
    if engine:
        return engine.target_points(source, target)
    if source.get('ObjectID') == 'BASE_BUBPIPE':
        return []
    # Gizmo polling must stay read-only: constructing Part wrappers writes
    # SnapID and is forbidden inside Blender draw callbacks.
    from .part import Part
    from .utils import materials_v2,mirror_pivot
    def group(obj):
        pid=obj.get('ObjectID')
        if pid=='BASE_BUBPIPE' and not materials_v2.is_high_res(obj):return 'BUBBLE_STRAIGHT_LEGACY'
        return next((key for key,row in Part.SNAP_MATRIX_DICTIONARY.items() if pid in row['parts']),None)
    a,b=group(source),group(target)
    pairing=Part.SNAP_PAIR_DICTIONARY.get(b,{}).get(a)
    if not pairing:return []
    points=Part.SNAP_MATRIX_DICTIONARY[b].get('snap_points',{})
    frame=target.matrix_world
    if mirror_pivot.is_normalized(target):frame=frame@Matrix.Translation(mirror_pivot.pivot(target.get('ObjectID')))
    return [(key.strip(),frame@Matrix(points[key.strip()]['matrix']).translation)
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


def selected_pair(context):
    selected=context.selected_objects
    target=context.active_object
    if len(selected)!=2 or target not in selected:return None
    source=next(o for o in selected if o!=target)
    return (source,target) if options(source,target) else None


def place_at(source,target,key,cycle=False):
    engine=native_engine(source,target)
    if bubble_pair(source,target):
        from . import bubble_preview
        repeat=cycle and source.get('bbe_native_snap_target')==target.name and source.get('bbe_native_target_socket')==key
        return bubble_preview.snap_native(source,target,target_key=key,next_source=repeat)
    if engine:
        choice=engine.choose(source,target,key,cycle_source=cycle)
        if not choice:return False
        engine.apply(source,target,choice)
        return True
    from .builder import get_builder
    builder=get_builder()
    a,b=(builder.get_builder_object_from_bpy_object(o) for o in (source,target))
    if not a or not b:return False
    a.SNAP_CACHE.setdefault(target.name,{})['target']=key
    return a.snap_to(b) is not False


def place_initial(context,source,target):
    if target is None:return False
    choices=options(source,target)
    if not choices or not place_at(source,target,choices[0][0]):return False
    for obj in tuple(context.selected_objects):obj.select_set(False)
    source.select_set(True);target.select_set(True)
    context.view_layer.objects.active=target
    start(context,source,target)
    return True


class BBE_OT_quick_snap(bpy.types.Operator):
    bl_idname='bbe.quick_snap'
    bl_label='Snap Selected Parts'
    bl_description='Snap the other selected part to the active part, then click a green target to change its connection'
    bl_options={'REGISTER','UNDO'}
    def execute(self,context):
        pair=selected_pair(context)
        if not pair or not place_initial(context,*pair):return {'CANCELLED'}
        return {'FINISHED'}


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
        if not place_at(source,target,self.target_key,cycle=True):return {'CANCELLED'}
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


CLASSES = (BBE_OT_quick_snap, BBE_OT_click_snap, BBE_GT_snap_target, BBE_GGT_snap_targets)

@persistent
def _reset_session(*args):
    SESSION.clear()
    _BUBBLE_POINTS.clear()
    corvette_snapping.CACHE.clear()
    base_snapping.CACHE.clear()

@persistent
def _reset_history(*args):
    _BUBBLE_POINTS.clear()
    corvette_snapping.CACHE.clear()
    base_snapping.CACHE.clear()

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
