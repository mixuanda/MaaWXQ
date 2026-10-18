"""Read observation JSONL and explain advisory decisions at explicit cutoffs."""

import argparse
from collections import Counter
from dataclasses import asdict
import json
from pathlib import Path
import sys

from .codec import observation_from_dict, registry_from_dict, timestamp
from .contracts import MatchState, identifier, to_dict
from .policy import Policy, decide
from .rolling.demo import world_from_dict
from .rolling.economy import EconomyObjective
from .rolling.memory import MemoryPolicy
from .rolling.model import formation, formation_ban_conflicts, read_position
from .rolling.search import Budget, plan
from .state import reduce_observation

SCHEMA = "strategy-session/1"
MAX_EVENTS = 2048
MAX_POINTS = 16
MAX_BYTES = 16 * 1024 * 1024


def _object(value, allowed, name):
    if not isinstance(value, dict) or set(value) - set(allowed):
        raise ValueError(name + " must be an object with supported keys")
    return value


def _unique_object(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            raise ValueError("duplicate JSON key: " + key)
        value[key] = item
    return value


def _invalid_constant(value):
    raise ValueError("nonfinite JSON constant: " + value)


def _json(text):
    return json.loads(text, object_pairs_hook=_unique_object, parse_constant=_invalid_constant)


def read_request(path):
    path = Path(path)
    if path.stat().st_size > MAX_BYTES:
        raise ValueError("request exceeds input byte limit")
    return _json(path.read_text(encoding="utf-8-sig"))


def observations_from_jsonl(text):
    if len(text.encode("utf-8")) > MAX_BYTES:
        raise ValueError("observation log exceeds input byte limit")
    events = []
    for line_number, line in enumerate(text.lstrip("\ufeff").splitlines(), 1):
        if not line.strip():
            continue
        if len(events) >= MAX_EVENTS:
            raise ValueError("observation log exceeds event limit")
        try:
            events.append(observation_from_dict(_json(line)))
        except (ValueError, TypeError) as error:
            raise ValueError("observation line " + str(line_number) + ": " + str(error)) from error
    # Preserve file order for ties. The reducer still checks origin and versions.
    return tuple(sorted(events, key=lambda event: event.ingested_at))


def read_observations(path):
    path = Path(path)
    if path.stat().st_size > MAX_BYTES:
        raise ValueError("observation log exceeds input byte limit")
    return observations_from_jsonl(path.read_text(encoding="utf-8-sig"))


def _snapshot(state):
    return {
        "context": {key: getattr(state, key) for key in
                    ("match_id", "lifecycle", "round", "phase", "game_build", "rules_version",
                     "state_version", "ban_version")},
        "own_fields": [to_dict(item) for item in state.fields],
        "opponent_memory": [to_dict(item) for item in state.opponents],
        "confirmed_bans": list(state.confirmed_bans),
        "ban_evidence": to_dict(state.ban_evidence) if state.ban_evidence else None,
    }


def _link_changes(before, after, name):
    old, new = dict(getattr(before, name)), dict(getattr(after, name))
    return {"gained": [[key, new[key]] for key in sorted(new.keys() - old.keys())],
            "lost": [[key, old[key]] for key in sorted(old.keys() - new.keys())],
            "value_delta": sum(new.values()) - sum(old.values())}


def _rolling_ranking(result, state, world):
    baseline = {}
    pos, _ = read_position(state, world)
    if pos is not None and result.belief and not formation_ban_conflicts(
            world, pos.board_ids, state.confirmed_bans):
        try:
            baseline = {profile.profile_id: formation(world, pos.board_ids, profile)
                        for profile in world.profiles if profile.profile_id in result.belief.profile_ids}
        except ValueError:
            baseline = {}
    rows = []
    best = result.alternatives[0].total_utility if result.alternatives else None
    for rank, item in enumerate(result.alternatives, 1):
        changes = []
        for profile in item.rounds[0].profiles:
            before = baseline.get(profile.profile_id)
            if before is not None:
                changes.append({
                    "profile_id": profile.profile_id,
                    "isolated_value_delta": profile.isolated_value - before.isolated_value,
                    "pair_links": _link_changes(before, profile, "pair_links"),
                    "threshold_links": _link_changes(before, profile, "threshold_links"),
                    "opponent_adjustment_delta": profile.opponent_adjustment - before.opponent_adjustment,
                    "formation_value_delta": profile.total - before.total,
                })
        rows.append({
            "rank": rank, "candidate": item.first_move,
            "selected": bool(result.selected and result.selected.move.label == item.first_move),
            "score": item.total_utility, "gap_from_best": best - item.total_utility,
            "score_components": {
                "weighted_round_utility": sum(trace.weighted_value for trace in item.rounds),
                "switching_utility_cost": item.switching_cost,
                "terminal_reserve_value": item.terminal_resource_value,
            },
            "economy": {
                "credits_spent": sum(step.credits_spent for step in item.resource_ledger),
                "income_received": sum(step.income_received for step in item.resource_ledger),
                "terminal_credits": item.terminal_position.credits,
                "reserve_value_delta_from_root": item.resource_value_delta_from_root,
            },
            "first_settlement_link_changes": changes,
            "baseline_comparison": "available" if changes else "unavailable_not_a_legal_supported_baseline",
            "analysis_path": list(item.path),
            "analysis_path_is_executable": False,
            "rounds": [to_dict(trace) for trace in item.rounds],
            "resource_ledger": [to_dict(step) for step in item.resource_ledger],
        })
    return rows


def _reviewed_ranking(result):
    eligible = sorted((item for item in result.evaluations if item.accepted),
                      key=lambda item: (-item.score, item.candidate.candidate_id))
    return [{"rank": index, "candidate": item.candidate.operation,
             "candidate_id": item.candidate.candidate_id,
             "opponent_id": item.candidate.opponent_id,
             "selected": bool(result.selected and result.selected == item.candidate),
             "score": item.score, "gap_from_best": eligible[0].score - item.score,
             "score_components": [to_dict(value) for value in item.components],
             "resource_costs": [to_dict(value) for value in item.candidate.resource_costs],
             "expected_results": list(item.candidate.expected_results)}
            for index, item in enumerate(eligible, 1)]


def _action_proposal(result, engine):
    if result.selected is None:
        return None
    rolling = engine == "synthetic_rolling"
    intent = result.selected.intent if rolling else result.selected
    return {"schema_version": "strategy-action-proposal/1", "execution_allowed": False,
            "intent": to_dict(intent),
            "analysis_move": to_dict(result.selected.move) if rolling else None,
            "memory_digest": result.selected.memory_digest if rolling else None,
            "world_digest": result.selected.world_digest if rolling else None,
            "controller_obligations": ["revalidate_against_fresh_state_and_rules",
                                       "bind_semantic_intent_to_current_game_ui",
                                       "apply_single_owner_input_and_stop_guards",
                                       "verify_separately_observed_postconditions"],
            "postcondition_contract": "required_from_reviewed_game_adapter_not_inferred_from_score"}


def decide_observations(request, observation_records, *, allow_test_rules=False):
    """Software-facing API: recognizers may supply the same records as JSONL.

    No manual actor, file, desktop tool or input API is required. The controller
    receives bound semantic intents, not a queue of speculative future actions.
    """
    if not isinstance(observation_records, (list, tuple)) or len(observation_records) > MAX_EVENTS:
        raise ValueError("bounded observation record sequence required")
    events = tuple(observation_from_dict(item) for item in observation_records)
    return build_report(request, events, allow_test_rules=allow_test_rules)


def configure_request(request, *, allow_test_rules=False):
    """Decode frozen engine settings without starting a decision."""
    _object(request, ("schema_version", "engine", "label", "rule_data", "policy",
                      "memory_policy", "decision_points"), "session request")
    if request.get("schema_version") != SCHEMA:
        raise ValueError("unsupported strategy session schema")
    engine = request.get("engine")
    if engine not in ("reviewed_rules", "synthetic_rolling"):
        raise ValueError("engine must be reviewed_rules or synthetic_rolling")
    if "label" in request and not isinstance(request["label"], str):
        raise ValueError("label must be text")
    settings = _object(request.get("policy", {}),
                       set(Policy.__dataclass_fields__) - {"allow_test_rules"}, "policy")
    policy = Policy(**settings, allow_test_rules=allow_test_rules)
    memory_settings = _object(request.get("memory_policy", {}),
                              MemoryPolicy.__dataclass_fields__, "memory policy")
    memory_policy = MemoryPolicy(**memory_settings)
    if not isinstance(request.get("rule_data"), dict):
        raise ValueError("rule_data must be an explicit registry or world object")
    rules = (world_from_dict(request["rule_data"]) if engine == "synthetic_rolling"
             else registry_from_dict(request["rule_data"]))
    return engine, rules, policy, memory_policy


def evaluate_state(state, configured, point, *, at, available, total_events):
    """Shared typed-state engine for the replay API and incremental advisor."""
    engine, rules, policy, memory_policy = configured
    _object(point, ("point_id", "decision_at", "opponent_id", "budget", "economy"), "decision point")
    point_id = point["point_id"]
    identifier(point_id)
    if engine == "synthetic_rolling":
        identifier(point.get("opponent_id"))
        budget = Budget(**_object(point.get("budget", {}), Budget.__dataclass_fields__, "budget"))
        economy = EconomyObjective(**_object(point.get("economy", {}),
                                   ("reserve_target", "value_per_credit"), "economy"))
        result = plan(state, rules, point["opponent_id"], now=at, budget=budget,
                      policy=policy, memory_policy=memory_policy, economy=economy)
        ranking = _rolling_ranking(result, state, rules)
        rejected = [{"candidate": name, "reasons": list(reasons)}
                    for name, reasons in result.root_rejections]
        selected = result.selected.move.label if result.selected else None
        status = result.status
        score_kind = result.score_kind
    else:
        if set(point) & {"opponent_id", "budget", "economy"}:
            raise ValueError("rolling-only point settings cannot affect reviewed_rules")
        result = decide(state, rules, now=at, policy=policy)
        ranking = _reviewed_ranking(result)
        rejected = [{"candidate": item.candidate.operation,
                     "candidate_id": item.candidate.candidate_id,
                     "reasons": list(item.reasons)} for item in result.evaluations if not item.accepted]
        selected = result.selected.operation if result.selected else None
        status = "recommend" if selected else "abstain"
        score_kind = result.score_kind
    row = {
        "point_id": point_id, "decision_at": at.isoformat(), "status": status,
        "execution_allowed": False, "rule_domain": rules.domain,
        "selected": selected, "score_kind": score_kind,
        "action_proposal": _action_proposal(result, engine),
        "blocking_gaps": ([{"code": reason.partition(":")[0],
                            "detail": reason.partition(":")[2] or None}
                           for reason in result.reasons]
                          if result.selected is None or status == "fallback" else []),
        "snapshot": _snapshot(state),
        "input_window": {"available_event_ids": [event.event_id for event in available],
                         "events_after_cutoff": total_events - len(available),
                         "source_counts": dict(sorted(Counter(event.source.kind for event in available).items()))},
        "ranking_scope": "completed_paths_only" if engine == "synthetic_rolling" else "accepted_candidates",
        "ranking": ranking, "rejected": rejected,
        "reasons": list(result.reasons), "core_result": to_dict(result),
    }
    return row, result


def build_report(request, events, *, allow_test_rules=False):
    """Rebuild each cutoff from observations; outcomes and future events stay out."""
    engine, rules, policy, memory_policy = configure_request(request, allow_test_rules=allow_test_rules)
    points = request.get("decision_points")
    if not isinstance(points, list) or not 1 <= len(points) <= MAX_POINTS:
        raise ValueError("one through sixteen decision points required")
    if not isinstance(events, tuple) or len(events) > MAX_EVENTS:
        raise ValueError("bounded observation tuple required")
    rows, point_ids, previous_at = [], set(), None
    for point in points:
        _object(point, ("point_id", "decision_at", "opponent_id", "budget", "economy"), "decision point")
        point_id, at = point["point_id"], timestamp(point["decision_at"])
        identifier(point_id)
        if point_id in point_ids or (previous_at is not None and at < previous_at):
            raise ValueError("unique points in nondecreasing cutoff order required")
        point_ids.add(point_id)
        previous_at = at
        state = MatchState()
        available = tuple(event for event in events if event.ingested_at <= at and event.observed_at <= at)
        for event in sorted(available, key=lambda event: event.ingested_at):
            state = reduce_observation(state, event, now=at)
        row, _ = evaluate_state(state, (engine, rules, policy, memory_policy), point,
                                at=at, available=available, total_events=len(events))
        rows.append(row)
    return {"schema_version": "strategy-session-report/1", "request_schema": SCHEMA,
            "engine": engine, "label": request.get("label", ""), "rule_domain": rules.domain,
            "execution_allowed": False, "placement_probabilities": None,
            "policy": asdict(policy), "memory_policy": asdict(memory_policy), "points": rows}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--request", required=True, type=Path)
    parser.add_argument("--observations", required=True, type=Path, help="JSONL path or - for stdin")
    parser.add_argument("--allow-test-rules", action="store_true")
    parser.add_argument("--output", type=Path, help="optional JSON report path; keep real evidence private")
    args = parser.parse_args()
    try:
        events = (observations_from_jsonl(sys.stdin.read(MAX_BYTES + 1)) if str(args.observations) == "-"
                  else read_observations(args.observations))
        report = build_report(read_request(args.request), events,
                              allow_test_rules=args.allow_test_rules)
        output = json.dumps(report, indent=2, ensure_ascii=True, allow_nan=False) + "\n"
        if args.output:
            if args.output.resolve() in (args.request.resolve(), args.observations.resolve()):
                raise ValueError("report must not overwrite request or observations")
            args.output.write_text(output, encoding="utf-8")
        else:
            print(output, end="")
    except (ValueError, KeyError, TypeError, OSError) as error:
        parser.exit(2, "Invalid strategy session: " + str(error) + "\n")


if __name__ == "__main__":
    main()
