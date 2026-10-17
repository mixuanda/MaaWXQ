"""Offline preparation only. No game input or capture calls."""
import argparse
import copy
import ctypes
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
UNKNOWN = "unknown"

def timestamp(value):
    if not isinstance(value, str):
        raise ValueError("timestamp must be a string")
    result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if result.tzinfo is None:
        raise ValueError("timestamp needs a timezone")
    return result

def initial_state():
    return {"schema_version": "1.0", "session_id": UNKNOWN,
            "player_chess_player": {"entity_type": "chess_player", "name": "弈星", "id": UNKNOWN},
            "phase": UNKNOWN, "round": UNKNOWN,
            "opening_bans": {"status": UNKNOWN, "lineups": [], "observed_at": UNKNOWN},
            "opponent_history": []}

def apply_event(state, event, now=None):
    now = now or datetime.now(timezone.utc)
    if not isinstance(event, dict):
        raise ValueError("event must be an object")
    kind = event.get("type")
    required = {"opponent_observation": {"type", "opponent_id", "observed_at", "units"},
                "opening_bans": {"type", "observed_at", "lineups"}}
    if kind not in required or set(event) != required[kind]:
        raise ValueError("unknown event type or unexpected/missing fields")
    observed = timestamp(event["observed_at"])
    if observed > now:
        raise ValueError("future observation rejected")
    result = copy.deepcopy(state)
    if kind == "opponent_observation":
        if not isinstance(event["opponent_id"], str) or not event["opponent_id"]:
            raise ValueError("opponent_id must be a nonempty string or unknown")
        if not isinstance(event["units"], list):
            raise ValueError("units must be a list")
        units = []
        for unit in event["units"]:
            if not isinstance(unit, dict) or set(unit) - {"name", "hero_id"}:
                raise ValueError("unit allows only name and hero_id")
            name, hero_id = unit.get("name", UNKNOWN), unit.get("hero_id", UNKNOWN)
            if not isinstance(name, str) or not name or not isinstance(hero_id, str) or not hero_id:
                raise ValueError("name/hero_id must be nonempty strings; missing IDs stay unknown")
            units.append({"entity_type": "hero", "name": name, "hero_id": hero_id})
        result["opponent_history"].append({"opponent_id": event["opponent_id"],
            "observed_at": event["observed_at"], "units": units, "source": "manual_offline"})
    else:
        if not isinstance(event["lineups"], list) or any(not isinstance(x, str) or not x for x in event["lineups"]):
            raise ValueError("lineups must be a list of nonempty strings")
        previous = result["opening_bans"]["observed_at"]
        if previous != UNKNOWN and observed < timestamp(previous):
            raise ValueError("older ban observation cannot replace newer state")
        result["opening_bans"] = {"status": "observed", "lineups": event["lineups"], "observed_at": event["observed_at"]}
    return result

def with_freshness(state, ttl, now=None):
    now = now or datetime.now(timezone.utc)
    result = copy.deepcopy(state)
    for item in [result["opening_bans"], *result["opponent_history"]]:
        value = item["observed_at"]
        age = None if value == UNKNOWN else (now - timestamp(value)).total_seconds()
        item["age_seconds"] = age
        item["freshness"] = UNKNOWN if age is None or age < 0 else ("fresh" if age <= ttl else "stale")
    result["evaluated_at"] = now.isoformat()
    return result

def windows(title):
    if sys.platform != "win32":
        raise ValueError("window inspection requires Windows")
    from ctypes import wintypes
    api = ctypes.WinDLL("user32", use_last_error=True)
    callback_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    api.EnumWindows.argtypes = [callback_type, wintypes.LPARAM]
    api.GetWindowTextLengthW.argtypes = [wintypes.HWND]
    api.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
    api.IsWindowVisible.argtypes = [wintypes.HWND]
    found = []
    @callback_type
    def visit(hwnd, _):
        size = api.GetWindowTextLengthW(hwnd)
        buffer = ctypes.create_unicode_buffer(size + 1)
        api.GetWindowTextW(hwnd, buffer, size + 1)
        if api.IsWindowVisible(hwnd) and title in buffer.value:
            found.append({"hwnd": hex(hwnd), "title": buffer.value})
        return True
    if not api.EnumWindows(visit, 0):
        raise ctypes.WinError(ctypes.get_last_error())
    return found

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["demo", "replay", "capture-plan", "windows"])
    parser.add_argument("--events", type=Path)
    args = parser.parse_args()
    config = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))
    if args.command == "windows":
        output = windows(config["window_title"])
    elif args.command == "capture-plan":
        output = {"window_title": config["window_title"], "capture_enabled": False,
                  "input_enabled": False, "local_cache": str(ROOT / config["cache_dir"]),
                  "archive_dir": config["archive_dir"], "status": "prepared_not_captured",
                  "next_step": "Verify a fresh real-game frame; a launcher screenshot is not game validation."}
    else:
        state = initial_state()
        if args.command == "replay":
            if args.events is None:
                parser.error("replay requires --events")
            for line in args.events.read_text(encoding="utf-8-sig").splitlines():
                if line.strip():
                    state = apply_event(state, json.loads(line))
        output = with_freshness(state, config["freshness_seconds"])
    print(json.dumps(output, ensure_ascii=False, indent=2))

if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError) as error:
        print(f"Error: {error}", file=sys.stderr)
        sys.exit(1)
