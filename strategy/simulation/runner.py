"""Finite offline harness; interrupted/failed episodes never count as results."""

from dataclasses import dataclass, field
import time
from typing import Callable

from ..contracts import number
from .bridge import DecisionInput, decision_input
from .contracts import (AuditEvent, EpisodeMetadata, IllegalAction, SimulatorAdapter,
                        StepReceipt, TerminalResult)


class _ClockFault(RuntimeError):
    """Deadline evidence is unavailable; no dependent action may be submitted."""


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
                events = adapter.export_events()
                if not isinstance(events, tuple) or any(not isinstance(x, AuditEvent) for x in events):
                    raise TypeError("invalid audit events")
                audit_status = "exported"
            except Exception:
                # An incomplete audit must not masquerade as a completed run.
                status, reason, terminal, audit_status = "failed", "audit_export_failed", None, "failed"
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
            stage = "legal_actions"
            legal = adapter.legal_actions(player)
            if (result := interrupted()) is not None:
                return result
            stage = "bridge"
            request = decision_input(view, legal)
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
