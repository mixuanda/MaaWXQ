"""Authenticated heartbeat/action envelopes. No Windows IPC endpoint is opened here."""
from datetime import datetime, timezone
import hashlib
import hmac
import json
import threading

from .control import ActionRequest, InputAction, SessionBinding
from .stop_protocol import _canonical, _timestamp, _unique_fields

FIELDS = {"schema_version", "connection_id", "binding_digest", "sequence", "stop_generation",
          "kind", "issued_at", "body", "mac"}


class ControlProtocol:
    """Separate from the priority stop lane, so action ordering cannot suppress stop."""
    def __init__(self, key, binding, *, ttl_seconds=3):
        if not isinstance(key, bytes) or len(key) < 32:
            raise ValueError("control_key_requires_at_least_32_bytes")
        if type(ttl_seconds) is not int or not 1 <= ttl_seconds <= 10:
            raise ValueError("invalid_control_message_ttl")
        if not isinstance(binding, SessionBinding):
            raise ValueError("validated_protocol_binding_required")
        self._key, self.binding, self._ttl = key, binding, ttl_seconds
        self._lock = threading.Lock()
        self.last_sequence = 0

    def encode(self, kind, sequence, stop_generation, body, *, issued_at=None):
        if kind not in ("heartbeat", "action") or type(sequence) is not int or sequence < 1:
            raise ValueError("invalid_control_message")
        if type(stop_generation) is not int or stop_generation < 0 or not isinstance(body, dict):
            raise ValueError("invalid_control_body")
        issued_at = issued_at or datetime.now(timezone.utc).isoformat()
        _timestamp(issued_at)
        message = {"schema_version": "child-control/1", "connection_id": self.binding.connection_id,
                   "binding_digest": self.binding.digest, "sequence": sequence, "stop_generation": stop_generation,
                   "kind": kind, "issued_at": issued_at, "body": body}
        message["mac"] = hmac.new(self._key, _canonical(message), hashlib.sha256).hexdigest()
        payload = _canonical(message)
        if len(payload) > 4096:
            raise ValueError("control_message_too_large")
        return payload

    def receive(self, payload, core, *, now=None):
        rejected = {"authenticated": False, "sequence_accepted": False, "transport_delivered": False,
                    "sent": False, "execution_confirmed": False}
        if not isinstance(payload, bytes) or len(payload) > 4096:
            return rejected | {"reason": "invalid_control_payload_size"}
        try:
            message = json.loads(payload, object_pairs_hook=_unique_fields)
            if not isinstance(message, dict) or set(message) != FIELDS:
                raise ValueError("invalid_fields")
            signature = message.pop("mac")
            expected = hmac.new(self._key, _canonical(message), hashlib.sha256).hexdigest()
            if not isinstance(signature, str) or not hmac.compare_digest(signature, expected):
                return rejected | {"reason": "control_authentication_failed"}
            if (message["schema_version"] != "child-control/1" or message["connection_id"] != self.binding.connection_id
                    or message["binding_digest"] != self.binding.digest or core.binding != self.binding):
                return rejected | {"reason": "control_connection_or_binding_mismatch"}
            now = now or datetime.now(timezone.utc)
            if now.tzinfo is None:
                raise ValueError("timezone_required")
            age = (now - _timestamp(message["issued_at"])).total_seconds()
            if not 0 <= age <= self._ttl:
                return rejected | {"reason": "control_message_stale_or_future"}
            sequence, generation = message["sequence"], message["stop_generation"]
            if type(sequence) is not int or sequence < 1 or type(generation) is not int or generation < 0:
                raise ValueError("invalid_sequence_or_generation")
            body = message["body"]
            if message["kind"] == "heartbeat":
                if body != {}:
                    raise ValueError("heartbeat_body_must_be_empty")
                request = None
            elif message["kind"] == "action":
                if not isinstance(body, dict) or set(body) != {"action_id", "lease_id", "operation", "code"}:
                    raise ValueError("invalid_action_fields")
                request = ActionRequest(body["action_id"], body["lease_id"], generation, self.binding.digest,
                                        InputAction(body["operation"], body["code"]))
            else:
                raise ValueError("unsupported_control_kind")
        except (ValueError, TypeError, KeyError, AttributeError, UnicodeError):
            return rejected | {"reason": "invalid_control_payload"}
        with self._lock:
            if sequence <= self.last_sequence:
                return rejected | {"reason": "control_sequence_replayed_or_reordered"}
            # Consume authenticated valid messages even when the core rejects their old generation/lease.
            self.last_sequence = sequence
            # Preserve accepted message order through core application. Stop uses a
            # separate codec/lock and must never wait for this action lane.
            result = (core.heartbeat(generation, self.binding.digest) if request is None else core.enqueue(request))
        return {"authenticated": True, "sequence_accepted": True, "scope": "local_protocol_only",
                "control_result": result, "transport_delivered": False, "sent": False, "execution_confirmed": False}
