"""Bounded child-worker control state machine; only explicit synthetic ports can submit."""
from collections import deque
from dataclasses import asdict, dataclass
import hashlib
import json
import math
import threading
import time

from .ports import DisconnectedInput, DisconnectedTransport


def _identifier(value):
    if not isinstance(value, str) or not 1 <= len(value) <= 128 or value == "unknown":
        raise ValueError("resolved_bounded_identifier_required")


def _positive(value):
    return type(value) in (int, float) and math.isfinite(value) and value > 0


@dataclass(frozen=True)
class SessionBinding:
    connection_id: str
    worker_instance_id: str
    main_session_id: int
    child_session_id: int
    worker_session_id: int
    game_session_id: int
    window_identity_version: str
    geometry_version: str

    def __post_init__(self):
        for value in (self.connection_id, self.worker_instance_id, self.window_identity_version, self.geometry_version):
            _identifier(value)
        ids = (self.main_session_id, self.child_session_id, self.worker_session_id, self.game_session_id)
        if not all(type(value) is int and 0 <= value < 0xFFFFFFFF for value in ids):
            raise ValueError("invalid_session_binding")
        if not (self.child_session_id > 0 and self.child_session_id == self.worker_session_id == self.game_session_id
                and self.child_session_id != self.main_session_id):
            raise ValueError("game_and_worker_must_share_isolated_child_session")

    @property
    def digest(self):
        return hashlib.sha256(json.dumps(asdict(self), sort_keys=True, separators=(",", ":")).encode()).hexdigest()


@dataclass(frozen=True)
class InputAction:
    operation: str
    code: int

    def __post_init__(self):
        if self.operation not in ("key_down", "key_up", "button_down", "button_up"):
            raise ValueError("unsupported_control_operation")
        upper = 255 if self.operation.startswith("key_") else 2
        lower = 1 if self.operation.startswith("key_") else 0
        if type(self.code) is not int or not lower <= self.code <= upper:
            raise ValueError("invalid_input_code")

    @property
    def ledger_key(self):
        return (self.operation.split("_")[0], self.code)


@dataclass(frozen=True)
class ActionRequest:
    action_id: str
    lease_id: str
    stop_generation: int
    binding_digest: str
    action: InputAction

    def __post_init__(self):
        for value in (self.action_id, self.lease_id, self.binding_digest):
            _identifier(value)
        if type(self.stop_generation) is not int or self.stop_generation < 0 or not isinstance(self.action, InputAction):
            raise ValueError("invalid_action_request")


@dataclass(frozen=True)
class ControlLimits:
    heartbeat_timeout_seconds: float = 1.0
    max_lease_seconds: float = 1.0
    max_hold_seconds: float = 0.5
    max_actions: int = 16
    max_queue: int = 16
    max_seen_actions: int = 256

    def __post_init__(self):
        if not all(_positive(value) and value <= 10 for value in
                   (self.heartbeat_timeout_seconds, self.max_lease_seconds, self.max_hold_seconds)):
            raise ValueError("invalid_control_deadline")
        if not all(type(value) is int and 1 <= value <= 256 for value in
                   (self.max_actions, self.max_queue, self.max_seen_actions)):
            raise ValueError("invalid_control_budget")


@dataclass
class _Held:
    since: float
    in_flight: bool = True
    releasing: bool = False


class ControlCore:
    """No loop/thread is started. A future independent supervisor must call tick()."""
    def __init__(self, binding, *, transport=None, native=None, simulation=False, clock=time.monotonic, limits=None):
        if not isinstance(binding, SessionBinding) or type(simulation) is not bool:
            raise ValueError("validated_control_context_required")
        self._binding = binding
        self.transport = transport if transport is not None else DisconnectedTransport()
        self.native = native if native is not None else DisconnectedInput()
        self.simulation = simulation
        self.clock = clock
        self.limits = ControlLimits() if limits is None else limits
        if not isinstance(self.limits, ControlLimits):
            raise ValueError("validated_control_limits_required")
        self._lock = threading.RLock()
        self._queue = deque()
        self._seen = set()
        self._held = {}
        self._lease = None
        self._lease_counter = 0
        self._heartbeat = None
        self._last_clock = None
        self._in_flight = 0
        self._closed = False
        self._close_attempted = False
        self.stop_generation = 0
        self.stop_latched = False
        self.stop_reason = None
        self.cleanup_errors = []
        self.cleanup_error_count = 0

    @property
    def binding(self):
        return self._binding

    def _record_error(self, message):
        with self._lock:
            self.cleanup_error_count += 1
            if len(self.cleanup_errors) < 16:
                self.cleanup_errors.append(message)

    def snapshot(self):
        with self._lock:
            return {"scope": "synthetic_only" if self.simulation else "unconnected",
                    "operational": False, "native_transport_implemented": False,
                    "stop_generation": self.stop_generation, "stop_latched": self.stop_latched,
                    "stop_reason": self.stop_reason, "closed": self._closed,
                    "queued": len(self._queue), "in_flight": self._in_flight,
                    "held_in_local_model": len(self._held), "active_lease": self._lease["id"] if self._lease else None,
                    "cleanup_errors": list(self.cleanup_errors), "cleanup_error_count": self.cleanup_error_count,
                    "remote_release_confirmed": False}

    def _port_reason(self):
        if self._closed:
            return "control_closed"
        if not self.simulation:
            return "native_transport_not_implemented"
        if getattr(self.transport, "scope", None) != "synthetic" or getattr(self.native, "scope", None) != "synthetic":
            return "only_explicit_synthetic_ports_supported"
        if getattr(self.transport, "connected", None) is not True:
            return "transport_not_connected"
        if getattr(self.native, "connected", None) is not True:
            return "native_input_not_connected"
        return None

    def _now(self):
        try:
            value = self.clock()
        except Exception:
            self.stop_local("monotonic_clock_unavailable")
            return None
        if type(value) not in (int, float) or not math.isfinite(value):
            self.stop_local("invalid_monotonic_clock")
            return None
        with self._lock:
            regressed = self._last_clock is not None and value < self._last_clock
            self._last_clock = value
        if regressed:
            self.stop_local("monotonic_clock_regressed")
            return None
        return value

    def tick(self):
        now = self._now()
        if now is None:
            return self.snapshot()
        with self._lock:
            reason = None
            if not self.stop_latched:
                if self._heartbeat is not None and now - self._heartbeat >= self.limits.heartbeat_timeout_seconds:
                    reason = "heartbeat_expired"
                elif self._lease and now >= self._lease["expires"]:
                    reason = "lease_expired"
                elif any(now - item.since >= self.limits.max_hold_seconds for item in self._held.values()):
                    reason = "held_input_deadline_exceeded"
                port_reason = self._port_reason()
                if port_reason and (self._heartbeat is not None or self._held or self._in_flight):
                    reason = port_reason
        if not reason:
            with self._lock:
                inspect = (not self.stop_latched and self._heartbeat is not None and not self._port_reason())
            if inspect:
                try:
                    if self.native.observe_binding() != self.binding:
                        reason = "session_or_identity_changed"
                except Exception:
                    reason = "binding_query_failed"
        if reason:
            self.stop_local(reason)
        return self.snapshot()

    def _preflight(self):
        self.tick()
        with self._lock:
            if self.stop_latched:
                return "stop_latched"
            reason = self._port_reason()
        if reason:
            return reason
        try:
            observed = self.native.observe_binding()
        except Exception:
            self.stop_local("binding_query_failed")
            return "binding_query_failed"
        if observed != self.binding:
            self.stop_local("session_or_identity_changed")
            return "session_or_identity_changed"
        with self._lock:
            return "stop_latched" if self.stop_latched else self._port_reason()

    def heartbeat(self, stop_generation, binding_digest):
        reason = self._preflight()
        if reason:
            return {"accepted": False, "reason": reason}
        now = self._now()
        with self._lock:
            if (now is None or self.stop_latched or type(stop_generation) is not int or
                    stop_generation != self.stop_generation or binding_digest != self.binding.digest):
                return {"accepted": False, "reason": "stale_generation_or_binding"}
            expired = self._heartbeat is not None and now - self._heartbeat >= self.limits.heartbeat_timeout_seconds
            if not expired:
                self._heartbeat = now
        if expired:
            self.stop_local("heartbeat_expired")
            return {"accepted": False, "reason": "heartbeat_expired"}
        return {"accepted": True, "scope": "local_synthetic_heartbeat", "transport_delivered": False}

    def grant_lease(self, *, duration_seconds=0.5, action_budget=4):
        if (not _positive(duration_seconds) or duration_seconds > self.limits.max_lease_seconds or
                type(action_budget) is not int or not 1 <= action_budget <= self.limits.max_actions):
            return {"granted": False, "reason": "invalid_lease_limits"}
        reason = self._preflight()
        if reason:
            return {"granted": False, "reason": reason}
        now = self._now()
        with self._lock:
            if (now is None or self.stop_latched or self._heartbeat is None or self._port_reason()
                    or now - self._heartbeat >= self.limits.heartbeat_timeout_seconds):
                return {"granted": False, "reason": "fresh_heartbeat_required"}
            if self._held or self._queue or self._in_flight:
                return {"granted": False, "reason": "control_busy"}
            self._lease_counter += 1
            self._lease = {"id": "lease-" + str(self._lease_counter), "generation": self.stop_generation,
                           "expires": now + duration_seconds, "remaining": action_budget}
            return {"granted": True, "scope": "synthetic_only", "lease_id": self._lease["id"],
                    "stop_generation": self.stop_generation, "binding_digest": self.binding.digest,
                    "expires_monotonic": self._lease["expires"], "execution_allowed": False}

    def _request_reason(self, request, now):
        if self.stop_latched:
            return "stop_latched"
        if request.stop_generation != self.stop_generation or request.binding_digest != self.binding.digest:
            return "stale_generation_or_binding"
        if not self._lease or request.lease_id != self._lease["id"]:
            return "lease_missing_or_replaced"
        if now >= self._lease["expires"] or self._lease["remaining"] <= 0:
            return "lease_expired_or_exhausted"
        if self._heartbeat is None or now - self._heartbeat >= self.limits.heartbeat_timeout_seconds:
            return "fresh_heartbeat_required"
        return self._port_reason()

    def enqueue(self, request):
        if not isinstance(request, ActionRequest):
            return {"queued": False, "reason": "invalid_action_request"}
        reason = self._preflight()
        if reason:
            return {"queued": False, "reason": reason}
        now = self._now()
        with self._lock:
            reason = "clock_invalid" if now is None else self._request_reason(request, now)
            if not reason and request.action_id in self._seen:
                reason = "action_id_replayed"
            if not reason and len(self._seen) >= self.limits.max_seen_actions:
                reason = "action_history_budget_exceeded"
            if not reason and (len(self._queue) >= self.limits.max_queue or len(self._queue) >= self._lease["remaining"]):
                reason = "queue_or_lease_budget_exceeded"
            if reason:
                return {"queued": False, "reason": reason}
            self._seen.add(request.action_id)
            self._queue.append(request)
        return {"queued": True, "scope": "local_synthetic_queue", "sent": False, "execution_confirmed": False}

    def _permit(self, request):
        # The adapter may call this while holding its own submission lock.
        # Never invoke cleanup, binding observation or any adapter I/O here.
        try:
            now = self.clock()
        except Exception:
            return False
        if type(now) not in (int, float) or not math.isfinite(now):
            return False
        with self._lock:
            # Budget was reserved before this callback; it may now be zero.
            return ((self._last_clock is None or now >= self._last_clock) and not self.stop_latched
                    and not self._port_reason() and self._lease is not None
                    and request.lease_id == self._lease["id"] and request.stop_generation == self.stop_generation
                    and request.binding_digest == self.binding.digest and now < self._lease["expires"]
                    and self._heartbeat is not None and now - self._heartbeat < self.limits.heartbeat_timeout_seconds
                    and all(now - item.since < self.limits.max_hold_seconds for item in self._held.values()))

    def drain_one(self):
        reason = self._preflight()
        if reason:
            return {"status": "blocked", "reason": reason, "sent": False, "execution_confirmed": False}
        now = self._now()
        with self._lock:
            if self._in_flight or not self._queue:
                return {"status": "not_dispatched", "reason": "busy_or_queue_empty", "sent": False, "execution_confirmed": False}
            request = self._queue.popleft()
            reason = "clock_invalid" if now is None else self._request_reason(request, now)
            key = request.action.ledger_key
            down = request.action.operation.endswith("_down")
            if not reason and ((down and key in self._held) or (not down and key not in self._held)):
                reason = "input_already_owned" if down else "input_not_owned"
            if reason:
                return {"status": "blocked", "reason": reason, "sent": False, "execution_confirmed": False}
            self._lease["remaining"] -= 1
            self._in_flight += 1
            if down:
                self._held[key] = _Held(now)
            else:
                self._held[key].in_flight = True
        submitted, failure, interrupt = False, None, None
        try:
            if self._permit(request):
                submitted = self.native.emit(request.action, lambda: self._permit(request)) is True
            if not submitted:
                failure = "adapter_rejected_or_permit_revoked"
        except BaseException as error:
            failure = "adapter_error:" + type(error).__name__
            if not isinstance(error, Exception):
                interrupt = error
        finally:
            with self._lock:
                self._in_flight -= 1
                if key in self._held:
                    self._held[key].in_flight = False
                    if not down and submitted:
                        del self._held[key]
                revoked = self.stop_latched or request.stop_generation != self.stop_generation
                exhausted = self._lease is not None and self._lease["remaining"] <= 0
            if failure or revoked or exhausted:
                self.stop_local(failure or ("late_adapter_completion" if revoked else "action_budget_exhausted"))
        if interrupt:
            raise interrupt
        return {"status": "simulated_submission_reported" if submitted and not revoked else "blocked_or_uncertain",
                "reason": failure or ("generation_revoked" if revoked else None), "adapter_submission_reported": submitted,
                "scope": "synthetic_only", "sent": False, "execution_confirmed": False}

    def _release_owned(self):
        with self._lock:
            keys = [key for key, held in self._held.items() if not held.in_flight and not held.releasing]
        for key in keys:
            with self._lock:
                held = self._held.get(key)
                if held is None or held.in_flight or held.releasing:
                    continue
                held.releasing = True
            released = False
            try:
                if (self.simulation and self.native.scope == "synthetic" and self.native.connected is True
                        and self.native.observe_binding() == self.binding):
                    released = self.native.release(key[0] + "_up", key[1], self.binding.digest) is True
            except Exception as error:
                self._record_error("release_error:" + type(error).__name__)
            finally:
                with self._lock:
                    if released:
                        self._held.pop(key, None)
                    elif key in self._held:
                        self._held[key].releasing = False

    def stop_local(self, reason="requested_stop"):
        with self._lock:
            if not self.stop_latched:
                self.stop_generation += 1
                self.stop_reason = reason
            self.stop_latched = True
            self._lease = None
            self._queue.clear()
        self._release_owned()  # Never perform adapter I/O while holding the state lock.
        return {"status": "local_permission_revoked", **self.snapshot(),
                "transport_delivered": False, "remote_release_confirmed": False}

    def close(self):
        self.stop_local("control_closed")
        with self._lock:
            if self._close_attempted:
                return self.snapshot()
            self._close_attempted = True
            self._closed = True
        for name, port in (("transport", self.transport), ("native", self.native)):
            try:
                port.close()
            except Exception as error:
                self._record_error(name + "_close_error:" + type(error).__name__)
        return self.snapshot()

    def __enter__(self):
        return self

    def __exit__(self, kind, value, traceback):
        self.close()
        return False
