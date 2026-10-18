# V5 minimal state and strategy API

The V5 screen producer is connected to the persistent Advisor through
`strategy.minimal_screen.project_minimal` and
`runtime.strategy_bridge.ScreenAdvisorBridge`. This is a local integration
milestone. It has not executed a strategy-generated game action.

That statement describes the original V5 bridge milestone. The later
[V8 specialized purchase producer](hand-appearance-evidence.md) automatically
verified one Sun Bin purchase. [V9](DEPLOYMENT_V9.md) later executed a drag whose
placement was confirmed from original images; automatic deployment verification
and a complete match remain unfinished.

## What the real replay established

One previously captured battle image produced OCR candidates for round 4,
45 seconds, and energy 28. Their status stays `candidate`, their core `value`
and confidence stay null, and their original crop hashes/rectangles/raw text
remain in `projection.field_evidence`. The old battle used Bai Ge. Neither a
shop card named Yi Xing nor his equipped skin proves that he is the selected
battle chess player. The scene recognizer detects battle controls, not the
preparation phase or match mode.

`projection.provenance` exposes source kind, explicit live/replay mode,
capture time, processing time, decision cutoff, age, and frame hash. Saved
replay cannot mutate the live Advisor. No replay timestamp is replaced with
the processing time. The six-crop Windows OCR path took approximately 16.5
seconds in the control worker's measured replay. Live bridge ingestion stops
when that original frame is older than five seconds.

## Call the local API

The controller has already created the three records below. `capture_record`
is the exact saved capture JSON; `ui_state` is the independently recognized
state for that hash; `minimal_state` is `maawxq-minimal-state/1`. No private
example capture or machine path is included in source.

```python
from strategy.advisor import Advisor
from runtime.strategy_bridge import ScreenAdvisorBridge, unverified_configuration

advisor = Advisor(unverified_configuration())
bridge = ScreenAdvisorBridge(advisor)  # Keep one instance for this custom match.
result = bridge.observe_frame(
    capture_record, ui_state, minimal_state=minimal_state,
    now=current_utc_iso, source_mode="live_capture",
)
print(result["projection"]["field_evidence"]["resources.energy"])
print(result["projection"]["first_action_requirements"])
print(result["decision"])  # None when replay/stale/not battle; otherwise advisory.
```

The live producer must explicitly set `source_mode="live_capture"` and
`source_capture_reused=false` after a new capture. `run_saved` defaults to
saved replay. Explicit live mode cannot admit a minimal record marked as
reused or saved replay. The live observer passes the shared capture-budget
root to the OCR producer. This example does not authorize input.

Replay an existing capture without starting any desktop operation:

```powershell
python -B -m runtime.replay_strategy --minimal <private-minimal.json> --frame <private-capture.json> --recognition <private-ui-state.json> --now <actual-UTC-cutoff> --output <new-private-replay.json>
```

Or call `runtime.replay_strategy.replay(minimal, frame, state, now=...)`. It
evaluates a new isolated Advisor and returns the projection, observation
records and decision. It uses the original screen source and capture time;
it does not label a real frame as synthetic. The configuration has no reviewed
gameplay rules, so no gameplay proposal is issued.

## First real gameplay milestone

The scoped first-purchase handler is now implemented in
[`runtime.purchase.PurchaseHandler`](PURCHASE_HANDLER_API.md). That limited
transaction uses only confirmed current mode/phase, specified currency/price,
offer target/hero and one visible legal empty hand slot. It does not require
the global registry/build/ban/combat checklist below. The table below describes
the earlier generic Advisor path; use the linked scoped API for the first
purchase. The current OCR candidates are still insufficient for dispatch.

The smallest useful milestone is one verified shop purchase into a verified
free hand slot. `first_purchase_requirements(minimal_state)` returns each
required path, current candidate/confidence, expected evidence and responsible
producer, rather than just generic abstention reasons.

| Input | Current evidence | Deliverable before the first purchase |
| --- | --- | --- |
| Selected chess player | Unknown | Actual in-battle Yi Xing identity or verified selection/confirmation chain |
| Round | OCR candidate 4 | Independently verified integer and confidence |
| Buy-enabled phase | Unknown | Positive preparation/transaction controls; a timer alone is insufficient |
| Energy/currency | OCR candidate 28 | Verified amount and reviewed mapping to strategy `credits` |
| One shop offer | Hero ID/cost unknown | Stable ID, grade, slot, exact target and effective cost for that frame |
| Destination hand slot | Unknown coverage | Full hand-slot coverage and a legal free destination |
| Current match bans | Unknown | Explicit tags, including reviewed semantics for an empty set |
| Client and mode | Unknown build; custom mode lacks a battle binding | Versioned purchase rule tied to this client/custom match |
| Purchase utility | No executable gameplay rule | Reviewed eligibility, fixed/effective cost semantics and score |
| Input/result adapter | No gameplay handler | One bound purchase and independent resource/destination postcondition |

When a future independent recognizer really establishes a value, it can supply
`status="observed", value=<actual>, confidence=<explicit similarity>` using
the existing prototype's uncalibrated confidence convention. Numeric confidence
is not a calibrated probability. The current OCR producer never does this.
`strategy_fields` accepts the explicit core currency/zone fields; energy is
never silently mapped to credits. Selected chess-player identity can only come
from `selection.confirmed`. Round/phase/build/rules fields have their own paths.
All events still pass through the core codecs, reducer and strategy gates.

Full board IDs/positions/grades, opponent identity and coverage, original
opponent timestamps, and reviewed synergy/combat utility are the next stage
for dynamic formations. They are not required to pretend a random manual
target exists: the observed Yi Xing passive copies automatically/randomly at
battle start. Current displayed rule text remains non-executable evidence.

## Deterministic UI inspection already available

`runtime.lobby.recognize(frame)` followed by `runtime.lobby.decide(state)`
recognizes the current encyclopedia/collection context and proposes a specific
inspection transition. For the positively recognized Yi Xing tooltip, all five
regions must match and the operation is `view_yixing_passive_details`; its target
comes from the recognized `view_details` region. An unknown, duplicate, nonfinite
or incomplete region set stops. The actual broker retains its existing identity,
foreground, freshness, tag, interruption and owned-release checks.

This is a usable scene-to-action API for inspection, separate from a gameplay
purchase. These offline integration checks did not execute it. Real custom
match start remains blocked until actual Yi Xing selection and confirmation
are implemented. Public source does not include private reference images,
profiles, receipts or current-client rule-evidence JSON.

## Preserved integration protections

The newer original native broker and owned diagnostic are byte-identical.
V5 changes to `custom_setup.capture` are merged with the existing shared
50 PNG / 64 MiB budget. OCR crops count against that same root and stop before
starting when their reservation would exceed the budget. New lobby and bot
entry points reserve their frame pair/transaction before any input. Broker and
port cleanup are combined and verified before postcondition capture. Input
timestamp checks cover the interval after the one-shot broker closes.

The earlier 18-file reviewed feature commits remain the baseline. This
integration does not modify `main` and excludes private profiles, screenshots,
receipts and client-rule evidence JSON. The control worker separately confirmed
Yi Xing selection/entry; this documentation does not claim a completed
strategy match or a strategy-generated purchase outcome.
