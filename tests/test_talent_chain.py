from copy import deepcopy
import unittest

from runtime.talent_chain import talent_layout, assess_selected_detail, stability_decision, verify_detail_return
import test_transition_verification as fixtures


class TalentChainTests(unittest.TestCase):
    def detail(self, sha='a', captured='2026-01-01T00:00:00Z', name='双人游'):
        frame = fixtures.phase_frame(sha, captured)
        frame['v14'] = {'anchors': []}
        ocr = {'name': fixtures.bundle(frame, [267, 415, 223, 40], name),
               'description': fixtures.bundle(frame, [267, 475, 223, 65], '随机获得2张2-3阶英雄牌。')}
        result = assess_selected_detail(frame, ocr, expected_name='双人游', effect_fragment='随机获得',
                                         now=captured)
        return frame, ocr, result

    def test_one_complete_family_is_required_instead_of_three_mixed_votes(self):
        frame, _, _ = self.detail()
        frame['v14']['anchors'] = [{'id': 'current_talent_footer_0', 'score': 1}, {'id': 'gold_talent_footer_1', 'score': 1}]
        fixtures.set_score(frame, 'talent_footer_3', 1)
        self.assertEqual(talent_layout(frame)['kind'], 'unknown')
        frame['v14']['anchors'] = [{'id': 'gold_talent_footer_' + str(i), 'score': 1} for i in range(3)]
        self.assertEqual(talent_layout(frame)['kind'], 'three_candidates')

    def test_missing_duplicate_and_nonfinite_footer_records_fail_closed(self):
        frame, _, _ = self.detail(); frame['matches'] = []
        self.assertEqual(talent_layout(frame)['kind'], 'unknown')
        frame, _, _ = self.detail(); frame['v14']['anchors'] = [{'id': 'x', 'score': float('nan')}]
        self.assertEqual(talent_layout(frame)['kind'], 'unknown')
        frame['v14']['anchors'] = [{'id': 'x', 'score': 1}, {'id': 'x', 'score': 1}]
        self.assertEqual(talent_layout(frame)['kind'], 'unknown')

    def test_animation_waits_and_exact_bound_name_effect_is_only_a_detail_candidate(self):
        _, _, unstable = self.detail(name=''); _, _, stable = self.detail('b', '2026-01-01T00:00:01Z')
        self.assertFalse(unstable['detail_matched']); self.assertTrue(stable['detail_matched'])
        self.assertFalse(stable['selection_commit_verified']); self.assertFalse(stable['rewards_verified'])
        self.assertEqual(stability_decision([unstable])['action'], 'wait_read_only')
        self.assertEqual(stability_decision([unstable, stable])['action'], 'detail_seen')

    def test_three_failed_captures_stop_without_reselect_or_unbounded_polling(self):
        rows = [self.detail(sha, '2026-01-01T00:00:0' + str(i) + 'Z', name='')[2] for i, sha in enumerate('abc')]
        result = stability_decision(rows)
        self.assertEqual(result['action'], 'stop_no_retry'); self.assertFalse(result['native_retry_allowed'])
        with self.assertRaises(ValueError): stability_decision(rows + [rows[-1]])
        with self.assertRaises(ValueError): stability_decision([rows[0], rows[0]])
        changed = deepcopy(rows[1]); changed['identity_version'] = 'another-game'
        with self.assertRaises(ValueError): stability_decision([rows[0], changed])

    def test_detail_ocr_frame_and_freshness_cannot_be_replaced_by_review_text(self):
        frame, ocr, _ = self.detail(); ocr['name']['ocr']['frame_sha256'] = 'f' * 64
        self.assertFalse(assess_selected_detail(frame, ocr, expected_name='双人游', effect_fragment='随机获得', now=frame['captured_at'])['detail_matched'])
        frame, ocr, _ = self.detail()
        self.assertFalse(assess_selected_detail(frame, ocr, expected_name='双人游', effect_fragment='随机获得', now='2026-01-01T00:00:09Z')['detail_matched'])

    def recovery(self):
        _, _, detail = self.detail()
        after = fixtures.phase_frame('b', '2026-01-01T00:00:20Z')
        after['v14'] = {'owner': 0, 'capacity': 1, 'counts': [{'value': 4, 'score': 1}], 'anchors': []}
        step = {'operation': 'dismiss_verified_selected_talent_detail', 'before': detail['frame_sha256'],
                'started_at': '2026-01-01T00:00:01Z', 'completed_at': '2026-01-01T00:00:01.1Z',
                'submission': {'sent': True, 'owned_release_confirmed': True, 'cleanup_errors': [],
                               'action_budget_remaining': 0, 'submission_outcome': 'down_and_owned_up_submitted'},
                'native_summary': {'held': False, 'release_confirmed': True, 'cleanup_errors': [], 'down_count': 2, 'owned_up_count': 1}}
        return detail, after, step

    def test_close_then_animation_recovery_preserves_deadline_and_deployment_boundary(self):
        detail, after, step = self.recovery()
        result = verify_detail_return(detail, after, step, expected_count=4, deadline_at='2026-01-01T00:01:00Z', now='2026-01-01T00:00:21Z')
        self.assertEqual(result['status'], 'talent_detail_return_replay_verified')
        self.assertFalse(result['game_postcondition_verified']); self.assertFalse(result['five_unit_verified'])
        self.assertFalse(result['native_retry_allowed'])
        result = verify_detail_return(detail, after, step, expected_count=4, deadline_at='2026-01-01T00:00:19Z', now='2026-01-01T00:00:21Z')
        self.assertFalse(result['evidence_verified'])
        step['native_summary']['held'] = True
        result = verify_detail_return(detail, after, step, expected_count=4, deadline_at='2026-01-01T00:01:00Z', now='2026-01-01T00:00:21Z')
        self.assertIn('talent_close_release_unproven', result['reasons'])


if __name__ == '__main__': unittest.main()
