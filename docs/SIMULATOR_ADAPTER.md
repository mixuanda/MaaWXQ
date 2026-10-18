# Offline simulator adapter

This is an **original synthetic fixture**, not a WXQ simulator or a source of
real win-rate evidence. It adds a small offline boundary around the existing
strategy types. No third-party simulator code, game assets, model, dependency,
network call, training or live-game operation is included.

The increment was prepared against strategy baseline
`eff3dcd367aed9a53e90325f7810d13ded62b8a2`, including the earlier planning work
at `c7220215097b1caa12ab1e145ce01883954179a1`. Existing strategy, capture, input,
configuration and state files are unchanged. The implementation was prepared
as an add-only handoff; the integrating thread reviews and publishes it separately.

## Contract and lifecycle

The importable `SimulatorAdapter` protocol is in
[`contracts.py`](../strategy/simulation/contracts.py):

| Method | Result and obligation |
| --- | --- |
| `reset(seed, scenario)` | Called once on a fresh instance; returns audit-only `EpisodeMetadata`. Unknown scenarios and invalid seeds are errors. |
| `observe(player)` | Immutable `PlayerView` with the player's visible `Observation` history and public current-round `World`. No engine object or full-state reference. |
| `legal_actions(player)` | Immutable `SimAction` tuple using the existing `Move`; bind seat and current revision. Terminal episodes return no actions. |
| `step(action)` | Atomically reject illegal/stale actions with `IllegalAction`; accepted steps return a `StepReceipt`. Unexpected exceptions are unconfirmed outcomes and end the harness run without retry. |
| `export_events()` | Audit-only immutable event sequence with existing `StepTrace` resource-ledger entries. Not an observation or policy input. |
| `terminal_result()` | `None` until actual terminal confirmation; then a typed `TerminalResult`. A step receipt, action limit or deadline alone is insufficient. |

`ToySimulator.audit_snapshot()` is an additional test-only full-state channel,
deliberately outside the protocol and `PlayerView`. It includes hidden offer
sequences, private opponent reserve and RNG state. Only tests/auditors use it.
Create a new simulator for each episode; calling `reset` twice is rejected.
`run_episode(factory, policy, ...)` calls the factory for every run. The caller
must supply a fresh-instance factory, not a pooled mutable engine.

This first fixture supports only `player-0` and a passive synthetic opponent,
`opponent-0`. Other observer/action seats are explicitly unsupported. It does
not establish multiplayer, concurrent turns or a functioning opponent policy.

## Information boundary and existing strategy

The allowed path is:

```text
engine private state -> observe(player) + legal_actions(player)
  -> decision_input(...) -> immutable DecisionInput -> policy -> one SimAction
engine metadata / audit_snapshot / export_events / terminal_result -> auditor
```

`decision_input` replays only visible, synthetic `Observation` records through
the existing `reduce_observation` reducer. It uses `MatchState`, `World`, `Move`,
the existing opponent-memory checks and candidate resource gates. Every step
produces fresh own-state and public-opponent evidence; the bridge rebuilds on
each decision, so a previous continuation is never queued for execution.

The policy receives its own hand and current shop, public opponent board and
bans. It receives no opponent hand, hidden offer order, future offer outcomes,
seed, RNG state, reset metadata or audit handle. Synthetic source references and
match IDs contain no seed. Historical own observations are permitted information.

Only the current round's `RoundRule` is projected into the policy's `World`.
The demonstration `rolling_policy` therefore requests `Budget(horizon=1)` with
explicit synthetic-rule opt-in. Requesting two rounds correctly abstains with
`round_transition_unknown`, rather than revealing future offers. Extending to
multi-round uncertain futures requires a separate reviewed belief/scenario
projection; do not pass the private engine `World` to recover the old four-round
search. The existing search core is unchanged.

The original `CandidateAction`/rolling result still has
`execution_allowed=false`. The bridge matches one selected immediate `Move`
against the simulator's current legal-action tuple. This authorizes only a toy
state transition; it creates no game-input authorization or `Outcome` actor.
The reused `StepTrace.analysis_only=true` also remains appropriate for this
offline audit. No live execution semantics were added to existing contracts.

Frozen dataclasses and a one-way API help prevent accidental information leaks;
they are not a sandbox for hostile Python policy code. An external adapter must
implement a reviewed visibility projection. The bridge checks its declared
synthetic domain and frame shape, not arbitrary source-specific hidden fields.

## Original fixed fixtures and accounting

[`fixtures.py`](../strategy/simulation/fixtures.py) defines three anonymous
fixtures: `synthetic-economy-v1`, `synthetic-zero-budget-v1` and
`synthetic-banned-v1`. All constants below are invented engineering values.

Each episode has three preparation rounds, two board slots and two hand slots.
It starts with `unit-a` on board. The economy fixture starts with three credits;
the zero-budget fixture starts with zero. The ban fixture bans `unit-c`.
Buy moves one distinct offer to hand and charges its declared price. Deploy
costs zero. Replace costs one credit and one synthetic utility point, discards
the outgoing unit and provides no refund. Entry into rounds two and three adds
one credit. Ending round three confirms completion and adds no further income.
Hold changes no resources but consumes a step/revision in the harness.

For each round, a local `random.Random(seed)` shuffles the five unit IDs. The
first two still-available IDs become the visible shop when that round begins.
Owned/discarded units cannot be drawn again. Unbought previous offers can return.
This is not a shared card pool, rarity model or real shop distribution. The
private opponent reserve is an opaque synthetic marker; it never acts in combat.

Every accepted action records credits before/after, spending, entry income,
board, hand, offers, capacity, discard and switching utility cost. The invariant
is `after = before - spent + income`. Rejected actions change neither state,
revision, observations, audit events nor RNG state.

[`seed7.json`](../examples/strategy_synthetic/simulation/seed7.json) freezes an
original seven-action trace with three completed rounds. Its final board is
`unit-a, unit-c`, final balance is one credit and `unit-d` is discarded. These
are expected test outputs, not recorded gameplay or an optimality claim.

## Provenance, termination and failures

Every successful reset records engine name/revision, engine Git commit, source
digest, Python version, strategy baseline commit, rules version, scenario ID/content digest,
seed, supported mechanisms and unknown mechanisms. The adapter does not resolve
its checkout revision and honestly records `engine_commit=null`; it never mislabels
the strategy baseline as the commit containing the new engine. `engine_source_digest` hashes the new
simulation modules and reused model/contracts/reducer, with line endings
normalized. The integrator should bind the eventual containing commit in its
evaluation manifest after committing. Preserve the source digest as well.

Record the Python version with experiment evidence. The demonstrated runtime
is Python 3.13.12. Seed reproducibility is scoped to the same fixture, source
digest and runtime/RNG implementation; it is not promised across arbitrary
engine or Python upgrades. Deadline truncation and scheduling-dependent policy
budget exhaustion must be recorded separately; a seed cannot reproduce wall-clock
load. Event timestamps use deterministic synthetic time,
not wall-clock gameplay or perception measurements.

`run_episode` defaults to 32 accepted steps and two seconds, with validated upper
bounds of 256 steps and 30 seconds. The demonstration planner has its own 256-node,
0.2-second budget. Cancellation is latched within a run; it and the monotonic
deadline are checked around decision/engine callbacks and before every `step`.
Late cancellation/deadline during final audit export also revokes completion.
Unavailable, nonfinite or regressing monotonic-clock readings fail the run before
another action. Failure of a final control check revokes completion without
retrying the already completed audit export.

`completed` requires an explicit terminal result, a consistent terminal receipt
when produced by `step`, and successful audit export. `truncated`, `cancelled`
and `failed` reports have no counted terminal result. A hold loop or partial run
never becomes a placement. Policy abstention, illegal/stale advice, unavailable
observations, exceptions and terminal/receipt mismatches stop immediately.
Exceptions are reported with stable stage codes, without copying potentially
private third-party exception text. A step exception may have occurred after a
mutation: inspect audit evidence and discard that run; never automatically retry.
Audit export failure itself makes the report failed.

These are **cooperative** limits. A blocking factory, policy, engine, audit
export or cancellation callback cannot be forcibly preempted in process.
Use a separately supervised worker process and bounded transport before running
an untrusted/slow external engine. No process supervisor or external runtime is
implemented in this slice.

## Run and verification

From the repository root, without opening the game:

```powershell
python -B -m strategy.simulation --allow-synthetic-fixture --seed 7
python -B -m unittest discover -s tests -p "test_strategy_simulation.py" -v
python -B -m unittest discover -s tests -p "test_strategy_*.py" -v
```

The CLI requires explicit synthetic opt-in and emits a JSON audit report. It
imports no capture/UI backend and adds no runtime dependency. The original
worker handoff reported 15 focused tests, 44 combined strategy tests and
36 state/capture/child-session/control offline tests passed. Integration adds
three clock/final-control regressions, bringing focused simulator coverage to
18 tests. The full strategy-discovery command also executes earlier planning
ranker fits; use focused simulator tests for a no-training review.
The worker's first root-suite run hit the host sandbox's redirected temporary-directory
permissions; setting `tempfile.tempdir` to a workspace-owned scratch directory
resolved it, with no product-code changes or native calls.
The seed-7 demonstration completes seven actions/three synthetic rounds.

Tests cover reproducibility and independent instances; reset/lifecycle errors;
hidden-state mutation without policy-view changes; fresh reducer/strategy
integration; refusal of an undeclared future horizon; fixed resource ledger;
unknown/illegal/stale/banned/unaffordable actions without mutation; early/final
terminal behavior; bounded no-op loops; time/cancel arriving inside callbacks;
exceptions after mutation without retry; receipt mismatch; policy failure or
abstention; and failed/late final audit export.

No real match, real room observation, measured placement, win-rate evaluation,
training, model download, external-engine execution or live interaction occurred.

## Integrating an external engine later

1. Select an engine with an explicitly reviewed license and pinned source
   revision. Keep third-party code/runtime outside this original increment.
   Review its rules and data against a named actual game version first.
2. Implement the six protocol methods in a separate adapter. Use a fresh engine
   instance per episode; preserve engine/rules/source/seed/capability metadata.
   Map unsupported facts to explicit unknowns, never invented defaults.
3. Project legal visible state into existing `Observation` records with stable
   synthetic player/unit IDs and monotonic event/revision bindings. Keep hidden
   state and future RNG entirely inside the engine/auditor. Publish only known
   rules and observed outcomes to the policy. Unit-instance identity, duplicate
   copies and any new resources need an explicit mapping beyond this small toy.
4. Translate only the immediate `Move`/candidate supported by the engine and
   recheck actor, revision, target, phase, resources and bans at the step boundary.
   Preserve atomic illegal-action rejection, append-only events and audited
   conservation. Stop uncertain transport/step outcomes without retry.
5. Return terminal results only after a complete engine match, with explicit
   cause and the engine's supported result semantics. This first contract only
   reports synthetic completion; introduce a separate reviewed result schema
   before adding actual placement or multi-player evaluation.
6. Run these contract tests against the adapter plus source-specific visibility,
   resource and terminal checks. Add supervised process cancellation/timeouts
   before relying on hard deadlines. Keep synthetic engineering results separate
   from any future held-out real-rule evaluation.

`ns2250225/wanxiangqi` at
[`2f9ef5af1c782f205960f66b3a47124c9b8b9ae5`](https://github.com/ns2250225/wanxiangqi/tree/2f9ef5af1c782f205960f66b3a47124c9b8b9ae5)
is excluded under the task's provenance restriction. The earlier research notes
are carry-forward context, not a rules re-verification in this slice. No source
from that project was fetched, copied, installed, imported or executed here.

## Unverified real-rule table

Every row is unsupported for actual gameplay. Third-party behavior mentioned
in prior notes is not adopted as truth.

| Mechanism | Carry-forward uncertainty | Fixture behavior / requirement before real integration |
| --- | --- | --- |
| Shop tiers and rarity odds | Actual version and distribution not verified | Seeded permutation only; obtain versioned authoritative odds. |
| Shared card pool, duplicates, return/recycle | Counts, instance identity and refund rules unknown | Five unique synthetic IDs; no real pool or duplicate merging. |
| Level/upgrade experience | Costs and progression not verified | No levels/XP; require explicit reviewed transitions. |
| Refresh, lock and sale | Costs, persistence and refunds unknown | Unsupported; no guessed refund. |
| Combat damage | Previously reported third-party scale `0.5` is unverified | No combat; verify health/damage formula and event order independently. |
| Combat duration | Previously reported third-party `45s` limit is unverified | No combat clock; verify actual timeout and tie rules. |
| Chess-player Yixing copying | Triggers, targets, limits, persistence and UI version unknown | No copying; do not substitute same-named hero rules. |
| Links, thresholds, skills and equipment | Current thresholds and interactions not verified | Invented pair/threshold utility only; no gameplay meaning. |
| Economy and survival | Income/interest, losses, health and elimination unknown | One invented entry credit; no health or survival model. |
| Bans and opponent scheduling | Objects/lifetime and match assignment not verified | One explicit synthetic ban and passive public opponent. |
| Terminal placement and strength | No validated real-rule match population | Synthetic completion only; placement is null and real-match count is zero. |

Real-game screenshots, startup, input and match tests remain paused until the
user explicitly announces an available custom room and authorizes resumption.

## Increment file list

All ten files are additions; no existing tracked file is modified:

- `strategy/simulation/__init__.py`
- `strategy/simulation/__main__.py`
- `strategy/simulation/contracts.py`
- `strategy/simulation/fixtures.py`
- `strategy/simulation/toy.py`
- `strategy/simulation/bridge.py`
- `strategy/simulation/runner.py`
- `examples/strategy_synthetic/simulation/seed7.json`
- `tests/test_strategy_simulation.py`
- `docs/SIMULATOR_ADAPTER.md`
