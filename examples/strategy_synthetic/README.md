# Synthetic strategy replay

Every rule, resource, unit ID, opponent ID, phase and score in `scenario.json`
is **test_rules_not_gameplay**. There are no game assets, accounts, captures or
real-match outcomes here. These costs and composition signals are invented test
inputs, not Yixing rules.

From the repository root, with Python 3.10 or newer:

```powershell
python -B -m strategy --fixture examples/strategy_synthetic/scenario.json --allow-test-rules
python -B -m unittest discover -s tests -p "test_strategy_*.py" -v
```

The fixture freezes the decision clock, so repeated runs emit identical JSON.
The detailed output includes bound prerequisites, costs, expiry, hard rejection
reasons and individual score contributions. `expected_summary.json` records the
small expected result for review:

- `test_blocked`: rejected for `confirmed_ban`, even with a synthetic score input of 1000; no score is calculated.
- `test_develop`: score 3; selected using observed credits and capacity.
- `test_conserve`: score 2.
- `test_review_opponent`: separate scores 1 and 2 for `slot-a` and `slot-b`; equal display names never merge their identities. Reviewing an opponent is not choosing a game matchup.

Without `--allow-test-rules`, the same fixture returns no selected action. The
flag only enables synthetic advisory evaluation. Every output has
`execution_allowed: false`; there is no input option or executor.
