# Purchase recognition repair and first actual purchase

This records the earlier Yao/OCR milestone. A later Sun Bin purchase automatically
passed the spatial hand and currency verifier; see [V8 evidence and API](hand-appearance-evidence.md).
The original Yao receipt remains visual-only. [V9 placement](DEPLOYMENT_V9.md)
was subsequently confirmed from original images; its live automatic
deployment postcondition remained unfinished at that checkpoint. Later
[V11](DEPLOYMENT_V11.md) automatically verified a separate Niumo deployment;
ready postconditions and full strategy remain unfinished.

The control worker submitted one actual purchase of Yao in a five-bot Xingyao
custom game. It visually inspected original before/after client images and
confirmed energy 6 to 3 and a new Yao card in hand. The native callback completed
one click and owned release. These are separate facts from automatic verification:
hand-name OCR omitted Yao, `PurchaseHandler.verify` was not called, and the
runtime stopped for dual-postcondition review. That recorded attempt is not an automatic closed
loop, deployment result, complete match, or win-rate claim. Private evidence
images, receipts, identifiers and local paths are not included in source.

## Portable subset

`runtime.purchase_recognition.classify_phase_labels(frame)` compares both
`phase_ready` and `phase_start`, requires a winning similarity >= .97 and class
margin >= .02. Observed wrong-label similarity around .954631 is not fixed by
lowering the threshold. Recognizing a label alone does not prove buy eligibility.

`assess_purchase_features(frame, hero_mapping, now=..., source_mode=...)` adds
shop-price visibility, known numeric components, portrait/currency/round/empty
region anchors and unambiguous reviewed hero-template matches. It returns only
candidate evidence, never a purchase permit or observed `purchase-screen/1`.
The optional `expected_balance` and `expected_price` constrain a reviewed trial;
there are no built-in energy 6 or price 3 gameplay assumptions. Live mode keeps
the original five-second source-frame age. Replay is explicit and advisory.

`ConsecutivePurchaseFrames.observe(result)` requires two consecutive distinct
hashes with increasing capture times, same game identity, source mode and offer
facts, no more than five seconds apart. Unknown evidence resets the gate. This
reduces transient matches; repeated identical files do not count as two votes.
The controller must still provide a verified custom-match origin and separate
positive evidence for a legal empty destination before calling PurchaseHandler.

`numeric_candidate(record)` validates one- or two-digit component results from
the private producer: explicit Known=true, ASCII decimal text consistent with
the integer/component count, score >= .90 and class margin >= .08. Known=false
never means a known zero. These are uncalibrated candidates, not general OCR or
an independent verification of the producer. The raw C# extraction adapter
remains a separate local review candidate; it and its private observed bitmap
bank are not included in this patch.

The same phase classifier was checked against the existing 77 saved-frame
feature records: 10 expected text positives, 67 negatives, no classification
differences. This replays recorded matcher outputs, not newly captured images
or an independent accuracy estimate. Synthetic tests cover the competing-label
confusion, missing/ambiguous evidence, numeric unknowns and temporal stability.

## Private runner review and remaining work

The private first-round producer and coordinator are not copied wholesale.
They still contain machine-specific paths, bitmap banks and opening assumptions.
Their retention helper deletes older unprotected PNGs, while the repository's
capture budget stops at its limit and preserves evidence; this integration keeps
that existing no-deletion behavior. No controller files or running processes
were modified during the review.

The private postcondition fallback counts a hero name in a wide hand OCR region
and assigns it to a specific previously empty receiving region. That is not
enough to prove new appearance at that destination, and OCR text equality is not
a calibrated confidence of 1. Do not publish that fallback as automatic success.
Next work is a spatially bound before/after hand-card detector, or a verified
slot-specific recognition result, retaining the original frame hash/time. Until
then the actual purchase remains visually confirmed with automatic postcondition
review pending. Failed verification must not trigger a second purchase.
