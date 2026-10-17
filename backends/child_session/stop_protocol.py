"""Authenticated stop-message codec and replay protection, without an IPC transport."""
from datetime import datetime, timezone
import hashlib
import hmac
import json
import threading

FIELDS = {"schema_version", "session_token", "sequence", "command", "issued_at", "mac"}


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False).encode("ascii")


def _unique_fields(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            raise ValueError("duplicate_stop_field")
        value[key] = item
    return value


def _timestamp(value):
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("timezone_required")
    return parsed


class StopProtocol:
    """A local protocol state machine. Accepted messages are not remote acknowledgments."""
    def __init__(self, key, session_token, *, ttl_seconds=3):
        if not isinstance(key, bytes) or len(key) < 32:
            raise ValueError("stop_key_requires_32_random_bytes_or_more")
        if not isinstance(session_token, str) or not 1 <= len(session_token) <= 128:
            raise ValueError("invalid_session_token")
        if type(ttl_seconds) is not int or not 1 <= ttl_seconds <= 10:
            raise ValueError("invalid_stop_ttl")
        self._key, self._token, self._ttl = key, session_token, ttl_seconds
        self.last_sequence = 0
        self._sequence_lock = threading.Lock()

    def encode_stop(self, sequence, *, issued_at=None):
        if type(sequence) is not int or sequence < 1:
            raise ValueError("positive_stop_sequence_required")
        issued_at = issued_at or datetime.now(timezone.utc).isoformat()
        _timestamp(issued_at)
        message = {"schema_version": "child-stop/1", "session_token": self._token, "sequence": sequence,
                   "command": "stop", "issued_at": issued_at}
        message["mac"] = hmac.new(self._key, _canonical(message), hashlib.sha256).hexdigest()
        return _canonical(message)

    def receive(self, payload, backend, *, now=None):
        rejected = {"protocol_accepted": False, "transport_delivered": False, "remote_release_confirmed": False}
        if not isinstance(payload, bytes) or len(payload) > 4096:
            return rejected | {"reason": "invalid_stop_payload_size"}
        try:
            message = json.loads(payload, object_pairs_hook=_unique_fields)
            if not isinstance(message, dict) or set(message) != FIELDS:
                raise ValueError("invalid_fields")
            signature = message.pop("mac")
            expected = hmac.new(self._key, _canonical(message), hashlib.sha256).hexdigest()
            if not isinstance(signature, str) or not hmac.compare_digest(signature, expected):
                return rejected | {"reason": "stop_authentication_failed"}
            if (message["schema_version"] != "child-stop/1" or message["command"] != "stop" or
                    message["session_token"] != self._token):
                return rejected | {"reason": "stop_session_or_command_mismatch"}
            sequence = message["sequence"]
            if type(sequence) is not int or sequence < 1:
                return rejected | {"reason": "stop_replay_or_invalid_sequence"}
            now = now or datetime.now(timezone.utc)
            if now.tzinfo is None:
                raise ValueError("timezone_required")
            age = (now - _timestamp(message["issued_at"])).total_seconds()
            if not 0 <= age <= self._ttl:
                return rejected | {"reason": "stop_message_stale_or_future"}
        except (ValueError, TypeError, KeyError, AttributeError, UnicodeError):
            return rejected | {"reason": "invalid_stop_payload"}
        with self._sequence_lock:
            if sequence <= self.last_sequence:
                return rejected | {"reason": "stop_replay_or_invalid_sequence"}
            # Consume before cleanup, which may complete after a newer stop callback.
            self.last_sequence = sequence
        # Local revocation is real; delivery/release in another process is not implemented.
        receipt = backend.stop_local()
        return {"protocol_accepted": True, "scope": "local_protocol_only", "reason": "local_stop_latched",
                "status": "local_permission_revoked", "stop_generation": receipt["stop_generation"],
                "transport_delivered": False, "remote_release_confirmed": False}
