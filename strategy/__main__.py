"""Replay an offline JSON fixture and emit advice; no execution option exists."""

import argparse
import json
from pathlib import Path

from .codec import observation_from_dict, registry_from_dict, timestamp
from .contracts import MatchState, to_dict
from .policy import Policy, decide
from .state import reduce_observation


def replay_fixture(data, *, allow_test_rules=False):
    now = timestamp(data["decision_at"])
    registry = registry_from_dict(data["registry"])
    state = MatchState()
    for item in data["observations"]:
        state = reduce_observation(state, observation_from_dict(item), now=now)
    return decide(state, registry, now=now, policy=Policy(allow_test_rules=allow_test_rules))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixture", required=True, type=Path)
    parser.add_argument("--allow-test-rules", action="store_true",
                        help="explicitly allow test_rules_not_gameplay for synthetic checks only")
    args = parser.parse_args()
    try:
        data = json.loads(args.fixture.read_text(encoding="utf-8"))
        result = replay_fixture(data, allow_test_rules=args.allow_test_rules)
    except (ValueError, KeyError, TypeError, OSError) as error:
        parser.exit(2, "Invalid offline fixture: " + str(error) + "\n")
    print(json.dumps(to_dict(result), indent=2, ensure_ascii=True, allow_nan=False))


if __name__ == "__main__":
    main()
