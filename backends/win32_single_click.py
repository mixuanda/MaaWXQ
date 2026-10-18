"""Default-off, one-click foreground diagnostic. No child-session isolation.

Only explicit process-owned self-tests can arm; custom rooms are hard-blocked.
No keyboard typing, dragging, focus activation, cursor restoration, driver,
elevation or fallback.
Native behavior is unverified until exercised on a self-owned test window.
"""
from dataclasses import dataclass
import ctypes as c
from ctypes import wintypes as w
import math
import os
import secrets
import sys
import threading
import time


# Windows mutexes are recursive for their owning thread. This additional lease
# prevents two brokers on that same thread from both acquiring native ownership.
_PROCESS_INPUT_LEASE = threading.Lock()
_INCOMPLETE_NATIVE_CLEANUP = []  # Keep callback references alive on failed teardown.


class NativeUnavailable(RuntimeError):
    pass


# An opaque correlation tag, NOT authentication. This machine's mouse path
# returns only 32 bits even though the API fields retain their ULONG_PTR ABI.
# Allocate the complete tag in that range; NEVER mask a received tag to match.
INPUT_TAG_GENERATION = "uniform_nonzero_uint32_no_process_reuse/1"
_INPUT_TAG_LOCK = threading.Lock()
_USED_INPUT_TAGS = set()  # Keep retired tags too, so delayed events cannot reuse one.
_INPUT_TAG_LIMIT = 65536  # Bound retained memory; exhaustion refuses a new port.


def _new_input_tag():
    """Unique per broker in this process lifetime; no cross-process guarantee."""
    with _INPUT_TAG_LOCK:
        if len(_USED_INPUT_TAGS) >= _INPUT_TAG_LIMIT:
            raise NativeUnavailable("input_tag_budget_exhausted")
        for _ in range(32):  # Broken/repeating entropy must not hang or reuse a tag.
            value = secrets.randbits(32)
            if value != 0 and value not in _USED_INPUT_TAGS:
                _USED_INPUT_TAGS.add(value)
                return value
        raise NativeUnavailable("unique_input_tag_unavailable")


@dataclass(frozen=True)
class Binding:
    hwnd: int
    pid: int
    process_started_at: str
    class_name: str
    geometry_version: str
    width: int
    height: int
    screen_x: int
    screen_y: int

    def __post_init__(self):
        if (any(type(x) is not int or x <= 0 for x in (self.hwnd, self.pid, self.width, self.height))
                or any(type(x) is not int for x in (self.screen_x, self.screen_y))
                or any(not isinstance(x, str) or not x.strip() for x in
                       (self.process_started_at, self.class_name, self.geometry_version))):
            raise ValueError("invalid_binding")

    @classmethod
    def from_observation(cls, value):
        if (value.get("visible") is not True or value.get("minimized") is not False
                or type(value["desktop"]["foreground_hwnd"]) is not int
                or value["desktop"]["foreground_hwnd"] != value["hwnd"]):
            raise ValueError("complete_visible_foreground_identity_required")
        result = cls(value["hwnd"], value["pid"], value["process_started_at"], value["class_name"],
                     value["geometry_version"], value["client"]["width"], value["client"]["height"],
                     value["client"]["screen_x"], value["client"]["screen_y"])
        return result


@dataclass(frozen=True)
class ClickEvidence:
    binding: Binding
    observed_monotonic: float
    x: int
    y: int
    context: str = "unknown"
    no_other_humans_verified: bool = False
    operation: str = "unknown"


class WindowsClickPort:
    """Ordinary user-mode APIs; local hooks observe takeover without suppressing it."""
    def __init__(self, observer):
        if sys.platform != "win32":
            raise NativeUnavailable("windows_required")
        self.observe = observer
        self.user = c.WinDLL("user32", use_last_error=True)
        self.kernel = c.WinDLL("kernel32", use_last_error=True)
        self.token = _new_input_tag()
        self.ready = threading.Event()
        self.closed = threading.Event()
        self.error = None
        self.thread_id = None
        self.mutex = None
        self.thread = None
        self.held = False
        self.submission_outcome = "not_attempted"
        self.submitted_event_count = None
        self.ledger_lock = threading.Lock()
        self.cleanup_errors = []
        self.owner_thread = None
        self.open_attempted = False
        self.process_lease_owned = False
        self.mutex_owned = False
        self.owned_release_attempt_count = 0
        self.owned_release_last_raw_return = None
        self.owned_release_completed_at = None
        self._configure()

    def _configure(self):
        ptr = c.c_size_t
        signed_ptr = c.c_ssize_t
        self.HOOKPROC = c.WINFUNCTYPE(signed_ptr, c.c_int, ptr, signed_ptr)

        class Mouse(c.Structure):
            _fields_ = [("dx", w.LONG), ("dy", w.LONG), ("mouseData", w.DWORD),
                        ("dwFlags", w.DWORD), ("time", w.DWORD), ("dwExtraInfo", ptr)]

        class Keyboard(c.Structure):
            _fields_ = [("vk", w.WORD), ("scan", w.WORD), ("flags", w.DWORD),
                        ("time", w.DWORD), ("extra", ptr)]

        class Hardware(c.Structure):
            _fields_ = [("message", w.DWORD), ("low", w.WORD), ("high", w.WORD)]

        class Payload(c.Union):
            _fields_ = [("mi", Mouse), ("ki", Keyboard), ("hi", Hardware)]

        class Input(c.Structure):
            _anonymous_ = ("payload",)
            _fields_ = [("type", w.DWORD), ("payload", Payload)]

        class MouseHook(c.Structure):
            _fields_ = [("pt", w.POINT), ("data", w.DWORD), ("flags", w.DWORD),
                        ("time", w.DWORD), ("extra", ptr)]

        class KeyboardHook(c.Structure):
            _fields_ = [("vk", w.DWORD), ("scan", w.DWORD), ("flags", w.DWORD),
                        ("time", w.DWORD), ("extra", ptr)]

        class LastInput(c.Structure):
            _fields_ = [("cbSize", w.UINT), ("dwTime", w.DWORD)]

        self.Input, self.Mouse, self.MouseHook, self.KeyboardHook = Input, Mouse, MouseHook, KeyboardHook
        self.LastInput = LastInput
        if c.sizeof(Input) != (40 if c.sizeof(c.c_void_p) == 8 else 28):
            raise NativeUnavailable("unexpected_input_structure_size")
        signatures = {
            "GetForegroundWindow": ([], w.HWND),
            "GetWindowThreadProcessId": ([w.HWND, c.POINTER(w.DWORD)], w.DWORD),
            "WindowFromPoint": ([w.POINT], w.HWND),
            "GetAncestor": ([w.HWND, w.UINT], w.HWND),
            "GetLastInputInfo": ([c.POINTER(LastInput)], w.BOOL),
            "GetSystemMetrics": ([c.c_int], c.c_int),
            "GetAsyncKeyState": ([c.c_int], c.c_short),
            "SendInput": ([w.UINT, c.POINTER(Input), c.c_int], w.UINT),
            "SetWindowsHookExW": ([c.c_int, self.HOOKPROC, w.HINSTANCE, w.DWORD], w.HANDLE),
            "CallNextHookEx": ([w.HANDLE, c.c_int, ptr, signed_ptr], signed_ptr),
            "UnhookWindowsHookEx": ([w.HANDLE], w.BOOL),
            "RegisterHotKey": ([w.HWND, c.c_int, w.UINT, w.UINT], w.BOOL),
            "UnregisterHotKey": ([w.HWND, c.c_int], w.BOOL),
            "GetMessageW": ([c.POINTER(w.MSG), w.HWND, w.UINT, w.UINT], c.c_int),
            "PostThreadMessageW": ([w.DWORD, w.UINT, ptr, signed_ptr], w.BOOL),
        }
        for name, (arguments, result) in signatures.items():
            function = getattr(self.user, name)
            function.argtypes, function.restype = arguments, result
        for name, arguments, result in (
            ("GetModuleHandleW", [w.LPCWSTR], w.HMODULE),
            ("GetCurrentThreadId", [], w.DWORD),
            ("CreateMutexW", [c.c_void_p, w.BOOL, w.LPCWSTR], w.HANDLE),
            ("WaitForSingleObject", [w.HANDLE, w.DWORD], w.DWORD),
            ("ReleaseMutex", [w.HANDLE], w.BOOL),
            ("CloseHandle", [w.HANDLE], w.BOOL),
        ):
            function = getattr(self.kernel, name)
            function.argtypes, function.restype = arguments, result

    def _diagnostic_signal(self, kind, message, flags=0, detail=0):
        """Optional owned-test observation; default does not record any input."""

    def _diagnostic_mouse_tag(self, message, flags, expected, observed):
        """Passive owned-test evidence only; never an input-acceptance predicate."""

    def foreground(self):
        return int(self.user.GetForegroundWindow() or 0)

    def _require_owner(self):
        if self.owner_thread is not None and self.owner_thread != threading.get_ident():
            raise NativeUnavailable("native_owner_thread_required")

    def _cleanup_error(self, reason):
        if reason not in self.cleanup_errors:
            self.cleanup_errors.append(reason)

    def open(self, stop):
        self._require_owner()
        if self.open_attempted or self.closed.is_set():
            raise NativeUnavailable("native_port_cannot_reopen")
        self.owner_thread = threading.get_ident()
        self.open_attempted = True
        # No broad key-up: refuse while any physical key/button is already held.
        if any(self.user.GetAsyncKeyState(code) & 0x8000 for code in range(1, 256)):
            raise NativeUnavailable("preexisting_held_input")
        if not _PROCESS_INPUT_LEASE.acquire(blocking=False):
            raise NativeUnavailable("another_process_local_input_owner")
        self.process_lease_owned = True
        self.mutex = self.kernel.CreateMutexW(None, False, "Local\\MaaWXQ.SingleClickBroker.v1")
        if not self.mutex:
            _PROCESS_INPUT_LEASE.release()
            self.process_lease_owned = False
            raise NativeUnavailable("input_mutex_unavailable:" + str(c.get_last_error()))
        if self.kernel.WaitForSingleObject(self.mutex, 0) not in (0, 0x80):
            self.close()
            raise NativeUnavailable("another_input_owner")
        self.mutex_owned = True

        def hook_loop():
            mouse_handle = keyboard_handle = None
            hotkey = False
            self.thread_id = self.kernel.GetCurrentThreadId()

            def mouse(code, message, address):
                try:
                    if code >= 0:
                        item = c.cast(address, c.POINTER(self.MouseHook)).contents
                        self._diagnostic_signal("mouse", int(message), int(item.flags),
                                                int(item.extra == self.token))
                        if not (item.flags & 1 and item.extra == self.token):
                            stop("user_or_foreign_mouse_input")
                        self._diagnostic_mouse_tag(int(message), int(item.flags), self.token, int(item.extra))
                except Exception:
                    self.error = "mouse_guard_callback_failed"
                    stop(self.error)
                return self.user.CallNextHookEx(None, code, message, address)

            def keyboard(code, message, address):
                try:
                    if code >= 0:
                        item = c.cast(address, c.POINTER(self.KeyboardHook)).contents
                        self._diagnostic_signal("keyboard", int(message), int(item.flags), int(item.vk))
                        if not (item.flags & 0x10 and item.extra == self.token):
                            stop("user_or_foreign_keyboard_input")
                except Exception:
                    self.error = "keyboard_guard_callback_failed"
                    stop(self.error)
                return self.user.CallNextHookEx(None, code, message, address)

            self.mouse_callback, self.keyboard_callback = self.HOOKPROC(mouse), self.HOOKPROC(keyboard)
            try:
                module = self.kernel.GetModuleHandleW(None)
                mouse_handle = self.user.SetWindowsHookExW(14, self.mouse_callback, module, 0)
                keyboard_handle = self.user.SetWindowsHookExW(13, self.keyboard_callback, module, 0)
                if not mouse_handle or not keyboard_handle:
                    raise NativeUnavailable("takeover_hook_registration_failed:" + str(c.get_last_error()))
                hotkey = bool(self.user.RegisterHotKey(None, 0x5751, 0x4003, 0x78))  # Ctrl+Alt+F9
                if not hotkey:
                    raise NativeUnavailable("emergency_hotkey_registration_failed:" + str(c.get_last_error()))
                self.ready.set()
                message = w.MSG()
                while not self.closed.is_set():
                    outcome = self.user.GetMessageW(c.byref(message), None, 0, 0)
                    if outcome <= 0:
                        stop("guard_message_loop_failed" if outcome < 0 else "guard_message_loop_ended")
                        break
                    if message.message == 0x0312:
                        self._diagnostic_signal("hotkey", int(message.wParam), 0, int(message.lParam))
                        stop("emergency_hotkey")
            except Exception as error:
                self.error = str(error)
                stop("native_guard_unavailable")
            finally:
                self.ready.set()
                for handle in (mouse_handle, keyboard_handle):
                    if handle:
                        try:
                            if not self.user.UnhookWindowsHookEx(handle):
                                self._cleanup_error("unhook_failed")
                        except Exception:
                            self._cleanup_error("unhook_failed")
                if hotkey:
                    try:
                        if not self.user.UnregisterHotKey(None, 0x5751):
                            self._cleanup_error("hotkey_unregister_failed")
                    except Exception:
                        self._cleanup_error("hotkey_unregister_failed")

        self.thread = threading.Thread(target=hook_loop, name="maawxq-input-guard", daemon=True)
        self.thread.start()
        if not self.ready.wait(1) or self.error:
            self.close()
            raise NativeUnavailable(self.error or "native_guard_start_timeout")
        self.activity_baseline = self.activity_marker()

    def activity_marker(self):
        value = self.LastInput()
        value.cbSize = c.sizeof(value)
        if not self.user.GetLastInputInfo(c.byref(value)):
            raise NativeUnavailable("last_input_query_failed")
        return int(value.dwTime)

    def user_activity_changed(self):
        return self.activity_marker() != self.activity_baseline

    def guard_healthy(self):
        return (self.thread is not None and self.thread.is_alive() and self.ready.is_set()
                and self.error is None and not self.closed.is_set())

    def click(self, hwnd, x, y, permit):
        self._require_owner()
        if not self.guard_healthy():
            raise NativeUnavailable("native_guard_not_healthy")
        left, top, width, height = [self.user.GetSystemMetrics(i) for i in (76, 77, 78, 79)]
        if width <= 1 or height <= 1 or not (left <= x < left + width and top <= y < top + height):
            raise NativeUnavailable("point_outside_virtual_desktop")
        absolute_x = round((x - left) * 65535 / (width - 1))
        absolute_y = round((y - top) * 65535 / (height - 1))
        events = (self.Input * 3)()
        for event in events:
            event.type = 0
            event.mi.dwExtraInfo = self.token
        events[0].mi.dx, events[0].mi.dy = absolute_x, absolute_y
        events[0].mi.dwFlags = 0xC001  # MOVE | ABSOLUTE | VIRTUALDESK
        events[1].mi.dwFlags, events[2].mi.dwFlags = 0x0002, 0x0004
        with self.ledger_lock:
            process = w.DWORD()
            if (not self.user.GetWindowThreadProcessId(hwnd, c.byref(process))
                    or process.value != os.getpid()):
                raise NativeUnavailable("native_self_owned_target_required")
            if (self.foreground() != hwnd
                    or int(self.user.GetAncestor(self.user.WindowFromPoint(w.POINT(x, y)), 2) or 0) != hwnd
                    or any(self.user.GetAsyncKeyState(code) & 0x8000 for code in range(1, 256))
                    or not permit()):
                raise NativeUnavailable("final_target_or_permission_changed")
            self.held = True  # Reserve ownership before irreversible submission.
            self.submission_outcome = "uncertain"
            try:
                sent = int(self.user.SendInput(3, events, c.sizeof(self.Input)))
            except BaseException:
                # Retain a visible, possibly held ledger entry for cleanup.
                raise
            self.held = sent == 2
            self.submitted_event_count = sent
            self.submission_outcome = "complete_batch" if sent == 3 else "incomplete_batch"
        if sent != 3:
            self.release_owned()
            raise NativeUnavailable("send_input_incomplete:" + str(sent))
        return sent

    def release_owned(self):
        with self.ledger_lock:
            if not self.held:
                return True
            event = self.Input()
            event.type, event.mi.dwFlags, event.mi.dwExtraInfo = 0, 0x0004, self.token
            self.owned_release_attempt_count += 1
            try:
                self.owned_release_last_raw_return = int(
                    self.user.SendInput(1, c.byref(event), c.sizeof(self.Input)))
                released = self.owned_release_last_raw_return == 1
            except Exception:
                self.owned_release_last_raw_return = None
                released = False
            if not released:
                self._cleanup_error("owned_button_release_failed")
                return False
            self.held = False
            self.owned_release_completed_at = time.monotonic()
            return True

    def close(self):
        self.closed.set()
        self._require_owner()
        try:
            released = self.release_owned()
        except BaseException:
            # Continue removing hooks/closing the guard even after cleanup fails.
            released = False
            self._cleanup_error("owned_button_release_exception")
        if self.thread_id and self.thread and self.thread.is_alive():
            try:
                if not self.user.PostThreadMessageW(self.thread_id, 0x0012, 0, 0):
                    self._cleanup_error("guard_quit_post_failed")
            except Exception:
                self._cleanup_error("guard_quit_post_failed")
        if self.thread and self.thread is not threading.current_thread():
            if self.thread.is_alive():
                self.thread.join(1)
            if self.thread.is_alive():
                self._cleanup_error("guard_thread_close_timeout")
                if self not in _INCOMPLETE_NATIVE_CLEANUP:
                    _INCOMPLETE_NATIVE_CLEANUP.append(self)
                return False  # Keep exclusivity while guard teardown is uncertain.
        if not released or any(x in self.cleanup_errors for x in ("unhook_failed", "hotkey_unregister_failed")):
            if self not in _INCOMPLETE_NATIVE_CLEANUP:
                _INCOMPLETE_NATIVE_CLEANUP.append(self)
            return False  # Keep ownership and the ledger available for inspection.
        if self.mutex:
            if self.mutex_owned:
                try:
                    unlocked = bool(self.kernel.ReleaseMutex(self.mutex))
                except Exception:
                    unlocked = False
                if not unlocked:
                    self._cleanup_error("mutex_release_failed")
                    return False
                self.mutex_owned = False
            try:
                closed = bool(self.kernel.CloseHandle(self.mutex))
            except Exception:
                closed = False
            if not closed:
                self._cleanup_error("mutex_handle_close_failed")
                return False
            self.mutex = None
        if self.process_lease_owned:
            _PROCESS_INPUT_LEASE.release()
            self.process_lease_owned = False
        if self in _INCOMPLETE_NATIVE_CLEANUP:
            _INCOMPLETE_NATIVE_CLEANUP.remove(self)
        return not self.cleanup_errors


class SingleClickBroker:
    """One bounded supervised diagnostic; construction alone never opens native APIs."""
    def __init__(self, evidence, *, observer, enabled=False, port_factory=WindowsClickPort,
                 clock=time.monotonic, max_age=2.0, max_seconds=2.0):
        if not isinstance(evidence, ClickEvidence):
            raise ValueError("typed_click_evidence_required")
        if (type(enabled) is not bool
                or any(type(x) not in (int, float) or not math.isfinite(x)
                       for x in (max_age, max_seconds, evidence.observed_monotonic))
                or not 0 < max_age <= 10 or not 0 < max_seconds <= 5):
            raise ValueError("invalid_diagnostic_limits")
        self.evidence, self.observer, self.enabled = evidence, observer, enabled
        self.port_factory, self.clock = port_factory, clock
        self.max_age, self.max_seconds = max_age, max_seconds
        self.port = None
        self.stopped = threading.Event()
        self.closed = threading.Event()
        self.lock = threading.Lock()
        self.stop_reason = None
        self.stop_monotonic = None
        self.deadline = None
        self.sent = False
        self.submission_outcome = "not_attempted"
        self.attempted = False
        self.watchdog = None
        self.release_confirmed = True
        self.cleanup_errors = []
        self.owner_thread = threading.get_ident()
        self.arm_attempted = False

    def _require_owner(self):
        if self.owner_thread != threading.get_ident():
            self.stop("broker_owner_thread_changed")
            raise NativeUnavailable("broker_owner_thread_required")

    def _release_owned(self):
        try:
            self.release_confirmed = self.port.release_owned() is True
        except BaseException:
            self.release_confirmed = False
            if "owned_release_exception" not in self.cleanup_errors:
                self.cleanup_errors.append("owned_release_exception")
        return self.release_confirmed

    def stop(self, reason="requested_stop"):
        # Hook callbacks only latch revocation; native cleanup runs outside hooks.
        with self.lock:
            if not self.stopped.is_set():
                self.stop_reason = reason
                self.stopped.set()
                try:
                    self.stop_monotonic = self.clock()
                except Exception:
                    self.stop_monotonic = None

    def _check_liveness(self):
        if self.stopped.is_set():
            raise NativeUnavailable("stop_latched:" + str(self.stop_reason))
        now = self.clock()
        if not 0 <= now - self.evidence.observed_monotonic <= self.max_age:
            raise NativeUnavailable("observation_stale_or_future")
        if self.deadline is not None and now >= self.deadline:
            raise NativeUnavailable("diagnostic_deadline_expired")
        if self.port is not None and not self.sent and self.port.user_activity_changed():
            raise NativeUnavailable("user_or_foreign_input_marker_changed")
        if self.port is not None and not self.port.guard_healthy():
            raise NativeUnavailable("native_guard_not_healthy")

    def _check(self):
        self._check_liveness()
        observed = self.observer(self.evidence.binding.hwnd, self.evidence.binding.pid)
        if Binding.from_observation(observed) != self.evidence.binding:
            raise NativeUnavailable("window_identity_or_geometry_changed")
        # Observation can block or trigger revocation. A pre-observation timestamp
        # must never authorize a submission that is now stale or past its deadline.
        self._check_liveness()
        return observed

    def arm(self):
        self._require_owner()
        if not self.enabled:
            raise NativeUnavailable("automatic_input_disabled")
        if self.arm_attempted or self.port is not None or self.attempted or self.closed.is_set():
            raise NativeUnavailable("session_cannot_rearm")
        self.arm_attempted = True
        if self.evidence.context == "self_owned_test":
            if self.evidence.binding.pid != os.getpid():
                raise NativeUnavailable("test_window_not_owned_by_this_process")
        elif self.evidence.context == "custom_room":
            if self.evidence.no_other_humans_verified is not True or self.evidence.operation != "reversible_non_spending_panel":
                raise NativeUnavailable("verified_custom_room_and_non_spending_operation_required")
            # The first native self-test was denied emergency hotkey registration.
            # This candidate deliberately cannot arm a game until that live gate
            # is independently passed and the integrator reviews the extension.
            raise NativeUnavailable("live_game_validation_gate_not_passed")
        else:
            raise NativeUnavailable("permitted_context_missing")
        if (type(self.evidence.x) is not int or type(self.evidence.y) is not int
                or not 0 <= self.evidence.x < self.evidence.binding.width
                or not 0 <= self.evidence.y < self.evidence.binding.height):
            raise NativeUnavailable("point_outside_observed_client")
        self._check()
        self.port = self.port_factory(self.observer)
        try:
            self.port.open(self.stop)
            self.deadline = self.clock() + self.max_seconds
            self._check()
        except BaseException:
            self.stop("arming_failed")
            self.close()
            raise

        def supervise():
            while not self.closed.wait(0.02):
                try:
                    self._check()
                except Exception as error:
                    self.stop(str(error))
                    self._release_owned()
                    break

        self.watchdog = threading.Thread(target=supervise, name="maawxq-click-deadline", daemon=True)
        try:
            self.watchdog.start()
        except BaseException:
            self.stop("supervisor_start_failed")
            self.close()
            raise

    def click_once(self):
        self._require_owner()
        if self.port is None or self.deadline is None:
            raise NativeUnavailable("not_armed")
        with self.lock:
            if self.attempted:
                raise NativeUnavailable("one_action_budget_exhausted")
            self.attempted = True
        try:
            observed = self._check()
            if self.stopped.is_set():
                raise NativeUnavailable("stop_latched")
            def permit():
                try:
                    self._check()
                    return not self.stopped.is_set()
                except Exception as error:
                    self.stop(str(error))
                    return False
            self.port.click(self.evidence.binding.hwnd,
                            observed["client"]["screen_x"] + self.evidence.x,
                            observed["client"]["screen_y"] + self.evidence.y, permit)
            self.sent = True
            self.submission_outcome = getattr(self.port, "submission_outcome", "submitted")
        except BaseException:
            self.submission_outcome = getattr(self.port, "submission_outcome", "uncertain")
            self.stop("click_failed_or_revoked")
            raise
        finally:
            self.stop("one_action_completed" if self.sent else "click_failed_or_revoked")
            self._release_owned()
        return {"status": "submitted_requires_visual_verification", "sent": True,
                "game_postcondition_verified": False, "action_budget_remaining": 0,
                "submission_outcome": self.submission_outcome,
                "owned_release_confirmed": self.release_confirmed,
                "cleanup_errors": tuple(self.cleanup_errors) + tuple(self.port.cleanup_errors)}

    def close(self):
        self.stop("closed")
        self._require_owner()
        self.closed.set()
        if self.watchdog and self.watchdog is not threading.current_thread():
            try:
                if self.watchdog.is_alive():
                    self.watchdog.join(1)
                if self.watchdog.is_alive() and "supervisor_close_timeout" not in self.cleanup_errors:
                    self.cleanup_errors.append("supervisor_close_timeout")
            except BaseException:
                if "supervisor_close_exception" not in self.cleanup_errors:
                    self.cleanup_errors.append("supervisor_close_exception")
        if self.port:
            self._release_owned()
            try:
                if self.port.close() is False and "port_cleanup_incomplete" not in self.cleanup_errors:
                    self.cleanup_errors.append("port_cleanup_incomplete")
            except BaseException:
                if "port_close_exception" not in self.cleanup_errors:
                    self.cleanup_errors.append("port_close_exception")

    def __enter__(self):
        self.arm()
        return self

    def __exit__(self, kind, value, traceback):
        self.close()
        return False
