"""Run the explicitly synthetic CPU planning comparison. No game or model API."""

import argparse
import json
from pathlib import Path

from .demo import comparison


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixture", required=True, type=Path)
    parser.add_argument("--allow-test-rules", action="store_true")
    parser.add_argument("--timing-repeats", type=int, default=3)
    parser.add_argument("--output", type=Path, help="optional explicit local JSON report path")
    args = parser.parse_args()
    try:
        data = json.loads(args.fixture.read_text(encoding="utf-8"))
        report = comparison(data, allow_test_rules=args.allow_test_rules, timing_repeats=args.timing_repeats)
        text = json.dumps(report, indent=2, ensure_ascii=True, allow_nan=False) + "\n"
        if args.output:
            args.output.write_text(text, encoding="utf-8")
        else:
            print(text, end="")
    except (ValueError, TypeError, KeyError, OSError) as error:
        parser.exit(2, "Invalid synthetic comparison: " + str(error) + "\n")


if __name__ == "__main__":
    main()
