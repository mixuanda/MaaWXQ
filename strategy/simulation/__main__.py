"""Bounded synthetic-only demonstration. No external engine is imported."""

import argparse
import json

from ..contracts import to_dict
from .bridge import rolling_policy
from .fixtures import SCENARIOS
from .runner import run_episode
from .toy import ToySimulator


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--allow-synthetic-fixture", action="store_true")
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--scenario", choices=[x.scenario_id for x in SCENARIOS],
                        default="synthetic-economy-v1")
    args = parser.parse_args()
    if not args.allow_synthetic_fixture:
        parser.error("explicit --allow-synthetic-fixture is required")
    result = run_episode(ToySimulator, rolling_policy, seed=args.seed, scenario=args.scenario)
    print(json.dumps(to_dict(result), ensure_ascii=True, indent=2, allow_nan=False))
    return 0 if result.status == "completed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
