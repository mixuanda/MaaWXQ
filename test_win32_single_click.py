"""Offline guard checks. Native libraries, hooks and input are never opened."""
import copy
from dataclasses import replace
import os
import threading
import unittest
from unittest.mock import Mock, patch

import backends.win32_single_click as native

from backends.win32_single_click import Binding, ClickEvidence, NativeUnavailable, SingleClickBroker, WindowsClickPort


def observed():
    return {"hwnd": 1, "pid": os.getpid(), "process_started_at": "synthetic-start",
            "class_name": "SyntheticWindow", "geometry_version": "synthetic-geometry",
            "visible": True, "minimized": False,
            "client": {"screen_x": 10, "screen_y": 20, "width": 100, "height": 80},
            "desktop": {"foreground_hwnd": 1}}


class FakePort:
    def __init__(self, observer):
        self.observer = observer
        self.calls = []
        self.changed = False
        self.released = 0
        self.closed = False
        self.cleanup_errors = []
        self.healthy = True
    def open(self, stop):
        self.stop = stop
    def user_activity_changed(self):
        return self.changed
    def guard_healthy(self):
        return self.healthy
    def click(self, hwnd, x, y, permit):
        if not permit():
            raise NativeUnavailable("permission_revoked")
        self.calls.append((hwnd, x, y))
    def release_owned(self):
        self.released += 1
        return True
    def close(self):
        self.closed = True


class SingleClickTests(unittest.TestCase):
    def setUp(self):
        self.value = observed()
        self.observer = Mock(side_effect=lambda *args: copy.deepcopy(self.value))
        self.evidence = ClickEvidence(Binding.from_observation(self.value), 10.0, 50, 40, "self_owned_test")
        self.now = 10.0
        self.factory = Mock(side_effect=lambda observer: FakePort(observer))
    def broker(self, **options):
        result = SingleClickBroker(self.evidence, observer=self.observer, port_factory=self.factory,
                                   clock=lambda: self.now, **options)
        self.addCleanup(result.close)
        return result
    def test_default_off_does_not_open_any_native_port(self):
        with self.assertRaisesRegex(NativeUnavailable, "automatic_input_disabled"):
            self.broker().arm()
        self.factory.assert_not_called()
    def test_unknown_or_incomplete_room_is_rejected_before_port_creation(self):
        self.evidence = replace(self.evidence, context="custom_room", operation="reversible_non_spending_panel")
        with self.assertRaisesRegex(NativeUnavailable, "verified_custom_room"):
            self.broker(enabled=True).arm()
        self.factory.assert_not_called()
    def test_missing_process_start_and_lost_foreground_cannot_bind(self):
        for changes in ({"process_started_at": None}, {"desktop": {"foreground_hwnd": 2}}):
            with self.subTest(changes=changes):
                value = observed()
                value.update(changes)
                with self.assertRaises(ValueError):
                    Binding.from_observation(value)
    def test_positive_room_assertion_cannot_bypass_failed_native_validation(self):
        self.evidence = replace(self.evidence, context="custom_room", no_other_humans_verified=True,
                                operation="reversible_non_spending_panel")
        with self.assertRaisesRegex(NativeUnavailable, "live_game_validation_gate_not_passed"):
            self.broker(enabled=True).arm()
        self.factory.assert_not_called()
    def test_stale_evidence_never_opens_port(self):
        self.now = 20
        with self.assertRaisesRegex(NativeUnavailable, "stale_or_future"):
            self.broker(enabled=True).arm()
        self.factory.assert_not_called()
    def test_exactly_one_submission_never_claims_a_game_postcondition(self):
        broker = self.broker(enabled=True)
        broker.arm()
        result = broker.click_once()
        self.assertEqual(broker.port.calls, [(1, 60, 60)])
        self.assertTrue(result["sent"])
        self.assertFalse(result["game_postcondition_verified"])
        with self.assertRaisesRegex(NativeUnavailable, "one_action_budget"):
            broker.click_once()
        self.assertEqual(len(broker.port.calls), 1)
    def test_user_takeover_latches_stop_without_submission(self):
        broker = self.broker(enabled=True)
        broker.arm()
        broker.port.stop("user_or_foreign_mouse_input")
        with self.assertRaises(NativeUnavailable):
            broker.click_once()
        self.assertEqual(broker.port.calls, [])
        self.assertEqual(broker.stop_reason, "user_or_foreign_mouse_input")
    def test_independent_input_marker_prevents_submission(self):
        broker = self.broker(enabled=True)
        broker.arm()
        broker.port.changed = True
        with self.assertRaises(NativeUnavailable):
            broker.click_once()
        self.assertEqual(broker.port.calls, [])
    def test_dead_guard_blocks_submission(self):
        broker = self.broker(enabled=True)
        broker.arm()
        broker.port.healthy = False
        with self.assertRaisesRegex(NativeUnavailable, "native_guard_not_healthy"):
            broker.click_once()
        self.assertEqual(broker.port.calls, [])
    def test_geometry_and_focus_changes_block_before_submission(self):
        for field in ("geometry", "focus"):
            with self.subTest(field=field):
                self.value = observed()
                broker = self.broker(enabled=True)
                broker.arm()
                if field == "geometry":
                    self.value["geometry_version"] = "changed"
                else:
                    self.value["desktop"]["foreground_hwnd"] = 2
                with self.assertRaises((NativeUnavailable, ValueError)):
                    broker.click_once()
                self.assertEqual(broker.port.calls, [])
                broker.close()
    def test_deadline_and_final_permit_are_rechecked(self):
        broker = self.broker(enabled=True, max_seconds=0.1)
        broker.arm()
        self.now = 10.2
        with self.assertRaises(NativeUnavailable):
            broker.click_once()
        self.assertEqual(broker.port.calls, [])
    def test_stop_during_port_preflight_is_not_revived(self):
        broker = self.broker(enabled=True)
        broker.arm()
        def revoked(hwnd, x, y, permit):
            broker.stop("revoked_before_native_send")
            self.assertFalse(permit())
            raise NativeUnavailable("permission_revoked")
        broker.port.click = revoked
        with self.assertRaises(NativeUnavailable):
            broker.click_once()
        self.assertFalse(broker.sent)
    def test_cleanup_result_remains_visible(self):
        broker = self.broker(enabled=True)
        broker.arm()
        broker.port.release_owned = lambda: False
        broker.close()
        self.assertFalse(broker.release_confirmed)

    def test_expiry_during_observer_is_rechecked(self):
        broker = self.broker(enabled=True, max_seconds=0.1)
        broker.arm()
        def slow_observation(*args):
            self.now = 10.2
            return copy.deepcopy(self.value)
        broker.observer = slow_observation
        with self.assertRaisesRegex(NativeUnavailable, "deadline_expired"):
            broker.click_once()
        self.assertEqual(broker.port.calls, [])

    def test_changed_client_origin_cannot_hide_behind_same_geometry_version(self):
        broker = self.broker(enabled=True)
        broker.arm()
        self.value["client"]["screen_x"] += 1
        with self.assertRaisesRegex(NativeUnavailable, "identity_or_geometry"):
            broker.click_once()
        self.assertEqual(broker.port.calls, [])

    def test_wrong_thread_revokes_without_closing_owner_resources(self):
        broker = self.broker(enabled=True)
        broker.arm()
        errors = []
        def foreign_close():
            try:
                broker.close()
            except NativeUnavailable as error:
                errors.append(str(error))
        worker = threading.Thread(target=foreign_close)
        worker.start()
        worker.join(1)
        self.assertFalse(worker.is_alive())
        self.assertEqual(errors, ["broker_owner_thread_required"])
        self.assertTrue(broker.stopped.is_set())
        self.assertFalse(broker.port.closed)
        broker.close()  # The creating thread can still finish cleanup.
        self.assertTrue(broker.port.closed)
        self.assertEqual(broker.port.calls, [])

    def test_release_exception_cannot_skip_stop_or_port_close(self):
        broker = self.broker(enabled=True)
        broker.arm()
        broker.port.release_owned = Mock(side_effect=RuntimeError("synthetic release failure"))
        result = broker.click_once()
        self.assertTrue(broker.stopped.is_set())
        self.assertFalse(result["owned_release_confirmed"])
        self.assertIn("owned_release_exception", result["cleanup_errors"])
        broker.close()
        self.assertTrue(broker.port.closed)

    def test_failed_arm_cannot_retry_same_session(self):
        self.now = 20
        broker = self.broker(enabled=True)
        with self.assertRaises(NativeUnavailable):
            broker.arm()
        self.now = 10
        with self.assertRaisesRegex(NativeUnavailable, "cannot_rearm"):
            broker.arm()
        self.factory.assert_not_called()

    def test_supervisor_start_failure_revokes_and_closes_port(self):
        broker = self.broker(enabled=True)
        with patch.object(native.threading.Thread, "start", side_effect=RuntimeError("synthetic thread failure")):
            with self.assertRaises(RuntimeError):
                broker.arm()
        self.assertTrue(broker.stopped.is_set())
        self.assertTrue(broker.closed.is_set())
        self.assertTrue(broker.port.closed)
        self.assertEqual(broker.port.calls, [])


class NativePortFakeApiTests(unittest.TestCase):
    """Exercise port bookkeeping with fake DLLs, never load or call User32."""
    def setUp(self):
        for name, value in (("_PROCESS_INPUT_LEASE", threading.Lock()), ("_INCOMPLETE_NATIVE_CLEANUP", [])):
            guard = patch.object(native, name, value)
            guard.start()
            self.addCleanup(guard.stop)

    def port(self):
        user, kernel = Mock(), Mock()
        user.GetSystemMetrics.side_effect = lambda index: {76: 0, 77: 0, 78: 1000, 79: 800}[index]
        user.GetForegroundWindow.return_value = 1
        def current_process(hwnd, output):
            native.c.cast(output, native.c.POINTER(native.w.DWORD)).contents.value = os.getpid()
            return 7
        user.GetWindowThreadProcessId.side_effect = current_process
        user.WindowFromPoint.return_value = 1
        user.GetAncestor.return_value = 1
        user.GetAsyncKeyState.return_value = 0
        user.SendInput.return_value = 3
        kernel.ReleaseMutex.return_value = True
        kernel.CloseHandle.return_value = True
        # CFUNCTYPE only supplies inert callback objects for the fake API. This
        # deliberately does not certify native calling conventions or behavior.
        with patch.object(native.c, "WinDLL", side_effect=[user, kernel], create=True), \
                patch.object(native.c, "WINFUNCTYPE", native.c.CFUNCTYPE, create=True), \
                patch.object(native.sys, "platform", "win32"):
            port = WindowsClickPort(Mock())
        port.owner_thread = threading.get_ident()
        port.thread = Mock()
        port.thread.is_alive.return_value = True
        port.ready.set()
        return port

    def test_three_event_batch_has_only_tagged_mouse_move_down_up(self):
        port = self.port()
        self.assertEqual(port.click(1, 60, 60, lambda: True), 3)
        count, events, size = port.user.SendInput.call_args.args
        self.assertEqual(count, 3)
        self.assertEqual(size, native.c.sizeof(port.Input))
        self.assertEqual([event.type for event in events], [0, 0, 0])
        self.assertEqual([event.mi.dwFlags for event in events], [0xC001, 2, 4])
        self.assertEqual([event.mi.dwExtraInfo for event in events], [port.token] * 3)
        self.assertFalse(port.held)

    def test_partial_batch_releases_only_possibly_owned_left_button(self):
        for submitted in (0, 1, 2):
            with self.subTest(submitted=submitted):
                port = self.port()
                port.user.SendInput.side_effect = [submitted, 1]
                with self.assertRaisesRegex(NativeUnavailable, "send_input_incomplete"):
                    port.click(1, 60, 60, lambda: True)
                calls = port.user.SendInput.call_args_list
                self.assertEqual([call.args[0] for call in calls], [3, 1] if submitted == 2 else [3])
                if submitted == 2:
                    event = native.c.cast(calls[1].args[1], native.c.POINTER(port.Input)).contents
                    self.assertEqual(event.mi.dwFlags, 4)
                self.assertFalse(port.held)

    def test_uncertain_submission_keeps_ledger_until_owned_release(self):
        port = self.port()
        port.user.SendInput.side_effect = [RuntimeError("uncertain synthetic send"), 1]
        with self.assertRaises(RuntimeError):
            port.click(1, 60, 60, lambda: True)
        self.assertTrue(port.held)
        self.assertEqual(port.submission_outcome, "uncertain")
        self.assertIsNone(port.submitted_event_count)
        self.assertTrue(port.release_owned())
        self.assertFalse(port.held)
        self.assertEqual([call.args[0] for call in port.user.SendInput.call_args_list], [3, 1])

    def test_final_permission_runs_after_target_queries(self):
        port = self.port()
        revoked = []
        port.user.GetAncestor.side_effect = lambda *args: revoked.append(True) or 1
        with self.assertRaisesRegex(NativeUnavailable, "final_target_or_permission"):
            port.click(1, 60, 60, lambda: not revoked)
        port.user.SendInput.assert_not_called()

    def test_final_held_input_blocks_native_submission(self):
        port = self.port()
        port.user.GetAsyncKeyState.return_value = 0x8000
        with self.assertRaises(NativeUnavailable):
            port.click(1, 60, 60, lambda: True)
        port.user.SendInput.assert_not_called()

    def test_native_pid_rejects_an_external_window_despite_caller_assertions(self):
        port = self.port()
        port.user.GetWindowThreadProcessId.side_effect = lambda *args: 7  # PID remains unresolved/zero.
        with self.assertRaisesRegex(NativeUnavailable, "native_self_owned_target_required"):
            port.click(1, 60, 60, lambda: True)
        port.user.SendInput.assert_not_called()

    def test_same_process_lease_rejects_recursive_windows_mutex_ownership(self):
        port = self.port()
        native._PROCESS_INPUT_LEASE.acquire()
        try:
            with self.assertRaisesRegex(NativeUnavailable, "process_local_input_owner"):
                port.open(Mock())
            port.kernel.CreateMutexW.assert_not_called()
        finally:
            native._PROCESS_INPUT_LEASE.release()

    def test_release_failure_does_not_skip_guard_quit_or_drop_exclusivity(self):
        port = self.port()
        port.mutex, port.mutex_owned, port.held = 123, True, True
        port.user.SendInput.side_effect = RuntimeError("synthetic release failure")
        port.thread_id = 7
        port.thread.is_alive.side_effect = [True, True, False]
        self.assertFalse(port.close())
        port.user.PostThreadMessageW.assert_called_once_with(7, 0x0012, 0, 0)
        port.thread.join.assert_called_once_with(1)
        self.assertTrue(port.held)
        self.assertEqual(port.mutex, 123)
        port.kernel.ReleaseMutex.assert_not_called()
        port.kernel.CloseHandle.assert_not_called()

    def test_fake_hotkey_error_five_aborts_before_any_send(self):
        port = self.port()
        port.thread = None
        port.ready.clear()
        port.kernel.CreateMutexW.return_value = 123
        port.kernel.WaitForSingleObject.return_value = 0
        port.kernel.GetCurrentThreadId.return_value = 7
        port.user.SetWindowsHookExW.side_effect = [101, 102]
        port.user.RegisterHotKey.return_value = False
        port.user.UnhookWindowsHookEx.return_value = True
        with patch.object(native.c, "get_last_error", return_value=5, create=True):
            with self.assertRaisesRegex(NativeUnavailable, "hotkey_registration_failed:5"):
                port.open(Mock())
        port.user.SendInput.assert_not_called()
        self.assertEqual(port.user.UnhookWindowsHookEx.call_count, 2)
        self.assertIsNone(port.mutex)
        self.assertFalse(port.process_lease_owned)

    def test_unhook_exception_does_not_skip_other_hook_cleanup(self):
        port = self.port()
        port.thread = None
        port.ready.clear()
        port.kernel.CreateMutexW.return_value = 123
        port.kernel.WaitForSingleObject.return_value = 0
        port.kernel.GetCurrentThreadId.return_value = 7
        port.user.SetWindowsHookExW.side_effect = [101, 102]
        port.user.RegisterHotKey.return_value = False
        port.user.UnhookWindowsHookEx.side_effect = [RuntimeError("synthetic unhook failure"), True]
        with patch.object(native.c, "get_last_error", return_value=5, create=True):
            with self.assertRaisesRegex(NativeUnavailable, "hotkey_registration_failed:5"):
                port.open(Mock())
        self.assertEqual(port.user.UnhookWindowsHookEx.call_count, 2)
        port.user.SendInput.assert_not_called()
        self.assertIn("unhook_failed", port.cleanup_errors)
        self.assertTrue(port.process_lease_owned)
        self.assertIn(port, native._INCOMPLETE_NATIVE_CLEANUP)
        port.kernel.ReleaseMutex.assert_not_called()

    def test_guard_close_timeout_retains_exclusivity_and_callback_references(self):
        port = self.port()
        port.mutex, port.mutex_owned = 123, True
        self.assertFalse(port.close())
        self.assertIn("guard_thread_close_timeout", port.cleanup_errors)
        self.assertIn(port, native._INCOMPLETE_NATIVE_CLEANUP)
        port.kernel.ReleaseMutex.assert_not_called()

    def test_guard_that_never_started_does_not_prevent_mutex_cleanup(self):
        port = self.port()
        port.thread = threading.Thread(target=lambda: None)
        port.mutex, port.mutex_owned = 123, True
        self.assertTrue(port.close())
        port.kernel.ReleaseMutex.assert_called_once_with(123)
        port.kernel.CloseHandle.assert_called_once_with(123)


if __name__ == "__main__":
    unittest.main()
