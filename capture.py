"""Explicit one-shot window capture. No desktop fallback, focus, or game input."""
import argparse
import json

from capture_backend import capture_one


def capture(hwnd, pid, role="unknown", **options):
    return capture_one(hwnd, pid, role, **options)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--hwnd", required=True, type=lambda value: int(value, 0))
    parser.add_argument("--pid", required=True, type=int)
    parser.add_argument("--role", choices=["launcher", "game", "unknown"], default="unknown",
                        help="Caller assertion only; does not validate image semantics")
    parser.add_argument("--backend", choices=["printwindow", "wgc"], default="printwindow")
    parser.add_argument("--identity-version", help="Optional token from a fresh window_identity observation")
    args = parser.parse_args()
    print(json.dumps(capture(args.hwnd, args.pid, args.role, backend=args.backend,
                             expected_identity_version=args.identity_version), ensure_ascii=False, indent=2))
