# Synthetic rolling planning slice

This is **test_rules_not_gameplay**. All units, links, thresholds, opponents,
offers, income, capacities and utility numbers are invented fixture declarations.
The results below are engineering contrasts, with zero real-room observations
and zero measured game results. No value is a win rate or a placement probability.

## Run and integration

Python 3.10+ and the standard library suffice, from the isolated slice root or
the repository root after integration:

```powershell
python -B -m strategy.rolling --fixture examples/strategy_synthetic/rolling/scenarios.json --allow-test-rules
python -B -m unittest discover -s tests -p test_strategy_rolling.py -v
```

Without `--allow-test-rules`, the CLI abstains. There is no training, download,
network, game capture, login, input, API, credentials, GPU or additional package.
Output is stdout unless the caller explicitly supplies `--output`. Regenerate:

```powershell
python -B -m strategy.rolling --fixture examples/strategy_synthetic/rolling/scenarios.json --allow-test-rules --output examples/strategy_synthetic/rolling/report.json
```

The handoff's `INTEGRATION_MANIFEST.json` lists additions and hashes. Integrate
only those additions. The copied `strategy` core files, old fixtures and
`test_strategy_core.py` are baseline dependencies for isolated development;
they are excluded from the patch. Do not replace `strategy/planning` or any
existing file. This preserves the integrated evaluator/hold and unavailable
snapshot fixes. The new module independently tests the same behaviors.

## Distinguishing contrasts

| Contrast family | Immediate recommendation | Completed declared utility |
| --- | --- | --- |
| One-round objective, A deployed, B/C offered | Buy B | 7 in that round |
| Same state, two-round objective with declared D offer | Buy C; keep one credit | 26 over two rounds; the B-first alternative totals 14 |
| Same two rounds, D banned | Buy B | 14; the three-role threshold cannot be completed |
| Fresh complete guard opponent view | Deploy C | 11 |
| Fresh complete breaker opponent view | Deploy B | 7 |
| Only the shared enemy unit observed, partial coverage | Deploy B under worst case over guard/breaker | 7 |
| A/B deployed, C/E in hand; credit switching cost 1, utility cost 2 | Replace B with C | 9 after switching cost |
| Same state after C is banned | Replace B with E | 8 after switching cost |

The tests additionally show that increasing the declared switching utility cost
to five preserves A/B and ends the toy round, and that four declared rounds
retain the C investment with total 66. These are related synthetic contrasts,
not independent matches, training examples or a playing-strength evaluation.

## Modules and contracts

- `model.py`: frozen versioned world, positions, moves, exact local transitions,
  pair bonuses, and role-count thresholds. A threshold counts distinct deployed
  units with the role, activates once, and stacks with pairs only as declared.
- `memory.py`: a named opponent's match-scoped evidence, source/event provenance,
  confidence, coverage, timestamps and round age. Complete views must match a
  declared profile. Partial views retain every declared profile containing the
  observed units. Unseen units are not treated as absent. Both the sighting and
  the board field must be fresh; a newer sighting without a refreshed board
  cannot refresh the old board by association. The board's observed phase must
  be known and match the current phase; other-phase evidence cannot silently
  stand in for the current lineup.
- `actions.py`: dynamic immediate moves bound to current `MatchState` evidence,
  world content, planning horizon, opponent memory and the shared core hard
  filter. Resource, capacity, confidence, ban, version and expiry checks precede
  evaluation. Canonical payload comparison rejects edited targets or bindings.
- `search.py`: bounded depth-first receding-horizon planning, dominance pruning,
  complete-path incumbents, cooperative cancellation and final revalidation.
- `demo.py` and `__main__.py`: opt-in synthetic fixture input and JSON report.

The shared core contracts remain unchanged. The new position adapter reads
`credits`, `board_ids`, `hand_ids`, `offer_ids`, `discarded_ids`, `capacity`,
`hand_capacity`, `free_board` and `free_hand`, plus the state's current round.
These are new strategy fields, not changes to the capture/state JSONL schema.
Missing or unknown fields never become empty lists, zero resources or defaults.

`World` has domain `test_rules_not_gameplay`, schema `toy-rolling-world/1`, an
explicit build/rule version and full content digest. Its default verification is
unverified. Optional numeric/rule fields may carry `None`; a requested horizon
with unknown utility, price, cost, offer, income, capacity or round weight causes
abstention. An unavailable world, unsupported real data, unknown ban target,
stale state/memory or unresolved opponent identity also causes abstention. The
core reducer scopes memories to a match, deduplicates observations and discards
old-match updates. The planner has no global memory or replayed plan cache.

The result schema is `advisory-rolling-plan/1`. It contains one immediate
`selected` advice envelope with the core candidate's preconditions, state/rule/
ban versions, expiry, expected results and invalidation conditions. Every
alternative carries a complete **analysis-only** path, round-by-round value
breakdown and resource ledger. `execution_allowed` is always false and
`placement_probabilities` is null. Reobserve after any material action and call
`plan` again; continuation labels cannot be sent to an executor.

## Explicit transition and objective limits

Buying consumes credits and an actual current offer, placing one unique unit in
hand. Deployment consumes the declared deployment cost and one free board slot.
Replacement consumes both declared resource and utility costs, discards the old
unit, and deploys a held unit. There is no refund or automatic sale. Banned IDs
or tags forbid acquisition/deployment/replacement of those units; they do not
silently evict already deployed units. Direct interaction-ban semantics are not
defined: an undeclared ban target causes abstention.

An `end_round` simulation settles the current board's declared utility. When
another modeled round remains, it adds the next round's declared entry income,
applies its declared capacity and replaces the shop with its declared offers.
Owned or discarded unique IDs cannot appear again. A capacity decrease requiring
an unsupported removal invalidates that branch. Current snapshot credits already
include current-round income; it is never added again. The final settlement does
not add another income or round. `hold` changes nothing and is a safe fallback,
not a branch that manufactures time or resources.

The objective is the sum of weighted round formation utilities minus utility
switching costs. Undeployed units and leftover credits have no terminal utility.
The toy contains no combat, health, elimination, selling, copy mechanics, chance
draws, discounting or survival model. Future offers/income/capacity are fully
declared synthetic inputs, never predictions of a real shop. This deterministic
fixture cannot support conclusions about a stochastic game economy.

Current-round evaluation uses fresh memory's compatible scenarios. Every future
round expands to **all** declared opponent profiles. The score takes the worst
profile independently in each round, so an adversarial opponent may change
profiles between rounds. No persistence probability, uniform distribution or
calibrated belief is invented. A real lineup outside this closed toy support
cannot be evaluated.

## Budgets, failures and integration checks

Defaults: two rounds, at most three preparation actions per round, 2,048 expanded
transitions and one second of wall budget. Supported caps are four rounds, four
preparation actions, 10,000 nodes and five seconds. Round settlement also counts
as an expanded node. The action cap is a search restriction, not a game rule.
Dominance pruning compares the same future position, action budget and first
move; it retains the greater accumulated utility. End-round branches are visited
first to establish complete baseline incumbents early.

`horizon_exhausted` means all paths within these modeled restrictions were
explored. Node/time exhaustion may return the best **completed** incumbent with
status `budget_limited` and an explicit warning that unexplored paths may be
better. Without a complete incumbent it returns a revalidated `hold`. Cancelling
always clears the selected action. Once cancellation is observed in a request,
it stays latched even if a later callback poll returns false. An unavailable/failed
evaluator also returns
a revalidated hold. No fallback bypasses freshness, state/rule/ban binding or the
memory gate.

Before returning advice, `latest_snapshot()` may supply the latest observed
`MatchState` and `World`. A missing, failed or invalid snapshot causes abstention.
Changed bans, memory, state, rules, expiry or unknown evidence revoke old advice.
Use `actions.revalidate` again before presenting any stored advice. There is no
input permission implied by this check. Budget checks surround bounded local
operations; arbitrary blocking evaluator/snapshot/clock callbacks cannot be
preempted. This is not a hard real-time deadline or an input watchdog.

The ten focused tests cover horizon conflict and resource accounting, fresh/
partial/changed opponent evidence, new-match isolation and duplicate events,
ban-driven alternatives and switching costs, unknown rules, budgeting/cancellation,
evaluator fallback, final snapshot failures, cancellation pulses, opponent phase
ambiguity and forged targets/horizons. The real
CLI is exercised with capture, input, network and heavy-model imports blocked.

## Later custom-room observation: pending human readiness

Current work is offline only. No login, screenshot, capture, game interaction or
room validation has occurred. Later observation remains pending the user's
explicit login-ready signal and coordination with the observation thread. A
custom room does not supply permission for ranked automation. The current
planner accepts only synthetic evidence, so real observations cannot activate
its toy rules.

After readiness and a separately reviewed observation plan, useful human-driven
custom-room scenarios are: resource changes before/after one purchase and one
deployment; a verified pair/threshold activation or loss; one clearly identified
opponent changing lineup across observations; a ban or capacity constraint; and
one replacement with independently observed costs. Use matched before/after
observations to check the declared rule proposal. Do not assume these scenarios
exist or have the toy semantics; unknown or unavailable mechanics remain gaps.

`room_observation.template.json` is an empty record specification, explicitly
ineligible for the synthetic planner. Record:

- Observation/run ID, explicit consent/readiness reference, custom-room mode,
  pseudonymous match/opponent IDs, build/patch, round/phase and decision cutoff.
- Source, observed/ingested timestamps, coverage, each field's last_seen, value
  status and uncalibrated confidence; resources, units, offers and ban evidence.
- Reviewed rule references/version/digest and unresolved semantics; current
  candidate, hard rejections, budget, selected advice, rationale and expiry.
- Human intervention and actual action separately from the suggestion; observed
  outcome/time/source separately from decision-time input, without future leakage.

Stop the scenario immediately on a stop request, missing consent/readiness,
unexpected ranked/public mode, login/security/account prompt, private information
exposure, identity/round/phase ambiguity, stale or conflicting evidence, unknown
cost/ban semantics, a version change, an invalid recommendation, unavailable
snapshot, capture/input failure or unmet time budget. Record the reason and
leave the action unexecuted; do not guess a correction or switch modes.

Keep real-room records separate from `report.json`, with their real provenance.
Do not publish screenshots, account identifiers, private paths or unredacted logs.
Any promotion from a rule observation to active real rules needs its own reviewed,
version-bound adapter and validation; these synthetic numbers cannot be promoted.
