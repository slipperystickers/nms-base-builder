import math
from mathutils import Matrix, Quaternion, Vector
from ..part_overrides import line
from ..utils import material


class U_PIPELINE(line.Line):
    def __init__(self, *args, **kwargs):
        super(U_PIPELINE, self).__init__(*args, **kwargs)
        material.assign_pipe_material(self.object)

    @classmethod
    def deserialise_from_data(cls, data, builder_object, build_rigs=True, compensate_normal=True):
        part = super().deserialise_from_data(data, builder_object, build_rigs, compensate_normal)
        up = data.get('Up')
        if up and Vector(up).length_squared:
            part.object['bbe_pipe_import_up'] = tuple(Matrix.Rotation(math.pi/2,3,'X') @ Vector(up))
        return part

    def serialise(self):
        record = super().serialise()
        roll = self.object.bbe_supply_roll
        axis = Vector(record['At'])
        if roll and axis.length_squared:
            record['Up'] = list(Quaternion(axis.normalized(),roll) @ Vector(record['Up']))
        return record


def restore_roll(obj):
    up = Vector(obj['bbe_pipe_import_up'])
    del obj['bbe_pipe_import_up']
    matrix = obj.matrix_world
    axis = matrix.col[2].xyz.normalized()
    default = matrix.col[1].xyz.normalized()
    if axis.length_squared and default.length_squared:
        obj.bbe_supply_roll = math.atan2(axis.dot(default.cross(up)),default.dot(up))
