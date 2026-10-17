"""Pure match-scoped reducer. The caller provides the clock."""

from dataclasses import replace

from .contracts import EvidenceField, MatchState, Observation, OpponentMemory, aware


def _newer(event, previous):
    if previous is None:
        return True
    if event.round is not None and previous.round is not None and event.round != previous.round:
        return event.round > previous.round and event.observed_at >= previous.last_seen
    return event.observed_at > previous.last_seen


def _evidence(event, value):
    return EvidenceField(value, event.event_id, event.source, event.observed_at,
                         event.round, event.phase)


def _merge(previous, event):
    values = {item.field.key: item for item in previous}
    for value in event.fields:
        if _newer(event, values.get(value.key)):
            values[value.key] = _evidence(event, value)
    # Missing fields, even in a full view, do not imply zero/sold/empty.
    return tuple(values[key] for key in sorted(values))


def reduce_observation(state: MatchState, event: Observation, *, now) -> MatchState:
    aware(now)
    if event.observed_at > now or event.ingested_at > now:
        raise ValueError("future evidence is unavailable at this decision point")
    if event.match_id in state.retired_match_ids:
        return state  # Delayed old-match start/update cannot restore its memory.
    if event.match_id == state.match_id:
        previous = next((x for x in state.events if x.event_id == event.event_id), None)
        if previous is not None:
            if previous != event:
                raise ValueError("event ID reused with different content")
            return state
    if event.kind == "match_start":
        if event.match_id == state.match_id:
            raise ValueError("match already started; use a new match ID")
        if state.evidence_watermark and event.observed_at < state.evidence_watermark:
            raise ValueError("new match cannot begin before the evidence watermark")
        retired = state.retired_match_ids + ((state.match_id,) if state.match_id else ())
        return MatchState(match_id=event.match_id, state_version=1,
                          game_build=event.game_build, rules_version=event.rules_version,
                          lifecycle="active", round=event.round, phase=event.phase,
                          last_seen=event.observed_at, context_confidence=event.context_confidence,
                          evidence_watermark=event.ingested_at, events=(event,),
                          retired_match_ids=retired)
    if event.match_id != state.match_id or state.lifecycle != "active":
        raise ValueError("an active matching match_start is required")
    if ((event.game_build is not None and event.game_build != state.game_build)
            or (event.rules_version is not None and event.rules_version != state.rules_version)):
        raise ValueError("build/rule changes require a new explicitly reviewed match context")
    result = replace(state, state_version=state.state_version + 1,
                     evidence_watermark=max(state.evidence_watermark, event.ingested_at),
                     events=state.events + (event,))
    if event.kind == "match_end":
        return replace(result, lifecycle="ended")
    if event.kind == "state":
        result = replace(result, fields=_merge(state.fields, event))
        if _newer(event, state):
            result = replace(result, round=event.round, phase=event.phase,
                             last_seen=event.observed_at,
                             context_confidence=event.context_confidence)
    elif event.kind == "opponent" and event.opponent_id is not None:
        memories = {x.opponent_id: x for x in state.opponents}
        old = memories.get(event.opponent_id)
        fields = _merge(old.fields if old else (), event)
        latest = _newer(event, old)
        memories[event.opponent_id] = OpponentMemory(
            event.opponent_id, event.observed_at if latest else old.last_seen,
            event.round if latest else old.round, event.coverage if latest else old.coverage, fields)
        result = replace(result, opponents=tuple(memories[key] for key in sorted(memories)))
    elif event.kind == "bans":
        value = event.fields[0]
        # Confirmed bans are a match-long hard constraint, regardless of TTL.
        confirmed = set(state.confirmed_bans)
        if value.status == "observed" and value.confidence is not None and value.confidence >= 0.8:
            confirmed.update(value.value)
        newer = _newer(event, state.ban_evidence)
        if newer or confirmed != set(state.confirmed_bans):
            result = replace(result, confirmed_bans=tuple(sorted(confirmed)),
                             ban_evidence=_evidence(event, value) if newer else state.ban_evidence,
                             ban_version=state.ban_version + 1)
    # Unresolved opponent sightings remain separate in events, never one shared opponent.
    return result
