"""Movable, fixed-pose scale references. These are never native game parts."""
from pathlib import Path
import bpy

TAG = 'bbe_character_reference'
PREFIX = 'BBE_CHARACTER_'
RACES = (
    ('ASTRO_DEFAULT', 'Anomaly'), ('GEK_DEFAULT', 'Gek'),
    ('KORVAX_DEFAULT', 'Korvax'), ('VYKEEN_DEFAULT', "Vy'keen"),
    ('FOURTH_DEFAULT', 'Traveller'), ('BUI_DEFAULT', 'Autophage'),
    ('ASTRO_ARMOURED', 'Armoured Anomaly'),
)
POSES = ('STANDING', 'SEATED')
RESOURCE = Path(__file__).parent / 'resources'


def asset_id(race, pose):
    return PREFIX + pose + '_' + race


def decode(identifier):
    for pose in POSES:
        for race, label in RACES:
            if identifier == asset_id(race, pose):
                return race, pose, label
    return None


def category_entries(favourites=()):
    return {pose.title(): {
        asset_id(race, pose): {'name': label + ' — ' + pose.title(),
                             'is_fav': asset_id(race, pose) in favourites,
                             'is_reference': True}
        for race, label in RACES} for pose in POSES}


def detailed_roots():
    from . import hd_library
    roots = []
    # Separate character downloads may provide their own root; older packs
    # still resolve through the established additions location.
    character_root = getattr(hd_library, 'characters_root', None)
    if character_root:
        roots.append(character_root())
    roots.extend((hd_library.additions_root(), hd_library.library_root(),
                  RESOURCE / 'hd_additions'))
    return [Path(root) / 'character_references' for root in roots if root]


def asset_path(race, pose, detailed):
    if race not in dict(RACES) or pose not in POSES:
        raise ValueError('Unknown character reference')
    roots = detailed_roots() if detailed else [RESOURCE / 'character_references']
    filename = race + '_' + pose + '.blend'
    path = next((root / filename for root in roots if (root / filename).is_file()), None)
    if path is None:
        raise ValueError('Detailed character references need the character pack' if detailed
                         else 'Character reference assets are missing')
    return path


def relink_texture_images(images=None):
    images = [image for image in (bpy.data.images if images is None else images)
              if image.get('bbe_character_texture') and not image.packed_file]
    if not images:
        return 0
    roots = [root / 'textures' for root in detailed_roots()]
    changed = 0
    for image in images:
        name = image.get('bbe_character_texture')
        if not isinstance(name, str) or Path(name).name != name or image.packed_file:
            continue
        path = next((root / name for root in roots if (root / name).is_file()), None)
        if path and image.filepath != str(path):
            image.filepath = str(path)
            image.reload()
            changed += 1
    return changed


def mesh_for(race, pose, detailed):
    path = asset_path(race, pose, detailed)
    pack_sha = None
    if detailed:
        from . import hd_library
        pack_sha = hd_library.characters_specification()['content_sha256']
    # Revision 2 carries the native mask-coloured HD materials. Do not reuse
    # an older mesh retained inside a saved .blend after the pack is updated.
    key = f'{race}:{pose}:{int(detailed)}:2'
    cached = next((mesh for mesh in bpy.data.meshes
                   if mesh.get('bbe_character_asset') == key
                   and (not detailed or mesh.get('bbe_character_pack_sha256') == pack_sha)), None)
    if cached:
        if detailed:
            relink_texture_images()
        return cached
    with bpy.data.libraries.load(str(path), link=False) as (source, target):
        target.meshes = list(source.meshes)
    meshes = [mesh for mesh in target.meshes if mesh]
    if len(meshes) != 1:
        for mesh in meshes:
            bpy.data.meshes.remove(mesh)
        raise ValueError('Invalid character reference library')
    mesh = meshes[0]
    image_nodes = [node for material in mesh.materials if material and material.use_nodes
                   for node in material.node_tree.nodes if getattr(node, 'image', None)]
    required = {node.image.get('bbe_character_texture') for node in image_nodes
                if node.image.get('bbe_character_texture')}
    if any(Path(name).name != name or not (path.parent / 'textures' / name).is_file()
           for name in required):
        materials = list(mesh.materials)
        images = {node.image for node in image_nodes}
        bpy.data.meshes.remove(mesh)
        for material in materials:
            if material and material.users == 0:
                bpy.data.materials.remove(material)
        for image in images:
            if image.users == 0:
                bpy.data.images.remove(image)
        raise ValueError('Character colour textures are missing from the character pack')
    for node in image_nodes:
        image = node.image
        name = image.get('bbe_character_texture')
        if not name:
            continue
        shared = next((item for item in bpy.data.images if item != image
                       and item.get('bbe_character_texture') == name
                       and item.colorspace_settings.name == image.colorspace_settings.name), None)
        if shared:
            node.image = shared
            if image.users == 0:
                bpy.data.images.remove(image)
        node.image.filepath = str(path.parent / 'textures' / name)
    mesh['bbe_character_asset'] = key
    if pack_sha:
        mesh['bbe_character_pack_sha256'] = pack_sha
    return mesh


def resolved_mesh(race, pose, detailed):
    try:
        return mesh_for(race, pose, detailed), detailed, ''
    except ValueError as exc:
        if not detailed:
            raise
        return mesh_for(race, pose, False), False, str(exc)


def character_pack_available():
    from . import hd_library
    return hd_library.characters_root() is not None


def add(context, identifier):
    decoded = decode(identifier)
    if decoded is None:
        raise ValueError('Unknown character reference')
    race, pose, label = decoded
    mesh, detailed, warning = resolved_mesh(race, pose, character_pack_available())
    collection = next((item for item in context.scene.collection.children
                       if item.get('bbe_character_collection')), None)
    if collection is None:
        collection = bpy.data.collections.new('Character References')
        collection['bbe_character_collection'] = True
        context.scene.collection.children.link(collection)
    obj = bpy.data.objects.new(label + ' — ' + pose.title() + ' Reference', mesh)
    collection.objects.link(obj)
    obj.location = context.scene.cursor.location.copy()
    obj[TAG] = True
    obj['bbe_character_race'] = race
    obj['bbe_character_pose'] = pose
    obj['bbe_character_detailed'] = detailed
    obj['bbe_character_asset_warning'] = warning
    obj['excluded_from_nms_export'] = True
    obj['reference_only'] = True
    obj.hide_render = True
    obj.hide_select = False
    obj.lock_location = obj.lock_rotation = obj.lock_scale = (False, False, False)
    # No native ObjectID, PresetID, SnapID or parenting/placement drivers.
    for selected in context.selected_objects:
        selected.select_set(False)
    obj.select_set(True)
    context.view_layer.objects.active = obj
    if detailed and context.area and context.area.type == 'VIEW_3D':
        context.area.spaces.active.shading.type = 'MATERIAL'
    return obj


def sync_scene_quality(scene, detailed):
    # Character references have a separate HD pack and are not ship proxies.
    # Switching ship parts to Simple Proxies must not strip their colour.
    if not detailed:
        return 0, 0
    switched = missing = 0
    for obj in scene.objects:
        if not obj.get(TAG):
            continue
        mesh, actual, warning = resolved_mesh(obj['bbe_character_race'],
                                              obj['bbe_character_pose'], character_pack_available())
        obj.data = mesh
        obj['bbe_character_detailed'] = actual
        obj['bbe_character_asset_warning'] = warning
        switched += 1
        missing += bool(warning)
    return switched, missing


@bpy.app.handlers.persistent
def load_post(_):
    references = [obj for obj in bpy.data.objects
                  if not obj.library and obj.users_scene and obj.get(TAG)]
    if not references:
        return
    relink_texture_images()
    from . import hd_library
    pack_sha = (hd_library.characters_specification()['content_sha256']
                if hd_library.characters_root() else None)
    # A saved scene can contain simple references placed before the separate
    # character pack was installed. Promote them when the pack is available.
    # Also replace HD meshes from an older pack revision without moving objects.
    for obj in references:
        race, pose = obj.get('bbe_character_race'), obj.get('bbe_character_pose')
        wants_hd = bool(pack_sha)
        if not wants_hd and not obj.get('bbe_character_detailed'):
            continue
        try:
            asset_path(race, pose, True)
            needs_mesh = (not obj.get('bbe_character_detailed') or
                          obj.data.get('bbe_character_asset') != f'{race}:{pose}:1:2' or
                          obj.data.get('bbe_character_pack_sha256') != pack_sha)
            if not needs_mesh:
                images = {node.image for material in obj.data.materials if material and material.use_nodes
                          for node in material.node_tree.nodes if getattr(node, 'image', None)}
                if any(image.source == 'FILE' and not image.packed_file
                       and not Path(bpy.path.abspath(image.filepath, library=image.library)).is_file()
                       for image in images):
                    raise ValueError('Character colour textures are unavailable on this computer')
            if needs_mesh:
                obj.data = mesh_for(race, pose, True)
            obj['bbe_character_detailed'] = True
            obj['bbe_character_asset_warning'] = ''
        except (ValueError, OSError) as error:
            try:
                mesh = mesh_for(race, pose, False)
            except (ValueError, OSError) as fallback_error:
                obj['bbe_character_asset_warning'] = str(fallback_error)
                continue
            obj.data = mesh
            obj['bbe_character_detailed'] = False
            obj['bbe_character_asset_warning'] = str(error) + '; showing the lightweight reference'


def refresh_open_references():
    """Repair references in an already-open scene after enabling this add-on."""
    load_post(None)
    return None


def register():
    if load_post not in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.append(load_post)
    if not bpy.app.timers.is_registered(refresh_open_references):
        bpy.app.timers.register(refresh_open_references, first_interval=0.1)


def unregister():
    if load_post in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.remove(load_post)
    if bpy.app.timers.is_registered(refresh_open_references):
        bpy.app.timers.unregister(refresh_open_references)
