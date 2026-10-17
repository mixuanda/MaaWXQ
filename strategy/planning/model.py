"""Explicit test transitions and nonadditive formation values; no WXQ mechanics."""

from dataclasses import dataclass, replace
from datetime import datetime
import math

from ..contracts import (EvidenceField, FieldValue, MatchState, Observation, Source,
                         digest, identifier, number)
from ..state import reduce_observation

DOMAIN = "test_rules_not_gameplay"
FEATURE_VERSION = "toy-composition-features/1"
FEATURE_NAMES = ("isolated_value", "pair_interaction_value", "higher_order_interaction_value")
REQUIRED_FIELDS = ("credits", "board_ids", "hand_ids", "offer_ids", "capacity", "hand_capacity",
                   "free_board", "free_hand")


@dataclass(frozen=True)
class Card:
    card_id: str
    isolated_value: float
    price: int | None
    roles: tuple[str, ...] = ()
    ban_tags: tuple[str, ...] = ()

    def __post_init__(self):
        identifier(self.card_id)
        if not number(self.isolated_value):
            raise ValueError("card value must be finite")
        if self.price is not None and (type(self.price) is not int or self.price < 0):
            raise ValueError("price must be unknown or a nonnegative integer")
        for items in (self.roles, self.ban_tags):
            if not isinstance(items, tuple):
                raise ValueError("card collections must be immutable")
            for item in items:
                identifier(item)


@dataclass(frozen=True)
class Interaction:
    interaction_id: str
    requires: tuple[str, ...]
    value: float

    def __post_init__(self):
        identifier(self.interaction_id)
        if not isinstance(self.requires, tuple) or not 2 <= len(self.requires) <= 8:
            raise ValueError("an interaction needs two to eight distinct unit IDs")
        if len(set(self.requires)) != len(self.requires) or not number(self.value):
            raise ValueError("invalid interaction")


@dataclass(frozen=True)
class Scenario:
    scenario_id: str = "declared_toy_opponent"
    disabled_interactions: tuple[str, ...] = ()
    support: str = "declared_synthetic"

    def __post_init__(self):
        identifier(self.scenario_id)
        if not isinstance(self.disabled_interactions, tuple):
            raise ValueError("scenario collections must be immutable")
        if self.support not in ("declared_synthetic", "unknown"):
            raise ValueError("invalid scenario support")


@dataclass(frozen=True)
class ToyWorld:
    version: str
    cards: tuple[Card, ...]
    interactions: tuple[Interaction, ...] = ()
    domain: str = DOMAIN
    verification: str = "unverified"
    build: str = "synthetic-planning-build-1"
    phase: str = "test_preparation"
    schema_version: str = "toy-planning-world/1"

    def __post_init__(self):
        for item in (self.version, self.build, self.phase):
            identifier(item)
        if self.domain != DOMAIN or self.schema_version != "toy-planning-world/1":
            raise ValueError("this transition model supports only explicitly synthetic worlds")
        if self.verification not in ("declared_synthetic", "unverified"):
            raise ValueError("invalid toy verification")
        if not isinstance(self.cards, tuple) or not 1 <= len(self.cards) <= 16:
            raise ValueError("toy worlds require one to sixteen immutable cards")
        if not isinstance(self.interactions, tuple) or len(self.interactions) > 32:
            raise ValueError("invalid interaction collection")
        ids = {x.card_id for x in self.cards}
        if len(ids) != len(self.cards):
            raise ValueError("duplicate card IDs")
        if len({x.interaction_id for x in self.interactions}) != len(self.interactions):
            raise ValueError("duplicate interaction IDs")
        if any(not set(x.requires) <= ids for x in self.interactions):
            raise ValueError("interaction references an unknown unit")

    @property
    def fingerprint(self):
        return digest(self)

    def card(self, card_id):
        return next(x for x in self.cards if x.card_id == card_id)


@dataclass(frozen=True)
class Position:
    credits: int
    board_ids: tuple[str, ...]
    hand_ids: tuple[str, ...]
    offer_ids: tuple[str, ...]
    capacity: int
    hand_capacity: int

    @property
    def free_board(self):
        return self.capacity - len(self.board_ids)

    @property
    def free_hand(self):
        return self.hand_capacity - len(self.hand_ids)


@dataclass(frozen=True)
class FormationValue:
    scenario_id: str
    isolated_value: float
    pair_interaction_value: float
    higher_order_interaction_value: float
    active_interactions: tuple[tuple[str, float], ...]
    roles: tuple[str, ...]
    total: float

    @property
    def features(self):
        return (self.isolated_value, self.pair_interaction_value, self.higher_order_interaction_value)


def position(state, world):
    """Read declared fields. No unknown-to-zero or observed-empty coercion."""
    values = {x.field.key: x.field for x in state.fields}
    missing = [name for name in REQUIRED_FIELDS
               if name not in values or values[name].status != "observed"]
    if missing:
        return None, tuple("required_field_unknown:" + x for x in missing)
    data = {x: values[x].value for x in REQUIRED_FIELDS}
    for name in ("credits", "capacity", "hand_capacity", "free_board", "free_hand"):
        if type(data[name]) is not int or data[name] < 0:
            return None, ("invalid_position_number:" + name,)
    if data["capacity"] > 8 or data["hand_capacity"] > 8:
        return None, ("position_capacity_budget_exceeded",)
    ids = {x.card_id for x in world.cards}
    for name in ("board_ids", "hand_ids", "offer_ids"):
        if (not isinstance(data[name], tuple) or len(data[name]) > 8
                or len(set(data[name])) != len(data[name]) or not set(data[name]) <= ids):
            return None, ("unresolved_or_duplicate_unit:" + name,)
    all_ids = data["board_ids"] + data["hand_ids"] + data["offer_ids"]
    if len(set(all_ids)) != len(all_ids):
        return None, ("toy_unique_card_identity_violated",)
    result = Position(**{x: data[x] for x in Position.__dataclass_fields__})
    if result.free_board != data["free_board"] or result.free_hand != data["free_hand"]:
        return None, ("inconsistent_capacity_evidence",)
    return result, ()


def fields_for(pos, *, unknown=()):
    values = {x: getattr(pos, x) for x in Position.__dataclass_fields__}
    values.update(free_board=pos.free_board, free_hand=pos.free_hand)
    return tuple(FieldValue(key) if key in unknown else FieldValue(key, "observed", value, 0.95)
                 for key, value in sorted(values.items()))


def make_state(world, *, now: datetime, board_ids=(), hand_ids=(), offer_ids=(), credits=2,
               capacity=2, hand_capacity=4, bans=(), unknown=(), match_id="synthetic-planning-match"):
    """Fixture builder only: all facts are explicitly synthetic annotations."""
    source = Source("synthetic", DOMAIN + ":planning-fixture")
    start = Observation("start", match_id, "match_start", now, now, source, round=1,
                        phase=world.phase, context_confidence=0.95,
                        game_build=world.build, rules_version=world.version)
    state = reduce_observation(MatchState(), start, now=now)
    ban_event = Observation("bans", match_id, "bans", now, now, source, round=1,
                            phase=world.phase,
                            fields=(FieldValue("banned_tags", "observed", tuple(sorted(bans)), 0.95),))
    state = reduce_observation(state, ban_event, now=now)
    pos = Position(credits, tuple(board_ids), tuple(hand_ids), tuple(offer_ids), capacity, hand_capacity)
    event = Observation("position", match_id, "state", now, now, source, round=1,
                        phase=world.phase, context_confidence=0.95, fields=fields_for(pos, unknown=unknown))
    return reduce_observation(state, event, now=now)


def simulated_state(state, pos, now, transition_id):
    """Tree-local predicted facts; never merge these into an observed match."""
    source = Source("synthetic", DOMAIN + ":tree-local-prediction")
    fields = tuple(EvidenceField(x, transition_id, source, now, state.round, state.phase)
                   for x in fields_for(pos))
    return replace(state, state_version=state.state_version + 1, fields=fields)


def formation_value(world, board_ids, scenario=Scenario()):
    if scenario.support != "declared_synthetic":
        raise ValueError("unsupported opponent belief")
    if not set(scenario.disabled_interactions) <= {x.interaction_id for x in world.interactions}:
        raise ValueError("scenario references an unknown interaction")
    active = tuple((x.interaction_id, x.value) for x in world.interactions
                   if set(x.requires) <= set(board_ids) and x.interaction_id not in scenario.disabled_interactions)
    base = sum(world.card(x).isolated_value for x in board_ids)
    pair = sum(x.value for x in world.interactions if len(x.requires) == 2
               and (x.interaction_id, x.value) in active)
    higher = sum(x.value for x in world.interactions if len(x.requires) > 2
                 and (x.interaction_id, x.value) in active)
    total = base + pair + higher
    if not math.isfinite(total):
        raise ValueError("formation utility overflow")
    roles = tuple(sorted({role for unit in board_ids for role in world.card(unit).roles}))
    return FormationValue(scenario.scenario_id, base, pair, higher, active, roles, total)
