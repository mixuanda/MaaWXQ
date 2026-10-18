# Decide from relevant known rules without filling irrelevant unknowns

The rolling planner previously required every card value, every acquisition
price and every interaction value in the entire declared world to be known.
One unknown parameter could therefore block a complete known route even when
the associated card was prohibited or unavailable throughout the requested
horizon. The exact prior whole-world check remains reproducible by calling
`support_reasons(world, first_round, horizon)` without a scope.

The planner now derives a conservative support scope from the observed own
position, confirmed match bans and the explicitly declared horizon. It keeps
unknown parameters as `None`. An unknown is excluded only when its value is not
needed within that scope; there is no zero, average value or invented game rule.

## Independent acceptance case

The existing synthetic pivot fixture declares A/B/C/E, A+C and A+E links,
one-credit replacement payment and two points of switching utility cost. This
change deliberately marks C's price/value and its A/C link value **unknown**.
The observations remain A/B deployed, C/E held, one credit, and a fresh guard
opponent view. All prices and scores below are `test_rules_not_gameplay`.

| Evidence or horizon | Before | Now and explanation |
| --- | --- | --- |
| C confirmed prohibited for this match | Abstain because the whole catalog contains unknowns | Replace B with E: known A/E formation 10 minus switching utility cost 2 = 8, versus keeping A/B at 7 |
| Same own zones, C not prohibited | Abstain | Still abstain: C and A/C are possible, so their unknown utility cannot be ignored |
| Only E held, C unavailable in the current one-round horizon | Abstain | The same known E pivot is supported; no unseen future shop is invented |
| Same state, declared second round can offer unknown C | Abstain | Still abstain for a two-round request; C's possible purchase and interaction re-enter required support |
| C prohibited in both declared rounds | Abstain | The known robust two-round route replaces A with E, yielding 9 + 9 - 2 = 16; keeping B avoids relying on the link a future breaker disables |

The two-round opponent set still expands to all declared profiles. Excluding C
does not assume the current guard persists. After E is additionally confirmed
prohibited, replanning keeps A/B and old E advice fails ban-version validation.

A second contrast keeps C's value and interaction known but its acquisition
price unknown. C already held can be deployed without inventing its old purchase
price. C currently offered cannot be bought at an unknown price. A prohibited C
offer is rejected before `ResourceCost` construction, avoiding both a `None`
constructor failure and any fabricated free purchase.

## Conservative support contract

[`planning_scope`](../strategy/rolling/model.py) uses this over-approximation:

1. Retain all currently deployed own units. A ban is not evidence that an observed
   unit disappeared; an unknown unit still on the board remains required.
2. Add non-prohibited held units and possible purchases from current offers plus
   the declared future frames inside the requested horizon. Already owned or
   irreversibly discarded toy units cannot be reacquired in this model.
3. Require an acquisition price only for a possible purchase. Require formation
   values for every potentially usable own unit.
4. Require a pair's utility if both units remain possible. Require a threshold's
   utility if enough possible distinct units carry its declared role. An excluded
   unknown link stays unknown; it contributes no invented scoring term.

This ignores affordability and simultaneous-board-capacity pruning when deriving
the scope. It can therefore require more knowledge than exact search needs.
It does not silently evaluate only favorable known alternatives when an unknown
alternative remains possible. Missing future offers/income/capacity/round weights,
unverified rules and unknown shared transition costs still stop planning.

The scope is constructed separately at the root gate and for each synthetic
transition. The original ban, resource, capacity, source, opponent memory,
cancellation and final revalidation gates remain independent. A scope record is
an explanation, not authorization to execute or bypass those gates.

`Result.support_scope` and the immediate-action `Batch.support_scope` expose:

- `potential_unit_ids` and `purchase_unit_ids`;
- `required_link_ids`;
- `excluded_unknowns` and `required_unknowns`, using explicit parameter keys;
- a criterion identifying conservative declared-horizon support.

The existing result/advice still bind the complete world fingerprint, horizon,
state, ban version and opponent evidence. A newly observed offer, changed rules
or updated ban requires fresh planning/validation. Output retains
`execution_allowed=false` and has no calibrated placement probability.

## Focused evidence and real-game limits

Five focused methods in [`test_strategy_support_scope.py`](../tests/test_strategy_support_scope.py)
check the contrasts above, owned versus offered prices, possible versus impossible
links, and independent invalidation. The ten existing rolling tests, five resource
option tests and two existing simulation bridge/visibility tests pass as well.
The resulting 22-test run rejects native DLL loading and records zero native
Windows calls. No ranker fitting, model training, downloads or game interaction
is involved. Test count is not evidence of playing strength.

```powershell
python -B -m unittest discover -s tests -p test_strategy_support_scope.py -v
python -B -m unittest discover -s tests -p test_strategy_rolling.py -v
python -B -m unittest discover -s tests -p test_strategy_economy.py -v
```

This is a concrete prerequisite for using partially reviewed rule catalogs;
the current rolling implementation still accepts synthetic evidence only.
WXQ card values, prices, links, ban semantics and the client's effective build
remain unverified/unknown wherever no applicable reviewed evidence exists.
This change adds no real-rule registry, OCR adapter, input path or game action.
The [live handoff](STRATEGY_LIVE_HANDOFF.md) and
[resource-objective limits](STRATEGY_RESOURCE_OPTIONS.md) still apply. The
default-off [input diagnostic](EXPERIMENTAL_SINGLE_CLICK.md) remains separate.

## Provenance and license status

This increment is original project code, synthetic tests and English documentation
using only the Python standard library. No third-party implementation, asset,
runtime or dependency is added. MaaWXQ's own license is still undecided; this
increment does not add or change a license. See
[the existing notices](../THIRD_PARTY_NOTICES.md) and
[contribution policy](../CONTRIBUTING.md) for the project's current status.
