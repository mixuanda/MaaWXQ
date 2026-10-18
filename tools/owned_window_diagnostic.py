"""Explicit, user-operated checks on this process's own fixed test widgets.

Native stages have not been run by the restricted executor. There is no game,
external-window, keyboard injection, remote control, elevation or fallback mode.
"""
import argparse
from collections import deque
import ctypes as c
from ctypes import wintypes as w
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import secrets
import sys
import threading
import time

ROOT = Path(__file__).resolve().parents[1]
EXPECTED_BROKER_CANONICAL_HASH = "4c0e382c34601ea609e319e331ef1ca1d6ea9106e69866b96b3bbfa1d2075724"
sys.path.insert(0, str(ROOT))
import backends.win32_single_click as native
from window_identity import find_windows, inspect_window

AUTO_PHASES = ("deadline", "click", "focus")
PHASES = (
    ("deadline", "自动检查 1/3：等待后不点击 / Wait without clicking",
     "授权后自动依次执行第 1–3 项。松开所有键和鼠标，保持静止；本项不应产生点击。\n"
     "One approval covers checks 1–3. Release all keys/buttons and keep still. This check must reject the delayed click."),
    ("click", "自动检查 2/3：点一下蓝色区域 / One target click",
     "自动进行，无需再次确认。请保持静止；蓝色区域应只收到一次按下和一次松开。\n"
     "Automatic: keep still. The blue target must receive exactly one DOWN and one UP."),
    ("focus", "自动检查 3/3：切换窗口后不点击 / Stop after focus changes",
     "自动进行，无需再次确认。请保持静止；程序切到自己的第二个窗口，原目标必须拒绝点击。\n"
     "Automatic: keep still. Focus moves to another owned window; the old target must reject input."),
    ("emergency", "真人 1/2：急停组合键 / Physical emergency chord",
     "本项稍后会请你同时按 Ctrl+Alt+F9，再松开这三个键。现在不要提前按键。\n"
     "先点击“我准备好了”；看到“现在按键”的提示再按。\n"
     "You will press Ctrl+Alt+F9 together. Wait for the NOW prompt."),
    ("owned_release", "真人 2/2：保留右 Shift / Preserve physical Right Shift",
     "本项稍后会请你按住键盘右侧 Shift。现在先不要按。\n"
     "先点击“我准备好了”；按住后，等提示“现在松开右 Shift”再松开。不要碰鼠标。\n"
     "You will hold RIGHT Shift until the release prompt. Do not touch the mouse."),
)

PREARM_TIMEOUT_SECONDS = 15.0
PREARM_QUIET_SECONDS = 1.0
PREARM_POLL_MS = 50
PREARM_MAX_SAMPLE_GAP_SECONDS = 0.25


def held_input_categories(get_key_state):
    """Same high-bit/all-VK predicate as the broker; never retain text/key codes."""
    names = {1: "mouse.left", 2: "mouse.right", 4: "mouse.middle", 5: "mouse.x1", 6: "mouse.x2",
             0x10: "modifier.shift", 0x11: "modifier.ctrl", 0x12: "modifier.alt",
             0xA0: "modifier.left_shift", 0xA1: "modifier.right_shift",
             0xA2: "modifier.left_ctrl", 0xA3: "modifier.right_ctrl",
             0xA4: "modifier.left_alt", 0xA5: "modifier.right_alt",
             0x5B: "modifier.left_win", 0x5C: "modifier.right_win",
             0x0D: "activation.enter", 0x20: "activation.space", 0x1B: "control.escape",
             0x14: "lock.caps", 0x90: "lock.num", 0x91: "lock.scroll"}
    # No GetKeyState toggle bits, ToUnicode, key names for text keys, or key-up.
    categories = {names.get(code, "keyboard.other") for code in range(1, 256)
                  if get_key_state(code) & 0x8000}
    for modifier in ("shift", "ctrl", "alt"):
        if categories & {"modifier.left_" + modifier, "modifier.right_" + modifier}:
            categories.discard("modifier." + modifier)  # Avoid generic/side aliases in the report.
    return sorted(categories)


class PrearmInputProbe:
    """Read-only, foreground-owned sampling. No port, hooks, lease or input."""
    def __init__(self, widget_hwnd):
        self.user = c.WinDLL("user32", use_last_error=True)
        class LastInput(c.Structure):
            _fields_ = [("cbSize", w.UINT), ("dwTime", w.DWORD)]
        self.LastInput = LastInput
        for name, arguments, result in (
            ("GetAsyncKeyState", [c.c_int], c.c_short),
            ("GetLastInputInfo", [c.POINTER(LastInput)], w.BOOL),
            ("GetForegroundWindow", [], w.HWND),
            ("GetAncestor", [w.HWND, w.UINT], w.HWND),
            ("GetWindowThreadProcessId", [w.HWND, c.POINTER(w.DWORD)], w.DWORD),
        ):
            function = getattr(self.user, name)
            function.argtypes, function.restype = arguments, result
        self.hwnd = int(self.user.GetAncestor(widget_hwnd, 2) or 0)
        pid = w.DWORD()
        if (not self.hwnd or not self.user.GetWindowThreadProcessId(self.hwnd, c.byref(pid))
                or pid.value != os.getpid()):
            raise native.NativeUnavailable("prearm_owned_window_required")

    def sample(self):
        if int(self.user.GetForegroundWindow() or 0) != self.hwnd:
            raise native.NativeUnavailable("prearm_owned_window_lost_foreground")
        held = held_input_categories(self.user.GetAsyncKeyState)
        marker = self.LastInput(c.sizeof(self.LastInput), 0)
        if not self.user.GetLastInputInfo(c.byref(marker)):
            raise native.NativeUnavailable("prearm_input_marker_unavailable")
        if int(self.user.GetForegroundWindow() or 0) != self.hwnd:
            raise native.NativeUnavailable("prearm_owned_window_lost_foreground")
        return held, int(marker.dwTime)  # Marker stays in memory, never in JSON.


class InputReadinessGate:
    """Bounded pre-arm wait; observations do not spend or retry the action budget."""
    def __init__(self, started):
        self.started, self.last_at, self.last_marker, self.quiet_since = started, None, None, None
        self.observed = set()
        self.report = dict(status="waiting", timeout_seconds=PREARM_TIMEOUT_SECONDS,
                           quiet_required_seconds=PREARM_QUIET_SECONDS, poll_ms=PREARM_POLL_MS,
                           samples=0, quiet_resets=0, observed_held_categories=[], last_held_categories=[])

    def observe(self, held, marker, now):
        elapsed = now - self.started
        self.observed.update(held)
        self.report.update(samples=self.report["samples"] + 1, elapsed_seconds=elapsed,
                           observed_held_categories=sorted(self.observed), last_held_categories=list(held))
        # Absolute timeout, including UI stalls; successful-looking late samples cannot arm.
        if elapsed < 0 or elapsed >= PREARM_TIMEOUT_SECONDS:
            self.report["status"] = "timed_out"
            return "timed_out"
        changed = self.last_marker is not None and marker != self.last_marker
        gap = self.last_at is not None and not 0 <= now - self.last_at <= PREARM_MAX_SAMPLE_GAP_SECONDS
        if held or changed or gap:
            if self.quiet_since is not None:
                self.report["quiet_resets"] += 1
            self.quiet_since = None
        if not held and self.quiet_since is None:
            self.quiet_since = now
        self.last_at, self.last_marker = now, marker
        quiet = 0.0 if self.quiet_since is None else now - self.quiet_since
        self.report.update(quiet_seconds=quiet, remaining_seconds=PREARM_TIMEOUT_SECONDS - elapsed)
        status = "ready" if quiet >= PREARM_QUIET_SECONDS else "waiting"
        self.report["status"] = status
        return status


def describe_mouse_tag(expected, observed, pointer_bits, fingerprint_key):
    """Read-only comparisons, never an acceptance rule; no raw tag is returned."""
    mask = (1 << pointer_bits) - 1
    if not (type(expected) is int and type(observed) is int and 0 <= expected <= mask and 0 <= observed <= mask):
        return {"comparison_valid": False, "pointer_bits": pointer_bits}
    low = expected & 0xFFFFFFFF
    sign_extended = (low | (mask ^ 0xFFFFFFFF)) if pointer_bits > 32 and low & 0x80000000 else low
    def fingerprint(value):
        return hashlib.blake2b(value.to_bytes(pointer_bits // 8, "little"),
                               key=fingerprint_key, digest_size=8).hexdigest()
    return {"comparison_valid": True, "pointer_bits": pointer_bits,
            "expected_bits": expected.bit_length(), "observed_bits": observed.bit_length(),
            "observed_zero": observed == 0, "full_equal": observed == expected,
            "low32_equal": (observed & 0xFFFFFFFF) == low,
            "equals_zero_extended_expected_low32": observed == low,
            "equals_sign_extended_expected_low32": observed == sign_extended,
            "xor_bit_count": (expected ^ observed).bit_count(),
            "expected_fingerprint": fingerprint(expected), "observed_fingerprint": fingerprint(observed)}


def describe_native_layout(port):
    """ctypes layout metadata only; no library lookup or native call."""
    types = {"INPUT": port.Input, "MOUSEINPUT": port.Mouse, "MSLLHOOKSTRUCT": port.MouseHook,
             "KBDLLHOOKSTRUCT": port.KeyboardHook}
    return {"pointer_bits": c.sizeof(c.c_void_p) * 8, "ulong_ptr_bytes": c.sizeof(c.c_size_t),
            "long_bytes": c.sizeof(w.LONG), "dword_bytes": c.sizeof(w.DWORD),
            "structures": {name: {"bytes": c.sizeof(cls), "alignment": c.alignment(cls),
                "offsets": {field[0]: getattr(cls, field[0]).offset for field in cls._fields_}}
                for name, cls in types.items()}}


def _read_token_metadata():
    kernel, advapi = c.WinDLL("kernel32", use_last_error=True), c.WinDLL("advapi32", use_last_error=True)
    kernel.GetCurrentProcess.restype = w.HANDLE
    kernel.CloseHandle.argtypes, kernel.CloseHandle.restype = [w.HANDLE], w.BOOL
    advapi.OpenProcessToken.argtypes = [w.HANDLE, w.DWORD, c.POINTER(w.HANDLE)]
    advapi.OpenProcessToken.restype = w.BOOL
    advapi.GetTokenInformation.argtypes = [w.HANDLE, c.c_int, c.c_void_p, w.DWORD, c.POINTER(w.DWORD)]
    advapi.GetTokenInformation.restype = w.BOOL
    handle = w.HANDLE()
    if not advapi.OpenProcessToken(kernel.GetCurrentProcess(), 8, c.byref(handle)):
        return {"known": False, "error": c.get_last_error()}
    result = {"known": True}
    try:
        for name, cls in (("app_container", 29), ("elevated", 20), ("ui_access", 26)):
            value, size = w.DWORD(), w.DWORD()
            ok = advapi.GetTokenInformation(handle, cls, c.byref(value), c.sizeof(value), c.byref(size))
            result[name] = bool(value.value) if ok else None
            result["known"] = result["known"] and bool(ok)
    finally:
        if not kernel.CloseHandle(handle):
            result.update(known=False, token_handle_close_failed=True)
    return result


def token_metadata():
    try:
        return _read_token_metadata()
    except Exception as error:
        return {"known": False, "error_type": type(error).__name__}


def ordinary_token(value):
    return (value.get("known") is True and all(value.get(k) is False for k in
                                             ("app_container", "elevated", "ui_access")))


class OwnedDiagnosticPort(native.WindowsClickPort):
    """Observe the real integrated guards; add only a bounded owned-test down."""
    def __init__(self, observer):
        self.audit = deque(maxlen=128)
        self.audit_lock = threading.Lock()
        self.release_samples = {}
        self.hold_raw_return = None
        self.hold_attempted = False
        self.open_input_precheck = {}
        self.mouse_tag_records = deque(maxlen=16)
        self.mouse_tag_total = 0
        self.first_foreign_mouse_tag = None
        self.mouse_tag_lock = threading.Lock()
        self.tag_fingerprint_key = secrets.token_bytes(32)  # Private per-port salt, never serialized.
        super().__init__(observer)
        self.created_token = self.token

    def _diagnostic_mouse_tag(self, message, flags, expected, observed):
        # Called AFTER the unchanged foreign-input stop. Copy scalars only;
        # hash/format off the hook thread, and never collect pointer coordinates.
        record = (message, flags, expected, observed, time.monotonic())
        with self.mouse_tag_lock:
            self.mouse_tag_total += 1
            if self.first_foreign_mouse_tag is None and not (flags & 1 and observed == expected):
                self.first_foreign_mouse_tag = record
            self.mouse_tag_records.append(record)

    def ownership_snapshot(self):
        # Called after guard cleanup by the report path. Evidence cannot authorize input.
        bits = c.sizeof(c.c_void_p) * 8
        # Cleanup can be incomplete. Copy a coherent bounded snapshot even when
        # the hook thread remains alive; never format/hash while holding its lock.
        with self.mouse_tag_lock:
            records = tuple(self.mouse_tag_records)
            first_foreign = self.first_foreign_mouse_tag
            total = self.mouse_tag_total
            created_token, current_token = self.created_token, self.token
        def summarize(record):
            message, flags, expected, observed, at = record
            return {"message": message, "flags": flags, "at": at,
                    "injected": bool(flags & 1), "lower_integrity_injected": bool(flags & 2),
                    "matches_created_token": expected == created_token,
                    **describe_mouse_tag(expected, observed, bits, self.tag_fingerprint_key)}
        return {"revision": "full-width-mouse-tags/1", "layout": describe_native_layout(self),
                "token_generation": native.INPUT_TAG_GENERATION,
                "token_unchanged_since_creation": current_token == created_token,
                "created_token_bits": created_token.bit_length(),
                "mouse_events_seen": total,
                "trace_dropped": max(0, total - len(records)),
                "first_foreign_mouse": summarize(first_foreign) if first_foreign else None,
                "mouse_trace": [summarize(record) for record in records]}

    def open(self, stop):
        if not ordinary_token(token_metadata()):
            raise native.NativeUnavailable("ordinary_nonadmin_noncontainer_diagnostic_required")
        held = held_input_categories(self.user.GetAsyncKeyState)
        self.open_input_precheck = {"held_categories": held, "checked_at": time.monotonic()}
        if held:
            raise native.NativeUnavailable("preexisting_held_input")
        try:
            super().open(stop)  # Keep the broker's independent, final high-bit refusal.
        except native.NativeUnavailable as error:
            if str(error) == "preexisting_held_input":
                # A later sample is not proof of the exact key that triggered the guard.
                self.open_input_precheck["broker_refused_after_clear_sample"] = True
                self.open_input_precheck["held_categories_after_refusal"] = held_input_categories(self.user.GetAsyncKeyState)
            raise

    def _diagnostic_signal(self, kind, message, flags=0, detail=0):
        # Never record typed text, arbitrary key values, pointer paths or screenshots.
        if kind == "mouse" and message not in (0x0201, 0x0202):
            return
        names = {0x78: "F9", 0xA1: "RightShift", 0x11: "Ctrl", 0xA2: "Ctrl", 0xA3: "Ctrl",
                 0x12: "Alt", 0xA4: "Alt", 0xA5: "Alt"}
        item = {"kind": kind, "message": message, "at": time.monotonic()}
        if kind == "keyboard":
            item.update(key=names.get(detail, "other"), injected=bool(flags & 0x10))
        elif kind == "mouse":
            item.update(own_token=bool(detail), injected=bool(flags & 1))
        elif kind == "hotkey":
            item.update(id=message, modifiers=detail & 0xFFFF, vk=(detail >> 16) & 0xFFFF)
        with self.audit_lock:
            self.audit.append(item)

    def audit_snapshot(self):
        with self.audit_lock:
            return list(self.audit)

    def release_owned(self):
        result = super().release_owned()  # Exercise the integrated release, unchanged.
        count = self.owned_release_attempt_count
        if count:
            with self.audit_lock:
                if count not in self.release_samples:
                    try:
                        sample = {"right_shift_down": bool(self.user.GetAsyncKeyState(0xA1) & 0x8000),
                                  "left_button_down": bool(self.user.GetAsyncKeyState(1) & 0x8000)}
                    except Exception as error:
                        sample = {"sample_error": type(error).__name__}
                    self.release_samples[count] = {"at": time.monotonic(), "raw_return": self.owned_release_last_raw_return,
                                                   "release_completed_at": self.owned_release_completed_at, **sample}
        return result

    def hold_owned_left_once(self, evidence, permit):
        self._require_owner()
        if self.hold_attempted:
            raise native.NativeUnavailable("owned_hold_one_attempt_only")
        self.hold_attempted = True
        binding = evidence.binding
        if evidence.context != "self_owned_test" or binding.pid != os.getpid() or not self.guard_healthy():
            raise native.NativeUnavailable("owned_hold_scope_or_guard_invalid")
        x, y = binding.screen_x + evidence.x, binding.screen_y + evidence.y
        left, top, width, height = [self.user.GetSystemMetrics(i) for i in (76, 77, 78, 79)]
        if (width <= 1 or height <= 1 or not 0 <= evidence.x < binding.width
                or not 0 <= evidence.y < binding.height
                or not left <= x < left + width or not top <= y < top + height):
            raise native.NativeUnavailable("owned_hold_point_invalid")
        events = (self.Input * 2)()
        for event in events:
            event.type, event.mi.dwExtraInfo = 0, self.token
        events[0].mi.dx = round((x - left) * 65535 / (width - 1))
        events[0].mi.dy = round((y - top) * 65535 / (height - 1))
        events[0].mi.dwFlags, events[1].mi.dwFlags = 0xC001, 0x0002
        with self.ledger_lock:
            pid = w.DWORD()
            if (not self.user.GetWindowThreadProcessId(binding.hwnd, c.byref(pid)) or pid.value != os.getpid()
                    or self.foreground() != binding.hwnd
                    or int(self.user.GetAncestor(self.user.WindowFromPoint(w.POINT(x, y)), 2) or 0) != binding.hwnd
                    or any(self.user.GetAsyncKeyState(code) & 0x8000 for code in range(1, 256)) or not permit()):
                raise native.NativeUnavailable("owned_hold_final_guard_rejected")
            self.held, self.submission_outcome = True, "uncertain"
            try:
                sent = int(self.user.SendInput(2, events, c.sizeof(self.Input)))
            except BaseException:
                raise  # Retain possibly-held ownership for integrated cleanup.
            self.hold_raw_return = self.submitted_event_count = sent
            self.held = sent == 2
            self.submission_outcome = "owned_down_submitted" if sent == 2 else "incomplete_batch"
        if sent != 2:
            self.release_owned()
            raise native.NativeUnavailable("owned_hold_incomplete:" + str(sent))


class OwnedHoldBroker(native.SingleClickBroker):
    """Test-only split submission; inherited deadline/watchdog/stop/cleanup stay live."""
    def hold_once(self):
        self._require_owner()
        if self.port is None or self.deadline is None:
            raise native.NativeUnavailable("not_armed")
        with self.lock:
            if self.attempted:
                raise native.NativeUnavailable("one_action_budget_exhausted")
            self.attempted = True
        try:
            self._check()
            def permit():
                try:
                    self._check()
                    return not self.stopped.is_set()
                except Exception as error:
                    self.stop(str(error))
                    return False
            self.port.hold_owned_left_once(self.evidence, permit)
            self.sent, self.submission_outcome = True, self.port.submission_outcome
        except BaseException:
            self.submission_outcome = self.port.submission_outcome
            self.stop("owned_hold_failed_or_revoked")
            self._release_owned()
            raise
        # Do not mark completion. The inherited watchdog releases on the first
        # stop signal or deadline; the operator never sends a programmatic key.


def phase_passes(name, row):
    """Strict report acceptance, independent of UI and native receipts alone."""
    if row.get("explicit_confirmation") is not True or row.get("cleanup_confirmed") is not True:
        return False
    downs, ups = row.get("target_downs"), row.get("target_ups")
    if type(downs) is not int or type(ups) is not int:
        return False
    if name in ("deadline", "focus"):
        return (row.get("attempt_rejected") is True and row.get("sent") is False
                and downs == ups == 0 and row.get("stop_expected") is True
                and row.get("submission_outcome") == "not_attempted"
                and row.get("raw_return") is None and row.get("release_attempts") == 0
                and (name != "focus" or row.get("focus_transition_verified") is True))
    if name == "click":
        return (row.get("raw_return") == 3 and row.get("sent") is True and downs == ups == 1
                and row.get("submission_outcome") == "complete_batch"
                and row.get("own_down_up_hook_pair") is True
                and row.get("stop_reason") == "one_action_completed")
    common = (row.get("raw_return") == 2 and row.get("owned_down_delivered_before_trigger") is True
              and row.get("sent") is True and row.get("submission_outcome") == "owned_down_submitted"
              and downs == ups == 1 and row.get("release_attempts") == 1
              and row.get("release_raw_return") == 1 and row.get("own_down_up_hook_pair") is True
              and row.get("left_button_down_after_release") is False
              and row.get("second_attempt_rejected") is True
              and row.get("stop_reason") == "user_or_foreign_keyboard_input"
              and row.get("physical_trigger_before_stop") is True
              and type(row.get("stop_to_release_ms")) in (int, float)
              and 0 <= row["stop_to_release_ms"] <= 250
              and type(row.get("stop_to_widget_up_ms")) in (int, float)
              and 0 <= row["stop_to_widget_up_ms"] <= 250)
    if not common:
        return False
    if name == "emergency":
        return (row.get("physical_f9_down") is True and row.get("registered_hotkey_received") is True
                and row.get("physical_f9_up") is True and row.get("emergency_keys_released") is True)
    return (name == "owned_release" and row.get("physical_right_shift_down") is True
            and row.get("right_shift_down_after_release") is True
            and row.get("right_shift_preserved_100ms") is True
            and row.get("right_shift_released_early") is False
            and row.get("physical_right_shift_up_after_prompt") is True)


def save_report(output, result):
    """Atomically replace a private checkpoint; failure must not skip cleanup."""
    temporary = output.with_suffix(".tmp")
    temporary.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(output)


def chinese_prompt(value):
    """Keep the current Chinese instruction; English remains in source/report data."""
    lines = []
    for line in str(value).splitlines():
        if not any("\u4e00" <= ch <= "\u9fff" for ch in line):
            continue
        # Bilingual headings use this explicit separator; do not touch key names.
        import re
        line = re.sub(r" / [A-Za-z].*", "", line)
        lines.append(line)
    return "\n".join(lines) or str(value)


class Suite:
    def __init__(self, result, output):
        import tkinter as tk
        from tkinter import font as tkfont
        self.tk, self.result, self.output = tk, result, output
        self.root = tk.Tk()
        self.result["window_created"] = True
        self.title = "MaaWXQ 自建窗口检查 " + str(os.getpid())
        self.root.title(self.title)
        self.root.configure(bg="#f2f5fa")
        # Respect Tk/Windows' current DPI; point fonts scale naturally. No OS setting changes.
        scale = max(1.0, self.root.winfo_fpixels("1i") / 96.0)
        screen_w, screen_h = self.root.winfo_screenwidth(), self.root.winfo_screenheight()
        width, height = min(int(1000 * scale), int(screen_w * .90)), min(int(850 * scale), int(screen_h * .88))
        self.root.geometry(f"{width}x{height}+{max(0,(screen_w-width)//2)}+{max(0,(screen_h-height)//2-20)}")
        self.root.minsize(min(width, int(780*scale)), min(height, int(680*scale)))
        self.root.resizable(True, True)
        family = "Microsoft YaHei UI" if "Microsoft YaHei UI" in tkfont.families(self.root) else "Microsoft YaHei"
        compact = height / scale < 730
        body_size, status_size = (12, 17) if compact else (14, 20)
        self.root.option_add("*Font", (family, body_size))
        self.result["ui_layout"] = {"width": width, "height": height, "tk_scale": float(self.root.tk.call("tk", "scaling")),
                                   "dpi": self.root.winfo_fpixels("1i"), "font": family, "compact": compact}
        self.index, self.active, self.secondary = 0, None, None
        self.brokers, self.events = [], []
        self.ending = False
        self.auto_group_consent = None
        self.readiness, self.input_probe = None, None
        self.confirm = tk.BooleanVar(value=False)
        class DisplayVar(tk.StringVar):
            def set(self, value):
                super().set(chinese_prompt(value))
        self.heading, self.instructions, self.status = DisplayVar(), DisplayVar(), DisplayVar()
        panel = tk.Frame(self.root, bg="#f2f5fa")
        panel.pack(fill="both", expand=True, padx=24, pady=16)
        tk.Label(panel, text="自建窗口检查", font=(family, 24, "bold"), bg="#f2f5fa", fg="#11213b", anchor="w").pack(fill="x")
        self.heading_label = tk.Label(panel, textvariable=self.heading, font=(family, body_size), bg="#f2f5fa", fg="#506176", justify="left", anchor="w")
        self.heading_label.pack(fill="x", pady=(2,10))
        self.status_label = tk.Label(panel, textvariable=self.status, font=(family, status_size, "bold"), bg="#ffffff", fg="#102b4d", justify="left", anchor="w", padx=18, pady=18)
        self.status_label.pack(fill="x", pady=(0,10))
        self.instructions_label = tk.Label(panel, textvariable=self.instructions, font=(family, body_size), bg="#f2f5fa", fg="#42556e", justify="left", anchor="w")
        self.instructions_label.pack(fill="x", pady=(0,8))
        self.check = tk.Checkbutton(panel, text="我同意只检查本程序自己的窗口", variable=self.confirm, bg="#f2f5fa", activebackground="#f2f5fa", anchor="w", justify="left")
        self.check.pack(fill="x", pady=(0,6))
        self.run_button = tk.Button(panel, text="开始自动检查", command=self.confirm_phase, font=(family, body_size+3, "bold"), bg="#1764d8", fg="white", activebackground="#0d4fae", activeforeground="white", disabledforeground="#c3cddd", relief="flat", padx=16, pady=10)
        self.run_button.pack(fill="x", pady=(0,10))
        self.target = tk.Label(panel, text="蓝色测试区 · 已松开（无需点击这里）", bg="#dbeafe", fg="#174a7b", height=2,
                               relief="flat", takefocus=True, font=(family, body_size))
        self.target.pack(fill="x", pady=(0,8))
        self.target.bind("<ButtonPress-1>", lambda e: self.target_event("down"))
        self.target.bind("<ButtonRelease-1>", lambda e: self.target_event("up"))
        bottom = tk.Frame(panel, bg="#f2f5fa")
        bottom.pack(fill="x", side="bottom")
        self.details_frame = tk.Frame(panel, bg="#f2f5fa")
        self.details = tk.Text(self.details_frame, height=5, font=("Consolas", 10), wrap="word", state="disabled")
        self.details.pack(fill="both", expand=True)
        self.details_visible = False
        def toggle_details():
            self.details_visible = not self.details_visible
            if self.details_visible:
                self.details.configure(state="normal")
                self.details.delete("1.0", "end")
                self.details.insert("1.0", "报告位置：" + str(self.output) + "\n" + json.dumps(self.result, ensure_ascii=False, indent=2))
                self.details.configure(state="disabled")
                self.details_frame.pack(fill="both", expand=True)
            else:
                self.details_frame.pack_forget()
            self.details_button.configure(text="收起技术记录" if self.details_visible else "查看技术记录")
        self.details_button = tk.Button(bottom, text="查看技术记录", command=toggle_details, relief="flat", bg="#f2f5fa", fg="#42556e")
        self.details_button.pack(side="left")
        self.stop_button = tk.Button(bottom, text="停止并保存", command=lambda: self.finish("operator_stopped"), bg="#fff1f0", fg="#a52e22", relief="flat", padx=14, pady=6)
        self.stop_button.pack(side="right")
        def fit_text(event):
            if event.widget is panel:
                wrap = max(320, event.width - 40)
                for widget in (self.heading_label, self.status_label, self.instructions_label, self.check):
                    widget.configure(wraplength=wrap)
        panel.bind("<Configure>", fit_text)
        self.root.protocol("WM_DELETE_WINDOW", lambda: self.finish("operator_closed"))
        self.result["status"] = "awaiting_phase_confirmation"
        self.show_phase()

    def target_event(self, kind):
        if self.active is None:
            return
        self.events.append({"kind": kind, "at": time.monotonic(), "phase": PHASES[self.index][0]})
        events = self.phase_events()
        self.target.configure(text="蓝色测试区：" + ("已按下" if kind == "down" else "已松开") +
            "\n收到按下：" + str(sum(e["kind"] == "down" for e in events)) +
            " 次 / 松开：" + str(sum(e["kind"] == "up" for e in events)) + " 次")
        if not self.ending and kind == "down":
            name = PHASES[self.index][0]
            if name == "emergency":
                self.status.set("当前状态：蓝色区域已按下\n下一步：现在同时按 Ctrl+Alt+F9，然后松开这三个键。\n"
                                "需要你操作：现在按键；不要碰鼠标。\nNOW press Ctrl+Alt+F9 together, then release all three.")
            elif name == "owned_release":
                self.status.set("当前状态：蓝色区域已按下\n下一步：现在按住右侧 Shift，一直按住。\n"
                                "需要你操作：按住，等下一条松开提示；不要碰鼠标。\nNOW HOLD RIGHT Shift until told to release.")


    def save(self):
        save_report(self.output, self.result)

    def show_phase(self):
        if self.index == len(PHASES):
            self.finish("all_owned_window_phases_passed")
            return
        name, title, instructions = PHASES[self.index]
        passed_count = sum(row.get("status") == "passed" for row in self.result["phases"].values())
        self.heading.set("当前第 " + str(self.index + 1) + "/5 项｜已通过 " + str(passed_count) + " 项\n" + title)
        self.instructions.set(instructions if name not in AUTO_PHASES else
                              "程序只检查自己的蓝色区域，不操作游戏。随时可以点“停止”。\n"
                              "Only the owned blue target is tested. You can press Stop at any time.")
        self.target.configure(text="蓝色测试区 · 已松开（无需点击这里）")
        self.confirm.set(False)
        if name in AUTO_PHASES and self.auto_group_consent is not None:
            self.check.configure(state="disabled")
            self.run_button.configure(state="disabled")
            self.status.set("当前状态：准备下一项自动检查\n下一步：保持静止，程序会继续。\n需要你操作：不需要。\nAutomatic checks continue; keep still.")
            self.result["status"] = "automatic_group_next:" + name
            self.save()
            consent = self.auto_group_consent
            self.root.after(750, lambda: self.start_phase(consent))
            return
        self.check.configure(state="normal")
        self.run_button.configure(state="normal")
        if name in AUTO_PHASES:
            self.check.configure(text="我同意自动完成前三项检查（只操作本窗口）")
            self.run_button.configure(text="开始自动检查 · 只需点一次")
            self.result["status"] = "awaiting_automatic_group_confirmation"
            self.status.set("当前状态：尚未开始\n下一步：勾选下方确认框，点击“开始自动检查”。\n需要你操作：只需确认这一次，随后保持静止。\nApprove once, then keep still.")
        else:
            self.check.configure(text="我已看懂当前按键说明，准备好了")
            self.run_button.configure(text="我准备好了")
            self.result["status"] = "awaiting_phase_confirmation:" + name
            self.status.set("当前状态：等你准备好\n下一步：勾选确认框，点击“我准备好了”。\n需要你操作：现在只需确认，不要按测试键。\nConfirm readiness; do not press the test key yet.")
        self.save()

    def confirm_phase(self):
        if not self.confirm.get() or self.active is not None or self.ending:
            return
        name = PHASES[self.index][0]
        confirmed_at = datetime.now(timezone.utc).isoformat()
        if name in AUTO_PHASES:
            # One actual UI confirmation explicitly covers only these three phases.
            if self.index != 0 or self.auto_group_consent is not None:
                return
            consent = {"mode": "automatic_group", "phases": list(AUTO_PHASES),
                       "confirmed_at_utc": confirmed_at}
            self.auto_group_consent = consent
            self.result["automatic_group_consent"] = dict(consent)
        else:
            consent = {"mode": "individual_physical", "phases": [name],
                       "confirmed_at_utc": confirmed_at}
        self.start_phase(consent)

    def start_phase(self, consent):
        # Scheduled continuations cannot run after cancellation or overlap a phase.
        if self.ending or self.active is not None:
            return
        name = PHASES[self.index][0]
        if name not in consent.get("phases", ()):
            return
        if name in AUTO_PHASES:
            if consent is not self.auto_group_consent or consent.get("mode") != "automatic_group":
                return
        elif consent.get("mode") != "individual_physical":
            return
        try:
            self.check.configure(state="disabled")
            self.run_button.configure(state="disabled")
            self.active = {"explicit_confirmation": True,
                           "confirmation_mode": consent["mode"],
                           "confirmed_individually": consent["mode"] == "individual_physical",
                           "confirmed_at_utc": consent["confirmed_at_utc"],
                           "phase_started_at_utc": datetime.now(timezone.utc).isoformat(),
                           "status": "waiting_for_input_ready", "event_start": len(self.events)}
            self.result["phases"][name] = self.active
            self.result["status"] = "phase_prearm_wait:" + name
            self.readiness = InputReadinessGate(time.monotonic())
            self.active["input_readiness"] = self.readiness.report
            self.target.focus_set()  # Within the already-foreground owned window.
            self.status.set("当前状态：等待所有按键松开\n下一步：松开按键和鼠标，保持静止 1 秒。\n需要你操作：只需松开；现在不要按测试键。\nRelease all keys/buttons and keep still for 1 second.")
            self.save()
            self.root.update_idletasks()
            self.input_probe = PrearmInputProbe(self.root.winfo_id())
            phase = self.active
            self.root.after(PREARM_POLL_MS, lambda: self.poll_input_ready(phase))
        except BaseException as error:
            self.fail(error)

    def poll_input_ready(self, phase):
        if self.ending or self.active is not phase or phase.get("status") != "waiting_for_input_ready":
            return
        try:
            held, marker = self.input_probe.sample()
            decision = self.readiness.observe(held, marker, time.monotonic())
            record = self.readiness.report
            if decision == "timed_out":
                raise native.NativeUnavailable("prearm_input_readiness_timeout")
            if decision == "ready":
                phase["status"] = "arming"
                self.result["status"] = "phase_arming:" + PHASES[self.index][0]
                self.status.set("当前状态：检查正在运行\n下一步：等下一条提示。\n需要你操作：现在不需要。\nCheck running; wait for the next prompt.")
                self.save()
                self.begin_phase()
                return
            if held:
                detail = "当前状态：仍有键或鼠标按住\n下一步：松开所有按键与鼠标。\n需要你操作：只需松开，不要按测试键。"
            else:
                detail = "当前状态：已全部松开\n下一步：再保持静止 %.1f 秒。\n需要你操作：不需要。" % (
                    PREARM_QUIET_SECONDS - record["quiet_seconds"])
            self.status.set(detail + "\n等待剩余：%.1f 秒。" % record["remaining_seconds"])
            self.root.after(PREARM_POLL_MS, lambda: self.poll_input_ready(phase))
        except BaseException as error:
            self.fail(error)

    def evidence(self):
        rows = [row for row in find_windows(self.title) if row["pid"] == os.getpid() and row["title"] == self.title]
        if len(rows) != 1:
            raise native.NativeUnavailable("unique_owned_window_required")
        binding = native.Binding.from_observation(rows[0])
        user = c.WinDLL("user32", use_last_error=True)
        user.GetWindowRect.argtypes, user.GetWindowRect.restype = [w.HWND, c.POINTER(w.RECT)], w.BOOL
        user.SetThreadDpiAwarenessContext.argtypes, user.SetThreadDpiAwarenessContext.restype = [c.c_void_p], c.c_void_p
        previous = user.SetThreadDpiAwarenessContext(c.c_void_p(-4))
        if not previous:
            raise native.NativeUnavailable("owned_target_dpi_context_unavailable")
        try:
            rect = w.RECT()
            if not user.GetWindowRect(self.target.winfo_id(), c.byref(rect)):
                raise native.NativeUnavailable("owned_target_rect_unavailable")
            x, y = (rect.left + rect.right) // 2 - binding.screen_x, (rect.top + rect.bottom) // 2 - binding.screen_y
        finally:
            user.SetThreadDpiAwarenessContext(c.c_void_p(previous))
        return native.ClickEvidence(binding, time.monotonic(), x, y, "self_owned_test")

    def begin_phase(self):
        if self.ending:
            return
        name = PHASES[self.index][0]
        try:
            if self.active.get("status") != "arming" or self.readiness.report.get("status") != "ready":
                raise native.NativeUnavailable("input_readiness_required_before_arming")
            self.root.update_idletasks()
            hold = name in ("emergency", "owned_release")
            cls = OwnedHoldBroker if hold else native.SingleClickBroker
            limits = {"max_seconds": 4.0, "max_age": 5.0} if hold else {}
            if name == "deadline":
                limits = {"max_seconds": 0.20}
            evidence = self.evidence()
            # Layout/identity queries can take time. Recheck after those reads,
            # immediately before broker construction, rather than before them.
            held, marker = self.input_probe.sample()
            if self.readiness.observe(held, marker, time.monotonic()) != "ready":
                raise native.NativeUnavailable("input_changed_before_arming")
            broker = cls(evidence, observer=inspect_window, enabled=True, port_factory=OwnedDiagnosticPort, **limits)
            self.brokers.append(broker)
            self.active["broker_index"] = len(self.brokers) - 1
            broker.arm()
            self.result["status"] = "phase_running:" + name
            self.active["armed_at"] = time.monotonic()
            if name == "deadline":
                self.root.after(350, self.check_rejection)
            elif name == "click":
                self.active["receipt"] = broker.click_once()
                broker.close()
                self.root.after(120, self.complete_phase)
            elif name == "focus":
                self.focus_transition()
                self.root.after(160, self.check_rejection)
            else:
                broker.hold_once()
                self.active["hold_submitted_at"] = time.monotonic()
                self.status.set("当前状态：等待蓝色区域就绪\n下一步：等“现在按键”的提示。\n"
                                "需要你操作：暂时不需要，不要碰鼠标。\nWait for the NOW prompt; do not touch the mouse.")
                self.root.after(10, self.poll_hold)
        except BaseException as error:
            self.fail(error)

    def current_broker(self):
        return self.brokers[self.active["broker_index"]]

    def focus_transition(self):
        self.secondary = self.tk.Toplevel(self.root)
        self.secondary.withdraw()
        self.secondary.title("MaaWXQ Owned Focus Target / 自建焦点窗口 " + str(os.getpid()))
        self.secondary.geometry("360x160+940+100")
        self.tk.Label(self.secondary, text="本程序的第二个窗口：原目标必须拒绝输入。\nSecond owned window: the old target must reject input.", wraplength=320).pack(pady=30)
        self.secondary.deiconify()
        self.secondary.update_idletasks()
        user = c.WinDLL("user32", use_last_error=True)
        user.GetAncestor.argtypes, user.GetAncestor.restype = [w.HWND, w.UINT], w.HWND
        user.SetForegroundWindow.argtypes, user.SetForegroundWindow.restype = [w.HWND], w.BOOL
        self.active["focus_requested_at"] = time.monotonic()
        self.active["focus_target_hwnd"] = int(user.GetAncestor(self.secondary.winfo_id(), 2) or 0)
        self.active["focus_request_return"] = bool(user.SetForegroundWindow(self.active["focus_target_hwnd"]))

    def check_rejection(self):
        if self.ending:
            return
        try:
            broker = self.current_broker()
            self.active["attempt_rejected"] = False
            try:
                broker.click_once()
            except (native.NativeUnavailable, ValueError) as error:
                self.active.update(attempt_rejected=True, rejection=str(error))
            if PHASES[self.index][0] == "deadline":
                self.active["stop_expected"] = broker.stop_reason == "diagnostic_deadline_expired"
            else:
                observed = inspect_window(broker.evidence.binding.hwnd, os.getpid())
                target = self.active.get("focus_target_hwnd")
                owned = inspect_window(target, os.getpid()) if target else None
                self.active["focus_transition_verified"] = bool(owned and owned["pid"] == os.getpid()
                    and observed["desktop"]["foreground_hwnd"] == target)
                self.active["stop_expected"] = (broker.stopped.is_set() and
                    self.active["focus_transition_verified"] and
                    (broker.stop_reason == "complete_visible_foreground_identity_required"
                     or self.active.get("rejection") == "complete_visible_foreground_identity_required"))
            broker.close()
            self.root.after(80, self.complete_phase)
        except BaseException as error:
            self.fail(error)

    def phase_events(self):
        return self.events[self.active["event_start"]:]

    def poll_hold(self):
        if self.ending:
            return
        try:
            broker, row = self.current_broker(), self.active
            port, now = broker.port, time.monotonic()
            name = PHASES[self.index][0]
            if port.foreground() != broker.evidence.binding.hwnd:
                raise native.NativeUnavailable("owned_hold_target_lost_foreground")
            audit = port.audit_snapshot()
            physical_downs = [e for e in audit if e["kind"] == "keyboard" and not e["injected"]
                              and e["message"] in (0x100, 0x104)]
            trigger_key = "F9" if name == "emergency" else "RightShift"
            trigger = next((e for e in physical_downs if e["key"] == trigger_key), None)
            down = next((e for e in self.phase_events() if e["kind"] == "down"), None)
            stop_keys = ("Ctrl", "Alt", "F9") if name == "emergency" else ("RightShift",)
            first_trigger = next((e for e in physical_downs if e["key"] in stop_keys), None)
            if trigger:
                row["physical_f9_down" if name == "emergency" else "physical_right_shift_down"] = True
                row["owned_down_delivered_before_trigger"] = bool(down and first_trigger and down["at"] < first_trigger["at"])
            row["physical_trigger_before_stop"] = bool(broker.stop_monotonic is not None and any(
                e["key"] in stop_keys and e["at"] <= broker.stop_monotonic for e in physical_downs))
            row["registered_hotkey_received"] = any(e["kind"] == "hotkey" and e["id"] == 0x5751
                and e["modifiers"] == 3 and e["vk"] == 0x78 for e in audit)
            if broker.stopped.is_set() and not port.held and port.owned_release_last_raw_return == 1:
                if name == "emergency" and trigger and row["registered_hotkey_received"]:
                    row["physical_f9_up"] = any(e["kind"] == "keyboard" and e["key"] == "F9"
                        and not e["injected"] and e["message"] in (0x101, 0x105)
                        and e["at"] > trigger["at"] for e in audit)
                    row["emergency_keys_released"] = not any(port.user.GetAsyncKeyState(code) & 0x8000
                                                              for code in (0x11, 0x12, 0x78))
                    if row["physical_f9_up"] and row["emergency_keys_released"]:
                        broker.close()
                        self.root.after(80, self.complete_phase)
                        return
                if name == "owned_release" and trigger:
                    shift_down = bool(port.user.GetAsyncKeyState(0xA1) & 0x8000)
                    sample = port.release_samples.get(1, {})
                    early_ups = [e for e in audit if e["kind"] == "keyboard" and e["key"] == "RightShift"
                                 and e["message"] in (0x101, 0x105) and e["at"] >= trigger["at"]
                                 and e["at"] < row.get("release_shift_prompt_at", float("inf"))]
                    row["right_shift_released_early"] = row.get("right_shift_released_early", False) or bool(early_ups)
                    if shift_down and sample.get("right_shift_down") is True:
                        row.setdefault("shift_preserved_since", now)
                        if now - row["shift_preserved_since"] >= 0.10:
                            row["right_shift_preserved_100ms"] = True
                            if "release_shift_prompt_at" not in row:
                                self.status.set("当前状态：可以松开了\n下一步：现在松开右 Shift。\n需要你操作：松开右 Shift；不要碰鼠标。\nRELEASE RIGHT SHIFT NOW; do not touch the mouse.")
                                self.root.update_idletasks()
                                row["release_shift_prompt_at"] = time.monotonic()
                    elif "release_shift_prompt_at" not in row:
                        row.pop("shift_preserved_since", None)
                    ups = [e for e in audit if e["kind"] == "keyboard" and e["key"] == "RightShift"
                           and e["message"] in (0x101, 0x105) and not e["injected"]]
                    row["physical_right_shift_up_after_prompt"] = any(e["at"] >= row.get("release_shift_prompt_at", float("inf")) for e in ups)
                    if row.get("right_shift_preserved_100ms") and row["physical_right_shift_up_after_prompt"] and not shift_down:
                        broker.close()
                        self.root.after(80, self.complete_phase)
                        return
            # The guard remains registered briefly after first revocation to
            # observe WM_HOTKEY/key-up, with no rearm or further submission.
            if now >= broker.deadline + 2.0:
                raise native.NativeUnavailable("operator_trigger_or_release_evidence_timeout")
            self.root.after(10, self.poll_hold)
        except BaseException as error:
            self.fail(error)

    def broker_record(self, broker):
        port = broker.port
        return {"sent": broker.sent, "stop_reason": broker.stop_reason, "stop_at": broker.stop_monotonic,
                "submission_outcome": broker.submission_outcome,
                "raw_return": getattr(port, "submitted_event_count", None),
                "cleanup_confirmed": bool(broker.release_confirmed and broker.closed.is_set()
                    and not broker.cleanup_errors and (port is None or (
                    not port.cleanup_errors and not port.held and port.closed.is_set()
                    and not port.process_lease_owned and port.mutex is None
                    and (port.thread is None or not port.thread.is_alive())))),
                "cleanup_errors": list(broker.cleanup_errors) + list(port.cleanup_errors if port else []),
                "audit": port.audit_snapshot() if port else [],
                "open_input_precheck": dict(port.open_input_precheck) if port else {},
                "ownership_diagnostics": port.ownership_snapshot() if port else {},
                "release_samples": dict(port.release_samples) if port else {},
                "release_attempts": getattr(port, "owned_release_attempt_count", 0),
                "release_raw_return": getattr(port, "owned_release_last_raw_return", None)}

    def complete_phase(self):
        if self.ending:
            return
        try:
            name, row, broker = PHASES[self.index][0], self.active, self.current_broker()
            if isinstance(broker, OwnedHoldBroker):
                try:
                    broker.hold_once()
                except native.NativeUnavailable as error:
                    row["second_attempt_rejected"] = str(error) == "one_action_budget_exhausted"
                    row["second_attempt_rejection"] = str(error)
            row.update(self.broker_record(broker))
            events = self.phase_events()
            row["target_downs"] = sum(e["kind"] == "down" for e in events)
            row["target_ups"] = sum(e["kind"] == "up" for e in events)
            row["target_events"] = events
            own = [e for e in row["audit"] if e["kind"] == "mouse" and e["own_token"] and e["injected"]]
            row["own_down_up_hook_pair"] = ([e["message"] for e in own] == [0x201, 0x202])
            sample = broker.port.release_samples.get(1, {})
            row["right_shift_down_after_release"] = sample.get("right_shift_down")
            row["left_button_down_after_release"] = sample.get("left_button_down")
            if sample.get("release_completed_at") is not None and broker.stop_monotonic is not None:
                row["stop_to_release_ms"] = 1000 * (sample["release_completed_at"] - broker.stop_monotonic)
            target_up = next((e for e in events if e["kind"] == "up"), None)
            if target_up is not None and broker.stop_monotonic is not None:
                row["stop_to_widget_up_ms"] = 1000 * (target_up["at"] - broker.stop_monotonic)
            row["status"] = "passed" if phase_passes(name, row) else "failed_evidence"
            self.save()
            if row["status"] != "passed":
                self.finish("phase_failed:" + name)
                return
            if self.secondary:
                self.secondary.destroy()
                self.secondary = None
            self.active = None
            self.index += 1
            self.show_phase()  # Always returns to an unchecked confirmation.
        except BaseException as error:
            self.fail(error)

    def fail(self, error):
        if self.active is not None:
            self.active.update(status="blocked_or_failed", error={"type": type(error).__name__, "message": str(error)})
        self.finish("native_stage_stopped")

    def finish(self, status):
        if self.ending:
            return
        self.ending = True
        for broker in self.brokers:
            try:
                broker.close()
            except BaseException as error:
                self.result.setdefault("harness_cleanup_errors", []).append(str(error))
        if self.active is not None and "broker_index" in self.active:
            self.active.update(self.broker_record(self.current_broker()))
        if self.active is not None and self.active.get("status") in ("waiting_for_input_ready", "arming", "running"):
            self.active["status"] = "interrupted"
        self.result.update(status=status, finished_at_utc=datetime.now(timezone.utc).isoformat(),
            all_phases_passed=all(self.result["phases"][key].get("status") == "passed" for key, _, _ in PHASES),
            broker_cleanup=[self.broker_record(b) for b in self.brokers])
        if self.result.get("harness_cleanup_errors") or any(not b["cleanup_confirmed"] for b in self.result["broker_cleanup"]):
            self.result["all_phases_passed"] = False
            self.result["status"] = "cleanup_incomplete_requires_attention"
        try:
            self.save()
            saved = True
        except Exception as error:
            saved = False
            self.result.update(all_phases_passed=False, report_write_error=type(error).__name__)
            if self.result["status"] != "cleanup_incomplete_requires_attention":
                self.result["status"] = "report_write_failed_after_cleanup"
        print(json.dumps(self.result, ensure_ascii=False, indent=2), flush=True)
        print(("Report: " if saved else "Report could not be saved: ") + str(self.output), flush=True)
        try:
            self.instructions.set(("报告已保存 / Report saved." if saved else "报告写入失败，请保留控制台 JSON / Report write failed; keep console JSON.")
                                  + "\n本次测试已结束，不会重试，也不会操作游戏。\nThis run has ended. No retry or game input.")
            self.status.set("当前状态：本次已结束\n下一步：等待结果分析；如果还按住键，请松开。\n需要你操作：不用再按测试键或重复点击。\nTest ended; no further test key presses.")
            if hasattr(self, "heading"):
                self.heading.set("全部检查通过 / All checks passed" if self.result["all_phases_passed"] else
                                 "本次未全部通过，已停止 / Check stopped")
            self.run_button.configure(state="disabled")
            self.check.configure(state="disabled")
            self.root.protocol("WM_DELETE_WINDOW", self.root.destroy)
        except self.tk.TclError:
            pass  # The window may already be destroyed; native cleanup/report ran.


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--check-only", action="store_true")
    mode.add_argument("--enable-once", action="store_true")
    args = parser.parse_args()
    output_dir = ROOT / "local" / "owned-window-diagnostic"
    output_dir.mkdir(parents=True, exist_ok=True)
    output = output_dir / ("owned-window-diagnostic-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ") + ".json")
    result = {"schema": "maawxq-owned-window-diagnostic/2", "readiness_revision": "bounded-release-and-quiet/1",
        "ownership_diagnostics_revision": "full-width-mouse-tags/1", "ui_revision": "chinese-current-step/2",
        "pid": os.getpid(), "status": "input_disabled",
        "window_created": False, "all_phases_passed": False, "target_scope": "current_process_owned_fixed_widgets",
        "game_input_count": 0, "game_gate_passed": False, "keyboard_injection_count": 0,
        "security_changes": 0, "privilege_changes": 0, "phases": {key: {"status": "not_run"} for key, _, _ in PHASES}}
    actual_path = Path(native.__file__).resolve()
    result["broker_sha256"] = hashlib.sha256(actual_path.read_bytes()).hexdigest()
    result["broker_canonical_sha256"] = hashlib.sha256(actual_path.read_text(encoding="utf-8").encode("utf-8")).hexdigest()
    result["diagnostic_canonical_sha256"] = hashlib.sha256(Path(__file__).read_text(encoding="utf-8").encode("utf-8")).hexdigest()
    if (actual_path != (ROOT / "backends" / "win32_single_click.py").resolve()
            or result["broker_canonical_sha256"] != EXPECTED_BROKER_CANONICAL_HASH):
        result["status"] = "reviewed_broker_source_mismatch"
    elif args.check_only or args.enable_once:
        result["runtime_token"] = token_metadata()
        result["status"] = "preflight_only" if ordinary_token(result["runtime_token"]) else "requires_normal_nonadmin_noncontainer_process"
        if args.enable_once and ordinary_token(result["runtime_token"]):
            suite = None
            try:
                suite = Suite(result, output)
                suite.root.mainloop()
            except BaseException as error:
                result["ui_error"] = {"type": type(error).__name__, "message": str(error)}
                if suite is None:
                    result["status"] = "window_setup_failed_before_arming"
                    save_report(output, result)
                    print(json.dumps(result, indent=2))
            finally:
                if suite is not None and not suite.ending:
                    suite.finish("ui_loop_ended")
            return 0 if result["all_phases_passed"] else 1
    save_report(output, result)
    print(json.dumps(result, indent=2))
    print("Report: " + str(output))
    return 2 if result["status"] in ("reviewed_broker_source_mismatch", "requires_normal_nonadmin_noncontainer_process") else 0


if __name__ == "__main__":
    raise SystemExit(main())
