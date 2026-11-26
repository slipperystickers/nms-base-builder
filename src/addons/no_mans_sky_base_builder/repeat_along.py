"""Repeat a selection using its exposed, orientation-preserving structural sockets."""

from collections import defaultdict
from dataclasses import dataclass
from functools import lru_cache
from math import atan2, cos, floor, pi, sin

import bpy
from . import curve_links
from . import i18n
import gpu
from bpy.app.handlers import persistent
from bpy_extras import view3d_utils as view
from gpu_extras.batch import batch_for_shader
from mathutils import Matrix, Vector, kdtree

from . import base_snapping, curve_widgets as paint, repeat_ports
from .utils import materials_v2, mirror_pivot

_sessions = {}
MAX_NEW_PARTS = 4096


@lru_cache(maxsize=256)
def scene_steps(scene):
    filename = scene.rsplit("/", 1)[-1]
    if "/basicparts/" not in scene or not any(word in filename for word in ("wall", "floor", "roof")):
        return ()
    sockets = {s[1]: s for s in base_snapping._scene_sockets(scene)}
    found = {}
    for _, pair, point, relative in base_snapping._scene_options(scene, scene):
        a, b = (sockets[key] for key in pair.split(">"))
        if a[2].startswith("WallStack"):
            # Stacking frames point in opposite directions across a horizontal
            # seam. Mate their positions while keeping the wall upright.
            delta = point - a[4].translation
        else:
            if any(abs(relative[i][j] - int(i == j)) > 0.0002 for i in range(3) for j in range(3)):
                continue
            delta = relative.translation
        if delta.length < 0.001:
            continue
        key = tuple(round(v, 4) for vec in (point, delta) for v in vec)
        found.setdefault(key, (point.copy(), delta.copy(), a[2]))
    return tuple(found.values())


def eligible(obj):
    if (
        not obj
        or obj.type != "MESH"
        or "ObjectID" not in obj
        or obj.library
        or "bbe_shape_slot" in obj
        or curve_links.parent_name(obj)
    ):
        return False
    if obj["ObjectID"] in repeat_ports.SUPPORTED:
        return repeat_ports.eligible(obj)
    rec = base_snapping.catalog()["parts"].get(obj.get("ObjectID"))
    return bool(rec and scene_steps(rec["scene"]))


def targets(objects, blocked_decks=()):
    """One translation per exposed socket, measured across the entire selection."""
    directions = defaultdict(list)
    for obj in objects:
        pid = obj["ObjectID"]
        native = mirror_pivot.native_matrix(
            obj.matrix_world, pid, normalized=mirror_pivot.is_normalized(obj)
        )
        steps = (
            repeat_ports.steps(pid, repeat_ports.intent(obj))
            if pid in repeat_ports.SUPPORTED
            else scene_steps(base_snapping.catalog()["parts"][pid]["scene"])
        )
        for point, delta, kind in steps:
            step = native.to_3x3() @ delta
            if step.length < 1e-6:
                continue
            direction = tuple(round(v, 4) for v in step.normalized())
            blocked = bool(blocked_decks) and (obj, tuple(point)) in blocked_decks
            directions[direction].append((obj, native @ point, step, kind, blocked))
    result = []
    for entries in directions.values():
        if len({e[0] for e in entries}) != len(objects):
            continue
        axis = entries[0][2].normalized()
        origin = entries[0][1]
        front = max((p - origin).dot(axis) for _, p, _, _, _ in entries)
        back = min((p - step - origin).dot(axis) for _, p, step, _, _ in entries)
        stride = axis * (front - back)
        tolerance = max(0.0001, min(e[2].length for e in entries) * 0.00015)
        # All selected habs move together. One occupied bay on the leading
        # deck blocks that translation, including the other bay of a long hab.
        if any(blocked and abs((point - origin).dot(axis) - front) < tolerance
               for _, point, _, _, blocked in entries):
            continue
        by_kind = defaultdict(list)
        for _, p, step, kind, _ in entries:
            entry = p - step
            if abs((entry - origin).dot(axis) - back) < tolerance:
                by_kind[kind].append(entry)
        trees = {}
        for kind, points in by_kind.items():
            tree = kdtree.KDTree(len(points))
            for i, p in enumerate(points):
                tree.insert(p, i)
            tree.balance()
            trees[kind] = tree
        for _, p, step, kind, _ in entries:
            if kind in trees and abs((p - origin).dot(axis) - front) < tolerance:
                if trees[kind].find(p - stride)[2] < tolerance:
                    result.append((p, stride))
    return result


@lru_cache(maxsize=256)
def wall_corners(scene):
    """Match the incoming end to an authored upright quarter-turn socket."""
    options = base_snapping._scene_options(scene, scene)
    result = []
    up = Vector((0, 1, 0))  # Native NMS coordinates.
    for point, pitch, kind in scene_steps(scene):
        if not kind.startswith("Wall") or kind.startswith("WallStack"):
            continue
        entry = point - pitch
        signs = set()
        for _, _, target, relative in options:
            if (target - point).length > 0.001 or (relative @ entry - point).length > 0.001:
                continue
            facing = relative.to_3x3()
            outgoing = facing @ pitch
            if (facing @ up - up).length > 0.001 or abs(
                pitch.normalized().dot(outgoing.normalized())
            ) > 0.001:
                continue
            signs.add(1 if pitch.cross(outgoing).dot(up) > 0 else -1)
        if signs:
            result.append((point, pitch, tuple(sorted(signs))))
    return tuple(result)


@dataclass(eq=False)
class RepeatDirection:
    step: Vector
    objects: tuple
    pivot_transform: Matrix | None = None
    route: repeat_ports.Route | None = None

    def total(self, count):
        return count * len(self.objects) + int(bool(count and self.route and self.route.corner))

    @property
    def limit(self):
        return (MAX_NEW_PARTS - int(bool(self.route and self.route.corner))) // len(self.objects)


def socket_handles(objects, active):
    """Merge coincident seam markers; keep the active wall as the branch template."""
    routed = [obj for obj in objects if obj["ObjectID"] in repeat_ports.SUPPORTED]
    entries = repeat_ports.connections(routed, bpy.context.scene.objects) if routed else ()
    blocked_decks = {(obj, tuple(point)) for obj, point, axis, _, used in entries
                     if used and obj['ObjectID'] in repeat_ports.HABS and abs(axis.y) > .999}
    candidates = [(p, RepeatDirection(step, objects)) for p, step in targets(objects, blocked_decks)]
    if entries:
        occupied = kdtree.KDTree(len(entries))
        free = defaultdict(list)
        for i, (obj, p, n, world, used) in enumerate(entries):
            if used:
                occupied.insert(world, i)
            else:
                free[obj].append((p, n))
        occupied.balance()
        candidates = [(p, d) for p, d in candidates if not occupied.find_range(p, 0.0002)]
        for obj, p, n, world, used in sorted(entries, key=lambda entry: entry[0] != active):
            native = base_snapping._native_target(obj)
            for route in repeat_ports.routes(obj, p, n, used, free[obj]):
                step = native.to_3x3() @ route.pitch
                if step.length < 0.00001:
                    continue
                plan = repeat_ports.Route(
                    repeat_ports.world_piece(native, route.run),
                    step,
                    repeat_ports.world_piece(native, route.corner),
                )
                candidates.append((world, RepeatDirection(step, (obj,), route=plan)))
    for obj in sorted(objects, key=lambda obj: obj != active):
        pid = obj["ObjectID"]
        if pid in repeat_ports.SUPPORTED:
            continue
        scene = base_snapping.catalog()["parts"][pid]["scene"]
        corners = wall_corners(scene)
        if not corners:
            continue
        native = base_snapping._native_target(obj)
        frame = native.to_3x3()
        for point, pitch, signs in corners:
            pivot = native @ point
            forward = frame @ pitch
            # Use the plane normal, including when the wall has a scaled parent.
            normal = (frame @ Vector((0, 0, 1))).cross(frame @ Vector((1, 0, 0)))
            if normal.length_squared < 1e-12 or forward.length_squared < 1e-12:
                continue
            for sign in signs:
                rotation = Matrix.Rotation(sign * pi / 2, 4, normal)
                turn = Matrix.Translation(pivot) @ rotation @ Matrix.Translation(-pivot)
                candidates.append((pivot, RepeatDirection(rotation.to_3x3() @ forward, (obj,), turn)))
    tree = kdtree.KDTree(len(candidates))
    for i, (p, _) in enumerate(candidates):
        tree.insert(p, i)
    if candidates:
        tree.balance()
    handles = []
    grouped = set()
    for i, (p, _) in enumerate(candidates):
        if i in grouped:
            continue
        members = sorted(index for _, index, _ in tree.find_range(p, 0.0002) if index not in grouped)
        grouped.update(members)
        directions = []
        for index in members:
            candidate = candidates[index][1]
            if not any(
                candidate.step.normalized().dot(other.step.normalized()) > 0.9999
                for other in directions
            ):
                directions.append(candidate)
        handles.append((p, directions))
    return handles


def place(context, objects, step, count, pivot_transform=None):
    """Create independent game parts only on release; roll back a partial allocation."""
    if count < 1 or count * len(objects) > MAX_NEW_PARTS:
        raise ValueError("Repeat count is out of range.")
    order = 1 + max(
        (int(o.get("order", 0)) for o in context.scene.objects if "ObjectID" in o), default=-1
    )
    created = []
    meshes = []
    active = context.active_object
    try:
        for n in range(1, count + 1):
            transform = Matrix.Translation(step * n)
            if pivot_transform is not None:
                transform = transform @ pivot_transform
            copies = {}
            for src in objects:
                obj = src.copy()
                created.append(obj)
                if not materials_v2.is_high_res(src):
                    mesh = src.data.copy()
                    meshes.append(mesh)
                    obj.data = mesh
                for col in src.users_collection:
                    col.objects.link(obj)
                obj["order"] = order
                order += 1
                for prop in (
                    "snapped_to",
                    "bbe_native_snap_target",
                    "bbe_native_target_socket",
                    "bbe_native_source_socket",
                    "bbe_native_source_option",
                ):
                    if prop in obj:
                        del obj[prop]
                copies[src] = obj
            for src, obj in copies.items():
                if src.parent in copies:
                    obj.parent = copies[src.parent]
                    # Both ends moved by the same world translation.
                    obj.matrix_basis = src.matrix_basis
                else:
                    obj.matrix_world = transform @ src.matrix_world
        for obj in created:
            obj.select_set(True)
        context.view_layer.objects.active = active
        if any(src.get("ObjectID") == repeat_ports.BUBBLE for src in objects):
            from . import bubble_preview

            bubble_preview.request_refresh(context.scene)
    except Exception:
        if created:
            bpy.data.batch_remove(created)
        for mesh in meshes:
            if mesh.users == 0:
                bpy.data.meshes.remove(mesh)
        raise
    return created


def place_route(context, source, route, count):
    from . import builder_v2

    created = []
    prior = tuple(context.selected_objects)
    active = context.active_object

    def add(piece):
        obj = builder_v2.add_part(
            piece.pid,
            user_data=source.get("UserData", 0),
            build_rigs=False,
            high_res=materials_v2.is_high_res(source),
        ).object
        created.append(obj)
        for coll in source.users_collection:
            if coll not in obj.users_collection:
                coll.objects.link(obj)
        for coll in tuple(obj.users_collection):
            if coll not in source.users_collection:
                coll.objects.unlink(obj)
        obj.parent = source.parent
        obj.matrix_world = (
            mirror_pivot.display_matrix(piece.matrix, piece.pid)
            if mirror_pivot.is_normalized(obj)
            else piece.matrix
        )
        obj["order"] = 1 + max(
            (
                int(other.get("order", 0))
                for other in context.scene.objects
                if other != obj and "ObjectID" in other
            ),
            default=-1,
        )
        return obj

    try:
        if route.corner:
            add(route.corner)
        run = route.run
        if run.pid == source["ObjectID"]:
            desired = (
                mirror_pivot.display_matrix(run.matrix, run.pid)
                if mirror_pivot.is_normalized(source)
                else run.matrix
            )
            transform = Matrix.Translation(-route.pitch) @ desired @ source.matrix_world.inverted()
            spans = place(context, (source,), route.pitch, count, transform)
            created.extend(spans)
        else:
            head = add(run)
            context.view_layer.update()
            spans = [head]
            if count > 1:
                copies = place(context, (head,), route.pitch, count - 1)
                created.extend(copies)
                spans.extend(copies)
        for obj in context.selected_objects:
            obj.select_set(False)
        for obj in spans:
            obj.select_set(True)
        context.view_layer.objects.active = spans[-1]
        return created
    except Exception:
        if created:
            bpy.data.batch_remove(created)
        for obj in prior:
            obj.select_set(True)
        context.view_layer.objects.active = active
        raise


@lru_cache(maxsize=1)
def target_shader():
    interface = gpu.types.GPUStageInterfaceInfo("bbe_repeat_target")
    interface.smooth("VEC2", "uv")
    interface.flat("FLOAT", "target")
    info = gpu.types.GPUShaderCreateInfo()
    info.vertex_in(0, "VEC3", "position")
    info.vertex_in(1, "VEC2", "corner")
    info.vertex_in(2, "FLOAT", "index")
    info.push_constant("MAT4", "projection")
    info.push_constant("VEC2", "radius")
    info.push_constant("FLOAT", "hovered")
    info.vertex_out(interface)
    info.fragment_out(0, "VEC4", "color")
    info.vertex_source("""
        void main() {
            vec4 clip = projection * vec4(position, 1.0);
            clip.xy += corner * radius * clip.w;
            gl_Position = clip;
            uv = corner;
            target = index;
        }
    """)
    info.fragment_source("""
        void main() {
            float d = length(uv);
            float aa = max(fwidth(d), 0.01);
            float alpha = 1.0 - smoothstep(0.92-aa, 0.92+aa, d);
            if (alpha <= 0.0) discard;
            vec2 a = abs(uv);
            float crosshair = (1.0-smoothstep(0.06,0.14,min(a.x,a.y))) *
                              (1.0-smoothstep(0.34,0.44,max(a.x,a.y)));
            float rim = smoothstep(0.65-aa, 0.65+aa, d);
            vec3 fill = target == hovered ? vec3(0.12,0.40,0.21) : vec3(0.025,0.10,0.055);
            color = vec4(mix(fill, vec3(0.32,1.0,0.56), max(rim,crosshair)), alpha);
        }
    """)
    return gpu.shader.create_from_info(info)


class TargetMarkers:
    """Static world-space target quads. Navigation only changes the projection uniform."""

    def __init__(self, choices):
        self.shader = target_shader()
        corners = ((-1, -1), (1, -1), (1, 1), (-1, 1))
        self.batch = batch_for_shader(
            self.shader,
            "TRIS",
            {
                "position": [position for position, _ in choices for _ in corners],
                "corner": corners * len(choices),
                "index": [float(i) for i in range(len(choices)) for _ in corners],
            },
            indices=[
                (4 * i + a, 4 * i + b, 4 * i + c)
                for i in range(len(choices))
                for a, b, c in ((0, 1, 2), (0, 2, 3))
            ],
        )

    def draw(self, context, hover, scale):
        self.shader.bind()
        self.shader.uniform_float("projection", context.region_data.perspective_matrix)
        self.shader.uniform_float(
            "radius", (22 * scale / context.region.width, 22 * scale / context.region.height)
        )
        self.shader.uniform_float("hovered", -1.0 if hover is None else float(hover))
        self.batch.draw(self.shader)


@lru_cache(maxsize=1)
def ghost_shader():
    info = gpu.types.GPUShaderCreateInfo()
    info.vertex_in(0, "VEC3", "pos")
    info.push_constant("MAT4", "localToClip")
    info.push_constant("VEC4", "clipStep")
    info.fragment_out(0, "VEC4", "color")
    info.vertex_source(
        "void main(){gl_Position=localToClip*vec4(pos,1)+float(gl_InstanceID+1)*clipStep;}"
    )
    info.fragment_source("void main(){color=vec4(0.23,0.92,0.53,0.22);}")
    return gpu.shader.create_from_info(info)


def route_mesh(source, piece):
    from . import builder_v2

    if source["ObjectID"] == piece.pid:
        pose = (
            mirror_pivot.display_matrix(piece.matrix, piece.pid)
            if mirror_pivot.is_normalized(source)
            else piece.matrix
        )
        return pose, source.data
    mesh = builder_v2.load_high_res_mesh(piece.pid) if materials_v2.is_high_res(source) else None
    if mesh is None:
        mesh = builder_v2.load_proxy_mesh(piece.pid)
    if mesh is None:
        raise ValueError(f"Could not load the {piece.pid} route preview.")
    return mirror_pivot.display_matrix(piece.matrix, piece.pid), mesh


class Ghosts:
    """One GPU mesh per proxy, instanced along the snapped world translation."""

    def __init__(self, objects, route=None):
        import numpy as np

        self.shader = ghost_shader()
        batches = {}
        self.parts = []
        meshes = (
            [(route_mesh(objects[0], route.run), False)]
            if route
            else [((obj.matrix_world.copy(), obj.data), False) for obj in objects]
        )
        if route and route.corner:
            meshes.append((route_mesh(objects[0], route.corner), True))
        for (matrix, mesh), fixed in meshes:
            if mesh not in batches:
                mesh.calc_loop_triangles()
                vertices = np.empty(len(mesh.vertices) * 3, dtype="f")
                triangles = np.empty(len(mesh.loop_triangles) * 3, dtype="i")
                mesh.vertices.foreach_get("co", vertices)
                mesh.loop_triangles.foreach_get("vertices", triangles)
                batches[mesh] = batch_for_shader(
                    self.shader,
                    "TRIS",
                    {"pos": vertices.reshape(-1, 3)},
                    indices=triangles.reshape(-1, 3),
                )
            self.parts.append((matrix, batches[mesh], fixed))
        self.prepositioned = route is not None

    def draw(self, projection, step, count, pivot_transform=None):
        if count < 1:
            return
        blend, depth, mask = (
            gpu.state.blend_get(),
            gpu.state.depth_test_get(),
            gpu.state.depth_mask_get(),
        )
        try:
            gpu.state.blend_set("ALPHA")
            gpu.state.depth_test_set("LESS_EQUAL")
            gpu.state.depth_mask_set(False)
            self.shader.bind()
            clip_step = projection @ Vector((*step, 0.0))
            if pivot_transform is not None:
                projection = projection @ pivot_transform
            for matrix, batch, fixed in self.parts:
                self.shader.uniform_float("clipStep", (0.0, 0.0, 0.0, 0.0) if fixed else clip_step)
                if self.prepositioned and not fixed:
                    matrix = Matrix.Translation(-step) @ matrix
                self.shader.uniform_float("localToClip", projection @ matrix)
                batch.draw_instanced(self.shader, instance_count=1 if fixed else count)
        finally:
            gpu.state.depth_mask_set(mask)
            gpu.state.depth_test_set(depth)
            gpu.state.blend_set(blend)


class BBE_OT_repeat_along(bpy.types.Operator):
    bl_idname = "bbe.repeat_along"
    bl_label = "Repeat Along"
    bl_description = "Pick an opening or snap target, then drag its arrow to repeat the selected parts"
    bl_options = {"UNDO", "BLOCKING"}

    @classmethod
    def poll(cls, context):
        return (
            context.area
            and context.area.type == "VIEW_3D"
            and context.mode == "OBJECT"
            and context.active_object
            and context.active_object.select_get()
            and eligible(context.active_object)
        )

    def invoke(self, context, event):
        objects = tuple(context.selected_objects)
        if not objects or not all(eligible(o) for o in objects):
            self.report(
                {"INFO"}, "Select repeatable structural parts, habs, passages or straight pipes."
            )
            return {"CANCELLED"}
        self.handles_by_socket = socket_handles(objects, context.active_object)
        from .viewport_cutaway import limits, contains
        cuts = limits(context.scene)
        if cuts:
            self.handles_by_socket = [(p, ds) for p, ds in self.handles_by_socket if contains(cuts,p)]
        self.choices = [(point, directions[0].step) for point, directions in self.handles_by_socket]
        if not self.choices:
            self.report(
                {"INFO"}, "This selection has no matching exposed sockets in a common direction."
            )
            return {"CANCELLED"}
        if len(objects) > MAX_NEW_PARTS:
            self.report({"INFO"}, "Select fewer parts for this repeat.")
            return {"CANCELLED"}
        self.area = context.area
        self.region = context.region
        self.scene = context.scene
        self.key = self.area.as_pointer()
        if self.key in _sessions:
            return {"CANCELLED"}
        self.objects = objects
        self.phase = "PICK"
        self.choice = None
        self.count = 0
        self.ghosts = None
        self.mouse = Vector((event.mouse_region_x, event.mouse_region_y))
        self.graphics = gpu.shader.from_builtin("UNIFORM_COLOR")
        self.markers = TargetMarkers(self.choices)
        self.projection_key = None
        self.hover = None
        self.handles = []
        _sessions[self.key] = self
        try:
            for draw, stage in ((self.draw_preview, "POST_VIEW"), (self.draw_ui, "POST_PIXEL")):
                self.handles.append(bpy.types.SpaceView3D.draw_handler_add(draw, (), "WINDOW", stage))
            context.window_manager.modal_handler_add(self)
            self.area.tag_redraw()
        except Exception:
            self.close()
            raise
        return {"RUNNING_MODAL"}

    def close(self):
        from . import wasd_navigation

        if getattr(wasd_navigation._active, "_owner", None) == self:
            wasd_navigation.stop()
        for h in self.handles:
            bpy.types.SpaceView3D.draw_handler_remove(h, "WINDOW")
        self.handles.clear()
        self.ghosts = None
        self.markers = None
        if _sessions.get(self.key) == self:
            del _sessions[self.key]
        try:
            self.area.tag_redraw()
        except ReferenceError:
            pass

    def cancel(self, context):
        self.close()

    def draw_preview(self):
        ctx = bpy.context
        if ctx.region == self.region and self.phase == "DRAG" and self.count:
            self.ghosts.draw(
                ctx.region_data.perspective_matrix,
                self.direction.step,
                self.count,
                self.direction.pivot_transform,
            )

    def project(self, point):
        return view.location_3d_to_region_2d(self.region, self.area.spaces.active.region_3d, point)

    def nearest(self):
        region = self.region
        projection = self.area.spaces.active.region_3d.perspective_matrix
        key = (region.width, region.height, *map(tuple, projection))
        if key != self.projection_key:
            points = [(i, self.project(point)) for i, (point, _) in enumerate(self.choices)]
            self.screen_points = [(i, p.x, p.y) for i, p in points if p is not None]
            self.projection_key = key
        x, y = self.mouse
        limit = (15 * self.scale) ** 2
        nearest = None
        for i, px, py in self.screen_points:
            distance = (x - px) ** 2 + (y - py) ** 2
            if distance < limit:
                nearest, limit = i, distance
        return nearest

    @property
    def scale(self):
        return bpy.context.preferences.system.ui_scale

    def arrows(self):
        """Separate handles that project onto the same screen ray in a side view."""
        point = self.choice[0]
        offset = self.handle_offset if self.phase == "DRAG" else 0
        base = self.project(point)
        if base is None:
            return []
        result = []
        angles = []
        for option in self.directions:
            other = self.project(point + option.step * 0.05)
            projected = other - base if other is not None else Vector((0, 0))
            if projected.length < 0.08:
                eye_axis = self.area.spaces.active.region_3d.view_rotation @ Vector((0, 0, 1))
                projected = Vector((0, 1 if option.step.dot(eye_axis) >= 0 else -1))
            angle = atan2(projected.y, projected.x)
            for shift in (0, pi / 6, -pi / 6, pi / 3, -pi / 3, pi / 2, -pi / 2):
                candidate = angle + shift
                if all(cos(candidate - used) < 0.92 for used in angles):
                    break
            angles.append(candidate)
            if self.phase == "DRAG" and option is not self.direction:
                continue
            start = self.project(point + option.step * offset) if offset else base
            if start is not None:
                u = Vector((cos(candidate), sin(candidate)))
                result.append((option, start, start + u * 52 * self.scale, u))
        return result

    def arrow(self):
        return next(((a, b, u) for opt, a, b, u in self.arrows() if opt is self.direction), None)

    def draw_ui(self):
        context = bpy.context
        if context.region != self.region:
            return
        s = self.scale
        shader = self.graphics
        ink = (0.32, 1.0, 0.56, 1)
        dark = (0.025, 0.10, 0.055, 0.95)
        with paint.canvas(context):
            if self.phase == "PICK":
                self.markers.draw(context, self.hover, s)
                label = i18n.interface("Repeat Along   ·   Pick a snap target")
            else:
                for option, a, b, u in self.arrows():
                    v = Vector((-u.y, u.x))
                    color = (
                        (0.36, 0.82, 1.0, 1)
                        if option.pivot_transform is not None or (option.route and option.route.corner)
                        else ink
                    )
                    paint.disc(shader, *a, 5 * s, ink)
                    paint.line(shader, a, b - u * 9 * s, 5 * s, color)
                    paint.polygon(
                        shader, [b, b - u * 15 * s + v * 8 * s, b - u * 15 * s - v * 8 * s], color
                    )
                label = (
                    (
                        i18n.interface("Drag an arrow to choose the direction")
                        if len(self.directions) > 1
                        else i18n.interface("Drag the arrow to repeat")
                    )
                    if self.phase == "ARM"
                    else i18n.interface("{count} repeats · {parts} new parts · Release to place").format(
                        count=self.count, parts=self.direction.total(self.count))
                )
            if self.phase == "DRAG" and self.count == self.direction.limit:
                label += "   ·   " + i18n.interface("Drag limit reached")
            import blf

            label += "   ·   " + i18n.interface("Esc to cancel")
            blf.size(0, 12 * s)
            width = blf.dimensions(0, label)[0] + 24 * s
            x = (self.region.width - width) / 2
            paint.rounded(shader, x, 22 * s, width, 28 * s, 8 * s, dark)
            paint.text(label, x + 12 * s, 31 * s, 12 * s, ink)

    def along(self):
        point, step = self.choice
        rv = self.area.spaces.active.region_3d
        ray = view.region_2d_to_vector_3d(self.region, rv, self.mouse)
        axis = step.normalized()
        dot = ray.dot(axis)
        if 1 - dot * dot < 0.0025:
            return None
        origin = view.region_2d_to_origin_3d(
            self.region, rv, self.mouse, clamp=max(100.0, rv.view_distance * 3)
        )
        delta = origin - point
        return (axis.dot(delta) - dot * ray.dot(delta)) / ((1 - dot * dot) * step.length)

    def modal(self, context, event):
        if _sessions.get(self.key) != self:
            return {"CANCELLED"}
        if (
            context.scene != self.scene
            or context.area != self.area
            or context.mode != "OBJECT"
            or event.type in {"ESC", "WINDOW_DEACTIVATE"}
        ):
            self.close()
            return {"CANCELLED"}
        if event.type == "RIGHTMOUSE" and event.value == "PRESS":
            from . import wasd_navigation

            prefs = wasd_navigation.preferences(context)
            if not prefs or not prefs.bbe_wasd_enabled:
                self.close()
                return {"CANCELLED"}
            if bpy.ops.bbe.wasd_navigation.poll():
                result = bpy.ops.bbe.wasd_navigation("INVOKE_DEFAULT", from_repeat=True)
                if "RUNNING_MODAL" in result:
                    self.hover = None
                    if self.phase == "DRAG":
                        self.phase = "ARM"
                        self.count = 0
                    self.area.tag_redraw()
            return {"RUNNING_MODAL"}
        if event.type.startswith("NDOF") or event.type in {
            "MIDDLEMOUSE",
            "WHEELUPMOUSE",
            "WHEELDOWNMOUSE",
            "TRACKPADPAN",
            "TRACKPADZOOM",
        }:
            return {"PASS_THROUGH"} if self.phase != "DRAG" else {"RUNNING_MODAL"}
        if event.type not in {"MOUSEMOVE", "LEFTMOUSE"}:
            return {"RUNNING_MODAL"}
        self.mouse = Vector((event.mouse_region_x, event.mouse_region_y))
        if self.phase == "PICK" and event.type == "MOUSEMOVE":
            nearest = self.nearest()
            if nearest != self.hover:
                self.hover = nearest
                self.area.tag_redraw()
        if event.type == "LEFTMOUSE" and event.value == "PRESS":
            if self.phase == "PICK":
                i = self.nearest()
                if i is not None:
                    point, self.directions = self.handles_by_socket[i]
                    self.direction = self.directions[0]
                    self.choice = point, self.direction.step
                    self.phase = "ARM"
                    self.area.tag_redraw()
            elif self.phase == "ARM":
                hits = []
                for option, a, b, u in self.arrows():
                    along = (self.mouse - a).dot(u)
                    if len(self.directions) > 1 and along < 8 * self.scale:
                        continue
                    nearest = a + u * max(0, min((b - a).length, along))
                    distance = (nearest - self.mouse).length
                    if distance <= 12 * self.scale:
                        hits.append((distance, option, u))
                if hits:
                    _, self.direction, u = min(hits, key=lambda hit: hit[0])
                    self.choice = self.choice[0], self.direction.step
                    try:
                        if self.ghosts is None or self.ghost_direction is not self.direction:
                            self.ghost_direction = self.direction
                            self.ghosts = Ghosts(self.direction.objects, self.direction.route)
                    except (RuntimeError, ValueError) as error:
                        self.close()
                        self.report({"ERROR"}, str(error))
                        return {"CANCELLED"}
                    self.start = self.along()
                    self.press = self.mouse.copy()
                    self.screen_axis = u
                    self.handle_offset = 0.0
                    self.last_draw_mouse = self.mouse.copy()
                    self.phase = "DRAG"
                    self.area.tag_redraw()
        if self.phase == "DRAG":
            current = self.along()
            amount = (
                current - self.start
                if self.start is not None and current is not None
                else (self.mouse - self.press).dot(self.screen_axis) / (48 * self.scale)
            )
            self.handle_offset = max(0.0, min(self.direction.limit, amount))
            count = floor(self.handle_offset + 0.5)
            if count != self.count or (self.mouse - self.last_draw_mouse).length_squared >= 1.0:
                self.count = count
                self.last_draw_mouse = self.mouse.copy()
                self.area.tag_redraw()
            if event.type == "LEFTMOUSE" and event.value == "RELEASE":
                self.close()
                if self.count == 0:
                    return {"CANCELLED"}
                try:
                    if self.direction.route:
                        created = place_route(
                            context, self.direction.objects[0], self.direction.route, self.count
                        )
                    else:
                        created = place(
                            context,
                            self.direction.objects,
                            self.direction.step,
                            self.count,
                            self.direction.pivot_transform,
                        )
                    if self.direction.pivot_transform is not None:
                        for source in self.objects:
                            source.select_set(False)
                        context.view_layer.objects.active = created[-1]
                except (ValueError, RuntimeError, ReferenceError) as error:
                    self.report({"ERROR"}, str(error))
                    return {"CANCELLED"}
                self.report({"INFO"}, f"Placed {len(created)} parts")
                return {"FINISHED"}
        return {"RUNNING_MODAL"}


@persistent
def stop(*_):
    for session in tuple(_sessions.values()):
        session.close()
    target_shader.cache_clear()
    ghost_shader.cache_clear()
