from copy import copy

from .. import part
from ..utils import blend_utils


class BONE_REPLACER(part.Part):
    """Capture extra "Message" attribute."""

    def __init__(self, *args, **kwargs):
        super(BONE_REPLACER, self).__init__(*args, **kwargs)
        if "Message" not in self.object:
            self.object["Message"] = ""

    @property
    def message(self):
        return self.object.get("Message", "")

    @message.setter
    def message(self, value):
        self.object["Message"] = str(value)

    def serialise(self):
        data = super(BONE_REPLACER, self).serialise()
        data["Message"] = self.message
        return data

    @classmethod
    def deserialise_from_data(cls, data, *args, **kwargs):
        part = super(BONE_REPLACER, cls).deserialise_from_data(data, *args, **kwargs)
        part.message = data.get("Message", "")
        if part.message:
            return part.swap_object()
        return part

    def swap_object(self):
        # imported here rather than at the top: builder_v2 pulls in the override
        # table, which pulls in this module
        from .. import builder_v2

        matrix = copy(self.object.matrix_world)
        # the save keeps the colour on the placeholder, so carry it across or the
        # bone is built on the default palette and every fossil comes out the
        # same colour
        user_data = self.object.get("UserData", 0)
        time_stamp = self.time_stamp
        order = self.order
        belongs_to_preset = self.belongs_to_preset
        bone_id = self.message
        # the bone id is in the override table too, so this lands on BONE, which
        # builds it out of the high res library
        bone_part = builder_v2.add_part(
            bone_id, user_data=user_data, builder_object=self.builder,
            build_rigs=self.build_rigs,
        )
        bone_part.object.matrix_world = matrix
        bone_part.time_stamp = time_stamp
        bone_part.order = order
        bone_part.belongs_to_preset = belongs_to_preset
        # Clipboard, Save Manager and prefab import all use the returned Part.
        # Keep both wrappers live after replacing the temporary placeholder.
        blend_utils.delete(self.object)
        self.object = bone_part.object
        return bone_part
