"""Differential/metamorphic synthetic tests, not game-strength measurements."""

import math
import random
import unittest
from dataclasses import replace

from strategy.contracts import to_dict
from strategy.rolling.model import Move
from strategy.simulation.bridge import decision_input, rolling_policy
from strategy.simulation.contracts import AuditEvent, IllegalAction, SimAction, SimulatorError, replay_record
from strategy.simulation.fixtures import SCENARIOS
from strategy.simulation.runner import RunBudget, run_episode
from strategy.simulation.toy import PLAYER, ToySimulator

SEEDS = (0, 1, 7, 42, 2**32 + 17, 2**64 - 1)
SCENARIO = "synthetic-economy-v1"
PRICES = {"unit-a": 1, "unit-b": 2, "unit-c": 1, "unit-d": 2, "unit-e": 3}


def end_round(request):
    return next(x for x in request.legal_actions if x.move.kind == "end_round")


def scripted(request):
    if request.revision == 0:
        return next(x for x in request.legal_actions if x.move.kind == "hold")
    order = {"deploy": 0, "replace": 1, "buy": 2, "end_round": 3, "hold": 4}
    return min(request.legal_actions, key=lambda x: (order[x.move.kind], x.move.label))


class AccountingOracle:
    """Independent set/integer specification; never calls production transitions.

    Hidden permutations are supplied by the test auditor for draw accounting,
    not to the policy. Prices above are the fixture's explicit invented values.
    """

    def __init__(self, spec, hidden):
        self.spec, self.hidden = spec, hidden
        self.round, self.credits, self.terminal = 1, spec.credits, False
        self.board, self.hand, self.discard = {"unit-a"}, set(), set()
        self.offers = self.draw()

    def draw(self):
        unavailable = self.board | self.hand | self.discard
        return set([x for x in self.hidden[self.round - 1] if x not in unavailable]
                   [:self.spec.offers_per_round])

    def legal(self):
        if self.terminal:
            return set()
        result = {Move("hold"), Move("end_round")}
        result.update(Move("buy", unit) for unit in self.offers
                      if unit not in self.spec.bans and PRICES[unit] <= self.credits
                      and len(self.hand) < self.spec.hand_capacity)
        for unit in self.hand - set(self.spec.bans):
            if len(self.board) < self.spec.capacity:
                result.add(Move("deploy", unit))
            if self.credits >= 1:
                result.update(Move("replace", unit, old) for old in self.board)
        return result

    def step(self, move):
        spent = income = switching = 0
        if move.kind == "buy":
            spent = PRICES[move.unit_id]
            self.offers.remove(move.unit_id)
            self.hand.add(move.unit_id)
        elif move.kind in ("deploy", "replace"):
            self.hand.remove(move.unit_id)
            self.board.add(move.unit_id)
            if move.kind == "replace":
                spent = switching = 1
                self.board.remove(move.replaced_id)
                self.discard.add(move.replaced_id)
        elif move.kind == "end_round":
            if self.round == self.spec.rounds:
                self.terminal = True
            else:
                self.round += 1
                income = self.spec.income
                self.offers = self.draw()
        self.credits += income - spent
        return spent, income, switching


class SimulationBoundaryTests(unittest.TestCase):
    def test_multiseed_differential_accounting_legality_and_terminal(self):
        covered = set()
        for seed in SEEDS:
            for spec in SCENARIOS:
                with self.subTest(seed=seed, scenario=spec.scenario_id):
                    sim = ToySimulator()
                    sim.reset(seed, spec.scenario_id)
                    oracle = AccountingOracle(spec, sim.audit_snapshot().hidden_offers)
                    revision = 0
                    while not oracle.terminal:
                        self.assertLess(revision, 24, "finite fixture failed to terminate")
                        view, legal = sim.observe(PLAYER), sim.legal_actions(PLAYER)
                        self.assertEqual({x.move for x in legal}, oracle.legal())
                        before = sim.audit_snapshot()
                        self.assertIsNone(sim.terminal_result())
                        invalid = (SimAction(PLAYER, revision + 1, Move("end_round"), view.episode_id),
                                   SimAction(PLAYER, revision, Move("buy", "absent"), view.episode_id),
                                   SimAction(PLAYER, revision, Move("sell", "unit-a"), view.episode_id))
                        for attempt in invalid:
                            events = sim.export_events()
                            with self.assertRaises(IllegalAction):
                                sim.step(attempt)
                            self.assertEqual(sim.audit_snapshot(), before)
                            self.assertEqual(sim.observe(PLAYER), view)
                            self.assertEqual(sim.export_events(), events)
                        selected = scripted(decision_input(view, legal))
                        covered.add(selected.move.kind)
                        expected = oracle.step(selected.move)
                        receipt = sim.step(selected)
                        revision += 1
                        ledger, actual = sim.export_events()[-1].ledger, sim.audit_snapshot().position
                        self.assertEqual(receipt.revision, revision)
                        self.assertEqual((ledger.credits_spent, ledger.income_received,
                                          ledger.switching_utility_cost), expected)
                        self.assertEqual((actual.round, actual.credits), (oracle.round, oracle.credits))
                        self.assertEqual(set(actual.board_ids), oracle.board)
                        self.assertEqual(set(actual.hand_ids), oracle.hand)
                        self.assertEqual(set(actual.offer_ids), oracle.offers)
                        self.assertEqual(set(actual.discarded_ids), oracle.discard)
                        self.assertEqual(ledger.credits_after,
                                         ledger.credits_before - expected[0] + expected[1])
                        zones = (oracle.board, oracle.hand, oracle.offers, oracle.discard)
                        self.assertEqual(len(set.union(*zones)), sum(map(len, zones)))
                        self.assertEqual(receipt.terminal, oracle.terminal)
                    terminal = sim.terminal_result()
                    self.assertEqual((terminal.completed_rounds, terminal.final_credits),
                                     (spec.rounds, oracle.credits))
                    self.assertEqual(set(terminal.final_board), oracle.board)
                    self.assertEqual(sim.legal_actions(PLAYER), ())
                    self.assertIsNone(terminal.placement)
        self.assertEqual(covered, {"hold", "buy", "deploy", "replace", "end_round"})

    def test_replay_survives_global_rng_noise_and_interleaved_other_episodes(self):
        process_rng = random.getstate()
        try:
            for seed in SEEDS:
                with self.subTest(seed=seed):
                    first = run_episode(ToySimulator, scripted, seed=seed, scenario=SCENARIO, clock=lambda: 0)
                    random.seed(seed ^ 12345)
                    for _ in range(11):
                        random.random()
                    other = ToySimulator()
                    other.reset(seed ^ 31, "synthetic-banned-v1")
                    other.step(next(x for x in other.legal_actions(PLAYER) if x.move.kind == "hold"))
                    frozen = other.audit_snapshot()
                    replay = run_episode(ToySimulator, scripted, seed=seed, scenario=SCENARIO, clock=lambda: 0)
                    self.assertEqual(replay_record(first), replay_record(replay))
                    self.assertEqual(first.status, "completed")
                    self.assertEqual(other.audit_snapshot(), frozen)
                    self.assertEqual(first.real_match_results, 0)
        finally:
            random.setstate(process_rng)

    def test_hidden_state_mutation_preserves_public_decision_until_revelation(self):
        for seed in SEEDS:
            with self.subTest(seed=seed):
                first, mutated = ToySimulator(), ToySimulator()
                for sim in (first, mutated):
                    sim.reset(seed, SCENARIO)
                mutated._hidden = (mutated._hidden[0], tuple(reversed(mutated._hidden[1])),
                                   tuple(reversed(mutated._hidden[2])))
                mutated._opponent_hand = ("different-private-synthetic-marker",)
                mutated._rng.random()
                left = decision_input(first.observe(PLAYER), first.legal_actions(PLAYER))
                right = decision_input(mutated.observe(PLAYER), mutated.legal_actions(PLAYER))
                self.assertEqual(replay_record(left), replay_record(right))
                self.assertEqual(rolling_policy(left).move, rolling_policy(right).move)
                for request in (left, right):
                    self.assertEqual([x.round for x in request.world.rounds], [1])
                self.assertNotEqual(first.audit_snapshot(), mutated.audit_snapshot())
                for sim in (first, mutated):
                    sim.step(end_round(decision_input(sim.observe(PLAYER), sim.legal_actions(PLAYER))))
                # Revelation may change the next public shop, never past evidence.
                self.assertEqual(replay_record(first.observe(PLAYER))["observations"][:4],
                                 replay_record(mutated.observe(PLAYER))["observations"][:4])

    def test_clock_faults_across_callbacks_fail_closed_without_repeated_audit(self):
        stages = ("initial_clock", "factory", "reset", "observe", "legal_actions", "policy", "before_step",
                  "step", "terminal", "export_events")
        faults = ("raise", float("nan"), float("inf"), -float("inf"), True, "invalid", -1)
        for stage in stages:
            for fault in faults:
                if stage == "initial_clock" and fault == -1:
                    continue  # A negative origin is valid; regression needs an earlier sample.
                with self.subTest(stage=stage, fault=str(fault)):
                    sim, state, exports = ToySimulator(), {"armed": stage == "initial_clock", "calls": 0}, []
                    factories = []

                    def clock():
                        if not state["armed"]:
                            return 0
                        state["calls"] += 1
                        if stage == "before_step" and state["calls"] == 1:
                            return 0
                        if fault == "raise":
                            raise OSError("synthetic-private-clock-detail")
                        return fault

                    def arm_method(name):
                        original = getattr(sim, name)

                        def callback(*args):
                            result = original(*args)
                            if name != "terminal_result" or result is not None:
                                state["armed"] = True
                            return result

                        setattr(sim, name, callback)

                    if stage in ("reset", "observe", "legal_actions", "step"):
                        arm_method(stage)
                    if stage == "terminal":
                        arm_method("terminal_result")
                    original_export = sim.export_events

                    def export():
                        exports.append(True)
                        if stage == "export_events":
                            state["armed"] = True
                        return original_export()

                    sim.export_events = export

                    def factory():
                        factories.append(True)
                        if stage == "factory":
                            state["armed"] = True
                        return sim

                    def policy(request):
                        if stage in ("policy", "before_step"):
                            state["armed"] = True
                        return end_round(request)

                    report = run_episode(factory, policy, seed=7, scenario=SCENARIO, clock=clock)
                    expected_steps = 3 if stage in ("terminal", "export_events") else int(stage == "step")
                    self.assertEqual((report.status, report.reason, report.steps),
                                     ("failed", "monotonic_clock_unavailable", expected_steps))
                    self.assertEqual(len(factories), int(stage != "initial_clock"))
                    self.assertEqual(len(exports), int(stage not in ("initial_clock", "factory")))
                    self.assertIsNone(report.terminal)
                    self.assertNotIn("private-clock", str(to_dict(report)))

    def test_elapsed_deadline_is_translation_invariant_and_exact_boundary_is_exclusive(self):
        limit = 2.0
        for origin in (0, -1000000, 1000000):
            for elapsed in (math.nextafter(limit, 0), limit):
                # Use origin zero for the nextafter case: adding a large origin
                # can round that distinct float to the exact deadline.
                if origin and elapsed < limit:
                    continue
                with self.subTest(origin=origin, elapsed=elapsed):
                    sim, ticks = ToySimulator(), [origin]
                    original = sim.step

                    def step(value):
                        receipt = original(value)
                        if receipt.terminal:
                            ticks[0] = origin + elapsed
                        return receipt

                    sim.step = step
                    report = run_episode(lambda: sim, end_round, seed=7, scenario=SCENARIO,
                                         budget=RunBudget(max_seconds=limit), clock=lambda: ticks[0])
                    self.assertEqual(report.status, "completed" if elapsed < limit else "truncated")
                    self.assertEqual(report.terminal is None, elapsed >= limit)
        negative = run_episode(ToySimulator, end_round, seed=7, scenario=SCENARIO, clock=lambda: -100)
        zero = run_episode(ToySimulator, end_round, seed=7, scenario=SCENARIO, clock=lambda: 0)
        self.assertEqual(replay_record(negative), replay_record(zero))

    def test_cancel_pulse_and_terminal_step_budget_boundaries(self):
        for seed in SEEDS:
            for steps in (2, 3):
                with self.subTest(seed=seed, max_steps=steps):
                    report = run_episode(ToySimulator, end_round, seed=seed, scenario=SCENARIO,
                                         budget=RunBudget(max_steps=steps), clock=lambda: 0)
                    self.assertEqual(report.status, "completed" if steps == 3 else "truncated")
                    self.assertEqual(report.steps, steps)
                    self.assertEqual(report.terminal is None, steps < 3)
        sim, state, exports = ToySimulator(), {"pulse": False}, []
        original_export = sim.export_events

        def policy(request):
            state["pulse"] = True
            return end_round(request)

        def cancelled():
            value, state["pulse"] = state["pulse"], False
            return value

        def export():
            exports.append(True)
            return original_export()

        sim.export_events = export
        report = run_episode(lambda: sim, policy, seed=7, scenario=SCENARIO,
                             cancelled=cancelled, clock=lambda: 0)
        self.assertEqual((report.status, report.steps), ("cancelled", 0))
        self.assertEqual(sim.audit_snapshot().revision, 0)
        self.assertEqual(exports, [True])
        self.assertFalse(state["pulse"])

    def test_final_audit_cancellation_wins_without_reading_failed_clock(self):
        sim, state, exports = ToySimulator(), {"audit": False}, []
        original = sim.export_events

        def export():
            exports.append(True)
            state["audit"] = True
            return original()

        def clock():
            if state["audit"]:
                raise AssertionError("clock must not run after observed cancellation")
            return 0

        sim.export_events = export
        report = run_episode(lambda: sim, end_round, seed=7, scenario=SCENARIO,
                             cancelled=lambda: state["audit"], clock=clock)
        self.assertEqual((report.status, report.reason), ("cancelled", "cancelled"))
        self.assertEqual(len(exports), 1)
        self.assertIsNone(report.terminal)

    def test_invalid_audit_payload_is_discarded_and_failure_remains_serializable(self):
        for payload in (None, object(), ["synthetic-private-payload"], (object(),),
                        (AuditEvent(0, "reset", ledger=object()),),
                        (AuditEvent(0, "reset", action=object()),)):
            with self.subTest(payload_type=type(payload).__name__):
                sim, exports = ToySimulator(), []

                def export():
                    exports.append(True)
                    return payload

                sim.export_events = export
                report = run_episode(lambda: sim, end_round, seed=7, scenario=SCENARIO, clock=lambda: 0)
                self.assertEqual((report.status, report.reason), ("failed", "audit_export_failed"))
                self.assertEqual(report.audit_events, ())
                self.assertEqual(to_dict(report)["audit_events"], [])
                self.assertEqual(len(exports), 1)
                self.assertIsNone(report.terminal)

    def test_incomplete_or_conflicting_trace_never_counts_as_completion(self):
        for fault in ("empty", "missing_step", "sequence", "conservation"):
            with self.subTest(audit_fault=fault):
                sim = ToySimulator()
                original = sim.export_events
                def export():
                    events = original()
                    if fault == "empty":
                        return ()
                    if fault == "missing_step":
                        return events[:-1]
                    last = events[-1]
                    if fault == "sequence":
                        last = replace(last, sequence=99)
                    else:
                        last = replace(last, ledger=replace(last.ledger, credits_after=last.ledger.credits_after + 1))
                    return events[:-1] + (last,)
                sim.export_events = export
                report = run_episode(lambda: sim, end_round, seed=7, scenario=SCENARIO, clock=lambda: 0)
                self.assertEqual((report.status, report.reason), ("failed", "audit_integrity_failed"))
                self.assertIsNone(report.terminal)
                self.assertEqual(to_dict(report)["audit_events"], [])
        for changes in ({"final_credits": 999}, {"final_board": ()}, {"completed_rounds": 2}):
            with self.subTest(terminal_conflict=changes):
                sim = ToySimulator()
                original = sim.terminal_result
                def terminal():
                    value = original()
                    return replace(value, **changes) if value is not None else None
                sim.terminal_result = terminal
                report = run_episode(lambda: sim, end_round, seed=7, scenario=SCENARIO, clock=lambda: 0)
                self.assertEqual((report.status, report.reason), ("failed", "terminal_audit_mismatch"))
                self.assertIsNone(report.terminal)
                self.assertEqual(len(report.audit_events), report.steps + 1)

    def test_same_seed_revision_foreign_actions_and_mixed_views_are_rejected(self):
        first, second = ToySimulator(), ToySimulator()
        for sim in (first, second):
            sim.reset(7, SCENARIO)
        foreign = next(x for x in first.legal_actions(PLAYER) if x.move.kind == "end_round")
        local = next(x for x in second.legal_actions(PLAYER) if x.move.kind == "end_round")
        self.assertNotEqual(foreign.episode_id, local.episode_id)
        self.assertEqual((foreign.player, foreign.revision, foreign.move), (local.player, local.revision, local.move))
        before = second.audit_snapshot()
        with self.assertRaises(IllegalAction):
            second.step(foreign)
        self.assertEqual(second.audit_snapshot(), before)
        with self.assertRaises(SimulatorError):
            decision_input(first.observe(PLAYER), second.legal_actions(PLAYER))
        report = run_episode(ToySimulator, lambda _: foreign, seed=7, scenario=SCENARIO, clock=lambda: 0)
        self.assertEqual((report.status, report.reason, report.steps), ("failed", "policy_action_not_legal", 0))
        self.assertIsNone(report.terminal)


if __name__ == "__main__":
    unittest.main()
