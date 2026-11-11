"""Exercise the Duplicate Save popup against a disposable two-context Steam slot.

Run in windowed Blender with --factory-startup --enable-event-simulate.
"""
import copy
from pathlib import Path
import struct
import sys
import tempfile
import traceback
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_support import bpy, module, report
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from test_ship_link_resilience import fixture

manager = module('save_editor.ship_management')
files = manager.ship_files
core = manager.core
temporary = tempfile.TemporaryDirectory()
folder = Path(temporary.name)
source = files.slot_paths(folder, 1)[0]
root = fixture()
for ctx in ('Main', 'Season'):
    if ctx == 'Season':
        root['ExpeditionContext'] = fixture(context=ctx)['ExpeditionContext']
    player = core.player(root, ctx)
    ships = core.ships(root, ctx)
    ships[1] = copy.deepcopy(ships[0])
    ships[1]['Resource']['Filename'] = 'MODELS/FIGHTER.SCENE.MBIN'
    ships[1]['Name'] = ctx + ' fighter'
    for name in ('North', 'South'):
        player['PersistentPlayerBases'].append({
            'BaseType': {'PersistentBaseTypes': 'HomePlanetBase'},
            'Name': ctx + ' ' + name, 'Objects': [],
        })

save = files.SaveFile(source)
save.json_data = core.translate(root, False)
save.save()
meta = source.with_name('mf_' + source.name)
plain = bytearray(432)
struct.pack_into('<I', plain, 0, 0xeeeeeebe)
meta.write_bytes(files.steam_metadata.crypt(plain, files.steam_metadata.storage_number(meta.name)))
before = files.hashes([source, meta])
selector = patch.object(type(bpy.context.scene.nms_save_data), 'get_current_slot_data',
                        return_value={'saves': [str(source)]})
selector.start()

drawn = set()
draw_item = manager.BBE_UL_ship_keep.draw_item

def track_draw(self, context, layout, data, item, icon, active_data, active_propname, index):
    global review
    draw_item(self, context, layout, data, item, icon, active_data, active_propname, index)
    review = data
    drawn.add((item.context_name, item.ship, item.index))

tracker = patch.object(manager.BBE_UL_ship_keep, 'draw_item', track_draw)
tracker.start()
step = 0

def press(key):
    window = bpy.context.window_manager.windows[0]
    for value in ('PRESS', 'RELEASE'):
        window.event_simulate(type=key, value=value)

def open_review():
    window = bpy.context.window_manager.windows[0]
    area = next(a for a in window.screen.areas if a.type == 'VIEW_3D')
    region = next(r for r in area.regions if r.type == 'WINDOW')
    with bpy.context.temp_override(window=window, area=area, region=region):
        assert bpy.ops.bbe.ship_duplicate('INVOKE_DEFAULT') == {'RUNNING_MODAL'}

def verify():
    global step
    try:
        if step == 0:
            press('ESC')
        elif step in (1, 3):
            assert set(folder.iterdir()) == {source, meta}
            drawn.clear()
            open_review()
        elif step in (2, 4):
            expected_rows = {(ctx, ship, i) for ctx in ('Main', 'Season')
                             for ship, i in ((True, 0), (True, 1), (False, 1), (False, 2))}
            assert drawn == expected_rows, drawn
            assert set(folder.iterdir()) == {source, meta}
            for row in review.entries:
                assert row.keep == (row.ship and row.index == 1)
                # Keep different ships and bases in the two contexts.
                keep_ship, keep_base = (0, 2) if row.context_name == 'Main' else (1, 1)
                row.keep = row.index == (keep_ship if row.ship else keep_base)
            press('ESC' if step == 2 else 'RET')
        else:
            for path in files.slot_paths(folder, 2):
                result = files.SaveFile(path).load()
                assert path.with_name('mf_' + path.name).exists()
                for ctx in ('Main', 'Season'):
                    ships = core.ships(result, ctx)
                    assert [i for i, s in enumerate(ships) if core.occupied(s)] == ([0] if ctx == 'Main' else [1])
                    expected = ['PlayerShipBase', 'Main South'] if ctx == 'Main' else ['Season North']
                    bases = core.get(core.player(result, ctx), 'PersistentPlayerBases')
                    assert [core.kind(b) if core.kind(b) == 'PlayerShipBase' else core.get(b,'Name') for b in bases] == expected
                    core.validate_links(result, ctx)
            assert files.hashes(before) == before
            report('duplicate_save_picker', {'blender': bpy.app.version_string, 'passed': True})
            tracker.stop()
            selector.stop()
            temporary.cleanup()
            bpy.ops.wm.quit_blender()
            return None
        step += 1
        return 0.8
    except BaseException:
        print(traceback.format_exc(), flush=True)
        # Timers don't propagate exceptions to --python-exit-code.
        sys.stdout.flush()
        import os
        os._exit(1)

bpy.app.timers.register(verify, first_interval=2)
