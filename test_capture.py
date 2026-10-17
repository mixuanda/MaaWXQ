"""Offline capture invariants. No Win32 calls or game interaction."""
import copy
import json
from pathlib import Path
import struct
import subprocess
import tempfile
import unittest
from unittest.mock import Mock
import zlib

from capture_backend import CANDIDATE, capture_one
from window_identity import IdentityError, stamp


def png(width=2, height=2):
    def chunk(kind, data):
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)) +
            chunk(b"IDAT", zlib.compress((b"\0" + b"\xff\0\x7f" * width) * height)) + chunk(b"IEND", b""))


def identity():
    return stamp({"hwnd": 123, "pid": 456, "process_started_at": "2026-01-01T00:00:00+00:00",
                  "class_name": "SyntheticWindow", "dpi": 96, "visible": True, "minimized": False,
                  "observed_at": "2026-01-01T00:00:01+00:00", "client": {"screen_x": 0, "screen_y": 0, "width": 2, "height": 2},
                  "window_rect": {"left": 0, "top": 0, "right": 2, "bottom": 2},
                  "desktop": {"foreground_hwnd": 777, "cursor": {"x": 20, "y": 30}}})


class CaptureTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.config = {"cache_dir": "cache", "cache_max_bytes": 67108864, "cache_max_files": 50}
        self.configure()
        self.before = identity()
        self.observe = Mock(return_value=self.before)
        self.worker = Mock(return_value={"status": CANDIDATE, "reason": "candidate", "image_bytes": png(), "sampled_colors": 10})

    def configure(self, **values):
        self.config.update(values)
        (self.root / "config.json").write_text(json.dumps(self.config), encoding="utf-8")

    def capture(self, **options):
        return capture_one(123, 456, root=self.root, observe=self.observe, worker=self.worker, **options)

    def assert_unusable(self, result, reason):
        self.assertEqual(result["reason"], reason)
        self.assertIsNone(result["image"])
        self.assertIsNone(result["frame_id"])
        self.assertIsNotNone(result["completed_at"])
        self.assertFalse((self.root / ".capture.lock").exists())

    def test_tokens_track_identity_and_geometry_separately(self):
        other = copy.deepcopy(self.before)
        other["observed_at"] = "2026-01-02T00:00:00+00:00"
        self.assertEqual(stamp(other)["geometry_version"], self.before["geometry_version"])
        other["client"]["screen_x"] = 1
        self.assertNotEqual(stamp(other)["geometry_version"], self.before["geometry_version"])
        self.assertEqual(other["identity_version"], self.before["identity_version"])
        other["process_started_at"] = None
        self.assertNotEqual(stamp(other)["identity_version"], self.before["identity_version"])

    def test_candidate_is_saved_but_never_claims_game_validation(self):
        result = self.capture(role="game")
        self.assertEqual(result["status"], CANDIDATE)
        self.assertEqual(Path(result["image"]).read_bytes(), png())
        self.assertEqual(result["game_recognition"], "not_validated")
        self.assertIsNone(result["source_frame_at"])
        self.assertFalse(result["input_enabled"])
        self.assertNotIn("image_bytes", result)

    def test_stale_binding_and_unavailable_window_never_start_worker(self):
        result = self.capture(expected_identity_version="old")
        self.assert_unusable(result, "window_identity_changed")
        self.observe.side_effect = IdentityError("window_not_found")
        self.assert_unusable(self.capture(), "window_not_found")
        self.worker.assert_not_called()

    def test_hidden_and_minimized_never_start_worker(self):
        for key, reason in (("visible", "window_hidden"), ("minimized", "window_minimized")):
            with self.subTest(key=key):
                changed = copy.deepcopy(self.before)
                changed[key] = key == "minimized"
                self.observe.return_value = changed
                self.assert_unusable(self.capture(), reason)
        self.worker.assert_not_called()

    def test_geometry_change_during_capture_discards_frame(self):
        after = copy.deepcopy(self.before)
        after["client"]["screen_x"] = 1
        self.observe.side_effect = [self.before, stamp(after)]
        self.assert_unusable(self.capture(), "window_geometry_changed")
        self.assertEqual(list((self.root / "cache").glob("*.png")), [])

    def test_identity_change_during_capture_discards_frame(self):
        after = copy.deepcopy(self.before)
        after["process_started_at"] = None
        self.observe.side_effect = [self.before, stamp(after)]
        self.assert_unusable(self.capture(), "window_identity_changed")

    def test_byte_and_file_limits_preserve_existing_files(self):
        cache = self.root / "cache"
        cache.mkdir()
        existing = cache / "keep.txt"
        existing.write_bytes(b"keep")
        for limits in ({"cache_max_files": 1}, {"cache_max_files": 50, "cache_max_bytes": 4}):
            self.configure(**limits)
            self.assert_unusable(self.capture(), "no_new_capture_written")
            self.assertEqual(existing.read_bytes(), b"keep")
        self.worker.assert_not_called()

    def test_encoded_frame_and_late_writer_cannot_exceed_budget(self):
        self.configure(cache_max_bytes=len(png()) - 1)
        self.assert_unusable(self.capture(), "new_frame_would_exceed_limit")
        self.configure(cache_max_bytes=67108864, cache_max_files=1)
        def late_file(*args):
            (self.root / "cache").mkdir(exist_ok=True)
            (self.root / "cache" / "keep.txt").write_bytes(b"keep")
            return {"status": CANDIDATE, "image_bytes": png()}
        self.worker.side_effect = late_file
        self.assert_unusable(self.capture(), "new_frame_would_exceed_limit")
        self.assertEqual((self.root / "cache" / "keep.txt").read_bytes(), b"keep")

    def test_timeout_cleans_own_partial_and_lock(self):
        def timeout(*args):
            output = args[3]
            output.parent.mkdir(exist_ok=True)
            output.write_bytes(b"partial")
            raise subprocess.TimeoutExpired("synthetic-worker", 12)
        self.worker.side_effect = timeout
        self.assert_unusable(self.capture(), "capture_timeout")
        self.assertEqual(list((self.root / "cache").iterdir()), [])

    def test_existing_lock_is_preserved(self):
        lock = self.root / ".capture.lock"
        lock.write_text("another owner", encoding="utf-8")
        result = self.capture()
        self.assertEqual(result["reason"], "capture_lock_exists")
        self.assertEqual(lock.read_text(), "another owner")
        self.worker.assert_not_called()

    def test_backend_failure_and_wrong_dimensions_have_no_usable_image(self):
        self.worker.return_value = {"status": "capture_unavailable", "reason": "wgc_runtime_missing"}
        self.assert_unusable(self.capture(backend="wgc"), "wgc_runtime_missing")
        self.worker.return_value = {"status": CANDIDATE, "image_bytes": png(3, 2)}
        self.assert_unusable(self.capture(), "frame_dimensions_mismatch")


if __name__ == "__main__":
    unittest.main()
