from copy import deepcopy
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import hashlib
import json
import unittest

from runtime.chain_guards import ChainBudget, empty_room_pair
from runtime.deployment_postcondition import digest
from runtime.lobby import recognize, decide


class ChainGuardTests(unittest.TestCase):
    def room(self, sha='a', captured='2026-01-01T00:00:00Z'):
        names = ['lobby_title', 'ai_settings', 'start_game', 'empty_slot_robot'] + ['empty_' + str(i) for i in range(1, 6)]
        return {'layout': 'custom_lobby_bot_menu', 'sha256': sha * 64, 'captured_at': captured,
                'identity': {'identity_version': 'fixture-game', 'geometry_version': 'fixture-geometry'},
                'matches': [{'name': name, 'score': 1, 'center': [3, 4]} for name in names]}

    def test_current_guest_overrides_old_empty_proof_and_never_authorizes_input(self):
        before = self.room(); current = self.room('b', '2026-01-01T00:00:02Z')
        self.assertTrue(empty_room_pair(before, current, now='2026-01-01T00:00:03Z')['empty_room_evidence_verified'])
        next(row for row in current['matches'] if row['name'] == 'empty_1')['score'] = .012
        current['other_humans_verified_absent'] = True
        result = empty_room_pair(before, current, now='2026-01-01T00:00:03Z')
        self.assertFalse(result['empty_room_evidence_verified']); self.assertFalse(result['automatic_retry_allowed'])
        self.assertFalse(result['execution_allowed']); self.assertEqual(decide(recognize(current))['action'], 'stop')

    def test_later_empty_image_does_not_resume_refused_pair(self):
        before = self.room(); next(row for row in before['matches'] if row['name'] == 'empty_1')['score'] = 0
        later = self.room('b', '2026-01-01T00:00:02Z')
        self.assertEqual(empty_room_pair(before, later, now='2026-01-01T00:00:03Z')['status'], 'room_refused_no_retry')
        self.assertFalse(empty_room_pair(self.room(), later, now='2026-01-01T00:00:08Z')['empty_room_evidence_verified'])

    def test_room_binding_unknown_duplicate_and_changed_window_are_rejected(self):
        before = self.room(); current = self.room('b', '2026-01-01T00:00:02Z')
        current['identity']['identity_version'] = 'other-game'
        self.assertIn('room_window_changed', empty_room_pair(before, current, now='2026-01-01T00:00:03Z')['reasons'])
        current = self.room('b', '2026-01-01T00:00:02Z'); current['matches'].append(deepcopy(current['matches'][0]))
        self.assertFalse(empty_room_pair(before, current, now='2026-01-01T00:00:03Z')['empty_room_evidence_verified'])

    def test_existing_lobby_runner_never_constructs_native_broker_after_guest_joins(self):
        from runtime import lobby_setup
        before = self.room(); joined = self.room('b', '2026-01-01T00:00:02Z')
        next(row for row in joined['matches'] if row['name'] == 'empty_1')['score'] = .012
        row = {'hwnd': 1, 'pid': 2, 'title': 'fixture-game', 'class_name': 'UnityWndClass',
               'executable_path': r'C:\Synthetic\WXQ.exe', 'process_security': {'integrity_rid': 8192}}
        security = {'known': True, 'app_container': False, 'ui_access': False, 'elevated': False, 'integrity_rid': 8192}
        with TemporaryDirectory() as directory:
            root = Path(directory); reference = root / 'reference.bin'; reference.write_bytes(b'fixture reference')
            profile = root / 'profile.json'; profile.write_text(json.dumps({key: row[key] for key in ('title', 'class_name', 'executable_path')}))
            with patch.object(lobby_setup, 'process_security', return_value=security), patch.object(lobby_setup, 'find_windows', return_value=[row]), \
                 patch.object(lobby_setup, 'inspect_game', return_value=row), patch.object(lobby_setup, 'ensure_capture_capacity', return_value={}), \
                 patch.object(lobby_setup, 'capture', side_effect=[before, joined]), patch.object(lobby_setup, 'GameClickBroker') as broker:
                result = lobby_setup.run(root / 'run', reference, hashlib.sha256(reference.read_bytes()).hexdigest(), profile, True, False, 'custom_lobby_bot_menu')
            self.assertFalse(result['input_attempted']); self.assertEqual(result['error'], 'empty_custom_lobby_not_verified')
            broker.assert_not_called()

    def budget(self):
        return ChainBudget('fixture-scope', '2026-01-01T00:00:00Z', '2026-01-01T00:05:00Z', max_captures=3, max_bytes=1000, max_native_attempts=2)

    def test_resume_retains_counters_original_deadline_and_failed_attempt_charge(self):
        budget = self.budget().charge(now='2026-01-01T00:00:01Z', native_attempts=1)
        snapshot = budget.snapshot()
        resumed = ChainBudget.restore(snapshot, expected_sha256=digest(snapshot), now='2026-01-01T00:01:00Z')
        self.assertEqual(resumed.native_attempts, 1); self.assertEqual(resumed.deadline_at, budget.deadline_at)
        used = resumed.charge(now='2026-01-01T00:01:01Z', native_attempts=1)
        with self.assertRaises(ValueError): used.charge(now='2026-01-01T00:01:02Z', native_attempts=1)
        snapshot['native_attempts'] = 0
        with self.assertRaises(ValueError): ChainBudget.restore(snapshot, expected_sha256=digest(budget.snapshot()), now='2026-01-01T00:01:00Z')

    def test_capture_deletion_cannot_credit_budget_and_limits_cannot_expand(self):
        budget = self.budget().charge(now='2026-01-01T00:00:01Z', captures=2, capture_bytes=900)
        with self.assertRaises(ValueError): budget.charge(now='2026-01-01T00:00:02Z', captures=1, capture_bytes=101)
        with self.assertRaises(ValueError): budget.charge(now='2026-01-01T00:00:02Z', captures=-1, capture_bytes=-100)
        with self.assertRaises(ValueError): replace(budget, max_captures=120)
        with self.assertRaises(ValueError): replace(budget, max_bytes=96 * 1024 * 1024)
        with self.assertRaises(ValueError): budget.charge(now='2026-01-01T00:05:00Z', native_attempts=1)

    def test_pause_or_uncertain_stop_stays_stopped_across_restore(self):
        budget = self.budget().stop('uncertain_native_attempt')
        with self.assertRaises(ValueError): budget.charge(now='2026-01-01T00:00:01Z', native_attempts=1)
        with self.assertRaises(ValueError): ChainBudget.restore(budget.snapshot(), expected_sha256=digest(budget.snapshot()), now='2026-01-01T00:00:01Z')


if __name__ == '__main__': unittest.main()
