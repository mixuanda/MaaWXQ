"""Offline-only ChildSession policy/protocol tests; native probes use fake APIs."""
import ctypes
from ctypes import wintypes
from dataclasses import replace
from datetime import datetime, timedelta, timezone
import json
import unittest
from unittest.mock import Mock

from backends.child_session.backend import (API_NAMES, LIVE_CAPABILITIES, ChildSessionBackend,
                                             ChildSessionConfig, PlatformFacts, probe_platform)
from backends.child_session.stop_protocol import StopProtocol

NOW = datetime(2026, 1, 1, 12, tzinfo=timezone.utc)


def synthetic_facts():
    return PlatformFacts(platform="win32", api_exports_available=True, child_sessions_enabled=True,
                         main_session_id=10, child_session_id=20, worker_session_id=20,
                         game_session_id=20, origin="synthetic_fixture")


class ChildSessionTests(unittest.TestCase):
    def test_default_is_disabled_without_even_a_native_probe(self):
        loader = Mock(side_effect=AssertionError("must not query Windows"))
        self.assertEqual(probe_platform(_loader=loader)["status"], "not_probed")
        loader.assert_not_called()
        backend = ChildSessionBackend()
        report = backend.assess()
        self.assertEqual(report["status"], "disabled")
        self.assertFalse(report["operational"])
        self.assertFalse(backend.open()["connected"])
        self.assertIsNone(backend.capture_one()["image"])
        self.assertFalse(backend.send_action({"kind": "synthetic_click"})["sent"])

    def test_unsafe_configuration_and_credential_fields_are_rejected(self):
        for patch in ({"preview_input_enabled": True}, {"allow_main_desktop_input_fallback": True},
                      {"require_same_child_session": False}, {"require_authenticated_stop_ipc": False},
                      {"enabled": "true"}, {"stop_message_ttl_seconds": 0}, {"username": "synthetic"}):
            with self.subTest(patch=patch), self.assertRaises(ValueError):
                ChildSessionConfig.from_dict(patch)
        with self.assertRaises(ValueError):
            PlatformFacts(api_exports_available="yes")
        with self.assertRaises(ValueError):
            PlatformFacts(child_session_id=True)
        with self.assertRaises(ValueError):
            ChildSessionBackend({})
        with self.assertRaises(ValueError):
            ChildSessionBackend().assess(facts={})
        with self.assertRaises(ValueError):
            ChildSessionBackend().assess(observations=[])

    def test_fake_api_probe_reads_metadata_but_never_enables_sessions(self):
        api = Mock(spec=list(API_NAMES))
        def enabled(output):
            ctypes.cast(output, ctypes.POINTER(wintypes.BOOL))[0] = 1
            return 1
        def child(output):
            ctypes.cast(output, ctypes.POINTER(wintypes.ULONG))[0] = 0xFFFFFFFF
            return 1
        api.WTSIsChildSessionsEnabled.side_effect = enabled
        api.WTSGetChildSessionId.side_effect = child
        report = probe_platform(allow_native_probe=True, _loader=lambda: api, _platform="win32")
        self.assertEqual(report["status"], "reported")
        self.assertEqual(report["facts"]["origin"], "synthetic_probe")
        self.assertTrue(report["facts"]["child_sessions_enabled"])
        self.assertIsNone(report["facts"]["child_session_id"])
        api.WTSEnableChildSessions.assert_not_called()
        missing = probe_platform(allow_native_probe=True, _loader=lambda: Mock(spec=[]), _platform="win32")
        self.assertEqual(missing["reason"], "child_session_api_missing")

    def test_positive_facts_and_even_reported_live_checks_cannot_activate_transport(self):
        backend = ChildSessionBackend(ChildSessionConfig(enabled=True))
        checks = {name: {"state": "pass", "scope": "live_test", "observed_at": NOW.isoformat()}
                  for name in LIVE_CAPABILITIES}
        report = backend.assess(synthetic_facts(), checks, now=NOW)
        self.assertTrue(all(item["state"] == "pass" for item in report["checks"].values()))
        self.assertFalse(report["operational"])
        self.assertFalse(report["input_permitted"])
        self.assertIn("native_child_session_transport_not_implemented", report["reasons"])
        self.assertFalse(backend.open()["connected"])
        self.assertFalse(backend.send_action({})["sent"])

    def test_same_session_and_main_desktop_rejections(self):
        backend = ChildSessionBackend(ChildSessionConfig(enabled=True))
        for patch in ({"worker_session_id": 10}, {"game_session_id": 30},
                      {"main_session_id": 20}, {"child_session_id": 0, "worker_session_id": 0, "game_session_id": 0}):
            report = backend.assess(replace(synthetic_facts(), **patch), now=NOW)
            self.assertEqual(report["checks"]["same_child_session"]["state"], "fail")
            self.assertFalse(report["input_permitted"])

    def test_synthetic_stale_future_and_failed_capabilities_never_pass_live_gate(self):
        backend = ChildSessionBackend(ChildSessionConfig(enabled=True))
        for observation in ({"state": "pass", "scope": "synthetic", "observed_at": NOW.isoformat()},
                            {"state": "pass", "scope": "live_test", "observed_at": (NOW-timedelta(seconds=121)).isoformat()},
                            {"state": "pass", "scope": "live_test", "observed_at": (NOW+timedelta(seconds=1)).isoformat()},
                            {"state": "fail", "scope": "live_test", "observed_at": NOW.isoformat()}):
            report = backend.assess(synthetic_facts(), {"main_desktop_noninterference": observation}, now=NOW)
            self.assertNotEqual(report["checks"]["main_desktop_noninterference"]["state"], "pass")
            self.assertFalse(report["operational"])

    def test_stop_authentication_replay_and_latched_local_revocation(self):
        # Publicly recognizable synthetic test key, never a production credential.
        protocol = StopProtocol(b"synthetic-test-key-material-only-1234", "synthetic-session")
        backend = ChildSessionBackend(ChildSessionConfig(enabled=True))
        message = protocol.encode_stop(1, issued_at=NOW.isoformat())
        receipt = protocol.receive(message, backend, now=NOW)
        self.assertTrue(receipt["protocol_accepted"])
        self.assertEqual(receipt["stop_generation"], 1)
        self.assertFalse(receipt["transport_delivered"])
        self.assertFalse(receipt["remote_release_confirmed"])
        self.assertEqual(backend.open()["reason"], "stop_latched")
        self.assertEqual(backend.send_action({})["reason"], "stop_latched")
        self.assertEqual(protocol.receive(message, backend, now=NOW)["reason"], "stop_replay_or_invalid_sequence")
        self.assertEqual(backend.stop_generation, 1)

    def test_bad_expired_foreign_or_duplicate_stop_messages_do_not_acknowledge(self):
        key = b"synthetic-test-key-material-only-1234"
        protocol = StopProtocol(key, "synthetic-session")
        backend = ChildSessionBackend()
        message = protocol.encode_stop(1, issued_at=NOW.isoformat())
        tampered = json.loads(message)
        tampered["command"] = "start"
        foreign = StopProtocol(key, "other-synthetic-session").encode_stop(1, issued_at=NOW.isoformat())
        expired = protocol.encode_stop(2, issued_at=(NOW-timedelta(seconds=4)).isoformat())
        duplicate = message[:-1] + b',"command":"stop"}'
        for payload in (json.dumps(tampered).encode(), foreign, expired, duplicate, b"x"*4097, b"{}"):
            with self.subTest(payload_length=len(payload)):
                receipt = protocol.receive(payload, backend, now=NOW)
                self.assertFalse(receipt["protocol_accepted"])
                self.assertFalse(receipt["remote_release_confirmed"])
        self.assertFalse(backend.stop_latched)
        self.assertEqual(protocol.last_sequence, 0)


if __name__ == "__main__":
    unittest.main()
