# V42 guarded lineup feedback loop

This version connects the existing Advisor to the actual Windows click and drag
brokers. `runtime.lineup_runtime.LineupRuntime` selects, submits and independently
verifies purchases, player upgrades, refreshes and deployment in one match loop.
It is default-off. Importing or constructing it performs no capture, process
launch or Windows input. This change was verified offline; no new game was run.

## Behavior that addresses the stalled baseline

- A sourced future lineup can contain more units than today's observed capacity.
  It is no longer discarded before the Advisor can recommend leveling. Actual
  deployment still requires a currently observed legal empty own-board cell.
- While the shop is positively visible, affordable remaining target cards are
  bought before closing it to deploy owned targets. Every purchase requires a
  fresh observation; unrelated cards are not bought. There is no per-round
  first-purchase quota. Holds, upgrades and refreshes never close the shop.
- A visible needed card blocked by the declared leveling reserve no longer
  prevents an affordable, independently quoted upgrade toward the search goal.
  Neither capacity, a hero's level, card quality nor stars supplies player level.
- Confirmed refresh cost/count accumulate across rounds in the same bridge.
  Unknown outcomes latch pending both in the runtime and the native executor;
  repeated calls cannot dispatch the same transaction again.

These fixes do not establish better placements or resource utilization in a real
match. The previously observed high unspent balance is a motivation, not a new
benchmark result. Exact card odds and future shop probabilities remain unknown.

## Connect the sole host controller

Use this commit as one version, after the current controller has stopped. Do not
overlay individual files into an active frozen run. Keep one runtime instance
for one match and retain the host's existing aggregate attempt/capture budgets.

```python
from runtime.lineup_runtime import LineupRuntime

runtime = LineupRuntime(
    reviewed_lingbao_policy,
    observe=host.observe_projected_frame,
    observer=host.observe_window_identity,
    before_input=host.reserve_and_check_current_action,
    clock=host.utc_iso,
    enabled=host.explicit_input_enabled,
    close_shop=host.close_shop_once_with_raw_receipt,
)
results = runtime.run(max_steps=host.remaining_feedback_steps)
```

`observe()` captures/projects a new frame each time. Reusing its timestamp is
rejected. `attach_current_state` joins current same-frame facts and OCR with
`EconomyUI.parse` and the existing projection. Producers must supply the
`frame_sha256`/`captured_at` envelopes; the adapter cannot stamp old measurements
as live. Pass `source_mode` explicitly. At least eight observed preparation
seconds are required before a new action. The loop stops on hold/uncertainty
instead of polling, closing the shop or guessing a fallback purchase.

`before_input(frame, intent)` executes the host's existing pause/stop, verified
custom-room origin, capture reservation and cumulative attempt charge. Its
receipt must contain `custom_room_verified`, `no_other_humans_verified`,
`postcondition_reserved`, `attempt_charged` all true, plus the matching
`match_id` and `frame_sha256`. Those values must describe completed checks,
not a constant success dictionary. Preserve the 50-image / 64 MiB stop-on-full
limits and no-deletion policy. A stopped, uncertain or exhausted run cannot
restart those budgets by constructing a new runtime.

The default `GuardedLineupExecutor` uses the existing `GameClickPort` and
`DeploymentDragPort`: foreground/window/geometry validation, exclusive native
ownership, foreign-input cancellation, owned-button release and Ctrl+Alt+F9
remain active. Runtime `pause()`/`stop()` are also checked by the native watchdog
and final permit; `resume()` never clears an uncertain transaction. The native
adapter only targets the verified Unity Windows game. It does not add an ADB,
emulator, memory, injection or anti-cheat workaround route.

`close_shop` is the host's existing guarded close adapter. It is called only for
an Advisor-requested owned deployment. Return raw `action="close_shop"`,
`before_sha256`, `started_at`, `released_at`, `submission`, `native_summary`.
The runtime itself obtains the after frame and requires positive hidden-shop
evidence, unchanged current units/resources and clean release in the same round.
Unknown results remain pending. Closing is never counted as deployment.

## Current producer bindings

The existing complete `recognized_zones.board/hand` contract remains mandatory.
Hand slot IDs must stay tied to physical positions even when identical cards
exist. Empty purchase slots also require `legal=true` and positive classification.
Projection exports observed hand bindings with their confidence and bounds.

Each recognized shop offer can carry `ui_binding`, bound to current frame,
identity and geometry, with `status="observed"`, confidence at least .97,
`hero_id`, `purchasable_verified=true`, `rect` and `target`. It becomes
`strategy_ui_bindings.offers[offer_id]`. Selection must equal the Advisor's exact
demand offer, price and currency. No cheapest-card or whole-shop fallback exists.

For deployment, supply current `recognized_deployment` with the same binding
tokens/confidence, `board_slot_id`, `rect`, `target`, and positive
`empty_verified`, `own_board_verified`, `legal_verified`. The starting point is
the selected physical hand slot. No fifth position or expanded board coordinate
is inferred. Postconditions require that exact hand instance to disappear and
the selected hero to appear in the bound board cell, preserving other units.

Current bound facts include `timer`, `shop_visible`, and, only when positively
proven, `shop_hidden_verified`. Hidden shop projects an empty offer list so the
Advisor can deploy without carrying old offers forward. Mere failure to detect
the shop remains unknown. Purchase completion requires exact spend and exactly
one new selected hero in a previously legal empty slot; an old same-hero image
or unchanged hand count cannot satisfy it. Automatic merging that changes these
expected physical transitions stays unproven and is not retried.

## Player-level and paid-refresh readers

`EconomyUI` accepts reviewed `scalar_readers` for `player_level` and
`level_up_target_level`. Each has a distinct semantic source, ROI, anchor and an
optional full-match `pattern` with named `value` capture. Population ratios,
upgrade-cost labels and unrelated hero-level strings do not match a player
scalar. Target level must be independently observed; there is no implicit +1.

`quote_readers.refresh_cost/level_up_cost` provide `text_key`, `rect`,
`anchor_id`, `pattern` with named `value` capture and `semantic_source`.
`actions.paid_refresh` and `actions.level_up` need a positively matching
`enabled_anchor_id`, `rect` and `target`. Missing price is unknown, never zero.
Paid-refresh cost is read each time, not supplied as a constant. Conflicting
upgrade quotes disable that action. All OCR must match the original frame hash
and time. Free refresh still needs its literal current label and positive count.

The saved Windows frame reviewed for V41 shows free refresh and an upgrade cost;
it does not establish player/target levels or the paid-refresh layout. No real
profile for those missing readers is activated or published here. The control
owner must obtain their actual UI evidence and a real Lingbao policy, then bind
the complete zone producer before this version can take those live actions.
The previously rejected saved-frame OCR worker was not retried or bypassed.

## Single-version acceptance

The controller owner should freeze this commit together with its actual reviewed
profile, Lingbao policy, recognition references and host callbacks. In the allowed
custom room, inspect a short trace for demand-only purchases, quoted upgrades,
budgeted refreshes, one close before a deployment batch and actual slot changes.
Count spending and deployments from independent receipts; do not equate sent
events, loop iterations or shop closes with success. If a required reader stays
unknown, report that specific gap instead of resuming the old arbitrary filler.

Offline checks cover the full wired adapter path with native ports replaced,
plus the affected Advisor/projection regressions. They do not prove OCR accuracy,
Windows authorization, game acceptance, final rank or strategy improvement.
