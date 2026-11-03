"""Independent native pilot regressions; NumPy only, no Blender or game access."""
import copy
import json
from pathlib import Path
import sys
import unittest

import numpy as np

REPO = Path(__file__).resolve().parents[1]
ADDON = REPO / 'src/addons/no_mans_sky_base_builder'
sys.path.insert(0, str(ADDON))
from pilot_math import apply_solver_pose, derive_foot_baselines, skin, solve_pilot


class NativePilotMathTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.settings = json.loads((ADDON / 'resources/pilot_profiles/ASTRO_ARMOURED.json').read_text())
        cls.fixture = json.loads((REPO / 'tests/fixtures/pilot-solver-native-regression.json').read_text())
        cls.captured = solve_pilot(cls.settings)

    def assert_positions(self, actual, expected, tolerance=1e-6):
        for name, point in expected.items():
            error = float(np.linalg.norm(np.asarray(actual[name]) - point))
            self.assertLess(error, tolerance, (name, error, actual[name], point))

    def test_captured_local_player_wrists_and_hips(self):
        # Targets came from complete local-player scene chains, independently
        # of the solver's output buffer. The fixture records visibility scope.
        with np.load(ADDON / 'resources/hd_additions/pilot_references/ASTRO_ARMOURED.skin.npz', allow_pickle=False) as asset:
            indices = {str(name): j for j, name in enumerate(asset['names'])}
            for state in self.fixture['live_states']:
                with self.subTest(state=state['label']):
                    result = solve_pilot(self.settings, foot_corrections=state['corrections'])
                    pose = apply_solver_pose(asset, result['names'], result['local_matrices'])
                    frame = np.asarray(state['model_to_cockpit'])
                    actual = {name: (pose[indices[name]] @ frame)[3, :3] for name in state['expected']}
                    self.assert_positions(actual, state['expected'])

    def test_held_out_native_solver_inputs(self):
        # Asymmetric, negative and partial corrections catch solutions that
        # merely interpolate the two observed poses or apply a whole-body lift.
        for case in self.fixture['held_out']:
            with self.subTest(case=case['name']):
                result = solve_pilot(self.settings, foot_corrections=case['corrections'])
                self.assert_positions(result['positions'], case['expected'])

    def test_both_skin_qualities_keep_all_hand_influences(self):
        resources = {
            'light': 'resources/pilot_references/ASTRO_ARMOURED.skin.npz',
            'detailed': 'resources/hd_additions/pilot_references/ASTRO_ARMOURED.skin.npz',
        }
        for quality, resource in resources.items():
            with self.subTest(quality=quality), np.load(ADDON / resource, allow_pickle=False) as asset:
                expected = self.fixture['skin_surfaces'][quality]
                self.assertEqual(asset['weights'].shape, (expected['vertex_count'], expected['influences']))
                pose = apply_solver_pose(asset, self.captured['names'], self.captured['local_matrices'])
                points = skin(asset, pose)[expected['vertex_indices']]
                error = np.linalg.norm(points - expected['expected_model_points'], axis=1)
                # Complete captured animation includes tiny finger updates
                # beyond the23 solved joints; these hand surface points remain
                # within20 micrometres, including fourth/later influences.
                self.assertLess(float(error.max()), 2e-5)

    def test_foot_baselines_can_be_derived_from_rest_rig(self):
        derived = derive_foot_baselines(self.settings)
        result = solve_pilot(derived)
        self.assert_positions(result['positions'], self.captured['positions'])

    def test_solver_preserves_shared_profile_inputs(self):
        before = copy.deepcopy(self.settings)
        solve_pilot(self.settings, foot_corrections=[0., .2])
        self.assertEqual(self.settings, before)


if __name__ == '__main__':
    unittest.main()
