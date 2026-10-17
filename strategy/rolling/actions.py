"""Bind only an immediate move to observed evidence and the shared hard gate."""

from dataclasses import dataclass, field

from ..contracts import CandidateAction, ResourceCost, Source
from ..policy import Policy, filter_candidates, generate_candidates
from ..rules import Requirement, Rule, RuleRegistry
from .memory import MemoryPolicy, assess
from .model import DOMAIN, FIELDS, Move, World, move_reasons, moves, read_position, support_reasons


@dataclass(frozen=True)
class Advice:
    intent: CandidateAction
    move: Move
    world_digest: str
    opponent_id: str
    memory_digest: str
    horizon: int
    schema_version: str = field(default="rolling-advice/1", init=False)


@dataclass(frozen=True)
class Batch:
    actions: tuple[Advice, ...]
    rejections: tuple[tuple[str, tuple[str, ...]], ...]
    reasons: tuple[str, ...]
    registry: RuleRegistry | None = None


def generate(state, world, opponent_id, *, now, horizon=2, policy=Policy(),
             memory_policy=MemoryPolicy(), issued_at=None):
    if not isinstance(world, World):
        return Batch((), (), ("rules_unavailable",))
    if type(horizon) is not int or not 1 <= horizon <= 4:
        return Batch((), (), ("horizon_outside_supported_bound",))
    if not policy.allow_test_rules:
        return Batch((), (), ("test_rules_require_explicit_opt_in",))
    pos, reasons = read_position(state, world)
    if pos is None:
        return Batch((), (), reasons)
    reasons = support_reasons(world, pos.round, horizon)
    if reasons:
        return Batch((), (), reasons)
    if (not state.events or any(x.source.kind != "synthetic" for x in state.events)
            or any(x.source.kind != "synthetic" for x in state.fields)):
        return Batch((), (), ("real_state_evidence_not_supported_by_toy_world",))
    frame = world.frame(pos.round)
    if frame.capacity != pos.capacity or not set(pos.offer_ids) <= set(frame.offers):
        return Batch((), (), ("position_outside_declared_round_support",))
    belief, reasons = assess(state, world, opponent_id, now=now, policy=memory_policy)
    if belief is None:
        return Batch((), (), reasons)
    specs = moves(pos)
    if len(specs) > policy.max_candidates:
        return Batch((), (), ("candidate_budget_exhausted",))
    rules, mapping = [], {}
    for move in specs:
        key = "rolling:" + move.label
        required = tuple(Requirement("self." + name) for name in FIELDS)
        tags, costs = (), ()
        if move.unit_id:
            card = world.card(move.unit_id)
            tags = (move.unit_id, *card.ban_tags)
        if move.kind == "buy":
            required += (Requirement("self.free_hand", "ge", 1),)
            costs = (ResourceCost("self.credits", card.price),)
        elif move.kind in ("deploy", "replace"):
            cost = world.deploy_credit_cost if move.kind == "deploy" else world.replace_credit_cost
            costs = (ResourceCost("self.credits", cost),)
            if move.kind == "deploy":
                required += (Requirement("self.free_board", "ge", 1),)
        expected = ("Declared synthetic " + move.label + "; no execution.",
                    "World content binding: " + world.fingerprint,
                    "Opponent evidence binding: " + opponent_id + ":" + belief.evidence_digest,
                    "Declared planning horizon: " + str(horizon),
                    "No sale refunds, combat, draws or undeclared effects are simulated.")
        if move.kind == "replace":
            expected += ("Discard old unit; pay declared resource and switching utility costs.",)
        rules.append(Rule(key, "test_rolling_" + move.kind, "verified",
                          Source("synthetic", DOMAIN + ":rolling-transitions"), (world.phase,),
                          required, (), expected, ban_tags=tags, resource_costs=costs))
        mapping[key] = move
    registry = RuleRegistry(world.build, world.version, DOMAIN, True, tuple(rules))
    candidates = generate_candidates(state, registry, now=issued_at or now, policy=policy)
    evaluations = filter_candidates(state, registry, candidates, now=now, policy=policy)
    accepted, rejected = [], []
    for evaluation in evaluations:
        move = mapping[evaluation.candidate.rule_id]
        why = tuple(dict.fromkeys(evaluation.reasons + move_reasons(pos, world, move, state.confirmed_bans)))
        if why:
            rejected.append((move.label, why))
        else:
            accepted.append(Advice(evaluation.candidate, move, world.fingerprint, opponent_id,
                                   belief.evidence_digest, horizon))
    reasons = () if accepted else tuple(dict.fromkeys(
        ["no_supported_immediate_move"] + [why for _, reasons in rejected for why in reasons]))
    return Batch(tuple(accepted), tuple(rejected), reasons, registry)


def revalidate(advice, state, world, *, now, policy=Policy(), memory_policy=MemoryPolicy()):
    if advice.world_digest != world.fingerprint:
        return ("world_rules_changed",)
    batch = generate(state, world, advice.opponent_id, now=now, horizon=advice.horizon,
                     policy=policy, memory_policy=memory_policy, issued_at=advice.intent.issued_at)
    if batch.registry is None:
        return batch.reasons
    checked = filter_candidates(state, batch.registry, (advice.intent,), now=now, policy=policy)[0]
    reasons = list(checked.reasons)
    belief, why = assess(state, world, advice.opponent_id, now=now, policy=memory_policy)
    reasons.extend(why)
    if belief and belief.evidence_digest != advice.memory_digest:
        reasons.append("opponent_memory_changed")
    if advice not in batch.actions:
        reasons.append("advice_binding_or_target_changed")
    return tuple(dict.fromkeys(reasons))
