"""Match-scoped opponent evidence selects explicit scenarios, never probabilities."""

from dataclasses import dataclass
from datetime import datetime

from ..contracts import OpponentMemory, aware, digest, identifier, number
from .model import ids


@dataclass(frozen=True)
class MemoryPolicy:
    max_seconds: float = 20
    max_round_age: int = 0
    min_confidence: float = 0.8

    def __post_init__(self):
        if (not number(self.max_seconds) or self.max_seconds < 0
                or not number(self.min_confidence) or not 0 <= self.min_confidence <= 1
                or type(self.max_round_age) is not int or self.max_round_age < 0):
            raise ValueError("invalid memory policy")


@dataclass(frozen=True)
class Binding:
    match_id: str
    memory: OpponentMemory
    policy: MemoryPolicy


@dataclass(frozen=True)
class Belief:
    opponent_id: str
    profile_ids: tuple[str, ...]
    coverage: str
    last_seen: datetime
    round: int
    age_seconds: float
    evidence_digest: str
    event_ids: tuple[str, ...]
    sources: tuple[str, ...]
    uncertainty: tuple[str, ...]
    criterion: str = "worst_case_over_declared_scenarios_not_probability"


def assess(state, world, opponent_id, *, now, policy=MemoryPolicy()):
    aware(now)
    identifier(opponent_id)
    item = next((x for x in state.opponents if x.opponent_id == opponent_id), None)
    if item is None or state.match_id is None:
        return None, ("opponent_identity_unresolved",)
    field = next((x for x in item.fields if x.field.key == "board_ids"), None)
    if field is None or field.field.status != "observed":
        return None, ("opponent_board_unknown",)
    if field.source.kind != "synthetic":
        return None, ("real_opponent_evidence_not_supported_by_toy_world",)
    if field.field.confidence is None or field.field.confidence < policy.min_confidence:
        return None, ("opponent_confidence_insufficient",)
    if field.last_seen != item.last_seen or field.round != item.round:
        return None, ("opponent_board_not_refreshed_by_latest_sighting",)
    if field.phase is None or field.phase != state.phase:
        return None, ("opponent_phase_unknown_or_mismatched",)
    try:
        ids(field.field.value)
    except (ValueError, TypeError):
        return None, ("opponent_board_unresolved",)
    for seen, round_number in ((item.last_seen, item.round), (field.last_seen, field.round)):
        if (seen is None or not 0 <= (now - seen).total_seconds() <= policy.max_seconds
                or round_number is None or state.round is None
                or not 0 <= state.round - round_number <= policy.max_round_age):
            return None, ("opponent_memory_stale_or_future",)
    observed = set(field.field.value)
    if item.coverage == "full":
        profiles = tuple(x.profile_id for x in world.profiles if set(x.board_ids) == observed)
    elif item.coverage == "partial":
        profiles = tuple(x.profile_id for x in world.profiles if observed <= set(x.board_ids))
    else:
        return None, ("opponent_coverage_unknown",)
    if not profiles:
        return None, ("opponent_outside_declared_scenario_support",)
    uncertainty = ("future_rounds_expand_to_all_declared_profiles", "scenario_set_is_synthetic_and_closed")
    if item.coverage == "partial":
        uncertainty += ("unseen_opponent_units_are_not_absent",)
    result = Belief(opponent_id, profiles, item.coverage, field.last_seen, field.round,
                    (now - field.last_seen).total_seconds(), digest(Binding(state.match_id, item, policy)),
                    (field.event_id,), (field.source.reference,), uncertainty)
    return result, ()
