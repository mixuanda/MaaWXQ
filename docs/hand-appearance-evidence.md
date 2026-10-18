# V8: automatic purchase verified; deployment pending

This heading describes the V8 checkpoint. Later [V11](DEPLOYMENT_V11.md)
automatically verified a separate Niumo purchase and deployment. Full strategy
and ready-action postconditions remain incomplete.

Later [V9 deployment evidence](DEPLOYMENT_V9.md) records a Li Yuanfang drag whose
placement was confirmed by original-image review. Its live deployment
postcondition is still unverified. The V8 events below retain their outcomes.

The control worker's recorded Sun Bin purchase automatically returned
`purchase_verified`: energy changed from 6 to 3 and the spatial detector found
the purchased hero added to the hand while preserving both original cards.
The unchanged PurchaseHandler verified both postconditions with no reasons and
no blind retry. The original after image was captured at 21:30:07.6226148 UTC;
verification had completed by 21:30:08.893302 UTC on 2026-10-18. No source
timestamp was replaced with processing time.

This is separate from the earlier Yao purchase. That original transaction was
visually confirmed but its hand-name OCR gate failed; its receipt is not changed
to automatic success. V8 does not depend on that OCR fallback.

The subsequent single click on Sun Bin opened his details card, with the card
still in hand. Deployment is unverified. No board destination, drag operation,
double-click operation, complete match, win rate or broader keyboard safety is
claimed by this milestone. The current guarded purchase adapter remains one
short click; implementation of deployment requires its own observed transition
and postcondition.

## The specialized hand detector

`runtime/hand_appearance.cs` is image-only and byte-identical to the frozen
matcher used in the actual successful controller run. `HandAppearance.Analyze`
accepts the actual preaction/after client bitmaps, selected offer index 0..3 and
four comparison labels. It has no window, capture, focus or input API. Private
bitmaps, local paths, receipts and client profiles are not part of this source.

The reviewed 1450 x 869 initial hand changes from two logical cards to three.
Both original passive and equipment artwork must be preserved and recentered
at similarity >= .97; the new right-hand artwork must match the purchased live
shop artwork at >= .92, exceed different-hero offers by >= .12, and have been
absent from both original hand positions (< .75). Search is restricted to the
observed translations and scales .585/.595/.605/.615. Half-pixel sampling handles
the equipment's observed recentering. These are uncalibrated correlations, not
probabilities or a general inventory/counting model.

Use `runtime.hand_postcondition.matcher_labels(hero_ids)` for the C# labels:
recognized duplicates receive the same ASCII identity, while unknown offers
receive distinct slot identities and remain competitors. Missing/unknown names
must not cause all unknown offers to be treated as the same hero.

The successful live record reports received-art score .956297, different-hero
margin .778570 and preserved-equipment score .987512. This is one observed live
automatic purchase, not a general accuracy estimate. The earlier Yao images
provided a saved-image regression case; failed/unchanged-layout cases remain
separate from the later live success.

## Bind the actual dispatched intent

`runtime.hand_postcondition.make_snapshot` checks the raw matcher predicates,
coordinates/scales, layout counts, numeric currency result, game identity,
newer frame and original source hash. A `Known=true` flag cannot waive those
checks. It creates evidence for the one logical receiving slot of this special
layout, whose pixel positions recenter; it does not infer arbitrary free slots.

```python
from runtime.hand_postcondition import make_snapshot, matcher_labels

# Before C# Analyze, derive labels from four current recognized offer IDs.
labels = matcher_labels(current_hero_ids)

# Retain intent.to_dict() from the guarded dispatch callback, after recapture.
# plan["selected"] from prepare may refer to the older before image.
post = make_snapshot(
    actual_dispatched_intent, after_capture_record,
    source_sha256=actual_preaction_sha256, source_mode="live_capture",
)
verification = handler.verify(post, now=actual_current_utc_iso)
```

The producer must bind the C# source bitmap to that exact preaction hash and
the target bitmap/results to the after capture. The helper does not load or
authenticate pixels itself. It defaults to saved replay; explicit reused or
conflicting source modes cannot become live postconditions. It does not declare
purchase success: the unchanged handler still checks the actual current time,
original timestamps, same match, exact currency delta and expected hero.

Integration regression replay uses the original recorded verification cutoff
and is labelled historical. Current-time verification correctly rejects those
old frames, and default saved-replay snapshots cannot pass as live verification.
This integration did not recapture the screen, rerun the pixel matcher, launch
the controller or send input. The C# bytes are verified against the executed V8
snapshot; Python tests cover binding, tampered predicates, unknown competitors,
wrong currency delta, replay and freshness.

The complete 20-file private snapshot and its private patch are review material,
not a replacement for the repository. Path-bound coordinators, screenshot banks,
input scripts and the private deletion/retention helper are excluded. The newer
native guards, original handler and repository's no-deletion budget remain
unchanged.
