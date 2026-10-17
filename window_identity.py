"""Read-only Win32 target identity. No activation, input, or process memory reads."""
import argparse
import ctypes as c
from ctypes import wintypes as w
from datetime import datetime, timezone, timedelta
import hashlib
import json
import sys


class IdentityError(Exception):
    def __init__(self, reason):
        self.reason = reason
        super().__init__(reason)


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def version_of(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()[:24]


def stamp(identity):
    """Stable tokens; observation time and unrelated desktop activity are excluded."""
    identity["identity_version"] = version_of({key: identity[key] for key in
                                               ("hwnd", "pid", "process_started_at", "class_name")})
    identity["geometry_version"] = version_of({key: identity[key] for key in ("client", "window_rect", "dpi")})
    return identity


def _apis():
    if sys.platform != "win32":
        raise IdentityError("windows_required")
    user = c.WinDLL("user32", use_last_error=True)
    kernel = c.WinDLL("kernel32", use_last_error=True)
    signatures = {
        "IsWindow": ([w.HWND], w.BOOL), "IsWindowVisible": ([w.HWND], w.BOOL),
        "IsIconic": ([w.HWND], w.BOOL),
        "GetWindowThreadProcessId": ([w.HWND, c.POINTER(w.DWORD)], w.DWORD),
        "GetClientRect": ([w.HWND, c.POINTER(w.RECT)], w.BOOL),
        "GetWindowRect": ([w.HWND, c.POINTER(w.RECT)], w.BOOL),
        "ClientToScreen": ([w.HWND, c.POINTER(w.POINT)], w.BOOL),
        "GetWindowTextW": ([w.HWND, w.LPWSTR, c.c_int], c.c_int),
        "GetClassNameW": ([w.HWND, w.LPWSTR, c.c_int], c.c_int),
        "GetForegroundWindow": ([], w.HWND),
        "GetCursorPos": ([c.POINTER(w.POINT)], w.BOOL),
    }
    for name, (args, result) in signatures.items():
        fn = getattr(user, name)
        fn.argtypes, fn.restype = args, result
    kernel.OpenProcess.argtypes = [w.DWORD, w.BOOL, w.DWORD]
    kernel.OpenProcess.restype = w.HANDLE
    kernel.CloseHandle.argtypes = [w.HANDLE]
    kernel.CloseHandle.restype = w.BOOL
    kernel.GetProcessTimes.argtypes = [w.HANDLE] + [c.POINTER(w.FILETIME)] * 4
    kernel.GetProcessTimes.restype = w.BOOL
    return user, kernel


def inspect_window(hwnd, expected_pid=None):
    user, kernel = _apis()
    if type(hwnd) is not int or hwnd <= 0 or not user.IsWindow(hwnd):
        raise IdentityError("window_not_found")
    pid = w.DWORD()
    if not user.GetWindowThreadProcessId(hwnd, c.byref(pid)):
        raise IdentityError("window_identity_unavailable")
    if expected_pid is not None and pid.value != expected_pid:
        raise IdentityError("window_identity_changed")
    # Thread-local DPI context affects only this observer, not the target window.
    previous = None
    if hasattr(user, "SetThreadDpiAwarenessContext"):
        user.SetThreadDpiAwarenessContext.argtypes = [c.c_void_p]
        user.SetThreadDpiAwarenessContext.restype = c.c_void_p
        previous = user.SetThreadDpiAwarenessContext(c.c_void_p(-4))
    try:
        client, rect, origin = w.RECT(), w.RECT(), w.POINT()
        if not (user.GetClientRect(hwnd, c.byref(client)) and
                user.GetWindowRect(hwnd, c.byref(rect)) and
                user.ClientToScreen(hwnd, c.byref(origin))):
            raise IdentityError("bounds_unavailable")
        dpi = None
        if hasattr(user, "GetDpiForWindow"):
            user.GetDpiForWindow.argtypes, user.GetDpiForWindow.restype = [w.HWND], w.UINT
            dpi = user.GetDpiForWindow(hwnd) or None
        title, class_name = c.create_unicode_buffer(2048), c.create_unicode_buffer(256)
        user.GetWindowTextW(hwnd, title, len(title))
        user.GetClassNameW(hwnd, class_name, len(class_name))
        started, metadata_error = None, None
        handle = kernel.OpenProcess(0x1000, False, pid.value)  # QUERY_LIMITED_INFORMATION only
        if handle:
            try:
                times = [w.FILETIME() for _ in range(4)]
                if kernel.GetProcessTimes(handle, *(c.byref(t) for t in times)):
                    ticks = (times[0].dwHighDateTime << 32) | times[0].dwLowDateTime
                    started = (datetime(1601, 1, 1, tzinfo=timezone.utc) + timedelta(microseconds=ticks // 10)).isoformat()
                else:
                    metadata_error = c.get_last_error()
            finally:
                kernel.CloseHandle(handle)
        else:
            metadata_error = c.get_last_error()
        point = w.POINT()
        cursor = {"x": point.x, "y": point.y} if user.GetCursorPos(c.byref(point)) else None
        value = {
            "hwnd": hwnd, "pid": pid.value, "process_started_at": started,
            "process_metadata_error": metadata_error, "title": title.value,
            "class_name": class_name.value, "observed_at": utc_now(), "dpi": dpi,
            "dpi_context": "per_monitor_v2" if previous else "unconfirmed",
            "client": {"screen_x": origin.x, "screen_y": origin.y,
                       "width": client.right - client.left, "height": client.bottom - client.top},
            "window_rect": {"left": rect.left, "top": rect.top, "right": rect.right, "bottom": rect.bottom},
            "visible": bool(user.IsWindowVisible(hwnd)), "minimized": bool(user.IsIconic(hwnd)),
            "desktop": {"foreground_hwnd": int(user.GetForegroundWindow() or 0), "cursor": cursor},
        }
        after_pid = w.DWORD()
        if not user.IsWindow(hwnd) or not user.GetWindowThreadProcessId(hwnd, c.byref(after_pid)) or after_pid.value != pid.value:
            raise IdentityError("window_identity_changed")
        return stamp(value)
    finally:
        if previous:
            user.SetThreadDpiAwarenessContext(previous)


def find_windows(title):
    user, _ = _apis()
    callback_type = c.WINFUNCTYPE(w.BOOL, w.HWND, w.LPARAM)
    user.EnumWindows.argtypes, user.EnumWindows.restype = [callback_type, w.LPARAM], w.BOOL
    found = []

    @callback_type
    def visit(hwnd, _):
        text = c.create_unicode_buffer(2048)
        user.GetWindowTextW(hwnd, text, len(text))
        if title in text.value and user.IsWindowVisible(hwnd):
            try:
                found.append(inspect_window(int(hwnd)))
            except IdentityError:
                pass  # A target can disappear during enumeration.
        return True

    if not user.EnumWindows(visit, 0):
        raise IdentityError("window_enumeration_failed")
    return found


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--title", default="王者万象棋")
    args = parser.parse_args()
    try:
        print(json.dumps({"observed_at": utc_now(), "windows": find_windows(args.title)}, ensure_ascii=False, indent=2))
    except IdentityError as error:
        print(json.dumps({"status": "unavailable", "reason": error.reason}))
