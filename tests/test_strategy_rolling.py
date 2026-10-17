"""Distinguishing offline invariants; all data is test_rules_not_gameplay."""

from dataclasses import dataclass, replace
from datetime import timedelta
import json
from pathlib import Path
import subprocess
import sys
import unittest

from strategy.contracts import FieldValue, Observation, Source, digest
from strategy.policy import Policy
from strategy.state import reduce_observation
from strategy.rolling.actions import revalidate
from strategy.rolling.demo import FIXTURE_TIME, TEST_POLICY, comparison, load_fixture, make_state
from strategy.rolling.memory import assess
from strategy.rolling.model import DOMAIN, Move, RoundRule, formation, read_position, transition
from strategy.rolling.search import Budget, ExactEvaluator, plan

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "examples/strategy_synthetic/rolling/scenarios.json"


class RollingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fixture, cls.worlds = load_fixture(FIXTURE)
        cls.cases = {x["case_id"]: x for x in cls.fixture["cases"]}

    def case(self, name):
        case = self.cases[name]
        world = self.worlds[case["world"]]
        return world, make_state(world, **case["state"])

    def run_plan(self, world, state, **kwargs):
        return plan(state, world, "toy-opponent", now=FIXTURE_TIME, policy=TEST_POLICY, **kwargs)

    def label(self, result):
        return result.selected.move.label if result.selected else None

    def test_horizon_changes_investment_with_explicit_resource_ledger(self):
        world, state = self.case("patient_two_rounds")
        before = digest(state)
        greedy = self.run_plan(world, state, budget=Budget(horizon=1))
        patient = self.run_plan(world, state)
        self.assertEqual(self.label(greedy), "buy:B")
        self.assertEqual(self.label(patient), "buy:C")
        best = patient.alternatives[0]
        self.assertEqual(best.total_utility, 26)
        self.assertEqual(next(x.total_utility for x in patient.alternatives if x.first_move == "buy:B"), 14)
        self.assertIn(("three-team", 12), best.rounds[-1].profiles[0].threshold_links)
        self.assertEqual([x.credits_after for x in best.resource_ledger], [1, 1, 1, 0, 0, 0])
        self.assertEqual(best.resource_ledger[2].next_round, 2)
        for step in best.resource_ledger:
            self.assertEqual(step.credits_after, step.credits_before - step.credits_spent + step.income_received)
        self.assertEqual([x.credits_spent for x in best.resource_ledger], [1, 0, 0, 1, 0, 0])
        self.assertEqual(best.resource_ledger[2].offers_after, ("D",))
        self.assertTrue(patient.horizon_exhausted)
        self.assertFalse(patient.execution_allowed)
        self.assertTrue(best.analysis_only)
        self.assertEqual(digest(state), before)
        self.assertEqual(patient, self.run_plan(world, state))
        four = replace(world, version="toy-four-rounds", rounds=world.rounds + (
            RoundRule(3, 0, (), 3, 1), RoundRule(4, 0, (), 3, 1)))
        four_state = make_state(four, **self.cases["patient_two_rounds"]["state"])
        longer = self.run_plan(four, four_state, budget=Budget(horizon=4))
        self.assertEqual(self.label(longer), "buy:C")
        self.assertEqual(longer.alternatives[0].total_utility, 66)
        self.assertEqual(len(longer.alternatives[0].rounds), 4)

    def test_fresh_opponent_change_partial_view_and_future_uncertainty(self):
        world, state = self.case("fresh_guard")
        old = self.run_plan(world, state, budget=Budget(horizon=1))
        self.assertEqual(self.label(old), "deploy:C")
        seen = FIXTURE_TIME + timedelta(milliseconds=1)
        event = Observation("changed-lineup", state.match_id, "opponent", seen, seen,
                            Source("synthetic", DOMAIN + ":changed-opponent"), round=1,
                            phase=world.phase, opponent_id="toy-opponent", coverage="full",
                            fields=(FieldValue("board_ids", "observed", ("enemy-base", "breaker"), 0.95),))
        updated = reduce_observation(state, event, now=seen)
        changed = plan(updated, world, "toy-opponent", now=seen, policy=TEST_POLICY, budget=Budget(horizon=1))
        self.assertEqual(self.label(changed), "deploy:B")
        self.assertEqual(updated, reduce_observation(updated, event, now=seen))
        self.assertTrue(revalidate(old.selected, updated, world, now=seen, policy=TEST_POLICY))
        _, partial = self.case("partial_opponent")
        robust = self.run_plan(world, partial, budget=Budget(horizon=1))
        self.assertEqual(self.label(robust), "deploy:B")
        self.assertEqual(set(robust.belief.profile_ids), {"guard", "breaker"})
        two = replace(world, version="toy-pivot-two-rounds", rounds=world.rounds + (RoundRule(2, 0, (), 2, 1),))
        two_state = make_state(two, **self.cases["fresh_guard"]["state"])
        future = self.run_plan(two, two_state)
        self.assertEqual(future.belief.profile_ids, ("guard",))
        self.assertEqual({x.profile_id for x in future.alternatives[0].rounds[-1].profiles}, {"guard", "breaker"})
        self.assertEqual(future.alternatives[0].rounds[-1].belief_kind, "all_declared_profiles_future_uncertain")
        missing_board = replace(event, event_id="partial-without-board", coverage="partial",
                                fields=(FieldValue("unrelated_note", "observed", "test", 0.95),))
        not_refreshed = reduce_observation(state, missing_board, now=seen)
        belief, why = assess(not_refreshed, world, "toy-opponent", now=seen)
        self.assertIsNone(belief)
        self.assertIn("opponent_board_not_refreshed_by_latest_sighting", why)

    def test_bans_replan_links_and_switching_cost_changes_the_pivot(self):
        world, state = self.case("pivot_before_ban")
        prior = self.run_plan(world, state, budget=Budget(horizon=1))
        self.assertEqual(self.label(prior), "replace:B->C")
        self.assertEqual(prior.alternatives[0].switching_cost, 2)
        self.assertEqual(prior.alternatives[0].resource_ledger[0].credits_after, 0)
        ban = Observation("new-ban", state.match_id, "bans", FIXTURE_TIME, FIXTURE_TIME,
                          Source("synthetic", DOMAIN + ":ban-change"), round=1, phase=world.phase,
                          fields=(FieldValue("banned_tags", "observed", ("C",), 0.95),))
        banned = reduce_observation(state, ban, now=FIXTURE_TIME)
        problems = revalidate(prior.selected, banned, world, now=FIXTURE_TIME, policy=TEST_POLICY)
        self.assertIn("candidate_ban_version_changed", problems)
        after = self.run_plan(world, banned, budget=Budget(horizon=1))
        self.assertEqual(self.label(after), "replace:B->E")
        self.assertEqual(after.alternatives[0].total_utility, 8)
        self.assertTrue(any("confirmed_ban" in why for _, why in after.root_rejections))
        revoked = self.run_plan(world, state, budget=Budget(horizon=1), latest_snapshot=lambda: (banned, world))
        self.assertIsNone(revoked.selected)
        self.assertIn("candidate_ban_version_changed", revoked.reasons)
        expensive = replace(world, version="toy-expensive-pivot", replace_utility_cost=5)
        expensive_state = make_state(expensive, **self.cases["pivot_before_ban"]["state"])
        hold_board = self.run_plan(expensive, expensive_state, budget=Budget(horizon=1))
        self.assertEqual(self.label(hold_board), "end_round")
        self.assertEqual(hold_board.alternatives[0].terminal_position.board_ids, ("A", "B"))
        long_world, long_state = self.case("future_threshold_unit_banned")
        long = self.run_plan(long_world, long_state)
        self.assertEqual(self.label(long), "buy:B")
        self.assertFalse(any("buy:D" in step for step in long.alternatives[0].path))

    def test_transitions_never_invent_refunds_offers_or_partial_thresholds(self):
        world, state = self.case("patient_two_rounds")
        pos, _ = read_position(state, world)
        bought = transition(pos, world, Move("buy", "C"), bans=(), final_round=2)
        deployed = transition(bought.position, world, Move("deploy", "C"), bans=(), final_round=2)
        self.assertEqual(formation(world, deployed.position.board_ids, world.profiles[0]).threshold_links, ())
        income_world = replace(world, rounds=(world.rounds[0], replace(world.rounds[1], income_on_entry=3)))
        next_round = transition(deployed.position, income_world, Move("end_round"), bans=(), final_round=2)
        self.assertEqual(next_round.position.credits, 4)
        self.assertEqual(next_round.income_received, 3)
        self.assertEqual(next_round.position.offer_ids, ("D",))
        self.assertEqual(next_round.position.capacity, 3)
        self.assertEqual(transition(next_round.position, income_world, Move("hold"), bans=(), final_round=2).position.credits, 4)
        with self.assertRaises(ValueError):
            transition(pos, world, Move("buy", "D"), bans=(), final_round=2)
        with self.assertRaises(ValueError):
            transition(pos, world, Move("buy", "C"), bans=("C",), final_round=2)
        pivot_world, pivot_state = self.case("pivot_before_ban")
        pivot_pos, _ = read_position(pivot_state, pivot_world)
        replaced = transition(pivot_pos, pivot_world, Move("replace", "C", "B"), bans=(), final_round=1)
        self.assertEqual(replaced.position.discarded_ids, ("B",))
        self.assertEqual(replaced.position.credits, 0)
        self.assertEqual(replaced.switching_cost, 2)

    def test_unknown_stale_identity_and_new_match_abstain(self):
        world, state = self.case("fresh_guard")
        kwargs = dict(self.cases["fresh_guard"]["state"])
        for bad in (make_state(world, **kwargs, memory_age=21),
                    make_state(world, **kwargs, unknown=("credits",)),
                    make_state(world, **{**kwargs, "opponent_id": "another-opponent"})):
            self.assertIsNone(self.run_plan(world, bad, budget=Budget(horizon=1)).selected)
        missing = replace(world, rounds=(replace(world.rounds[0], utility_weight=None),))
        unknown = self.run_plan(missing, state, budget=Budget(horizon=1))
        self.assertIn("round_transition_unknown:1", unknown.reasons)
        no_future = self.run_plan(world, state)
        self.assertIn("round_transition_unknown:2", no_future.reasons)
        self.assertIn("rules_unavailable", self.run_plan(None, state).reasons)
        unknown_ban = make_state(world, **kwargs, bans=("undeclared-ban-target",))
        rejected = self.run_plan(world, unknown_ban, budget=Budget(horizon=1))
        self.assertIsNone(rejected.selected)
        self.assertIn("ban_target_outside_declared_support", rejected.reasons)
        unverified = replace(world, verification="unverified")
        self.assertIn("rules_unverified", self.run_plan(unverified, state, budget=Budget(horizon=1)).reasons)
        self.assertIsNone(plan(state, world, "toy-opponent", now=FIXTURE_TIME, budget=Budget(horizon=1)).selected)
        self.assertIsNone(plan(state, world, "toy-opponent", now=FIXTURE_TIME + timedelta(seconds=31),
                               policy=TEST_POLICY, budget=Budget(horizon=1)).selected)
        with self.assertRaises(ValueError):
            replace(world, domain="gameplay")
        start_at = FIXTURE_TIME + timedelta(seconds=1)
        new_match = Observation("new", "new-match", "match_start", start_at, start_at,
                                Source("synthetic", DOMAIN + ":new-match"), round=1, phase=world.phase,
                                game_build=world.build, rules_version=world.version, context_confidence=0.95)
        reset = reduce_observation(state, new_match, now=start_at)
        self.assertEqual(reset.opponents, ())
        belief, why = assess(reset, world, "toy-opponent", now=start_at)
        self.assertIsNone(belief)
        self.assertIn("opponent_identity_unresolved", why)

    def test_budgets_cancellation_evaluator_and_final_snapshot_fail_closed(self):
        world, state = self.case("patient_two_rounds")
        for budget in (Budget(max_nodes=0), Budget(max_seconds=0)):
            fallback = self.run_plan(world, state, budget=budget)
            self.assertEqual(self.label(fallback), "hold")
            self.assertEqual(fallback.status, "fallback")
            self.assertEqual(fallback.final_gate, "passed_advice_only")
        incumbent = self.run_plan(world, state, budget=Budget(max_nodes=2))
        self.assertEqual(incumbent.status, "budget_limited")
        self.assertTrue(incumbent.alternatives)
        self.assertFalse(incumbent.horizon_exhausted)
        self.assertEqual(incumbent.nodes, 2)
        cancelled = self.run_plan(world, state, cancelled=lambda: True)
        self.assertIsNone(cancelled.selected)
        self.assertEqual(cancelled.termination, "cancelled")

        @dataclass(frozen=True)
        class Broken(ExactEvaluator):
            def score(self, value):
                raise AttributeError("offline scorer unavailable")

        for evaluator in (None, Broken()):
            result = self.run_plan(world, state, evaluator=evaluator)
            self.assertEqual(self.label(result), "hold")
            self.assertEqual(result.final_gate, "passed_advice_only")
        calls = [0]
        def during_search():
            calls[0] += 1
            return calls[0] >= 12
        stopped = self.run_plan(world, state, cancelled=during_search)
        self.assertIsNone(stopped.selected)
        self.assertEqual(stopped.termination, "cancelled")

        class Timer:
            value = 0
            def __call__(self):
                return self.value
        timer = Timer()
        @dataclass(frozen=True)
        class Delayed(ExactEvaluator):
            def score(self, value):
                timer.value = 2
                return value.total
        timed = self.run_plan(world, state, evaluator=Delayed(), clock=timer)
        self.assertEqual(self.label(timed), "hold")
        self.assertEqual(timed.termination, "time_budget_exhausted")
        def unavailable():
            raise LookupError("snapshot unavailable")
        for callback in (unavailable, lambda: None, lambda: (None, world)):
            result = self.run_plan(world, state, latest_snapshot=callback)
            self.assertIsNone(result.selected)
            self.assertEqual(result.termination, "final_snapshot_unavailable")
        changed = self.run_plan(world, state, latest_snapshot=lambda: (state, replace(world, version="new-rules")))
        self.assertIsNone(changed.selected)
        self.assertIn("world_rules_changed", changed.reasons)
        original = self.run_plan(world, state).selected
        forged = replace(original, move=Move("buy", "B"))
        self.assertTrue(revalidate(forged, state, world, now=FIXTURE_TIME, policy=TEST_POLICY))
        forged_horizon = replace(original, horizon=1)
        self.assertTrue(revalidate(forged_horizon, state, world, now=FIXTURE_TIME, policy=TEST_POLICY))

    def test_receding_horizon_requires_actual_observation_before_continuation(self):
        world, state = self.case("patient_two_rounds")
        first = self.run_plan(world, state)
        self.assertEqual(self.label(first), "buy:C")
        # These are new fixture observations, not the old plan applied to MatchState.
        bought = make_state(world, board_ids=("A",), hand_ids=("C",), offer_ids=("B",), credits=1)
        next_advice = self.run_plan(world, bought)
        self.assertEqual(self.label(next_advice), "deploy:C")
        self.assertTrue(revalidate(first.selected, bought, world, now=FIXTURE_TIME, policy=TEST_POLICY))
        observed_round_two = make_state(world, board_ids=("A", "C"), offer_ids=("D",), credits=1,
                                        capacity=3, round_number=2)
        next_round = self.run_plan(world, observed_round_two, budget=Budget(horizon=1))
        self.assertEqual(self.label(next_round), "buy:D")
        self.assertEqual(observed_round_two.round, 2)

    def test_cancel_pulses_before_search_and_during_final_gate_cannot_revive_advice(self):
        world, state = self.case("patient_two_rounds")
        calls = [0]
        def pulse_before_search():
            calls[0] += 1
            return calls[0] == 2
        early = self.run_plan(world, state, cancelled=pulse_before_search)
        self.assertIsNone(early.selected)
        self.assertEqual(early.termination, "cancelled")
        self.assertIn("cancelled", early.reasons)
        gate = {"active": False, "polls": 0}
        def latest():
            gate["active"] = True
            return state, world
        def pulse_during_gate():
            if gate["active"]:
                gate["polls"] += 1
                return gate["polls"] == 2
            return False
        late = self.run_plan(world, state, cancelled=pulse_during_gate, latest_snapshot=latest)
        self.assertIsNone(late.selected)
        self.assertEqual(late.termination, "cancelled")
        self.assertIn("cancelled", late.reasons)

    def test_unknown_or_mismatched_opponent_phase_rejects_current_and_stored_advice(self):
        world, state = self.case("fresh_guard")
        original = self.run_plan(world, state, budget=Budget(horizon=1)).selected
        seen = FIXTURE_TIME + timedelta(milliseconds=1)
        for phase in (None, "another_toy_phase"):
            with self.subTest(phase=phase):
                event = Observation("phase-check", state.match_id, "opponent", seen, seen,
                                    Source("synthetic", DOMAIN + ":phase-check"), round=1, phase=phase,
                                    opponent_id="toy-opponent", coverage="full",
                                    fields=(FieldValue("board_ids", "observed", ("enemy-base", "guard"), 0.95),))
                updated = reduce_observation(state, event, now=seen)
                belief, why = assess(updated, world, "toy-opponent", now=seen)
                self.assertIsNone(belief)
                self.assertIn("opponent_phase_unknown_or_mismatched", why)
                result = plan(updated, world, "toy-opponent", now=seen, policy=TEST_POLICY,
                              budget=Budget(horizon=1))
                self.assertIsNone(result.selected)
                self.assertIn("opponent_phase_unknown_or_mismatched", result.reasons)
                self.assertIn("opponent_phase_unknown_or_mismatched",
                              revalidate(original, updated, world, now=seen, policy=TEST_POLICY))

    def test_cli_is_disconnected_and_synthetic_opt_in_is_required(self):
        self.assertEqual(comparison(FIXTURE)["cases"], [])
        code = '''
import importlib.abc, json, runpy, sys
class Guard(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        blocked = {'ctypes','capture','capture_backend','main','socket','openai','requests',
                   'torch','tensorflow','transformers','pyautogui','pynput'}
        if fullname.split('.')[0] in blocked:
            raise RuntimeError('forbidden side effect dependency: '+fullname)
sys.meta_path.insert(0, Guard())
sys.argv=['strategy.rolling','--fixture','examples/strategy_synthetic/rolling/scenarios.json','--allow-test-rules']
runpy.run_module('strategy.rolling',run_name='__main__')
'''
        output = subprocess.run([sys.executable, "-B", "-c", code], cwd=ROOT,
                                text=True, capture_output=True, timeout=20, check=True)
        report = json.loads(output.stdout)
        self.assertEqual(report["domain"], DOMAIN)
        self.assertFalse(report["execution_allowed"])
        self.assertFalse(report["training_executed"])
        self.assertEqual(report["real_room_observations"], 0)
        labels = {row["case_id"]: row["result"]["selected"]["move"]["unit_id"] for row in report["cases"]}
        self.assertEqual(labels["greedy_current_round"], "B")
        self.assertEqual(labels["patient_two_rounds"], "C")
        self.assertEqual(labels["pivot_after_c_ban"], "E")


if __name__ == "__main__":
    unittest.main()
