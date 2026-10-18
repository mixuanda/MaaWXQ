"""Decision contrasts for explicit resource-option assumptions, not game rules."""

from dataclasses import replace
from datetime import timedelta
from pathlib import Path
import unittest

from strategy.contracts import FieldValue, Observation, Source, to_dict
from strategy.rolling.demo import FIXTURE_TIME, TEST_POLICY, load_fixture, make_state
from strategy.rolling.economy import EconomyObjective
from strategy.rolling.model import DOMAIN, RoundRule
from strategy.rolling.search import Budget, plan
from strategy.rolling.actions import revalidate
from strategy.state import reduce_observation

ROOT = Path(__file__).resolve().parents[1]
ASSUMPTION = EconomyObjective(reserve_target=2, value_per_credit=3)


class EconomyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        _, worlds = load_fixture(ROOT / "examples/strategy_synthetic/rolling/scenarios.json")
        original = worlds["pivot"]
        cls.world = replace(original, version="synthetic-resource-options-1", rounds=(
            replace(original.rounds[0], offers=("B", "C")),))

    def state(self, *, credits=2, board=("A",), hand=(), offers=("B", "C"),
              opponent=("enemy-base", "guard"), **kwargs):
        return make_state(self.world, board_ids=board, hand_ids=hand, offer_ids=offers,
                          credits=credits, opponent_board=opponent, **kwargs)

    def decision(self, state, *, now=FIXTURE_TIME, **kwargs):
        return plan(state, self.world, "toy-opponent", now=now, policy=TEST_POLICY,
                    budget=Budget(horizon=1), economy=ASSUMPTION, **kwargs)

    def label(self, result):
        return result.selected.move.label if result.selected else None

    def test_same_offers_change_with_cash_and_existing_link_support(self):
        no_support_low = self.decision(self.state(board=()))
        no_support_high = self.decision(self.state(board=(), credits=5))
        supported_low = self.decision(self.state())
        self.assertEqual(self.label(no_support_low), "end_round")
        self.assertEqual(self.label(no_support_high), "buy:B")
        self.assertEqual(self.label(supported_low), "buy:C")
        self.assertEqual(no_support_low.alternatives[0].total_utility, 6)
        self.assertEqual(no_support_high.alternatives[0].total_utility, 12)
        chosen = supported_low.alternatives[0]
        self.assertEqual(chosen.total_utility, 14)
        self.assertEqual(chosen.terminal_resource_value, 3)
        self.assertEqual(chosen.resource_value_delta_from_root, -3)
        self.assertEqual(dict(chosen.rounds[0].profiles[0].pair_links), {"pair-ac": 8})
        baseline = plan(self.state(board=()), self.world, "toy-opponent", now=FIXTURE_TIME,
                        policy=TEST_POLICY, budget=Budget(horizon=1))
        self.assertEqual(self.label(baseline), "buy:B")
        self.assertEqual(baseline.economy, EconomyObjective())

    def test_current_opponent_memory_changes_joint_value_and_partial_view_is_robust(self):
        state = self.state()
        prior = self.decision(state)
        self.assertEqual(self.label(prior), "buy:C")
        seen = FIXTURE_TIME + timedelta(milliseconds=1)
        change = Observation("fresh-counter", state.match_id, "opponent", seen, seen,
                             Source("synthetic", DOMAIN + ":resource-option-contrast"),
                             round=1, phase=self.world.phase, opponent_id="toy-opponent", coverage="full",
                             fields=(FieldValue("board_ids", "observed", ("enemy-base", "breaker"), 0.95),))
        updated = reduce_observation(state, change, now=seen)
        revised = self.decision(updated, now=seen)
        self.assertEqual(self.label(revised), "end_round")
        self.assertEqual(revised.alternatives[0].total_utility, 7)
        self.assertTrue(revalidate(prior.selected, updated, self.world, now=seen, policy=TEST_POLICY))
        rich_counter = self.decision(self.state(credits=5, opponent=("enemy-base", "breaker")))
        self.assertEqual(self.label(rich_counter), "buy:B")
        partial = self.decision(self.state(opponent=("enemy-base",), coverage="partial"))
        self.assertEqual(self.label(partial), "end_round")
        self.assertEqual(set(partial.belief.profile_ids), {"guard", "breaker"})

    def test_same_pivot_is_feasible_but_only_worth_its_joint_cost_with_spare_cash(self):
        poor = self.state(board=("A", "B"), hand=("C", "E"), offers=())
        rich = self.state(board=("A", "B"), hand=("C", "E"), offers=(), credits=5)
        keep, pivot = self.decision(poor), self.decision(rich)
        self.assertEqual(self.label(keep), "end_round")
        self.assertEqual(self.label(pivot), "replace:B->C")
        available = next(x for x in keep.alternatives if x.first_move == "replace:B->C")
        self.assertEqual(available.total_utility, 12)
        self.assertEqual(available.switching_cost, 2)
        self.assertEqual(available.resource_value_delta_from_root, -3)
        self.assertEqual(keep.alternatives[0].total_utility, 13)
        self.assertEqual(pivot.alternatives[0].total_utility, 15)
        self.assertEqual(pivot.alternatives[0].resource_value_delta_from_root, 0)
        banned = self.decision(self.state(board=("A", "B"), hand=("C", "E"), offers=(), credits=5, bans=("C",)))
        self.assertEqual(self.label(banned), "replace:B->E")
        self.assertTrue(any("confirmed_ban" in reasons for _, reasons in banned.root_rejections))

    def test_option_value_is_recorded_once_and_cannot_rescue_unknown_or_stale_evidence(self):
        state = self.state()
        longer = replace(self.world, version="synthetic-options-two-rounds", rounds=self.world.rounds + (
            RoundRule(2, 0, (), 2, 1),))
        observed = make_state(longer, board_ids=("A",), offer_ids=("B", "C"), credits=2,
                              opponent_board=("enemy-base", "guard"))
        result = plan(observed, longer, "toy-opponent", now=FIXTURE_TIME, policy=TEST_POLICY,
                      budget=Budget(horizon=2), economy=ASSUMPTION)
        preserve = next(x for x in result.alternatives if x.first_move == "end_round")
        self.assertEqual(preserve.total_utility, 8)  # two board points plus one reserve value of six
        self.assertEqual(preserve.terminal_resource_value, 6)
        self.assertEqual(to_dict(result)["economy"]["origin"], "declared_strategy_assumption_not_game_rule")
        for bad in (self.state(unknown=("credits",)), self.state(memory_age=21)):
            self.assertIsNone(self.decision(bad).selected)
        self.assertIsNone(self.decision(state, cancelled=lambda: True).selected)
        self.assertFalse(result.execution_allowed)
        with self.assertRaises(ValueError):
            EconomyObjective(reserve_target=2, value_per_credit=None)
        with self.assertRaises(ValueError):
            EconomyObjective(reserve_target=2, value_per_credit=float("nan"))

    def test_objective_uses_existing_simulator_and_audit_without_new_engine_features(self):
        from strategy.simulation.runner import run_episode
        from strategy.simulation.toy import OPPONENT, ToySimulator
        def policy(request):
            decision = plan(request.state, request.world, OPPONENT, now=request.state.last_seen,
                            policy=TEST_POLICY, budget=Budget(horizon=1), economy=ASSUMPTION)
            if decision.selected is None:
                return None
            return next(x for x in request.legal_actions if x.move == decision.selected.move)
        report = run_episode(ToySimulator, policy, seed=7, scenario="synthetic-economy-v1", clock=lambda: 0)
        self.assertEqual(report.status, "completed")
        self.assertEqual(report.terminal.completed_rounds, 3)
        self.assertEqual(len(report.audit_events), report.steps + 1)
        self.assertEqual(report.real_match_results, 0)
        self.assertFalse(report.execution_allowed)


if __name__ == "__main__":
    unittest.main()
