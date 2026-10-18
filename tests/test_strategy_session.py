"""Exercise the software input-to-decision boundary, with no real game rules."""

from copy import deepcopy
from datetime import timedelta
import json
from pathlib import Path
import subprocess
import sys
import unittest

from strategy.codec import timestamp
from strategy.contracts import to_dict
from strategy.session import (build_report, decide_observations, observations_from_jsonl,
                              read_observations, read_request)

ROOT = Path(__file__).resolve().parents[1]
SAMPLE = ROOT / "examples/strategy_synthetic/session"


class SessionTests(unittest.TestCase):
    def setUp(self):
        self.request = read_request(SAMPLE / "request.synthetic.json")
        self.events = read_observations(SAMPLE / "observations.synthetic.jsonl")

    def report(self, request=None, events=None):
        return build_report(request or self.request, events or self.events, allow_test_rules=True)

    def test_one_observation_log_connects_links_economy_memory_and_bans(self):
        report = self.report()
        self.assertEqual([point["selected"] for point in report["points"]],
                         ["replace:B->C", "end_round", "end_round", "replace:B->E"])
        first, reserve, breaker, banned = report["points"]
        self.assertEqual(first["core_result"]["belief"]["profile_ids"], ["guard"])
        self.assertEqual(breaker["core_result"]["belief"]["profile_ids"], ["breaker"])
        self.assertEqual(banned["snapshot"]["confirmed_bans"], ["C"])
        self.assertTrue(any(item["candidate"] == "replace:B->C" for item in banned["rejected"]))
        self.assertEqual(reserve["ranking"][0]["economy"]["terminal_credits"], 1)
        self.assertEqual(reserve["ranking"][0]["score_components"]["terminal_reserve_value"], 4)
        changes = first["ranking"][0]["first_settlement_link_changes"][0]
        self.assertEqual(changes["pair_links"]["gained"], [["pair-ac", 8]])
        self.assertEqual(changes["isolated_value_delta"], -4)
        self.assertEqual(changes["formation_value_delta"], 4)
        for point in report["points"]:
            self.assertFalse(point["execution_allowed"])
            self.assertEqual(point["action_proposal"]["intent"], point["core_result"]["selected"]["intent"])
            for item in point["ranking"]:
                parts = item["score_components"]
                self.assertEqual(item["score"], parts["weighted_round_utility"]
                                 - parts["switching_utility_cost"] + parts["terminal_reserve_value"])
                self.assertFalse(item["analysis_path_is_executable"])

    def test_software_api_preserves_recognizer_sources_and_reports_real_gaps(self):
        records = [to_dict(event) for event in self.events]
        for event in records:
            event["source"] = {"kind": "screen_recognition", "reference": "fixture-only:frame:extractor-v1"}
        request = {"schema_version": "strategy-session/1", "engine": "reviewed_rules",
                   "rule_data": {"schema_version": "1.0", "domain": "gameplay",
                                 "game_build": None, "rules_version": "unverified",
                                 "ban_semantics_verified": False, "rules": []},
                   "decision_points": [{"point_id": "actual-adapter-path-fixture",
                                        "decision_at": self.request["decision_points"][0]["decision_at"]}]}
        point = decide_observations(request, records)["points"][0]
        self.assertIsNone(point["action_proposal"])
        gaps = {item["code"] for item in point["blocking_gaps"]}
        self.assertTrue({"rules_unavailable", "rules_build_or_version_mismatch",
                         "ban_semantics_unverified"} <= gaps)
        self.assertEqual(point["snapshot"]["own_fields"][0]["source"]["kind"], "screen_recognition")
        self.assertTrue(point["snapshot"]["opponent_memory"])
        self.assertIsNone(self.report(events=tuple(observations_from_jsonl(
            "\n".join(json.dumps(record) for record in records))))["points"][0]["selected"])

    def test_reviewed_rule_entry_keeps_candidates_components_and_intent_expiry(self):
        fixture = json.loads((ROOT / "examples/strategy_synthetic/scenario.json").read_text(encoding="utf-8"))
        request = {"schema_version": "strategy-session/1", "engine": "reviewed_rules",
                   "rule_data": fixture["registry"], "decision_points": [
                       {"point_id": "core-fixture", "decision_at": fixture["decision_at"]}]}
        point = decide_observations(request, fixture["observations"], allow_test_rules=True)["points"][0]
        self.assertEqual(point["selected"], "test_develop_composition")
        self.assertTrue(point["ranking"][0]["selected"])
        self.assertEqual(point["ranking"][0]["score_components"][0]["event_id"], "own-state")
        intent = point["action_proposal"]["intent"]
        self.assertLess(timestamp(intent["issued_at"]), timestamp(intent["expires_at"]))
        self.assertEqual(intent, point["core_result"]["selected"])
        self.assertEqual(point["action_proposal"]["postcondition_contract"],
                         "required_from_reviewed_game_adapter_not_inferred_from_score")

    def test_late_ingestion_is_excluded_until_available_and_current_match_resets(self):
        records = [to_dict(event) for event in self.events if event.event_id not in ("opponent-guard-2", "ban-c")]
        start = timestamp(self.request["decision_points"][0]["decision_at"])
        late = next(record for record in records if record["event_id"] == "opponent-breaker-1")
        late["ingested_at"] = (start + timedelta(seconds=3)).isoformat()
        request = deepcopy(self.request)
        request["decision_points"] = [deepcopy(request["decision_points"][0]) for _ in range(2)]
        for index, second in enumerate((1, 3)):
            request["decision_points"][index].update(point_id=str(index),
                decision_at=(start + timedelta(seconds=second)).isoformat())
        points = decide_observations(request, records, allow_test_rules=True)["points"]
        self.assertEqual([point["selected"] for point in points], ["replace:B->C", "end_round"])
        self.assertNotIn(late["event_id"], points[0]["input_window"]["available_event_ids"])
        new_match = deepcopy(records[0])
        new_match.update(event_id="next-start", match_id="next-fixture-match",
                         observed_at=(start + timedelta(seconds=4)).isoformat(),
                         ingested_at=(start + timedelta(seconds=4)).isoformat())
        records.append(new_match)
        request["decision_points"] = [{**request["decision_points"][0], "point_id": "new-match",
            "decision_at": new_match["ingested_at"]}]
        point = decide_observations(request, records, allow_test_rules=True)["points"][0]
        self.assertEqual(point["snapshot"]["opponent_memory"], [])
        self.assertIsNone(point["action_proposal"])

    def test_schema_input_errors_are_explicit_and_no_opt_in_is_hidden_in_request(self):
        for text in ('{"event_id":"a","event_id":"b"}', '{"value":NaN}', '{}'):
            with self.subTest(text=text), self.assertRaisesRegex(ValueError, "observation line 1"):
                observations_from_jsonl(text)
        request = deepcopy(self.request)
        request["policy"] = {"allow_test_rules": True}
        with self.assertRaises(ValueError):
            self.report(request=request)
        request = deepcopy(self.request)
        request["decision_points"][1]["point_id"] = request["decision_points"][0]["point_id"]
        with self.assertRaises(ValueError):
            self.report(request=request)
        report = build_report(self.request, self.events)
        self.assertTrue(all(point["action_proposal"] is None for point in report["points"]))
        limited = deepcopy(self.request)
        limited["decision_points"] = limited["decision_points"][:1]
        limited["decision_points"][0]["budget"]["max_nodes"] = 0
        fallback = self.report(request=limited)["points"][0]
        self.assertEqual(fallback["selected"], "hold")
        self.assertTrue(fallback["blocking_gaps"])
        for path in (ROOT / "schemas").glob("strategy-*.schema.json"):
            self.assertEqual(json.loads(path.read_text(encoding="utf-8"))["$schema"],
                             "https://json-schema.org/draft/2020-12/schema")

    def test_cli_accepts_recognizer_jsonl_on_stdin_without_desktop_dependencies(self):
        script = '''
import importlib.abc, runpy, sys
class Forbidden(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split('.')[0] in {'capture', 'main', 'ctypes', 'socket', 'tkinter', 'pyautogui', 'pynput'}:
            raise RuntimeError('Forbidden strategy dependency: ' + fullname)
sys.meta_path.insert(0, Forbidden())
sys.argv = ['strategy.session', '--request', sys.argv[1], '--observations', '-', '--allow-test-rules']
runpy.run_module('strategy.session', run_name='__main__')
'''
        run = subprocess.run([sys.executable, "-B", "-c", script, str(SAMPLE / "request.synthetic.json")],
                             input=(SAMPLE / "observations.synthetic.jsonl").read_text(encoding="utf-8"),
                             cwd=ROOT, text=True, capture_output=True, timeout=15, check=True)
        report = json.loads(run.stdout)
        self.assertEqual(report["points"][0]["selected"], "replace:B->C")
        self.assertFalse(report["execution_allowed"])


if __name__ == "__main__":
    unittest.main()
