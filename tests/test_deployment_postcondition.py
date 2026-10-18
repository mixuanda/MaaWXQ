"""Synthetic evidence regressions; no capture, native API or live game input."""
from copy import deepcopy
import unittest

from runtime.deployment_postcondition import bind_inspected_evidence, digest, intent_from, verify_deployment


class DeploymentPostconditionTests(unittest.TestCase):
    def fixture(self):
        identity = {'identity_version': 'fixture-identity', 'geometry_version': 'fixture-geometry',
                    'client': {'width': 1450, 'height': 869}}
        source = {'sha256': 'a' * 64, 'captured_at': '2026-01-01T00:00:00Z', 'identity': identity}
        intent = intent_from(source, match_id='fixture-custom', hero_id='fixture-hero',
                             shop_frame_sha256='b' * 64, offer_slot=0)
        post = {'sha256': 'c' * 64, 'captured_at': '2026-01-01T00:00:04Z', 'identity': deepcopy(identity),
                'deployment_pixels': {
                    'hand': {'Known': True, 'BeforeCount': 3, 'AfterCount': 2,
                             'Passive': {'Score': .99, 'X': 610, 'Y': 774, 'Scale': 1},
                             'Equipment': {'Score': .98, 'X': 743, 'Y': 778, 'Scale': 1},
                             'BeforePassiveHero': .1, 'BeforeEquipmentHero': .2},
                    'new_unit': {'Known': True, 'Pixels': 8000, 'X': 622, 'Y': 457,
                                 'Width': 156, 'Height': 118, 'CenterX': 699, 'CenterY': 523}}}
        selected = {'sha256': 'd' * 64, 'captured_at': '2026-01-01T00:00:06Z', 'identity': deepcopy(identity),
                    'detail_board': {'one_score': 1, 'zero_score': .4, 'capacity_score': 1},
                    'deployment_detail': {'Known': True, 'Score': .98, 'OtherScore': .1, 'Margin': .88, 'Slot': 0},
                    'unit_owner_score': 1}
        evidence = bind_inspected_evidence(intent, post, selected, inspection_target=[699, 523],
                                           shop_frame_sha256='b' * 64)
        submission = {'sent': True, 'owned_release_confirmed': True, 'cleanup_errors': [],
                      'action_budget_remaining': 0, 'submission_outcome': 'drag_path_submitted_requires_visual_verification',
                      'released_at': '2026-01-01T00:00:02Z'}
        return intent, submission, evidence, post, selected

    def verify(self, intent, submission, evidence, **options):
        return verify_deployment(intent, submission, evidence, now=options.pop('now', '2026-01-01T00:00:08Z'), **options)

    def test_replay_default_cannot_be_reported_as_a_live_game_result(self):
        intent, submission, evidence, _, _ = self.fixture()
        result = self.verify(intent, submission, evidence)
        self.assertEqual(result['status'], 'deployment_replay_verified')
        self.assertTrue(result['evidence_verified'])
        self.assertFalse(result['game_postcondition_verified'])
        self.assertFalse(result['blind_retry_allowed'])
        self.assertEqual(result['reasons'], [])
        evidence['source_mode'] = 'live_capture'
        result = self.verify(intent, submission, evidence, source_mode='live_capture')
        self.assertEqual(result['status'], 'deployment_verified')
        self.assertTrue(result['game_postcondition_verified'])

    def test_source_mode_cannot_be_silently_promoted_or_reused(self):
        intent, submission, evidence, post, selected = self.fixture()
        result = self.verify(intent, submission, evidence, source_mode='live_capture')
        self.assertIn('source_mode_mismatch', result['reasons'])
        undeclared = deepcopy(evidence); undeclared.pop('source_mode')
        self.assertIn('source_mode_mismatch', self.verify(intent, submission, undeclared, source_mode='live_capture')['reasons'])
        post.update(source_mode='saved_replay')
        with self.assertRaisesRegex(ValueError, 'mode_mismatch'):
            bind_inspected_evidence(intent, post, selected, inspection_target=[699, 523],
                                    shop_frame_sha256='b' * 64, source_mode='live_capture')
        evidence.update(source_mode='live_capture', source_capture_reused=True)
        self.assertIn('reused_frame_cannot_be_live', self.verify(intent, submission, evidence, source_mode='live_capture')['reasons'])
        with self.assertRaises(ValueError): self.verify(intent, submission, evidence, source_mode='auto')

    def test_intent_match_hero_and_purchased_offer_are_bound(self):
        original, submission, raw, _, _ = self.fixture()
        for key, value, reason in [('intent_sha256', '0' * 64, 'intent_binding'),
                                   ('match_id', 'different-match', 'match_binding'),
                                   ('hero_id', 'different-hero', 'hero_binding')]:
            evidence = deepcopy(raw); evidence[key] = value
            self.assertIn(reason, self.verify(original, submission, evidence)['reasons'])
        for field, value, reason in [('shop_sha256', 'e' * 64, 'purchased_shop_binding'),
                                     ('Slot', 1, 'target_unit_identity'), ('hero_id', 'other-hero', 'target_unit_identity')]:
            evidence = deepcopy(raw); evidence['unit'][field] = value
            self.assertIn(reason, self.verify(original, submission, evidence)['reasons'])
        changed = deepcopy(original); changed['destination'] = [711, 555]
        evidence = deepcopy(raw); evidence['intent_sha256'] = digest(changed)
        self.assertIn('invalid_intent', self.verify(changed, submission, evidence)['reasons'])

    def test_counts_alone_cannot_prove_hero_or_ownership(self):
        intent, submission, raw, _, _ = self.fixture()
        changes = [('Known', False, 'target_unit_identity'), ('Score', .91, 'target_unit_identity'),
                   ('Margin', .01, 'target_unit_ambiguity'), ('OtherScore', .97, 'target_unit_ambiguity'),
                   ('owner_score', .96, 'target_unit_ownership'), ('method', 'confirmed_world_model', 'target_unit_identity')]
        for field, value, reason in changes:
            evidence = deepcopy(raw); evidence['unit'][field] = value
            with self.subTest(field=field): self.assertIn(reason, self.verify(intent, submission, evidence)['reasons'])

    def test_preserved_hand_and_removed_card_constraints_are_independent(self):
        intent, submission, raw, _, _ = self.fixture()
        for section, field, value, reason in [('Passive', 'Score', .96, 'hand_preserved_passive'),
                ('Equipment', 'X', 800, 'hand_preserved_equipment'), ('Passive', 'Scale', .5, 'hand_preserved_passive')]:
            evidence = deepcopy(raw); evidence['hand'][section][field] = value
            self.assertIn(reason, self.verify(intent, submission, evidence)['reasons'])
        for field, value, reason in [('Known', 1, 'hand_transition'), ('AfterCount', True, 'hand_transition'),
                                     ('BeforePassiveHero', .75, 'hand_hero_removal')]:
            evidence = deepcopy(raw); evidence['hand'][field] = value
            self.assertIn(reason, self.verify(intent, submission, evidence)['reasons'])

    def test_population_and_inspection_must_use_the_same_new_frame(self):
        intent, submission, raw, _, _ = self.fixture()
        for field, value, reason in [('capacity', 3, 'board_transition'), ('before', False, 'board_transition'),
                                     ('frame_sha256', 'c' * 64, 'board_frame_binding'), ('one_score', .96, 'board_transition')]:
            evidence = deepcopy(raw); evidence['board'][field] = value
            self.assertIn(reason, self.verify(intent, submission, evidence)['reasons'])
        evidence = deepcopy(raw); evidence['identity_frame'] = deepcopy(evidence['post_frame'])
        self.assertIn('new_inspection_frame_required', self.verify(intent, submission, evidence)['reasons'])

    def test_component_bounds_and_inspection_target_are_not_waived_by_known(self):
        intent, submission, raw, _, _ = self.fixture()
        for key, value in [('X', 5), ('Pixels', 249), ('Pixels', 100000), ('Width', 181), ('CenterX', True)]:
            evidence = deepcopy(raw); evidence['new_unit'][key] = value
            self.assertIn('new_unit_at_drop', self.verify(intent, submission, evidence)['reasons'])
        evidence = deepcopy(raw); evidence['inspection_target'] = [700, 523]
        self.assertIn('inspection_target_binding', self.verify(intent, submission, evidence)['reasons'])

    def test_freshness_order_and_capture_hashes_are_strict(self):
        intent, submission, raw, _, _ = self.fixture()
        for frame, key, value, reason in [('post_frame', 'sha256', 'a' * 64, 'post_frame_new_capture'),
                ('identity_frame', 'sha256', 'z' * 64, 'identity_frame_new_capture'),
                ('identity_frame', 'identity_version', 'different', 'identity_frame_identity'),
                ('post_frame', 'captured_at', '2026-01-01T00:00:01Z', 'post_frame_order'),
                ('identity_frame', 'captured_at', '2026-01-01T00:00:06', 'identity_frame_timestamp')]:
            evidence = deepcopy(raw); evidence[frame][key] = value
            self.assertIn(reason, self.verify(intent, submission, evidence)['reasons'])
        result = self.verify(intent, submission, raw, now='2026-01-01T00:00:20Z')
        self.assertIn('identity_frame_stale', result['reasons'])
        self.assertIn('post_frame_stale', result['reasons'])
        delayed = deepcopy(submission); delayed['released_at'] = '2026-01-01T00:00:06Z'
        self.assertIn('submission_source_stale_or_out_of_order', self.verify(intent, delayed, raw)['reasons'])

    def test_uncertain_submission_or_owned_release_failure_cannot_verify(self):
        intent, original, evidence, _, _ = self.fixture()
        for key, value in [('sent', 1), ('owned_release_confirmed', False), ('cleanup_errors', ['failed']),
                           ('action_budget_remaining', 1), ('submission_outcome', 'drag_move_outcome_uncertain')]:
            submission = deepcopy(original); submission[key] = value
            result = self.verify(intent, submission, evidence)
            self.assertIn('unclean_submission', result['reasons']); self.assertFalse(result['game_postcondition_verified'])

    def test_malformed_and_nonfinite_evidence_rejects_without_native_fallback(self):
        intent, submission, raw, _, _ = self.fixture()
        for key in ('post_frame', 'identity_frame', 'hand', 'board', 'unit', 'new_unit'):
            evidence = deepcopy(raw); evidence[key] = None
            self.assertFalse(self.verify(intent, submission, evidence)['evidence_verified'])
        for value in (float('nan'), float('inf'), True, 1.1):
            evidence = deepcopy(raw); evidence['unit']['Score'] = value
            self.assertFalse(self.verify(intent, submission, evidence)['evidence_verified'])
        for value in (None, {}, {'source_capture_utc': 'bad'}):
            self.assertFalse(self.verify(value, submission, raw)['evidence_verified'])

    def test_binder_copies_evidence_and_requires_reviewed_geometry(self):
        intent, _, evidence, post, selected = self.fixture()
        post['deployment_pixels']['hand']['Known'] = False
        selected['deployment_detail']['Known'] = False
        self.assertTrue(evidence['hand']['Known']); self.assertTrue(evidence['unit']['Known'])
        selected['identity']['client']['width'] = 1920
        with self.assertRaisesRegex(ValueError, 'geometry'):
            bind_inspected_evidence(intent, post, selected, inspection_target=[699, 523], shop_frame_sha256='b' * 64)


if __name__ == '__main__': unittest.main()
