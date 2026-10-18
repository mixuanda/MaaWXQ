"""One-way strategy bridge: only filtered public evidence reaches a policy."""

from dataclasses import dataclass

from ..contracts import MatchState
from ..policy import Policy
from ..rolling.model import World
from ..rolling.search import Budget, plan
from ..state import reduce_observation
from .contracts import PlayerView, SimAction, SimulatorError
from .toy import OPPONENT


@dataclass(frozen=True)
class DecisionInput:
    player: str
    revision: int
    state: MatchState
    world: World
    legal_actions: tuple[SimAction, ...]


def decision_input(view: PlayerView, legal_actions: tuple[SimAction, ...]) -> DecisionInput:
    """Rebuild the existing match reducer exclusively from visible observations.

    This bridge cannot sanitize a malicious adapter. A production adapter must
    implement its own reviewed visibility projection before constructing a view.
    """
    if (not isinstance(view, PlayerView) or not view.observations
            or any(x.source.kind != "synthetic" for x in view.observations)):
        raise SimulatorError("synthetic_observation_required")
    state = MatchState()
    now = max(x.ingested_at for x in view.observations)
    for event in view.observations:
        state = reduce_observation(state, event, now=now)
    if (state.lifecycle != "active" or len(view.world.rounds) != 1
            or view.world.rounds[0].round != state.round
            or view.world.verification != "declared_synthetic"):
        raise SimulatorError("current_synthetic_round_required")
    if not isinstance(legal_actions, tuple) or any(
            not isinstance(x, SimAction) or x.player != view.player or x.revision != view.revision
            for x in legal_actions):
        raise SimulatorError("action_binding_mismatch")
    return DecisionInput(view.player, view.revision, state, view.world, legal_actions)


def rolling_policy(request: DecisionInput) -> SimAction | None:
    """Reuse the existing hard gate/search, with no future-world disclosure.

    One round is the only declared horizon in this public projection. Future
    offers remain unavailable. The core still returns advisory-only intents;
    matching the immediate move below acts on this synthetic engine only.
    """
    result = plan(request.state, request.world, OPPONENT, now=request.state.last_seen,
                  budget=Budget(horizon=1, max_nodes=256, max_seconds=0.2),
                  policy=Policy(allow_test_rules=True))
    if result.selected is None:
        return None
    return next((x for x in request.legal_actions if x.move == result.selected.move), None)
