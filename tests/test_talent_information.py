from copy import deepcopy
import unittest

from runtime.talent_information import (assess_information, information_still_current, bind_persistent_information,
                                       CENTER_TITLE_RECT, CENTER_DESCRIPTION_RECT, CENTER_PERSISTENT_NAME_RECT)
from runtime.talent_chain import assess_selected_detail
import test_transition_verification as fixtures


class TalentInformationTests(unittest.TestCase):
    def information(self):
        frame = fixtures.phase_frame('a', '2026-01-01T00:00:00Z')
        rects = {'name': [600, 280, 220, 40], 'description': [580, 340, 280, 120]}
        ocr = {key: fixtures.bundle(frame, rects[key], text) for key, text in
               [('name', 'Talent Example'), ('description', 'Receive two pieces of visible equipment.')]}
        args = dict(expected_name='Talent Example', effect_fragment='two pieces', now=frame['captured_at'],
                    name_rect=rects['name'], description_rect=rects['description'])
        return frame, ocr, args

    def current(self):
        frame, ocr, args = self.information(); bound = assess_information(frame, ocr, **args)
        current = fixtures.phase_frame('b', '2026-01-01T00:00:20Z')
        anchors = [{'field': key, 'reference_sha256': frame['sha256'], 'frame_sha256': current['sha256'],
                    'roi': bound[key + '_rect'], 'score': 1} for key in ('name', 'description')]
        options = dict(now='2026-01-01T00:00:21Z', deadline_at='2026-01-01T00:01:00Z')
        return bound, current, anchors, options

    def test_centered_preview_uses_actual_rectangles_without_claiming_selection(self):
        frame, ocr, args = self.information(); result = assess_information(frame, ocr, **args)
        self.assertTrue(result['information_matched']); self.assertFalse(result['selection_commit_verified'])
        self.assertFalse(result['rewards_verified']); self.assertFalse(result['execution_allowed'])

    def test_selected_summary_cannot_be_verified_with_preview_ocr_or_effect(self):
        frame, ocr, args = self.information()
        result = assess_selected_detail(frame, ocr, expected_name=args['expected_name'],
                                        effect_fragment=args['effect_fragment'], now=args['now'])
        self.assertFalse(result['detail_matched']); self.assertFalse(result['selection_commit_verified'])
        args['description_rect'] = [267, 475, 223, 65]
        self.assertFalse(assess_information(frame, ocr, **args)['information_matched'])

    def test_review_text_is_insufficient_without_bound_uncached_ocr_pixels(self):
        frame, ocr, args = self.information()
        for area, key, value in [('ocr', 'cache_hit', True), ('ocr', 'frame_sha256', 'f' * 64),
                                  ('roi', 'scale', 1), ('roi', 'pixel_sha256', 'f' * 64)]:
            changed = deepcopy(ocr); changed['description'][area][key] = value
            self.assertFalse(assess_information(frame, changed, **args)['information_matched'])
        self.assertFalse(assess_information(frame, ocr, **(args | {'now': '2026-01-01T00:00:09Z'}))['information_matched'])

    def test_malformed_outside_or_overlapping_rectangles_fail_closed(self):
        frame, ocr, args = self.information()
        for rect in ([600, 280, 220, 40], [1440, 340, 280, 120], [580, 340, 0, 120],
                     [580, 340, True, 120], [580, 340, 280], None):
            result = assess_information(frame, ocr, **(args | {'description_rect': rect}))
            self.assertFalse(result['information_matched'])

    def test_fresh_revalidation_requires_both_complete_comparisons(self):
        bound, current, anchors, options = self.current()
        result = information_still_current(bound, current, anchors, **options)
        self.assertTrue(result['information_current']); self.assertFalse(result['execution_allowed'])
        self.assertFalse(result['game_postcondition_verified']); self.assertFalse(result['native_retry_allowed'])
        for rows in ([], anchors[:1], [anchors[0], anchors[0]], anchors + anchors[:1], None):
            self.assertFalse(information_still_current(bound, current, rows, **options)['information_current'])

    def test_disappeared_overlay_changed_geometry_and_wrong_hash_stop_without_close(self):
        bound, current, anchors, options = self.current()
        for key, value in [('score', .96), ('score', float('nan')), ('roi', [600, 280, 221, 40]),
                           ('reference_sha256', 'f' * 64), ('frame_sha256', 'f' * 64)]:
            changed = deepcopy(anchors); changed[0][key] = value
            result = information_still_current(bound, current, changed, **options)
            self.assertFalse(result['information_current']); self.assertFalse(result['native_retry_allowed'])
        current['identity']['geometry_version'] = 'other-geometry'
        self.assertFalse(information_still_current(bound, current, anchors, **options)['information_current'])

    def test_stale_review_expired_deadline_or_saved_source_cannot_become_live(self):
        bound, current, anchors, options = self.current()
        for changes in ({'now': '2026-01-01T00:00:29Z'}, {'deadline_at': '2026-01-01T00:00:20Z'}):
            self.assertFalse(information_still_current(bound, current, anchors, **(options | changes))['information_current'])
        current['captured_at'] = '2026-01-01T00:01:01Z'
        self.assertFalse(information_still_current(bound, current, anchors, now=current['captured_at'],
                                                  deadline_at='2026-01-01T00:02:00Z')['information_current'])
        bound, current, anchors, options = self.current()
        self.assertFalse(information_still_current(bound, current, anchors, **options, source_mode='live_capture')['information_current'])

    def centered(self):
        frame = fixtures.phase_frame('a', '2026-01-01T00:00:00Z')
        ocr = {'name': fixtures.bundle(frame, CENTER_TITLE_RECT, '银算盘衍生卡'),
               'description': fixtures.bundle(frame, CENTER_DESCRIPTION_RECT, '每次出售英雄时随机提高等级。')}
        return assess_information(frame, ocr, expected_name='银算盘衍生卡', effect_fragment='每次出售英雄',
                                  name_rect=CENTER_TITLE_RECT, description_rect=CENTER_DESCRIPTION_RECT, now=frame['captured_at'])

    def test_full_title_identity_and_internal_persistent_regions_have_distinct_roles(self):
        identity = self.centered(); self.assertTrue(identity['information_matched'])
        bound = bind_persistent_information(identity)
        self.assertEqual(identity['name_rect'], CENTER_TITLE_RECT)
        self.assertEqual(bound['name_rect'], CENTER_PERSISTENT_NAME_RECT)
        self.assertEqual(bound['ocr_identity_regions']['name'], CENTER_TITLE_RECT)
        current = fixtures.phase_frame('b', '2026-01-01T00:00:20Z')
        anchors = [{'field': key, 'reference_sha256': bound['frame_sha256'], 'frame_sha256': current['sha256'],
                    'roi': bound[key + '_rect'], 'score': 1} for key in ('name', 'description')]
        result = information_still_current(bound, current, anchors, now=current['captured_at'], deadline_at='2026-01-01T00:01:00Z')
        self.assertTrue(result['information_current']); self.assertFalse(result['selection_commit_verified'])
        anchors[0]['score'] = .4099
        self.assertFalse(information_still_current(bound, current, anchors, now=current['captured_at'],
                                                   deadline_at='2026-01-01T00:01:00Z')['information_current'])

    def test_persistent_binding_cannot_skip_initial_identity_or_change_the_reviewed_geometry(self):
        identity = self.centered()
        for key, value in [('information_matched', False), ('name', '银算盘'), ('frame_sha256', '?'),
                           ('name_rect', [500, 45, 449, 50]), ('description_rect', [613, 467, 224, 75])]:
            with self.assertRaises(ValueError): bind_persistent_information(identity | {key: value})

    def test_wide_transient_title_is_allowed_only_at_its_exact_reviewed_rectangle(self):
        frame, ocr, args = self.information()
        self.assertFalse(assess_information(frame, ocr, **(args | {'name_rect': [600, 280, 450, 40]}))['information_matched'])


if __name__ == '__main__': unittest.main()
