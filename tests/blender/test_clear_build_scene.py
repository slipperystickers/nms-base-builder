"""Both clear and file-import remove old build containers without touching other scenes."""
from pathlib import Path
import json
import sys
sys.path.insert(0, str(Path(__file__).parent))
from test_support import *

scene = bpy.context.scene
other = bpy.data.scenes.new('Other scene remains')
shared = bpy.data.collections.new('Shared with other scene')
other.collection.children.link(shared)
shared_obj = bpy.data.objects.new('Shared empty', None)
shared.objects.link(shared_obj)
asset = bpy.data.collections.new('Unlinked library asset')
asset.use_fake_user = True
asset.objects.link(bpy.data.objects.new('Library empty', None))
pin = module('tools.asset_browser_operators').browser_pin_object()
original_screen = bpy.context.window.screen


def dirty():
    parent = bpy.data.collections.new('Old build')
    child = bpy.data.collections.new('Old helper collection')
    scene.collection.children.link(parent)
    parent.children.link(child)
    child.objects.link(bpy.data.objects.new('Untagged empty', None))
    root = bpy.data.objects.new('Old Forge root', None)
    child.objects.link(root)
    part = module('builder_v2').add_part('BUILDFLATPANEL', high_res=False).object
    part.name = 'Old build panel'
    part.parent = root
    scene.collection.children.link(shared)
    return parent.name, child.name, root.name, part.name


def clean_check(old):
    assert len(scene.collection.children) == 1
    assert scene.collection.children[0].get('_nms_collection_name') == 'Collection'
    assert all(name not in bpy.data.collections for name in old[:2])
    assert all(name not in bpy.data.objects for name in old[2:])
    assert shared_obj.name in other.objects
    assert shared.name in other.collection.children
    assert asset.name in bpy.data.collections and len(asset.objects) == 1
    assert pin.name in bpy.data.objects and pin.get('bbe_asset_browser_pin')
    assert bpy.context.window.screen == original_screen


old = dirty()
assert bpy.ops.object.nms_new_file('EXEC_DEFAULT') == {'FINISHED'}
clean_check(old)
assert set(scene.objects) == {pin}

old = dirty()
path = QA / 'clear_import.json'
path.write_text(json.dumps({'Objects': [{'ObjectID': '^BUILDFLATPANEL',
    'UserData': 5, 'Position': [0, 0, 0], 'Up': [0, 1, 0], 'At': [0, 0, 1]}]}))
scene.nms_main.import_build_file(str(path))
clean_check(old)
assert len([o for o in scene.objects if 'ObjectID' in o]) == 1
assert not any(o.type == 'EMPTY' for o in scene.objects)
report('clear_build_scene', dict(passed=True, explicitClear=True, importClear=True,
       nestedEmptiesAndCollections=True, otherSceneAndAssetPreserved=True,
       browserAndWorkspacePreserved=True))
print('CLEAR_BUILD_SCENE_PASS', flush=True)
