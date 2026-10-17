"""Generate from current offers/hand/board, then reuse the independent hard gate."""

from dataclasses import dataclass, replace

from ..contracts import CandidateAction, ResourceCost, Source
from ..policy import Policy, filter_candidates, generate_candidates
from ..rules import Requirement, Rule, RuleRegistry
from .model import DOMAIN, REQUIRED_FIELDS, position, simulated_state

TEST_POLICY = Policy(allow_test_rules=True, max_candidates=128)


@dataclass(frozen=True)
class Action:
    intent: CandidateAction
    kind: str
    unit_id: str | None
    replaced_id: str | None
    world_digest: str

    @property
    def label(self):
        if self.kind == "replace":
            return "replace:" + self.replaced_id + "->" + self.unit_id
        return self.kind + (":" + self.unit_id if self.unit_id else "") + (
            ":replace:" + self.replaced_id if self.replaced_id else "")


@dataclass(frozen=True)
class Batch:
    actions: tuple[Action, ...]
    rejections: tuple[tuple[str, tuple[str, ...]], ...]
    registry: RuleRegistry | None
    reasons: tuple[str, ...] = ()


def generate(state, world, *, now, policy=Policy(), issued_at=None):
    if world.verification != "declared_synthetic":
        return Batch((), (), None, ("transition_rules_unverified",))
    if not policy.allow_test_rules:
        return Batch((), (), None, ("test_rules_require_explicit_opt_in",))
    pos, reasons = position(state, world)
    if pos is None:
        return Batch((), (), None, reasons)
    specs = [("hold", None, None)]
    specs.extend(("buy", x, None) for x in sorted(pos.offer_ids))
    for unit in sorted(pos.hand_ids):
        specs.append(("deploy", unit, None))
        specs.extend(("replace", unit, old) for old in sorted(pos.board_ids))
    if len(specs) > policy.max_candidates:
        return Batch((), (), None, ("dynamic_candidate_budget_exceeded",))
    records, mapping = [], {}
    for kind, unit, old in specs:
        rule_id = "toy:" + kind + (":" + unit if unit else "") + (":" + old if old else "")
        required = [Requirement("self." + name) for name in REQUIRED_FIELDS]
        # Equality binds the semantic targets; numeric limits remain separate.
        required.extend(Requirement("self." + name, "eq", getattr(pos, name))
                        for name in ("board_ids", "hand_ids", "offer_ids"))
        costs, tags, verified = (), (), "verified"
        if unit is not None:
            card = world.card(unit)
            tags = (unit,) + card.ban_tags
        if kind == "buy":
            required.append(Requirement("self.free_hand", "ge", 1))
            if card.price is None:
                verified = "unverified"
            else:
                costs = (ResourceCost("self.credits", card.price),)
        elif kind == "deploy":
            required.append(Requirement("self.free_board", "ge", 1))
        records.append(Rule(rule_id, "test_" + kind, verified,
                            Source("synthetic", DOMAIN + ":dynamic-operations"),
                            (world.phase,), tuple(required), (),
                            ("Declared toy " + kind + " transition; analysis only.",),
                            ban_tags=tags, resource_costs=costs))
        mapping[rule_id] = (kind, unit, old)
    registry = RuleRegistry(world.build, world.version, DOMAIN, True, tuple(records))
    intents = generate_candidates(state, registry, now=issued_at or now, policy=policy)
    evaluations = filter_candidates(state, registry, intents, now=now, policy=policy)
    actions, rejections = [], []
    for result in evaluations:
        kind, unit, old = mapping[result.candidate.rule_id]
        action = Action(result.candidate, kind, unit, old, world.fingerprint)
        if result.accepted:
            actions.append(action)
        else:
            rejections.append((action.label, result.reasons))
    reasons = () if actions else tuple(dict.fromkeys(
        ["no_supported_dynamic_candidate"] + [reason for _, why in rejections for reason in why]))
    return Batch(tuple(actions), tuple(rejections), registry, reasons)


def revalidate(action, state, world, *, now, policy=Policy()):
    if action.world_digest != world.fingerprint:
        return ("world_rules_changed",)
    batch = generate(state, world, now=now, issued_at=action.intent.issued_at, policy=policy)
    if batch.registry is None:
        return batch.reasons
    checked = filter_candidates(state, batch.registry, (action.intent,), now=now, policy=policy)[0]
    if not checked.accepted:
        return checked.reasons
    # Require the complete canonical action, not a model-edited target or payload.
    if action in batch.actions:
        return ()
    reasons = next((why for label, why in batch.rejections if label == action.label), ())
    return reasons or ("candidate_state_ban_or_payload_changed",)


def step(state, world, action, *, now, policy=Policy()):
    reasons = revalidate(action, state, world, now=now, policy=policy)
    if reasons:
        raise ValueError("unsupported transition: " + ",".join(reasons))
    pos, _ = position(state, world)
    if action.kind == "hold":
        return state
    if action.kind == "buy":
        pos = replace(pos, credits=pos.credits - world.card(action.unit_id).price,
                      offer_ids=tuple(x for x in pos.offer_ids if x != action.unit_id),
                      hand_ids=tuple(sorted(pos.hand_ids + (action.unit_id,))))
    elif action.kind in ("deploy", "replace"):
        board = tuple(x for x in pos.board_ids if x != action.replaced_id) + (action.unit_id,)
        # A replaced toy unit is discarded, without a sale return or hidden effect.
        pos = replace(pos, board_ids=tuple(sorted(board)),
                      hand_ids=tuple(x for x in pos.hand_ids if x != action.unit_id))
    else:
        raise ValueError("transition operation unsupported")
    return simulated_state(state, pos, now, "predicted:" + action.intent.candidate_id)
