"""Control contracts tested with synthetic ports/clocks; no native calls or endpoints."""
from dataclasses import replace
from datetime import datetime, timedelta, timezone
import json
import threading
import unittest

from backends.child_session.control import ActionRequest, ControlCore, ControlLimits, InputAction, SessionBinding
from backends.child_session.control_protocol import ControlProtocol
from backends.child_session.stop_protocol import StopProtocol

NOW = datetime(2026, 1, 1, 12, tzinfo=timezone.utc)
KEY = b"synthetic-control-test-key-only-123456"


def binding():
    return SessionBinding("synthetic-connection", "synthetic-worker", 10, 20, 20, 20,
                          "synthetic-window-version", "synthetic-geometry-version")


class FakeClock:
    value = 0.0
    def __call__(self):
        return self.value


class FakeTransport:
    scope = "synthetic"
    def __init__(self):
        self.connected, self.close_calls, self.close_error = True, 0, False
    def close(self):
        self.close_calls += 1
        self.connected = False
        if self.close_error:
            raise OSError("synthetic-close-failure")


class FakeInput(FakeTransport):
    def __init__(self, context):
        super().__init__()
        self.binding, self.events = context, []
        self.emit_error, self.release_error = None, False
        self.entered, self.proceed = threading.Event(), threading.Event()
        self.block, self.ignore_permit = False, False
    def observe_binding(self):
        return self.binding
    def emit(self, action, permit):
        if self.block:
            self.entered.set()
            if not self.proceed.wait(2):
                raise TimeoutError("synthetic-test-deadline")
        if not self.ignore_permit and not permit():
            return False
        self.events.append((action.operation, action.code))
        if self.emit_error:
            raise self.emit_error
        return True
    def release(self, operation, code, binding_digest):
        if self.release_error:
            raise OSError("synthetic-release-failure")
        self.events.append((operation, code))
        return True


class ChildControlTests(unittest.TestCase):
    def setUp(self):
        self.binding = binding()
        self.clock, self.transport = FakeClock(), FakeTransport()
        self.native = FakeInput(self.binding)
        self.core = ControlCore(self.binding, simulation=True, clock=self.clock,
                                transport=self.transport, native=self.native)
        self.assertTrue(self.core.heartbeat(0, self.binding.digest)["accepted"])
        self.lease = self.core.grant_lease(duration_seconds=1, action_budget=8)
        self.assertTrue(self.lease["granted"])

    def request(self, identifier="synthetic-a", operation="key_down", code=65, **changes):
        request = ActionRequest(identifier, self.lease["lease_id"], 0, self.binding.digest, InputAction(operation, code))
        return replace(request, **changes)

    def down(self):
        self.assertTrue(self.core.enqueue(self.request())["queued"])
        return self.core.drain_one()

    def test_unconnected_or_non_simulation_core_never_calls_input(self):
        core = ControlCore(self.binding, native=self.native, transport=self.transport)
        self.assertFalse(core.heartbeat(0, self.binding.digest)["accepted"])
        self.assertFalse(core.grant_lease()["granted"])
        self.assertFalse(core.enqueue(self.request())["queued"])
        self.assertFalse(core.drain_one()["sent"])
        self.assertEqual(self.native.events, [])
        self.assertFalse(core.snapshot()["operational"])

    def test_owned_down_up_and_non_execution_receipts(self):
        receipt = self.down()
        self.assertTrue(receipt["adapter_submission_reported"])
        self.assertFalse(receipt["sent"])
        self.assertFalse(receipt["execution_confirmed"])
        self.assertTrue(self.core.enqueue(self.request("up", "key_up"))["queued"])
        self.core.drain_one()
        self.assertEqual(self.native.events, [("key_down", 65), ("key_up", 65)])
        self.assertEqual(self.core.snapshot()["held_in_local_model"], 0)
        self.assertFalse(self.core.enqueue(self.request("up", "key_up"))["queued"])

    def test_stop_clears_queue_invalidates_late_messages_and_cannot_resume(self):
        self.assertTrue(self.core.enqueue(self.request())["queued"])
        receipt = self.core.stop_local()
        self.assertEqual(receipt["queued"], 0)
        self.assertEqual(receipt["stop_generation"], 1)
        self.assertFalse(self.core.enqueue(self.request("late"))["queued"])
        self.assertFalse(self.core.heartbeat(1, self.binding.digest)["accepted"])
        self.assertFalse(self.core.grant_lease()["granted"])
        self.assertEqual(self.native.events, [])

    def test_heartbeat_lease_and_hold_deadlines_fail_closed(self):
        self.core.enqueue(self.request())
        self.clock.value = 1.0
        self.core.tick()
        self.assertTrue(self.core.stop_latched)
        self.assertEqual(self.native.events, [])
        fresh = ControlCore(self.binding, simulation=True, clock=self.clock,
                            transport=self.transport, native=self.native)
        fresh.heartbeat(0, self.binding.digest)
        lease = fresh.grant_lease(duration_seconds=0.2)
        fresh.enqueue(replace(self.request(), lease_id=lease["lease_id"]))
        self.clock.value = 1.21
        self.assertFalse(fresh.drain_one()["sent"])
        self.assertEqual(fresh.stop_reason, "lease_expired")

    def test_hold_timeout_releases_only_owned_inputs(self):
        self.down()
        self.clock.value = 0.5
        report = self.core.tick()
        self.assertEqual(report["stop_reason"], "held_input_deadline_exceeded")
        self.assertEqual(self.native.events, [("key_down", 65), ("key_up", 65)])
        self.assertFalse(report["remote_release_confirmed"])

    def test_session_change_does_not_release_into_new_session(self):
        self.down()
        self.native.binding = replace(self.binding, child_session_id=30, worker_session_id=30, game_session_id=30)
        report = self.core.tick()
        self.assertEqual(report["stop_reason"], "session_or_identity_changed")
        self.assertEqual(report["held_in_local_model"], 1)
        self.assertEqual(self.native.events, [("key_down", 65)])
        self.assertFalse(self.core.enqueue(self.request("wrong-session"))["queued"])

    def test_adapter_error_transport_loss_and_close_cleanup(self):
        self.native.emit_error = OSError("synthetic-uncertain-down")
        self.down()
        self.assertTrue(self.core.stop_latched)
        self.assertEqual(self.native.events, [("key_down", 65), ("key_up", 65)])
        self.transport.close_error = True
        self.core.close()
        self.core.close()
        self.assertEqual(self.transport.close_calls, 1)
        self.assertEqual(self.native.close_calls, 1)
        self.assertIn("transport_close_error:OSError", self.core.snapshot()["cleanup_errors"])
        native = FakeInput(self.binding)
        transport = FakeTransport()
        core = ControlCore(self.binding, simulation=True, clock=self.clock, transport=transport, native=native)
        core.heartbeat(0, self.binding.digest)
        lease = core.grant_lease()
        core.enqueue(replace(self.request(), lease_id=lease["lease_id"]))
        core.drain_one()
        transport.connected = False
        self.assertEqual(core.tick()["stop_reason"], "transport_not_connected")
        self.assertEqual(native.events, [("key_down", 65), ("key_up", 65)])

    def test_interrupt_cleanup_and_context_manager_close_both_ports(self):
        self.native.emit_error = KeyboardInterrupt()
        with self.assertRaises(KeyboardInterrupt):
            with self.core:
                self.down()
        self.assertTrue(self.core.stop_latched)
        self.assertEqual(self.core.snapshot()["held_in_local_model"], 0)
        self.assertEqual(self.transport.close_calls, 1)
        self.assertEqual(self.native.close_calls, 1)

    def test_release_failure_is_not_hidden_or_acknowledged(self):
        self.down()
        self.native.release_error = True
        receipt = self.core.stop_local()
        self.assertEqual(receipt["held_in_local_model"], 1)
        self.assertFalse(receipt["remote_release_confirmed"])
        self.assertIn("release_error:OSError", receipt["cleanup_errors"])

    def test_stop_during_in_flight_call_fences_or_cleans_late_completion(self):
        for ignore in (False, True):
            with self.subTest(ignore_permit=ignore):
                native = FakeInput(self.binding)
                native.block, native.ignore_permit = True, ignore
                core = ControlCore(self.binding, simulation=True, clock=self.clock,
                                   transport=FakeTransport(), native=native)
                core.heartbeat(0, self.binding.digest)
                lease = core.grant_lease()
                core.enqueue(replace(self.request(), lease_id=lease["lease_id"]))
                outcomes = []
                thread = threading.Thread(target=lambda: outcomes.append(core.drain_one()))
                thread.start()
                try:
                    self.assertTrue(native.entered.wait(1))
                    receipt = core.stop_local()
                    self.assertTrue(receipt["stop_latched"])
                    self.assertEqual(receipt["in_flight"], 1)
                finally:
                    native.proceed.set()
                    thread.join(2)
                self.assertFalse(thread.is_alive())
                self.assertFalse(outcomes[0]["execution_confirmed"])
                self.assertEqual(outcomes[0]["status"], "blocked_or_uncertain")
                self.assertEqual(core.snapshot()["held_in_local_model"], 0)
                if ignore:
                    self.assertEqual(native.events, [("key_down", 65), ("key_up", 65)])
                else:
                    self.assertNotIn(("key_down", 65), native.events)

    def test_authenticated_control_sequence_and_independent_priority_stop(self):
        protocol = ControlProtocol(KEY, self.binding)
        body = {"action_id": "wire-action", "lease_id": self.lease["lease_id"], "operation": "key_down", "code": 65}
        pending = protocol.encode("action", 101, 0, body, issued_at=NOW.isoformat())
        heartbeat = protocol.encode("heartbeat", 100, 0, {}, issued_at=NOW.isoformat())
        self.assertTrue(protocol.receive(heartbeat, self.core, now=NOW)["sequence_accepted"])
        stop = StopProtocol(KEY, self.binding.connection_id)
        receipt = stop.receive(stop.encode_stop(1, issued_at=NOW.isoformat()), self.core, now=NOW)
        self.assertTrue(receipt["protocol_accepted"])
        late = protocol.receive(pending, self.core, now=NOW)
        self.assertTrue(late["authenticated"])
        self.assertFalse(late["control_result"]["queued"])
        self.assertFalse(late["execution_confirmed"])
        self.assertFalse(protocol.receive(pending, self.core, now=NOW)["sequence_accepted"])
        self.assertEqual(self.native.events, [])

    def test_priority_stop_sequence_cannot_regress_during_slow_cleanup(self):
        entered, proceed = threading.Event(), threading.Event()
        class SlowLocalStop:
            calls = 0
            def stop_local(self):
                self.calls += 1
                if self.calls == 1:
                    entered.set()
                    if not proceed.wait(2):
                        raise TimeoutError("synthetic-stop-deadline")
                return {"stop_generation": 1}
        protocol = StopProtocol(KEY, self.binding.connection_id)
        backend = SlowLocalStop()
        first = protocol.encode_stop(1, issued_at=NOW.isoformat())
        second = protocol.encode_stop(2, issued_at=NOW.isoformat())
        thread = threading.Thread(target=lambda: protocol.receive(first, backend, now=NOW))
        thread.start()
        try:
            self.assertTrue(entered.wait(1))
            self.assertTrue(protocol.receive(second, backend, now=NOW)["protocol_accepted"])
        finally:
            proceed.set()
            thread.join(2)
        self.assertFalse(thread.is_alive())
        self.assertEqual(protocol.last_sequence, 2)
        self.assertFalse(protocol.receive(second, backend, now=NOW)["protocol_accepted"])

    def test_control_application_order_is_serial_and_stop_lane_is_independent(self):
        entered, proceed, second_called = threading.Event(), threading.Event(), threading.Event()
        calls, results = [], []
        context = self.binding
        class SlowLocalCore:
            binding = context
            def heartbeat(self, generation, digest):
                calls.append(generation)
                if generation == 1:
                    entered.set()
                    if not proceed.wait(2):
                        raise TimeoutError("synthetic-control-deadline")
                else:
                    second_called.set()
                return {"accepted": False}
        protocol = ControlProtocol(KEY, self.binding)
        core = SlowLocalCore()
        first = protocol.encode("heartbeat", 1, 1, {}, issued_at=NOW.isoformat())
        second = protocol.encode("heartbeat", 2, 2, {}, issued_at=NOW.isoformat())
        threads = [threading.Thread(target=lambda p=p: results.append(protocol.receive(p, core, now=NOW)))
                   for p in (first, second)]
        threads[0].start()
        try:
            self.assertTrue(entered.wait(1))
            threads[1].start()
            self.assertFalse(second_called.wait(0.05))
            stop = StopProtocol(KEY, self.binding.connection_id)
            receipt = stop.receive(stop.encode_stop(1, issued_at=NOW.isoformat()), self.core, now=NOW)
            self.assertTrue(receipt["protocol_accepted"])
            self.assertTrue(self.core.stop_latched)
        finally:
            proceed.set()
            for thread in threads:
                if thread.ident is not None:
                    thread.join(2)
        self.assertTrue(all(not thread.is_alive() for thread in threads))
        self.assertEqual(calls, [1, 2])
        self.assertEqual(len(results), 2)
        self.assertTrue(all(result["sequence_accepted"] for result in results))

    def test_bad_control_messages_and_old_lease_cannot_enqueue(self):
        protocol = ControlProtocol(KEY, self.binding)
        good = protocol.encode("heartbeat", 1, 0, {}, issued_at=NOW.isoformat())
        tampered = json.loads(good)
        tampered["stop_generation"] = 99
        stale = protocol.encode("heartbeat", 2, 0, {}, issued_at=(NOW-timedelta(seconds=4)).isoformat())
        for payload in (json.dumps(tampered).encode(), stale, b"{}", b"x"*4097):
            self.assertFalse(protocol.receive(payload, self.core, now=NOW)["sequence_accepted"])
        newer = self.core.grant_lease()
        self.assertNotEqual(newer["lease_id"], self.lease["lease_id"])
        self.assertFalse(self.core.enqueue(self.request())["queued"])
        with self.assertRaises(ValueError):
            replace(self.binding, game_session_id=10)
        with self.assertRaises(ValueError):
            InputAction("launch_process", 1)


if __name__ == "__main__":
    unittest.main()
