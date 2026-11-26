"""Catalogue additions get individual, persistent discovery borders."""
import importlib
import json
import os
from pathlib import Path
import sys
import tempfile
from unittest.mock import patch

import bpy

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_support import D, module

markers = module('utils.new_assets')
definitions = module('utils.dictionary').get_parts_definition()
holiday = set(json.loads((D / 'resources/holiday_assets.json').read_text())['assets'])
holiday -= {'B_WNG_O_0', 'B_WNG_O_0_R'}  # Existing tiles with revised geometry.
assert len(holiday) == 34

with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, NMS_BASE_BUILDER_DATA_DIR=directory):
    importlib.reload(markers)
    # Keep discoveries from the previous release when upgrading an existing profile.
    legacy = markers._path()
    legacy.parent.mkdir(parents=True, exist_ok=True)
    legacy.write_text(json.dumps(['B_WNG_Y']))
    with patch.dict(definitions, {'^FUTURE_PART': definitions['^B_COK_A']}):
        assert markers.is_new('FUTURE_PART')
    assert all(markers.is_new(pid) for pid in holiday)
    assert not any(markers.is_new(pid) for pid in ('B_WNG_Y', 'B_COK_A', 'B_WNG_O_0', 'B_WNG_O_0_R'))
    assert markers.is_new('B_WNG_X') and not markers.is_new('prefab:SWARM_TROPHY_R')
    # Use the same operator that places a horizontal search result.
    result = module('asset_strip').place(bpy.context, 'SWARM_TROPHY_R')
    assert result == {'FINISHED'} and not markers.is_new('^SWARM_TROPHY_R')
    assert all(markers.is_new(pid) for pid in holiday - {'SWARM_TROPHY_R'})
    importlib.reload(markers)
    assert not markers.is_new('SWARM_TROPHY_R') and not markers.is_new('B_WNG_Y')
    assert markers.is_new('SWARM_TROPHY_G')
    assert markers.mark_viewed('SWARM_TROPHY_G')
    assert not markers.mark_viewed('SWARM_TROPHY_G')

print('Asset discovery passed: Holiday, Forsaken migration, future additions and browser clicks.')
