# V17: shop normalization verified, five-unit strategy still blocked

Later evidence and stricter input-free guards are recorded in
[V27](AUTO_CHAIN_V27.md): bounded talent-detail recovery, three later automatic
deployment records, and a refused room transaction. Five of five remains
unverified; the historical V17 limitations below are preserved.

In one preregistered bounded diagnostic, the sole control worker normally closed
the shop once in round 4 and again in round 5. Each close retained the same
current round-title pixels and preparation controls, then recaptured and checked
the current population, capacity and next empty cell. After the second close,
Pig Bajie was deployed from the owned hand, increasing population from 1/5 to
2/5 alongside Ganjiang Moye.

The deployment receipt says `deployment_verified` with
`method=bound_model_visual_postcondition`: the selected unit, Sell ownership and
2/5 were confirmed by bound image review. This is not a wholly automatic name
and numeric postcondition. Native release was confirmed with no held button or
cleanup errors.

Both live pre-close scenes already had readable population/capacity. The old
V16 shop-obscured counter failure is covered by replay of its actual saved
image, not a newly reproduced live occlusion-and-recovery sequence. The
demonstrated live result is two normal shop closes with fresh post-close checks.
Neither this distinction nor the original V16 refusal is discarded.

## Surface decisions before deployment checks

`runtime.surface_gate.inspect_surface(frame, expected_count, target_cell)` is a
portable, input-free adaptation of the frozen decision gate. It returns an
advisory action with `execution_allowed=false` and `blind_retry_allowed=false`.
Its reviewed client geometry is 1450 x 869; observed population scope is 0 to 4.

The ordering is intentional:

1. Unknown preparation controls wait. The winning preparation anchor must be
   at least .97 with at least .02 separation.
2. A known selected-owned-unit panel is proposed for dismissal first. A Sell
   panel with an unknown name stops; it is not silently treated as shop UI.
3. The own-player portrait must be positively recognized before a shop close.
   Two current price anchors establish the reviewed shop scene.
4. A recognized shop may be proposed for dismissal even when population is
   covered or missing. That unknown count never permits deployment.
5. Only a new uncovered scene with current count, capacity and one positively
   recognized target empty cell returns `deployment_surface_ready`.

Count/capacity thresholds remain .97 with .02 separation from competing count
templates. Missing, duplicate, nonfinite or ambiguous measurements fail closed.
Template values require independently reviewed reference images; they are not
standalone numeric OCR. The gate's output does not prove a hero, numeric round,
custom origin, freshness or native input permission. Those remain independent
controller requirements. No native executor or private capture worker is added.

## Shop-close evidence contract

`verify_shop_close` checks a distinct before/after pair, unchanged identity and
geometry, original dispatch/release times, clean one-click native receipts and
a fresh restored surface. The after image must follow confirmed release, not
just dispatch start. The source-to-dispatch age stays within five seconds and
the new result within eight seconds.

The supplied round-title comparison must bind both frame hashes, the exact
[678,7,60,30] ROI and similarity at least .97. If both numeric OCR readings are
valid, different rounds are rejected. An unchanged title-pixel comparison may
bridge malformed numeric OCR for this close only. Every later deployment still
needs a parsed current round and fresh independent preaction validation.
Preparation/count/empty-cell checks are not waived.

```python
from runtime.surface_gate import inspect_surface, verify_shop_close

decision = inspect_surface(before, expected_count=known_count, target_cell=next_cell)
# The sole authorized controller handles this advisory decision through its
# existing one-attempt native guard and produces the actual release receipt.
check = verify_shop_close(
    before, after, expected_count=known_count, target_cell=next_cell,
    title_anchor=bound_round_title_comparison,
    submission=actual_click_receipt, native=actual_native_summary,
    started_at=actual_dispatch_utc, released_at=confirmed_release_utc,
    now=current_utc_iso, source_mode="live_capture",
)
```

Default saved replay returns `shop_close_replay_verified` with
`game_postcondition_verified=false`. Explicit current live evidence can verify
the close only; `deployment_verified` and `execution_allowed` remain false.
No failure or uncertain result authorizes a repeated close. Producers must hash
the original bitmaps, bind their comparisons and preserve actual capture times;
metadata booleans alone are not independent perception or authorization.

## Preserved failures and stopping boundary

The first diagnostic entry stopped before input after malformed round OCR.
Its zero-action receipt remains unchanged. The later bounded entry used current
preparation controls and before/after title-pixel identity for shop closing,
while keeping numeric-round validation for gameplay actions.

The fill continuation reached a talent overlay in round 6; it was still open
in the last round-7 observation. The minimal branch waited, and the old talent
footer matcher was below .97. No talent selection was attempted. The declared
30-observation fill budget stopped the controller; aggregate diagnostic usage
was 109/120 captures. No active worker remained in the frozen final check.
These historical images do not establish the game's present screen.

Five units were not verified and no new complete baseline was started. The
diagnostic was classified before launch and is not baseline four. The three
prior baseline ranks remain [6,6,6], with zero champions/top-three finishes in
those recorded runs; no long-run win-rate inference follows. Full strategy
remains unfinished.

The native shop click took .088 s and stable post-close capture 2.322 s. Pig
Bajie's drag-to-identity image took 1.953 s; review-confirmed completion took
13.969 s, including 11.914 s waiting for review. Median fill capture with hand
scan was .800 s. These separate scopes do not demonstrate a fast fully automatic
preparation loop. Next work is complete round/phase-aware talent handling and
lower review latency, then live 5/5 verification before another fixed baseline.

## Integration verification

Integration checked five frozen source hashes, 318 evidence hashes including
ten frozen PNGs, 229 preregistered source hashes and six unchanged native
dependencies. The corrected private patch hash was verified; the failed
intermediate newline package remains history and is not published.

Four actual V16 replay cases retain the expected decisions: covered counters
propose shop dismissal, known details propose detail dismissal, unknown details
stop and settlement waits. Both V17 shop-close pairs pass the stricter public
postcondition only as saved replay; current time rejects the old images.
Nine original image hashes were checked. Synthetic tests cover scene ordering,
unclean release, image ordering, changed windows, duplicate/invalid evidence,
title binding, numeric round disagreement and no-effect/no-retry behavior.

Private images, profiles, receipts, identities, local paths, diagnostic runners
and larger private budgets remain outside this public subset. Integration made
no capture, focus, controller launch or game input, and did not edit the control
workspace. The public 50 PNG / 64 MiB no-deletion budget, native ownership/
foreground/identity guards and MaaFramework 5.7.2 remain unchanged.
