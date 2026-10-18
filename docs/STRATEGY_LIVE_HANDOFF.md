# Strategy entry points and live integration handoff

This records the tracked project's code connection, not a successful live-game
run. Its connection audit refers to repository baseline `cf27e5f`; the separately
assigned live task is implementing native input in an independent directory.
That later patch needs its own integration and evidence. The live task owns all
desktop interaction. This
strategy slice inspects files and runs offline tests only; it does not capture,
recognize, focus, click or press keys in the actual client.

## Actual connection status

| Boundary | Current implementation | What it does not establish |
| --- | --- | --- |
| Capture to image | [`capture_one`](../capture_backend.py) returns a capture envelope; `game_recognition` is `waiting_for_game` for a launcher and otherwise `not_validated`; source-frame time can be unavailable | No OCR/entity/cost/phase extractor publishes a complete strategy state here |
| Legacy annotations to strategy evidence | [`legacy_observation`](../strategy/adapter.py) accepts manual opponent/ban records | No trusted entity mapping, confidence, full own position or semantic ban mapping; legacy `unit_ids` are not rolling `board_ids` |
| Reviewed evidence to generic advice | [`reduce_observation`](../strategy/state.py), [`decide`/`filter_candidates`](../strategy/policy.py) and [`RuleRegistry`](../strategy/rules.py) | No activated real gameplay registry or verified action executor is supplied by this slice |
| Synthetic position to adaptive advice | [`rolling.plan`](../strategy/rolling/search.py), optionally with [`EconomyObjective`](../strategy/rolling/economy.py) | This world accepts only `test_rules_not_gameplay` and rejects non-synthetic observations; it is not a real-rule adapter |
| Synthetic advice to an accepted move | [`decision_input`/`rolling_policy`](../strategy/simulation/bridge.py) and [`ToySimulator`](../strategy/simulation/toy.py) | Only toy episode-bound `SimAction` execution; no real pointer/keyboard translation |
| ChildSession action transport at the reviewed baseline | [`ChildSessionBackend`](../backends/child_session/backend.py), [`ControlCore`](../backends/child_session/control.py) and [`DisconnectedInput`](../backends/child_session/ports.py) | `native_transport_not_implemented` and `native_input_not_implemented` block real submissions; supported submissions are explicitly synthetic and never confirm actual execution |

[`main.py`](../main.py) does not call the strategy core or an OCR recognizer;
its replay path maintains manual annotation state. The tracked default
[`config.json`](../config.json) has capture/input flags false. These facts do not
claim that the separate live task lacks private observation tools; its outputs
have not been wired into an executable strategy path in this tracked code.
The live task reports a usable actual-game image region through its separate
capture helper. That does not make this strategy consume recognized state.
The unconnected native-input baseline above must not be described as a prior
successful real click. Even after an independently reviewed native input patch,
the semantic recognition, real-rule and action/postcondition obligations below
still need evidence.

Do not relabel real OCR/manual evidence as synthetic to pass the toy gate. The
strategy outputs and simulation reports retain `execution_allowed=false`.

## Reusable entrances

For version-reviewed real evidence, the generic advisory route is:

```python
state = reduce_observation(previous_state, observation, now=decision_cutoff)
advice = decide(state, reviewed_registry, now=decision_cutoff, policy=policy)
# This returns advice only. An unavailable/unverified registry yields no action.
```

`reviewed_registry` must be a genuine applicable `RuleRegistry`, with verified
ban semantics and rule/source/build/version bindings. No such registry is
manufactured by the resource-option feature. `filter_candidates` can independently
recheck a stored candidate against fresh state and the same reviewed registry.

For the current synthetic strategy experiment, use `rolling.plan(state, world,
opponent_id, now=..., policy=explicit_test_policy, budget=...,
economy=EconomyObjective(...))`. Its immediate `Advice` includes legality and
memory bindings, and `Result.economy`/alternative components explain the ranking.
`rolling.actions.revalidate` rechecks stored legality; it does not approve input
or certify a ranking after the objective changes. The resource-option feature
does not alter the generic real-evidence route.

## Minimum evidence contract

Every `Observation` needs a unique event ID, match-local match/opponent identity,
source reference/kind, timezone-aware observed/ingested times and decision cutoff.
Begin with an explicit matching `match_start`, build/rules version, round, phase
and context confidence. Reset on a new match; do not reuse an old opponent ID or
memory as a global player profile.

Each required value is a `FieldValue` plus `EvidenceField` provenance: status,
value, confidence, last seen, round, phase and source/event reference. Unknown or
ambiguous facts retain null values. An observed empty set requires positive
evidence. Confidence thresholds are engineering gates, not proof of calibrated
OCR accuracy. A UI name alone does not resolve a chess-player/hero/card instance.

The rolling experiment reads these own-position fields, all explicitly observed:

| Fields | Meaning and check |
| --- | --- |
| `credits` | Current spendable resource count; never default unknown to zero |
| `board_ids`, `hand_ids`, `offer_ids`, `discarded_ids` | Resolved unique toy unit IDs, actual current zones/offers; no invented future offers |
| `capacity`, `hand_capacity` | Declared current slot capacities |
| `free_board`, `free_hand` | Must equal capacity minus the corresponding observed zone size |
| `banned_tags` ban event | Confirmed semantic IDs/tags, explicit match scope and ban version; no name-to-ban inference |
| Named opponent `board_ids` | Match-local identity, current round/phase, last-seen/confidence and full/partial coverage |

The toy's unique IDs/closed opponent profiles are not an established real-card
instance or duplicate-copy mapping. Real integration needs its own reviewed
mapping and transition subset. Current rolling memory rejects stale, future,
phase-mismatched, unresolved or unsupported opponent evidence. Partial views
retain plausible alternatives and do not assert that unseen units are absent.

The `World` also declares entity values/roles, interaction effects, legal costs,
income/offers/capacity/round weights and replacement semantics. Unknown required
rules abstain. A current public one-round view does not authorize a longer
horizon. Health is not consumed by this resource-option feature; no health-aware
survival decision has been validated.

## Before a real executor can consume advice

The following are missing integration obligations, not passed acceptance tests:

1. A permitted current custom-room observation and fresh game-window identity,
   process/session binding, geometry/DPI version and usable capture provenance.
   A launcher, host timestamp alone or unavailable source-frame time is not proof
   of a current semantic game state.
2. Version/server/mode-bound real rules and IDs, plus reviewed OCR-to-Observation
   mapping for all fields required by the selected operation. Keep the official
   Yixing patch statement separate from the running client's effective cost.
3. A real semantic-action-to-current-UI-target mapping with independently checked
   phase, target, resources, capacity, bans and game postcondition. It does not
   exist merely because the toy has a `buy`/`replace` move.
4. A fresh final candidate check against current match/state/ban/rule/memory and
   expiry, plus the same window/session/geometry. Drop changed advice and replan;
   never queue the contingent path or retry an uncertain game action.
5. The single assigned desktop executor, explicit run authorization, manual
   pause/emergency stop, generation/lease/heartbeat checks and owned-input cleanup.
   Missing native transport or a failed gate cannot trigger a foreground fallback.
6. Separate actual-action and postcondition observations. A protocol receipt,
   submitted click or high synthetic utility is not proof of game execution.

No item is bypassed by setting a config flag or by selecting a nonzero reserve
weight. The core handoff is ready for a separately reviewed observation adapter;
the recognition-to-real-action loop is **not connected by this slice**.

For later review/data work, retain the visible cutoff state and provenance,
rejected/eligible actions, objective/settings and score breakdown, policy/rule
versions, intervention and separately timestamped outcomes. Preserve unknowns and
do not turn a toy choice into a real expert label. No data platform is added here.
