# V11: actual automatic purchase and deployment verification

Later [V12](SUSTAINED_V12.md) verified ready transitions in rounds 3, 4 and 5
and two separately reviewed talent selections. The pending statements below
describe V11. Full strategy and win-rate evaluation remain incomplete.

In the approved custom game with five Xingyao bots and no other human players,
the control worker positively recognized Yi Xing and automatically bought Niumo
for three energy. The purchase verifier confirmed energy 6 to 3 and the added
hand card. It then submitted one bounded owned-card drag and automatically
returned `deployment_verified` with an empty rejection list. Verification
completed at 2026-10-18 22:34:52 UTC.

The live result combined hand count 3 to 2 with both original cards preserved,
population 0/5 to 1/5, a new component at the intended drop, purchased shop-art
similarity 0.97958 versus competing art 0.09101, and the owned-unit sell label
similarity 1. Population and unit ownership were measured on the same new
selected-unit screenshot. Native receipts confirmed owned release and no
cleanup errors. These are results of that particular live transaction, not
general inventory accuracy or a complete strategy match.

## Capacity correction and historical outcomes

The earlier V9 capacity labels 0/3 and 1/3 were transcription errors. The
unobscured selected-unit panel shows capacity five; the correct labels are
0/5 and 1/5. Current `DeploymentDragBroker` therefore requires `capacity=5`
and rejects the old value three. All its other protections remain unchanged.
This is a fixed observed layout restriction, not a general game rule.
The public drag receipt now records `released_at` immediately after the owned
release completes, for the evidence verifier's release-to-capture ordering.

Original private V9 records and failed/unverified V10 receipts remain unchanged.
A retrospective capacity or pixel correction does not turn those historical
attempts into live success. V11's Niumo result is a separate newly executed and
automatically verified transaction. The earlier [V8](hand-appearance-evidence.md)
and [V9](DEPLOYMENT_V9.md) milestones retain their original verification status.

## Portable evidence API

`runtime.deployment_postcondition` has no capture, focus, click or input APIs.
It adapts the executed V11 evidence contract with additional strict type,
finite-score, geometry and provenance checks. Its supported path is the actual
`inspected_shop_art` method, for the reviewed 1450 x 869 first-unit layout,
three-card hand, empty capacity-five board and destination (710,555). The private
world-model shortcut and weaker name/art fallback are not included.

The sole controller must first obtain an actual successful purchase and a fresh
recognized deployment source. Bind the purchased shop bitmap and exact offer
slot from the dispatched purchase, then retain the intent unchanged:

```python
from runtime.deployment_postcondition import (
    intent_from, bind_inspected_evidence, verify_deployment,
)

intent = intent_from(
    pre_drag_frame, match_id=actual_match_id, hero_id=actual_purchased_hero,
    shop_frame_sha256=actual_purchase_source_sha256, offer_slot=actual_offer_slot,
)
# The separately authorized controller submits one guarded drag, saves its
# release receipt, and produces fresh post-drag and inspected-owned-unit frames.
evidence = bind_inspected_evidence(
    intent, post_drag_frame, selected_owned_unit_frame,
    inspection_target=recognized_new_unit_center,
    shop_frame_sha256=actual_matcher_shop_source_sha256,
    source_mode="live_capture",
)
result = verify_deployment(
    intent, actual_drag_receipt, evidence,
    now=current_utc_iso, source_mode="live_capture",
)
```

The producer must hash each original bitmap, validate identity/geometry around
capture, retain original capture times and use those exact images for matching.
The selected-unit producer supplies `detail_board`, `deployment_detail` and
`unit_owner_score` from the same frame. The post-drag producer supplies
`deployment_pixels.hand` and `deployment_pixels.new_unit`. The matching shop
source must be the actual dispatched purchase frame. Caller-supplied flags or
typed objects alone do not establish these facts or grant input permission.

The verifier independently checks:

- Intent digest, match, hero, purchased shop hash and selected offer slot.
- A complete single drag, exhausted action budget, owned release and empty
  cleanup errors. An uncertain or partial gesture cannot verify.
- Original source-to-release age at most five seconds, increasing source,
  release, post and inspection times, current UTC and unchanged identity/geometry.
  Post frames may be at most ten seconds old; inspection frames at most five.
- Preserved passive/equipment positions, scale and similarity, removal of the
  purchased hand card, and a spatially bounded new component at the drop.
- Population 0 to 1 with capacity five, bound to the selected-unit frame, plus
  independently checked shop-art score, competitor margin and owned-unit label.

The new `shop_frame_sha256` and `offer_slot` intent fields strengthen the public
purchase-to-deployment binding. Offline adaptation of the original private
receipt explicitly adds these fields and recomputes only the replay digest;
it does not alter or replace the original live receipt.

Both functions default to `source_mode="saved_replay"`. Successful replay returns
`deployment_replay_verified`, `evidence_verified=true` and
`game_postcondition_verified=false`. Explicit live mode also requires matching
evidence mode and current timestamps; stale or reused frames are rejected.
Only successful live verification returns `deployment_verified`. Every outcome
has `blind_retry_allowed=false`. This module does not implement a dispatch loop
or automatically inspect a unit; any inspection click remains a separately
guarded, bounded controller transaction.

## Exact pixel source and verification limits

`runtime/deploy_transition_pixels.cs` is byte-identical to the frozen source
used by the actual V11 trial, SHA256
`0dc3cd53b5d4dea7d54b1d968abcd1ea2c0065e081b4651b5b2cbc96439329a2`.
It contains only bitmap comparisons and connected-component analysis. Its
bounded tilted-card search covers the observed 17-pixel panel offset. The
selected shop card competes against other distinct offer identities. Supply
four bounded identity labels using the existing `matcher_labels` convention.
These similarities are uncalibrated, not probabilities.

Integration verified 58 frozen source hashes, 13 executed-source hashes,
37 evidence hashes and six unchanged native/handler dependencies. It rechecked
four original bitmap hashes and reproduced the evidence result only as saved
replay using the recorded historical clock. Current time rejects those old
frames. Python/fake-native regressions exercise the public contract and existing
drag protections without opening native APIs. Integration did not recompile or
rerun the C# matcher, capture, launch a controller or send game input; its pixel
execution evidence is the exact source bound to the original live trial.

## Round observation and remaining work

The later finite run recorded 15 observations, recognized rounds 3, 4 and 5,
and submitted one ready click in each. It observed preparation, battle or
resolution, draft preview and unknown scenes. The round-3 after-frame showed
combat; visual review showed Cancel after the other two ready clicks. Every
ready receipt still has `game_postcondition_verified=false`. These observations
do not constitute a general ready/Cancel postcondition validator. Draft preview
was wait-only; unknown scenes received no input. An alternative talent scene
remained unknown, and malformed round OCR was rejected.

The public round parser is now backed by these actual round observations, but
the path-bound private cycle is not published here. Next work at V11 was a
ready/Cancel verifier, varied round/talent recognition and a finite match policy;
V12 adds the reviewed ready/talent paths.
Buying/selling decisions, talent choice, opponent-aware formation and win-rate
evaluation remain unfinished. Seeing combat or draft preview is not evidence
of those capabilities. Foreground mouse interaction in this approved bot-only
custom game does not establish background input or general held-key safety.

Private images, profiles, receipts, authorization records, local paths and the
private patch stay outside public source. Shared capture limits remain 50 PNGs
/ 64 MiB with stop-on-full and no deletion. The private retention helper is not
ported. MaaFramework remains pinned to 5.7.2.
