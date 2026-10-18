"""Fixture-only provenance checks; no current client rules are asserted."""

from dataclasses import replace
import json
from pathlib import Path
import unittest

from strategy.codec import observation_from_dict, registry_from_dict, timestamp
from strategy.contracts import MatchState, Source, to_dict
from strategy.policy import Policy, decide
from strategy.state import reduce_observation


FIXTURE = Path(__file__).resolve().parents[1] / "examples" / "strategy_synthetic" / "scenario.json"
DATA = json.loads(FIXTURE.read_text(encoding="utf-8"))
NOW = timestamp(DATA["decision_at"])
TEST_POLICY = Policy(allow_test_rules=True)
LOSSY_LABEL = "fixture_discard_existing_unit"


class DomainBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.events = tuple(observation_from_dict(row) for row in DATA["observations"])
        self.registry = registry_from_dict(DATA["registry"])
        self.registry = replace(self.registry, rules=tuple(
            replace(rule, operation=LOSSY_LABEL) if rule.rule_id == "test_develop" else rule
            for rule in self.registry.rules))
        self.state = self.replay(self.events)

    def replay(self, events):
        state = MatchState()
        for event in events:
            state = reduce_observation(state, event, now=NOW)
        return state

    def relabel_fixture(self, kind):
        # Exercise a domain path, not evidence that these annotations are real.
        return self.replay(tuple(replace(event, source=Source(
            kind, "boundary-fixture-only:" + event.event_id)) for event in self.events))

    def gameplay_registry_fixture(self):
        # The reviewed_rule label here is test data, not a reviewed WXQ rule.
        return replace(self.registry, domain="gameplay", rules=tuple(
            replace(rule, source=Source("reviewed_rule", "boundary-fixture-only:" + rule.rule_id))
            for rule in self.registry.rules))

    def assert_abstains(self, state, registry, reason, policy=TEST_POLICY):
        before = to_dict(state)
        result = decide(state, registry, now=NOW, policy=policy)
        self.assertIsNone(result.selected)
        self.assertFalse(result.execution_allowed)
        self.assertIn(reason, result.reasons)
        self.assertTrue(result.evaluations)
        self.assertTrue(all(not item.accepted and item.score is None and not item.components
                            and reason in item.reasons for item in result.evaluations))
        self.assertEqual(to_dict(state), before)
        return result

    def cache_variants(self, state, source):
        own = replace(state.fields[0], source=source)
        opponent = state.opponents[0]
        other = replace(opponent, fields=(replace(opponent.fields[0], source=source),
                                          *opponent.fields[1:]))
        return {
            "history": replace(state, events=(replace(state.events[0], source=source),
                                               *state.events[1:])),
            "own_cache": replace(state, fields=(own, *state.fields[1:])),
            "opponent_cache": replace(state, opponents=(other, *state.opponents[1:])),
            "ban_cache": replace(state, ban_evidence=replace(state.ban_evidence, source=source)),
        }

    def test_synthetic_fixture_still_requires_explicit_opt_in(self):
        result = decide(self.state, self.registry, now=NOW, policy=TEST_POLICY)
        self.assertEqual(result.selected.operation, LOSSY_LABEL)
        self.assertFalse(result.execution_allowed)
        self.assert_abstains(self.state, self.registry, "test_rules_require_explicit_opt_in",
                             policy=Policy())

    def test_test_opt_in_cannot_apply_synthetic_rules_to_other_sources(self):
        for kind in ("manual_annotation", "legacy_manual", "reviewed_rule"):
            with self.subTest(kind=kind):
                state = self.relabel_fixture(kind)
                self.assert_abstains(state, self.registry, "non_synthetic_evidence_not_test_rules")
        # Deliberately inconsistent caches model an adapter reconstruction bug.
        for location, state in self.cache_variants(
                self.state, Source("manual_annotation", "boundary-fixture-only:cache")).items():
            with self.subTest(location=location):
                self.assert_abstains(state, self.registry, "non_synthetic_evidence_not_test_rules")

    def test_gameplay_rejects_synthetic_history_or_cached_evidence(self):
        state = self.relabel_fixture("manual_annotation")
        registry = self.gameplay_registry_fixture()
        # A positive control makes the source checks, not a different rejection,
        # responsible for abstention in each deliberately mixed-domain variant.
        self.assertIsNotNone(decide(state, registry, now=NOW).selected)
        for location, mixed in self.cache_variants(
                state, Source("synthetic", "boundary-fixture-only:cache")).items():
            with self.subTest(location=location):
                self.assert_abstains(mixed, registry, "synthetic_evidence_not_gameplay")

    def test_unknown_ban_semantics_and_version_mismatch_never_allow_lossy_advice(self):
        for state, registry in ((self.state, self.registry),
                                (self.relabel_fixture("manual_annotation"),
                                 self.gameplay_registry_fixture())):
            with self.subTest(domain=registry.domain):
                self.assert_abstains(state, replace(registry, ban_semantics_verified=False),
                                     "ban_semantics_unverified")
                for changed in (replace(registry, game_build="fixture-other-build"),
                                replace(registry, rules_version="fixture-other-rules")):
                    self.assert_abstains(state, changed, "rules_build_or_version_mismatch")


if __name__ == "__main__":
    unittest.main()
