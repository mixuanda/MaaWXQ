"""Synthetic army measurements and review bytes; no live input or capture."""
from copy import deepcopy
import hashlib
import json
import unittest

from runtime.army_perception import assess_army_frame, bind_roster_review, hand_match_candidate
import test_transition_verification as transition_fixtures


class ArmyPerceptionTests(unittest.TestCase):
    def hand(self):
        return {'Known': True, 'Score': .98, 'Margin': .98, 'Scale': 1,
                'X': 735, 'Y': 794, 'Width': 24, 'Height': 38}

    def frame(self):
        frame = transition_fixtures.phase_frame()
        frame['army'] = {'hand': self.hand(), 'population': 1, 'capacity': 1, 'empty': .99}
        return frame

    def assess(self, frame, **options):
        return assess_army_frame(frame, reference_sha256s=options.pop('reference_sha256s',
                                {'hand': 'b' * 64, 'board': 'c' * 64, 'population': 'd' * 64}),
                                now=options.pop('now', '2026-01-01T00:00:01Z'), **options)

    def review(self):
        image = b'synthetic-original-image-bytes'
        review = {'sha256': hashlib.sha256(image).hexdigest(), 'method': 'assistant_visual_image_review',
                  'source': 'private-review-image.png', 'evidence_receipt': 'private-receipt.json',
                  'automatic_status_preserved': 'unit_identity_unverified_no_retry',
                  'population_before': 1, 'population_after': 2, 'capacity': 5,
                  'confirmed_name': 'fixture-second-hero', 'known_roster': ['fixture-first-hero', 'fixture-second-hero']}
        return review, image

    def test_hand_match_retains_only_a_bounded_fingerprint_candidate(self):
        result = hand_match_candidate(self.hand())
        self.assertEqual(result['center'], [747, 813])
        self.assertIsNone(result['hero_id']); self.assertFalse(result['ownership_verified'])

    def test_known_flag_does_not_waive_score_margin_geometry_or_scale(self):
        changes = [('Known', 1), ('Score', .93), ('Margin', .09), ('Score', float('nan')),
                   ('Scale', .91), ('Width', 25), ('Height', 39), ('X', 200), ('Y', 850), ('X', 735.0)]
        for key, value in changes:
            hand = self.hand(); hand[key] = value
            with self.subTest(key=key): self.assertIsNone(hand_match_candidate(hand))

    def test_template_similarity_one_is_not_population_or_capacity_one(self):
        result = self.assess(self.frame())
        self.assertEqual(result['status'], 'army_perception_candidate')
        self.assertEqual(result['template_similarities']['population'], 1)
        self.assertIsNone(result['population_value']); self.assertIsNone(result['capacity_value'])
        self.assertFalse(result['roster_verified']); self.assertFalse(result['execution_allowed'])
        self.assertFalse(result['game_postcondition_verified']); self.assertFalse(result['blind_retry_allowed'])

    def test_frame_time_geometry_and_reference_provenance_are_required(self):
        self.assertIn('army_frame_stale_or_future', self.assess(self.frame(), now='2026-01-01T00:00:06Z')['reasons'])
        frame = self.frame(); frame['identity']['client']['width'] = 1920
        self.assertIn('invalid_army_frame_binding', self.assess(frame)['reasons'])
        self.assertIn('bound_template_reference_hashes_required', self.assess(self.frame(), reference_sha256s={})['reasons'])
        frame = self.frame(); frame['captured_at'] = 'not-a-time'
        self.assertIn('invalid_army_capture_time', self.assess(frame)['reasons'])

    def test_unknown_overlay_and_nonfinite_similarities_do_not_enable_a_candidate(self):
        frame = self.frame(); frame['matches'] = []
        self.assertIn('positive_preparation_required', self.assess(frame)['reasons'])
        for value in (float('inf'), 3, True, None, .96):
            frame = self.frame(); frame['army']['population'] = value
            self.assertIn('empty_cell_or_population_template_unproven', self.assess(frame)['reasons'])

    def test_live_mode_never_produces_an_input_intent_or_accepts_reused_capture(self):
        frame = self.frame(); frame['source_mode'] = 'saved_replay'
        self.assertIn('source_mode_mismatch', self.assess(frame, source_mode='live_capture')['reasons'])
        frame['source_mode'] = 'live_capture'; result = self.assess(frame, source_mode='live_capture')
        self.assertFalse(result['execution_allowed']); self.assertFalse(result['game_postcondition_verified'])
        frame['source_capture_reused'] = True
        self.assertIn('reused_frame_cannot_be_live', self.assess(frame, source_mode='live_capture')['reasons'])
        with self.assertRaises(ValueError): self.assess(frame, source_mode='auto')

    def test_bound_visual_review_retains_failed_automatic_status_and_omits_paths(self):
        review, image = self.review(); result = bind_roster_review(review, image)
        self.assertEqual(result['status'], 'retained_visual_review_bound')
        self.assertEqual(result['original_automatic_status'], 'unit_identity_unverified_no_retry')
        self.assertFalse(result['execution_allowed']); self.assertFalse(result['game_postcondition_verified'])
        text = json.dumps(result)
        self.assertNotIn(review['source'], text); self.assertNotIn(review['evidence_receipt'], text)
        result['known_roster'].clear(); self.assertEqual(len(review['known_roster']), 2)

    def test_missing_original_cannot_be_reconstructed_from_its_digest(self):
        review, image = self.review(); result = bind_roster_review(review, None)
        self.assertEqual(result['status'], 'review_source_unavailable')
        self.assertIn('original_review_image_unavailable', result['reasons'])
        self.assertEqual(result['image_sha256'], review['sha256'])
        self.assertFalse(result['game_postcondition_verified'])
        result = bind_roster_review(review, b'changed')
        self.assertIn('original_review_image_changed', result['reasons'])
        self.assertFalse(result['original_image_available'])

    def test_review_count_capacity_name_and_original_status_are_independent(self):
        original, image = self.review()
        for key, value in [('capacity', 3), ('population_after', True), ('population_before', 0),
                           ('known_roster', ['duplicate', 'duplicate']), ('confirmed_name', 'unseen'),
                           ('automatic_status_preserved', 'deployment_verified')]:
            review = deepcopy(original); review[key] = value
            self.assertNotEqual(bind_roster_review(review, image)['status'], 'retained_visual_review_bound')
        review = deepcopy(original); review.pop('automatic_status_preserved')
        review['original_status'] = 'unit_identity_verified_population_requires_review'
        self.assertEqual(bind_roster_review(review, image)['original_automatic_status'], review['original_status'])

    def test_malformed_measurements_and_reviews_fail_without_a_native_fallback(self):
        self.assertIsNone(hand_match_candidate(None))
        self.assertEqual(self.assess(None)['status'], 'army_perception_unknown')
        for review, image in ((None, None), ({}, b'bytes'), ({'sha256': 'z' * 64}, b'bytes')):
            self.assertFalse(bind_roster_review(review, image)['game_postcondition_verified'])


if __name__ == '__main__': unittest.main()
