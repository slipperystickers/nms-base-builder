"""Open an unsaved, isolated comparison scene; never write the user's bench."""
import hashlib
import json
import sys
from pathlib import Path
import bpy
from mathutils import Quaternion

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / 'tests/blender'))
from test_support import module, QA

source = Path('G:/blenderstuff/pilottest.blend')
before = hashlib.sha256(source.read_bytes()).hexdigest()
p = module('pilot_reference')
original_asset_path = p.asset_path
p.asset_path = lambda race, detailed: (
    Path(p.__file__).parent / 'resources/hd_additions/pilot_references' / f'{race}.blend'
    if detailed else original_asset_path(race, detailed))

# Append the bench into an unsaved session rather than opening/overwriting it.
for obj in list(bpy.context.scene.objects):
    bpy.data.objects.remove(obj, do_unlink=True)
with bpy.data.libraries.load(str(source), link=False) as (src, dst):
    dst.objects = list(src.objects)
for obj in dst.objects:
    if obj:
        bpy.context.scene.collection.objects.link(obj)
cockpit = p.first_cockpit(bpy.context.scene)
assert cockpit is not None
for obj in bpy.context.selected_objects:
    obj.select_set(False)
cockpit.select_set(True)
bpy.context.view_layer.objects.active = cockpit
bpy.context.view_layer.update()
bpy.context.scene.bbe_detailed_proxies = True
model = p.choose(bpy.context, 'ASTRO_DEFAULT')
bpy.context.view_layer.update()
bpy.context.scene.name = 'Pilot origin comparison — UNSAVED'
for screen in bpy.data.screens:
    for area in screen.areas:
        if area.type != 'VIEW_3D':
            continue
        space = area.spaces.active
        space.show_gizmo = space.show_gizmo_context = True
        space.show_region_ui = False
        space.shading.type = 'SOLID'
        space.shading.color_type = 'MATERIAL'
        space.region_3d.view_rotation = Quaternion((.5, .5, .5, .5))
        space.region_3d.view_perspective = 'ORTHO'
        space.region_3d.view_location = (0, .1, .85)
        space.region_3d.view_distance = 4
assert not bpy.data.filepath, 'Comparison must remain an unsaved scene'
assert before == hashlib.sha256(source.read_bytes()).hexdigest()
bpy.ops.ed.undo_push(message='Pilot comparison ready')
report = {'source': str(source), 'source_unchanged': True,
          'first_cockpit': cockpit.name, 'order': cockpit.get('order'),
          'scale': list(cockpit.scale), 'reference': model.name,
          'placement': 'Fixed origin; game calibration pending'}
(QA / 'pilot-comparison-ready.json').write_text(json.dumps(report, indent=2))
print('PILOT_COMPARISON_READY', json.dumps(report), flush=True)

def capture():
    bpy.ops.screen.screenshot(filepath=str(QA / 'pilot-comparison-ready.png'))
    return None
bpy.app.timers.register(capture, first_interval=5)
