"""Finite offline harness; interrupted/failed episodes never count as results."""

from dataclasses import dataclass, field
import time
from typing import Callable

from ..contracts import identifier, number, to_dict
from ..rolling.model import ids, read_position
from ..rolling.search import StepTrace
from .bridge import DecisionInput, decision_input
from .contracts import (AuditEvent, EpisodeMetadata, IllegalAction, SimulatorAdapter,
                        SimAction, StepReceipt, TerminalResult)


class _ClockFault(RuntimeError):
    """Deadline evidence is unavailable; no dependent action may be submitted."""


def _check_audit(events, submitted, steps, episode_id, *, uncertain=False):
    """Fixture mapping: one reset, then one event per accepted submitted action."""
    if (not events or type(events[0].sequence) is not int
            or events[0] != AuditEvent(0, "reset")):
        raise ValueError("audit_reset_missing")
    count = len(events) - 1
    if not steps <= count <= (len(submitted) if uncertain else steps):
        raise ValueError("audit_step_coverage_mismatch")
    previous = None
    for sequence, event in enumerate(events[1:], 1):
        action, observed = submitted[sequence - 1]
        ledger = event.ledger
        if (type(event.sequence) is not int or event.sequence != sequence or event.kind != "step"
                or type(event.action) is not SimAction or event.action != action
                or action.episode_id != episode_id or action.revision != sequence - 1
                or type(ledger) is not StepTrace or ledger.analysis_only is not True
                or ledger.move != action.move.label):
            raise ValueError("audit_action_binding_mismatch")
        for value in (ledger.round, ledger.next_round, ledger.credits_before, ledger.credits_after,
                      ledger.credits_spent, ledger.income_received, ledger.capacity_after):
            if type(value) is not int or value < 0:
                raise ValueError("audit_number_invalid")
        if (not number(ledger.switching_utility_cost) or ledger.switching_utility_cost < 0
                or ledger.round != observed.round or ledger.credits_before != observed.credits
                or ledger.board_before != observed.board_ids
                or ledger.credits_after != ledger.credits_before - ledger.credits_spent + ledger.income_received):
            raise ValueError("audit_resource_mismatch")
        zones = ledger.board_after + ledger.hand_after + ledger.offers_after + ledger.discarded_after
        ids(zones)
        ids(ledger.board_before)
        if len(ledger.board_after) > ledger.capacity_after:
            raise ValueError("audit_capacity_mismatch")
        if ledger.next_round not in (ledger.round, ledger.round + 1):
            raise ValueError("audit_round_discontinuity")
        if ledger.next_round == ledger.round and (ledger.capacity_after != observed.capacity
                or (action.move.kind == "end_round" and ledger.offers_after != observed.offer_ids)):
            raise ValueError("audit_undeclared_same_round_change")
        if action.move.kind != "end_round" and (ledger.next_round != ledger.round or ledger.income_received):
            raise ValueError("audit_unearned_income")
        if action.move.kind == "end_round" and (ledger.credits_spent or ledger.switching_utility_cost
                or ledger.board_after != observed.board_ids or ledger.hand_after != observed.hand_ids
                or ledger.discarded_after != observed.discarded_ids):
            raise ValueError("audit_settlement_mutated_owned_units")
        if previous is not None and (
                (previous.next_round, previous.credits_after, previous.board_after, previous.hand_after,
                 previous.offers_after, previous.discarded_after, previous.capacity_after)
                != (observed.round, observed.credits, observed.board_ids, observed.hand_ids,
                    observed.offer_ids, observed.discarded_ids, observed.capacity)):
            raise ValueError("audit_position_discontinuity")
        previous = ledger


def _check_terminal(events, terminal, submitted, steps):
    if not steps or steps != len(submitted) or len(events) != steps + 1:
        raise ValueError("terminal_trace_incomplete")
    last = events[-1].ledger
    rounds = tuple(event.ledger.round for event in events[1:] if event.action.move.kind == "end_round")
    if (events[-1].action.move.kind != "end_round" or last.next_round != last.round
            or last.income_received or submitted[0][1].round != 1
            or rounds != tuple(range(1, terminal.completed_rounds + 1))
            or terminal.completed_rounds != last.round or terminal.final_credits != last.credits_after
            or terminal.final_board != last.board_after):
        raise ValueError("terminal_audit_mismatch")


@dataclass(frozen=True)
class RunBudget:
    max_steps: int = 32
    max_seconds: float = 2

    def __post_init__(self):
        if type(self.max_steps) is not int or not 0 <= self.max_steps <= 256:
            raise ValueError("step budget must be in [0, 256]")
        if not number(self.max_seconds) or not 0 <= self.max_seconds <= 30:
            raise ValueError("time budget must be in [0, 30] seconds")


@dataclass(frozen=True)
class EpisodeReport:
    status: str
    reason: str
    steps: int
    metadata: EpisodeMetadata | None
    terminal: TerminalResult | None
    audit_events: tuple[AuditEvent, ...]
    audit_status: str
    synthetic_fixture: bool = field(default=True, init=False)
    real_match_results: int = field(default=0, init=False)
    execution_allowed: bool = field(default=False, init=False)


def run_episode(factory: Callable[[], SimulatorAdapter], policy: Callable[[DecisionInput], object],
                *, seed: int, scenario: str, player="player-0", budget=RunBudget(),
                cancelled=lambda: False, clock=time.monotonic) -> EpisodeReport:
    """Create a fresh adapter. Never give the policy the adapter or audit state.

    Time/cancel checks surround every callback and immediately precede step.
    Cooperative checks cannot interrupt a blocking factory/engine/policy; put an
    untrusted external engine in a separately supervised process for hard limits.
    No automatic retry follows any failure, including audit export failures.
    """
    adapter = metadata = None
    steps = 0
    submitted = []
    stopped = False
    started = last_clock = None

    def stop_reason():
        nonlocal stopped, started, last_clock
        stopped = stopped or bool(cancelled())
        if stopped:
            return "cancelled"
        try:
            current = clock()
            valid = number(current)
        except Exception:
            raise _ClockFault() from None
        if not valid or (last_clock is not None and current < last_clock):
            raise _ClockFault()
        last_clock = current
        if started is None:
            started = current
        if current - started >= budget.max_seconds:
            return "time_budget_exhausted"
        return None

    def report(status, reason, terminal=None):
        events, audit_status = (), "not_started"
        if adapter is not None and metadata is not None:
            try:
                exported = adapter.export_events()
                if not isinstance(exported, tuple) or any(not isinstance(x, AuditEvent) for x in exported):
                    raise TypeError("invalid audit events")
                for event in exported:
                    to_dict(event)  # Reject malformed nested values before retaining the payload.
            except Exception:
                # An incomplete audit must not masquerade as a completed run.
                status, reason, terminal, audit_status = "failed", "audit_export_failed", None, "failed"
            else:
                try:
                    _check_audit(exported, submitted, steps, metadata.episode_id,
                                 uncertain=reason == "step_failed_outcome_unconfirmed")
                except Exception:
                    status, reason, terminal, audit_status = "failed", "audit_integrity_failed", None, "failed"
                else:
                    events, audit_status = exported, "exported"
                    if status == "completed":
                        try:
                            _check_terminal(events, terminal, submitted, steps)
                        except Exception:
                            status, reason, terminal = "failed", "terminal_audit_mismatch", None
        if status == "completed":
            try:
                why = stop_reason()
            except _ClockFault:
                status, reason, terminal = "failed", "monotonic_clock_unavailable", None
            except Exception:
                # Do not unwind into the outer handler and export audit twice.
                status, reason, terminal = "failed", "completion_check_failed", None
            else:
                if why:
                    status, reason, terminal = ("cancelled" if why == "cancelled" else "truncated"), why, None
        return EpisodeReport(status, reason, steps, metadata, terminal, events, audit_status)

    def interrupted():
        why = stop_reason()
        return report("cancelled" if why == "cancelled" else "truncated", why) if why else None

    stage = "factory"
    try:
        if (result := interrupted()) is not None:
            return result
        adapter = factory()
        if (result := interrupted()) is not None:
            return result
        stage = "reset"
        metadata = adapter.reset(seed, scenario)
        if not isinstance(metadata, EpisodeMetadata) or not metadata.synthetic_fixture:
            raise TypeError("synthetic metadata required")
        identifier(metadata.episode_id)
        if (result := interrupted()) is not None:
            return result
        while True:
            stage = "terminal"
            terminal = adapter.terminal_result()
            if (result := interrupted()) is not None:
                return result
            if terminal is not None:
                if not isinstance(terminal, TerminalResult):
                    raise TypeError("invalid terminal result")
                return report("completed", "terminal_result_confirmed", terminal)
            if steps >= budget.max_steps:
                return report("truncated", "step_budget_exhausted")
            stage = "observe"
            view = adapter.observe(player)
            if (result := interrupted()) is not None:
                return result
            if view.episode_id != metadata.episode_id:
                raise ValueError("view_episode_mismatch")
            stage = "legal_actions"
            legal = adapter.legal_actions(player)
            if (result := interrupted()) is not None:
                return result
            stage = "bridge"
            request = decision_input(view, legal)
            observed, unknown = read_position(request.state, request.world)
            if unknown:
                raise ValueError("audit_initial_position_unknown")
            if (result := interrupted()) is not None:
                return result
            stage = "policy"
            action = policy(request)
            if (result := interrupted()) is not None:
                return result
            if action is None:
                return report("truncated", "policy_abstained")
            if action not in legal:
                return report("failed", "policy_action_not_legal")
            # Do not send any action after an observed cancellation/deadline.
            if (result := interrupted()) is not None:
                return result
            stage = "step"
            submitted.append((action, observed))
            receipt = adapter.step(action)
            steps += 1
            if (result := interrupted()) is not None:
                return result
            if (not isinstance(receipt, StepReceipt) or type(receipt.revision) is not int
                    or receipt.revision != view.revision + 1
                    or type(receipt.terminal) is not bool):
                return report("failed", "invalid_step_receipt")
            stage = "terminal"
            terminal = adapter.terminal_result()
            if (result := interrupted()) is not None:
                return result
            if receipt.terminal != (terminal is not None):
                return report("failed", "terminal_receipt_mismatch")
            if terminal is not None:
                if not isinstance(terminal, TerminalResult):
                    return report("failed", "invalid_terminal_result")
                return report("completed", "terminal_result_confirmed", terminal)
    except _ClockFault:
        return report("failed", "monotonic_clock_unavailable")
    except IllegalAction:
        return report("failed", "illegal_action_rejected")
    except Exception:
        # Stable codes only: third-party exception strings can contain private data.
        return report("failed", stage + "_failed_outcome_unconfirmed")
