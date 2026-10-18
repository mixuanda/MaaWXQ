"""Bounded receding-horizon search. Continuations are analysis, never commands."""

from dataclasses import dataclass, field, is_dataclass
from datetime import datetime, timedelta
import time

from ..contracts import MatchState, digest, number
from ..policy import Policy
from .actions import Advice, generate, revalidate
from .economy import EconomyObjective
from .memory import Belief, MemoryPolicy, assess
from .model import DOMAIN, Formation, Position, World, formation, move_reasons, moves, read_position, transition


@dataclass(frozen=True)
class Budget:
    horizon: int = 2
    max_prep_actions: int = 3
    max_nodes: int = 2048
    max_seconds: float = 1

    def __post_init__(self):
        for value, low, high in ((self.horizon, 1, 4), (self.max_prep_actions, 0, 4),
                                 (self.max_nodes, 0, 10000)):
            if type(value) is not int or not low <= value <= high:
                raise ValueError("search budget outside supported bound")
        if not number(self.max_seconds) or not 0 <= self.max_seconds <= 5:
            raise ValueError("wall budget must be between zero and five seconds")


@dataclass(frozen=True)
class ExactEvaluator:
    version: str = "declared-round-utility/1"
    domain: str = DOMAIN
    score_kind: str = "synthetic_utility_not_probability"

    def score(self, value):
        return value.total


@dataclass(frozen=True)
class RoundTrace:
    round: int
    board_ids: tuple[str, ...]
    credits_before_income: int
    profiles: tuple[Formation, ...]
    worst_case_value: float
    utility_weight: float
    weighted_value: float
    belief_kind: str


@dataclass(frozen=True)
class Alternative:
    first_move: str
    path: tuple[str, ...]
    total_utility: float
    switching_cost: float
    rounds: tuple[RoundTrace, ...]
    terminal_position: Position
    resource_ledger: tuple["StepTrace", ...]
    terminal_resource_value: float = 0
    resource_value_delta_from_root: float = 0
    analysis_only: bool = field(default=True, init=False)


@dataclass(frozen=True)
class StepTrace:
    round: int
    move: str
    credits_before: int
    credits_after: int
    next_round: int
    board_before: tuple[str, ...]
    board_after: tuple[str, ...]
    discarded_after: tuple[str, ...]
    switching_utility_cost: float
    credits_spent: int
    income_received: int
    hand_after: tuple[str, ...]
    offers_after: tuple[str, ...]
    capacity_after: int
    analysis_only: bool = field(default=True, init=False)


@dataclass(frozen=True)
class Result:
    match_id: str | None
    state_version: int
    ban_version: int
    world_digest: str
    evaluated_at: datetime
    status: str
    selected: Advice | None
    alternatives: tuple[Alternative, ...]
    belief: Belief | None
    reasons: tuple[str, ...]
    root_rejections: tuple[tuple[str, tuple[str, ...]], ...]
    termination: str
    nodes: int
    deduplicated_nodes: int
    completed_paths: int
    horizon_exhausted: bool
    budget: Budget
    evaluator_version: str
    final_gate: str
    economy: EconomyObjective = EconomyObjective()
    schema_version: str = "advisory-rolling-plan/1"
    domain: str = field(default=DOMAIN, init=False)
    execution_allowed: bool = field(default=False, init=False)
    placement_probabilities: None = field(default=None, init=False)
    score_kind: str = field(default="synthetic_utility_not_probability", init=False)


@dataclass(frozen=True)
class Node:
    position: Position
    path: tuple[str, ...] = ()
    total: float = 0
    switching_cost: float = 0
    traces: tuple[RoundTrace, ...] = ()
    prep_used: int = 0
    first_move: str | None = None
    resource_ledger: tuple[StepTrace, ...] = ()


def plan(state, world, opponent_id, *, now, budget=Budget(), policy=Policy(),
         memory_policy=MemoryPolicy(), evaluator=ExactEvaluator(), cancelled=lambda: False,
         latest_snapshot=None, clock=time.monotonic, economy=EconomyObjective()):
    """Rebuild from observations each call; no old continuation is ever replayed.

    A completed incumbent can survive node/time exhaustion, with the limitation
    explicit. Without one, return a revalidated hold. Cancellation returns none.
    Checks are cooperative and cannot preempt arbitrary caller-supplied code.
    """
    if not isinstance(economy, EconomyObjective):
        raise ValueError("an explicit validated economy objective is required")
    started = clock()
    root = None
    belief = None
    choices = {}
    nodes = duplicates = completed = 0
    termination = "complete"
    visited = {}
    evaluator_version = getattr(evaluator, "version", "unavailable")
    cancellation_seen = False

    def cancellation_requested():
        nonlocal cancellation_seen
        # Once this request observes cancellation, later polling cannot revive it.
        cancellation_seen = cancellation_seen or bool(cancelled())
        return cancellation_seen

    def stop():
        if cancellation_requested():
            return "cancelled"
        if clock() - started >= budget.max_seconds:
            return "time_budget_exhausted"
        return None

    def finish(selected, status, why, *, exhaustive=False):
        nonlocal termination
        reasons = tuple(why)
        gate = "no_action"
        if cancellation_requested():
            selected, status, termination = None, "abstain", "cancelled"
            reasons += ("cancelled",)
        current_state, current_world = state, world
        if selected is not None:
            try:
                current_state, current_world = latest_snapshot() if latest_snapshot else (state, world)
                if not isinstance(current_state, MatchState) or not isinstance(current_world, World):
                    raise ValueError("current snapshot unavailable")
            except Exception:
                selected, status, termination = None, "abstain", "final_snapshot_unavailable"
                reasons += ("final_snapshot_unavailable",)
        if selected is not None:
            at = now + timedelta(seconds=max(0, clock() - started))
            try:
                problems = revalidate(selected, current_state, current_world, now=at,
                                      policy=policy, memory_policy=memory_policy)
            except Exception:
                problems = ("final_snapshot_invalid",)
            if problems:
                selected, status, gate = None, "abstain", "rejected"
                reasons += ("final_revalidation_failed",) + problems
            elif cancellation_requested():
                selected, status, termination, gate = None, "abstain", "cancelled", "cancelled"
                reasons += ("cancelled",)
            else:
                gate = "passed_advice_only"
                # Final validation itself can cross the cooperative budget.
                if stop() == "time_budget_exhausted" and termination == "complete":
                    termination = "time_budget_exhausted"
                    exhaustive = False
                    reasons += ("time_budget_exhausted",)
                    if status == "recommend":
                        status = "budget_limited"
        if cancellation_requested():
            selected, status, termination, gate = None, "abstain", "cancelled", "cancelled"
            reasons += ("cancelled",)
        return Result(state.match_id, state.state_version, state.ban_version,
                      world.fingerprint if isinstance(world, World) else "unavailable",
                      now, status, selected, tuple(sorted(choices.values(), key=alternative_key)),
                      belief, tuple(dict.fromkeys(reasons)), root.rejections if root else (),
                      termination, nodes, duplicates, completed, exhaustive, budget,
                      evaluator_version, gate, economy)

    def fallback(reason):
        nonlocal termination
        termination = reason
        hold = next((x for x in root.actions if x.move.kind == "hold"), None) if root else None
        if reason == "cancelled":
            hold = None
        return finish(hold, "fallback" if hold else "abstain", (reason,))

    if cancellation_requested():
        termination = "cancelled"
        return finish(None, "abstain", ("cancelled",))
    root = generate(state, world, opponent_id, now=now, horizon=budget.horizon,
                    policy=policy, memory_policy=memory_policy)
    if not root.actions:
        termination = "unsupported_state_or_rules"
        return finish(None, "abstain", root.reasons)
    belief, why = assess(state, world, opponent_id, now=now, policy=memory_policy)
    if belief is None:
        termination = "unsupported_memory"
        return finish(None, "abstain", why)
    reason = stop()
    if reason:
        return fallback(reason)
    if (not is_dataclass(evaluator) or not evaluator.__dataclass_params__.frozen
            or getattr(evaluator, "domain", None) != DOMAIN
            or not isinstance(evaluator_version, str) or not evaluator_version.strip()
            or getattr(evaluator, "score_kind", None) != "synthetic_utility_not_probability"
            or not callable(getattr(evaluator, "score", None))):
        return fallback("evaluator_unavailable")
    pos, _ = read_position(state, world)
    root_resource_value = economy.terminal_value(pos.credits)
    first_round = pos.round
    final_round = first_round + budget.horizon - 1
    root_actions = {x.move.label: x for x in root.actions}
    initial_profiles = tuple(x for x in world.profiles if x.profile_id in belief.profile_ids)

    def settle(node):
        profiles = initial_profiles if node.position.round == first_round else world.profiles
        values = tuple(formation(world, node.position.board_ids, x) for x in profiles)
        scores = tuple(evaluator.score(x) for x in values)
        if any(not number(x) for x in scores):
            raise ValueError("nonfinite_evaluator_output")
        frame = world.frame(node.position.round)
        worst = min(scores)
        weighted = worst * frame.utility_weight
        if not number(weighted):
            raise ValueError("weighted_utility_overflow")
        trace = RoundTrace(node.position.round, node.position.board_ids, node.position.credits,
                           values, worst, frame.utility_weight, weighted,
                           "observed_memory_scenarios" if node.position.round == first_round
                           else "all_declared_profiles_future_uncertain")
        return trace

    def visit(node):
        nonlocal nodes, duplicates, completed, termination
        reason = stop()
        if reason:
            termination = reason
            return False
        candidates = moves(node.position)
        # End the round first to obtain a complete baseline incumbent early.
        candidates = sorted((x for x in candidates if x.kind != "hold"),
                            key=lambda x: (x.kind != "end_round", x.label))
        for move in candidates:
            if node.first_move is None and move.label not in root_actions:
                continue
            if move.kind != "end_round" and node.prep_used >= budget.max_prep_actions:
                continue
            if move_reasons(node.position, world, move, state.confirmed_bans):
                continue
            reason = stop()
            if reason or nodes >= budget.max_nodes:
                termination = reason or "node_budget_exhausted"
                return False
            try:
                outcome = transition(node.position, world, move, bans=state.confirmed_bans,
                                     final_round=final_round)
            except ValueError:
                # A declared capacity decrease can make this particular branch unsupported.
                continue
            nodes += 1
            path = node.path + ("r" + str(node.position.round) + ":" + move.label,)
            total = node.total - outcome.switching_cost
            traces = node.traces
            if outcome.settled_round is not None:
                trace = settle(node)
                total += trace.weighted_value
                traces += (trace,)
            if not number(total):
                raise ValueError("cumulative_utility_overflow")
            first = node.first_move or move.label
            child = Node(outcome.position, path, total, node.switching_cost + outcome.switching_cost,
                         traces, 0 if outcome.settled_round is not None else node.prep_used + 1, first,
                         node.resource_ledger + (StepTrace(node.position.round, move.label,
                             node.position.credits, outcome.position.credits, outcome.position.round,
                             node.position.board_ids, outcome.position.board_ids, outcome.position.discarded_ids,
                             outcome.switching_cost, outcome.credits_spent, outcome.income_received,
                             outcome.position.hand_ids, outcome.position.offer_ids, outcome.position.capacity),))
            reason = stop()
            if reason:
                termination = reason
                return False
            if outcome.terminal:
                completed += 1
                reserve_value = economy.terminal_value(outcome.position.credits)
                combined = total + reserve_value
                if not number(combined):
                    raise ValueError("combined_utility_overflow")
                choice = Alternative(first, path, combined, child.switching_cost, traces, outcome.position,
                                     child.resource_ledger, reserve_value, reserve_value - root_resource_value)
                previous = choices.get(first)
                if previous is None or alternative_key(choice) < alternative_key(previous):
                    choices[first] = choice
                continue
            signature = (child.position, child.prep_used, first)
            previous = visited.get(signature)
            if previous is not None and previous >= total:
                duplicates += 1
                continue
            visited[signature] = total
            if not visit(child):
                return False
        return True

    try:
        exhaustive = visit(Node(pos))
    except Exception:
        # Preserve the independent hard gate when a replaceable evaluator fails.
        return fallback("evaluator_or_transition_unavailable")
    if termination == "cancelled":
        return fallback("cancelled")
    if not choices:
        return fallback(termination if termination != "complete" else "no_supported_complete_horizon")
    best = min(choices.values(), key=alternative_key)
    limited = not exhaustive
    reasons = ("best_completed_declared_worst_case_path", "continuations_require_new_observation_and_replanning")
    if economy.enabled:
        reasons += ("explicit_terminal_credit_option_value", "economy_weights_are_not_calibrated_game_rules")
    if limited:
        reasons += (termination, "unexplored_paths_may_be_better")
    return finish(root_actions[best.first_move], "budget_limited" if limited else "recommend",
                  reasons, exhaustive=exhaustive)


def alternative_key(item):
    return (-item.total_utility, len(item.path), item.first_move != "end_round", item.path)
