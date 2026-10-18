"""A prohibited active unit cannot earn formation utility or next-round income."""
from dataclasses import replace
from pathlib import Path
import unittest

from strategy.contracts import FieldValue, Observation, Source, digest, to_dict
from strategy.rolling.actions import revalidate
from strategy.rolling.demo import FIXTURE_TIME, TEST_POLICY, load_fixture, make_state
from strategy.rolling.economy import EconomyObjective
from strategy.rolling.model import DOMAIN, Move, RoundRule, read_position, transition
from strategy.rolling.search import Budget, plan
from strategy.state import reduce_observation

ROOT = Path(__file__).resolve().parents[1]


class FormationBanTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        _, worlds = load_fixture(ROOT / "examples/strategy_synthetic/rolling/scenarios.json")
        cls.world = worlds["pivot"]

    def state(self, world=None, **changes):
        values = dict(board_ids=("A", "B"), hand_ids=("C", "E"), credits=1, bans=("A",),
                      opponent_board=("enemy-base", "guard"))
        values.update(changes)
        return make_state(world or self.world, **values)

    def decision(self, state, world=None, **changes):
        values = dict(now=FIXTURE_TIME, policy=TEST_POLICY, budget=Budget(horizon=1))
        values.update(changes)
        return plan(state, world or self.world, "toy-opponent", **values)

    def test_banned_anchor_no_longer_wins_through_an_untargeted_link(self):
        allowed = self.decision(self.state(bans=()))
        self.assertEqual(allowed.selected.move.label, "replace:B->C")
        self.assertEqual(allowed.alternatives[0].total_utility, 9)
        banned_state = self.state()
        before = digest(banned_state)
        result = self.decision(banned_state)
        self.assertEqual(result.selected.move.label, "replace:A->E")
        chosen = result.alternatives[0]
        self.assertEqual(chosen.total_utility, 7)  # B/E formation 9 minus switching cost 2.
        self.assertEqual(chosen.switching_cost, 2)
        self.assertEqual(chosen.resource_ledger[0].credits_spent, 1)
        self.assertEqual(chosen.terminal_position.board_ids, ("B", "E"))
        self.assertEqual(chosen.rounds[0].profiles[0].pair_links, ())
        self.assertTrue(all("A" not in round.board_ids for alt in result.alternatives for round in alt.rounds))
        self.assertIn(("end_round", ("confirmed_ban_on_board:A",)), result.root_rejections)
        self.assertEqual(to_dict(result)["root_formation_conflicts"],
                         [dict(unit_id="A", matched_bans=["A"])])
        self.assertEqual(digest(banned_state), before)
        tagged = replace(self.world, version="synthetic-banned-anchor-tag", cards=tuple(
            replace(card, ban_tags=("prohibited-anchor",)) if card.unit_id == "A" else card
            for card in self.world.cards))
        tagged_result = self.decision(self.state(tagged, bans=("prohibited-anchor",)), tagged)
        self.assertEqual(tagged_result.selected.move.label, "replace:A->E")
        self.assertEqual(tagged_result.root_formation_conflicts[0].matched_bans, ("prohibited-anchor",))
        held_only = self.decision(self.state(bans=("C",)))
        self.assertEqual(held_only.root_formation_conflicts, ())
        self.assertEqual(held_only.selected.move.label, "replace:B->E")

    def test_future_income_cannot_finance_repair_after_an_illegal_settlement(self):
        world = replace(self.world, version="synthetic-bans-two-rounds", rounds=self.world.rounds + (
            RoundRule(2, 2, (), 2, 1),))
        state = self.state(world, credits=0)
        position, _ = read_position(state, world)
        with self.assertRaisesRegex(ValueError, "confirmed_ban_on_board:A"):
            transition(position, world, Move("end_round"), bans=state.confirmed_bans, final_round=2)
        self.assertEqual((position.round, position.credits), (1, 0))
        result = self.decision(state, world, budget=Budget(horizon=2))
        self.assertEqual((result.status, result.selected.move.label), ("fallback", "hold"))
        self.assertEqual(result.alternatives, ())
        self.assertEqual(result.completed_paths, 0)
        self.assertIn("hold_does_not_settle_or_resolve_bans", result.reasons)
        self.assertFalse(result.horizon_exhausted)
        funded = self.decision(self.state(world), world, budget=Budget(horizon=2),
                               economy=EconomyObjective(reserve_target=2, value_per_credit=3))
        self.assertEqual(funded.selected.move.label, "replace:A->E")
        best = funded.alternatives[0]
        self.assertEqual(best.total_utility, 22)  # 9 + 9 - 2 + one terminal reserve 6.
        self.assertEqual(sum(step.credits_spent for step in best.resource_ledger), 1)
        self.assertEqual(sum(step.income_received for step in best.resource_ledger), 2)
        self.assertEqual(best.terminal_position.credits, 2)
        self.assertTrue(all("A" not in round.board_ids for round in best.rounds))
        self.assertFalse(funded.execution_allowed)

    def test_ban_updates_unknown_costs_and_budget_do_not_waive_the_constraint(self):
        state = self.state(bans=(), hand_ids=())
        old = self.decision(state)
        self.assertEqual(old.selected.move.label, "end_round")
        event = Observation("ban-active-anchor", state.match_id, "bans", FIXTURE_TIME, FIXTURE_TIME,
                            Source("synthetic", DOMAIN + ":formation-ban"), round=1, phase=self.world.phase,
                            fields=(FieldValue("banned_tags", "observed", ("A",), .95),))
        changed = reduce_observation(state, event, now=FIXTURE_TIME)
        self.assertIn("candidate_ban_version_changed", revalidate(old.selected, changed, self.world,
                                                                 now=FIXTURE_TIME, policy=TEST_POLICY))
        late = self.decision(state, latest_snapshot=lambda: (changed, self.world))
        self.assertIsNone(late.selected)
        self.assertIn("final_revalidation_failed", late.reasons)
        unknown = replace(self.world, version="synthetic-repair-cost-unknown", replace_credit_cost=None)
        refused = self.decision(self.state(unknown), unknown)
        self.assertIsNone(refused.selected)
        self.assertIn("transition_cost_unknown", refused.reasons)
        bounded = self.decision(self.state(), budget=Budget(horizon=1, max_nodes=0))
        self.assertEqual(bounded.selected.move.label, "hold")
        self.assertEqual(bounded.alternatives, ())
        self.assertFalse(bounded.horizon_exhausted)
        self.assertIsNone(self.decision(self.state(memory_age=21)).selected)
        self.assertIsNone(self.decision(self.state(), cancelled=lambda: True).selected)


if __name__ == "__main__":
    unittest.main()
