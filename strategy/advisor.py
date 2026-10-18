"""Incremental software advisor and persistent JSONL request/response transport."""

import argparse
from copy import deepcopy
from datetime import datetime
import json
from pathlib import Path
import sys
import uuid

from .codec import observation_from_dict, timestamp
from .contracts import MatchState, aware, identifier
from .policy import filter_candidates
from .rolling.actions import revalidate
from .session import (MAX_BYTES, MAX_EVENTS, _json, _object, _snapshot, configure_request,
                      evaluate_state, read_request)
from .state import reduce_observation


def _time(value):
    return aware(value) if isinstance(value, datetime) else timestamp(value)


class Advisor:
    """One serialized producer/controller owns this object; no input is sent.

    State and issued candidates remain typed immutable core records. Returned
    dictionaries cannot mutate the candidate used by the independent final gate.
    """

    def __init__(self, request, *, allow_test_rules=False):
        self._configured = configure_request(deepcopy(request), allow_test_rules=allow_test_rules)
        self._state = MatchState()
        self._selected = None
        self._proposal_id = None
        self._instance = uuid.uuid4().hex
        self._generation = 0
        self._invalidation_reason = None
        self._invalidation_time = None

    @property
    def state(self):
        return self._state

    def observe(self, record, *, now):
        """Accept an actual producer record without inventing missing fields."""
        return self.observe_batch([record], now=now)["receipts"][0]

    def observe_batch(self, records, *, now):
        """Commit one frame's events atomically; malformed siblings cannot partly update state."""
        if not isinstance(records, (list, tuple)) or not 1 <= len(records) <= MAX_EVENTS:
            raise ValueError("nonempty bounded observation batch required")
        events = tuple(observation_from_dict(record) for record in records)
        at, updated, receipts = _time(now), self._state, []
        for event in events:
            previous = updated
            updated = reduce_observation(previous, event, now=at)
            if len(updated.events) > MAX_EVENTS:
                raise ValueError("active match exceeds observation event limit")
            receipts.append({"schema_version": "strategy-observation-receipt/1",
                             "event_id": event.event_id, "state_changed": updated is not previous,
                             "match_id": updated.match_id, "state_version": updated.state_version,
                             "ban_version": updated.ban_version, "execution_allowed": False})
        self._state = updated
        policy = self._configured[2]
        if self._invalidation_reason and any(
                event.kind in ("state", "match_start")
                and (self._invalidation_time is None or event.observed_at > self._invalidation_time)
                and event.round is not None and event.phase is not None
                and event.context_confidence is not None and event.context_confidence >= policy.min_confidence
                for event in events):
            self._invalidation_reason = self._invalidation_time = None
        return {"schema_version": "strategy-observation-batch-receipt/1", "receipts": receipts,
                "state_version": updated.state_version, "execution_allowed": False}

    def invalidate(self, reason, *, now=None):
        """Keep prior observed facts while revoking an intent after an uncertain frame."""
        if not isinstance(reason, str) or not reason.strip():
            raise ValueError("an explicit invalidation reason is required")
        self._selected = self._proposal_id = None
        self._invalidation_reason = reason
        self._invalidation_time = _time(now) if now is not None else self._state.last_seen
        return {"schema_version": "strategy-proposal-revocation/1", "reason": reason,
                "state_version": self._state.state_version, "execution_allowed": False}

    def decide(self, *, decision_at, point_id="current", opponent_id=None,
               budget=None, economy=None):
        """Produce one immediate intent; replace the previous proposal handle."""
        at = _time(decision_at)
        if self._state.evidence_watermark is not None and at < self._state.evidence_watermark:
            raise ValueError("live cutoff precedes current evidence; use session replay for history")
        identifier(point_id)
        if self._invalidation_reason:
            return {"point_id": point_id, "decision_at": at.isoformat(), "status": "abstain",
                    "execution_allowed": False, "rule_domain": self._configured[1].domain,
                    "selected": None, "proposal_id": None, "action_proposal": None,
                    "blocking_gaps": [{"code": "fresh_recognition_required", "detail": self._invalidation_reason}],
                    "snapshot": _snapshot(self._state), "snapshot_eligibility": "suspended_pending_fresh_context",
                    "ranking": [], "ranking_scope": "no_current_supported_context", "rejected": [],
                    "reasons": ["fresh_recognition_required"], "core_result": None}
        point = {"point_id": point_id, "decision_at": at.isoformat()}
        for key, value in (("opponent_id", opponent_id), ("budget", budget), ("economy", economy)):
            if value is not None:
                point[key] = value
        row, result = evaluate_state(self._state, self._configured, point, at=at,
                                     available=self._state.events, total_events=len(self._state.events))
        self._generation += 1
        self._selected = result.selected
        self._invalidation_reason = None
        self._proposal_id = (self._instance + ":" + str(self._generation)) if self._selected else None
        row["proposal_id"] = self._proposal_id
        if row["action_proposal"] is not None:
            row["action_proposal"]["proposal_id"] = self._proposal_id
        return row

    def validate(self, proposal_id, *, now):
        """Recheck the issued typed candidate against current evidence and time.

        A valid intent remains advisory. The controller must separately bind the
        actual game UI and independently observe postconditions after any action.
        """
        at = _time(now)
        engine, rules, policy, memory_policy = self._configured
        reasons = ("proposal_unknown_or_superseded",)
        if self._invalidation_reason:
            reasons += ("recognition_invalidated_proposal:" + self._invalidation_reason,)
        intent = None
        if self._selected is not None and proposal_id == self._proposal_id:
            intent = self._selected.intent if engine == "synthetic_rolling" else self._selected
            if engine == "synthetic_rolling":
                reasons = revalidate(self._selected, self._state, rules, now=at,
                                     policy=policy, memory_policy=memory_policy)
            else:
                reasons = filter_candidates(self._state, rules, (self._selected,),
                                            now=at, policy=policy)[0].reasons
        return {"schema_version": "strategy-proposal-validation/1", "proposal_id": proposal_id,
                "candidate_id": intent.candidate_id if intent else None,
                "candidate_valid": not bool(reasons), "execution_allowed": False,
                "checked_at": at.isoformat(), "match_id": self._state.match_id,
                "state_version": self._state.state_version, "ban_version": self._state.ban_version,
                "expires_at": intent.expires_at.isoformat() if intent else None,
                "reasons": list(reasons)}

    def handle(self, command):
        """Handle one JSON transport command; exceptions leave input disabled."""
        if not isinstance(command, dict):
            raise ValueError("advisor command must be an object")
        operation = command.get("op")
        if operation == "observe":
            _object(command, ("op", "observation", "now"), "observe command")
            return self.observe(command["observation"], now=command["now"])
        if operation == "observe_batch":
            _object(command, ("op", "observations", "now"), "observe_batch command")
            return self.observe_batch(command["observations"], now=command["now"])
        if operation == "invalidate":
            _object(command, ("op", "reason", "now"), "invalidate command")
            return self.invalidate(command["reason"], now=command.get("now"))
        if operation == "decide":
            _object(command, ("op", "decision_at", "point_id", "opponent_id", "budget", "economy"),
                    "decide command")
            return self.decide(**{key: value for key, value in command.items() if key != "op"})
        if operation == "validate":
            _object(command, ("op", "proposal_id", "now"), "validate command")
            if not isinstance(command.get("proposal_id"), str) or not command["proposal_id"].strip():
                raise ValueError("proposal_id must be nonempty text")
            return self.validate(command["proposal_id"], now=command["now"])
        raise ValueError("unsupported advisor operation")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--request", required=True, type=Path, help="engine/rule/policy configuration")
    parser.add_argument("--allow-test-rules", action="store_true")
    args = parser.parse_args()
    try:
        advisor = Advisor(read_request(args.request), allow_test_rules=args.allow_test_rules)
    except (ValueError, KeyError, TypeError, OSError) as error:
        parser.exit(2, "Invalid advisor configuration: " + str(error) + "\n")
    while True:
        line = sys.stdin.readline(MAX_BYTES + 1)
        if not line:
            return
        if not line.strip():
            continue
        try:
            if len(line.encode("utf-8")) > MAX_BYTES:
                raise ValueError("advisor command exceeds byte limit")
            result = advisor.handle(_json(line))
            response = {"ok": True, "result": result}
        except (ValueError, KeyError, TypeError) as error:
            response = {"ok": False, "error": {"code": "invalid_advisor_command", "message": str(error)}}
        print(json.dumps(response, ensure_ascii=True, allow_nan=False), flush=True)
        if len(line) >= MAX_BYTES and not line.endswith("\n"):
            return  # Never interpret a remainder of one oversized command as a new command.


if __name__ == "__main__":
    main()
