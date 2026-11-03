"""Selectable, transform-locked pilot references; no scene edits during drawing.

Pristine pose meshes are cached; calibrated poses use private mesh copies.
Native constraints/drivers handle attachment, including parent transforms.
Native contact calculations refresh deferred, outside dependency-graph handlers.
The character remains full-sized and does not inherit cockpit scale.
"""
import math
import os
from pathlib import Path

import bpy
from mathutils import Matrix

TAG = 'bbe_pilot_reference'
ROOT_TAG = 'bbe_pilot_root'
TARGET = 'bbe_pilot_cockpit'
RACE = 'bbe_pilot_race'
DETAIL = 'bbe_pilot_detail'
RACES = (('ASTRO_DEFAULT', 'Anomaly'), ('GEK_DEFAULT', 'Gek'),
         ('KORVAX_DEFAULT', 'Korvax'), ('VYKEEN_DEFAULT', "Vy’keen"),
         ('FOURTH_DEFAULT', 'Traveller'), ('BUI_DEFAULT', 'Autophage'),
         ('ASTRO_ARMOURED', 'Armoured Anomaly'))
# Native PLAYERPOSITION chain, in the cockpit's native (Y-up) object axes.
# B_COK_D's scaled locator and full-size pose were checked against live game
# attachment, hip and wrist transforms. Other IDs use their native chains.
NATIVE = {'B_COK_A': (0, .58545, 4.079198),
          'B_COK_B': (0, -.902641, 4.234156),
          'B_COK_D': (0, .390375, 1.951858),
          'B_COK_E': (0, .333333, 9.3561768)}
for _id in (f'B_COK_C{i}' for i in range(1, 10)):
    NATIVE[_id] = (0, .610473, 4.768588)


def cockpit_id(obj):
    return str(obj.get('ObjectID', '')).lstrip('^') if obj else ''


def first_cockpit(scene):
    """Match Builder's stable export order, including legacy/missing order values."""
    return min((obj for obj in scene.objects if cockpit_id(obj) in NATIVE),
               key=lambda obj: obj.get('order', 0), default=None)


def target(context):
    obj = getattr(context, 'active_object', context.view_layer.objects.active)
    if context.mode != 'OBJECT' or obj is None or not obj.select_get():
        return None
    if not obj.get(TAG) and cockpit_id(obj) not in NATIVE:
        return None
    first = first_cockpit(context.scene)
    return first if obj.get(TAG) or obj == first else None


def references(scene, cockpit):
    return [obj for obj in scene.objects if obj.get(TAG) and obj.get(TARGET) == cockpit]


def preview(context):
    cockpit = target(context)
    if cockpit is None:
        return None
    return next(iter(references(context.scene, cockpit)), None)


def asset_path(race, detailed):
    if race not in dict(RACES):
        raise ValueError('Unknown pilot reference')
    override = os.environ.get('BBE_PILOT_ASSET_ROOT')
    if override:
        path = Path(override) / ('detailed' if detailed else 'light') / (race + '.blend')
    elif detailed:
        from . import hd_library
        roots = (hd_library.characters_root(), hd_library.additions_root(), hd_library.library_root(),
                 Path(__file__).parent / 'resources/hd_additions')
        candidates = [root / 'pilot_references' / (race + '.blend') for root in roots if root]
        path = next((candidate for candidate in candidates if candidate.is_file()), None)
        if path is None:
            raise ValueError('Detailed pilot model is missing from the HD pack; showing the lightweight reference')
    else:
        path = Path(__file__).parent / 'resources/pilot_references' / (race + '.blend')
    if not path.is_file():
        raise ValueError('Detailed pilot references need the updated HD pack' if detailed
                         else 'Pilot reference assets are not installed')
    return path


def mesh_for(race, detailed):
    key = f'{race}:{int(detailed)}:colour2'
    cached = next((m for m in bpy.data.meshes if m.get('bbe_pilot_asset') == key), None)
    if cached:
        if detailed:
            relink_texture_images()
        return cached
    path = asset_path(race, detailed)
    with bpy.data.libraries.load(str(path), link=False) as (src, dst):
        dst.meshes = list(src.meshes)
    meshes = [m for m in dst.meshes if m]
    if len(meshes) != 1:
        raise ValueError('Invalid pilot mesh library')
    mesh = meshes[0]
    required = {node.image.get('bbe_pilot_texture') for mat in mesh.materials if mat and mat.use_nodes
                for node in mat.node_tree.nodes if getattr(node, 'image', None)
                and node.image.get('bbe_pilot_texture')}
    if any(Path(name).name != name or not (path.parent / 'textures' / name).is_file() for name in required):
        materials = list(mesh.materials)
        images = {node.image for mat in materials if mat and mat.use_nodes
                  for node in mat.node_tree.nodes if getattr(node, 'image', None)}
        bpy.data.meshes.remove(mesh)
        for mat in materials:
            if mat and mat.users == 0:
                bpy.data.materials.remove(mat)
        for image in images:
            if image.users == 0:
                bpy.data.images.remove(image)
        raise ValueError('Pilot colour textures are missing from the HD pack; showing the lightweight reference')
    # Libraries contain portable shared texture names, not the build machine's paths.
    for material in mesh.materials:
        if material is None or not material.use_nodes:
            continue
        for node in material.node_tree.nodes:
            image = getattr(node, 'image', None)
            name = image.get('bbe_pilot_texture') if image else None
            if not name or Path(name).name != name:
                continue
            destination = path.parent / 'textures' / name
            if not destination.is_file():
                raise ValueError('Pilot colour textures are missing from the HD pack; showing the lightweight reference')
            shared = next((im for im in bpy.data.images if im != image and
                           im.get('bbe_pilot_texture') == name and
                           im.colorspace_settings.name == image.colorspace_settings.name), None)
            if shared:
                # Texture names are content hashes. Pack relocation must not
                # duplicate their decoded images each time a pilot is changed.
                if shared.filepath != str(destination):
                    shared.filepath = str(destination)
                    shared.reload()
                node.image = shared
                if image.users == 0:
                    bpy.data.images.remove(image)
            elif image.filepath != str(destination):
                image.filepath = str(destination)
                image.reload()
    mesh['bbe_pilot_asset'] = key
    return mesh


def relink_texture_images(images=None):
    """Keep saved/shared pilot previews portable across HD pack locations."""
    images = [image for image in (bpy.data.images if images is None else images)
              if image.get('bbe_pilot_texture') and not image.packed_file]
    if not images:
        return 0
    from . import hd_library
    roots = [root / 'pilot_references/textures' for root in
             (hd_library.characters_root(), hd_library.additions_root(), hd_library.library_root(),
              Path(__file__).parent / 'resources/hd_additions') if root]
    changed = 0
    for image in images:
        name = image.get('bbe_pilot_texture')
        if not isinstance(name, str) or Path(name).name != name or image.packed_file:
            continue
        destination = next((root / name for root in roots if (root / name).is_file()), None)
        if destination and image.filepath != str(destination):
            image.filepath = str(destination)
            image.reload()
            changed += 1
    return changed


def locked(obj, selectable):
    obj.hide_select = not selectable
    obj.lock_location = obj.lock_rotation = obj.lock_scale = (True, True, True)
    obj.hide_render = True


def constant_driver(obj, path, index, expression, cockpit=None):
    obj.driver_remove(path, index)
    curve = obj.driver_add(path, index)
    driver = curve.driver
    driver.type = 'SCRIPTED'
    driver.expression = expression
    if cockpit is not None:
        variable = driver.variables.new()
        variable.name = 's'
        variable.type = 'TRANSFORMS'
        variable.targets[0].id = cockpit
        variable.targets[0].transform_type = 'SCALE_Y'
        variable.targets[0].transform_space = 'WORLD_SPACE'


def set_pose_drivers(model, cockpit):
    # Remove properties left by the rejected geometry-snapping experiment.
    # Seat fitting is not the native contact calculation used by pilot_pose.
    for key in ('bbe_pilot_seat_root_up', 'bbe_pilot_seat_root_forward', 'bbe_pilot_seat_lift_m'):
        model.pop(key, None)
    # Mesh libraries are Z-up; the cockpit's imported local mesh is Y-up.
    # PLAYERPOSITION faces native -Z (180 degrees about native Y).
    rotation = (Matrix.Rotation(math.pi, 4, 'Y') @ Matrix.Rotation(-math.pi/2, 4, 'X')).to_euler()
    # Runtime sampling of the user's micro B_COK_D confirms the entire native
    # PLAYERPOSITION translation scales with the cockpit. The character pose
    # stays full size. Camera-fitted constants are not attachment transforms.
    native_y, native_z = NATIVE[cockpit_id(cockpit)][1:]
    offset = ('0.0', f's*{native_y!r}', f's*{native_z!r}')
    for axis in range(3):
        constant_driver(model, 'location', axis, offset[axis], cockpit if axis else None)
        constant_driver(model, 'rotation_euler', axis, repr(rotation[axis]))
        constant_driver(model, 'scale', axis, '1.0')
    model['bbe_pilot_position_status'] = 'Native cockpit locator; full-size seated pose'
    model['bbe_pilot_pose_version'] = 8
    model['bbe_pilot_locator_id'] = cockpit_id(cockpit)


def retarget_reference(model, cockpit):
    root = model.parent
    if root is None or not root.get(ROOT_TAG):
        raise ValueError('Pilot anchor is missing; remove this reference and choose again')
    root[TARGET] = model[TARGET] = cockpit
    for constraint in root.constraints:
        if constraint.type in {'COPY_LOCATION', 'COPY_ROTATION'}:
            constraint.target = cockpit
    root.name = 'Pilot anchor — ' + cockpit.name
    for collection in model.users_collection:
        if collection.get('bbe_pilot_collection'):
            collection.name = 'Pilot reference — ' + cockpit.name
    set_pose_drivers(model, cockpit)


def sync_flight_reference(context):
    """Called by explicit cockpit-order edits, never from draw/depsgraph handlers."""
    cockpit = first_cockpit(context.scene)
    if cockpit:
        for model in context.scene.objects:
            if model.get(TAG):
                retarget_reference(model, cockpit)
    from . import pilot_pose
    pilot_pose.update_scene(context.scene, force=True)


@bpy.app.handlers.persistent
def refresh_saved_pilot_poses(_):
    """Defer migration until Blender has finished restoring the file."""
    from . import pilot_pose, undo_guard
    for scene in bpy.data.scenes:
        if any(model.get(TAG) for model in scene.objects):
            undo_guard.track_generated_preview()
    pilot_pose.invalidate()


def scene_detail(scene):
    from .hd_library_ui import detailed_enabled
    return detailed_enabled(scene)


def resolved_mesh(race, detailed):
    try:
        return mesh_for(race, detailed), detailed, ''
    except ValueError as exc:
        if not detailed:
            raise
        # Choosing a character must remain usable with an older HD pack.
        return mesh_for(race, False), False, str(exc)


def sync_scene_quality(scene, detailed):
    """Reuse cached meshes when BBE's existing proxy-quality action runs."""
    switched = missing = 0
    for model in scene.objects:
        if not model.get(TAG):
            continue
        mesh, actual, warning = resolved_mesh(model[RACE], detailed)
        model[DETAIL] = actual
        model['bbe_pilot_asset_warning'] = warning
        from . import pilot_pose
        pilot_pose.update_model(scene, model, mesh)
        switched += 1
        missing += bool(warning)
    return switched, missing


def choose(context, race):
    cockpit = target(context)
    if cockpit is None:
        raise ValueError('Select the first Corvette cockpit or its pilot reference')
    scale = cockpit.matrix_world.to_scale()
    if min(scale) <= 0 or max(scale)-min(scale) > max(scale)*1e-4:
        raise ValueError('Pilot references require a positive, uniform cockpit scale')
    # Resolve asset before mutating the scene; failures preserve the old model.
    mesh, detailed, warning = resolved_mesh(race, scene_detail(context.scene))
    existing = [obj for obj in context.scene.objects if obj.get(TAG)]
    model = existing[0] if existing else None
    if model is None:
        collection = bpy.data.collections.new('Pilot reference — ' + cockpit.name)
        collection['bbe_pilot_collection'] = True
        context.scene.collection.children.link(collection)
        root = bpy.data.objects.new('Pilot anchor — ' + cockpit.name, None)
        collection.objects.link(root)
        root[ROOT_TAG] = True
        root[TARGET] = cockpit
        locked(root, False)
        for kind in ('COPY_LOCATION', 'COPY_ROTATION'):
            constraint = root.constraints.new(kind)
            constraint.target = cockpit
            constraint.target_space = constraint.owner_space = 'WORLD'
        model = bpy.data.objects.new('Pilot reference', mesh)
        collection.objects.link(model)
        model.parent = root
        model[TAG] = True
        model[TARGET] = cockpit
        locked(model, True)
    retarget_reference(model, cockpit)
    model.name = dict(RACES)[race] + ' pilot — ' + cockpit.name
    model[RACE], model[DETAIL] = race, detailed
    model['bbe_pilot_asset_warning'] = warning
    # Track generated IDs across Undo without changing preferences permanently.
    from . import undo_guard
    undo_guard.track_generated_preview()
    from . import pilot_pose
    pilot_pose.update_model(context.scene, model, mesh)
    return model


def remove(context):
    cockpit = target(context)
    for obj in references(context.scene, cockpit):
        collections = list(obj.users_collection)
        root = obj.parent
        mesh = obj.data
        if context.active_object == obj:
            obj.select_set(False)
            cockpit.select_set(True)
            context.view_layer.objects.active = cockpit
        bpy.data.objects.remove(obj, do_unlink=True)
        if mesh.get('bbe_pilot_posed_mesh') and mesh.users == 0:
            bpy.data.meshes.remove(mesh)
        if root and root.get(ROOT_TAG) and not root.children:
            bpy.data.objects.remove(root, do_unlink=True)
        for collection in collections:
            if collection.get('bbe_pilot_collection') and not collection.objects and not collection.children:
                bpy.data.collections.remove(collection)


class BBE_OT_choose_pilot(bpy.types.Operator):
    bl_idname = 'bbe.choose_pilot_reference'
    bl_label = 'Choose Pilot Reference'
    bl_description = 'Add or replace this cockpit’s selectable, transform-locked reference'
    bl_options = {'REGISTER', 'UNDO'}
    race: bpy.props.EnumProperty(items=[(key, label, '') for key, label in RACES])

    def execute(self, context):
        try:
            model = choose(context, self.race)
            if model.get('bbe_pilot_asset_warning'):
                self.report({'WARNING'}, model['bbe_pilot_asset_warning'])
            if model.get('bbe_pilot_pose_warning'):
                self.report({'WARNING'}, model['bbe_pilot_pose_warning'])
        except (ValueError, OSError, RuntimeError) as exc:
            self.report({'ERROR'}, str(exc))
            return {'CANCELLED'}
        return {'FINISHED'}


class BBE_OT_pilot_action(bpy.types.Operator):
    bl_idname = 'bbe.pilot_reference_action'
    bl_label = 'Pilot Reference'
    bl_options = {'REGISTER', 'UNDO'}
    action: bpy.props.EnumProperty(items=[(k, k.title(), '') for k in ('VISIBILITY', 'REMOVE')])

    def execute(self, context):
        obj = preview(context)
        if obj is None:
            return {'CANCELLED'}
        if self.action == 'REMOVE':
            remove(context)
        elif self.action == 'VISIBILITY':
            obj.hide_set(not obj.hide_get())
        return {'FINISHED'}


_anchors = {}


class BBE_GGT_pilot_reference(bpy.types.GizmoGroup):
    bl_idname = 'BBE_GGT_pilot_reference'
    bl_label = 'Pilot reference'
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'WINDOW'
    bl_options = {'PERSISTENT'}

    @classmethod
    def poll(cls, context):
        from . import undo_guard
        if undo_guard.restoring or len(context.selected_objects) != 1:
            return False
        cockpit = target(context)
        return cockpit is not None

    def setup(self, context):
        self.card = self.gizmos.new('BBE_GT_tube_button')
        self.card.hide_select = True
        self.card.color, self.card.alpha = (.055, .07, .09), .96
        self.buttons = []
        for race, label in RACES:
            button = self.gizmos.new('BBE_GT_tube_button')
            button.text = label
            operator = button.target_set_operator('bbe.choose_pilot_reference')
            operator.race = race
            self.buttons.append((button, operator))
        for action, label in (('VISIBILITY', 'Hide'), ('REMOVE', 'Remove')):
            button = self.gizmos.new('BBE_GT_tube_button')
            button.text = label
            operator = button.target_set_operator('bbe.pilot_reference_action')
            operator.action = action
            self.buttons.append((button, operator))
        for button, operator in self.buttons:
            button.color, button.alpha = (.18, .23, .29), 1
            button.color_highlight, button.alpha_highlight = (.22, .43, .61), 1
            button.use_tooltip = True
        self.card.buttons = tuple(b for b, _ in self.buttons)

    def draw_prepare(self, context):
        from .bubble_controls import fixed_panel_position, projected_bounds
        scale = context.preferences.system.ui_scale
        choice_rows = (len(RACES) + 1) // 2
        width, height = 310*scale, (106 + 29*choice_rows)*scale
        right = context.region.width-60*scale
        for region in context.area.regions:
            if region.type == 'UI' and region.width > 1:
                right -= region.width
        key = (context.window.as_pointer(), context.area.as_pointer(), context.region.as_pointer())
        bounds = projected_bounds(context, context.active_object) or (0, 0, 0, 0)
        if key not in _anchors and len(_anchors) > 64:
            _anchors.clear()
        (x, y), _anchors[key] = fixed_panel_position(_anchors.get(key), bounds, [bounds],
            (60*scale, 40*scale, right, context.region.height-100*scale), (width, height), height)
        obj = preview(context)
        self.card.matrix_basis = Matrix.Translation((x, y, 0))
        self.card.width, self.card.height, self.card.font_size = width, height, 11*scale
        self.card.lines = ((10*scale, height-19*scale, 'First cockpit · Pilot reference', (.94, .95, .97, 1)),
                           (10*scale, 30*scale, obj.get('bbe_pilot_position_status', '') if obj else
                            'Follows cockpit position, rotation and scale', (.72, .79, .85, 1)),
                           (10*scale, 12*scale, 'Reference only · excluded from game export', (.72, .79, .85, 1)))
        for i, (button, operator) in enumerate(self.buttons):
            row, col = divmod(i, 2)
            if i >= len(RACES):
                row, col = choice_rows + (i-len(RACES)) // 2, (i-len(RACES)) % 2
            button.matrix_basis = Matrix.Translation((x+(10+150*col)*scale, y+height-(53+29*row)*scale, 0))
            button.width, button.height, button.font_size = 140*scale, 24*scale, 11*scale
            button.hide = i >= len(RACES) and obj is None
            if i < len(RACES):
                button.color = (.17, .36, .5) if obj and obj.get(RACE) == RACES[i][0] else (.18, .23, .29)
        self.buttons[len(RACES)][0].text = 'Show' if obj and obj.hide_get() else 'Hide'


_classes = (BBE_OT_choose_pilot, BBE_OT_pilot_action, BBE_GGT_pilot_reference)


def register():
    from . import pilot_pose
    pilot_pose.register()
    for cls in _classes:
        bpy.utils.register_class(cls)
    if refresh_saved_pilot_poses not in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.append(refresh_saved_pilot_poses)


def unregister():
    from . import pilot_pose
    pilot_pose.unregister()
    if refresh_saved_pilot_poses in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.remove(refresh_saved_pilot_poses)
    for cls in reversed(_classes):
        bpy.utils.unregister_class(cls)
    _anchors.clear()
