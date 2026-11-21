"""Surface placement changes the native decal frame, never its export target."""
from . import i18n
import math

import bpy
from bpy_extras.view3d_utils import region_2d_to_origin_3d, region_2d_to_vector_3d
from mathutils import Matrix, Vector

from . import decals
from .bubble_controls import fixed_panel_position, projected_bounds

_anchors = {}


def selected_decal(context):
    obj = context.active_object
    return (obj if context.mode == 'OBJECT' and obj is not None
            and decals.is_decal(obj) and obj.select_get()
            and len(context.selected_objects) == 1 else None)


def surface_hit(context, origin, direction):
    """Pick the first visible build face, passing through decal artwork/helpers."""
    origin, direction = Vector(origin), Vector(direction).normalized()
    depsgraph = context.evaluated_depsgraph_get()
    from .viewport_cutaway import scene_pick
    for _ in range(128):
        hit, point, normal, face, obj, matrix = scene_pick(
            context.scene, depsgraph, origin, direction, distance=1e6)
        if not hit:
            return None
        original = obj.original
        if (original.type == 'MESH' and not decals.is_decal(original)
                and not original.get(decals.PREVIEW) and not original.hide_render
                and original.visible_get(view_layer=context.view_layer)
                and (original.get('ObjectID') or original.get('GroupID'))):
            # Place the artwork facing the side the user actually clicked.
            if normal.dot(direction) > 0:
                normal = -normal
            return point.copy(), normal.normalized(), original
        origin = point + direction * .0001
    return None


def surface_matrix(obj, point, normal, offset=.002):
    """Align the artwork plane to the face, retaining scale and artwork roll."""
    normal = Vector(normal).normalized()
    if normal.length < .5 or abs(obj.matrix_world.determinant()) < 1e-12:
        raise ValueError('The decal needs a nonzero scale and a valid surface normal')
    old = obj.matrix_world.copy()
    old_normal = old.to_3x3().inverted().transposed() @ Vector((0, 1, 0))
    turn = old_normal.normalized().rotation_difference(normal).to_matrix()
    result = (turn @ old.to_3x3()).to_4x4()
    result.translation = Vector(point) + normal * offset
    return result


class BBE_OT_place_decal_surface(bpy.types.Operator):
    bl_idname = 'bbe.place_decal_surface'
    bl_translation_context = "BBEExtendedInterface"
    bl_label = 'Place Decal on Surface'
    bl_description = 'Click a visible build face to place and angle this decal; Esc cancels'
    bl_options = {'REGISTER', 'UNDO', 'BLOCKING'}

    @classmethod
    def poll(cls, context):
        return (context.area is not None and context.area.type == 'VIEW_3D'
                and context.region is not None and context.region.type == 'WINDOW'
                and selected_decal(context) is not None)

    def invoke(self, context, event):
        self._name = context.active_object.name
        self._area = context.area
        context.window.cursor_modal_set('CROSSHAIR')
        context.area.header_text_set('Click a build surface to place the decal · Esc cancels')
        context.window_manager.modal_handler_add(self)
        return {'RUNNING_MODAL'}

    def finish(self, context):
        self._area.header_text_set(None)
        context.window.cursor_modal_restore()
        self._area.tag_redraw()

    def modal(self, context, event):
        obj = context.scene.objects.get(self._name)
        if event.type in {'ESC', 'RIGHTMOUSE'} or obj is None or context.active_object != obj:
            self.finish(context)
            return {'CANCELLED'}
        if event.type in {'MOUSEMOVE', 'LEFTMOUSE'}:
            xy = (event.mouse_region_x, event.mouse_region_y)
            if not (0 <= xy[0] < context.region.width and 0 <= xy[1] < context.region.height):
                return {'RUNNING_MODAL'}
            origin = region_2d_to_origin_3d(context.region, context.region_data, xy)
            direction = region_2d_to_vector_3d(context.region, context.region_data, xy)
            hit = surface_hit(context, origin, direction)
            label = f'Place on {hit[2].name}' if hit else 'Point at a visible build surface'
            self._area.header_text_set(label + ' · Click to place · Esc cancels')
            if event.type == 'LEFTMOUSE' and event.value == 'PRESS' and hit:
                try:
                    obj.matrix_world = surface_matrix(obj, hit[0], hit[1])
                except ValueError as exc:
                    self.report({'WARNING'}, str(exc))
                    return {'RUNNING_MODAL'}
                decals.request_refresh()
                self.finish(context)
                return {'FINISHED'}
        if event.type in {'MIDDLEMOUSE', 'WHEELUPMOUSE', 'WHEELDOWNMOUSE', 'TRACKPADPAN', 'TRACKPADZOOM'}:
            return {'PASS_THROUGH'}
        return {'RUNNING_MODAL'}


class BBE_OT_move_decal_free(bpy.types.Operator):
    bl_idname = 'bbe.move_decal_free'
    bl_translation_context = "BBEExtendedInterface"
    bl_label = 'Move Decal Freely'
    bl_description = 'Move with snapping initially off; keep the current preview mode; Esc cancels'

    @classmethod
    def poll(cls, context):
        return selected_decal(context) is not None

    def invoke(self, context, event):
        bpy.ops.transform.translate('INVOKE_DEFAULT', snap=False, release_confirm=False)
        return {'FINISHED'}


class BBE_OT_adjust_decal(bpy.types.Operator):
    bl_idname = 'bbe.adjust_decal'
    bl_translation_context = "BBEExtendedInterface"
    bl_label = 'Adjust Decal Placement'
    bl_description = 'Rotate the artwork or move along its surface normal; this exports to the game'
    bl_options = {'REGISTER', 'UNDO'}
    angle: bpy.props.FloatProperty(name='Artwork rotation', subtype='ANGLE')
    distance: bpy.props.FloatProperty(name='Surface offset', subtype='DISTANCE')

    @classmethod
    def poll(cls, context):
        return selected_decal(context) is not None

    def execute(self, context):
        obj = context.active_object
        matrix = obj.matrix_world.copy()
        if abs(matrix.determinant()) < 1e-12:
            self.report({'WARNING'}, 'The decal needs a nonzero scale')
            return {'CANCELLED'}
        normal = (matrix.to_3x3().inverted().transposed() @ Vector((0, 1, 0))).normalized()
        turn = Matrix.Rotation(self.angle, 3, normal)
        result = (turn @ matrix.to_3x3()).to_4x4()
        result.translation = matrix.translation + normal * self.distance
        obj.matrix_world = result
        decals.request_refresh()
        return {'FINISHED'}


class BBE_OT_rotate_decal(bpy.types.Operator):
    bl_idname = 'bbe.rotate_decal'
    bl_translation_context = "BBEExtendedInterface"
    bl_label = 'Rotate Decal'
    bl_description = 'Enter a positive or negative angle in degrees to rotate the artwork'
    bl_options = {'REGISTER', 'UNDO'}
    degrees: bpy.props.FloatProperty(name='Degrees', default=0.0, precision=2,
        description='Rotation from the current orientation; negative values rotate the other way')

    @classmethod
    def poll(cls, context):
        return selected_decal(context) is not None

    def invoke(self, context, event):
        self.degrees = 0.0
        return context.window_manager.invoke_props_dialog(self, width=280)

    def draw(self, context):
        i18n.localized_layout(self.layout).prop(self, 'degrees')

    def execute(self, context):
        # Reuse the existing placement math without nesting undo operators.
        self.angle = math.radians(self.degrees)
        self.distance = 0.0
        return BBE_OT_adjust_decal.execute(self, context)


class BBE_OT_toggle_decal_projection(bpy.types.Operator):
    bl_idname = 'bbe.toggle_decal_projection'
    bl_translation_context = "BBEExtendedInterface"
    bl_label = 'Toggle Decal Projection Preview'
    bl_description = 'Switch between projected and flat artwork in Blender only; game export is unchanged'
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return selected_decal(context) is not None

    def execute(self, context):
        obj = context.active_object
        obj[decals.PREVIEW_DISABLED] = not obj.get(decals.PREVIEW_DISABLED, False)
        addon = context.preferences.addons.get(__package__)
        if addon:
            addon.preferences.decal_projection_disabled = obj[decals.PREVIEW_DISABLED]
            bpy.ops.wm.save_userpref()
        decals.request_refresh()
        return {'FINISHED'}


def panel_key(context):
    return context.window.as_pointer(), context.area.as_pointer(), context.region.as_pointer()


class BBE_OT_move_decal_controls(bpy.types.Operator):
    bl_idname = 'bbe.move_decal_controls'
    bl_translation_context = "BBEExtendedInterface"
    bl_label = 'Move Decal Controls'
    bl_description = 'Drag to reposition this panel; it stays here between decals'
    bl_options = {'INTERNAL', 'BLOCKING'}

    def invoke(self, context, event):
        self._key = panel_key(context)
        self._anchor = _anchors.get(self._key)
        if self._anchor is None:
            return {'CANCELLED'}
        self._mouse = (event.mouse_region_x, event.mouse_region_y)
        context.window_manager.modal_handler_add(self)
        return {'RUNNING_MODAL'}

    def modal(self, context, event):
        if event.type in {'ESC', 'RIGHTMOUSE'}:
            _anchors[self._key] = self._anchor
            context.area.tag_redraw()
            return {'CANCELLED'}
        if event.type == 'MOUSEMOVE':
            _anchors[self._key] = (self._anchor[0]+event.mouse_region_x-self._mouse[0],
                                   self._anchor[1]+event.mouse_region_y-self._mouse[1])
            context.area.tag_redraw()
        if event.type == 'LEFTMOUSE' and event.value == 'RELEASE':
            return {'FINISHED'}
        return {'RUNNING_MODAL'}


class BBE_GGT_decal_controls(bpy.types.GizmoGroup):
    bl_idname = 'BBE_GGT_decal_controls'
    bl_label = 'Decal placement controls'
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'WINDOW'
    bl_options = {'PERSISTENT'}

    @classmethod
    def poll(cls, context):
        from . import undo_guard
        return not undo_guard.restoring and selected_decal(context) is not None

    def setup(self, context):
        self.card = self.gizmos.new('BBE_GT_tube_button')
        self.card.hide_select = True
        self.card.color = (.055, .07, .09)
        self.card.alpha = .96
        self.grip = self.gizmos.new('BBE_GT_tube_button')
        self.grip.target_set_operator('bbe.move_decal_controls')
        self.grip.use_tooltip = True
        self.buttons = []
        for label, op in (('Place on Surface', 'bbe.place_decal_surface'),
                          ('Free Move', 'bbe.move_decal_free'),
                          ('Rotate…  Enter degrees', 'bbe.rotate_decal'),
                          ('Closer 1 cm', 'bbe.adjust_decal'), ('Away 1 cm', 'bbe.adjust_decal'),
                          ('Projection Preview: ON', 'bbe.toggle_decal_projection')):
            button = self.gizmos.new('BBE_GT_tube_button')
            button.text = label
            button.color = (.18, .23, .29)
            button.alpha = 1
            button.color_highlight = (.22, .43, .61)
            button.alpha_highlight = 1
            button.use_tooltip = True
            self.buttons.append((button, button.target_set_operator(op)))
        self.buttons[3][1].distance = -.01
        self.buttons[4][1].distance = .01
        self.card.buttons = tuple(b for b, _ in self.buttons)

    def draw_prepare(self, context):
        scale = context.preferences.system.ui_scale
        width, height = 290*scale, 187*scale
        right = context.region.width-60*scale
        for region in context.area.regions:
            if region.type == 'UI' and region.width > 1:
                right -= region.width
        key = panel_key(context)
        bounds = ((projected_bounds(context, context.active_object) or (0, 0, 0, 0))
                  if key not in _anchors else (0, 0, 0, 0))
        if key not in _anchors and len(_anchors) > 64:
            _anchors.clear()
        (x, y), _anchors[key] = fixed_panel_position(_anchors.get(key), bounds, [bounds],
            (60*scale, 40*scale, right, context.region.height-100*scale), (width, height), height)
        self.card.matrix_basis = Matrix.Translation((x, y, 0))
        self.card.width, self.card.height, self.card.font_size = width, height, 11*scale
        self.card.lines = ((10*scale, height-19*scale, 'Decal placement', (.94, .95, .97, 1)),
                           (10*scale, 10*scale, 'Preview toggle does not change export.', (.72, .79, .85, 1)))
        self.grip.matrix_basis = Matrix.Translation((x, y+height-28*scale, 0))
        self.grip.width, self.grip.height = width, 28*scale
        for i, (button, _) in enumerate(self.buttons):
            row, col = ((0, 0), (0, 1), (1, 0), (2, 0), (2, 1), (3, 0))[i]
            button.matrix_basis = Matrix.Translation((x+(10+140*col)*scale, y+height-(58+31*row)*scale, 0))
            button.width, button.height, button.font_size = 130*scale, 26*scale, 11*scale
        self.buttons[2][0].width = 270*scale
        toggle = self.buttons[5][0]
        toggle.width = 270*scale
        toggle.text = ('Projection Preview: OFF (Flat)' if context.active_object.get(decals.PREVIEW_DISABLED)
                       else 'Projection Preview: ON')


_classes = (BBE_OT_place_decal_surface, BBE_OT_move_decal_free, BBE_OT_adjust_decal, BBE_OT_rotate_decal, BBE_OT_toggle_decal_projection,
            BBE_OT_move_decal_controls, BBE_GGT_decal_controls)


def register():
    for cls in _classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(_classes):
        bpy.utils.unregister_class(cls)
    _anchors.clear()
