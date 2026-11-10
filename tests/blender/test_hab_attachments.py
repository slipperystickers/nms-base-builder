"""Native hab openings: waste references, visible doors and both proxy modes."""
from pathlib import Path
import sys, json, time
import bpy
from mathutils import Matrix, Vector
sys.path.insert(0, str(Path(__file__).parent))
from test_support import module, addon, report

b = module('builder_v2')
h = module('hab_windows')
s = module('corvette_snapping')
switch = module('tools_menu.base_builder_menu_operators')
results = []

def unchanged(part, before):
    now = part.serialise()
    for key, value in before.items():
        if isinstance(value, list):
            assert max(abs(a-c) for a,c in zip(now[key], value)) < 1e-5, (key,now[key],value)
        else:
            assert now[key] == value, (key,now[key],value)

def remove_all():
    bpy.data.batch_remove(list(bpy.data.objects))
    addon.BUILDER.clear_caches()
    h._signatures.clear()

remove_all()
for detailed in (False, True):
    bpy.context.scene.bbe_detailed_proxies = detailed
    for pid in h.table():
        hab = b.add_part(pid, high_res=detailed)
        hab.matrix_world = Matrix.Translation((17,2,-4)) @ Matrix.Rotation(.7,4,'Z') @ b.X_ROT_90 @ Matrix.Scale(.3,4)
        hab_export = hab.serialise()
        closed = hab.object.data
        for aid in (h.WASTE, 'B_DOOR0', 'B_WALL_WIND0'):
            attachment = b.add_part(aid, high_res=detailed)
            obj = attachment.object
            previous_display = (obj.display_type, obj.hide_render, obj.show_in_front)
            covered = set()
            for choice in s.options(obj, hab.object):
                obj.matrix_world = choice[3]
                slots = h.matching_slots(obj, hab.object)
                if not slots or slots.issubset(covered):
                    continue
                covered.update(slots)
                before = attachment.serialise()
                h.refresh(force=True)
                assert slots.issubset(set(hab.object.data.get(h.OPEN,'').split(','))), (pid,aid,detailed,slots)
                assert hab.object.data != closed
                unchanged(hab,hab_export);unchanged(attachment,before)
                if aid == h.WASTE:
                    if pid.endswith('D'):
                        assert obj.data.get(h.GHOST_MESH) and obj.hide_render and not obj.hide_select
                    else:
                        assert h.GHOST not in obj and not obj.hide_render
                        assert obj.data.get(h.WASTE_STYLE, 'A') == pid[-1]
                    obj.select_set(True);assert obj.select_get()
                else:
                    assert (obj.display_type,obj.hide_render,obj.show_in_front) == previous_display
                snap_matrix = obj.matrix_world.copy()
                obj.location.x += 2
                bpy.context.view_layer.update();h.refresh(force=True)
                assert hab.object.data == closed
                assert h.GHOST not in obj and (obj.display_type,obj.hide_render,obj.show_in_front)==previous_display
                obj.matrix_world = snap_matrix;h.refresh(force=True)
                hab.matrix_world.translation.x += 2
                bpy.context.view_layer.update();h.refresh(force=True)
                assert hab.object.data == closed and h.GHOST not in obj
                hab.matrix_world.translation.x -= 2
                bpy.context.view_layer.update();h.refresh(force=True)
            expected = {k for k in h.table()[pid]['slots'] if aid != h.WASTE or k[4] in 'EW'}
            assert covered == expected,(pid,aid,detailed,covered,expected)
            # Deleting the attachment must restore the original closed proxy.
            bpy.data.objects.remove(obj,do_unlink=True);h.refresh(force=True)
            assert hab.object.data == closed
            results.append(dict(hab=pid,attachment=aid,detailed=detailed,slots=len(covered)))
        bpy.data.objects.remove(hab.object,do_unlink=True)

# Shared occupancy: removing one trigger cannot close a still-occupied wall.
bpy.context.scene.bbe_detailed_proxies = True
hab=b.add_part('B_HAB1_A');waste=b.add_part(h.WASTE);door=b.add_part('B_DOOR0')
bpy.context.view_layer.update()
choice=next(c for c in s.options(waste.object,hab.object)
            if s.DATA['B_HAB1_A'][int(c[0])]['name']=='SnapPoint_IntE1')
s.apply(waste.object,hab.object,choice)
target=choice[2]
doorchoice=next(c for c in s.options(door.object,hab.object)
               if (c[2]-target).length < .001)
s.apply(door.object,hab.object,doorchoice);h.refresh(force=True)
assert h.GHOST not in waste.object
saved=[p.serialise() for p in (hab,waste,door)]
for detailed in (False,True):
    bpy.context.scene.bbe_detailed_proxies=detailed
    switch._switch_scene_proxies(bpy.context,detailed,show_progress=False)
    h.refresh(force=True)
    assert h.GHOST not in waste.object and 'WALLE1_' in hab.object.data[h.OPEN]
    for part,before in zip((hab,waste,door),saved):unchanged(part,before)
waste.object.location.x += 5;bpy.context.view_layer.update();h.refresh(force=True)
assert h.GHOST not in waste.object and 'WALLE1_' in hab.object.data[h.OPEN]
bpy.data.objects.remove(door.object,do_unlink=True);h.refresh(force=True)
assert not hab.object.data.get(h.OPEN)

# The opposite-facing waste socket keeps the ordinary wall and loose model.
opposite = next(c for c in s.options(waste.object,hab.object)
                if s.DATA['B_HAB1_A'][int(c[0])]['name']=='SnapPoint_SPIGN_IntOppE1')
s.apply(waste.object,hab.object,opposite);bpy.context.view_layer.update();h.refresh(force=True)
assert h.GHOST not in waste.object and waste.object.data.get(h.WASTE_STYLE) == 'A'
assert not hab.object.data.get(h.OPEN)

# Invalid pose/scale and stale snap metadata cannot hide a loose reference.
waste.object['snapped_to']=hab.object.name
h.refresh(force=True);assert h.GHOST not in waste.object
s.apply(waste.object,hab.object,choice);waste.object.scale *= 1.1
bpy.context.view_layer.update();h.refresh(force=True)
assert h.GHOST not in waste.object

report('hab_attachments', dict(cases=results,total_slots=sum(r['slots'] for r in results),
       movement_deletion_quality_export=True,all_checks_passed=True))
