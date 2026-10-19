# V36: continuous five-unit fill with bounded model fact assistance

Later [V40](LOCAL_BASELINE_V40.md) records a local gameplay run reaching
sixth-place settlement without runtime model/fact calls. Automatic chess-player
selection still failed its observer budget, and strategy quality is unaccepted.
The assisted V36 five-unit result below remains a separate historical milestone.

One bot-only custom diagnostic reached round 5 with a current 5/5 population.
Li Yuanfang was the initial verified deployment, followed by Niumo, Sun
Shangxiang, Mi Yue and Jing. The same controller continued across preparation
periods without a restart or hot patch, then stopped at the fresh full-queue
observation. This was not five deployments inside one preparation period.

The four expansion receipts recorded automatic identity, ownership, population
and capacity checks, with zero model deployment-postcondition reviews:

| Expansion | Hero | Round | Recorded transaction time |
| --- | --- | --- | --- |
| 1 to 2 | Niumo | 2 | 4.866 seconds |
| 2 to 3 | Sun Shangxiang | 4 | 4.738 seconds |
| 3 to 4 | Mi Yue | 4 | 4.131 seconds |
| 4 to 5 | Jing | 5 | 4.476 seconds |

There were still three bounded model fact reviews: confirming that a hand
contained no hero card, identifying Mi Yue and identifying Jing. Those reviews
supplied readable card facts and template regions. Current software checks
followed; the reviews were not deployment postcondition reviews. The result is
an assisted continuous-fill diagnostic, not acceptance of fully autonomous
strategy, autonomous card semantics or a complete match policy.

## What the frozen evidence establishes

The initial start scene was freshly recognized as the player plus five bots,
with other humans verified absent. Four consecutive expansion records preserve
the same window identity and geometry, current preaction count/capacity/empty
cell, clean owned native release, new-unit components and fresh postaction
identity/count/capacity. Their original statuses and measured times are retained.
The final original bitmap visibly shows round 5 and 5/5; its digest is
`656961ffd52b90ea3d69ba87a26c5a1461a9b4a20dc5235b9badfdc339b954d9`.

The last native receipt has `held=false`, `release_confirmed=true` and no cleanup
errors. The frozen process snapshot reports no remaining input or perception
workers. Runtime and game receipts both report elevated High integrity,
AppContainer false and UIAccess false. Integration changed no privileges and
performed no game capture, input or controller run.

These are the actual private-controller results. The private identity path
still supports alternative name/art/panel evidence. This checkpoint does not
reclassify the stricter public per-slot competitor contract from V27 as live
validated, and it does not port the expected-hero-only art shortcut.

## Small public changes

`runtime.surface_gate.inspect_surface(frame, 5, None)` can now report
`full_queue_observed` after the existing preparation, own-player, uncovered
count and capacity checks. Five never returns a deployment-ready result, and
supplying a target cell at five is rejected. Population-template scope extends
through five while preserving the .97 score and .02 competitor margin; six is
still outside this reviewed scope. This remains an advisory observation without
wall-clock verification, roster identity proof or execution permission. A caller
must independently bind the current capture, original pixels and custom origin.

`runtime.talent_chain.talent_layout` adds the reviewed silver-footer appearance
as another complete family at the unchanged .97 threshold. It retains the V27
rule against combining partial matches from different families. Private images,
reference paths and catalogs are not included.

`runtime.talent_information` separates a readable information preview from the
selected-talent summary:

- `assess_information` binds exact name/effect OCR to the actual, bounded,
  nonoverlapping name and description rectangles. A centered information card
  is not forced into the selected-detail rectangle on the left.
- `information_still_current` requires both complete reference/current
  hash-and-ROI comparisons at .97, unchanged identity/geometry, a fresh capture
  after a bounded fact review and the original deadline. Empty, partial,
  duplicate, stale or changed comparisons fail closed. An overlay that
  disappears at a round transition does not authorize another close.

The preview's detailed effect and a selected talent's short summary can differ.
Preview OCR is not accepted as selected-summary OCR; each must bind its own
actual pixels and expected text. Both helpers remain input-free candidates and
never certify a selection commit, rewards or a complete talent flow. Saved
replay cannot become a new live game result. Pixel/ROI producers and original
bitmap bytes still need independent validation.

A regression also confirms the exact already-selected Star difficulty no-op:
the existing room-options runner keeps its original stopped receipt and
`input_attempted=false`, without constructing a native broker. It does not
pretend that a setting-changing click occurred. This exact case must not turn
arbitrary stopped receipts into success or prove that a room has no humans.

## Preserved failures and unfinished work

The previous diagnostic reached at most 4/5 and ended sixth. Its fifth card was
visible, but a hand-fact response missed the 60-second deadline, so no fifth
drag was sent. Those failures and later zero-input stops remain unchanged.
The first V36 bootstrap also stopped with an uninitialized aggregate capture
ledger; that receipt was retained separately before the actual match started.

When the initial deployment verifies directly, it may not produce a separate
identity bitmap. The private continuation used a hash-checked preregistered
historical owned-panel appearance reference in that case. That reference is
appearance only; it cannot prove current population, current hero identity or
ownership. No private path-based fallback is imported here.

V36 stopped after reaching 5/5. The merged open-information, choose, stabilize,
verify-summary and close talent flow has not been verified live as a complete
chain. Earlier evidence establishes information-button opening only. Long-held
physical-input takeover coverage remains unfinished. Full-match purchasing,
merging, opponent-aware dynamic formations and final match outcome are not
accepted by this fill milestone.

No new complete baseline or win-rate sample was added. The prior three
review-assisted baseline ranks remain [6, 6, 6]. The earlier sixth-place debug
results and the new five-unit fill are not autonomous win-rate samples.

## Validation and publication boundary

Integration verified 59 frozen source files, 690 evidence artifacts including
59 PNGs, the patch hash and all 362 preregistered actual source hashes before
editing the integration branch. Four original preaction images omitted from
the frozen image subset were additionally hash-checked against frozen metadata
and retained privately. The start scene, initial deployment, four expansion
receipts, three model fact responses and final full-queue frame were audited.

All 253 targeted offline tests pass with zero native UI calls and zero Tk
windows. Nine saved positive/negative images also pass the public complete-family
layout check, using freshly computed comparisons from the existing SpatialScore
method in a separate saved-bitmap harness. These public behavior checks
and synthetic information-geometry tests are offline validation, not another
live control run or proof of the unfinished full talent flow.

Only portable Python checks, their regressions and documentation are published.
The 59-file private diagnostic patch is not applied to the public worktree.
No private controller, image, nickname, machine path, learned catalog, raw receipt
or local replay executable is included. Native input dependencies and the
owned-window diagnostic remain unchanged.

The private run recorded 91/120 aggregate captures and 44 play observations;
these are historical private allowances, not public limits. Public retention
remains 50 PNGs and 64 MiB, stop-on-full with no deletion. No enlarged budget,
pinning or rolling-retention implementation is imported.
