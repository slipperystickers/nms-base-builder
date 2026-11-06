"""Although the control point is not a base part.

It's convenient to inherit from Part to get all the snap methods.

We override the object id classes so that it's stored in memory, rather
then on the node itself, so that it doesn't get exported along with everything
else when bringing it back into the game.

"""

from .. import part


class POWER_CONTROL(part.Part):
    def __init__(self, bpy_object=None, builder_object=None, *args, **kwargs):
        self.object = bpy_object
        self.__object_id = bpy_object["SnapID"]
        self.__builder_object = builder_object

    @property
    def builder(self):
        return self.__builder_object

    @property
    def object_id(self):
        return self.__object_id

    @object_id.setter
    def object_id(self, value):
        self.__object_id = value

    def snap_to(self, target, next_target=False, prev_target=False,
                next_source=False, prev_source=False):
        # Legacy point/Snap Next workflows (including NMS-Util) must use the
        # same typed sockets as the new asset-browser target picker.
        from .. import cable_connections as cables
        kind = self.object.get('bbe_cable_kind')
        if not kind:
            import bpy
            cable = bpy.data.objects.get(self.object.get('power_line', ''))
            kind = cable.get('ObjectID') if cable is not None else None
        if kind not in cables.KINDS:
            return super().snap_to(target, next_target, prev_target, next_source, prev_source)
        if self.object == target.object:
            return False
        points = cables.sockets(target.object, kind)
        if not points:
            return False
        keys = list(points)
        key = self.object.get('bbe_socket_key')
        if key not in keys:
            key = min(keys, key=lambda k: (points[k]-self.object.matrix_world.translation).length_squared)
        if next_target or prev_target:
            key = keys[(keys.index(key) + (1 if next_target else -1)) % len(keys)]
        cables.bind(self.object, target.object, key, kind)
        return True
