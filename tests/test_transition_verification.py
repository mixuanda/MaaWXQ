"""Synthetic and malformed evidence only; no Windows or game operations."""
from copy import deepcopy
import unittest

from runtime.phase_perception import classify
from runtime.transition_verification import (
    READY_REGIONS, TALENT_REGIONS, digest, make_ready_intent, make_talent_intent,
    verify_ready, verify_talent,
)


def phase_frame(sha='a', captured='2026-01-01T00:00:00Z'):
    scores = dict.fromkeys(['phase_ready', 'phase_start', 'own_portrait', 'one_unit', 'battle_labels',
                           'battle_header', 'draft_preview'] + ['price_' + str(i) for i in range(4)]
                          + ['draft_bot_' + str(i) for i in range(1, 6)]
                          + ['talent_footer_' + str(i) for i in range(1, 4)], 0)
    scores.update(phase_ready=1, phase_start=.94, own_portrait=1, one_unit=1, price_0=1, price_1=1)
    return {'sha256': sha * 64, 'captured_at': captured,
            'identity': {'identity_version': 'fixture-identity', 'geometry_version': 'fixture-geometry',
                         'client': {'width': 1450, 'height': 869}},
            'matches': [{'name': name, 'score': score} for name, score in scores.items()]}


def set_score(frame, name, score):
    next(row for row in frame['matches'] if row['name'] == name)['score'] = score


def bundle(frame, rect, text):
    return {'roi': {'kind': 'in_memory_bgra8', 'source_sha256': frame['sha256'], 'source_rect': rect,
                    'pixel_sha256': 'e' * 64, 'scale': 3},
            'ocr': {'status': 'recognized', 'frame_sha256': frame['sha256'], 'pixel_sha256': 'e' * 64,
                    'text': text, 'cache_hit': False}}


def ready_ocr(frame, button='取消', round_text='第4回合'):
    return {'round': bundle(frame, READY_REGIONS['round'], round_text),
            'ready_button': bundle(frame, READY_REGIONS['ready_button'], button)}


class TransitionVerificationTests(unittest.TestCase):
    def ready(self):
        before = phase_frame(); after = phase_frame('b', '2026-01-01T00:00:03Z')
        intent = make_ready_intent(before, match_id='fixture-match', ocr=ready_ocr(before, '准备'))
        return before, after, intent, self.arguments(intent, ready_ocr(after))

    def arguments(self, intent, ocr):
        return {'intent_sha256': digest(intent), 'ocr': ocr,
                'submission': {'sent': True, 'owned_release_confirmed': True, 'cleanup_errors': [],
                               'action_budget_remaining': 0, 'submission_outcome': 'down_and_owned_up_submitted'},
                'native': {'down_count': 2, 'owned_up_count': 1, 'held': False,
                           'release_confirmed': True, 'cleanup_errors': []},
                'started_at': '2026-01-01T00:00:01Z', 'now': '2026-01-01T00:00:05Z'}

    def talent(self):
        before = phase_frame(); after = phase_frame('b', '2026-01-01T00:00:03Z')
        rows = [{'name': prefix + str(i), 'score': 1} for i in range(3) for prefix in ('name_', 'description_')]
        before['matches'] = deepcopy(rows); after['matches'] = deepcopy(rows); after['matches'][0]['score'] = .4
        candidates = [{'name': '防御领域', 'description': '己方每次受到的伤害减少2点。'},
                      {'name': '其他候选甲', 'description': '效果有未确认条件。'},
                      {'name': '其他候选乙', 'description': '装备适用范围尚未确认。'}]
        intent = make_talent_intent(before, match_id='fixture-match', candidates=candidates, selected_index=0,
                                    verification_fragment='伤害减少2点')
        ocr = {'selected_name': bundle(after, TALENT_REGIONS['selected_name'], '防 御 领 域'),
               'selected_description': bundle(after, TALENT_REGIONS['selected_description'], '己方每次受到的伤害减少2点。')}
        return before, after, intent, self.arguments(intent, ocr)

    def test_phase_recognition_has_positive_preparation_combat_draft_and_talent_paths(self):
        frame = phase_frame(); self.assertEqual(classify(frame)['phase'], 'preparation')
        set_score(frame, 'phase_ready', .3); set_score(frame, 'battle_labels', .99); set_score(frame, 'battle_header', .98)
        self.assertEqual(classify(frame)['phase'], 'battle_or_resolution')
        set_score(frame, 'battle_header', .2); frame['enemy_health_bars'] = 1
        self.assertEqual(classify(frame)['evidence'], 'enemy_health_bars')
        frame['enemy_health_bars'] = 0; set_score(frame, 'draft_preview', .99)
        set_score(frame, 'draft_bot_1', 1); set_score(frame, 'draft_bot_2', 1)
        self.assertEqual(classify(frame)['phase'], 'draft_preview')
        set_score(frame, 'draft_preview', .2)
        for i in range(1, 4): set_score(frame, 'talent_footer_' + str(i), .99)
        self.assertEqual(classify(frame)['phase'], 'talent_selection')

    def test_missing_duplicate_or_nonfinite_phase_anchors_are_unknown(self):
        for change in ('missing', 'duplicate', 'nan', 'out_of_range', 'boolean'):
            frame = phase_frame()
            if change == 'missing': frame['matches'].pop()
            elif change == 'duplicate': frame['matches'].append(deepcopy(frame['matches'][0]))
            else: frame['matches'][0]['score'] = {'nan': float('nan'), 'out_of_range': 1.1, 'boolean': True}[change]
            with self.subTest(change=change): self.assertEqual(classify(frame)['phase'], 'unknown')

    def test_cancel_replay_and_explicit_live_result_are_separate(self):
        _, after, intent, args = self.ready()
        result = verify_ready(intent, after, **args)
        self.assertEqual(result['status'], 'ready_replay_verified'); self.assertTrue(result['evidence_verified'])
        self.assertEqual(result['method'], 'same_round_cancel_control')
        self.assertFalse(result['game_postcondition_verified']); self.assertFalse(result['blind_retry_allowed'])
        result = verify_ready(intent, after, **args, source_mode='live_capture')
        self.assertIn('source_mode_mismatch', result['reasons'])
        intent['source_mode'] = 'live_capture'; args['intent_sha256'] = digest(intent)
        result = verify_ready(intent, after, **args, source_mode='live_capture')
        self.assertEqual(result['status'], 'ready_verified'); self.assertTrue(result['game_postcondition_verified'])

    def test_combat_requires_positive_anchors_and_same_round(self):
        _, after, intent, args = self.ready()
        set_score(after, 'phase_ready', .3); set_score(after, 'battle_labels', .99); set_score(after, 'battle_header', .99)
        args['ocr'] = ready_ocr(after, '')
        self.assertEqual(verify_ready(intent, after, **args)['method'], 'same_round_combat')
        args['ocr'] = ready_ocr(after, '', '第5回合')
        self.assertFalse(verify_ready(intent, after, **args)['evidence_verified'])
        args['ocr'] = ready_ocr(after, ''); set_score(after, 'own_portrait', .98)
        self.assertFalse(verify_ready(intent, after, **args)['evidence_verified'])

    def test_intent_creation_rejects_cancel_unknown_round_and_missing_deployed_unit(self):
        for button, round_text in [('取消', '第4回合'), ('准备', '4'), ('unknown', '第4回合')]:
            frame = phase_frame()
            with self.assertRaises(ValueError): make_ready_intent(frame, match_id='fixture-match', ocr=ready_ocr(frame, button, round_text))
        frame = phase_frame(); set_score(frame, 'one_unit', .96)
        with self.assertRaises(ValueError): make_ready_intent(frame, match_id='fixture-match', ocr=ready_ocr(frame, '准备'))

    def test_unchanged_button_or_unknown_scene_never_verifies(self):
        _, after, intent, args = self.ready(); args['ocr'] = ready_ocr(after, '准备')
        self.assertIn('ready_postcondition', verify_ready(intent, after, **args)['reasons'])
        args['ocr'] = ready_ocr(after); after['matches'] = []
        self.assertIn('ready_postcondition', verify_ready(intent, after, **args)['reasons'])

    def test_ocr_requires_exact_frame_pixel_roi_scale_and_uncached_output(self):
        _, after, intent, original = self.ready()
        changes = [('roi', 'source_sha256', 'f' * 64), ('ocr', 'frame_sha256', 'f' * 64),
                   ('ocr', 'pixel_sha256', 'f' * 64), ('ocr', 'cache_hit', True),
                   ('roi', 'source_rect', [678, 7, 61, 30]), ('roi', 'scale', 2), ('ocr', 'text', None)]
        for section, field, value in changes:
            args = deepcopy(original); args['ocr']['round'][section][field] = value
            with self.subTest(field=field): self.assertIn('ready_ocr_binding', verify_ready(intent, after, **args)['reasons'])

    def test_binding_and_freshness_reject_reused_other_window_future_and_stale_frames(self):
        _, original, intent, args = self.ready()
        for key, value, reason in [('sha256', 'a' * 64, 'new_after_capture_required'),
                                   ('captured_at', '2026-01-01T00:00:06Z', 'post_frame_freshness'),
                                   ('captured_at', '2026-01-01T00:00:03', 'transition_timestamp')]:
            after = deepcopy(original); after[key] = value
            self.assertIn(reason, verify_ready(intent, after, **args)['reasons'])
        after = deepcopy(original); after['identity']['geometry_version'] = 'changed'
        self.assertIn('window_binding', verify_ready(intent, after, **args)['reasons'])
        self.assertIn('post_frame_freshness', verify_ready(intent, original, **(args | {'now': '2026-01-01T00:00:12Z'}))['reasons'])
        self.assertIn('source_freshness', verify_ready(intent, original, **(args | {'started_at': '2026-01-01T00:00:06Z'}))['reasons'])

    def test_uncertain_submission_and_unowned_or_failed_release_are_rejected(self):
        _, after, intent, original = self.ready()
        changes = [('submission', 'sent', 1), ('submission', 'action_budget_remaining', 1),
                   ('submission', 'submission_outcome', 'uncertain'), ('native', 'held', True),
                   ('native', 'release_confirmed', False), ('native', 'cleanup_errors', ['failed']),
                   ('native', 'owned_up_count', True), ('native', 'down_count', 1)]
        for section, field, value in changes:
            args = deepcopy(original); args[section][field] = value
            self.assertFalse(verify_ready(intent, after, **args)['evidence_verified'])

    def test_modified_intent_and_reused_live_frame_are_rejected(self):
        _, after, intent, args = self.ready(); changed = deepcopy(intent); changed['match_id'] = 'another-match'
        self.assertIn('intent_binding', verify_ready(changed, after, **args)['reasons'])
        intent['source_mode'] = 'live_capture'; args['intent_sha256'] = digest(intent); after['source_capture_reused'] = True
        self.assertIn('reused_frame_cannot_be_live', verify_ready(intent, after, **args, source_mode='live_capture')['reasons'])

    def test_talent_detail_replay_confirms_selection_but_never_reward_delivery(self):
        _, after, intent, args = self.talent(); result = verify_talent(intent, after, **args)
        self.assertEqual(result['status'], 'talent_selection_replay_verified'); self.assertTrue(result['evidence_verified'])
        self.assertFalse(result['game_postcondition_verified']); self.assertFalse(result['rewards_verified'])
        self.assertFalse(result['future_effects_verified']); self.assertFalse(result['blind_retry_allowed'])
        intent['source_mode'] = 'live_capture'; args['intent_sha256'] = digest(intent)
        result = verify_talent(intent, after, **args, source_mode='live_capture')
        self.assertEqual(result['status'], 'talent_selection_verified'); self.assertTrue(result['game_postcondition_verified'])
        self.assertFalse(result['rewards_verified'])

    def test_talent_candidates_must_be_readable_distinct_and_copied(self):
        before, _, intent, _ = self.talent(); candidates = deepcopy(intent['details']['candidates'])
        retained = make_talent_intent(before, match_id='fixture-match', candidates=candidates,
                                      selected_index=0, verification_fragment='伤害减少2点')
        candidates[0]['name'] = 'changed'; self.assertEqual(retained['details']['candidates'][0]['name'], '防御领域')
        for selected, fragment in [(True, '伤害减少2点'), (3, '伤害减少2点'), (0, 'unseen description')]:
            with self.assertRaises(ValueError): make_talent_intent(before, match_id='fixture-match', candidates=deepcopy(intent['details']['candidates']),
                                                                  selected_index=selected, verification_fragment=fragment)
        candidates = deepcopy(intent['details']['candidates']); candidates[1]['name'] = candidates[0]['name']
        with self.assertRaises(ValueError): make_talent_intent(before, match_id='fixture-match', candidates=candidates,
                                                              selected_index=0, verification_fragment='伤害减少2点')

    def test_missing_or_unchanged_talent_layout_cannot_prove_selection(self):
        before, after, intent, args = self.talent()
        for rows in (before['matches'], [], [dict(name='name_0', score=.1)] * 6):
            altered = deepcopy(after); altered['matches'] = deepcopy(rows)
            self.assertIn('three_candidate_layout_not_removed', verify_talent(intent, altered, **args)['reasons'])
        altered = deepcopy(after); altered['matches'][0]['score'] = float('nan')
        self.assertFalse(verify_talent(intent, altered, **args)['evidence_verified'])

    def test_talent_requires_exact_selected_name_fragment_and_bound_ocr(self):
        _, after, intent, original = self.talent()
        for key, text in [('selected_name', '其他候选甲'), ('selected_description', 'not the selected description')]:
            args = deepcopy(original); args['ocr'][key]['ocr']['text'] = text
            self.assertIn('selected_talent_detail', verify_talent(intent, after, **args)['reasons'])
        args = deepcopy(original); args['ocr']['selected_name']['ocr']['cache_hit'] = True
        self.assertIn('talent_ocr_binding', verify_talent(intent, after, **args)['reasons'])

    def test_malformed_records_fail_without_fallback_or_input(self):
        _, after, _, args = self.ready()
        for intent in (None, {}, {'source_frame': None}, {'source_mode': float('nan')}):
            self.assertFalse(verify_ready(intent, after, **args)['evidence_verified'])
        _, after, intent, args = self.talent()
        self.assertIn('transition_timestamp', verify_talent(intent, after, **(args | {'now': 'bad'}))['reasons'])
        with self.assertRaises(ValueError): verify_talent(intent, after, **args, source_mode='auto')


if __name__ == '__main__': unittest.main()
