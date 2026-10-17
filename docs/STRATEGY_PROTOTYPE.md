# Offline strategy prototype

English is authoritative. This is a deterministic advisory core, not a real-game
Yixing AI. It provides no playing-strength results, capture, OCR, game input,
ranked automation, combat simulator, learned model or automatic rule verification.
The research targets of at least 50% firsts and 75% top-three finishes at Xingyao
and above remain untested goals.

## Run and inspect

Python 3.10 or newer and the standard library are sufficient. From the repository root:

```powershell
python -B -m strategy --fixture examples/strategy_synthetic/scenario.json --allow-test-rules
python -B -m strategy --fixture examples/strategy_synthetic/scenario.json
python -B -m unittest discover -s tests -p "test_strategy_*.py" -v
python -B -m unittest -v test_state
```

The first command recommends a synthetic operation; the second abstains because
synthetic rules require explicit opt-in. These commands read the supplied fixture
and print JSON. They do not import the shared CLI, inspect windows, access the
network, write game state, or send mouse/keyboard input. A recommendation is
never execution permission, even when all hard constraints pass.

## Contracts and data flow

The independent strategy schema is `1.0`. Unsupported versions raise an error;
there is no silent migration. Frozen dataclasses use immutable tuples. The
shared `state.schema.json`, CLI, capture code and configuration remain untouched.

| Contract | Purpose and bindings |
| --- | --- |
| `Observation` | Match/event ID, observation/ingestion time, source reference, round/phase, confidence, coverage and optional resolved opponent ID. Start/end events delimit matches. |
| `FieldValue` | Explicit `observed`, `unknown` or `ambiguous`; unknown/ambiguous values are null. Observed empty lists are represented by empty tuples, not by unknown. Confidence is null or an uncalibrated number in [0, 1]. |
| `MatchState` | Current match and revision, game/rules versions, evidence watermark, context age, own fields, identified opponent memory, persistent confirmed bans and ban revision. |
| `EvidenceField` | One field and its event ID, source reference, `last_seen`, round and phase. Evidence remains inspectable after reduction. |
| `CandidateAction` | Semantic operation, optional opponent target, bound predicates and evidence, resource costs, state/rule/ban versions, registry content digest, domain, expiry, expected observable results and invalidation conditions. No coordinates or input commands. |
| `Decision` | Selected candidate or null, all rejected/accepted alternatives, rejection codes, score components and evidence IDs, policy settings, domain and limitations. `execution_allowed` is always false; placement probabilities are null. |
| `Outcome` | Separate decision/candidate-linked record of a human or unknown actor, observed changes, uncertain/non-executed status and intervention. It cannot be passed into the observation reducer or used as future decision evidence. |

`observation_from_dict` and `registry_from_dict` are the JSON ingress points;
`to_dict` emits JSON-ready records. `python -m strategy` replays one annotation
fixture at an explicit frozen decision time. Future observation **or ingestion**
times are rejected. There is no background loop or wall-clock dependence in the
decision functions.

## State and identity rules

Use a new match-local ID for each match and a stable slot/identity for each
resolved opponent. Names, chess-player names and hero names are not identity
keys. Two unknown opponents remain two unresolved events; they do not become one
opponent called `unknown`. Unit/entity IDs require external resolution; no name
lookup is inferred here.

The reducer is pure. Repeating the same `(match_id, event_id)` and content returns
the same state without incrementing its revision. Reusing that ID with different
content raises an error. Unique late events remain in the append-only current
match event tuple, but older round/time evidence cannot overwrite a newer field
or roll the context backward. Missing fields never imply a sale, zero resources
or empty board, including when coverage is marked full. A complete list must be
explicitly annotated as a field value; partial lists describe only what was seen.

A new `match_start` clears fields, opponent memory, bans and active event history.
Only retired match IDs remain to ignore delayed old-match events, including old
start events. A non-active match produces no recommendation. Match IDs must never
be reused. The reducer is intended for small offline logs; disk-backed history,
retention limits and a streaming workbench remain future work.

Confirmed bans with at least 0.8 annotation confidence are monotonic within one
match. Their constraints survive ordinary age expiry. Later unknown/low-confidence
ban evidence blocks advice without erasing already confirmed bans; a later
observed-empty set cannot remove them. This conservative prototype does not
support in-match unbanning. That behavior requires verified rules and a new
explicit contract. Every accepted ban update increments `ban_version`; all old
candidates then fail validation.

The reducer does not infer effects of a proposed or reported human action. After
any material action or uncertain outcome, explicitly re-observe or mark affected
fields unknown in a new state event before asking for further advice. There is no
blind retry path and no automatic application of expected results.

## Rule and policy boundary

`RuleRegistry()` is the default real-game registry: empty and unverified. It
cannot recommend an action. No current Yixing ability, economy threshold, copy
timing, eligible target, equipment effect, synergy, ban object or combat mechanic
is encoded as a real-game fact.

A rule record supplies its reviewed source reference, verification status,
operation, legal phases, explicit prerequisites, resource costs, affected ban
tags, expected results and score definitions. The enclosing registry binds the
game build, rule version, provenance domain and reviewed ban semantics. Rule
source references are data supplied by a reviewer; setting `verified` is a trust
assertion, not a verification service. Record source statements, review dates,
effective versions and interaction evidence before populating a gameplay
registry. Conflicting or unverified rules reject dependent candidates. Any rule
content change changes the registry digest, even if a version string is reused.

`generate_candidates` proposes one immediate operation per supplied rule, or per
resolved opponent when that rule explicitly requires opponent evidence. It does
not invent operations or infer the next opponent. The resource/capacity framework
uses explicit observed fields and numeric predicates; composition roles and
benefit fields remain annotations, not an evaluator of real game formations.

`filter_candidates` checks match lifecycle, known context, freshness, confidence,
game/rule build, verified ban semantics, observed bans, rule verification, phase,
resolved targets, costs, capacity predicates, evidence and candidate bindings.
All gates run before scoring. Unknown critical evidence rejects the dependent
candidate. Unknown bans or stale/unknown global context reject every candidate.
Synthetic evidence cannot enter a gameplay-domain recommendation.

`decide` scores only accepted candidates as `sum(observed_value * weight)`.
Every term includes its field, value, weight, contribution, definition and event
ID. Duplicate scoring fields within a rule are rejected to avoid accidental
double counting. These are uncalibrated heuristic points, not placement or win
probabilities. Stable candidate IDs break ties deterministically. Nonfinite
inputs/weights and score overflow are rejected.

Defaults are engineering limits: context and required field age <=30 seconds,
same round and phase, confidence >=0.8, advice lifetime 5 seconds, at most 64
candidates. Policy settings are included in the decision. They are not verified
game-validity rules. Confirmed bans are exempt from ordinary TTL; their source
must still be available at the decision time. There is no search, plan queue,
calibration, anti-oscillation tuning or playing-strength model in this version.

Before reusing any candidate, call `filter_candidates` against the current state,
registry and clock. Changes in state revision, match, round, phase, watermark,
ban revision, rule version/content, payload, prerequisites or expiry revoke it.
Even valid candidates remain advice only. This check is not an input safety gate.

## Existing JSONL bridge

`strategy/adapter.py` can convert legacy events without importing `main.py` or
changing the shared schema. Its caller supplies a new match ID, stable event ID,
ingestion time and optional round/phase, and must first supply `match_start`.

Legacy observations lack event IDs, reliable match boundaries, confidence and
coverage. The adapter labels confidence unknown and keeps unresolved hero or
opponent IDs unknown. Historical lineup labels, including an empty legacy ban
list, do not prove verified semantic ban IDs; they become unknown bans. It does
not manufacture decision-ready evidence from the old file.

## Verification and next evidence

Nine focused offline tests cover hard bans before high scores; ban persistence
and revision invalidation; unknown rules/bans/resources/confidence; resource,
capacity, phase, round and age limits; exact-event idempotency and conflicting IDs;
late/future evidence; opponent identity, partial views and match reset; changed
rule/payload rejection; legacy uncertainty; separate outcomes; deterministic CLI
execution with capture/network/input modules blocked. The synthetic fixture is
explicitly `test_rules_not_gameplay`, and it requires opt-in. These tests validate
structural invariants, not correctness of game mechanics or game performance.

Before a useful real decision can be evaluated, the project still needs:

1. Current, reviewed Yixing **chess-player** rules: triggers, timing, costs, legal
   targets, randomness, copied properties, capacity/overflow and interaction order.
2. Verified ban semantics and IDs, plus the economy, capacity, phase and formation
   rules needed by each supported immediate operation.
3. Sanitized, permitted manual annotations of complete decision points: own
   resources/board/hand/choices, opponent slot identities and visible fields,
   timestamps, rounds, confidence and explicit unknowns. Keep private source
   captures, accounts and raw replays outside Git.
4. Separately linked observed outcomes and blind human review of frozen decisions,
   split by whole match and game version. No future frames or final placement may
   enter decision inputs. Real-match performance evaluation needs separate scope
   and authorization; no ranked automation is authorized here.

This implementation follows the supplied strategy architecture's offline
contract/reducer/rules/baseline subset. It has not passed a real-replay usefulness,
shadow-operation, custom-room execution or playing-strength gate.
