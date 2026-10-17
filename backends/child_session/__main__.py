"""Offline ChildSession diagnostic. Does not query Windows or activate any session."""
import argparse
from dataclasses import replace
import json
from pathlib import Path

from .backend import ChildSessionBackend, ChildSessionConfig, PlatformFacts

ROOT = Path(__file__).resolve().parents[2]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=ROOT / "config" / "child_session.json")
    parser.add_argument("--synthetic-supported", action="store_true", help="Use anonymous invented facts; never marks the backend operational")
    args = parser.parse_args()
    config = ChildSessionConfig.from_dict(json.loads(args.config.read_text(encoding="utf-8")))
    facts = PlatformFacts()
    if args.synthetic_supported:
        facts = PlatformFacts(platform="win32", api_exports_available=True, child_sessions_enabled=True,
                              main_session_id=10, child_session_id=20, worker_session_id=20,
                              game_session_id=20, origin="synthetic_fixture")
        config = replace(config, enabled=True)
    print(json.dumps(ChildSessionBackend(config).assess(facts), indent=2))


if __name__ == "__main__":
    main()
