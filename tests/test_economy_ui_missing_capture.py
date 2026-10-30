"""Synthetic parser regressions; no capture or native input is opened."""
import unittest

from runtime.economy_ui import EconomyUI


class EconomyUIMissingCaptureTests(unittest.TestCase):
    def parse(self, *, current='4', target='5', quote='2', upgrade='', score=1,
              bound=True):
        reader = EconomyUI.__new__(EconomyUI)
        scalar = {'pattern': r'(?:unknown|(?P<value>\d{1,2}))',
                  'anchor_id': 'reviewed', 'semantic_source': 'synthetic reviewed level'}
        button = {'enabled_anchor_id': 'reviewed', 'rect': [0, 0, 20, 20], 'target': [10, 10]}
        reader.profile = {
            'reference': 'synthetic-only',
            'scalar_readers': {'player_level': dict(scalar), 'level_up_target_level': dict(scalar)},
            'quote_readers': {
                'refresh_cost': {'pattern': r'(?:unknown|(?P<value>\d{1,3}))',
                                 'text_key': 'price', 'anchor_id': 'reviewed',
                                 'semantic_source': 'synthetic reviewed quote'}},
            'actions': {'paid_refresh': dict(button), 'level_up': dict(button)},
        }
        frame = {'sha256': 'synthetic-frame', 'captured_at': 'synthetic-time',
                 'identity': {'identity_version': 'synthetic-window', 'geometry_version': 'synthetic-geometry'},
                 'v14': {'anchors': [{'id': 'reviewed', 'score': score},
                                     {'id': 'economy_upgrade_label', 'score': score}]}}
        text = {'frame_sha256': frame['sha256'] if bound else 'other-frame',
                'captured_at': frame['captured_at'],
                'values': {'player_level': current, 'level_up_target_level': target,
                           'price': quote, 'upgrade_button': upgrade}}
        return reader.parse(frame, text)

    def test_missing_optional_scalar_capture_is_unknown_and_cannot_upgrade(self):
        for field in ('current', 'target'):
            with self.subTest(field=field):
                result = self.parse(**{field: 'unknown'}, upgrade='8升级')
                self.assertNotIn('player_level' if field == 'current' else 'level_up_target_level', result)
                self.assertNotIn('level_up', result['actions'])

    def test_missing_optional_quote_capture_is_unknown_and_cannot_refresh(self):
        result = self.parse(quote='unknown')
        self.assertNotIn('refresh_cost', result)
        self.assertNotIn('refresh', result['actions'])

    def test_legacy_upgrade_requires_strictly_increasing_target(self):
        for target in ('3', '4'):
            with self.subTest(target=target):
                result = self.parse(target=target, upgrade='8升级')
                self.assertEqual(result['level_up_cost']['value'], 8)
                self.assertNotIn('level_up', result['actions'])

    def test_valid_captures_keep_paid_refresh_and_legacy_upgrade(self):
        result = self.parse(upgrade='8升级')
        self.assertEqual(result['player_level']['value'], 4)
        self.assertEqual(result['level_up_target_level']['value'], 5)
        self.assertEqual(result['refresh_cost']['value'], 2)
        self.assertEqual(set(result['actions']), {'refresh', 'level_up'})

    def test_existing_anchor_and_frame_gates_remain_closed(self):
        result = self.parse(score=.96, upgrade='8升级')
        self.assertEqual(result['actions'], {})
        self.assertNotIn('player_level', result)
        self.assertNotIn('refresh_cost', result)
        result = self.parse(bound=False, upgrade='8升级')
        self.assertEqual(result, {'actions': {}, 'reason': 'current_OCR_frame_binding_required'})


if __name__ == '__main__':
    unittest.main()
