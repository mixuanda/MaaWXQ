"""Offline acceptance/lifecycle tests; no native DLL, Tk window or input opens."""
from collections import deque
import contextlib
import ctypes
import importlib.util
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import threading
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("owned_window_diagnostic", ROOT / "tools/owned_window_diagnostic.py")
diagnostic = importlib.util.module_from_spec(spec)
spec.loader.exec_module(diagnostic)
native = diagnostic.native


class DiagnosticTests(unittest.TestCase):
    def hold_row(self):
        return dict(explicit_confirmation=True, cleanup_confirmed=True, raw_return=2, sent=True,
                    submission_outcome="owned_down_submitted", owned_down_delivered_before_trigger=True,
                    target_downs=1, target_ups=1, release_attempts=1, release_raw_return=1,
                    own_down_up_hook_pair=True, left_button_down_after_release=False,
                    second_attempt_rejected=True, stop_reason="user_or_foreign_keyboard_input",
                    physical_trigger_before_stop=True, stop_to_release_ms=10, stop_to_widget_up_ms=12,
                    physical_f9_down=True, physical_f9_up=True, registered_hotkey_received=True,
                    emergency_keys_released=True, physical_right_shift_down=True,
                    right_shift_down_after_release=True, right_shift_preserved_100ms=True,
                    right_shift_released_early=False, physical_right_shift_up_after_prompt=True)

    def test_hold_acceptance_requires_physical_delivery_release_and_cleanup(self):
        row = self.hold_row()
        for name, invalid in (
            ("emergency", [dict(registered_hotkey_received=False), dict(physical_f9_up=False),
                           dict(emergency_keys_released=False), dict(stop_reason="diagnostic_deadline_expired")]),
            ("owned_release", [dict(right_shift_released_early=True), dict(right_shift_down_after_release=False),
                               dict(right_shift_preserved_100ms=False), dict(physical_right_shift_up_after_prompt=False)]),
        ):
            self.assertTrue(diagnostic.phase_passes(name, row))
            for change in invalid + [dict(target_ups=0), dict(cleanup_confirmed=False),
                                     dict(stop_to_widget_up_ms=251), dict(sent=False)]:
                with self.subTest(name=name, change=change):
                    self.assertFalse(diagnostic.phase_passes(name, row | change))

    def test_click_receipt_or_foreign_stop_cannot_pass_as_verified_delivery(self):
        row = dict(explicit_confirmation=True, cleanup_confirmed=True, raw_return=3, sent=True,
                   target_downs=1, target_ups=1, submission_outcome="complete_batch",
                   own_down_up_hook_pair=True, stop_reason="one_action_completed")
        self.assertTrue(diagnostic.phase_passes("click", row))
        for change in (dict(target_ups=0), dict(own_down_up_hook_pair=False),
                       dict(submission_outcome="uncertain"), dict(stop_reason="user_or_foreign_mouse_input")):
            self.assertFalse(diagnostic.phase_passes("click", row | change))

    def test_rejected_stage_cannot_hide_uncertain_input_or_external_focus(self):
        row = dict(explicit_confirmation=True, cleanup_confirmed=True, attempt_rejected=True,
                   sent=False, target_downs=0, target_ups=0, stop_expected=True,
                   submission_outcome="not_attempted", raw_return=None, release_attempts=0)
        self.assertTrue(diagnostic.phase_passes("deadline", row))
        self.assertFalse(diagnostic.phase_passes("deadline", row | dict(submission_outcome="uncertain")))
        self.assertFalse(diagnostic.phase_passes("focus", row))
        self.assertTrue(diagnostic.phase_passes("focus", row | dict(focus_transition_verified=True)))

    def test_foreign_keyboard_stop_does_not_count_as_focus_rejection(self):
        suite = diagnostic.Suite.__new__(diagnostic.Suite)
        suite.ending, suite.index, suite.root = False, 2, Mock()
        suite.active = {"focus_target_hwnd": 2}
        broker = Mock()
        broker.evidence.binding.hwnd = 1
        broker.stop_reason = "user_or_foreign_keyboard_input"
        broker.click_once.side_effect = native.NativeUnavailable("stop_latched:user_or_foreign_keyboard_input")
        suite.current_broker = Mock(return_value=broker)
        observation = dict(pid=os.getpid(), desktop=dict(foreground_hwnd=2))
        with patch.object(diagnostic, "inspect_window", return_value=observation):
            suite.check_rejection()
        self.assertTrue(suite.active["focus_transition_verified"])
        self.assertFalse(suite.active["stop_expected"])
        broker.close.assert_called_once()

    def test_delayed_callbacks_do_nothing_after_stop(self):
        suite = diagnostic.Suite.__new__(diagnostic.Suite)
        suite.ending, suite.current_broker = True, Mock()
        for name in ("begin_phase", "check_rejection", "poll_hold", "complete_phase"):
            getattr(suite, name)()
        suite.poll_input_ready({})
        suite.current_broker.assert_not_called()

    def test_report_failure_does_not_skip_cleanup_or_console_evidence(self):
        suite = diagnostic.Suite.__new__(diagnostic.Suite)
        suite.ending, suite.active = False, None
        broker = Mock()
        suite.brokers = [broker]
        suite.broker_record = Mock(return_value=dict(cleanup_confirmed=True))
        suite.result = dict(phases={name: dict(status="passed") for name, _, _ in diagnostic.PHASES})
        suite.save = Mock(side_effect=OSError("synthetic write failure"))
        suite.output, suite.root = Path("synthetic-report.json"), Mock()
        suite.instructions = suite.status = suite.run_button = suite.check = Mock()
        suite.tk = Mock()
        console = io.StringIO()
        with contextlib.redirect_stdout(console):
            suite.finish("all_owned_window_phases_passed")
        broker.close.assert_called_once()
        self.assertFalse(suite.result["all_phases_passed"])
        self.assertEqual(suite.result["status"], "report_write_failed_after_cleanup")
        self.assertIn('"report_write_error": "OSError"', console.getvalue())

    def test_default_and_blocked_entry_never_create_ui_or_call_native_token_query(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            broker = root / "backends/win32_single_click.py"
            broker.parent.mkdir()
            broker.write_bytes(Path(native.__file__).read_bytes())
            for mode, status, code in (([], "input_disabled", 0),
                                       (["--enable-once"], "requires_normal_nonadmin_noncontainer_process", 2)):
                with patch.object(diagnostic, "ROOT", root), patch.object(native, "__file__", str(broker)), \
                        patch.object(sys, "argv", ["diagnostic", *mode]), \
                        patch.object(diagnostic, "Suite", side_effect=AssertionError("UI forbidden")) as ui, \
                        patch.object(diagnostic, "token_metadata", return_value=dict(known=True, app_container=True,
                                     elevated=False, ui_access=False)) as token, contextlib.redirect_stdout(io.StringIO()):
                    self.assertEqual(diagnostic.main(), code)
                    ui.assert_not_called()
                    self.assertEqual(token.call_count, int(bool(mode)))
                reports = sorted((root / "local/owned-window-diagnostic").glob("*.json"))
                data = json.loads(reports[-1].read_text(encoding="utf-8"))
                self.assertEqual(data["status"], status)
                self.assertFalse(data["window_created"])
                self.assertTrue(all(row["status"] == "not_run" for row in data["phases"].values()))
                self.assertEqual(data["game_input_count"], 0)

    def port(self):
        user, kernel = Mock(), Mock()
        user.GetSystemMetrics.side_effect = lambda index: {76: 0, 77: 0, 78: 1000, 79: 800}[index]
        user.GetForegroundWindow.return_value = user.WindowFromPoint.return_value = user.GetAncestor.return_value = 1
        user.GetAsyncKeyState.return_value = 0
        def current_pid(hwnd, output):
            ctypes.cast(output, ctypes.POINTER(native.w.DWORD)).contents.value = os.getpid()
            return 7
        user.GetWindowThreadProcessId.side_effect = current_pid
        with patch.object(ctypes, "WinDLL", side_effect=[user, kernel], create=True), \
                patch.object(ctypes, "WINFUNCTYPE", ctypes.CFUNCTYPE, create=True), \
                patch.object(native.sys, "platform", "win32"):
            port = diagnostic.OwnedDiagnosticPort(Mock())
        port.owner_thread, port.thread = threading.get_ident(), Mock()
        port.thread.is_alive.return_value = True
        port.ready.set()
        return port

    def evidence(self):
        binding = native.Binding(1, os.getpid(), "synthetic-start", "SyntheticWidget", "synthetic-geometry", 100, 80, 10, 20)
        return native.ClickEvidence(binding, 1.0, 50, 40, "self_owned_test")

    def test_hold_release_preserves_foreign_shift_and_emits_only_owned_mouse_up(self):
        port = self.port()
        port.user.SendInput.side_effect = [2, 1]
        port.hold_owned_left_once(self.evidence(), lambda: True)
        self.assertTrue(port.held)
        port.user.GetAsyncKeyState.side_effect = lambda code: 0x8000 if code == 0xA1 else 0
        self.assertTrue(port.release_owned())
        self.assertFalse(port.held)
        self.assertEqual(port.release_samples[1]["right_shift_down"], True)
        self.assertEqual(port.owned_release_attempt_count, 1)
        count, event, _ = port.user.SendInput.call_args.args
        event = ctypes.cast(event, ctypes.POINTER(port.Input)).contents
        self.assertEqual((count, event.type, event.mi.dwFlags), (1, 0, 4))
        with self.assertRaisesRegex(native.NativeUnavailable, "one_attempt"):
            port.hold_owned_left_once(self.evidence(), lambda: True)
        self.assertEqual(port.user.SendInput.call_count, 2)

    def test_incomplete_hold_is_not_retried_or_counted_as_a_held_button(self):
        for inserted in (0, 1):
            port = self.port()
            port.user.SendInput.return_value = inserted
            with self.assertRaisesRegex(native.NativeUnavailable, "owned_hold_incomplete"):
                port.hold_owned_left_once(self.evidence(), lambda: True)
            self.assertFalse(port.held)
            self.assertEqual(port.submission_outcome, "incomplete_batch")
            port.user.SendInput.assert_called_once()
            self.assertEqual(port.owned_release_attempt_count, 0)


class InputReadinessTests(unittest.TestCase):
    def test_high_bit_only_and_privacy_safe_categories(self):
        states = {0x14: 1, 0x90: 1, 0x91: 1, 0x41: 1}
        self.assertEqual(diagnostic.held_input_categories(lambda key: states.get(key, 0)), [])
        states.update({1: -32768, 0x20: -32767, 0xA1: 0x8000, 0x10: 0x8000, 0x41: 0x8000})
        self.assertEqual(diagnostic.held_input_categories(lambda key: states.get(key, 0)),
                         ['activation.space', 'keyboard.other', 'modifier.right_shift', 'mouse.left'])

    def test_long_confirmation_hold_waits_then_requires_full_quiet_interval(self):
        gate = diagnostic.InputReadinessGate(0.0)
        for step in range(1, 21):
            self.assertEqual(gate.observe(['activation.space'], step, step / 20), 'waiting')
        for step in range(21, 41):
            self.assertEqual(gate.observe([], 21, step / 20), 'waiting')
        self.assertEqual(gate.observe([], 21, 2.1), 'ready')
        self.assertEqual(gate.report['observed_held_categories'], ['activation.space'])
        self.assertEqual(gate.report['last_held_categories'], [])

    def test_short_press_or_motion_between_samples_resets_countdown(self):
        gate = diagnostic.InputReadinessGate(0.0)
        for step in range(1, 20):
            self.assertEqual(gate.observe([], 10, step / 20), 'waiting')
        self.assertEqual(gate.observe([], 11, 1.0), 'waiting')
        for step in range(21, 40):
            self.assertEqual(gate.observe([], 11, step / 20), 'waiting')
        self.assertEqual(gate.observe([], 11, 2.05), 'ready')
        self.assertEqual(gate.report['quiet_resets'], 1)

    def test_ui_stall_does_not_count_as_quiet_and_deadline_never_extends(self):
        gate = diagnostic.InputReadinessGate(0.0)
        gate.observe([], 10, 0.05)
        self.assertEqual(gate.observe([], 10, 2.0), 'waiting')
        self.assertEqual(gate.report['quiet_seconds'], 0)
        self.assertEqual(gate.observe([], 10, 15.0), 'timed_out')
        held = diagnostic.InputReadinessGate(0.0)
        for step in range(1, 300):
            self.assertEqual(held.observe(['mouse.left'], step, step / 20), 'waiting')
        self.assertEqual(held.observe([], 300, 15.0), 'timed_out')

    def suite(self):
        suite = diagnostic.Suite.__new__(diagnostic.Suite)
        suite.ending, suite.index = False, 1
        suite.active = dict(status='waiting_for_input_ready')
        suite.result, suite.brokers = {}, []
        suite.root, suite.status, suite.save, suite.fail = Mock(), Mock(), Mock(), Mock()
        suite.evidence = Mock()
        suite.readiness = diagnostic.InputReadinessGate(0.0)
        suite.input_probe = Mock()
        suite.input_probe.sample.return_value = ([], 5)
        return suite

    def test_timeout_focus_loss_and_cancel_never_construct_broker(self):
        for error in (None, native.NativeUnavailable('prearm_owned_window_lost_foreground'),
                      native.NativeUnavailable('prearm_input_marker_unavailable')):
            suite = self.suite()
            suite.input_probe.sample.side_effect = error
            with patch.object(diagnostic.time, 'monotonic', return_value=16.0), \
                    patch.object(native, 'SingleClickBroker', side_effect=AssertionError('No arm allowed')) as broker:
                suite.poll_input_ready(suite.active)
            suite.fail.assert_called_once()
            broker.assert_not_called()
            self.assertEqual(suite.brokers, [])
        suite = self.suite()
        suite.ending = True
        suite.poll_input_ready(suite.active)
        suite.input_probe.sample.assert_not_called()
        suite.ending = False
        suite.poll_input_ready(dict(status='waiting_for_input_ready'))  # Stale phase callback.
        suite.input_probe.sample.assert_not_called()

    def test_ready_transition_dispatches_once_and_final_race_refuses(self):
        suite = self.suite()
        for step in range(1, 22):
            suite.readiness.observe([], 5, step / 20)
        suite.begin_phase = Mock()
        phase = suite.active
        with patch.object(diagnostic.time, 'monotonic', return_value=1.1):
            suite.poll_input_ready(phase)
            suite.poll_input_ready(phase)
        suite.begin_phase.assert_called_once()
        self.assertEqual(phase['status'], 'arming')

        for held, marker in ((['mouse.left'], 5), ([], 6)):
            suite = self.suite()
            suite.active['status'] = 'arming'
            for step in range(1, 22):
                suite.readiness.observe([], 5, step / 20)
            suite.input_probe.sample.return_value = (held, marker)
            with patch.object(diagnostic.time, 'monotonic', return_value=1.15), \
                    patch.object(native, 'SingleClickBroker', side_effect=AssertionError('No arm allowed')) as broker:
                diagnostic.Suite.begin_phase(suite)
            broker.assert_not_called()
            self.assertEqual(suite.brokers, [])
            self.assertEqual(str(suite.fail.call_args.args[0]), 'input_changed_before_arming')

    def test_identity_query_stall_requires_new_quiet_interval_before_construction(self):
        suite = self.suite()
        suite.active['status'] = 'arming'
        for step in range(1, 22):
            suite.readiness.observe([], 5, step / 20)
        clock = {'now': 1.1}
        def slow_identity():
            clock['now'] = 2.0
            return Mock()
        suite.evidence.side_effect = slow_identity
        with patch.object(diagnostic.time, 'monotonic', side_effect=lambda: clock['now']), \
                patch.object(native, 'SingleClickBroker', side_effect=AssertionError('Must not arm')) as broker:
            suite.begin_phase()
        broker.assert_not_called()
        self.assertEqual(str(suite.fail.call_args.args[0]), 'input_changed_before_arming')

    def test_diagnostic_open_refuses_held_input_before_native_guard_or_submission(self):
        port = DiagnosticTests().port()
        port.user.GetAsyncKeyState.side_effect = lambda key: 0x8000 if key == 0x20 else 0
        token = dict(known=True, app_container=False, elevated=False, ui_access=False)
        with patch.object(diagnostic, 'token_metadata', return_value=token), \
                patch.object(native.WindowsClickPort, 'open', side_effect=AssertionError('Guard must not open')) as opened:
            with self.assertRaisesRegex(native.NativeUnavailable, '^preexisting_held_input$'):
                port.open(Mock())
        self.assertEqual(port.open_input_precheck['held_categories'], ['activation.space'])
        opened.assert_not_called()
        port.user.SendInput.assert_not_called()


if __name__ == "__main__":
    unittest.main()
