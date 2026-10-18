# Focused synthetic boundary review

Target: `8f20727314071f920fc960fce2af05d69c2a9675`.
This is a finite offline review of the integrated adapter, especially its
clock-failure and final-audit fixes. It does not run a third-party simulator,
connect to the game, download/train a model or measure real playing strength.
The worker's original delivery used a separate task snapshot and did not modify,
stage, commit or push the integrating repository.

Historical reproduction record: the findings below refer to the named target
commit and the worker's F1-only patch. The integrating repair resolves F1, F2
and B1 as described under "Integration resolution and strategy use" below.

## Findings

### F1: rejected audit payload remains in the failure report (local fix supplied)

Location: `strategy/simulation/runner.py`, `report`'s export/validation block.

At the target commit, `events = adapter.export_events()` retains the response
before validating it. When the response is `None`, a list, an arbitrary object,
or a tuple containing an invalid element, the report becomes
`failed/audit_export_failed` but its `audit_events` still contains that response.
For an arbitrary object, `to_dict(report)` then raises `ValueError`; a rejected
string-list payload can instead be serialized into the failure report. An
`AuditEvent` with malformed nested action/ledger values also passes the shallow
type check, potentially producing a completed report that cannot be serialized.

Minimal reproduction, with imports and `end_round` as shown below:

```python
sim = ToySimulator()
sim.export_events = lambda: object()
report = run_episode(lambda: sim, end_round, seed=7,
                     scenario="synthetic-economy-v1", clock=lambda: 0)
# Target commit: failed/audit_export_failed, but type(audit_events) is object.
to_dict(report)  # ValueError on the target commit.
```

The supplied local patch validates into a temporary `exported` variable,
checks nested JSON serialization with the existing `to_dict`, and retains the
tuple only after validation succeeds. Invalid exports leave `audit_events=()`.
It preserves single export, stable failure codes and no action retry. Six
malformed payload shapes are covered by the new regression test. This is
structural/serialization validation, not audit authenticity or rule validation.

### F2: completion is not reconciled with the audit (reproduced; suggestion only)

The target commit and the supplied F1-only patch both accept these independent
fault injections as `completed`:

1. `sim.export_events = lambda: ()`: an end-round-only episode reports three
   accepted steps but zero audit events.
2. Wrap `terminal_result` to replace its final credits with `999` after the
   real toy terminal is reached. The reported terminal balance is `999`, while
   the last exported ledger balance is `5`. Terminal receipt consistency checks
   only whether a result exists, so it does not catch conflicting values.

Minimal reproductions:

```python
sim = ToySimulator()
sim.export_events = lambda: ()
report = run_episode(lambda: sim, end_round, seed=7,
                     scenario="synthetic-economy-v1", clock=lambda: 0)
# completed; steps == 3; len(audit_events) == 0

sim = ToySimulator()
original = sim.terminal_result
def inconsistent_terminal():
    value = original()
    return replace(value, final_credits=999) if value is not None else None
sim.terminal_result = inconsistent_terminal
report = run_episode(lambda: sim, end_round, seed=7,
                     scenario="synthetic-economy-v1", clock=lambda: 0)
# completed; terminal.final_credits == 999; last ledger.credits_after == 5
```

Suggested next bounded fix: first specify the synthetic audit contract (reset
event, accepted-step coverage, sequence/revision binding and terminal linkage),
then reject absent/incomplete traces and compare final round, credits and board
against the final accepted end-round ledger. Verify ledger continuity and
conservation before counting a result. Do not impose an undocumented one-event
per-step rule on future adapters without declaring that mapping. This handoff
does not change that contract or silently claim F2 is fixed.

### B1: action identity does not distinguish episodes (interface boundary)

Two fresh same-seed fixtures do have independent state. However, `SimAction`
contains only player, revision and `Move`. An action issued by the first
instance at revision zero compares equal to a legal action in the second
same-seed instance and is accepted there. This is not a hidden-state leak or
shared-state mutation; it means per-instance state isolation does not imply
cross-episode intent rejection.

```python
first, second = ToySimulator(), ToySimulator()
for sim in (first, second):
    sim.reset(7, "synthetic-economy-v1")
foreign = next(a for a in first.legal_actions(PLAYER) if a.move.kind == "end_round")
second.step(foreign)  # accepted, revision 1
```

The current harness supplies only the fresh request's legal tuple, so this
requires a caller to reuse an equal action across runs. Before asynchronous or
external-engine integration, add an explicit episode binding to requests and
actions and reject mismatches. Define deterministic comparison separately from
unique run identity; do not expose seed/hidden RNG as that binding. No protocol
change is bundled in this small test increment.

Shared reproduction imports/helper:

```python
from dataclasses import replace
from strategy.contracts import to_dict
from strategy.simulation.runner import run_episode
from strategy.simulation.toy import PLAYER, ToySimulator
def end_round(request):
    return next(a for a in request.legal_actions if a.move.kind == "end_round")
```

## Coverage and evidence

New file: `tests/test_strategy_simulation_boundaries.py`.

Fixed seeds: `0, 1, 7, 42, 4294967313, 18446744073709551615`.
These include the accepted 64-bit maximum; they are fixture inputs, not a sample
of real matches or a denominator for win rates.

| Check | Scope and evidence |
| --- | --- |
| Independent accounting/legality oracle | 6 seeds x 3 scenarios; plain set/integer specification never calls production `transition`, `move_reasons` or `moves`. Covers every supported move kind. |
| Resource path | Compare every resulting board/hand/offer/discard zone and balance; check non-overlap, declared charges, no sale refund, entry income and final terminal state. |
| Illegal-action atomicity | At every oracle trace state, inject wrong revision, absent target and unsupported sale; compare full audit state including RNG, public observations and event sequence before/after rejection. |
| Reproducibility and state independence | Repeat six seeded episodes with global RNG noise and another interleaved fixture; reports remain equal and the other instance remains unchanged. |
| Hidden-state metamorphism | Across six seeds, mutate future permutations, private opponent reserve and RNG state; current visible request and existing rolling-policy choice remain equal. Past visible evidence remains equal after round advancement. |
| Clock faults | 69 stage/fault combinations: initial reading, after factory/reset/observe/legal/policy, immediately before step, after step, terminal confirmation and final audit. Inject exceptions, NaN, infinities, bool, string and regression where applicable. |
| Clock-fix outcome | Every injection fails closed with `monotonic_clock_unavailable`; zero later actions, at most one audit export, no counted terminal and no raw exception detail. Initial-clock failure prevents factory creation. |
| Budget edges | Deadline just below/exactly at limit; elapsed-time invariance under shifted origins; exact step budget two vs three over six seeds. A negative origin is valid; a regressing reading is not. |
| Cancellation | A one-check pulse during policy prevents step; cancellation observed during final audit wins without subsequently calling a failed clock. |
| Final-audit fix | Existing single-export regression plus new boundary/fault matrix pass; malformed top-level and nested payloads now fail cleanly with an empty, serializable audit field. |

At the target baseline, the initial new test run passed seven test methods and
failed the invalid-export regression at four top-level payload subcases. Nested
payload cases were then added to the regression. After the local F1 fix:

```powershell
python -B -m unittest discover -s tests -p "test_strategy_simulation*.py" -v
```

Result: **26 passed** (18 existing simulator tests plus 8 new methods), Python
3.13.12, 0.791 seconds for this run. Parameter combinations are reported above
separately from unittest's method count. The broader strategy/capture/control
suites were not rerun: neither policy core nor those backends changed.

## Integration resolution and strategy use

F1 exports are validated before retention and malformed nested payloads are
discarded. F2 now requires the explicit fixture mapping of one reset plus one
event per accepted submitted action, ordered sequence/revision/episode binding,
visible-position continuity and resource conservation. Completion also matches
the final end-round ledger's round, credits and board. Missing/incomplete audits
fail with `audit_integrity_failed`; conflicting terminals fail with
`terminal_audit_mismatch`, without a counted result or a second export.

B1 now binds metadata, observations, views, decision requests and actions to a
fresh seed-independent episode ID. The engine rejects foreign intents atomically;
the bridge rejects mixed views/actions. Deterministic comparison uses
`contracts.replay_record`, which normalizes that ID only and cannot authorize an
action. Actual action equality and execution checks retain the unique binding.

Two focused methods cover completion/audit conflicts and cross-episode rejection
in addition to the worker's existing cases. The earlier clock/final-audit fixes
remain in place. No new simulator mechanism, model dependency or test matrix is
added. Stop infrastructure work at this correction: valid synthetic traces can
now support comparisons of current-card selection, spending/holding credits,
declared pair/threshold value and paying replacement costs versus keeping a
formation. These are decision-boundary checks for the strategy core, not real
game mechanics or win-rate labels.

## Rule and verification limits

- The accounting oracle is for the invented five-unit, three-round fixture. It
  is not an independent model of WXQ shops, card pools or economy.
- The passive opponent and unique unit IDs cannot validate multiplayer play,
  duplicate copies, combat, health, elimination, rankings or opponent scheduling.
- Yixing copying, actual synergy thresholds, shop tiers/odds/pool/XP, damage
  scaling, combat timeout, refresh/lock/sale/refunds and skill/equipment order
  remain unverified. No third-party constants are adopted as game rules.
- Hidden-state tests prove the supplied adapter's projection on tested mutations,
  not a sandbox for hostile Python policies or arbitrary external adapters.
- Cooperative cancellation/deadlines cannot preempt blocking callbacks. Clock
  fault injection verifies control flow, not a real-time latency guarantee.
- F2 and B1 were not fixed in the worker's F1-only patch; the integration repair
  above addresses them. No real-game test or real win-rate conclusion is included.
