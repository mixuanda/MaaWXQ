"""Persistent recognition/decision/final-check API; every game fact is a fixture."""

from copy import deepcopy
from datetime import timedelta
import json
from pathlib import Path
import subprocess
import sys
import unittest

from strategy.advisor import Advisor
from strategy.codec import timestamp
from strategy.contracts import to_dict
from strategy.session import read_observations, read_request

ROOT = Path(__file__).resolve().parents[1]
SAMPLE = ROOT / "examples/strategy_synthetic/session"


class AdvisorTests(unittest.TestCase):
    def setUp(self):
        self.request = read_request(SAMPLE / "request.synthetic.json")
        self.events = read_observations(SAMPLE / "observations.synthetic.jsonl")
        self.at = timestamp(self.request["decision_points"][0]["decision_at"])
        self.advisor = Advisor(self.request, allow_test_rules=True)
        for event in self.events:
            if event.ingested_at <= self.at:
                self.advisor.observe(to_dict(event), now=self.at)

    def decide(self, index=0):
        return self.advisor.decide(**self.request["decision_points"][index])

    def test_incremental_state_returns_a_bound_intent_and_checks_issued_typed_candidate(self):
        point = self.decide()
        self.assertEqual(point["selected"], "replace:B->C")
        proposal_id = point["proposal_id"]
        self.assertEqual(point["action_proposal"]["proposal_id"], proposal_id)
        # The consumer cannot alter the retained typed candidate by editing JSON.
        point["action_proposal"]["intent"]["operation"] = "fixture_tampered"
        point["action_proposal"]["intent"]["preconditions"] = []
        result = self.advisor.validate(proposal_id, now=self.at + timedelta(milliseconds=100))
        self.assertTrue(result["candidate_valid"])
        self.assertFalse(result["execution_allowed"])
        self.assertEqual(result["state_version"], self.advisor.state.state_version)

    def test_new_opponent_evidence_invalidates_old_intent_and_changes_decision(self):
        old = self.decide()
        event = next(event for event in self.events if event.event_id == "opponent-breaker-1")
        self.advisor.observe(to_dict(event), now=event.ingested_at)
        check = self.advisor.validate(old["proposal_id"], now=event.ingested_at)
        self.assertFalse(check["candidate_valid"])
        self.assertTrue(check["reasons"])
        current = self.decide(2)
        self.assertEqual(current["selected"], "end_round")
        self.assertEqual(current["core_result"]["belief"]["profile_ids"], ["breaker"])

    def test_recompute_replaces_ticket_even_when_state_and_candidate_are_unchanged(self):
        first, second = self.decide(), self.decide()
        self.assertEqual(first["action_proposal"]["intent"]["candidate_id"],
                         second["action_proposal"]["intent"]["candidate_id"])
        self.assertNotEqual(first["proposal_id"], second["proposal_id"])
        self.assertFalse(self.advisor.validate(first["proposal_id"], now=self.at)["candidate_valid"])
        reserved = self.decide(1)
        self.assertEqual(reserved["selected"], "end_round")
        self.assertFalse(self.advisor.validate(second["proposal_id"], now=self.at)["candidate_valid"])

    def test_expiry_duplicate_delivery_match_reset_and_past_cutoff(self):
        point = self.decide()
        receipt = self.advisor.observe(to_dict(self.events[1]), now=self.at)
        self.assertFalse(receipt["state_changed"])
        self.assertTrue(self.advisor.validate(point["proposal_id"], now=self.at)["candidate_valid"])
        self.assertFalse(self.advisor.validate(point["proposal_id"], now=self.at + timedelta(seconds=5))["candidate_valid"])
        new = deepcopy(to_dict(self.events[0]))
        new.update(event_id="fresh-match", match_id="fresh-fixture", observed_at=(self.at + timedelta(seconds=1)).isoformat(),
                   ingested_at=(self.at + timedelta(seconds=1)).isoformat())
        self.advisor.observe(new, now=new["ingested_at"])
        self.assertEqual(self.advisor.state.opponents, ())
        self.assertFalse(self.advisor.validate(point["proposal_id"], now=new["ingested_at"])["candidate_valid"])
        with self.assertRaisesRegex(ValueError, "cutoff precedes"):
            self.advisor.decide(decision_at=self.at, opponent_id="toy-opponent")

    def test_recognition_producer_with_unverified_real_registry_reports_missing_rules(self):
        config = {"schema_version": "strategy-session/1", "engine": "reviewed_rules",
                  "rule_data": {"schema_version": "1.0", "domain": "gameplay", "rules": []}}
        advisor = Advisor(config)
        for event in self.events:
            if event.ingested_at > self.at:
                continue
            record = to_dict(event)
            record["source"] = {"kind": "screen_recognition", "reference": "fixture-only:frame+extractor"}
            advisor.observe(record, now=self.at)
        point = advisor.decide(decision_at=self.at)
        self.assertIsNone(point["proposal_id"])
        self.assertIsNone(point["action_proposal"])
        self.assertIn("ban_semantics_unverified", {gap["code"] for gap in point["blocking_gaps"]})
        self.assertTrue(advisor.state.fields)

    def test_jsonl_service_is_persistent_and_returns_one_result_per_command(self):
        commands = [{"op": "observe", "observation": to_dict(event), "now": self.at.isoformat()}
                    for event in self.events if event.ingested_at <= self.at]
        commands += [{"op": "decide", **self.request["decision_points"][0]},
                     {"op": "validate", "proposal_id": "unknown", "now": self.at.isoformat()},
                     {"op": "unsupported"}]
        script = '''
import importlib.abc, runpy, sys
class Forbidden(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split('.')[0] in {'capture', 'main', 'ctypes', 'socket', 'tkinter', 'pyautogui', 'pynput'}:
            raise RuntimeError('Forbidden advisor dependency: ' + fullname)
sys.meta_path.insert(0, Forbidden())
sys.argv = ['strategy.advisor', '--request', sys.argv[1], '--allow-test-rules']
runpy.run_module('strategy.advisor', run_name='__main__')
'''
        run = subprocess.run([sys.executable, "-B", "-c", script, str(SAMPLE / "request.synthetic.json")],
                             cwd=ROOT, input="".join(json.dumps(command) + "\n" for command in commands),
                             text=True, capture_output=True, timeout=15, check=True)
        results = [json.loads(line) for line in run.stdout.splitlines()]
        self.assertEqual(len(results), len(commands))
        self.assertEqual(results[-3]["result"]["selected"], "replace:B->C")
        self.assertFalse(results[-2]["result"]["candidate_valid"])
        self.assertFalse(results[-1]["ok"])


if __name__ == "__main__":
    unittest.main()
