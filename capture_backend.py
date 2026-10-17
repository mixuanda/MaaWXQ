"""Bounded single-frame contract, target revalidation, cache budget and worker isolation."""
import base64
import json
import os
from pathlib import Path
import struct
import subprocess
import sys
import time
import uuid

from window_identity import IdentityError, inspect_window, utc_now

ROOT = Path(__file__).resolve().parent
CANDIDATE = "candidate_requires_visual_review"


class BackendError(Exception):
    pass


def cache_usage(cache):
    files = [path for path in cache.rglob("*") if path.is_file()] if cache.exists() else []
    return len(files), sum(path.stat().st_size for path in files)


def run_backend(backend, root, identity, output, config, timeout):
    if backend == "wgc":
        command = [sys.executable, "-B", str(root / "wgc_worker.py"), "--hwnd", str(identity["hwnd"]),
                   "--pid", str(identity["pid"]), "--identity-version", identity["identity_version"],
                   "--geometry-version", identity["geometry_version"]]
    else:
        command = ["powershell.exe", "-NoProfile", "-NonInteractive", "-File", str(root / "capture_window.ps1"),
                   "-TargetHwnd", str(identity["hwnd"]), "-ExpectedPid", str(identity["pid"]),
                   "-OutputPath", str(output), "-MaxCacheBytes", str(config["cache_max_bytes"]),
                   "-MaxCacheFiles", str(config["cache_max_files"])]
    process = subprocess.run(command, capture_output=True, encoding="utf-8", errors="replace", timeout=timeout,
                             cwd=root, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    if process.returncode:
        return {"status": "capture_unavailable", "reason": "capture_worker_failed", "worker_exit_code": process.returncode}
    try:
        result = json.loads(process.stdout)
    except ValueError as error:
        raise BackendError("capture_worker_output_invalid") from error
    if not isinstance(result, dict) or "status" not in result:
        raise BackendError("capture_worker_output_invalid")
    if backend == "wgc" and result.get("status") == CANDIDATE:
        result["image_bytes"] = base64.b64decode(result.pop("png_base64"), validate=True)
    elif backend == "printwindow" and result.get("status") == CANDIDATE:
        if result.get("image") != str(output):
            raise ValueError("unexpected_worker_image")
        result["image_bytes"] = output.read_bytes()
    return result


def _capture_locked(result, root, expected_version, timeout, observe, worker):
    try:
        config = json.loads((root / "config.json").read_text(encoding="utf-8"))
    except OSError:
        result["reason"] = "configuration_unavailable"
        return
    except ValueError:
        result["reason"] = "invalid_configuration"
        return
    if not isinstance(config, dict):
        result["reason"] = "invalid_configuration"
        return
    for name, default in (("cache_max_bytes", 67108864), ("cache_max_files", 50)):
        config.setdefault(name, default)
        if type(config[name]) is not int or config[name] <= 0:
            result["reason"] = "invalid_cache_limits"
            return
    if config.get("cache_dir", "cache") != "cache":
        result["reason"] = "unsupported_cache_dir"
        return
    cache = root / "cache"
    if not cache.resolve().is_relative_to(root.resolve()):
        result["reason"] = "cache_outside_project"
        return
    count, size = cache_usage(cache)
    if count >= config["cache_max_files"] or size >= config["cache_max_bytes"]:
        result.update(status="cache_limit_reached", reason="no_new_capture_written")
        return
    before = observe(result["hwnd"], result["expected_pid"])
    result["identity_before"] = before
    if expected_version is not None and expected_version != before["identity_version"]:
        result["reason"] = "window_identity_changed"
        return
    if not before["visible"] or before["minimized"]:
        result["reason"] = "window_minimized" if before["minimized"] else "window_hidden"
        return
    if not all(0 < before["client"][key] <= 8192 for key in ("width", "height")):
        result["reason"] = "invalid_dimensions"
        return
    output = cache / (result["attempt_id"] + ".worker.png")
    if output.exists():
        result["reason"] = "output_name_collision"
        return
    try:
        result["acquisition_started_at"] = utc_now()
        frame = worker(result["backend"], root, before, output, config, timeout)
        result["acquisition_finished_at"] = utc_now()
        image = frame.pop("image_bytes", None)
        # Workers cannot overwrite the wrapper's identity, timestamps or output path.
        for key in ("status", "reason", "backend_version", "width", "height", "sampled_colors", "method", "visibility", "occlusion"):
            if key in frame:
                result[key] = frame[key]
        result["acquired_at"] = frame.get("acquired_at") if result["backend"] == "wgc" else result["acquisition_finished_at"]
        result["source_frame_at"] = None
        result["timestamp_source"] = "host_receipt"
        after = observe(result["hwnd"], result["expected_pid"])
        result["identity_after"] = after
        result["desktop_effects"] = {
            "foreground_unchanged": before["desktop"]["foreground_hwnd"] == after["desktop"]["foreground_hwnd"],
            "cursor_unchanged": (None if before["desktop"]["cursor"] is None or after["desktop"]["cursor"] is None
                                 else before["desktop"]["cursor"] == after["desktop"]["cursor"]),
            "scope": "two_endpoint_observations_not_continuous_or_causal_proof",
        }
        if before["identity_version"] != after["identity_version"]:
            result.update(status="capture_unavailable", reason="window_identity_changed")
            return
        if before["geometry_version"] != after["geometry_version"]:
            result.update(status="capture_unavailable", reason="window_geometry_changed")
            return
        if not after["visible"] or after["minimized"]:
            result.update(status="capture_unavailable", reason="window_minimized" if after["minimized"] else "window_hidden")
            return
        if result["status"] != CANDIDATE:
            return
        if not image or len(image) < 24 or image[:8] != b"\x89PNG\r\n\x1a\n":
            result.update(status="capture_unavailable", reason="invalid_encoded_frame")
            return
        width, height = struct.unpack(">II", image[16:24])
        if (width, height) != (before["client"]["width"], before["client"]["height"]):
            result.update(status="capture_unavailable", reason="frame_dimensions_mismatch")
            return
        result.update(width=width, height=height)
        if output.exists():
            output.unlink()  # Only this attempt's diagnostic worker candidate.
        count, size = cache_usage(cache)
        if count >= config["cache_max_files"] or size + len(image) > config["cache_max_bytes"]:
            result.update(status="cache_limit_reached", reason="new_frame_would_exceed_limit")
            return
        cache.mkdir(parents=True, exist_ok=True)
        destination = cache / (result["attempt_id"] + ".png")
        created = False
        try:
            with destination.open("xb") as stream:
                created = True
                stream.write(image)
        except OSError:
            if created and destination.exists():
                destination.unlink()
            raise
        result.update(image=str(destination), frame_id=result["attempt_id"], captured_at=result["acquired_at"],
                      geometry_version=before["geometry_version"], quality="candidate_not_semantically_validated")
    finally:
        if output.exists():
            output.unlink()


def capture_one(hwnd, pid, role="unknown", *, backend="printwindow", root=ROOT, timeout=12,
                expected_identity_version=None, observe=inspect_window, worker=run_backend):
    started = time.monotonic()
    result = {"schema_version": "capture/1", "attempt_id": "frame-" + uuid.uuid4().hex,
              "status": "capture_unavailable", "reason": None, "backend": backend,
              "window_role": role, "role_source": "caller_assertion" if role != "unknown" else "unknown",
              "game_recognition": "waiting_for_game" if role == "launcher" else "not_validated",
              "hwnd": hwnd, "expected_pid": pid, "requested_at": utc_now(), "completed_at": None,
              "acquisition_started_at": None, "acquisition_finished_at": None, "acquired_at": None,
              "captured_at": None, "source_frame_at": None, "timestamp_source": None,
              "identity_before": None, "identity_after": None, "geometry_version": None,
              "frame_id": None, "image": None, "quality": "unavailable", "input_enabled": False}
    root = Path(root)
    lock = root / ".capture.lock"
    owned_lock = False
    try:
        if backend not in ("printwindow", "wgc") or role not in ("unknown", "launcher", "game"):
            result["reason"] = "invalid_backend_or_role"
        elif type(timeout) not in (int, float) or not 0 < timeout <= 30:
            result["reason"] = "invalid_timeout"
        else:
            try:
                handle = lock.open("x", encoding="utf-8")
                owned_lock = True
            except FileExistsError:
                result["reason"] = "capture_lock_exists"
            except OSError:
                result["reason"] = "capture_lock_unavailable"
            else:
                with handle:
                    handle.write(json.dumps({"pid": os.getpid(), "requested_at": result["requested_at"]}))
                    handle.flush()
                    _capture_locked(result, root, expected_identity_version, timeout, observe, worker)
    except IdentityError as error:
        result.update(status="capture_unavailable", reason=error.reason)
    except BackendError as error:
        result.update(status="capture_unavailable", reason=str(error))
    except subprocess.TimeoutExpired:
        result.update(status="capture_unavailable", reason="capture_timeout")
    except (OSError, ValueError, KeyError, TypeError) as error:
        result.update(status="capture_unavailable", reason="capture_worker_or_storage_error", error_type=type(error).__name__)
    finally:
        if owned_lock:
            try:
                lock.unlink()
            except OSError as error:
                result["lock_cleanup_error"] = type(error).__name__
        result["completed_at"] = utc_now()
        result["elapsed_ms"] = round((time.monotonic() - started) * 1000, 3)
    return result
