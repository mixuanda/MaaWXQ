# V12: verified ready transitions and reviewed talent selections

Later [V13](ARMY_V13.md) records this V12 match's eventual sixth-place debug
result and a separate new four-unit army trial. Both are excluded from win-rate
samples. The unsettled statements below describe the original V12 handoff.

The control worker ran another authorized five-Xingyao-bot custom game as
positively recognized Yi Xing. It automatically purchased and deployed Li
Yuanfang, then verified ready transitions in rounds 3, 4 and 5. Round 3 used
same-round combat recognition; rounds 4 and 5 used the exact Cancel control.
Each original live result is `ready_verified`, with a distinct after-image,
unchanged game identity/geometry, same parsed round and clean owned release.
The controller checked foreign input before dispatch and after verification.
An already-Cancel control was left alone; unknown results stopped without retry.

This is the reviewed single-unit baseline. It preserves resources while
additional-unit placement is unverified; it does not implement competitive
army development, dynamic opponent formations or a full match strategy.
The private finite cycle ended at its observation budget without an error.

## Two actual talent selections

In the prior debug game, Defense Realm was chosen while only Niumo was
positively identified on the board. Its selected detail name and the visible
damage-reduction description were verified after the three-candidate layout
disappeared. The decision explicitly retained unknown health, full hand,
combat statistics, synergy thresholds and game/talent version.

In the fresh Li Yuanfang game, Keep Progress was chosen over the reviewed
equipment option and the option requiring two named heroes together. The
decision used the readable coupon/experience description without assigning
unknown equipment utility, combat values or victory-dependent benefits.
The new selected detail matched Keep Progress and the player-experience
fragment. The energy-clause OCR contains an error and remains raw evidence.
Neither result verifies coupon redemption, reward delivery, future experience
or the actual effectiveness of the selected talent.

Both original live receipts report `talent_selection_verified`. These are two
specific reviewed readable choices, not a general talent recognizer or ranking
model. Candidates and descriptions must be reviewed again for a changed screen.

## Portable ready and talent evidence API

`runtime.phase_perception.classify(frame)` is the pure phase-anchor portion of
the frozen producer. It recognizes the reviewed preparation, combat/resolution,
draft-preview and talent-anchor layouts, returning unknown for incomplete,
duplicate or nonfinite evidence. Phase recognition alone never authorizes input.
Its private template bank, capture builder and native pixel collection are not
included.

`runtime.transition_verification` contains only pure constructors and verifiers:

| API | Required evidence |
| --- | --- |
| `make_ready_intent(before, match_id=..., ocr=..., source_mode=...)` | Positive preparation, one deployed unit, exact Ready/Start Battle text and parsed round from bound original OCR |
| `verify_ready(intent, after, ...)` | Same-round Cancel/preparation or positive combat, source-bound post OCR, clean single click/release and fresh unchanged window |
| `make_talent_intent(before, match_id=..., candidates=..., selected_index=..., verification_fragment=..., source_mode=...)` | Three distinct readable reviewed candidates, all six name/description anchors, chosen fragment present in the reviewed description |
| `verify_talent(intent, after, ...)` | Old candidate layout gone with all six measurements still present, exact selected name and description fragment from fresh bound OCR |

Retain the intent and its `digest(intent)` before the actual guarded dispatch.
Both verifiers require that retained value as `intent_sha256`, the actual
`submission` and `native` receipts, the original dispatch `started_at` UTC and
current `now` UTC. Preserve the real custom-match origin; a caller-supplied match
string is not independent proof of that origin. These functions do not capture,
click, choose a talent, launch a loop or grant permission to act.

```python
from runtime.transition_verification import make_ready_intent, verify_ready, digest

intent = make_ready_intent(
    before, match_id=verified_custom_match_id,
    ocr=original_before_ocr, source_mode="live_capture",
)
retained_digest = digest(intent)
# The sole authorized controller performs its separately guarded transaction.
result = verify_ready(
    intent, after, intent_sha256=retained_digest, ocr=original_after_ocr,
    submission=actual_click_receipt, native=actual_native_summary,
    started_at=original_dispatch_started_at, now=current_utc_iso,
    source_mode="live_capture",
)
```

OCR bundles retain frame and pixel hashes, exact ROI/scale and uncached dynamic
output. The round ROI is the narrowed [678,7,60,30] header, excluding timer
symbols. The selected-name/description ROIs and ready-control ROI are the
reviewed 1450 x 869 layout. Unknown or malformed round OCR is rejected.
Native verification requires one MOVE+DOWN batch, one owned UP, no held input,
no cleanup errors and exhausted action budget. Source-to-dispatch age stays at
most five seconds; the new result must follow dispatch and remain within eight
seconds. Similarities remain uncalibrated, not probabilities.

Saved replay is the default. Successful replay returns `ready_replay_verified`
or `talent_selection_replay_verified` with `game_postcondition_verified=false`.
Only explicit matching live mode and current evidence can return a live result.
Every result has `blind_retry_allowed=false`; talent results also retain
`rewards_verified=false` and `future_effects_verified=false`.

## Integration evidence and limits

Integration checked 70 frozen sources, 105 evidence hashes, six unchanged native
dependencies and seven archived source hashes. The initial and resumed private
cycle snapshots differ from the final frozen cycle; the pure ready verifier is
identical. These variants remain explicit review history and are not ported.
No private controller, scheduling/resume logic or retention helper is published.
The existing V11 deployment verifier also accepted the new Li Yuanfang evidence
as saved replay through its inspected-shop-art path, without changing that API.

Fourteen original bitmap hashes were rechecked. The deployment, three ready
and two talent results were reproduced through the stricter public APIs as
saved replay only. The old transition receipts lack an exact saved per-click
start UTC (the talent task start precedes its preaction capture), so
retrospective tests explicitly use the original source capture as a
conservative lower bound; they do not invent an exact dispatch timestamp or
replace the live receipts. Current-clock checks reject the saved images.
Synthetic regressions also cover wrong rounds, unchanged controls, unknown
phases, unbound/cached OCR, changed intents/windows, invalid layouts and unclean
release. Integration made no capture, controller launch or game input and did
not modify the control workspace. Private images, paths, profiles, receipts
and patches are excluded.

The first private cycle stopped before input at the OCR width limit. Its resumed
version split the hand region and retained the original deadline, observation
budget, capture ledger and cumulative action limit. Historical failures remain
unchanged. This publication does not reset budgets or adopt private frame
retirement: the shared public limit remains 50 PNG / 64 MiB, stop-on-full,
without deletion. Native guards and MaaFramework 5.7.2 remain unchanged.

## Results and next work

The old debug match's sixth place is explicitly excluded from win-rate samples:
it included long development pauses and the single-unit baseline. The fresh
match has no final placement in this frozen handoff. Eligible win-rate samples
are zero; no win-rate estimate or full-strategy success is supported. Combat
and draft-preview observations alone do not establish strategic decisions.

The next implementation task is separately verified additional-unit placement,
then army development using current hand, board and energy evidence. The
existing first-unit adapter still requires an empty board and must not be
silently reused for that task. General talent recognition, varied round OCR,
actual build/version, opponent coverage and dynamic formations remain gaps.
