"""Targeted offline invariants; all mechanics here are test_rules_not_gameplay."""

from dataclasses import replace
from datetime import timedelta
import json
from pathlib import Path
import subprocess
import sys
import unittest

from strategy.__main__ import replay_fixture
from strategy.adapter import legacy_observation
from strategy.codec import observation_from_dict, registry_from_dict, timestamp
from strategy.contracts import FieldValue, MatchState, Outcome, Source, to_dict
from strategy.policy import Policy, decide, filter_candidates, generate_candidates
from strategy.rules import RuleRegistry
from strategy.state import reduce_observation

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "examples" / "strategy_synthetic" / "scenario.json"
DATA = json.loads(FIXTURE.read_text(encoding="utf-8"))
NOW = timestamp(DATA["decision_at"])
TEST_POLICY = Policy(allow_test_rules=True)


class StrategyTests(unittest.TestCase):
    def setUp(self):
        self.events = tuple(observation_from_dict(x) for x in DATA["observations"])
        self.registry = registry_from_dict(DATA["registry"])
        self.state = MatchState()
        for event in self.events:
            self.state = reduce_observation(self.state, event, now=NOW)

    def decision(self, state=None, registry=None, now=NOW, candidates=None):
        return decide(state or self.state, registry or self.registry, now=now,
                      policy=TEST_POLICY, candidates=candidates)

    def evaluation(self, decision, rule_id):
        return next(x for x in decision.evaluations if x.candidate.rule_id == rule_id)

    def test_hard_ban_precedes_score_and_survives_ttl(self):
        decision = self.decision()
        self.assertEqual(decision.selected.rule_id, "test_develop")
        blocked = self.evaluation(decision, "test_blocked")
        self.assertIn("confirmed_ban", blocked.reasons)
        self.assertIsNone(blocked.score)
        developed = self.evaluation(decision, "test_develop")
        self.assertEqual(developed.score, 3)
        self.assertEqual(developed.components[0].event_id, "own-state")
        later = NOW + timedelta(seconds=60)
        fresh = replace(self.events[2], event_id="fresh", observed_at=later, ingested_at=later)
        state = reduce_observation(self.state, fresh, now=later)
        decision = self.decision(state, now=later)
        self.assertEqual(decision.selected.rule_id, "test_develop")
        self.assertIn("confirmed_ban", self.evaluation(decision, "test_blocked").reasons)

    def test_ban_update_revokes_old_advice_and_never_erases_confirmed_bans(self):
        candidates = generate_candidates(self.state, self.registry, now=NOW, policy=TEST_POLICY)
        event = replace(self.events[1], event_id="new-bans", observed_at=NOW, ingested_at=NOW,
                        fields=(FieldValue("banned_tags", "observed", ("test:develop",), 0.95),))
        state = reduce_observation(self.state, event, now=NOW)
        old = self.decision(state, candidates=candidates)
        self.assertIsNone(old.selected)
        self.assertTrue(all("candidate_ban_version_changed" in x.reasons for x in old.evaluations))
        self.assertEqual(state.confirmed_bans, ("test:blocked", "test:develop"))
        self.assertEqual(self.decision(state).selected.rule_id, "test_conserve")
        uncertain = replace(event, event_id="uncertain-bans", observed_at=NOW + timedelta(seconds=1),
                            ingested_at=NOW + timedelta(seconds=1), fields=(FieldValue("banned_tags"),))
        state = reduce_observation(state, uncertain, now=uncertain.ingested_at)
        self.assertIn("test:develop", state.confirmed_bans)
        self.assertIsNone(self.decision(state, now=uncertain.ingested_at).selected)

    def test_unknown_rules_bans_resources_and_confidence_fail_closed(self):
        self.assertIsNone(self.decision(registry=RuleRegistry()).selected)
        self.assertIsNone(decide(self.state, self.registry, now=NOW).selected)
        unverified = replace(self.registry, rules=tuple(replace(x, verification="unverified")
                                                       for x in self.registry.rules))
        self.assertIsNone(self.decision(registry=unverified).selected)
        unknown = replace(self.events[2], event_id="uncertain-resource", observed_at=NOW, ingested_at=NOW,
                          fields=(FieldValue("credits"), FieldValue("free_slots", "observed", 1, 0.1)))
        state = reduce_observation(self.state, unknown, now=NOW)
        result = self.evaluation(self.decision(state), "test_develop")
        self.assertFalse(result.accepted)
        self.assertIn("field_unknown_or_ambiguous:self.credits", result.reasons)
        self.assertIn("field_confidence_insufficient:self.free_slots", result.reasons)
        self.assertIsNone(self.decision(replace(self.state, ban_evidence=None)).selected)
        with self.assertRaises(ValueError):
            FieldValue("credits", "unknown", 0)
        with self.assertRaises(ValueError):
            observation_from_dict(to_dict(self.events[0]) | {"schema_version": "2.0"})

    def test_resource_capacity_phase_and_time_are_hard_constraints(self):
        event = replace(self.events[2], event_id="poor", observed_at=NOW, ingested_at=NOW,
                        fields=(FieldValue("credits", "observed", 2, 0.95),
                                FieldValue("free_slots", "observed", 0, 0.95)))
        state = reduce_observation(self.state, event, now=NOW)
        rejected = self.evaluation(self.decision(state), "test_develop")
        self.assertIn("resource_or_capacity_limit:self.credits", rejected.reasons)
        self.assertIn("resource_or_capacity_limit:self.free_slots", rejected.reasons)
        self.assertIsNone(self.decision(now=NOW + timedelta(seconds=31)).selected)
        candidates = generate_candidates(self.state, self.registry, now=NOW, policy=TEST_POLICY)
        self.assertIsNone(self.decision(now=NOW + timedelta(seconds=5), candidates=candidates).selected)
        changed = replace(event, event_id="new-round", round=2, fields=())
        state = reduce_observation(self.state, changed, now=NOW)
        self.assertIsNone(self.decision(state).selected)
        changed = replace(event, event_id="combat", phase="test_combat", fields=())
        state = reduce_observation(self.state, changed, now=NOW)
        self.assertIsNone(self.decision(state).selected)

    def test_event_deduplication_late_data_and_future_cutoff(self):
        self.assertIs(reduce_observation(self.state, self.events[2], now=NOW), self.state)
        with self.assertRaises(ValueError):
            reduce_observation(self.state, replace(self.events[2], fields=()), now=NOW)
        late = replace(self.events[2], event_id="late", observed_at=self.events[1].observed_at,
                       ingested_at=NOW, fields=(FieldValue("credits", "observed", 99, 0.95),))
        state = reduce_observation(self.state, late, now=NOW)
        self.assertEqual(len(state.events), len(self.state.events) + 1)
        self.assertEqual(next(x.field.value for x in state.fields if x.field.key == "credits"), 4)
        self.assertEqual(state.last_seen, self.state.last_seen)
        with self.assertRaises(ValueError):
            reduce_observation(self.state, replace(late, ingested_at=NOW + timedelta(seconds=1)), now=NOW)

    def test_opponent_identity_partial_views_and_match_isolation(self):
        self.assertEqual([x.opponent_id for x in self.state.opponents], ["slot-a", "slot-b"])
        for index in range(2):
            unresolved = replace(self.events[3], event_id="unresolved-" + str(index), opponent_id=None)
            self.state = reduce_observation(self.state, unresolved, now=NOW)
        self.assertEqual(len(self.state.opponents), 2)
        partial = replace(self.events[3], event_id="partial", observed_at=NOW, ingested_at=NOW,
                          fields=(FieldValue("board_signal", "observed", 5, 0.95),))
        state = reduce_observation(self.state, partial, now=NOW)
        self.assertEqual(len(state.opponents[0].fields), 3)
        self.assertEqual(next(x.field.value for x in state.opponents[1].fields
                              if x.field.key == "board_signal"), 2)
        start = replace(self.events[0], event_id="next-start", match_id="synthetic-match-b",
                        observed_at=NOW, ingested_at=NOW)
        new = reduce_observation(state, start, now=NOW)
        self.assertEqual(new.opponents, ())
        self.assertEqual(new.confirmed_bans, ())
        self.assertIsNone(new.ban_evidence)
        self.assertEqual(new.events, (start,))
        self.assertIs(reduce_observation(new, self.events[0], now=NOW), new)
        self.assertIsNone(self.decision(new).selected)

    def test_rule_payload_changes_invalidate_recommendations(self):
        candidate = self.decision().selected
        tampered = replace(candidate, operation="invented_operation", preconditions=())
        result = filter_candidates(self.state, self.registry, (tampered,), now=NOW, policy=TEST_POLICY)[0]
        self.assertFalse(result.accepted)
        modified = replace(self.registry, rules=tuple(replace(x, expected_results=("Changed result",))
                                                     for x in self.registry.rules))
        self.assertIsNone(self.decision(registry=modified, candidates=(candidate,)).selected)
        self.assertTrue(candidate.preconditions)
        self.assertTrue(candidate.resource_costs)
        self.assertTrue(candidate.invalidation_conditions)

    def test_legacy_adapter_preserves_unknowns_and_outcomes_are_separate(self):
        common = dict(event_id="legacy", match_id=self.state.match_id, ingested_at=NOW)
        event = legacy_observation({"type": "opponent_observation", "observed_at": NOW.isoformat(),
                                    "opponent_id": "unknown", "units": [{"name": "Same name"}]}, **common)
        self.assertIsNone(event.opponent_id)
        self.assertEqual(event.fields[0].status, "unknown")
        bans = legacy_observation({"type": "opening_bans", "observed_at": NOW.isoformat(), "lineups": []}, **common)
        self.assertEqual(bans.fields[0].status, "unknown")
        outcome = Outcome("outcome", self.state.match_id, self.decision().decision_id, None,
                          NOW, Source("synthetic", "test_rules_not_gameplay:outcome"), "human", "uncertain")
        with self.assertRaises((ValueError, TypeError, AttributeError)):
            reduce_observation(self.state, outcome, now=NOW)

    def test_reproducible_advice_has_no_capture_network_or_input_dependency(self):
        self.assertEqual(replay_fixture(DATA, allow_test_rules=True), replay_fixture(DATA, allow_test_rules=True))
        script = '''
import importlib.abc, runpy, sys
class Disconnected(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split('.')[0] in {'capture', 'main', 'ctypes', 'socket', 'pyautogui',
                                    'pynput', 'win32api', 'win32gui', 'tkinter'}:
            raise RuntimeError('Forbidden strategy dependency: ' + fullname)
sys.meta_path.insert(0, Disconnected())
sys.argv = ['strategy', '--fixture', sys.argv[1], '--allow-test-rules']
runpy.run_module('strategy', run_name='__main__')
'''
        process = subprocess.run([sys.executable, "-B", "-c", script, str(FIXTURE)], cwd=ROOT,
                                 text=True, capture_output=True, timeout=10, check=True)
        output = json.loads(process.stdout)
        self.assertFalse(output["execution_allowed"])
        self.assertEqual(output["mode"], "advisory")
        self.assertIsNone(output["placement_probabilities"])
        self.assertEqual(output["selected"]["rule_id"], "test_develop")
        expected = json.loads(FIXTURE.with_name("expected_summary.json").read_text(encoding="utf-8"))
        summary = {"fixture_kind": output["rules_domain"], "execution_allowed": output["execution_allowed"],
                   "selected_rule": output["selected"]["rule_id"],
                   "evaluations": [{"rule_id": x["candidate"]["rule_id"],
                                    "opponent_id": x["candidate"]["opponent_id"],
                                    "accepted": x["accepted"], "score": x["score"], "reasons": x["reasons"]}
                                   for x in output["evaluations"]]}
        self.assertEqual(summary, expected)


if __name__ == "__main__":
    unittest.main()
