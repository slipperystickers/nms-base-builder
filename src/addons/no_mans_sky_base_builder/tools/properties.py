import bpy
from ..utils import curve, dictionary, blend_utils
from .. import builder
import re
from ..utils.mirror_utils import ShowMessageBox

nice_name_dictionary = dictionary.get_nice_names_diictionary()

BUILDER = builder.get_builder()


def get_uniform_scale(self):
    if self.active_object is not None:
        return self.active_object.scale.x
    return None


def set_uniform_scale(self, value):
    if self.active_object is not None:
        self.active_object.scale = (value, value, value)

class Properties(bpy.types.PropertyGroup):

    # For displaying field to edit number of objects on curve
    active_curve_number_of_objects: bpy.props.IntProperty(
        name="Number of Objects",
        default = 10,
        #update = lambda self, context: self.on_number_of_objects_change(),

        min=1,       # Absolute lowest value allowed
        max=1000,      # Absolute highest value allowed
        soft_min=5,  # Slider UI floor
        soft_max=500  # Slider UI ceiling
    )

    # For displaying a field that takes a float value that will be miltiplied over every object on curve
    active_curve_radius_multiplier: bpy.props.FloatProperty(
        name="Overall Radius",
        default = 1.0,
        #update = lambda self, context: self.on_curve_radius_multiplier_change(),

        min=0.0,       # Absolute lowest value allowed
        max=100.0,      # Absolute highest value allowed
        soft_min=0.01,  # Slider UI floor
        soft_max=5.0   # Slider UI ceiling
    )

    # Hidden properties to store the state from the previous update
    prev_curve_number_of_objects: bpy.props.IntProperty(default=5)
    prev_curve_radius_multiplier: bpy.props.FloatProperty(default=1.0)

    # For displaying name of target curve selected
    active_curve_name: bpy.props.StringProperty(
        name="active curve name",
        default = "",
        options={'SKIP_SAVE'},
    )

    # check to see if curve related options should be shown or not
    show_gap_edit_field : bpy.props.BoolProperty(
        name="Show gap edit field",
        default=False,
        options={'SKIP_SAVE'},
        #update = lambda self, context: self.on_show_gap_edit_field_change(),
    )

    # to show respective options when curve is switched to objects or curve mode
    selected_curve_object_is_parent: bpy.props.BoolProperty(
        name="Is parent of Child",
        default=True,
        options={'SKIP_SAVE'},
    )

    active_object : bpy.props.PointerProperty(
        name="Active Object",
        type=bpy.types.Object,
    )

    uniform_scale: bpy.props.FloatProperty(
        name="Scale",
        get=get_uniform_scale,
        set=set_uniform_scale,
        min=0.0,
        default=1.0,
        precision=6
    )

    copied_position: bpy.props.FloatVectorProperty(
        name="Copied Location",
        description="Position of an object",
        default=(0.0, 0.0, 0.0),
        size=3,
    )

    copied_rotation: bpy.props.FloatVectorProperty(
        name="Copied Rotation",
        description="Rotation of an object",
        default=(0.0, 0.0, 0.0),
        size=3,
    )

    copied_scale: bpy.props.FloatVectorProperty(
        name="Copied Scale",
        description="Scale of an object",
        default=(1.0, 1.0, 1.0),
        size=3,
    )


    def show_curve_edit_options(self,curve_obj):
        self.show_gap_edit_field = True
        self.active_curve_name = curve_obj.name
        self.active_curve_number_of_objects = curve_obj.get("objects_count",10)
        self.active_curve_radius_multiplier = curve_obj.get("radius_multiplier",1.0)

        self.prev_curve_number_of_objects = self.active_curve_number_of_objects
        self.prev_curve_radius_multiplier = self.active_curve_radius_multiplier


        self.selected_curve_object_is_parent = curve_obj["parent_selected"]

    def hide_curve_edit_options(self):
        self.show_gap_edit_field = False
        self.active_curve_name = ""

    def select_parent_curve(self):
        self.selected_curve_object_is_parent = True
        active_object = bpy.context.active_object
        selected_objects = bpy.context.selected_objects

        if active_object not in selected_objects:
            selected_objects.append(active_object)

        visited_curves_names = []
        curves_to_select = []
        for obj in selected_objects:
            if curve.Curve.PROP_CURVE_PARENT in obj and curve.Curve.PROP_CURVE_ID not in obj:
                parent_curve_name = obj.get(curve.Curve.PROP_CURVE_PARENT)
                if parent_curve_name in visited_curves_names:
                    continue

                parent_curve = curve.select_parent_curve(obj)
                if parent_curve is None:
                    continue

                visited_curves_names.append(parent_curve.name)
                curves_to_select.append(parent_curve)

        if curves_to_select:
            blend_utils.select(curves_to_select)

    def select_children_of_curve(self):
        self.selected_curve_object_is_parent = False
        active_object = bpy.context.active_object
        selected_objects = bpy.context.selected_objects

        for obj in selected_objects:
            if "CurveID" not in obj:
                ShowMessageBox(
                    message="All selected objects are not curves",
                    title="Selection Failed"
                )
                return

        children_to_select = []
        if active_object is not None and curve.Curve.PROP_CURVE_ID in active_object:
            for curve_obj in selected_objects:
                children = curve.select_children_of_curve(curve_obj)
                if children:
                    children_to_select.extend(children)

        if children_to_select:
            blend_utils.select(children_to_select)

    def active_curve_is_highlighted(self):
        selected_objects = bpy.context.selected_objects
        active_object = bpy.context.view_layer.objects.active
        active_curve_name = self.active_curve_name
        if "has_linked_objects" in active_object:
            for obj in selected_objects:
                if obj.name == active_curve_name:
                    return True
        elif "curve_parent" in active_object:
            for obj in selected_objects:
                if obj.name == active_object.name:
                    return True


        for obj in selected_objects:
            if obj.name == active_curve_name:
                return True
        return False

    def set_active_obect(self, obj):
        if obj is None:
            return

        curve_obj = curve.get_curve_or_linked_curve(obj)
        if curve_obj is not None:
            self.show_curve_edit_options(curve_obj)
        elif "ObjectID" in obj:
            self.hide_curve_edit_options()

        self.active_object = obj

    def get_active_object_nice_name(self):
        if self.active_object is None:
            return None, None

        if "ObjectID" not in self.active_object:
            return self.active_object.name, None

        object_id = self.active_object["ObjectID"]
        nice_name = nice_name_dictionary.get(object_id, "")
        nice_name = self.beaufity_name(nice_name)

        return nice_name, object_id

    def beaufity_name(self,text):
        parts = re.split(r'(\([^)]*\))', text)
        return ''.join(
            part if part.startswith('(') else part.title()
            for part in parts
        )

    def paste_transformatinos(self, paste_location = False, paste_rotation = False, paste_scale = False):
        location = self.copied_position
        rotation = self.copied_rotation
        scale = self.copied_scale

        selected_objects = bpy.context.selected_objects

        for obj in selected_objects:
            if paste_location:
                obj.location = location
            if paste_rotation:
                obj.rotation_euler = rotation
            if paste_scale:
                obj.scale = scale

