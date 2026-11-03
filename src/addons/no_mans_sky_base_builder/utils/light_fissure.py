"""Correct the Light Fissure's game-tinted beams in the HD preview.

The extracted beam textures are green masks. NMS tints them red/orange at
runtime; the raw texture colors are not the color seen in game.
"""

_BEAMS = {"BeamParticles_mat", "Scrolling_mat", "LightBeam_mat3"}
_REVISION = 1


def correct(mesh, object_id):
    if object_id != "BASE_BEAMSTONE" or mesh.get("bbe_fissure_tint_revision") == _REVISION:
        return

    for index, material in enumerate(mesh.materials):
        if material is None or material.name.split(".")[0] not in _BEAMS or not material.use_nodes:
            continue

        # The library can share materials across assets. Change only the
        # Light Fissure's mesh and preserve the texture-driven alpha.
        tinted = material.copy()
        tinted.name = "BBE Light Fissure / " + material.name
        tree = tinted.node_tree
        for shader in (n for n in tree.nodes if n.type == "BSDF_PRINCIPLED"):
            emission = shader.inputs["Emission Color"]
            if not emission.is_linked:
                continue
            source = emission.links[0].from_socket
            tree.links.remove(emission.links[0])
            luminance = tree.nodes.new("ShaderNodeRGBToBW")
            luminance.name = "BBE Fissure Brightness"
            tree.links.new(source, luminance.inputs["Color"])
            warm = tree.nodes.new("ShaderNodeValToRGB")
            warm.name = "BBE Fissure Red Orange"
            warm.color_ramp.elements[0].color = (0.08, 0.001, 0.0002, 1)
            warm.color_ramp.elements[1].color = (1, 0.19, 0.018, 1)
            tree.links.new(luminance.outputs["Val"], warm.inputs["Fac"])
            tree.links.new(warm.outputs["Color"], emission)
        mesh.materials[index] = tinted

    mesh["bbe_fissure_tint_revision"] = _REVISION


def refresh_scene(scene):
    """Upgrade Light Fissures in projects saved with the raw green texture."""
    seen = set()
    for obj in scene.objects:
        if obj.type != "MESH" or obj.get("ObjectID", "").lstrip("^") != "BASE_BEAMSTONE":
            continue
        mesh = obj.data
        if mesh.as_pointer() not in seen:
            correct(mesh, "BASE_BEAMSTONE")
            seen.add(mesh.as_pointer())
