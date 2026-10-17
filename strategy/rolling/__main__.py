"""Run the opt-in synthetic report, with no capture/input/network imports."""

import argparse
import json
from pathlib import Path

from .demo import comparison


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixture", required=True)
    parser.add_argument("--allow-test-rules", action="store_true")
    parser.add_argument("--output")
    args = parser.parse_args()
    report = comparison(args.fixture, allow_test_rules=args.allow_test_rules)
    text = json.dumps(report, indent=2, allow_nan=False) + "\n"
    if args.output:
        Path(args.output).write_text(text, encoding="utf-8")
    else:
        print(text, end="")


if __name__ == "__main__":
    main()
