# V13: four units observed, automatic army strategy unfinished

In a fresh authorized Yi Xing custom game with five Xingyao bots and no other
humans, the control worker automatically purchased and verified the first
deployment, Su Lie. It later dragged Kuang Tie, Da Qiao and Jiang Ziya from the
owned hand onto distinct reviewed empty cells. Recorded original-image reviews
confirmed populations 2/5, 3/5 and 4/5. Those later deployments did not pass a
complete automatic postcondition and their original statuses remain unchanged.

| Step | Round | Original automatic result | Recorded review and retained evidence |
| --- | --- | --- | --- |
| Su Lie, 0 to 1 | 1 | `deployment_verified` | Automatic first-unit result |
| Kuang Tie, 1 to 2 | 4 | `unit_identity_unverified_no_retry` | Name OCR empty; original image was reviewed then later retired; hash, capture metadata and receipts survive |
| Da Qiao, 2 to 3 | 7 | `unit_identity_verified_population_requires_review` | Exact name and owned-unit recognition passed; 3/5 was image-reviewed; original image remains |
| Jiang Ziya, 3 to 4 | 8 | `unit_identity_unverified_no_retry` | Exact name OCR failed; 4/5 and the selected-unit panel were image-reviewed; original image remains |
| Planned Miyamoto Musashi, 4 to 5 | Not executed | Both attempts stopped with `input_attempted=false` | Waited through combat/unknown scenes; final image was subsequently reviewed as a sixth-place result |

No fifth unit was submitted and no new ready action was sent in this V13 army
trial. It reached four units with development-assisted review, not an autonomous
five-unit army or complete match policy. The original native receipts retained
owned release, no held button and no cleanup errors after submitted actions.
This does not expand the historical keyboard/held-key safety claims.
Complete state/decision coverage was not recorded for every round; waiting
screens do not establish a full round-by-round army policy.

## Missing evidence and unchanged failures

The early 2/5 identity PNG was deleted by the private worker's older rolling
retention rule. Its SHA256, capture metadata, failed automatic receipt, review
record and prior conversation display survive. The missing pixels cannot be
reconstructed from those records and are not independently reproducible now.
The retained 3/5 and 4/5 images do not repair that historical gap.

After the trial, the private source added evidence pinning, stronger match and
review-source checks, source hashes for future receipts, and removed an unused
duplicate-hand branch. These changes were not tested in another live match.
They must not be described as the exact guarded path exercised by the earlier
actions. No private executor, retention/pinning helper, path-bound capture
builder, scheduling loop or unexecuted strategy draft is ported here.

Sunset Sea Reinforcement was the reviewed talent choice in this trial. The
selected name matched OCR, but its description OCR contained an error, so the
original `talent_selection_unverified_no_retry` remains. Image review confirmed
the choice; the reference energy was 40 and the later image showed 42. The
random awarded hero was not identified. No automatic status or unseen card
identity is substituted from this review.

## Portable read-only perception

`runtime/army_pixels.cs` is the frozen V13 bitmap-only matcher, SHA256
`673e698a498a3b95abbf5cea2cdaacbd88e3d208e7fde934d679d12da5f720ae`.
`ArmyPixels.FindHand` searches the observed hand band using a 24x38 fingerprint
in the reviewed examples, bounded scale/position refinement, correlation and
competitor margin. `ArmyPixels.NewUnit` measures a changed component inside a
caller-supplied reviewed cell region. These measurements do not identify all
heroes, establish ownership or count the whole board. Similarities are
uncalibrated, not probabilities. Producers must use original hashed bitmaps,
valid 1450 x 869 geometry and reviewed in-bounds reference/cell rectangles.

The frozen saved-measurement report contains nine hand cases: three self-image
matches, three shifted-hand matches and three absent-card rejections. Integration
checks those saved measurements against the public acceptance predicates; it
does not rerun the bitmap matcher or turn nine examples into an accuracy
estimate. The frozen source hash is known, but the live receipts lack a separate
execution-time hash attestation for this matcher, so byte-identical live
execution is not claimed.

`runtime.army_perception` adds three input-free helpers:

| Helper | Meaning and limits |
| --- | --- |
| `hand_match_candidate(match)` | Independently checks Known, score, margin, scale and the observed fingerprint geometry; leaves hero identity and ownership unverified |
| `assess_army_frame(frame, reference_sha256s=..., now=..., source_mode=...)` | Retains current original-frame and template-hash candidates, positive preparation and empty-cell/population similarities; never returns a dispatch intent |
| `bind_roster_review(review, image_bytes)` | Hash-binds available original bytes to the recorded manual review, preserves the original automatic status and omits private paths; missing or changed originals fail binding |

Population and capacity template fields are similarity scores: a score of 1
does not mean one unit or capacity one. `population_value` and `capacity_value`
stay null. A reference hash alone does not prove that template's content or the
current match roster. The manual-review helper verifies byte binding, not the
reviewer's visual interpretation or freshness. It supports the observed 2/5
through 4/5 review records and never supplies current action eligibility.

All helpers keep `execution_allowed=false`, `game_postcondition_verified=false`
and `blind_retry_allowed=false`. Saved replay is the default; explicit live
frame assessment still supplies only perception candidates. The source-only
owned-panel fallback is not ported: unknown/occluded phase evidence remains
unknown. The existing first-unit adapter retains its empty-board restriction.
No new native input adapter or automatic multi-unit controller is added.

## Integration checks and result limits

Integration verified 80 frozen source hashes, 383 retained evidence-file hashes
(including 51 PNGs), six unchanged native dependencies and the private delta
hash. It checked all nine saved hand measurements, bound the retained 3/5 and
4/5 manual-review images, and explicitly rejected the missing 2/5 original.
The existing public talent verifier also preserves the original description
failure during saved replay. Five retained original images were rechecked.
Synthetic regressions cover false Known flags, ambiguous or nonfinite matches,
geometry, stale frames, missing reference hashes, changed review images,
duplicate rosters and incorrect population metadata.

No private images were copied into public source. Integration performed no
capture, focus, controller launch, game input or control-workspace edit. The
private experiment ledger counted 85 captures against a cumulative 120 over
its original scoped stages, including the initial 45-frame trial. This is not
a public budget increase. The public 50 PNG / 64 MiB stop-on-full, no-deletion
policy and existing native guards remain unchanged. MaaFramework stays 5.7.2.

The V13 game ended sixth in round 8 and is excluded from win-rate samples
because of development pauses and manual postcondition review. The earlier
V12 match also later ended sixth and is separately excluded; it is not the
same roster carried into this new trial. Eligible win-rate samples remain zero.
No full-strategy or win-rate conclusion follows from these results.

Next work is fast, intent-bound automatic validation of added-unit identity
and numeric population, with all critical originals retained within the existing
budget. Then verify a fifth placement and a finite army-development policy in
a separately observed custom match. Selling, merging duplicates, equipment
application, strength estimates and opponent-aware formations are unfinished.
