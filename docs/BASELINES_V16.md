# V16: bounded name-mask repair and three failed baselines

Later [V17](SURFACE_V17.md) verified two normal shop closes and a review-assisted
deployment to 2/5. Its live pre-close counts were already readable; the older
occluded-count failure was covered offline. It stopped at a talent overlay and
its declared budget, without 5/5 or a new baseline. Pending statements below
describe the V16 checkpoint; all three failed results remain retained.

Three private custom-game baselines were registered before launch with frozen
policy/source hashes and an explicit `preregistered_model_review_assisted_baseline`
classification. All three sixth-place results are retained, including the
zero-deployment failure. They are eligible for this baseline report, but none
is an autonomous win-rate sample. The earlier V13 debug result is not silently
reclassified into this series.

| Registered version | Maximum confirmed deployment | Actual result | Limiting failure |
| --- | --- | --- | --- |
| V14, baseline 1 | 0/5 | Sixth | Initial purchase's preserved-equipment match was about .962, below .97; purchase verification stopped and no deployment followed |
| V15, baseline 2 | 2/5 | Sixth | Yi Xing was deployed in round 2, Li Yuanfang in round 3; panel-name similarities .691/.681 led to two unknown frames and permanently stopped input |
| V16, baseline 3 | 2/5 | Sixth | Initial Yi Xing purchase/deployment passed; round-2 Li Yuanfang deployment was model-reviewed; the round-4 shop obscured population/capacity, so Su Lie was not dragged |

V15's final OCR was empty. Its final numeric sixth-place image was separately
reviewed; the preceding image said the match had not ended and is not ranking
evidence. V16's final OCR contained an incorrect prefix, retained unchanged,
while the final image was reviewed as sixth. No forfeiture or further gameplay
input was used to obtain those settlements. All low outcomes remain reported.

The additional V15/V16 deployment receipts labelled `deployment_verified` use
`method=bound_model_visual_postcondition`; they include frame-bound model image
review. That label must not be presented as a wholly automatic numeric/name
postcondition. The registrations explicitly permit this bounded review and
exclude autonomous-win-rate interpretation. Full strategy and live 5/5 remain
unfinished.

## Live name-mask improvement

The V16 new-game frame recorded old panel-name similarity 0.89705 versus white
name-mask similarity 1.000, with owned-unit and 2/5/capacity template evidence
also matching. The controller closed that previously verified owned-unit panel
and continued observation, passing the earlier V15 name-recognition stop.
This establishes the specific live repair; it is not general name OCR accuracy
or a successful army strategy.

`runtime/name_mask.cs` is byte-identical to the preregistered V16 source,
SHA256 `33009ff5ed836be8571b44a617abb6a38f08dbf4983d3949828a72e05129ebbe`.
Its `NameMaskCandidate.Compare` operates only on supplied bitmaps. The reviewed
name ROI is [144,191,100,31] in a 1450 x 869 client. It selects near-white pixels,
rejects too little or overly dense ink, searches at most three pixels of
translation and compares both masks with one-pixel local tolerance. The
acceptance threshold remains .97. There are no capture, window or input APIs.

The frozen saved checks include two same-name frames, a different hero and a
final-result overlay. Integration recompiled the exact C# source and reproduced
scores .99080, .99197, .57591 and 0 respectively. It also recomputed the new
live frame's full mask result: score 1, translation (2,0), reference/current ink
counts 406/473. Those recomputations used original saved pixels, not new captures.
Similarities remain uncalibrated and these examples are not an accuracy estimate.

## Portable read-only gates

`runtime.name_mask.is_name_match(result)` checks the full C# result: score,
bounded integer translation and both ink counts. A scalar score of 1 alone
does not satisfy this contract. Producers should retain all result components
and hash both original bitmaps before accepting a measurement.

`assess_name_match(reference, current, result, now=..., source_mode=...)` binds
the declared source metadata, supported geometry, distinct current frame and
original timestamps. Saved replay is the default; stale or reused live frames
are rejected. The reference must be the reviewed known inspected-panel source,
not an arbitrary name image or a claim that an old roster is still current.
The function returns only a match candidate: name text and hero ID remain null,
ownership remains unverified, and input permission/postcondition flags stay
false. It does not dispatch panel dismissal or change the existing first-unit
or army adapters.

`population_template_gate(rows, expected_count=..., capacity_score=...)` retains
the private baseline's .97 score and .02 competitor-margin gates with strict
finite/type checks. Template values require independently reviewed, hash-bound
references; this helper is not standalone population OCR or authorization.
Neither a name match nor a remembered count can replace current population and
capacity evidence.

The actual round-4 failure has Su Lie hand similarity .99897 and empty-cell
similarity .99988, but current population/capacity similarities only .89242 and
.94085. That frame remains rejected and no Su Lie drag was submitted. The
proposed next repair is to recognize and close the shop, then recapture an
unobscured counter before evaluation. That transaction is not implemented or
live-tested here. Thresholds are not lowered and input is not re-enabled.

## Control and strategy limits

Selection initially stopped because a shuffled player-selection grid invalidated
the old fixed-position observer. The original `selection_confirmed=false`
remains; bounded visual review subsequently confirmed the actual selected
Yi Xing and board. This was another review-assisted step, not proof that the
automatic selection observer was repaired. A future fix must locate the actual
card and verify confirmation, not replace one fixed coordinate with another.

The baseline makes one initial purchase and fills distinct already owned heroes
left to right. It retains resources while merge/upgrade rules are unknown. No
ready or talent actions were executed in these three runs. Draft-preview states
were wait-only. Duplicate merging, refresh/upgrade policy, equipment use,
opponent-aware formations and a complete match policy are still missing.

Timing evidence is split by operation. The cold capture median was about 1.74 s
over 85 calls; the earlier resident hot-capture benchmark was about .22 s.
The interim V16 snapshot measured median .759 s with hand scans (24 calls) and
.361 s without them (22 calls). Those groups exclude native actions and model
review. The Li Yuanfang transaction took about 13.06 s, including a 10.75 s
model-review wait; later hand/phase reviews took about 15.05/15.51 s. No fast,
fully automatic preparation loop is demonstrated. These scoped measurements
must not be presented as whole-match strategy throughput.

## Verification and publication scope

Integration verified 115 frozen sources, 10 private assets, 1239 evidence-file
hashes, six unchanged native dependencies and the selected private patch hash.
All 205/210/220 preregistered source entries for the three versions still match,
and each registration predates its run. Invalid intermediate EOF/BOM patch
packages remain historical failures; the corrected private delta was reviewed
as source material and was not published wholesale.

The public subset contains the pure mask, metadata gates, synthetic bitmap/Python
regressions and this documentation. Seven synthetic bitmap cases and five saved
bitmap comparisons passed; nine original image hashes were checked. Current
time rejects saved-frame candidates, and the shop-occluded population gate is
still false. No private templates, catalogs, profiles, screenshots, receipts,
paths, model-review plumbing or resident capture worker are published.

Integration did not capture, focus, launch a game controller or send input. The
private trials' larger registered capture budgets and retention helpers are not
ported. Public capture limits stay 50 PNG / 64 MiB with stop-on-full and no
deletion. Native foreground, identity, geometry, freshness, exclusive ownership,
interruption and owned-release checks are unchanged. MaaFramework remains 5.7.2;
the historical Right Shift limitation has no new safety claim.
