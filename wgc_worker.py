"""Private subprocess entry: one plain WGC frame, with both native input methods None."""
import argparse
import base64
import ctypes as c
import hashlib
import json
import os
from pathlib import Path
import time

from window_identity import IdentityError, inspect_window, utc_now

ROOT = Path(__file__).resolve().parent


def capture_wgc(hwnd, pid, identity_version, geometry_version):
    result = {"status": "capture_unavailable", "reason": None, "image": None,
              "backend": "maafw_wgc", "source_frame_at": None, "timestamp_source": "host_receipt"}
    pin = json.loads((ROOT / "capture-runtime.lock.json").read_text(encoding="utf-8"))
    runtime = ROOT / "local" / ("maafw-" + pin["version"])
    if not (runtime / "receipt.json").is_file():
        return result | {"reason": "wgc_runtime_missing"}
    receipt = json.loads((runtime / "receipt.json").read_text(encoding="utf-8"))
    if receipt.get("wheel_sha256") != pin["sha256"] or receipt.get("version") != pin["version"]:
        return result | {"reason": "wgc_runtime_pin_mismatch"}
    for name, expected_hash in receipt["dll_sha256"].items():
        native = (runtime / name).resolve()
        if (not native.is_relative_to(runtime.resolve()) or not native.is_file() or
                hashlib.sha256(native.read_bytes()).hexdigest() != expected_hash):
            return result | {"reason": "wgc_runtime_integrity_failed"}
    libraries = list(runtime.rglob("MaaFramework.dll"))
    if len(libraries) != 1:
        return result | {"reason": "wgc_runtime_library_missing"}
    before = inspect_window(hwnd, pid)
    if before["identity_version"] != identity_version:
        return result | {"reason": "window_identity_changed"}
    if before["geometry_version"] != geometry_version:
        return result | {"reason": "window_geometry_changed"}
    if not before["visible"] or before["minimized"]:
        return result | {"reason": "window_minimized" if before["minimized"] else "window_hidden"}
    with os.add_dll_directory(str(libraries[0].parent)):
        try:
            api = c.WinDLL(str(libraries[0]))
        except OSError:
            return result | {"reason": "wgc_native_dependency_unavailable"}
        signatures = {
            "MaaVersion": ([], c.c_char_p),
            "MaaGlobalSetOption": ([c.c_int32, c.c_void_p, c.c_uint64], c.c_uint8),
            "MaaWin32ControllerCreate": ([c.c_void_p, c.c_uint64, c.c_uint64, c.c_uint64], c.c_void_p),
            "MaaControllerDestroy": ([c.c_void_p], None),
            "MaaControllerSetOption": ([c.c_void_p, c.c_int32, c.c_void_p, c.c_uint64], c.c_uint8),
            "MaaControllerPostConnection": ([c.c_void_p], c.c_int64),
            "MaaControllerPostScreencap": ([c.c_void_p], c.c_int64),
            "MaaControllerStatus": ([c.c_void_p, c.c_int64], c.c_int32),
            "MaaControllerCachedImage": ([c.c_void_p, c.c_void_p], c.c_uint8),
            "MaaImageBufferCreate": ([], c.c_void_p),
            "MaaImageBufferDestroy": ([c.c_void_p], None),
            "MaaImageBufferWidth": ([c.c_void_p], c.c_int32),
            "MaaImageBufferHeight": ([c.c_void_p], c.c_int32),
            "MaaImageBufferChannels": ([c.c_void_p], c.c_int32),
            "MaaImageBufferType": ([c.c_void_p], c.c_int32),
            "MaaImageBufferGetRawData": ([c.c_void_p], c.c_void_p),
            "MaaImageBufferGetEncoded": ([c.c_void_p], c.c_void_p),
            "MaaImageBufferGetEncodedSize": ([c.c_void_p], c.c_size_t),
        }
        for name, (args, returns) in signatures.items():
            function = getattr(api, name)
            function.argtypes, function.restype = args, returns
        version = api.MaaVersion().decode()
        if version.lstrip("v") != pin["version"]:
            return result | {"reason": "wgc_runtime_version_mismatch", "backend_version": version}
        result["backend_version"] = version
        disabled, off = c.c_uint8(0), c.c_int32(0)
        for option in (2, 6, 7):  # SaveDraw, DebugMode, SaveOnError
            if not api.MaaGlobalSetOption(option, c.byref(disabled), c.sizeof(disabled)):
                return result | {"reason": "wgc_configuration_failed"}
        if not api.MaaGlobalSetOption(4, c.byref(off), c.sizeof(off)):
            return result | {"reason": "wgc_configuration_failed"}
        # Exactly FramePool=2, never a combined fallback. Mouse/keyboard None=0.
        ctrl = api.MaaWin32ControllerCreate(hwnd, 2, 0, 0)
        if not ctrl:
            return result | {"reason": "wgc_controller_creation_failed"}
        image = None
        try:
            raw_size = c.c_uint8(1)
            if not api.MaaControllerSetOption(ctrl, 3, c.byref(raw_size), c.sizeof(raw_size)):
                return result | {"reason": "wgc_configuration_failed"}
            deadline = time.monotonic() + 8

            def wait(job):
                if not job:
                    return "failed"
                while time.monotonic() < deadline:
                    state = api.MaaControllerStatus(ctrl, job)
                    if state not in (1000, 2000):
                        return "succeeded" if state == 3000 else "failed"
                    time.sleep(0.02)
                return "timeout"

            connected = wait(api.MaaControllerPostConnection(ctrl))
            if connected != "succeeded":
                return result | {"reason": "wgc_connection_" + connected}
            result["acquisition_started_at"] = utc_now()
            captured = wait(api.MaaControllerPostScreencap(ctrl))
            if captured != "succeeded":
                return result | {"reason": "wgc_capture_" + captured}
            image = api.MaaImageBufferCreate()
            if not image or not api.MaaControllerCachedImage(ctrl, image):
                return result | {"reason": "wgc_image_unavailable"}
            result["acquired_at"] = utc_now()
            width, height = api.MaaImageBufferWidth(image), api.MaaImageBufferHeight(image)
            channels, image_type = api.MaaImageBufferChannels(image), api.MaaImageBufferType(image)
            if not (0 < width <= 8192 and 0 < height <= 8192 and channels in (3, 4) and image_type & 7 == 0):
                return result | {"reason": "invalid_dimensions_or_pixel_format"}
            raw = api.MaaImageBufferGetRawData(image)
            if not raw:
                return result | {"reason": "wgc_image_unavailable"}
            colors = {c.string_at(raw + (y * width + x) * channels, 3)
                      for y in range(0, height, max(1, height // 32))
                      for x in range(0, width, max(1, width // 32))}
            result.update(width=width, height=height, sampled_colors=len(colors))
            if len(colors) < 8:
                return result | {"status": "blank_or_low_detail_frame", "reason": "heuristic_low_color_variation"}
            encoded = api.MaaImageBufferGetEncoded(image)
            size = api.MaaImageBufferGetEncodedSize(image)
            if not encoded or not 24 <= size <= 67108864:
                return result | {"reason": "invalid_encoded_frame"}
            data = c.string_at(encoded, size)
            if data[:8] != b"\x89PNG\r\n\x1a\n":
                return result | {"reason": "unexpected_encoded_format"}
            return result | {"status": "candidate_requires_visual_review", "reason": "pixel_variation_is_not_semantic_validation",
                             "png_base64": base64.b64encode(data).decode("ascii")}
        finally:
            if image:
                api.MaaImageBufferDestroy(image)
            api.MaaControllerDestroy(ctrl)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--hwnd", type=int, required=True)
    parser.add_argument("--pid", type=int, required=True)
    parser.add_argument("--identity-version", required=True)
    parser.add_argument("--geometry-version", required=True)
    args = parser.parse_args()
    try:
        outcome = capture_wgc(args.hwnd, args.pid, args.identity_version, args.geometry_version)
    except IdentityError as error:
        outcome = {"status": "capture_unavailable", "reason": error.reason, "image": None}
    except (OSError, ValueError, KeyError, AttributeError) as error:
        outcome = {"status": "capture_unavailable", "reason": "wgc_worker_error", "error_type": type(error).__name__, "image": None}
    print(json.dumps(outcome))
