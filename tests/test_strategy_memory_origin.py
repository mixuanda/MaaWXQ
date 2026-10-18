"""JSON-to-decision coverage provenance; all fixtures are declared synthetic."""
from dataclasses import replace
from datetime import timedelta
from pathlib import Path
import unittest

from strategy.codec import observation_from_dict
from strategy.contracts import FieldValue, Observation, Source, digest, to_dict
from strategy.rolling.actions import revalidate
from strategy.rolling.demo import FIXTURE_TIME, TEST_POLICY, load_fixture, make_state
from strategy.rolling.memory import assess
from strategy.rolling.model import DOMAIN
from strategy.rolling.search import Budget, plan
from strategy.state import reduce_observation

ROOT = Path(__file__).resolve().parents[1]


class MemoryOriginTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        _, worlds = load_fixture(ROOT / "examples/strategy_synthetic/rolling/scenarios.json")
        base = worlds["pivot"]
        cls.world = replace(base, version="synthetic-coverage-origin-1", profiles=tuple(
            replace(profile, board_ids=("enemy-base", "guard", "breaker"))
            if profile.profile_id == "breaker" else profile for profile in base.profiles))

    def state(self):
        return make_state(self.world, board_ids=("A",), hand_ids=("B", "C"), credits=1,
                          capacity=2, opponent_id=None)

    def event(self, key, coverage, *, board=True, at=FIXTURE_TIME, **changes):
        fields = ((FieldValue("board_ids", "observed", ("enemy-base", "guard"), .95),) if board
                  else (FieldValue("note", "observed", "synthetic note", .95),))
        event = Observation(key, "synthetic-rolling-match", "opponent", at, at,
                            Source("synthetic", DOMAIN + ":origin:" + key), round=1,
                            phase=self.world.phase, opponent_id="toy-opponent", coverage=coverage,
                            fields=fields, game_build=self.world.build, rules_version=self.world.version)
        # Exercise the public JSON boundary, not just direct dataclass calls.
        return observation_from_dict(to_dict(replace(event, **changes)))

    def case(self, note_coverage="full", board_coverage="partial"):
        state = self.state()
        for event in (self.event("note", note_coverage, board=False), self.event("board", board_coverage)):
            state = reduce_observation(state, event, now=FIXTURE_TIME)
        return state

    def decision(self, state, now=FIXTURE_TIME, world=None):
        return plan(state, world or self.world, "toy-opponent", now=now,
                    policy=TEST_POLICY, budget=Budget(horizon=1))

    def test_same_timestamp_board_event_coverage_controls_both_decision_directions(self):
        for note, board, expected in (("full", "partial", "deploy:B"), ("partial", "full", "deploy:C")):
            with self.subTest(board_coverage=board):
                state = self.case(note, board)
                self.assertEqual(state.opponents[0].coverage, note)  # Summary belongs to the note.
                result = self.decision(state)
                self.assertEqual(result.selected.move.label, expected)
                self.assertEqual(result.belief.coverage, board)
                self.assertEqual(result.belief.event_ids, ("board",))
                self.assertEqual(result.belief.coverage_origin, "board_observation_event")
                self.assertEqual(result.belief.age_seconds, 0)
                self.assertEqual(result.belief.confidence, .95)
                self.assertEqual(result.belief.game_build, self.world.build)
                self.assertEqual(result.belief.observed_rules_version, self.world.version)
                self.assertEqual(set(result.belief.profile_ids),
                                 {"guard", "breaker"} if board == "partial" else {"guard"})
                self.assertEqual(result.alternatives[0].total_utility, 7 if board == "partial" else 11)
                self.assertFalse(result.execution_allowed)

    def test_new_note_cannot_refresh_stale_board_but_new_board_can(self):
        state = self.case()
        later = FIXTURE_TIME + timedelta(seconds=21)
        expired = self.decision(state, now=later)
        self.assertIsNone(expired.selected)
        self.assertIn("opponent_memory_stale_or_future", expired.reasons)
        note = self.event("later-note", "full", board=False, at=later)
        unrefreshed = reduce_observation(state, note, now=later)
        result = self.decision(unrefreshed, now=later)
        self.assertIsNone(result.selected)
        self.assertIn("opponent_board_not_refreshed_by_latest_sighting", result.reasons)
        refreshed_at = later + timedelta(milliseconds=1)
        board = self.event("fresh-board", "partial", at=refreshed_at)
        fresh = reduce_observation(unrefreshed, board, now=refreshed_at)
        revised = self.decision(fresh, now=refreshed_at)
        self.assertEqual(revised.selected.move.label, "deploy:B")
        self.assertEqual(revised.belief.event_ids, ("fresh-board",))
        self.assertEqual(revised.belief.age_seconds, 0)
        self.assertTrue(revalidate(self.decision(state).selected, fresh, self.world,
                                   now=refreshed_at, policy=TEST_POLICY))

    def test_bans_and_versions_still_bind_json_input_and_advice(self):
        state = self.case("partial", "full")
        prior = self.decision(state)
        self.assertEqual(prior.selected.move.label, "deploy:C")
        raw = to_dict(Observation("ban-c", state.match_id, "bans", FIXTURE_TIME, FIXTURE_TIME,
                                 Source("synthetic", DOMAIN + ":ban-origin"), round=1, phase=self.world.phase,
                                 game_build=self.world.build, rules_version=self.world.version,
                                 fields=(FieldValue("banned_tags", "observed", ("C",), .95),)))
        banned = reduce_observation(state, observation_from_dict(raw), now=FIXTURE_TIME)
        updated = self.decision(banned)
        self.assertEqual(updated.selected.move.label, "deploy:B")
        self.assertEqual(updated.selected.intent.ban_version, banned.ban_version)
        self.assertTrue(any("confirmed_ban" in why for _, why in updated.root_rejections))
        self.assertIn("candidate_ban_version_changed", revalidate(prior.selected, banned, self.world,
                                                                 now=FIXTURE_TIME, policy=TEST_POLICY))
        before = digest(state)
        for changes in ({"game_build": "synthetic-other-build"}, {"rules_version": "synthetic-other-rules"}):
            event = self.event("wrong-version", "full", **changes)
            with self.assertRaisesRegex(ValueError, "build/rule changes"):
                reduce_observation(state, event, now=FIXTURE_TIME)
        self.assertEqual(digest(state), before)
        inherited = self.event("inherited-version", "full", at=FIXTURE_TIME + timedelta(milliseconds=1),
                               game_build=None, rules_version=None)
        newer = reduce_observation(state, inherited, now=inherited.ingested_at)
        belief = self.decision(newer, now=inherited.ingested_at).belief
        self.assertEqual(belief.game_build, self.world.build)
        self.assertIsNone(belief.observed_game_build)  # No new client version observation invented.

    def test_missing_or_mismatched_origin_abstains_and_coverage_changes_invalidate_digest(self):
        state = self.case()
        original = self.decision(state)
        missing = replace(state, events=tuple(event for event in state.events if event.event_id != "board"))
        self.assertIsNone(self.decision(missing).selected)
        self.assertIn("opponent_board_origin_missing_or_ambiguous", self.decision(missing).reasons)
        wrong = replace(state, events=tuple(replace(event, opponent_id="other-toy-opponent")
                        if event.event_id == "board" else event for event in state.events))
        self.assertIsNone(self.decision(wrong).selected)
        self.assertIn("opponent_board_origin_mismatched", self.decision(wrong).reasons)
        # Defensive check for a bad cache: normal reduction rejects rewriting an
        # event ID. Even unchanged cached summary/state version cannot hide this.
        changed = replace(state, events=tuple(replace(event, coverage="full")
                          if event.event_id == "board" else event for event in state.events))
        self.assertEqual(self.decision(changed).selected.move.label, "deploy:C")
        self.assertNotEqual(original.belief.evidence_digest, self.decision(changed).belief.evidence_digest)
        self.assertIn("opponent_memory_changed", revalidate(original.selected, changed, self.world,
                                                           now=FIXTURE_TIME, policy=TEST_POLICY))


if __name__ == "__main__":
    unittest.main()
