"""Depth-bounded search with cooperative cancellation and an independent final gate."""

from dataclasses import dataclass, field
from datetime import timedelta
import time

from ..contracts import MatchState, aware, digest, number
from ..policy import Policy
from .candidates import Action, generate, revalidate, step
from .model import DOMAIN, FEATURE_VERSION, Scenario, ToyWorld, formation_value, position
from .ranker import ExactEvaluator


@dataclass(frozen=True)
class Budget:
    max_depth: int = 2
    max_nodes: int = 128
    max_seconds: float = 0.5

    def __post_init__(self):
        if type(self.max_depth) is not int or not 1 <= self.max_depth <= 2:
            raise ValueError("this planner supports depth one or two")
        if type(self.max_nodes) is not int or not 0 <= self.max_nodes <= 1024:
            raise ValueError("invalid node budget")
        if not number(self.max_seconds) or not 0 <= self.max_seconds <= 5:
            raise ValueError("invalid cooperative time budget")


@dataclass(frozen=True)
class LeafScore:
    scenario_id: str
    evaluator_score: float
    feature_contributions: tuple[tuple[str, float], ...]
    declared_toy_utility: float
    isolated_value: float
    active_interactions: tuple[tuple[str, float], ...]
    roles: tuple[str, ...]
    utility_delta_from_root: float


@dataclass(frozen=True)
class Alternative:
    first_action: Action
    contingent_path: tuple[str, ...]
    score: float
    leaves: tuple[LeafScore, ...]
    interactions_gained: tuple[str, ...]
    interactions_lost: tuple[str, ...]
    predicted_board: tuple[str, ...]
    predicted_credits: int
    analysis_only: bool = field(default=True, init=False)


@dataclass(frozen=True)
class PlanResult:
    match_id: str | None
    state_version: int
    world_digest: str
    status: str
    selected: Action | None
    contingent_path: tuple[str, ...]
    alternatives: tuple[Alternative, ...]
    root_actions: tuple[str, ...]
    root_rejections: tuple[tuple[str, tuple[str, ...]], ...]
    reasons: tuple[str, ...]
    termination: str
    nodes: int
    depth_reached: int
    evaluator_version: str
    evaluator_digest: str
    score_kind: str
    budget: Budget
    final_gate: str
    schema_version: str = "advisory-planning/1"
    domain: str = field(default=DOMAIN, init=False)
    scenario_aggregation: str = field(default="worst_case_without_probability_weights", init=False)
    execution_allowed: bool = field(default=False, init=False)
    placement_probabilities: None = field(default=None, init=False)


def plan(state, world, *, now, policy=Policy(), budget=Budget(), scenarios=(Scenario(),),
         evaluator=ExactEvaluator(), cancelled=lambda: False, clock=time.monotonic,
         latest_snapshot=None):
    """Return one immediate advice item. Predicted continuations are never a queue.

    `latest_snapshot`, when supplied, returns (latest observed state, latest world)
    for the last gate. Time limits are checked around each bounded local operation;
    an arbitrary blocking third-party evaluator cannot be preempted by this loop.
    """
    aware(now)
    started = clock()
    nodes, depth_reached = 0, 0
    root_batch = None
    choices = {}

    def stop_reason():
        if cancelled():
            return "cancelled"
        if clock() - started >= budget.max_seconds:
            return "time_budget_exhausted"
        return None

    def finish(selected, termination, reasons=(), path=(), *, fallback=False):
        nonlocal root_batch
        if cancelled():
            selected, path, termination = None, (), "cancelled"
        gate = "no_action"
        if selected is not None:
            try:
                current_state, current_world = latest_snapshot() if latest_snapshot else (state, world)
                if not isinstance(current_state, MatchState) or not isinstance(current_world, ToyWorld):
                    raise ValueError("current snapshot unavailable")
            except Exception:
                # Snapshot providers may fail with I/O or adapter-specific errors.
                # An unavailable final source cannot preserve earlier advice.
                selected, path, termination = None, (), "final_snapshot_unavailable"
                reasons = tuple(reasons) + ("final_snapshot_unavailable",)
        if selected is not None:
            at = now + timedelta(seconds=max(0.0, clock() - started))
            problems = revalidate(selected, current_state, current_world, now=at, policy=policy)
            if cancelled():
                selected, path, termination = None, (), "cancelled"
            elif problems:
                selected, path, gate = None, (), "rejected"
                reasons = tuple(reasons) + ("final_revalidation_failed",) + problems
            else:
                gate = "passed_advice_only"
                late_reason = stop_reason()
                if late_reason == "cancelled":
                    selected, path, termination, gate = None, (), "cancelled", "cancelled"
                elif late_reason == "time_budget_exhausted" and not fallback:
                    selected = next(x for x in root_batch.actions if x.kind == "hold")
                    path, termination, fallback = (selected.label,), "time_budget_exhausted", True
                    reasons = tuple(reasons) + (termination,)
                    at = now + timedelta(seconds=max(0.0, clock() - started))
                    problems = revalidate(selected, current_state, current_world, now=at, policy=policy)
                    if problems or cancelled():
                        selected, path, gate = None, (), "rejected"
                        reasons = tuple(reasons) + problems
        if cancelled():
            selected, path, termination, gate = None, (), "cancelled", "cancelled"
        if termination == "cancelled":
            reasons = tuple(dict.fromkeys(tuple(reasons) + ("cancelled",)))
        status = "abstain" if selected is None else ("fallback" if fallback else "recommend")
        return PlanResult(state.match_id, state.state_version, world.fingerprint, status,
                          selected, tuple(path), tuple(sorted(choices.values(), key=lambda x: (-x.score, x.contingent_path))),
                          tuple(x.label for x in root_batch.actions) if root_batch else (),
                          root_batch.rejections if root_batch else (), tuple(reasons), termination,
                          nodes, depth_reached, evaluator.version, digest(evaluator), evaluator.score_kind, budget, gate)

    def fallback(reason):
        hold = next((x for x in root_batch.actions if x.kind == "hold"), None) if root_batch else None
        return finish(None if reason == "cancelled" else hold, reason, (reason,),
                      () if hold is None or reason == "cancelled" else (hold.label,), fallback=True)

    if (not isinstance(scenarios, tuple) or not 1 <= len(scenarios) <= 8
            or len({x.scenario_id for x in scenarios}) != len(scenarios)
            or any(x.support != "declared_synthetic" for x in scenarios)):
        return finish(None, "unsupported_belief", ("belief_support_unknown",))
    if any(not set(x.disabled_interactions) <= {v.interaction_id for v in world.interactions} for x in scenarios):
        return finish(None, "unsupported_belief", ("unknown_interaction_in_belief",))
    root_batch = generate(state, world, now=now, policy=policy)
    if not root_batch.actions:
        return finish(None, "unsupported_state_or_rules", root_batch.reasons)
    reason = stop_reason()
    if reason:
        return fallback(reason)
    if evaluator.domain != DOMAIN or evaluator.feature_version != FEATURE_VERSION:
        return fallback("evaluator_support_mismatch")
    root_pos, _ = position(state, world)
    root_values = {}

    def evaluate(node_state, path):
        pos, _ = position(node_state, world)
        leaves = []
        gained, lost = set(), set()
        for scenario in scenarios:
            value = formation_value(world, pos.board_ids, scenario)
            score = evaluator.score(value)
            contributions = tuple(evaluator.contributions(value))
            if not number(score) or not all(number(x) for _, x in contributions):
                raise ValueError("evaluator_returned_nonfinite_value")
            root_value = root_values[scenario.scenario_id]
            active = {x for x, _ in value.active_interactions}
            old = {x for x, _ in root_value.active_interactions}
            gained.update(active - old)
            lost.update(old - active)
            leaves.append(LeafScore(scenario.scenario_id, score, contributions, value.total,
                                    value.isolated_value, value.active_interactions, value.roles,
                                    value.total - root_value.total))
        return Alternative(path[0], tuple(x.label for x in path), min(x.evaluator_score for x in leaves),
                           tuple(leaves), tuple(sorted(gained)), tuple(sorted(lost)), pos.board_ids, pos.credits)

    hold = next(x for x in root_batch.actions if x.kind == "hold")
    try:
        root_values = {x.scenario_id: formation_value(world, root_pos.board_ids, x) for x in scenarios}
        choices[hold.label] = evaluate(state, (hold,))
        frontier = [(state, ())]
        visited = set()
        while frontier:
            current, path = frontier.pop(0)
            batch = root_batch if not path else generate(current, world, now=now, policy=policy)
            for action in batch.actions:
                if action.kind == "hold":
                    continue
                reason = stop_reason()
                if reason:
                    return fallback(reason)
                if nodes >= budget.max_nodes:
                    return fallback("node_budget_exhausted")
                successor = step(current, world, action, now=now, policy=policy)
                nodes += 1
                next_path = path + (action,)
                depth_reached = max(depth_reached, len(next_path))
                reason = stop_reason()
                if reason:
                    return fallback(reason)
                alternative = evaluate(successor, next_path)
                reason = stop_reason()
                if reason:
                    return fallback(reason)
                first = next_path[0].label
                previous = choices.get(first)
                key = lambda x: (-x.score, len(x.contingent_path), x.contingent_path)
                if previous is None or key(alternative) < key(previous):
                    choices[first] = alternative
                pos, _ = position(successor, world)
                signature = (first, pos, len(next_path))
                if len(next_path) < budget.max_depth and signature not in visited:
                    visited.add(signature)
                    frontier.append((successor, next_path))
    except Exception as error:
        # A replaceable evaluator/transition may be unavailable for ordinary
        # adapter reasons such as OSError. Preserve only independently gated hold.
        return fallback("unsupported_evaluation_or_transition:" + type(error).__name__)
    reason = stop_reason()
    if reason:
        return fallback(reason)
    best = min(choices.values(), key=lambda x: (-x.score, x.first_action.kind != "hold",
                                               len(x.contingent_path), x.contingent_path))
    return finish(best.first_action, "complete", ("best_supported_worst_case_score",), best.contingent_path)
