"""Explicit external-game adapter; default self-owned diagnostic stays restricted."""
import threading
import time
import ctypes as c
from ctypes import wintypes as w
from dataclasses import dataclass
from backends.win32_single_click import Binding,ClickEvidence,WindowsClickPort,SingleClickBroker,NativeUnavailable

@dataclass(frozen=True)
class GameClickEvidence(ClickEvidence):
    scene: str = 'unknown'
    frame_sha256: str = ''
    recognizer: str = ''
    executable_path: str = ''
    digit: str = ''

class GameClickPort(WindowsClickPort):
    def __init__(self,observer,binding,executable_path,abort_event):
        self.binding=binding
        self.executable_path=executable_path
        self.abort_event=abort_event
        self.click_timing='bounded_60ms_down_up/1'
        self.down_submitted_at=None
        super().__init__(observer)

    def validate_native_target(self,hwnd):
        if hwnd!=self.binding.hwnd:raise NativeUnavailable('game_hwnd_changed')
        process=w.DWORD()
        if not self.user.GetWindowThreadProcessId(hwnd,c.byref(process)) or process.value!=self.binding.pid:
            raise NativeUnavailable('game_pid_changed')
        row=self.observe(hwnd,self.binding.pid)
        if (Binding.from_observation(row)!=self.binding or row.get('title')!='王者万象棋'
                or row.get('executable_path','').casefold()!=self.executable_path.casefold()):
            raise NativeUnavailable('game_identity_or_geometry_changed')

    def click(self, hwnd, x, y, permit):
        self._require_owner()
        if not self.guard_healthy():
            raise NativeUnavailable("native_guard_not_healthy")
        left, top, width, height = [self.user.GetSystemMetrics(i) for i in (76, 77, 78, 79)]
        if width <= 1 or height <= 1 or not (left <= x < left + width and top <= y < top + height):
            raise NativeUnavailable("point_outside_virtual_desktop")
        absolute_x = round((x - left) * 65535 / (width - 1))
        absolute_y = round((y - top) * 65535 / (height - 1))
        events = (self.Input * 2)()
        for event in events:
            event.type = 0
            event.mi.dwExtraInfo = self.token
        events[0].mi.dx, events[0].mi.dy = absolute_x, absolute_y
        events[0].mi.dwFlags = 0xC001  # MOVE | ABSOLUTE | VIRTUALDESK
        events[1].mi.dwFlags = 0x0002
        with self.ledger_lock:
            self.validate_native_target(hwnd)
            if (self.foreground() != hwnd
                    or int(self.user.GetAncestor(self.user.WindowFromPoint(w.POINT(x, y)), 2) or 0) != hwnd
                    or any(self.user.GetAsyncKeyState(code) & 0x8000 for code in range(1, 256))
                    or not permit()):
                raise NativeUnavailable("final_target_or_permission_changed")
            self.held = True  # Reserve ownership before irreversible submission.
            self.submission_outcome = "uncertain"
            try:
                sent = int(self.user.SendInput(2, events, c.sizeof(self.Input)))
            except BaseException:
                # Retain a visible, possibly held ledger entry for cleanup.
                raise
            self.held = sent == 2
            self.submitted_event_count = sent
            self.down_submitted_at=time.monotonic() if sent==2 else None
            self.submission_outcome = "down_submitted" if sent == 2 else "incomplete_down_batch"
        if sent != 2:
            self.release_owned()
            raise NativeUnavailable("send_input_incomplete:" + str(sent))
        # A normal short click spans rendering frames; there is no hold/drag API.
        # Cancellation wakes immediately. Every path only releases our own DOWN.
        try:
            interrupted=self.abort_event.wait(.060)
        finally:
            if not self.release_owned():raise NativeUnavailable('owned_click_release_failed')
        self.submission_outcome='released_after_interrupt' if interrupted else 'down_and_owned_up_submitted'
        return 3

    def user_activity_changed(self):
        # The marker necessarily changes after our own MOVE/DOWN. No new action
        # can follow; hooks still cancel and the only remaining input is owned UP.
        if self.submitted_event_count==2:return False
        return super().user_activity_changed()

class GameClickBroker(SingleClickBroker):
    def __init__(self,evidence,*,observer,enabled=False,**options):
        if not isinstance(evidence,GameClickEvidence):raise ValueError('typed_game_evidence_required')
        self.foreign_interrupt=threading.Event()
        super().__init__(evidence,observer=observer,enabled=enabled,
                         port_factory=lambda obs:GameClickPort(obs,evidence.binding,evidence.executable_path,self.stopped),**options)

    def stop(self,reason='requested_stop'):
        if reason not in ('closed','one_action_completed','stop_latched:one_action_completed'):
            self.foreign_interrupt.set()
        return super().stop(reason)

    def validate_context(self):
        e=self.evidence
        # First supported software transition. Unrecognized room/battle states do not act.
        selection=(e.scene=='custom_selection' and e.operation=='confirm_custom_selection' and e.recognizer=='custom-selection-glyphs/1')
        keypad=(e.scene=='room_keypad' and e.operation=='room_code_digit' and e.recognizer=='room-keypad-glyphs/1' and len(e.digit)==1 and e.digit in '0123456789')
        if (e.context!='custom_setup' or not (selection or keypad)
                or len(e.frame_sha256)!=64 or any(x not in '0123456789abcdef' for x in e.frame_sha256)
                or e.binding.class_name!='UnityWndClass' or not e.executable_path.casefold().endswith('\\wxq.exe')):
            raise NativeUnavailable('unsupported_or_unproven_game_transition')

    def arm(self):
        self._require_owner()
        if not self.enabled:
            raise NativeUnavailable("automatic_input_disabled")
        if self.arm_attempted or self.port is not None or self.attempted or self.closed.is_set():
            raise NativeUnavailable("session_cannot_rearm")
        self.arm_attempted = True
        self.validate_context()
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
