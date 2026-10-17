"""Fail-closed ChildSession preflight. No RDP activation, game capture or input path."""
import ctypes
from ctypes import wintypes
from dataclasses import asdict, dataclass, fields
from datetime import datetime, timezone
import math
import sys


API_NAMES = ("WTSIsChildSessionsEnabled", "WTSGetChildSessionId", "WTSEnableChildSessions")
LIVE_CAPABILITIES = ("child_capture", "child_click", "child_drag", "child_keyboard",
                     "main_desktop_noninterference", "authenticated_stop_delivery", "remote_input_release",
                     "heartbeat_watchdog", "independent_stop_hotkey")


@dataclass(frozen=True)
class ChildSessionConfig:
    schema_version: str = "child-session-config/1"
    enabled: bool = False
    main_session_role: str = "read_only_preview_and_stop"
    preview_input_enabled: bool = False
    allow_main_desktop_input_fallback: bool = False
    require_same_child_session: bool = True
    require_authenticated_stop_ipc: bool = True
    evidence_ttl_seconds: int = 120
    stop_message_ttl_seconds: int = 3

    def __post_init__(self):
        booleans = ("enabled", "preview_input_enabled", "allow_main_desktop_input_fallback",
                    "require_same_child_session", "require_authenticated_stop_ipc")
        if any(type(getattr(self, name)) is not bool for name in booleans):
            raise ValueError("configuration_booleans_required")
        if self.schema_version != "child-session-config/1":
            raise ValueError("unsupported_configuration_schema")
        if (self.main_session_role != "read_only_preview_and_stop" or self.preview_input_enabled or
                self.allow_main_desktop_input_fallback or not self.require_same_child_session or
                not self.require_authenticated_stop_ipc):
            raise ValueError("unsafe_child_session_configuration")
        for name, upper in (("evidence_ttl_seconds", 3600), ("stop_message_ttl_seconds", 10)):
            if type(getattr(self, name)) is not int or not 1 <= getattr(self, name) <= upper:
                raise ValueError("invalid_configuration_timeout")

    @classmethod
    def from_dict(cls, value):
        if not isinstance(value, dict) or set(value) - {item.name for item in fields(cls)}:
            raise ValueError("unknown_configuration_fields")
        return cls(**value)


@dataclass(frozen=True)
class PlatformFacts:
    # These are reported facts, not proof that a game supports isolated execution.
    platform: str = "unknown"
    api_exports_available: bool | None = None
    child_sessions_enabled: bool | None = None
    main_session_id: int | None = None
    child_session_id: int | None = None
    worker_session_id: int | None = None
    game_session_id: int | None = None
    origin: str = "unknown"

    def __post_init__(self):
        if not isinstance(self.platform, str) or not self.platform:
            raise ValueError("invalid_platform_fact")
        if any(value is not None and type(value) is not bool for value in
               (self.api_exports_available, self.child_sessions_enabled)):
            raise ValueError("invalid_boolean_fact")
        for value in (self.main_session_id, self.child_session_id, self.worker_session_id, self.game_session_id):
            if value is not None and (type(value) is not int or not 0 <= value < 0xFFFFFFFF):
                raise ValueError("invalid_session_id_fact")
        if self.origin not in ("unknown", "synthetic_fixture", "synthetic_probe", "native_read_only_probe"):
            raise ValueError("invalid_fact_origin")


def probe_platform(*, allow_native_probe=False, _loader=None, _platform=None):
    """Explicit read-only API probe; never invokes WTSEnableChildSessions or ActiveX.

    This function is not called by imports or the offline CLI. Current live-test
    restrictions still apply; tests inject a fake loader rather than querying Windows.
    """
    if allow_native_probe is not True:
        return {"status": "not_probed", "reason": "native_probe_not_requested", "facts": asdict(PlatformFacts())}
    platform = sys.platform if _platform is None else _platform
    if platform != "win32":
        return {"status": "unsupported", "reason": "windows_required",
                "facts": asdict(PlatformFacts(platform=platform, api_exports_available=False))}
    loader = _loader or (lambda: ctypes.WinDLL("wtsapi32", use_last_error=True))
    origin = "synthetic_probe" if _loader is not None else "native_read_only_probe"
    try:
        api = loader()
        missing = [name for name in API_NAMES if not hasattr(api, name)]
        if missing:
            return {"status": "unsupported", "reason": "child_session_api_missing", "missing_exports": missing,
                    "facts": asdict(PlatformFacts(platform="win32", api_exports_available=False, origin=origin))}
        api.WTSIsChildSessionsEnabled.argtypes = [ctypes.POINTER(wintypes.BOOL)]
        api.WTSIsChildSessionsEnabled.restype = wintypes.BOOL
        api.WTSGetChildSessionId.argtypes = [ctypes.POINTER(wintypes.ULONG)]
        api.WTSGetChildSessionId.restype = wintypes.BOOL
        enabled, child = wintypes.BOOL(), wintypes.ULONG()
        enabled_ok = bool(api.WTSIsChildSessionsEnabled(ctypes.byref(enabled)))
        child_ok = bool(api.WTSGetChildSessionId(ctypes.byref(child)))
        child_id = child.value if child_ok and child.value != 0xFFFFFFFF else None
        return {"status": "reported", "reason": "read_only_metadata_not_operational_validation",
                "facts": asdict(PlatformFacts(platform="win32", api_exports_available=True,
                                               child_sessions_enabled=bool(enabled.value) if enabled_ok else None,
                                               child_session_id=child_id, origin=origin)),
                "query_results": {"enabled_query_succeeded": enabled_ok, "session_query_succeeded": child_ok}}
    except (OSError, AttributeError):
        return {"status": "unavailable", "reason": "child_session_api_probe_failed",
                "facts": asdict(PlatformFacts(platform="win32", origin=origin))}


def _reported_check(value, passed, failed):
    if value is None:
        return {"state": "unknown", "reason": "evidence_missing"}
    return {"state": "pass" if value else "fail", "reason": passed if value else failed}


def _live_check(observation, now, ttl):
    if not isinstance(observation, dict):
        return {"state": "unknown", "reason": "live_evidence_missing"}
    if observation.get("state") not in ("unknown", "pass", "fail"):
        return {"state": "unknown", "reason": "invalid_evidence_state"}
    if observation.get("scope") != "live_test":
        return {"state": "unknown", "reason": "synthetic_or_unverified_evidence", "reported_state": observation.get("state")}
    try:
        when = datetime.fromisoformat(observation["observed_at"].replace("Z", "+00:00"))
        if when.tzinfo is None:
            raise ValueError("timezone_required")
        age = (now - when).total_seconds()
        if not math.isfinite(age) or not 0 <= age <= ttl:
            return {"state": "unknown", "reason": "evidence_stale_or_future"}
    except (KeyError, TypeError, ValueError, AttributeError):
        return {"state": "unknown", "reason": "invalid_evidence_time"}
    return {"state": observation["state"], "reason": "caller_reported_live_test_not_transport_implementation"}


class ChildSessionBackend:
    backend_id = "child_session"

    def __init__(self, config=None):
        self.config = ChildSessionConfig() if config is None else config
        if not isinstance(self.config, ChildSessionConfig):
            raise ValueError("validated_child_session_config_required")
        self.stop_generation = 0
        self.stop_latched = False

    def assess(self, facts=None, observations=None, *, now=None):
        facts = PlatformFacts() if facts is None else facts
        observations = {} if observations is None else observations
        if not isinstance(facts, PlatformFacts) or not isinstance(observations, dict):
            raise ValueError("invalid_assessment_inputs")
        now = now or datetime.now(timezone.utc)
        if now.tzinfo is None:
            raise ValueError("timezone_required")
        checks = {
            "windows": _reported_check(None if facts.platform == "unknown" else facts.platform == "win32",
                                       "windows_reported", "windows_required"),
            "api_exports": _reported_check(facts.api_exports_available, "exports_reported", "required_api_missing"),
            "child_sessions_enabled": _reported_check(facts.child_sessions_enabled, "already_enabled_reported", "requires_separate_enable_authorization"),
        }
        ids = (facts.main_session_id, facts.child_session_id, facts.worker_session_id, facts.game_session_id)
        valid_ids = all(type(value) is int and 0 <= value < 0xFFFFFFFF for value in ids)
        isolated = (facts.child_session_id == facts.worker_session_id == facts.game_session_id and
                    facts.child_session_id > 0 and facts.child_session_id != facts.main_session_id) if valid_ids else None
        checks["same_child_session"] = _reported_check(isolated, "same_child_session_reported", "session_mismatch_or_main_session_target")
        checks.update({name: _live_check(observations.get(name), now, self.config.evidence_ttl_seconds)
                       for name in LIVE_CAPABILITIES})
        reasons = ["native_child_session_transport_not_implemented", "startup_authorization_required"]
        if not self.config.enabled:
            reasons.insert(0, "backend_disabled")
        if self.stop_latched:
            reasons.insert(0, "stop_latched")
        reasons.extend(name + ":" + check["reason"] for name, check in checks.items() if check["state"] != "pass")
        return {"schema_version": "child-session-assessment/1", "backend": self.backend_id,
                "status": "disabled" if not self.config.enabled else "blocked", "operational": False,
                "input_permitted": False, "remote_connected": False, "native_transport_implemented": False,
                "evidence_origin": facts.origin, "checks": checks, "reasons": reasons,
                "stop_generation": self.stop_generation, "stop_latched": self.stop_latched}

    def open(self):
        return {"backend": self.backend_id, "status": "blocked", "connected": False,
                "reason": ("stop_latched" if self.stop_latched else "backend_disabled" if not self.config.enabled
                           else "startup_authorization_required"),
                "implementation": "native_child_session_transport_not_implemented"}

    def capture_one(self):
        return {"backend": self.backend_id, "status": "capture_unavailable", "image": None, "frame_id": None,
                "reason": ("stop_latched" if self.stop_latched else "backend_disabled" if not self.config.enabled
                           else "child_session_capture_not_implemented")}

    def send_action(self, intent):
        return {"backend": self.backend_id, "status": "action_blocked", "sent": False,
                "reason": ("stop_latched" if self.stop_latched else "backend_disabled" if not self.config.enabled
                           else "child_session_input_not_implemented"),
                "main_desktop_fallback": False}

    def stop_local(self):
        self.stop_generation += 1
        self.stop_latched = True
        return {"status": "local_permission_revoked", "stop_generation": self.stop_generation,
                "transport_delivered": False, "remote_release_confirmed": False}
