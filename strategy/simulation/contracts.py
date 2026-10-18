"""Small simulator protocol. Audit records are never policy inputs."""

from dataclasses import dataclass, field
from typing import Protocol

from ..contracts import Observation, identifier
from ..rolling.model import Move, World, ids
from ..rolling.search import StepTrace


class SimulatorError(RuntimeError):
    """Adapter lifecycle or unsupported capability failure."""


class IllegalAction(SimulatorError):
    """A rejected action must leave position, randomness and events unchanged."""


@dataclass(frozen=True)
class EpisodeMetadata:
    engine_name: str
    engine_revision: str
    engine_commit: str | None
    engine_source_digest: str
    python_version: str
    strategy_baseline_commit: str
    rules_version: str
    scenario_id: str
    scenario_digest: str
    seed: int
    supported_mechanisms: tuple[str, ...]
    unknown_mechanisms: tuple[str, ...]
    synthetic_fixture: bool = field(default=True, init=False)


@dataclass(frozen=True)
class PlayerView:
    """Immutable visible evidence plus public current-round rules only.

    No adapter handle, seed, hidden sequence, opponent hand or RNG state belongs
    here. Observation.source references are synthetic and contain no seed.
    """

    player: str
    revision: int
    observations: tuple[Observation, ...]
    world: World


@dataclass(frozen=True)
class SimAction:
    player: str
    revision: int
    move: Move

    def __post_init__(self):
        identifier(self.player)
        if type(self.revision) is not int or self.revision < 0 or not isinstance(self.move, Move):
            raise ValueError("action requires a nonnegative revision and existing Move")


@dataclass(frozen=True)
class StepReceipt:
    revision: int
    terminal: bool


@dataclass(frozen=True)
class AuditEvent:
    sequence: int
    kind: str
    action: SimAction | None = None
    ledger: StepTrace | None = None


@dataclass(frozen=True)
class TerminalResult:
    completed_rounds: int
    final_credits: int
    final_board: tuple[str, ...]
    reason: str = field(default="synthetic_round_limit", init=False)
    result_kind: str = field(default="synthetic_completion_not_placement", init=False)
    placement: None = field(default=None, init=False)

    def __post_init__(self):
        if type(self.completed_rounds) is not int or not 1 <= self.completed_rounds <= 4:
            raise ValueError("one through four completed synthetic rounds required")
        if type(self.final_credits) is not int or self.final_credits < 0:
            raise ValueError("nonnegative terminal credits required")
        ids(self.final_board)


class SimulatorAdapter(Protocol):
    """One instance per episode. Reset is called exactly once.

    Only observe/ legal_actions outputs cross the policy boundary. Reset
    metadata, export_events and terminal_result belong to the harness/auditor.
    Implementations must reject stale/illegal actions atomically. Unexpected
    step failures have an uncertain outcome: stop the episode, never retry.
    """

    def reset(self, seed: int, scenario: str) -> EpisodeMetadata: ...

    def observe(self, player: str) -> PlayerView: ...

    def legal_actions(self, player: str) -> tuple[SimAction, ...]: ...

    def step(self, action: SimAction) -> StepReceipt: ...

    def export_events(self) -> tuple[AuditEvent, ...]: ...

    def terminal_result(self) -> TerminalResult | None: ...
