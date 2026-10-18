"""Precise ABI/memory/guard evidence tests; never register hooks or send input."""
import ast
import ctypes as c
import json
from pathlib import Path
import unittest
from unittest.mock import Mock, patch

import test_owned_window_diagnostic as existing

diagnostic = existing.diagnostic


class MouseTagEvidenceTests(unittest.TestCase):
    def port(self):
        return existing.DiagnosticTests().port()  # Fake DLLs only.

    def callback(self, port, stop):
        source = Path(diagnostic.native.__file__).read_text(encoding="utf-8")
        tree = ast.parse(source)
        cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "WindowsClickPort")
        opened = next(n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name == "open")
        loop = next(n for n in opened.body if isinstance(n, ast.FunctionDef) and n.name == "hook_loop")
        callback = next(n for n in loop.body if isinstance(n, ast.FunctionDef) and n.name == "mouse")
        namespace = {"self": port, "stop": stop, "c": c}
        exec(compile(ast.Module(body=[callback], type_ignores=[]), "<python-hook-body-only>", "exec"), namespace)
        return namespace["mouse"]

    def test_native_layout_matches_windows_pointer_sized_abi(self):
        port = self.port()
        bits = c.sizeof(c.c_void_p) * 8
        self.assertEqual(c.sizeof(diagnostic.w.LONG), 4)
        self.assertEqual(c.sizeof(diagnostic.w.DWORD), 4)
        self.assertEqual(c.sizeof(c.c_size_t), bits // 8)
        self.assertEqual(c.sizeof(port.Input), 40 if bits == 64 else 28)
        self.assertEqual(port.Input.payload.offset, 8 if bits == 64 else 4)
        for cls, field in ((port.Mouse, 'dwExtraInfo'), (port.MouseHook, 'extra')):
            self.assertEqual(c.sizeof(cls), 32 if bits == 64 else 24)
            self.assertEqual(getattr(cls, field).offset, 24 if bits == 64 else 20)
        self.assertEqual(c.sizeof(port.KeyboardHook), 24 if bits == 64 else 20)
        self.assertEqual(port.KeyboardHook.extra.offset, 16)

    def test_actual_batch_bytes_preserve_full_tag_at_every_event(self):
        bits = c.sizeof(c.c_void_p) * 8
        values = [1, 0x7FFFFFFF] + ([0x80000001, 0x180000001, 0x1234567887654321,
                                   0x7FFFFFFFFFFFFFFF] if bits == 64 else [])
        for value in values:
            port = self.port()
            port.token = value  # Synthetic values only, no native call.
            port.user.SendInput.return_value = 3
            self.assertEqual(port.click(1, 60, 60, lambda: True), 3)
            _, events, _ = port.user.SendInput.call_args.args
            raw = bytes(events)
            offset = port.Input.payload.offset + port.Mouse.dwExtraInfo.offset
            for i in range(3):
                start = i * c.sizeof(port.Input) + offset
                self.assertEqual(int.from_bytes(raw[start:start + bits // 8], 'little'), value)
            hook = port.MouseHook()
            hook.extra = value
            self.assertEqual(c.cast(c.pointer(hook), c.POINTER(port.MouseHook)).contents.extra, value)

    def test_comparison_separates_full_zero_and_sign_extension_without_acceptance(self):
        expected = 0x1234567887654321
        cases = [(expected, True, True, False, False),
                 (0x87654321, False, True, True, False),
                 (0xFFFFFFFF87654321, False, True, False, True),
                 (0, False, False, False, False)]
        for observed, full, low, zero_extended, sign_extended in cases:
            result = diagnostic.describe_mouse_tag(expected, observed, 64, b'x' * 32)
            self.assertEqual(result['full_equal'], full)
            self.assertEqual(result['low32_equal'], low)
            self.assertEqual(result['equals_zero_extended_expected_low32'], zero_extended)
            self.assertEqual(result['equals_sign_extended_expected_low32'], sign_extended)
            self.assertEqual(result['expected_fingerprint'] == result['observed_fingerprint'], full)
            self.assertNotIn('expected', result)
            self.assertNotIn('observed', result)
        self.assertFalse(diagnostic.describe_mouse_tag(expected, -1, 64, b'x' * 32)['comparison_valid'])
        result32 = diagnostic.describe_mouse_tag(0x7FFFFFFF, 0x7FFFFFFF, 32, b'x' * 32)
        self.assertTrue(result32['full_equal'])
        self.assertEqual(result32['pointer_bits'], 32)

    def test_real_python_guard_keeps_rejecting_partial_and_noninjected_matches(self):
        if c.sizeof(c.c_void_p) != 8:
            self.skipTest('High/low 64-bit cases need a 64-bit interpreter')
        expected = 0x1234567887654321
        for flags, observed, foreign in ((1, expected, False), (1, expected & 0xFFFFFFFF, True),
                                         (1, 0xFFFFFFFF87654321, True), (1, 0, True), (0, expected, True)):
            port, stop = self.port(), Mock()
            port.token = port.created_token = expected
            callback = self.callback(port, stop)
            hook = port.MouseHook()
            hook.flags, hook.extra = flags, observed
            callback(0, 0x200, c.addressof(hook))  # MOVE, formerly absent from audit.
            if foreign:
                stop.assert_called_once_with('user_or_foreign_mouse_input')
            else:
                stop.assert_not_called()
            snapshot = port.ownership_snapshot()
            self.assertEqual(snapshot['first_foreign_mouse'] is not None, foreign)
            self.assertEqual(snapshot['mouse_trace'][0]['full_equal'], observed == expected)
            port.user.SendInput.assert_not_called()
            port.user.CallNextHookEx.assert_called_once()

    def test_snapshot_is_bounded_and_retains_first_foreign_without_raw_tags(self):
        port = self.port()
        expected = 0x1234567887654321 if c.sizeof(c.c_void_p) == 8 else 0x12345679
        port.token = port.created_token = expected
        port._diagnostic_mouse_tag(0x200, 1, expected, 0)
        for i in range(30):
            port._diagnostic_mouse_tag(0x201 if i % 2 == 0 else 0x202, 1, expected, expected)
        snapshot = port.ownership_snapshot()
        self.assertEqual(snapshot['mouse_events_seen'], 31)
        self.assertEqual(snapshot['trace_dropped'], 15)
        self.assertEqual(len(snapshot['mouse_trace']), 16)
        self.assertTrue(snapshot['first_foreign_mouse']['observed_zero'])
        data = json.dumps(snapshot)
        self.assertNotIn(str(expected), data)
        self.assertNotIn(hex(expected), data)
        self.assertNotIn('tag_fingerprint_key', data)
        changed_key = diagnostic.describe_mouse_tag(expected, expected, c.sizeof(c.c_void_p)*8, b'z'*32)
        self.assertNotEqual(changed_key['expected_fingerprint'], snapshot['mouse_trace'][0]['expected_fingerprint'])

    def test_snapshot_copies_under_lock_but_formats_after_unlock(self):
        port = self.port()
        port._diagnostic_mouse_tag(0x200, 1, port.token, 0)
        original = diagnostic.describe_mouse_tag
        def outside_lock(*args):
            self.assertFalse(port.mouse_tag_lock.locked())
            return original(*args)
        with patch.object(diagnostic, 'describe_mouse_tag', side_effect=outside_lock):
            result = port.ownership_snapshot()
        self.assertEqual(result['mouse_events_seen'], len(result['mouse_trace']))
        self.assertEqual(result['trace_dropped'], 0)


if __name__ == '__main__':
    unittest.main()
