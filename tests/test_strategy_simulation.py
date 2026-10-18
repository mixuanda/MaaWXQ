"""Visibility, accounting and harness contracts using original synthetic data."""

from dataclasses import FrozenInstanceError, replace
import json
from pathlib import Path
import unittest

from strategy.contracts import Source, to_dict
from strategy.policy import Policy
from strategy.rolling.model import Move, RoundRule, read_position
from strategy.rolling.search import Budget, plan
from strategy.simulation.bridge import decision_input, rolling_policy
from strategy.simulation.contracts import IllegalAction, SimAction, SimulatorError, StepReceipt, TerminalResult, replay_record
from strategy.simulation.runner import RunBudget, run_episode
from strategy.simulation.toy import OPPONENT, PLAYER, ToySimulator

ROOT = Path(__file__).resolve().parents[1]
SCENARIO = "synthetic-economy-v1"
GOLDEN = json.loads((ROOT / "examples/strategy_synthetic/simulation/seed7.json").read_text("utf-8"))


def end_round(request):
    return next(x for x in request.legal_actions if x.move.kind == "end_round")


def initialized(seed=7, scenario=SCENARIO):
    sim = ToySimulator()
    sim.reset(seed, scenario)
    return sim


def action(sim, label):
    return next(x for x in sim.legal_actions(PLAYER) if x.move.label == label)


class SimulationTests(unittest.TestCase):
    def test_seeded_replay_and_independent_instances(self):
        runs = [run_episode(ToySimulator, end_round, seed=7, scenario=SCENARIO) for _ in range(2)]
        self.assertNotEqual(runs[0].metadata.episode_id, runs[1].metadata.episode_id)
        self.assertEqual(replay_record(runs[0]), replay_record(runs[1]))
        self.assertEqual(runs[0].status, "completed")
        self.assertEqual(runs[0].terminal.completed_rounds, 3)
        self.assertEqual(runs[0].real_match_results, 0)
        self.assertIsNone(runs[0].terminal.placement)
        self.assertIsNone(runs[0].metadata.engine_commit)
        self.assertEqual(len(runs[0].metadata.engine_source_digest), 64)
        first, second = initialized(), initialized()
        before = second.audit_snapshot()
        first.step(action(first, "end_round"))
        self.assertEqual(second.audit_snapshot(), before)
        self.assertNotEqual(initialized(8).audit_snapshot().hidden_offers, before.hidden_offers)

    def test_lifecycle_and_parameter_rejection_do_not_mutate(self):
        sim = ToySimulator()
        for call in (lambda: sim.observe(PLAYER), lambda: sim.legal_actions(PLAYER),
                     sim.terminal_result, sim.export_events, sim.audit_snapshot,
                     lambda: sim.step(SimAction(PLAYER, 0, Move("hold"), "not-started"))):
            with self.assertRaises(SimulatorError):
                call()
        for seed in (-1, True, 2**64, "7"):
            with self.assertRaises(ValueError):
                sim.reset(seed, SCENARIO)
        with self.assertRaises(ValueError):
            sim.reset(7, "unregistered-scenario")
        sim.reset(7, SCENARIO)
        before = sim.audit_snapshot()
        with self.assertRaises(SimulatorError):
            sim.reset(8, SCENARIO)
        with self.assertRaises(SimulatorError):
            sim.observe("player-1")
        with self.assertRaises(SimulatorError):
            sim.legal_actions("player-1")
        self.assertEqual(sim.audit_snapshot(), before)

    def test_visibility_is_invariant_under_unseen_state_changes(self):
        sim = initialized()
        view, legal = sim.observe(PLAYER), sim.legal_actions(PLAYER)
        request = decision_input(view, legal)
        wire = to_dict(request)

        def keys(value):
            if isinstance(value, dict):
                return set(value) | set().union(*(keys(x) for x in value.values()), set())
            if isinstance(value, list):
                return set().union(*(keys(x) for x in value), set())
            return set()

        self.assertFalse(keys(wire) & {"seed", "hidden_offers", "opponent_hand", "rng_state", "metadata"})
        self.assertEqual([x.round for x in request.world.rounds], [1])
        self.assertNotIn(sim.audit_snapshot().opponent_hand[0], json.dumps(wire))
        # Test-auditor access only: alter hidden future/private state and prove
        # both observations and legal choices stay identical before revelation.
        sim._hidden = (sim._hidden[0], tuple(reversed(sim._hidden[1])), sim._hidden[2])
        sim._opponent_hand = ("different-private-reserve",)
        sim._rng.random()
        self.assertEqual(sim.observe(PLAYER), view)
        self.assertEqual(sim.legal_actions(PLAYER), legal)
        self.assertEqual(decision_input(sim.observe(PLAYER), legal), request)
        self.assertEqual(rolling_policy(request), rolling_policy(decision_input(sim.observe(PLAYER), legal)))
        with self.assertRaises(FrozenInstanceError):
            view.revision = 99

    def test_golden_resource_ledger_and_terminal_boundary(self):
        sim = initialized(GOLDEN["seed"], GOLDEN["scenario"])
        self.assertIsNone(sim.terminal_result())
        for index, label in enumerate(GOLDEN["actions"]):
            receipt = sim.step(action(sim, label))
            ledger = sim.export_events()[-1].ledger
            self.assertEqual(ledger.credits_after, GOLDEN["expected_credits_after"][index])
            self.assertEqual(ledger.credits_spent, GOLDEN["expected_spent"][index])
            self.assertEqual(ledger.income_received, GOLDEN["expected_income"][index])
            self.assertEqual(ledger.next_round, GOLDEN["expected_round_after"][index])
            self.assertEqual(ledger.credits_after,
                             ledger.credits_before - ledger.credits_spent + ledger.income_received)
            self.assertLessEqual(len(ledger.board_after), ledger.capacity_after)
            self.assertEqual(receipt.terminal, index == len(GOLDEN["actions"]) - 1)
            if not receipt.terminal:
                self.assertIsNone(sim.terminal_result())
        terminal = sim.terminal_result()
        self.assertEqual(terminal.final_credits, 1)
        self.assertEqual(terminal.final_board, tuple(GOLDEN["expected_final_board"]))
        self.assertEqual(sim.audit_snapshot().position.discarded_ids, tuple(GOLDEN["expected_discarded"]))
        self.assertEqual(sim.observe(PLAYER).observations[-1].kind, "match_end")
        self.assertEqual(sim.legal_actions(PLAYER), ())
        self.assert_rejected_unchanged(sim, SimAction(PLAYER, 7, Move("end_round"), sim.observe(PLAYER).episode_id))
        with self.assertRaises(SimulatorError):
            decision_input(sim.observe(PLAYER), ())

    def assert_rejected_unchanged(self, sim, attempt):
        before, events, view = sim.audit_snapshot(), sim.export_events(), sim.observe(PLAYER)
        with self.assertRaises(IllegalAction):
            sim.step(attempt)
        self.assertEqual(sim.audit_snapshot(), before)
        self.assertEqual(sim.export_events(), events)
        self.assertEqual(sim.observe(PLAYER), view)

    def test_illegal_actions_are_atomic_including_resources_bans_and_stale_revision(self):
        sim = initialized(scenario="synthetic-zero-budget-v1")
        self.assertFalse(any(x.move.kind == "buy" for x in sim.legal_actions(PLAYER)))
        self.assert_rejected_unchanged(sim, SimAction(PLAYER, 0, Move("buy", "unit-d"), sim.observe(PLAYER).episode_id))
        sim = initialized()
        episode = sim.observe(PLAYER).episode_id
        for attempt in (None, SimAction("player-1", 0, Move("hold"), episode),
                        SimAction(PLAYER, 0, Move("sell", "unit-a"), episode),
                        SimAction(PLAYER, 0, Move("deploy", "unit-c"), episode),
                        SimAction(PLAYER, 0, Move("buy", "absent"), episode)):
            self.assert_rejected_unchanged(sim, attempt)
        purchase = action(sim, "buy:unit-d")
        sim.step(purchase)
        self.assert_rejected_unchanged(sim, purchase)
        banned = initialized(scenario="synthetic-banned-v1")
        banned.step(action(banned, "end_round"))
        self.assertIn("unit-c", banned.audit_snapshot().position.offer_ids)
        self.assert_rejected_unchanged(banned, SimAction(PLAYER, 1, Move("buy", "unit-c"), banned.observe(PLAYER).episode_id))
        with self.assertRaises(ValueError):
            SimAction(PLAYER, True, Move("hold"), episode)

    def test_existing_strategy_bridge_and_no_future_horizon(self):
        seen = []

        def policy(request):
            seen.append(request)
            pos, why = read_position(request.state, request.world)
            self.assertFalse(why)
            self.assertEqual(pos.credits, next(x.field.value for x in request.state.fields
                                               if x.field.key == "credits"))
            return rolling_policy(request)

        run = run_episode(ToySimulator, policy, seed=7, scenario=SCENARIO)
        self.assertEqual(run.status, "completed")
        self.assertEqual([x.action.move.label for x in run.audit_events[1:]], GOLDEN["actions"])
        request = seen[0]
        result = plan(request.state, request.world, OPPONENT, now=request.state.last_seen,
                      budget=Budget(horizon=2), policy=Policy(allow_test_rules=True))
        self.assertIsNone(result.selected)
        self.assertIn("round_transition_unknown:2", result.reasons)
        self.assertFalse(result.execution_allowed)
        self.assertLess(seen[0].state.state_version, seen[-1].state.state_version)

    def test_bridge_rejects_future_frame_real_evidence_and_wrong_action_binding(self):
        sim = initialized()
        view = sim.observe(PLAYER)
        future = replace(view.world, rounds=view.world.rounds + (RoundRule(2, 1, (), 2, 1),))
        bad_views = (replace(view, world=future), replace(view, observations=(
            replace(view.observations[0], source=Source("manual_annotation", "fixture")),)))
        for bad in bad_views:
            with self.assertRaises(SimulatorError):
                decision_input(bad, sim.legal_actions(PLAYER))
        with self.assertRaises(SimulatorError):
            decision_input(view, (SimAction(PLAYER, 99, Move("hold"), view.episode_id),))

    def test_step_time_and_cancel_budgets_never_claim_completion(self):
        sim = ToySimulator()
        report = run_episode(lambda: sim, end_round, seed=7, scenario=SCENARIO,
                             budget=RunBudget(max_steps=1))
        self.assertEqual((report.status, report.reason, report.steps),
                         ("truncated", "step_budget_exhausted", 1))
        self.assertIsNone(report.terminal)
        self.assertIsNone(sim.terminal_result())
        for budget, why in ((RunBudget(max_steps=0), "step_budget_exhausted"),
                            (RunBudget(max_seconds=0), "time_budget_exhausted")):
            report = run_episode(ToySimulator, end_round, seed=7, scenario=SCENARIO, budget=budget)
            self.assertEqual((report.reason, report.steps), (why, 0))
            self.assertIsNone(report.terminal)
        factory_calls = []
        report = run_episode(lambda: factory_calls.append(True), end_round, seed=7, scenario=SCENARIO,
                             cancelled=lambda: True)
        self.assertEqual((report.status, report.reason), ("cancelled", "cancelled"))
        self.assertFalse(factory_calls)

    def test_deadline_and_cancel_arriving_during_policy_prevent_step(self):
        for mode in ("time", "cancel"):
            with self.subTest(mode=mode):
                sim, ticks, stop = ToySimulator(), [0], [False]

                def policy(request):
                    ticks[0], stop[0] = 10, mode == "cancel"
                    return end_round(request)

                report = run_episode(lambda: sim, policy, seed=7, scenario=SCENARIO,
                                     budget=RunBudget(max_seconds=5), clock=lambda: ticks[0],
                                     cancelled=lambda: stop[0])
                self.assertEqual(report.steps, 0)
                self.assertEqual(sim.audit_snapshot().revision, 0)
                self.assertEqual(report.status, "cancelled" if mode == "cancel" else "truncated")

    def test_cancel_during_adapter_callbacks_stops_dependent_work(self):
        for stage in ("reset", "observe", "legal_actions", "step"):
            with self.subTest(stage=stage):
                stop = [False]
                sim = ToySimulator()
                original = getattr(sim, stage)

                def wrapped(*args):
                    value = original(*args)
                    stop[0] = True
                    return value

                setattr(sim, stage, wrapped)
                report = run_episode(lambda: sim, end_round, seed=7, scenario=SCENARIO,
                                     cancelled=lambda: stop[0])
                self.assertEqual(report.status, "cancelled")
                self.assertIsNone(report.terminal)
                self.assertEqual(report.steps, 1 if stage == "step" else 0)

    def test_exceptions_are_failed_unconfirmed_and_never_retried(self):
        for stage in ("reset", "observe", "legal_actions", "step"):
            with self.subTest(stage=stage):
                sim, calls = ToySimulator(), []
                original = getattr(sim, stage)

                def broken(*args):
                    calls.append(True)
                    if stage == "step":
                        original(*args)  # Fault after mutation: outcome remains unconfirmed.
                    raise RuntimeError("PRIVATE exception detail")

                setattr(sim, stage, broken)
                report = run_episode(lambda: sim, end_round, seed=7, scenario=SCENARIO)
                self.assertEqual(report.status, "failed")
                self.assertEqual(report.reason, stage + "_failed_outcome_unconfirmed")
                self.assertIsNone(report.terminal)
                self.assertEqual(len(calls), 1)
                self.assertNotIn("PRIVATE", json.dumps(to_dict(report)))
                if stage == "step":
                    self.assertEqual(sim.audit_snapshot().revision, 1)
                    self.assertEqual(len(report.audit_events), 2)

    def test_policy_abstention_bad_action_and_exception(self):
        def broken(_):
            raise ValueError("PRIVATE policy detail")

        for policy, status, why in ((lambda _: None, "truncated", "policy_abstained"),
                                    (lambda _: "unknown", "failed", "policy_action_not_legal"),
                                    (broken, "failed", "policy_failed_outcome_unconfirmed")):
            report = run_episode(ToySimulator, policy, seed=7, scenario=SCENARIO)
            self.assertEqual((report.status, report.reason, report.steps), (status, why, 0))
            self.assertIsNone(report.terminal)

    def test_receipt_is_not_terminal_evidence(self):
        sim = ToySimulator()
        original = sim.step

        def false_terminal(value):
            receipt = original(value)
            return StepReceipt(receipt.revision, True)

        sim.step = false_terminal
        report = run_episode(lambda: sim, end_round, seed=7, scenario=SCENARIO)
        self.assertEqual((report.status, report.reason), ("failed", "terminal_receipt_mismatch"))
        self.assertIsNone(report.terminal)
        with self.assertRaises(ValueError):
            TerminalResult(0, 1, ())
        with self.assertRaises(ValueError):
            TerminalResult(3, -1, ())

    def test_failed_or_late_audit_cannot_count_as_completed(self):
        for mode in ("failure", "time", "cancel"):
            with self.subTest(mode=mode):
                sim, ticks, stop = ToySimulator(), [0], [False]
                original = sim.export_events

                def export():
                    if mode == "failure":
                        raise RuntimeError("PRIVATE audit detail")
                    ticks[0], stop[0] = 10, mode == "cancel"
                    return original()

                sim.export_events = export
                report = run_episode(lambda: sim, end_round, seed=7, scenario=SCENARIO,
                                     clock=lambda: ticks[0], cancelled=lambda: stop[0])
                self.assertEqual(report.status,
                                 {"failure": "failed", "time": "truncated", "cancel": "cancelled"}[mode])
                self.assertIsNone(report.terminal)

    def test_unavailable_initial_clock_prevents_factory_creation(self):
        for value in (float("nan"), float("inf"), True, "unknown"):
            with self.subTest(value=str(value)):
                calls = []
                report = run_episode(lambda: calls.append(True), end_round, seed=7,
                                     scenario=SCENARIO, clock=lambda: value)
                self.assertEqual((report.status, report.reason, report.steps),
                                 ("failed", "monotonic_clock_unavailable", 0))
                self.assertFalse(calls)
                self.assertIsNone(report.terminal)

    def test_clock_invalid_or_regressed_during_policy_prevents_step(self):
        for value in (float("nan"), float("inf"), -1):
            with self.subTest(value=str(value)):
                sim, ticks = ToySimulator(), [0]
                def policy(request):
                    ticks[0] = value
                    return end_round(request)
                report = run_episode(lambda: sim, policy, seed=7, scenario=SCENARIO,
                                     clock=lambda: ticks[0])
                self.assertEqual((report.status, report.reason, report.steps),
                                 ("failed", "monotonic_clock_unavailable", 0))
                self.assertEqual(sim.audit_snapshot().revision, 0)
                self.assertIsNone(report.terminal)

    def test_final_control_failure_never_retries_audit_export(self):
        for mode in ("cancel_callback", "clock"):
            with self.subTest(mode=mode):
                sim, exported, ticks = ToySimulator(), [], [0]
                original = sim.export_events
                def export():
                    exported.append(True)
                    if mode == "clock":
                        ticks[0] = float("nan")
                    return original()
                def cancel_check():
                    if exported and mode == "cancel_callback":
                        raise OSError("PRIVATE completion check detail")
                    return False
                sim.export_events = export
                report = run_episode(lambda: sim, end_round, seed=7, scenario=SCENARIO,
                                     cancelled=cancel_check, clock=lambda: ticks[0])
                expected = "completion_check_failed" if mode == "cancel_callback" else "monotonic_clock_unavailable"
                self.assertEqual((report.status, report.reason), ("failed", expected))
                self.assertEqual(len(exported), 1)
                self.assertIsNone(report.terminal)
                self.assertNotIn("PRIVATE", json.dumps(to_dict(report)))

    def test_noop_loop_is_bounded_without_terminal_result(self):
        report = run_episode(ToySimulator, lambda request: next(
            x for x in request.legal_actions if x.move.kind == "hold"), seed=7, scenario=SCENARIO,
            budget=RunBudget(max_steps=4))
        self.assertEqual((report.status, report.reason, report.steps),
                         ("truncated", "step_budget_exhausted", 4))
        self.assertIsNone(report.terminal)


if __name__ == "__main__":
    unittest.main()
