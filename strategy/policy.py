"""Hard constraints precede all transparent, evidence-backed heuristic scores."""

from dataclasses import asdict, dataclass, replace
from datetime import timedelta
import math

from .contracts import (BoundPrecondition, CandidateAction, CandidateEvaluation,
                        Decision, ScoreComponent, aware, number)


@dataclass(frozen=True)
class Policy:
    min_confidence: float = 0.8
    max_state_age_seconds: float = 30
    max_field_age_seconds: float = 30
    max_round_age: int = 0
    advice_ttl_seconds: float = 5
    max_candidates: int = 64
    allow_test_rules: bool = False

    def __post_init__(self):
        for value in (self.min_confidence, self.max_state_age_seconds,
                      self.max_field_age_seconds, self.advice_ttl_seconds):
            if not number(value) or value < 0:
                raise ValueError("policy limits require finite nonnegative numbers")
        if self.min_confidence > 1 or self.advice_ttl_seconds == 0:
            raise ValueError("invalid confidence/expiry limit")
        if type(self.max_round_age) is not int or self.max_round_age < 0:
            raise ValueError("round age must be a nonnegative integer")
        if type(self.max_candidates) is not int or not 1 <= self.max_candidates <= 256:
            raise ValueError("candidate budget must be in [1, 256]")
        if type(self.allow_test_rules) is not bool:
            raise ValueError("test rules require explicit boolean opt-in")


def _field(state, path, opponent_id):
    owner, key = path.split(".")
    if owner == "self":
        fields = state.fields
    else:
        opponent = next((x for x in state.opponents if x.opponent_id == opponent_id), None)
        fields = opponent.fields if opponent else ()
    return next((x for x in fields if x.field.key == key), None)


def _candidate(state, registry, rule, opponent_id, issued_at, policy):
    requirements = _requirements(rule)
    preconditions = [BoundPrecondition(x.path, _field(state, x.path, opponent_id), x.operator, x.value)
                     for x in requirements]
    paths = {x.path for x in requirements}
    preconditions.extend(BoundPrecondition(x.path, _field(state, x.path, opponent_id))
                         for x in rule.score_terms if x.path not in paths)
    candidate = CandidateAction(
        candidate_id="pending", match_id=state.match_id or "unresolved", state_version=state.state_version,
        rules_version=registry.rules_version, rules_digest=registry.fingerprint,
        rules_domain=registry.domain,
        ban_version=state.ban_version, round=state.round, phase=state.phase,
        evidence_watermark=state.evidence_watermark, rule_id=rule.rule_id,
        operation=rule.operation, opponent_id=opponent_id, ban_tags=rule.ban_tags,
        resource_costs=rule.resource_costs, preconditions=tuple(preconditions),
        issued_at=issued_at, expires_at=issued_at + timedelta(seconds=policy.advice_ttl_seconds),
        expected_results=rule.expected_results,
        invalidation_conditions=("match/state/round/phase/evidence watermark changes",
                                 "ban version or rule content/version changes",
                                 "required evidence becomes unknown, uncertain or stale",
                                 "expiry reached; re-observe after any material action",
                                 "advisory only; no input authorization"))
    from .contracts import digest
    return replace(candidate, candidate_id=digest(candidate)[:24])


def _requirements(rule):
    from .rules import Requirement
    return rule.requirements + tuple(Requirement(x.path, "ge", x.amount) for x in rule.resource_costs)


def generate_candidates(state, registry, *, now, policy=Policy()):
    aware(now)
    candidates = []
    for rule in sorted(registry.rules, key=lambda x: x.rule_id):
        targets = ([x.opponent_id for x in state.opponents] or [None]) if rule.targets_opponent else [None]
        for opponent_id in targets:
            if len(candidates) >= policy.max_candidates:
                raise ValueError("candidate budget exceeded; narrow the reviewed rule subset")
            candidates.append(_candidate(state, registry, rule, opponent_id, now, policy))
    return tuple(candidates)


def _evidence_source_kinds(state):
    """Check both history and caches; a rebuilt cache must not cross domains."""
    kinds = {event.source.kind for event in state.events}
    kinds.update(item.source.kind for item in state.fields)
    kinds.update(item.source.kind for opponent in state.opponents for item in opponent.fields)
    if state.ban_evidence is not None:
        kinds.add(state.ban_evidence.source.kind)
    return kinds


def _global_reasons(state, registry, now, policy):
    reasons = []
    if state.lifecycle != "active" or state.match_id is None:
        reasons.append("match_not_active")
    if state.round is None or state.phase is None:
        reasons.append("context_unknown")
    if state.context_confidence is None or state.context_confidence < policy.min_confidence:
        reasons.append("context_confidence_insufficient")
    if state.last_seen is None or not 0 <= (now - state.last_seen).total_seconds() <= policy.max_state_age_seconds:
        reasons.append("state_stale_or_future")
    if state.evidence_watermark is None or state.evidence_watermark > now:
        reasons.append("evidence_unavailable_at_decision_time")
    if not registry.rules:
        reasons.append("rules_unavailable")
    if state.game_build is None or state.game_build != registry.game_build or state.rules_version != registry.rules_version:
        reasons.append("rules_build_or_version_mismatch")
    if not registry.ban_semantics_verified:
        reasons.append("ban_semantics_unverified")
    bans = state.ban_evidence
    if (bans is None or bans.field.status != "observed" or bans.field.confidence is None
            or bans.field.confidence < max(0.8, policy.min_confidence)):
        reasons.append("bans_unknown_or_uncertain")
    elif bans.last_seen > now or (bans.round is not None and state.round is not None and bans.round > state.round):
        reasons.append("ban_evidence_from_future_context")
    source_kinds = _evidence_source_kinds(state)
    if registry.domain == "test_rules_not_gameplay":
        if not policy.allow_test_rules:
            reasons.append("test_rules_require_explicit_opt_in")
        if source_kinds - {"synthetic"}:
            reasons.append("non_synthetic_evidence_not_test_rules")
    if registry.domain == "gameplay" and "synthetic" in source_kinds:
        reasons.append("synthetic_evidence_not_gameplay")
    return reasons


def _evidence_reasons(item, state, now, policy, path):
    if item is None or item.field.status != "observed":
        return ["field_unknown_or_ambiguous:" + path]
    reasons = []
    if item.field.confidence is None or item.field.confidence < policy.min_confidence:
        reasons.append("field_confidence_insufficient:" + path)
    if not 0 <= (now - item.last_seen).total_seconds() <= policy.max_field_age_seconds:
        reasons.append("field_stale_or_future:" + path)
    if (item.round is None or state.round is None
            or not 0 <= state.round - item.round <= policy.max_round_age):
        reasons.append("field_round_age_invalid:" + path)
    if item.phase is None or item.phase != state.phase:
        reasons.append("field_phase_invalid:" + path)
    return reasons


def filter_candidates(state, registry, candidates, *, now, policy=Policy()):
    """Return hard rejections without scoring; never mutate input state."""
    aware(now)
    if len(candidates) > policy.max_candidates:
        raise ValueError("candidate budget exceeded")
    rules = {x.rule_id: x for x in registry.rules}
    global_reasons = _global_reasons(state, registry, now, policy)
    evaluations = []
    for candidate in candidates:
        reasons = list(global_reasons)
        rule = rules.get(candidate.rule_id)
        if candidate.match_id != state.match_id or candidate.state_version != state.state_version:
            reasons.append("candidate_state_changed")
        if candidate.ban_version != state.ban_version:
            reasons.append("candidate_ban_version_changed")
        if candidate.rules_digest != registry.fingerprint or candidate.rules_version != registry.rules_version:
            reasons.append("candidate_rules_changed")
        if not candidate.issued_at <= now < candidate.expires_at:
            reasons.append("candidate_expired_or_not_yet_issued")
        if rule is None:
            reasons.append("rule_unknown")
        else:
            if rule.verification != "verified":
                reasons.append("rule_unverified_or_conflicting:" + rule.rule_id)
            if candidate != _candidate(state, registry, rule, candidate.opponent_id, candidate.issued_at, policy):
                reasons.append("candidate_binding_or_payload_changed")
            if state.phase not in rule.phases:
                reasons.append("phase_not_legal")
            if set(rule.ban_tags) & set(state.confirmed_bans):
                reasons.append("confirmed_ban")
            if rule.targets_opponent and not any(x.opponent_id == candidate.opponent_id for x in state.opponents):
                reasons.append("opponent_identity_unresolved")
            if not rule.targets_opponent and candidate.opponent_id is not None:
                reasons.append("unexpected_opponent_target")
            requirements = _requirements(rule)
            paths = {x.path for x in requirements} | {x.path for x in rule.score_terms}
            for path in sorted(paths):
                item = _field(state, path, candidate.opponent_id)
                reasons.extend(_evidence_reasons(item, state, now, policy, path))
            for required in requirements:
                item = _field(state, required.path, candidate.opponent_id)
                if item is None or item.field.status != "observed":
                    continue
                value = item.field.value
                if required.operator == "eq" and (type(value) is not type(required.value) or value != required.value):
                    reasons.append("precondition_failed:" + required.path)
                if required.operator == "ge" and (not number(value) or value < required.value):
                    reasons.append("resource_or_capacity_limit:" + required.path)
            for term in rule.score_terms:
                item = _field(state, term.path, candidate.opponent_id)
                if item and item.field.status == "observed" and not number(item.field.value):
                    reasons.append("score_field_not_numeric:" + term.path)
        evaluations.append(CandidateEvaluation(candidate, not reasons, tuple(dict.fromkeys(reasons))))
    return tuple(evaluations)


def decide(state, registry, *, now, policy=Policy(), candidates=None):
    """Pure recommendation. Scores are arbitrary reviewed weights, never win rates."""
    if candidates is None:
        candidates = generate_candidates(state, registry, now=now, policy=policy)
    evaluations = filter_candidates(state, registry, candidates, now=now, policy=policy)
    scored = []
    rules = {x.rule_id: x for x in registry.rules}
    for evaluation in evaluations:
        if not evaluation.accepted:
            scored.append(evaluation)
            continue
        candidate = evaluation.candidate
        components = []
        for term in rules[candidate.rule_id].score_terms:
            item = _field(state, term.path, candidate.opponent_id)
            value = float(item.field.value)
            components.append(ScoreComponent(term.path, value, term.weight, value * term.weight,
                                             term.definition, item.event_id))
        total = sum(x.contribution for x in components)
        if not math.isfinite(total):
            scored.append(replace(evaluation, accepted=False, reasons=("score_overflow",)))
        else:
            scored.append(replace(evaluation, score=total, components=tuple(components)))
    ranked = sorted((x for x in scored if x.accepted), key=lambda x: (-x.score, x.candidate.candidate_id))
    selected = ranked[0].candidate if ranked else None
    reasons = (("highest_supported_heuristic_score",) if selected else
               tuple(dict.fromkeys(_global_reasons(state, registry, now, policy)
                                   + ["no_supported_candidate"])) )
    from .contracts import digest
    result = Decision("pending", state.match_id, state.state_version, now, selected,
                      tuple(scored), reasons, registry.fingerprint, registry.domain,
                      tuple(sorted(asdict(policy).items())))
    return replace(result, decision_id=digest(result)[:24])
