"""Metadata gates only; bitmap checks have their own input-free C# runner."""
from copy import deepcopy
import unittest

from runtime.name_mask import assess_name_match, is_name_match, population_template_gate
import test_transition_verification as fixtures


class NameMaskTests(unittest.TestCase):
    def measurement(self):
        return {'Score': .99, 'Dx': 3, 'Dy': 0, 'ReferencePixels': 359, 'CurrentPixels': 511}

    def frames(self):
        return fixtures.phase_frame(), fixtures.phase_frame('b', '2026-01-01T00:00:03Z')

    def test_same_threshold_bounded_translation_and_density_are_required(self):
        self.assertTrue(is_name_match(self.measurement()))
        for key, value in [('Score', .969), ('Dx', 4), ('Dy', -4), ('Dx', True),
                           ('ReferencePixels', 39), ('CurrentPixels', 2016), ('Score', float('nan'))]:
            result = self.measurement(); result[key] = value
            with self.subTest(key=key): self.assertFalse(is_name_match(result))
        result = self.measurement(); result['Score'] = .97
        self.assertTrue(is_name_match(result))

    def test_high_score_alone_cannot_replace_full_component_measurement(self):
        self.assertFalse(is_name_match({'Score': 1}))
        self.assertFalse(is_name_match(None))
        result = self.measurement(); result['CurrentPixels'] = 0
        self.assertFalse(is_name_match(result))

    def test_read_only_candidate_is_not_ocr_ownership_or_input_permission(self):
        reference, current = self.frames()
        result = assess_name_match(reference, current, self.measurement(), now='2026-01-01T00:00:04Z')
        self.assertEqual(result['status'], 'name_mask_candidate')
        self.assertEqual(result['source_mode'], 'saved_replay')
        self.assertIsNone(result['name_text']); self.assertIsNone(result['hero_id'])
        self.assertFalse(result['ownership_verified']); self.assertFalse(result['execution_allowed'])
        self.assertFalse(result['game_postcondition_verified']); self.assertFalse(result['blind_retry_allowed'])

    def test_current_frame_must_be_new_fresh_and_correct_geometry(self):
        reference, current = self.frames()
        same = deepcopy(current); same['sha256'] = reference['sha256']
        self.assertIn('distinct_current_frame_required', assess_name_match(reference, same, self.measurement(), now='2026-01-01T00:00:04Z')['reasons'])
        self.assertIn('name_frame_stale_or_future', assess_name_match(reference, current, self.measurement(), now='2026-01-01T00:00:09Z')['reasons'])
        current['identity']['client']['height'] = 1080
        self.assertIn('invalid_name_frame_binding', assess_name_match(reference, current, self.measurement(), now='2026-01-01T00:00:04Z')['reasons'])

    def test_source_mode_and_mutable_result_are_not_silently_promoted(self):
        reference, current = self.frames(); current['source_mode'] = 'saved_replay'; measurement = self.measurement()
        self.assertIn('source_mode_mismatch', assess_name_match(reference, current, measurement, now='2026-01-01T00:00:04Z', source_mode='live_capture')['reasons'])
        result = assess_name_match(reference, current, measurement, now='2026-01-01T00:00:04Z')
        measurement['Score'] = 0; self.assertEqual(result['measurement']['Score'], .99)
        current.update(source_mode='live_capture', source_capture_reused=True)
        self.assertIn('reused_frame_cannot_be_live', assess_name_match(reference, current, self.measurement(), now='2026-01-01T00:00:04Z', source_mode='live_capture')['reasons'])

    def test_population_requires_correct_winner_margin_and_capacity(self):
        rows = [{'value': 1, 'score': .50}, {'value': 2, 'score': 1}, {'value': 3, 'score': .86}]
        self.assertTrue(population_template_gate(rows, expected_count=2, capacity_score=1))
        self.assertFalse(population_template_gate(rows, expected_count=1, capacity_score=1))
        rows[-1]['score'] = .99
        self.assertFalse(population_template_gate(rows, expected_count=2, capacity_score=1))
        self.assertFalse(population_template_gate(rows, expected_count=2, capacity_score=.96))

    def test_fifth_population_preserves_thresholds_and_sixth_stays_out_of_scope(self):
        rows = [{'value': 5, 'score': 1}, {'value': 4, 'score': .8}]
        self.assertTrue(population_template_gate(rows, expected_count=5, capacity_score=1))
        for count in (6, True, -1):
            self.assertFalse(population_template_gate(rows, expected_count=count, capacity_score=1))
        rows[1]['score'] = .99
        self.assertFalse(population_template_gate(rows, expected_count=5, capacity_score=1))

    def test_shop_occlusion_is_not_waived_by_a_successful_name_or_hand_match(self):
        self.assertTrue(is_name_match(dict(self.measurement(), Score=1)))
        rows = [{'value': 2, 'score': .8924205378973105}]
        self.assertFalse(population_template_gate(rows, expected_count=2, capacity_score=.9408502772643254))
        # A prior high count is a different observation, not the current frame.
        self.assertTrue(population_template_gate([{'value': 2, 'score': 1}], expected_count=2, capacity_score=1))

    def test_malformed_population_and_frame_metadata_rejects(self):
        for rows in (None, [], [{'value': True, 'score': 1}], [{'value': 2, 'score': float('inf')}],
                     [{'value': 2, 'score': 1}, {'value': 2, 'score': .9}]):
            self.assertFalse(population_template_gate(rows, expected_count=2, capacity_score=1))
        result = assess_name_match(None, None, None, now='bad')
        self.assertNotEqual(result['status'], 'name_mask_candidate')
        reference, current = self.frames()
        with self.assertRaises(ValueError): assess_name_match(reference, current, self.measurement(), now='2026-01-01T00:00:04Z', source_mode='auto')


if __name__ == '__main__': unittest.main()
