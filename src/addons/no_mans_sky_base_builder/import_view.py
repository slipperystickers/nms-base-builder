"""Finish a build import in the user's modeling viewport."""
from itertools import product

from mathutils import Vector


def _bounds(objects, depsgraph):
    low = [float('inf')] * 3
    high = [float('-inf')] * 3
    for obj in objects:
        evaluated = obj.evaluated_get(depsgraph)
        world = evaluated.matrix_world
        box = evaluated.bound_box
        if box is None or all(tuple(corner) == (-1., -1., -1.) for corner in box):
            points = (world.translation,)
        else:
            points = (world @ Vector(corner) for corner in box)
        for point in points:
            for i, value in enumerate(point):
                low[i] = min(low[i], value)
                high[i] = max(high[i], value)
    if low[0] <= high[0]:
        return Vector(low), Vector(high)


def _viewport(context):
    # An import may finish in a file selector, Properties, or a detached
    # window. Prefer the invoking viewport, then a large view of this scene.
    candidates = []
    for window in context.window_manager.windows:
        if window.scene != context.scene:
            continue
        for area in window.screen.areas:
            if area.type == 'VIEW_3D':
                candidates.append((area == context.area, window == context.window,
                                   area.width * area.height, area))
    if candidates:
        return max(candidates, key=lambda item: item[:3])[-1]


def finish(context, objects):
    layer = context.view_layer
    layer.objects.active = None
    for obj in layer.objects:
        if obj.select_get(view_layer=layer):
            obj.select_set(False, view_layer=layer)

    area = _viewport(context)
    if area is None:
        return
    bounds = _bounds(objects, context.evaluated_depsgraph_get())
    if bounds is None:
        return
    low, high = bounds
    center = (low + high) * .5
    corners = [Vector(xyz) - center for xyz in product(*zip(low, high))]
    space = area.spaces.active
    for region in area.regions:
        if region.type != 'WINDOW' or not region.width or not region.height:
            continue
        view = region.data
        if view is None:
            continue
        if view.view_perspective == 'CAMERA':
            view.view_perspective = 'PERSP'
        rotation = view.view_rotation
        inverse = rotation.inverted()
        # Fit the projected corners, including their depth in perspective.
        # Blender's free viewport uses a 72 mm aperture on the longer side.
        focal = space.lens / 36 * max(region.width, region.height)
        fx, fy = focal / region.width, focal / region.height
        distance = 1.
        for corner in corners:
            x, y, z = inverse @ corner
            extent = 1.15 * max(abs(x) * fx, abs(y) * fy)
            if view.view_perspective == 'PERSP':
                extent = max(extent, 2 * space.clip_start) + z
            distance = max(distance, extent)
        far = distance + (high - center).length
        if far >= space.clip_end * .9:
            space.clip_end = far * 1.2
        view.view_location = center
        view.view_distance = distance
    area.tag_redraw()
