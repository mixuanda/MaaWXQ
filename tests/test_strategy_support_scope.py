"""Relevant unknowns block decisions; provably unused parameters stay unknown."""
from dataclasses import replace
from datetime import timedelta
from pathlib import Path
import unittest

from strategy.contracts import FieldValue, Observation, Source, digest, to_dict
from strategy.rolling.actions import revalidate
from strategy.rolling.demo import FIXTURE_TIME, TEST_POLICY, load_fixture, make_state
from strategy.rolling.model import DOMAIN, RoundRule, ThresholdLink, support_reasons
from strategy.rolling.search import Budget, plan
from strategy.state import reduce_observation

ROOT = Path(__file__).resolve().parents[1]


class SupportScopeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        _, worlds = load_fixture(ROOT / "examples/strategy_synthetic/rolling/scenarios.json")
        cls.base = worlds["pivot"]

    def unknown_c(self):
        return replace(self.base, version="synthetic-support-scope-1",
                       cards=tuple(replace(card, value=None, price=None) if card.unit_id == "C" else card
                                   for card in self.base.cards),
                       pairs=tuple(replace(link, value=None) if "C" in link.units else link
                                   for link in self.base.pairs))

    def state(self, world, **changes):
        values = dict(board_ids=("A", "B"), hand_ids=("C", "E"), credits=1, capacity=2,
                      bans=("C",), opponent_board=("enemy-base", "guard"))
        values.update(changes)
        return make_state(world, **values)

    def decision(self, world, state, **changes):
        values = dict(now=FIXTURE_TIME, policy=TEST_POLICY, budget=Budget(horizon=1))
        values.update(changes)
        return plan(state, world, "toy-opponent", **values)

    def test_confirmed_ban_unblocks_known_pivot_without_filling_unknowns(self):
        world = self.unknown_c()
        # This is the exact whole-world check used before scoped planning.
        self.assertIn("unit_value_or_price_unknown", support_reasons(world, 1, 1))
        before = digest(world)
        result = self.decision(world, self.state(world))
        self.assertEqual(result.selected.move.label, "replace:B->E")
        best = result.alternatives[0]
        self.assertEqual(best.total_utility, 8)  # known A/E formation 10 minus switching cost 2
        self.assertEqual(dict(best.rounds[0].profiles[0].pair_links), {"pair-ae": 6})
        self.assertEqual(result.support_scope.potential_unit_ids, ("A", "B", "E"))
        self.assertEqual(result.support_scope.required_link_ids, ("pair-ae",))
        self.assertEqual(result.support_scope.excluded_unknowns,
                         ("card:C:price", "card:C:value", "link:pair-ac:value"))
        self.assertEqual(result.support_scope.required_unknowns, ())
        self.assertTrue(any("confirmed_ban" in why for _, why in result.root_rejections))
        self.assertEqual(digest(world), before)
        self.assertIsNone(world.card("C").value)
        self.assertFalse(result.execution_allowed)
        self.assertEqual(to_dict(result)["support_scope"]["purchase_unit_ids"], [])
        unresolved = self.decision(world, self.state(world, bans=()))
        self.assertIsNone(unresolved.selected)
        self.assertIn("interaction_utility_unknown", unresolved.reasons)
        self.assertIn("card:C:value", unresolved.support_scope.required_unknowns)
        still_on_board = self.decision(world, self.state(world, board_ids=("A", "C"), hand_ids=("E",)))
        self.assertIsNone(still_on_board.selected)
        self.assertIn("C", still_on_board.support_scope.potential_unit_ids)

    def test_unknown_acquisition_price_is_only_required_for_possible_purchase(self):
        world = replace(self.base, version="synthetic-owned-price-unknown",
                        cards=tuple(replace(card, price=None) if card.unit_id == "C" else card
                                    for card in self.base.cards))
        owned = self.decision(world, self.state(world, board_ids=("A",), hand_ids=("C",), bans=()))
        self.assertEqual(owned.selected.move.label, "deploy:C")
        self.assertEqual(owned.alternatives[0].total_utility, 11)
        self.assertIn("card:C:price", owned.support_scope.excluded_unknowns)
        shop_world = replace(world, version="synthetic-offered-price-unknown", rounds=(
            replace(world.rounds[0], offers=("C",)),))
        offered = self.decision(shop_world, self.state(shop_world, board_ids=("A",), hand_ids=(),
                                                       offer_ids=("C",), bans=()))
        self.assertIsNone(offered.selected)
        self.assertIn("unit_value_or_price_unknown", offered.reasons)
        banned_offer = self.decision(shop_world, self.state(shop_world, hand_ids=("E",), offer_ids=("C",)))
        self.assertEqual(banned_offer.selected.move.label, "replace:B->E")
        self.assertIn(("buy:C", ("confirmed_ban", "price_unknown")), banned_offer.root_rejections)

    def test_current_horizon_does_not_hide_an_unknown_in_a_declared_future_offer(self):
        world = self.unknown_c()
        world = replace(world, version="synthetic-support-two-rounds",
                        rounds=world.rounds + (RoundRule(2, 2, ("C",), 2, 1),))
        state = self.state(world, hand_ids=("E",), bans=())
        current = self.decision(world, state)
        self.assertEqual(current.selected.move.label, "replace:B->E")
        self.assertNotIn("C", current.support_scope.potential_unit_ids)
        longer = self.decision(world, state, budget=Budget(horizon=2))
        self.assertIsNone(longer.selected)
        self.assertIn("C", longer.support_scope.purchase_unit_ids)
        self.assertIn("unit_value_or_price_unknown", longer.reasons)
        prohibited = self.decision(world, self.state(world, hand_ids=("E",)), budget=Budget(horizon=2))
        # The second round still expands to both declared opponent profiles.
        # Keeping B beside E avoids relying on a link the breaker disables.
        self.assertEqual(prohibited.selected.move.label, "replace:A->E")
        self.assertEqual(prohibited.alternatives[0].total_utility, 16)

    def test_possible_unknown_links_still_block_and_impossible_thresholds_do_not(self):
        world = replace(self.base, version="synthetic-active-link-unknown",
                        pairs=tuple(replace(link, value=None) if link.link_id == "pair-ae" else link
                                    for link in self.base.pairs))
        unknown_pair = self.decision(world, self.state(world))
        self.assertIsNone(unknown_pair.selected)
        self.assertIn("interaction_utility_unknown", unknown_pair.reasons)
        role = "synthetic-scope-role"
        threshold = replace(self.base, version="synthetic-threshold-support",
                            cards=tuple(replace(card, roles=(*card.roles, role))
                                        if card.unit_id in ("A", "C", "E") else card for card in self.base.cards),
                            thresholds=(ThresholdLink("unknown-three", role, 3, None),),
                            rounds=(replace(self.base.rounds[0], capacity=3),))
        limited = self.decision(threshold, self.state(threshold, capacity=3))
        self.assertEqual(limited.selected.move.label, "deploy:E")
        self.assertIn("link:unknown-three:value", limited.support_scope.excluded_unknowns)
        possible = self.decision(threshold, self.state(threshold, capacity=3, bans=()))
        self.assertIsNone(possible.selected)
        self.assertIn("unknown-three", possible.support_scope.required_link_ids)

    def test_revalidation_bans_memory_and_opt_in_remain_independent(self):
        world = self.unknown_c()
        state = self.state(world)
        prior = self.decision(world, state)
        event = Observation("ban-known-pivot", state.match_id, "bans", FIXTURE_TIME, FIXTURE_TIME,
                            Source("synthetic", DOMAIN + ":support-scope-ban"), round=1, phase=world.phase,
                            fields=(FieldValue("banned_tags", "observed", ("E",), 0.95),))
        updated = reduce_observation(state, event, now=FIXTURE_TIME)
        self.assertIn("candidate_ban_version_changed",
                      revalidate(prior.selected, updated, world, now=FIXTURE_TIME, policy=TEST_POLICY))
        self.assertEqual(self.decision(world, updated).selected.move.label, "end_round")
        self.assertIsNone(self.decision(world, state, latest_snapshot=lambda: (updated, world)).selected)
        self.assertIsNone(self.decision(world, self.state(world, memory_age=21)).selected)
        self.assertIsNone(self.decision(world, state, cancelled=lambda: True).selected)
        default = plan(state, world, "toy-opponent", now=FIXTURE_TIME, budget=Budget(horizon=1))
        self.assertIsNone(default.selected)
        self.assertIn("test_rules_require_explicit_opt_in", default.reasons)
        expired = revalidate(prior.selected, state, world, now=FIXTURE_TIME + timedelta(seconds=21),
                             policy=TEST_POLICY)
        self.assertTrue(expired)


if __name__ == "__main__":
    unittest.main()
