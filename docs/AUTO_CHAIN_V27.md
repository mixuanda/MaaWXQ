# V27: bounded talent recovery and automatic deployment evidence

Later [V36](FILL_V36.md) evidence reaches 5/5 in one continuous controller run
with three bounded model fact reviews. It does not establish fully autonomous
strategy or a complete talent/match flow. The historical V27 results below are
preserved.

The last in-match diagnostic reached round 8 with four of five units and ended
sixth. After Ganjiang Moye, three later deployments recorded automatic fresh
postconditions: Niumo in round 2, Yi Xing in round 3 and Kuang Tie in round 5.
Their recorded verification times were 4.443, 4.250 and 3.922 seconds, with zero
model postcondition reviews. These are the original private-controller results;
they are not live tests of the stricter public slot contract added here.

Five of five is still unverified. No new complete baseline was run. The three
earlier review-assisted baseline ranks remain [6, 6, 6]; they are not autonomous
win-rate samples. This checkpoint does not establish a full-match policy,
opponent-aware dynamic formations or general talent strategy.

## Talent selection, animation and return

Twin Tour (`双人游`) was selected once in round 6. The first post-selection image
was still in transition and did not automatically confirm the name. Its failed
receipt remains a failure. A later fresh detail image confirmed the exact name
and effect describing two random tier-2 to tier-3 heroes. A subsequent recovery
revalidated that detail, closed it once and later observed round-8 own-player
preparation with 4/5 population. Waiting through the intervening unknown scene
did not repeat the selection or close.

The unified V27 runner adds bounded post-selection observation and animation
waiting, but did not play a new live match: its latest room entry stopped before
adding the first bot. A longer semantic-review deadline is a source change, not
proof that a full strategy is now timely. The earlier late review was ignored
and its failed transaction is retained. The information-button branch and
repeated purchasing interfaces also lack complete live validation.

`runtime.talent_chain` exposes input-free checks:

- `talent_layout` requires one complete current, gold or legacy three-footer
  family. Missing, duplicate, nonfinite or mixed partial votes stay unknown.
- `assess_selected_detail` binds fresh name and description OCR to the original
  image hash and exact reviewed ROIs. Exact name/effect is a detail candidate;
  it does not establish selection commitment or reward delivery.
- `stability_decision` permits at most three post-selection observations. An
  unresolved animation waits read-only, then stops without another click.
- `verify_detail_return` links the exact detail to one clean owned release and
  a fresh own-player preparation/count/capacity scene under the original
  deadline and unchanged window geometry. It verifies recovery only.

Saved replay is the default. Replaying the frozen detail/close/return evidence
passes at its historical clock with `game_postcondition_verified=false`; the
current clock rejects those old detail frames. Explicit live evidence can
verify a current detail return, never reward delivery or five-unit deployment.
The caller must still validate original bitmap bytes and comparison producers.
No helper authorizes input or retries an uncertain action.

## Room refusal remains before the native broker

Another account occupied an otherwise empty room in the latest first-bot
transaction. The existing room recognizer rejected the empty-room proof and
returned `empty_custom_lobby_not_verified`, with `input_attempted=false`.
This zero-input statement applies to that refused bot transaction; earlier
bootstrap navigation had already occurred. A later read-only image showing an
empty room did not automatically restart it.

The existing lobby runner independently captures and recognizes both the
initial and preaction scenes, stopping before constructing the native broker
when either fails. A regression now simulates a guest arriving between those
captures and asserts that the broker is never constructed.
`runtime.chain_guards.empty_room_pair` adds a portable advisory check for both
five-empty-slot proofs, unchanged identity/geometry and increasing fresh capture
times. Old emptiness or a metadata boolean cannot override a current refusal.
Its result always has `execution_allowed=false` and no automatic retry.

## Distinct heroes, templates and physical slots

Review found that private fallback paths could accept expected-hero artwork
without a full competing-hero comparison. That is insufficient for the public
identity contract. It is a review finding, not evidence that an actual wrong
unit was clicked. The private fallback controller and template catalog are not
ported.

`runtime.slot_identity.template_registry` binds each reviewed template to a
hero, original image hash and exact fingerprint ROI. An image can contain
multiple heroes in different regions, so its hash alone is not an identity.
The same hash/ROI cannot name different heroes.
`resolve_hand_slots` requires all registered competitors for every current,
nonoverlapping hand slot. Alternate templates of one hero compete as one
identity within that slot; different physical cards retain distinct slot IDs.
Recognition requires score >= .94 and a distinct-hero margin >= .10. Missing,
ambiguous or unbound comparisons cannot identify a slot. The producer must
independently validate the original pixels, slot bounds and catalog semantics.

The older automatic deployment records lack this complete current per-slot
comparison contract. Their original statuses are preserved, without claiming
that the new stricter helper has been live validated. Its outputs remain
read-only candidates, with no game postcondition or execution permission.

## Cumulative budgets and resumable accounting

The frozen continuation records preserve the same original deadline and action
totals of 9, 13, 14 and 16. Review did not find a reset of those recorded totals.
Larger private observation and storage allowances are not imported.

`ChainBudget` adds immutable cumulative accounting bounded to 50 captures,
64 MiB, 28 native attempts and an original interval of at most 600 seconds;
callers can choose smaller limits. Restoration retains counters, deadline and
stop state and requires the expected checkpoint digest. Deleting a capture or
receiving a failed/uncertain input result does not refund usage.

The controller must charge attempts and durably persist the latest charged
checkpoint before dispatch. Its trusted resume record must retain the latest
expected digest; a digest alone does not prevent replaying an older checkpoint
or make persistence atomic. Actual capture counts/bytes must also be charged,
and existing disk reservations and stop-on-full checks remain mandatory before
capture or input. This helper does not implement a durable ledger, executor,
capture worker, deletion or automatic resume. Existing public capture limits
and no-deletion policy remain unchanged.

## Integration validation and scope

Read-only integrity checks verified 73 frozen sources, 911 evidence artifacts
(including 61 PNGs), 302 preregistered source hashes, the frozen patch hash and
six unchanged native dependencies. Three original room/detail/return images
were additionally checked for the bounded replay. Private retention counts are
historical evidence, not an expansion of public storage limits.

All 241 targeted offline tests pass, including a guest joining before dispatch,
mixed talent families, unknown-animation limits, cross-hero and duplicate-slot
ambiguity, and restoration without resetting counters or deadlines. The frozen
talent recovery passes the public replay contract; the three original automatic
deployment receipts were separately audited. Test execution made zero native
UI calls, opened zero Tk windows and sent no game input.

Only three pure Python guard modules, their tests and checkpoint documentation
are added. No private controller, image, nickname, machine path, catalog, patch
or capture-retention expansion is published. Native input dependencies and the
owned-window diagnostic remain unchanged. No new game capture or controller
run was performed during integration.
