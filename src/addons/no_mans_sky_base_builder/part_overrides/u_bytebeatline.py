from ..part_overrides import line
from ..utils import material, materials_v2


class U_BYTEBEATLINE(line.Line):
    def __init__(self, *args, **kwargs):
        super(U_BYTEBEATLINE, self).__init__(*args, **kwargs)

        if not materials_v2.is_high_res(self.object):
            material.assign_bytebeat_material(self.object)
        from .. import cable_connections
        cable_connections.style(self.object)

    def retrieve_object_from_id(self, object_id):
        # Keep Line's special length/export math and endpoint rig. Only the
        # display mesh changes; the generic bulk importer normalises lengths.
        from .. import builder_v2
        obj = builder_v2.new_high_res_object(object_id)
        return obj if obj is not None else super().retrieve_object_from_id(object_id)
