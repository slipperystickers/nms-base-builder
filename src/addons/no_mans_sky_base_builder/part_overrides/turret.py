import math
from copy import copy

import bmesh
import bpy
import mathutils
from mathutils import Vector

from .. import part
from ..utils import blend_utils


class TURRET(part.Part):
    """Capture extra "Message" attribute."""

    # The handler works with an existing textured mesh as well as a proxy.
    HIGH_RES_COMPATIBLE = True

    def __init__(self, *args, **kwargs):
        super(TURRET, self).__init__(*args, **kwargs)
        # Trying something here, not quite reliable...
        # TURRET.orient_to_nearest_face(self.object)

    @staticmethod
    def orient_to_nearest_face(source_obj, target_objs=None):
        """
        Orient source_obj to the nearest face of target objects.
        If target_objs is None, it will search all mesh objects in the scene except source_obj.
        """

        # Collect candidate target objects
        if target_objs is None:
            target_objs = [
                obj
                for obj in bpy.context.scene.objects
                if obj.type == "MESH" and obj != source_obj
            ]

        if not target_objs:
            print("No target objects found.")
            return

        # BVH trees for each target object
        bvh_trees = {}
        for obj in target_objs:
            mesh = obj.data
            bm = bmesh.new()
            bm.from_mesh(mesh)
            bm.verts.ensure_lookup_table()
            bm.faces.ensure_lookup_table()
            bm.transform(obj.matrix_world)  # transform to world coords
            bvh_trees[obj] = (mathutils.bvhtree.BVHTree.FromBMesh(bm), bm)

        source_loc = source_obj.matrix_world.translation

        nearest_dist = float("inf")
        nearest_face_normal = None
        nearest_point = None

        # Search nearest face across all objects
        for obj, (bvh, bm) in bvh_trees.items():
            location, normal, index, dist = bvh.find_nearest(source_loc)
            if location is not None and dist < nearest_dist:
                nearest_dist = dist
                nearest_face_normal = normal.normalized()
                nearest_point = location

        if nearest_face_normal is None:
            print("No face found.")
            return

        # Align object: set its Z axis to face normal
        # You can adjust this if you want another axis aligned
        up = Vector((0, 0, 1))
        rotation = up.rotation_difference(nearest_face_normal).to_matrix()
        source_obj.rotation_euler = rotation.to_euler()
        source_obj.rotation_euler.rotate_axis("Y", math.pi)
