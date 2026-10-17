"""Behavioral contrasts and fallbacks for the explicitly synthetic planner."""

from dataclasses import replace
from datetime import timedelta
import json
from pathlib import Path
import subprocess
import sys
import unittest

from strategy.codec import timestamp
from strategy.contracts import to_dict
from strategy.planning.candidates import TEST_POLICY, generate, revalidate, step
from strategy.planning.demo import case_state, comparison, training_groups, world_from_dict
from strategy.planning.model import Scenario, make_state, position
from strategy.planning.ranker import AdditiveEvaluator, ExactEvaluator, LinearRanker, fit_ranker
from strategy.planning.search import Budget, plan

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "examples/strategy_synthetic/planning/benchmark.json"
DATA = json.loads(FIXTURE.read_text(encoding="utf-8"))
NOW = timestamp(DATA["decision_at"])


class PlanningTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.world = world_from_dict(DATA["heldout_world"])
        cls.groups = training_groups(DATA)
        cls.fit = fit_ranker(cls.groups, **DATA["training_settings"])
        cls.ablated = fit_ranker(cls.groups, include_interactions=False, **DATA["training_settings"])

    def case(self, case_id):
        return case_state(self.world, next(x for x in DATA["cases"] if x["case_id"] == case_id), NOW)

    def run_plan(self, case_id="pair_synergy", **kwargs):
        state, scenarios = self.case(case_id)
        return plan(state, self.world, now=NOW, policy=TEST_POLICY, scenarios=scenarios, **kwargs)

    def test_nonadditive_two_step_choice_beats_independent_cards(self):
        additive = self.run_plan(evaluator=AdditiveEvaluator())
        planned = self.run_plan()
        self.assertEqual(additive.selected.label, "buy:B")
        self.assertEqual(planned.selected.label, "buy:C")
        self.assertEqual(planned.contingent_path, ("buy:C", "deploy:C"))
        chosen = next(x for x in planned.alternatives if x.first_action == planned.selected)
        self.assertEqual(chosen.predicted_board, ("A", "C"))
        self.assertEqual(chosen.leaves[0].declared_toy_utility, 11)
        self.assertEqual(chosen.interactions_gained, ("link-ac",))
        self.assertEqual(next(x.score for x in planned.alternatives if x.first_action.label == "buy:B"), 7)
        short = self.run_plan(budget=Budget(max_depth=1))
        self.assertEqual(short.selected.kind, "hold")
        self.assertFalse(planned.execution_allowed)
        self.assertIsNone(planned.placement_probabilities)

    def test_opportunity_threat_and_replacement_contrasts(self):
        expected = {"without_support": "buy:B", "banned_c": "buy:B", "no_energy": "hold",
                    "opponent_counter": "buy:B", "plausible_opponent_counter": "buy:B",
                    "replacement_breaks_link": "hold", "higher_order": "buy:C"}
        for case_id, label in expected.items():
            with self.subTest(case_id=case_id):
                self.assertEqual(self.run_plan(case_id).selected.label, label)
        original = self.run_plan("replacement_breaks_link")
        destructive = next(x for x in original.alternatives if x.first_action.label == "replace:A->D")
        self.assertEqual(destructive.interactions_lost, ("link-ac",))
        self.assertEqual(destructive.leaves[0].utility_delta_from_root, -4)
        self.assertEqual(self.run_plan("replacement_breaks_link", evaluator=AdditiveEvaluator()).selected.label,
                         "replace:A->D")
        triple = self.run_plan("higher_order")
        leaf = next(x for x in triple.alternatives if x.first_action == triple.selected).leaves[0]
        self.assertEqual(dict(leaf.active_interactions), {"link-ac": 8, "triple-acd": 4})

    def test_dynamic_generation_and_successors_obey_actual_offers_and_capacity(self):
        state, _ = self.case("pair_synergy")
        original = state
        batch = generate(state, self.world, now=NOW, policy=TEST_POLICY)
        self.assertEqual({x.label for x in batch.actions}, {"hold", "buy:B", "buy:C"})
        bought = step(state, self.world, next(x for x in batch.actions if x.label == "buy:C"),
                      now=NOW, policy=TEST_POLICY)
        next_batch = generate(bought, self.world, now=NOW, policy=TEST_POLICY)
        self.assertIn("deploy:C", {x.label for x in next_batch.actions})
        self.assertNotIn("buy:C", {x.label for x in next_batch.actions})
        self.assertEqual(position(bought, self.world)[0].credits, 1)
        self.assertEqual(state, original)
        forged = replace(next(x for x in batch.actions if x.kind == "buy"), unit_id="D")
        self.assertTrue(revalidate(forged, state, self.world, now=NOW, policy=TEST_POLICY))
        with self.assertRaises(ValueError):
            step(state, self.world, forged, now=NOW, policy=TEST_POLICY)

    def test_cpu_ranker_is_replaceable_serializable_and_cannot_override_bans(self):
        self.assertLess(self.fit.final_loss, self.fit.initial_loss)
        self.assertEqual(self.run_plan(evaluator=self.fit.model).selected.label, "buy:C")
        self.assertEqual(self.run_plan(evaluator=self.ablated.model).selected.label, "buy:B")
        restored = LinearRanker.from_dict(to_dict(self.fit.model))
        self.assertEqual(restored, self.fit.model)
        self.assertNotIn(DATA["split_manifest"]["heldout_family"], restored.trained_family_ids)
        extreme = replace(restored, weights=(0.0, 1e9, 1e9))
        banned = self.run_plan("banned_c", evaluator=extreme)
        self.assertNotEqual(banned.selected.label, "buy:C")
        self.assertIn("confirmed_ban", dict(banned.root_rejections)["buy:C"])
        with self.assertRaises(ValueError):
            LinearRanker.from_dict(to_dict(restored) | {"feature_version": "unknown"})
        with self.assertRaisesRegex(ValueError, "training_cancelled"):
            fit_ranker(self.groups, cancelled=lambda: True)

    def test_cancel_time_nodes_and_unavailable_evaluator_fall_back_safely(self):
        self.assertIsNone(self.run_plan(cancelled=lambda: True).selected)
        calls = [0]
        def cancel_during_search():
            calls[0] += 1
            return calls[0] > 4
        cancelled = self.run_plan(cancelled=cancel_during_search)
        self.assertIsNone(cancelled.selected)
        self.assertEqual(cancelled.termination, "cancelled")
        limited = self.run_plan(budget=Budget(max_nodes=1))
        self.assertEqual(limited.status, "fallback")
        self.assertEqual(limited.selected.kind, "hold")
        self.assertEqual(limited.termination, "node_budget_exhausted")
        elapsed = [0.0]
        class Delayed(ExactEvaluator):
            def score(self, value):
                elapsed[0] += 2
                return super().score(value)
        timed = self.run_plan(evaluator=Delayed(), clock=lambda: elapsed[0], budget=Budget(max_seconds=1))
        self.assertEqual(timed.termination, "time_budget_exhausted")
        self.assertEqual(timed.selected.kind, "hold")
        class Unavailable(ExactEvaluator):
            def score(self, value):
                raise RuntimeError("offline model unavailable")
        missing = self.run_plan(evaluator=Unavailable())
        self.assertEqual(missing.status, "fallback")
        self.assertEqual(missing.selected.kind, "hold")

    def test_final_gate_rejects_new_bans_rules_and_unavailable_snapshot(self):
        state, scenarios = self.case("pair_synergy")
        changed = make_state(self.world, now=NOW, board_ids=("A",), offer_ids=("B", "C"), bans=("C",))
        changed = replace(changed, state_version=state.state_version + 1, ban_version=state.ban_version + 1)
        result = plan(state, self.world, now=NOW, policy=TEST_POLICY, scenarios=scenarios,
                      latest_snapshot=lambda: (changed, self.world))
        self.assertIsNone(result.selected)
        self.assertIn("final_revalidation_failed", result.reasons)
        self.assertIn("candidate_ban_version_changed", result.reasons)
        revised = replace(self.world, interactions=())
        result = plan(state, self.world, now=NOW, policy=TEST_POLICY,
                      latest_snapshot=lambda: (state, revised))
        self.assertIsNone(result.selected)
        self.assertIn("world_rules_changed", result.reasons)
        def unavailable():
            raise RuntimeError("no current snapshot")
        self.assertIsNone(self.run_plan(latest_snapshot=unavailable).selected)

    def test_unknown_stale_unverified_and_unapproved_domains_abstain(self):
        self.assertIsNone(self.run_plan("unknown_resource").selected)
        state, _ = self.case("pair_synergy")
        self.assertIsNone(plan(state, self.world, now=NOW).selected)
        self.assertIsNone(plan(state, replace(self.world, verification="unverified"),
                               now=NOW, policy=TEST_POLICY).selected)
        self.assertIsNone(plan(state, self.world, now=NOW + timedelta(seconds=31), policy=TEST_POLICY).selected)
        self.assertIsNone(plan(state, self.world, now=NOW, policy=TEST_POLICY,
                               scenarios=(Scenario(support="unknown"),)).selected)
        with self.assertRaises(ValueError):
            replace(self.world, domain="gameplay")
        inactive = comparison(DATA)
        self.assertFalse(inactive["training_executed"])

    def test_reproducible_choices_and_disconnected_cpu_cli(self):
        first = self.run_plan(evaluator=self.fit.model)
        second = self.run_plan(evaluator=self.fit.model)
        self.assertEqual(first.selected, second.selected)
        self.assertEqual(first.alternatives, second.alternatives)
        script = '''
import importlib.abc,runpy,sys
class Offline(importlib.abc.MetaPathFinder):
    def find_spec(self,fullname,path=None,target=None):
        if fullname.split('.')[0] in {'ctypes','capture','capture_backend','main','socket',
                                     'openai','requests','torch','tensorflow','transformers','pyautogui','pynput'}:
            raise RuntimeError('Forbidden dependency: '+fullname)
sys.meta_path.insert(0,Offline())
sys.argv=['strategy.planning','--fixture',sys.argv[1],'--allow-test-rules','--timing-repeats','1']
runpy.run_module('strategy.planning',run_name='__main__')
'''
        process = subprocess.run([sys.executable, "-B", "-c", script, str(FIXTURE)], cwd=ROOT,
                                 capture_output=True, text=True, timeout=30, check=True)
        report = json.loads(process.stdout)
        self.assertFalse(report["execution_allowed"])
        self.assertEqual(report["real_match_results"], 0)
        pair = next(x for x in report["cases"] if x["case_id"] == "pair_synergy")["results"]
        self.assertEqual(pair["interaction_depth_two"]["declared_toy_utility"], 11)
        self.assertEqual(pair["independent_card_baseline"]["declared_toy_utility"], 7)
        self.assertEqual(pair["cpu_ranker_depth_two"]["selected"], "buy:C")


class AvailabilityTests(unittest.TestCase):
    """Callback failure regressions that never fit or download a model."""

    def setUp(self):
        self.world = world_from_dict(DATA["heldout_world"])
        self.state, self.scenarios = case_state(self.world, DATA["cases"][0], NOW)

    def test_ordinary_evaluator_failures_return_validated_hold(self):
        for error_type in (OSError, LookupError, TypeError):
            with self.subTest(error=error_type.__name__):
                class Unavailable(ExactEvaluator):
                    def score(self, value):
                        raise error_type("synthetic evaluator unavailable")
                result = plan(self.state, self.world, now=NOW, policy=TEST_POLICY,
                              scenarios=self.scenarios, evaluator=Unavailable())
                self.assertEqual(result.status, "fallback")
                self.assertEqual(result.selected.kind, "hold")
                self.assertEqual(result.final_gate, "passed_advice_only")
                self.assertIn("unsupported_evaluation_or_transition:" + error_type.__name__, result.reasons)
                self.assertFalse(result.execution_allowed)

    def test_ordinary_snapshot_failures_abstain(self):
        for error_type in (OSError, LookupError, TypeError):
            with self.subTest(error=error_type.__name__):
                def unavailable():
                    raise error_type("synthetic snapshot unavailable")
                result = plan(self.state, self.world, now=NOW, policy=TEST_POLICY,
                              scenarios=self.scenarios, latest_snapshot=unavailable)
                self.assertEqual(result.status, "abstain")
                self.assertIsNone(result.selected)
                self.assertEqual(result.termination, "final_snapshot_unavailable")
                self.assertIn("final_snapshot_unavailable", result.reasons)
                self.assertFalse(result.execution_allowed)


if __name__ == "__main__":
    unittest.main()
