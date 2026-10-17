"""One-shot PrintWindow capture. No desktop fallback, focus, or game input."""
import argparse
import json
from pathlib import Path
import subprocess
import sys
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parent

def _capture(hwnd, pid, role="unknown"):
    result = {"status": "capture_unavailable", "window_role": role,
              "role_source": "caller_assertion" if role != "unknown" else "unknown",
              "game_recognition": "waiting_for_game" if role == "launcher" else "not_validated",
              "hwnd": hwnd, "expected_pid": pid, "image": None,
              "captured_at": datetime.now(timezone.utc).isoformat()}
    if sys.platform != "win32":
        return result | {"reason": "windows_required"}
    # The subprocess bounds PrintWindow, which may block on an unresponsive app.
    # Only project-local cache is permitted, never NAS.
    output = ROOT / "cache" / ("window-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ") + ".png")
    config = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))
    max_bytes = config.get("cache_max_bytes", 67108864)
    max_files = config.get("cache_max_files", 50)
    if type(max_bytes) is not int or type(max_files) is not int or max_bytes <= 0 or max_files <= 0:
        return result | {"reason": "invalid_cache_limits"}
    command = ["powershell.exe", "-NoProfile", "-NonInteractive", "-File",
               str(ROOT / "capture_window.ps1"), "-TargetHwnd", str(hwnd),
               "-ExpectedPid", str(pid), "-OutputPath", str(output),
               "-MaxCacheBytes", str(max_bytes), "-MaxCacheFiles", str(max_files)]
    try:
        process = subprocess.run(command, capture_output=True, encoding="utf-8", errors="replace",
                                 timeout=12, creationflags=subprocess.CREATE_NO_WINDOW)
        if process.returncode:
            result["reason"] = "capture_worker_failed"
            result["detail"] = process.stderr.strip()[:800]
        else:
            result.update(json.loads(process.stdout))
    except subprocess.TimeoutExpired:
        result["reason"] = "capture_timeout"
    except (OSError, ValueError) as error:
        result["reason"] = "capture_worker_error"
        result["detail"] = str(error)
    # Failed/uncertain runs never retain an image or report capture success.
    if result["status"] != "candidate_requires_visual_review" and output.exists():
        output.unlink()
    return result

def capture(hwnd, pid, role="unknown"):
    lock = ROOT / ".capture.lock"
    try:
        handle = lock.open("x")
    except FileExistsError:
        return {"status": "capture_unavailable", "reason": "capture_lock_exists", "image": None}
    try:
        with handle:
            return _capture(hwnd, pid, role)
    finally:
        lock.unlink()

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--hwnd", required=True, type=lambda value: int(value, 0))
    parser.add_argument("--pid", required=True, type=int)
    parser.add_argument("--role", choices=["launcher", "game", "unknown"], default="unknown",
                        help="Explicit human-confirmed role; never inferred from a window title")
    args = parser.parse_args()
    print(json.dumps(capture(args.hwnd, args.pid, args.role), ensure_ascii=False, indent=2))
