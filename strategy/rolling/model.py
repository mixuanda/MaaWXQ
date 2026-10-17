"""Exact, small synthetic transitions. None means unsupported, never zero."""

from dataclasses import dataclass, replace
import math

from ..contracts import digest, identifier, number

DOMAIN = "test_rules_not_gameplay"
FIELDS = ("credits", "board_ids", "hand_ids", "offer_ids", "discarded_ids",
          "capacity", "hand_capacity", "free_board", "free_hand")


def ids(items):
    if not isinstance(items, tuple) or len(set(items)) != len(items):
        raise ValueError("IDs must be a distinct immutable tuple")
    for item in items:
        identifier(item)


def nonnegative(value, *, unknown=False):
    if unknown and value is None:
        return
    if type(value) is not int or value < 0:
        raise ValueError("expected a nonnegative integer or declared unknown")


@dataclass(frozen=True)
class Card:
    unit_id: str
    value: float | None
    price: int | None
    roles: tuple[str, ...] = ()
    ban_tags: tuple[str, ...] = ()

    def __post_init__(self):
        identifier(self.unit_id)
        if self.value is not None and not number(self.value):
            raise ValueError("unit utility must be finite or unknown")
        nonnegative(self.price, unknown=True)
        ids(self.roles)
        ids(self.ban_tags)


@dataclass(frozen=True)
class PairLink:
    link_id: str
    units: tuple[str, str]
    value: float | None

    def __post_init__(self):
        identifier(self.link_id)
        ids(self.units)
        if len(self.units) != 2 or (self.value is not None and not number(self.value)):
            raise ValueError("a pair needs two units and finite or unknown utility")


@dataclass(frozen=True)
class ThresholdLink:
    link_id: str
    role: str
    minimum: int
    value: float | None

    def __post_init__(self):
        identifier(self.link_id)
        identifier(self.role)
        if type(self.minimum) is not int or not 1 <= self.minimum <= 6:
            raise ValueError("threshold is bounded to one through six distinct units")
        if self.value is not None and not number(self.value):
            raise ValueError("threshold utility must be finite or unknown")


@dataclass(frozen=True)
class OpponentProfile:
    profile_id: str
    board_ids: tuple[str, ...]
    disabled_links: tuple[str, ...] = ()
    role_adjustments: tuple[tuple[str, float], ...] = ()

    def __post_init__(self):
        identifier(self.profile_id)
        ids(self.board_ids)
        ids(self.disabled_links)
        if len(self.board_ids) > 6 or not isinstance(self.role_adjustments, tuple):
            raise ValueError("invalid synthetic opponent profile")
        if any(not isinstance(x, tuple) or len(x) != 2 for x in self.role_adjustments):
            raise ValueError("role adjustments must be immutable pairs")
        if len({key for key, _ in self.role_adjustments}) != len(self.role_adjustments):
            raise ValueError("duplicate opponent role adjustments")
        for key, value in self.role_adjustments:
            identifier(key)
            if not number(value):
                raise ValueError("opponent adjustment must be finite")


@dataclass(frozen=True)
class RoundRule:
    round: int
    income_on_entry: int | None
    offers: tuple[str, ...] | None
    capacity: int | None
    utility_weight: float | None

    def __post_init__(self):
        if type(self.round) is not int or self.round < 1:
            raise ValueError("positive round required")
        nonnegative(self.income_on_entry, unknown=True)
        nonnegative(self.capacity, unknown=True)
        if self.capacity is not None and self.capacity > 6:
            raise ValueError("board capacity exceeds toy bound")
        if self.offers is not None:
            ids(self.offers)
            if len(self.offers) > 6:
                raise ValueError("offer count exceeds toy bound")
        if self.utility_weight is not None and (not number(self.utility_weight) or self.utility_weight < 0):
            raise ValueError("round weight must be nonnegative or unknown")


@dataclass(frozen=True)
class World:
    version: str
    cards: tuple[Card, ...]
    pairs: tuple[PairLink, ...]
    thresholds: tuple[ThresholdLink, ...]
    profiles: tuple[OpponentProfile, ...]
    rounds: tuple[RoundRule, ...]
    replace_credit_cost: int | None
    replace_utility_cost: float | None
    deploy_credit_cost: int | None
    verification: str = "unverified"
    domain: str = DOMAIN
    build: str = "synthetic-rolling-build-1"
    phase: str = "test_preparation"
    schema_version: str = "toy-rolling-world/1"

    def __post_init__(self):
        for item in (self.version, self.build, self.phase):
            identifier(item)
        if self.domain != DOMAIN or self.schema_version != "toy-rolling-world/1":
            raise ValueError("only test_rules_not_gameplay is supported")
        if self.verification not in ("unverified", "declared_synthetic"):
            raise ValueError("invalid rule support")
        for values, limit in ((self.cards, 12), (self.pairs, 24), (self.thresholds, 12),
                              (self.profiles, 8), (self.rounds, 6)):
            if not isinstance(values, tuple) or len(values) > limit:
                raise ValueError("world collection exceeds immutable toy bound")
        if not self.cards or not self.profiles or not self.rounds:
            raise ValueError("units, explicit opponent scenarios and rounds required")
        unit_ids = {x.unit_id for x in self.cards}
        link_ids = [x.link_id for x in (*self.pairs, *self.thresholds)]
        if (len(unit_ids) != len(self.cards) or len(link_ids) != len(set(link_ids))
                or len({x.profile_id for x in self.profiles}) != len(self.profiles)
                or len({frozenset(x.board_ids) for x in self.profiles}) != len(self.profiles)
                or len({x.round for x in self.rounds}) != len(self.rounds)):
            raise ValueError("duplicate world identities")
        if any(not set(x.units) <= unit_ids for x in self.pairs):
            raise ValueError("pair references unknown unit")
        if any(not set(x.disabled_links) <= set(link_ids) for x in self.profiles):
            raise ValueError("profile references unknown link")
        if any(x.offers is not None and not set(x.offers) <= unit_ids for x in self.rounds):
            raise ValueError("round references unknown unit")
        nonnegative(self.replace_credit_cost, unknown=True)
        nonnegative(self.deploy_credit_cost, unknown=True)
        if self.replace_utility_cost is not None and (
                not number(self.replace_utility_cost) or self.replace_utility_cost < 0):
            raise ValueError("switching utility cost must be nonnegative or unknown")

    @property
    def fingerprint(self):
        return digest(self)

    def card(self, unit_id):
        return next(x for x in self.cards if x.unit_id == unit_id)

    def frame(self, round_number):
        return next((x for x in self.rounds if x.round == round_number), None)


@dataclass(frozen=True)
class Position:
    round: int
    credits: int
    board_ids: tuple[str, ...]
    hand_ids: tuple[str, ...]
    offer_ids: tuple[str, ...]
    discarded_ids: tuple[str, ...]
    capacity: int
    hand_capacity: int

    @property
    def free_board(self):
        return self.capacity - len(self.board_ids)

    @property
    def free_hand(self):
        return self.hand_capacity - len(self.hand_ids)


def validate_position(pos, world):
    if not isinstance(pos, Position):
        raise ValueError("position required")
    for x in (pos.round, pos.credits, pos.capacity, pos.hand_capacity):
        nonnegative(x)
    if pos.round < 1 or pos.capacity > 6 or pos.hand_capacity > 6:
        raise ValueError("position exceeds toy bound")
    all_units = ()
    for units in (pos.board_ids, pos.hand_ids, pos.offer_ids, pos.discarded_ids):
        ids(units)
        all_units += units
    if (len(all_units) != len(set(all_units)) or not set(all_units) <= {x.unit_id for x in world.cards}
            or pos.free_board < 0 or pos.free_hand < 0 or len(pos.offer_ids) > 6):
        raise ValueError("invalid unit identity or capacity")


def read_position(state, world):
    values = {x.field.key: x.field for x in state.fields}
    unknown = tuple("required_field_unknown:" + name for name in FIELDS
                    if name not in values or values[name].status != "observed")
    if unknown:
        return None, unknown
    try:
        pos = Position(state.round, **{name: values[name].value for name in FIELDS
                                      if name not in ("free_board", "free_hand")})
        validate_position(pos, world)
        if (any(type(values[x].value) is not int for x in ("free_board", "free_hand"))
                or values["free_board"].value != pos.free_board or values["free_hand"].value != pos.free_hand):
            raise ValueError("capacity evidence inconsistent")
    except (ValueError, TypeError):
        return None, ("invalid_position",)
    return pos, ()


def support_reasons(world, first_round, horizon):
    reasons = []
    if world.verification != "declared_synthetic":
        reasons.append("rules_unverified")
    if any(x.value is None or x.price is None for x in world.cards):
        reasons.append("unit_value_or_price_unknown")
    if any(x.value is None for x in (*world.pairs, *world.thresholds)):
        reasons.append("interaction_utility_unknown")
    if any(x is None for x in (world.replace_credit_cost, world.replace_utility_cost,
                              world.deploy_credit_cost)):
        reasons.append("transition_cost_unknown")
    for round_number in range(first_round, first_round + horizon):
        frame = world.frame(round_number)
        if frame is None or any(x is None for x in (
                frame.income_on_entry, frame.offers, frame.capacity, frame.utility_weight)):
            reasons.append("round_transition_unknown:" + str(round_number))
    return tuple(reasons)


@dataclass(frozen=True)
class Move:
    kind: str
    unit_id: str | None = None
    replaced_id: str | None = None

    @property
    def label(self):
        if self.kind == "replace":
            return "replace:" + self.replaced_id + "->" + self.unit_id
        return self.kind + (":" + self.unit_id if self.unit_id else "")


def moves(pos):
    return ((Move("hold"), Move("end_round"))
            + tuple(Move("buy", unit) for unit in sorted(pos.offer_ids))
            + tuple(Move("deploy", unit) for unit in sorted(pos.hand_ids))
            + tuple(Move("replace", unit, old) for unit in sorted(pos.hand_ids)
                    for old in sorted(pos.board_ids)))


def move_reasons(pos, world, move, bans):
    validate_position(pos, world)
    known_tags = {tag for card in world.cards for tag in (card.unit_id, *card.ban_tags)}
    if not set(bans) <= known_tags:
        return ("ban_target_outside_declared_support",)
    if move not in moves(pos):
        return ("move_target_or_operation_unknown",)
    reasons = []
    if move.unit_id:
        card = world.card(move.unit_id)
        if {card.unit_id, *card.ban_tags} & set(bans):
            reasons.append("confirmed_ban")
    if move.kind == "buy":
        if card.price is None:
            reasons.append("price_unknown")
        elif pos.credits < card.price:
            reasons.append("insufficient_credits")
        if pos.free_hand < 1:
            reasons.append("hand_full")
    elif move.kind in ("deploy", "replace"):
        cost = world.deploy_credit_cost if move.kind == "deploy" else world.replace_credit_cost
        if cost is None or (move.kind == "replace" and world.replace_utility_cost is None):
            reasons.append("transition_cost_unknown")
        elif pos.credits < cost:
            reasons.append("insufficient_credits")
        if move.kind == "deploy" and pos.free_board < 1:
            reasons.append("board_full")
    return tuple(reasons)


@dataclass(frozen=True)
class Transition:
    position: Position
    switching_cost: float
    settled_round: int | None
    terminal: bool
    credits_spent: int = 0
    income_received: int = 0


def transition(pos, world, move, *, bans, final_round):
    """A final settlement ends the horizon; it does not invent another round."""
    if type(final_round) is not int or not pos.round <= final_round <= pos.round + 3:
        raise ValueError("invalid transition horizon")
    unsupported = support_reasons(world, pos.round, final_round - pos.round + 1)
    if unsupported:
        raise ValueError(",".join(unsupported))
    reasons = move_reasons(pos, world, move, bans)
    if reasons:
        raise ValueError(",".join(reasons))
    if move.kind == "hold":
        return Transition(pos, 0, None, False)
    if move.kind == "buy":
        return Transition(replace(pos, credits=pos.credits - world.card(move.unit_id).price,
                                  offer_ids=tuple(x for x in pos.offer_ids if x != move.unit_id),
                                  hand_ids=tuple(sorted((*pos.hand_ids, move.unit_id)))), 0, None, False,
                          world.card(move.unit_id).price)
    if move.kind in ("deploy", "replace"):
        cost = world.deploy_credit_cost if move.kind == "deploy" else world.replace_credit_cost
        next_pos = replace(pos, credits=pos.credits - cost,
                           board_ids=tuple(sorted(tuple(x for x in pos.board_ids
                                                        if x != move.replaced_id) + (move.unit_id,))),
                           hand_ids=tuple(x for x in pos.hand_ids if x != move.unit_id),
                           discarded_ids=tuple(sorted(pos.discarded_ids + (
                               (move.replaced_id,) if move.replaced_id else ()))))
        return Transition(next_pos, world.replace_utility_cost if move.replaced_id else 0, None, False, cost)
    if pos.round == final_round:
        return Transition(pos, 0, pos.round, True)
    frame = world.frame(pos.round + 1)
    if frame is None or any(x is None for x in (frame.income_on_entry, frame.offers, frame.capacity)):
        raise ValueError("future_round_unknown")
    if len(pos.board_ids) > frame.capacity:
        raise ValueError("future_capacity_requires_unsupported_removal")
    unavailable = set(pos.board_ids + pos.hand_ids + pos.discarded_ids)
    next_pos = replace(pos, round=frame.round, credits=pos.credits + frame.income_on_entry,
                       offer_ids=tuple(x for x in frame.offers if x not in unavailable), capacity=frame.capacity)
    validate_position(next_pos, world)
    return Transition(next_pos, 0, pos.round, False, 0, frame.income_on_entry)


@dataclass(frozen=True)
class Formation:
    profile_id: str
    isolated_value: float
    pair_links: tuple[tuple[str, float], ...]
    threshold_links: tuple[tuple[str, float], ...]
    opponent_adjustment: float
    total: float


def formation(world, board_ids, profile):
    units = [world.card(x) for x in board_ids]
    if any(x.value is None for x in units):
        raise ValueError("unit_value_unknown")
    active_pairs = [x for x in world.pairs if set(x.units) <= set(board_ids)
                    and x.link_id not in profile.disabled_links]
    active_thresholds = [x for x in world.thresholds if x.link_id not in profile.disabled_links
                         and sum(x.role in unit.roles for unit in units) >= x.minimum]
    if any(x.value is None for x in (*active_pairs, *active_thresholds)):
        raise ValueError("interaction_utility_unknown")
    base = sum(x.value for x in units)
    pair = tuple((x.link_id, x.value) for x in active_pairs)
    threshold = tuple((x.link_id, x.value) for x in active_thresholds)
    adjustment = sum(value for role, value in profile.role_adjustments for unit in units if role in unit.roles)
    total = base + sum(x[1] for x in (*pair, *threshold)) + adjustment
    if not math.isfinite(total):
        raise ValueError("utility_overflow")
    return Formation(profile.profile_id, base, pair, threshold, adjustment, total)
