"""Recognizer batches use wholly synthetic facts to exercise the real API shape."""

from copy import deepcopy
from datetime import timedelta
import json
from pathlib import Path
import unittest

from strategy.advisor import Advisor
from strategy.codec import timestamp
from strategy.recognition import frame_records, ingest_frame, input_requirements
from strategy.session import read_request

ROOT = Path(__file__).resolve().parents[1]
SAMPLE = ROOT / "examples/strategy_synthetic/session"


class RecognitionTests(unittest.TestCase):
    def setUp(self):
        self.request = read_request(SAMPLE / "request.synthetic.json")
        self.batch = json.loads((SAMPLE / "frame-batch.synthetic.json").read_text(encoding="utf-8"))
        self.at = self.batch["frame"]["ingested_at"]
        self.advisor = Advisor(self.request, allow_test_rules=True)

    def test_one_recognized_frame_connects_all_state_evidence_to_an_explained_decision(self):
        receipt = ingest_frame(self.advisor, self.batch, now=self.at)
        self.assertEqual(receipt["status"], "observed")
        self.assertEqual(len(receipt["event_receipts"]), 4)
        point = self.advisor.decide(**self.request["decision_points"][0])
        self.assertEqual(point["selected"], "replace:B->C")
        self.assertEqual(point["ranking"][0]["score"], 9)
        self.assertEqual(point["core_result"]["belief"]["profile_ids"], ["guard"])
        self.assertIn(self.batch["frame"]["sha256"], self.advisor.state.fields[0].source.reference)
        version = self.advisor.state.state_version
        duplicate = ingest_frame(self.advisor, self.batch, now=self.at)
        self.assertFalse(any(row["state_changed"] for row in duplicate["event_receipts"]))
        self.assertEqual(version, self.advisor.state.state_version)

    def test_unknown_menu_and_host_only_frame_revoke_an_intent_without_inventing_match_end(self):
        ingest_frame(self.advisor, self.batch, now=self.at)
        point = self.advisor.decide(**self.request["decision_points"][0])
        state = self.advisor.state
        menu = deepcopy(self.batch)
        menu["scene"] = {"status": "observed", "value": "lobby", "confidence": .95}
        result = ingest_frame(self.advisor, menu, now=self.at)
        self.assertEqual(result["records"], [])
        self.assertIn("active_battle_not_observed", result["blocking_gaps"])
        self.assertIs(self.advisor.state, state)
        self.assertFalse(self.advisor.validate(point["proposal_id"], now=self.at)["candidate_valid"])
        suspended = self.advisor.decide(**self.request["decision_points"][0])
        self.assertIsNone(suspended["action_proposal"])
        self.assertEqual(suspended["blocking_gaps"][0]["code"], "fresh_recognition_required")
        fresh = deepcopy(self.batch)
        later = (timestamp(self.at) + timedelta(seconds=1)).isoformat()
        fresh["start_match"] = False
        fresh["frame"].update(observed_at=later, ingested_at=later)
        ingest_frame(self.advisor, fresh, now=later)
        renewed = self.advisor.decide(**(self.request["decision_points"][0] | {"decision_at": later}))
        self.assertEqual(renewed["selected"], "replace:B->C")
        host_only = deepcopy(self.batch)
        host_only["frame"].update(observed_at=None, time_basis="host_acquisition_only")
        result = frame_records(host_only)
        self.assertEqual(result["records"], [])
        self.assertIn("source_frame_freshness_unverified", result["blocking_gaps"])
        self.assertIn("semantic_observation_time_unknown", result["blocking_gaps"])

    def test_frame_batch_is_atomic_and_unknown_credits_are_not_zero(self):
        records = frame_records(self.batch)["records"]
        invalid = deepcopy(records)
        invalid[-1]["match_id"] = "different-fixture-match"
        with self.assertRaises(ValueError):
            self.advisor.observe_batch(invalid, now=self.at)
        self.assertIsNone(self.advisor.state.match_id)
        unknown = deepcopy(self.batch)
        credit = next(field for field in unknown["own_fields"] if field["key"] == "credits")
        credit.update(status="unknown", value=None, confidence=None)
        ingest_frame(self.advisor, unknown, now=self.at)
        point = self.advisor.decide(**self.request["decision_points"][0])
        self.assertIsNone(point["action_proposal"])
        self.assertEqual(next(item.field.value for item in self.advisor.state.fields
                              if item.field.key == "credits"), None)

    def test_real_source_ingests_fields_and_requirements_explain_actual_remaining_rule_gap(self):
        registry = {"schema_version": "1.0", "domain": "gameplay", "rules": []}
        advisor = Advisor({"schema_version": "strategy-session/1", "engine": "reviewed_rules", "rule_data": registry})
        batch = deepcopy(self.batch)
        batch["data_kind"] = "screen_recognition"  # Fixture-labelled producer path, not a real game record.
        ingest_frame(advisor, batch, now=self.at)
        self.assertTrue(advisor.state.fields)
        self.assertEqual(advisor.state.fields[0].source.kind, "screen_recognition")
        point = advisor.decide(decision_at=self.at)
        self.assertIsNone(point["action_proposal"])
        manifest = input_requirements(registry, controller_operations=("confirm_custom_selection", "room_code_digit"))
        self.assertIn("reviewed_gameplay_rules_missing", manifest["gaps"])
        self.assertIn("ban_scope_and_effect_unverified", manifest["gaps"])
        self.assertFalse(manifest["model_limits"]["dynamic_cost_expressions"])
        fixture = json.loads((ROOT / "examples/strategy_synthetic/scenario.json").read_text(encoding="utf-8"))
        needed = input_requirements(fixture["registry"], controller_operations=())
        development = next(rule for rule in needed["rules"] if rule["rule_id"] == "test_develop")
        self.assertEqual(development["field_paths"], ["self.benefit", "self.credits", "self.free_slots"])
        self.assertFalse(development["controller_operation_supported"])


if __name__ == "__main__":
    unittest.main()
