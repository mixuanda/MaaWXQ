"""Synthetic surface order and shop-close contracts, without native input."""
from copy import deepcopy
import unittest

from runtime.surface_gate import inspect_surface, verify_shop_close
import test_transition_verification as fixtures


class SurfaceGateTests(unittest.TestCase):
    def frames(self):
        before = fixtures.phase_frame(); after = fixtures.phase_frame('b', '2026-01-01T00:00:03Z')
        for frame in (before, after):
            frame['v14'] = {'owner': 0, 'panel_name': 0, 'panel_name_white': 0, 'capacity': 1,
                            'counts': [{'value': 1, 'score': 1}, {'value': 2, 'score': .7}],
                            'cells': [{'id': 2, 'score': .999}]}
        for i in range(4): fixtures.set_score(after, 'price_' + str(i), 0)
        return before, after

    def arguments(self, before, after):
        return {'expected_count': 1, 'target_cell': 2,
                'title_anchor': {'before_sha256': before['sha256'], 'after_sha256': after['sha256'],
                                 'roi': [678, 7, 60, 30], 'score': 1},
                'submission': {'sent': True, 'owned_release_confirmed': True, 'cleanup_errors': [],
                               'action_budget_remaining': 0, 'submission_outcome': 'down_and_owned_up_submitted'},
                'native': {'held': False, 'release_confirmed': True, 'cleanup_errors': [], 'down_count': 2, 'owned_up_count': 1},
                'started_at': '2026-01-01T00:00:01Z', 'released_at': '2026-01-01T00:00:01.1Z',
                'now': '2026-01-01T00:00:04Z'}

    def test_shop_normalization_precedes_covered_population_but_cannot_authorize_deployment(self):
        before, after = self.frames(); before['v14'].update(counts=[], capacity=.5)
        decision = inspect_surface(before, 1, 2)
        self.assertEqual(decision['action'], 'dismiss_shop'); self.assertFalse(decision['execution_allowed'])
        after['v14'].update(counts=[], capacity=.5)
        self.assertEqual(inspect_surface(after, 1, 2)['action'], 'stop')

    def test_known_owned_panel_has_priority_and_unknown_panel_stops(self):
        before, _ = self.frames(); before['v14'].update(owner=1, panel_name_white=1)
        fixtures.set_score(before, 'own_portrait', 0)
        self.assertEqual(inspect_surface(before, 1, 2)['action'], 'dismiss_owned_panel')
        before['v14']['panel_name_white'] = .96
        self.assertEqual(inspect_surface(before, 1, 2)['action'], 'stop')

    def test_no_preparation_or_owned_player_proof_waits_without_input(self):
        before, _ = self.frames(); fixtures.set_score(before, 'phase_ready', .2)
        self.assertEqual(inspect_surface(before, 1, 2)['action'], 'wait')
        before, _ = self.frames(); fixtures.set_score(before, 'own_portrait', .98)
        self.assertEqual(inspect_surface(before, 1, 2)['action'], 'wait')

    def test_closed_surface_still_requires_fresh_count_capacity_and_one_empty_target(self):
        _, after = self.frames()
        self.assertEqual(inspect_surface(after, 1, 2)['action'], 'deployment_surface_ready')
        for rows in ([], [{'id': 2, 'score': .96}], [{'id': 2, 'score': 1}, {'id': 2, 'score': 1}]):
            altered = deepcopy(after); altered['v14']['cells'] = rows
            self.assertEqual(inspect_surface(altered, 1, 2)['action'], 'stop')
        after['v14']['counts'][1]['score'] = .99
        self.assertEqual(inspect_surface(after, 1, 2)['action'], 'stop')

    def test_malformed_anchors_and_owner_state_do_not_fall_back_to_clicks(self):
        before, _ = self.frames()
        for value in (float('nan'), True, 1.1):
            altered = deepcopy(before); altered['matches'][0]['score'] = value
            self.assertEqual(inspect_surface(altered, 1, 2)['action'], 'stop')
        before['matches'].append(deepcopy(before['matches'][0]))
        self.assertEqual(inspect_surface(before, 1, 2)['action'], 'stop')
        before, _ = self.frames(); before['v14'].pop('owner')
        self.assertEqual(inspect_surface(before, 1, 2)['action'], 'stop')
        self.assertEqual(inspect_surface(None, 1, 2)['action'], 'stop')

    def test_replay_and_explicit_live_close_are_separate_from_deployment_success(self):
        before, after = self.frames(); args = self.arguments(before, after)
        result = verify_shop_close(before, after, **args)
        self.assertEqual(result['status'], 'shop_close_replay_verified'); self.assertTrue(result['evidence_verified'])
        self.assertFalse(result['game_postcondition_verified']); self.assertFalse(result['deployment_verified'])
        self.assertFalse(result['execution_allowed']); self.assertFalse(result['blind_retry_allowed'])
        result = verify_shop_close(before, after, **args, source_mode='live_capture')
        self.assertEqual(result['status'], 'shop_close_verified'); self.assertTrue(result['game_postcondition_verified'])
        self.assertFalse(result['deployment_verified'])

    def test_header_pixel_identity_can_bridge_unknown_round_ocr_for_close_only(self):
        before, after = self.frames(); args = self.arguments(before, after)
        result = verify_shop_close(before, after, **args, before_round_text='2回战', after_round_text='')
        self.assertTrue(result['evidence_verified']); self.assertTrue(result['numeric_round_required_for_deployment'])
        result = verify_shop_close(before, after, **args, before_round_text='第4回合', after_round_text='第5回合')
        self.assertIn('shop_close_crossed_round', result['reasons'])

    def test_title_hash_roi_and_threshold_cannot_be_waived_by_preparation_controls(self):
        before, after = self.frames(); original = self.arguments(before, after)
        for key, value in [('before_sha256', 'f' * 64), ('after_sha256', 'f' * 64),
                           ('score', .96), ('score', float('nan')), ('roi', [678, 7, 61, 30])]:
            args = deepcopy(original); args['title_anchor'][key] = value
            self.assertIn('same_round_title_binding_required', verify_shop_close(before, after, **args)['reasons'])

    def test_current_frames_must_be_distinct_bound_fresh_and_in_order(self):
        before, after = self.frames(); args = self.arguments(before, after)
        self.assertIn('shop_close_frame_stale', verify_shop_close(before, after, **(args | {'now': '2026-01-01T00:00:12Z'}))['reasons'])
        altered = deepcopy(after); altered['identity']['geometry_version'] = 'changed'
        self.assertIn('shop_close_window_changed', verify_shop_close(before, altered, **args)['reasons'])
        altered = deepcopy(after); altered['sha256'] = before['sha256']
        self.assertIn('distinct_bound_shop_frames_required', verify_shop_close(before, altered, **args)['reasons'])
        altered = deepcopy(after); altered['captured_at'] = 'bad'
        self.assertIn('shop_close_timestamp', verify_shop_close(before, altered, **args)['reasons'])
        self.assertIn('shop_close_frame_order', verify_shop_close(before, after, **(args | {'released_at': '2026-01-01T00:00:03.1Z'}))['reasons'])

    def test_no_effect_or_unclean_release_never_verifies_or_retries(self):
        before, after = self.frames(); original = self.arguments(before, after)
        for section, key, value in [('native', 'held', True), ('native', 'cleanup_errors', ['failed']),
                                    ('submission', 'sent', 1), ('native', 'owned_up_count', 0)]:
            args = deepcopy(original); args[section][key] = value
            self.assertIn('shop_close_release_unproven', verify_shop_close(before, after, **args)['reasons'])
        fixtures.set_score(after, 'price_0', 1); fixtures.set_score(after, 'price_1', 1)
        self.assertIn('shop_close_or_restored_surface_unproven', verify_shop_close(before, after, **original)['reasons'])

    def test_reused_capture_and_source_mode_mismatch_reject_live_verification(self):
        before, after = self.frames(); args = self.arguments(before, after)
        after['source_mode'] = 'saved_replay'
        self.assertIn('source_mode_mismatch', verify_shop_close(before, after, **args, source_mode='live_capture')['reasons'])
        after.update(source_mode='live_capture', source_capture_reused=True)
        self.assertIn('reused_frame_cannot_be_live', verify_shop_close(before, after, **args, source_mode='live_capture')['reasons'])
        with self.assertRaises(ValueError): verify_shop_close(before, after, **args, source_mode='auto')


if __name__ == '__main__': unittest.main()
