# V41: current-state projection and one advised economy transaction

The lineup Advisor now has a portable state/transaction adapter. It projects
confirmed current recognition into the existing state store, recomputes lineup
demand before dispatch, and records refresh/level-up success only from a fresh
independent postcondition. This integration made no game input or new capture.
It does not establish live resource-use or strategy improvement.

## Connect current recognition

`strategy.state_projection.project_frame` returns `batch`, `ui_bindings`, gaps
and unknown fields. The default is saved replay. A current producer must
explicitly pass `source_mode="live_capture"` and preserve the actual capture
time and hash. Facts must carry matching `frame_sha256` and `captured_at`.

Resource value zero is distinct from unknown. A failed numeric recognition does
not yield zero credits: the numeric result must be known and agree with the
bound current facts, or an independently bound credits field must be supplied.
Currency mapping requires an explicit verified source. Unrelated defaults are
not substitutes for the current balance, quote or player level.

Full board/hand zones require current frame, identity and geometry tokens,
confidence, `coverage="full"`, `overflow_checked=true` and resolved slots.
Unmatched hero templates cannot establish empty slots. A positive current
zero-population glyph can prove an empty own board; nonzero population cannot
resolve its heroes. Equal heroes retain distinct physical slot IDs. Interactive
hand bindings additionally require actual bounded slot rectangles; a shared
hero/template name cannot distinguish two physical cards by itself.

`strategy.shop_facts.recognize_offers` reuses supplied current template/numeric
measurements. Its optional OCR input has the same frame/time envelope, with
texts under `values`. Unknown names/prices remain unknown. Faction annotations
need their own source; no private faction table or image catalog is included.

`runtime.economy_ui.EconomyUI` loads caller-provided reviewed references and
parses frame-bound OCR values. It recognizes a literal free-refresh label/counter
and an upgrade button quote. An upgrade button saying `5升级` does not establish
the current or resulting player level. Those require separate reviewed readers.
No real reference images or machine-specific UI profile are published.

## Use the same Advisor and match budget

`runtime.lineup_bridge.LineupBridge(policy)` imports the existing public Advisor
normally; it does not load code from an arbitrary `advisor_root` path. Policy
format is `v41-lineup-policy/1`, with actual sourced `plans`, optional reviewed
`upgrades`, provider `in_game_lingbao` and a match-scoped `spending` object.
The spending object supplies reference, reserve, level/copy reserves and refresh
spend/count caps. An empty/pending recommendation is rejected, not replaced with
a guessed lineup or arbitrary first purchase.

```python
from runtime.lineup_bridge import LineupBridge
from runtime.economy_actions import EconomyActionHandler

bridge = LineupBridge(reviewed_policy)  # Keep this instance for the same match.
handler = EconomyActionHandler(bridge)
result = handler.run_one(
    observe=current_capture_and_projection,
    dispatch=existing_guarded_click_adapter,
    clock=current_utc_iso,
)
```

`observe()` returns a current frame containing `strategy_batch` and
`strategy_ui_bindings`. Missing fields revoke their previous current values,
including prices and affinity inputs. Opponent history remains in the existing
match reducer. Round changes do not reset refresh spending; switching matches
requires a new bridge. The host must preserve this instance/ledger for the match;
durable process-restart recovery is not implemented here.

Saved projections cannot mutate the live bridge. `select_purchase` resolves the
Advisor's exact offer instance/name/price; it is not a cheapest-card fallback.
Buy/deploy input and completion still belong to their independently verified
existing handlers. A bare `completed(..., verified=True)` is deliberately
rejected; this integration does not supply a new duplicate-purchase or deployment
completion verifier.

## Submission and result are separate

`EconomyActionHandler.run_one` obtains a fresh observation and recomputes policy.
It only dispatches refresh or player-level upgrade suggestions. Target, label,
enabled state, frame/geometry, quote/currency, funds and the actual demand/budget
must agree. It latches the transaction pending **before** calling the supplied
guarded dispatch, so an exception or unknown result cannot become a retry.
The helper has no native port; the callback must retain all existing foreground,
exclusive ownership, interruption, emergency-stop and capture-budget checks.

`dispatch(frame, intent)` returns actual `action`, `before_sha256`, `started_at`,
`released_at`, `submission` and `native_summary`. The last two use the existing
clean one-click/owned-release receipt contract. The after frame must follow
confirmed release, remain fresh and retain game identity, geometry, match, round
and preparation phase.

`verify_action` requires the exact currency delta. A refresh additionally needs
resolved current shop slots with at least one changed hero identity; an identical
reroll remains unproven even if it may have happened. A level-up additionally
needs the quoted target **player** level. Hero level, quality and unit stars
cannot replace it. `LineupBridge.complete_economy` derives this result from the
raw new frame and native receipt. Only a verified refresh updates the match
count/spend ledger. Otherwise pending stays latched and no input is retried.

Review also found a private merge path that checked hero-level growth after a
star-upgrade opportunity. That is not proof of unit-star synthesis. It was not
ported. Private bootstrap/opening launchers and historical-template shortcuts
are likewise excluded; an empty initial roster is not an observed empty board,
and the known automatic-player-selection gap is not considered resolved.

## Remaining real-data gaps

Complete nonempty board/hand recognition, actual Lingbao lineup configuration,
current player/target levels and paid-refresh UI remain incomplete. The visible
free-refresh layout is not evidence that refresh or level-up has been exercised
live. Exact card odds remain unknown. The adapter therefore holds when its
required facts are missing; it cannot make the current private baseline ready
for unattended play merely by installing these files.

Validation used only small in-memory projection/transaction fixtures, changed
source syntax, patch/source integrity and privacy checks. No new full suite or
expanded replay campaign was added. Native input dependencies, public capture
limits and no-deletion policy are unchanged; no personal desktop images, raw
receipts, machine paths or private controllers are published.

The private saved-frame OCR worker was rejected by PowerShell
AuthorizationManager/UnauthorizedAccess before OCR startup. This integration
did not retry it, alter ExecutionPolicy, elevate it or use another launch route.
That saved-image OCR capability remains blocked.
