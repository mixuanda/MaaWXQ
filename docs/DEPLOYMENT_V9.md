# V9: automatic purchase, observed deployment, no continuous strategy yet

The control worker automatically bought Li Yuanfang for 3 from an energy balance
of 6; the unchanged PurchaseHandler returned `purchase_verified`. The subsequent
typed drag moved that owned card from the three-card hand to the reviewed empty
board location. The original after image showed the unit at the drop point,
population 0/3 to 1/3, and the hand reduced from three cards to the preserved two.
Original-image review and a later saved-image hand check confirmed placement.

The distinction is deliberate: the purchase postcondition was automatic in the
live runtime; the drag was automatic, but its final board result was confirmed
afterward. The live deployment receipt retains
`game_postcondition_verified=false`. This source does not claim an autonomous
live deployment postcondition, a complete match, a win rate, or continuous
strategy. The prior Sun Bin and Yao milestones retain their original outcomes.

## Explicit bounded drag

`backends.deployment_drag` provides `DeployEvidence`, `DeploymentDragPort` and
`DeploymentDragBroker`. This is a distinct `custom_deployment` /
`deploy_owned_hand_hero` operation; it is not routed as a purchase or setup click.
The public broker exposes `drag_once()` and rejects `click_once()` for this
gesture. The internal port protocol still uses its inherited method name.

The producer must supply a current, positively recognized preparation scene,
the automatically verified purchased hero still in hand, same custom match and
game identity, no other humans, recognized empty drop area, and the reviewed
empty population 0/3. Current source/phase/board/capacity similarities and phase
class margin are explicit evidence. Every value must come from the same original
capture or its correctly bound custom-match/purchase context. A caller-provided
boolean or typed record alone is not independent perception or authorization.

The adapter deliberately supports only the reviewed 1450 x 869 first-unit
layout, hand source region and destination (710,555). `capacity=3, occupied=0`
is an observed restriction of this prototype, not a general game rule or a
capacity inferred from unrelated UI. Other capacities, locations, hand layouts
and phases must be implemented from new evidence rather than guessed.

`DeployEvidence` adds these deployment-specific fields to the normal binding,
frame SHA256 and original monotonic capture time:

| Fields | Required meaning |
| --- | --- |
| `hero_id`, `match_id`, `purchase_verified` | Same hero/match as the automatic purchase result |
| `capture_utc` | Original capture UTC, never processing time |
| `x`, `y`, `end_x`, `end_y` | Positively recognized hand source and reviewed drop target |
| `source_match`, `empty_board_match`, `capacity_match` | Uncalibrated current hand/board/population similarities |
| `phase_match`, `phase_margin` | Current preparation-class similarity >= .97, margin >= .02 |
| `capacity`, `occupied`, `no_other_humans_verified` | Reviewed empty 0/3 custom-bot context |

The drag submits one tagged MOVE+DOWN batch, ten bounded move events and one
owned UP over approximately 300 ms. Legacy `down_count=2` counts that initial
two-event batch; it is one mouse press. Each move rechecks native target, game
identity/geometry, foreground, destination hit test, interruption state, held
ownership and deadline. Other held keys interrupt; only the owned left-down
state is expected during the gesture. Existing tag32, hooks, exclusive lease,
emergency stop and owned-release ledger remain unchanged.

Both UTC and monotonic source age stay bounded at five seconds; broker duration
cannot exceed two seconds. The result remains unverified after submission.
Partial/uncertain segments are logged and not repeated. Release failure retains
the held ledger until cleanup succeeds. No generic held-input or keyboard safety
claim follows from the one observed deployment.

```python
from backends.deployment_drag import guarded_executor

# evidence is built by the sole controller from a fresh validated capture and
# its actual automatic purchase result. Default enabled=False sends no input.
execute = guarded_executor(evidence, observer=inspect_game, enabled=operator_enabled)
receipt = execute()  # One consumed attempt, including failure/uncertain outcome.
assert receipt["game_postcondition_verified"] is False
```

Direct broker users must close it in `finally` and preserve its native summary
and `port.drag_moves`, including failures. Do not recreate the callback to retry
an uncertain submission. Reserve the required result capture under the existing
shared budget before dispatch; the private deletion/retention helper is not
included and does not replace the repository's no-deletion policy.

## Round parser and deferred loop

`runtime.round_label.parse_round_label(text)` accepts a full round label or the
observed abbreviated `3 回`, only from the already validated header ROI. It
rejects bare numbers, extra text and malformed labels. It does not recognize a
phase or authorize ready actions by itself.

The actual baseline stopped with zero ready actions after strict OCR parsing
failed. The frozen parser includes the subsequent source correction; that
correction and the adjusted selection-observer scheduling were not live-retested.
The path-bound private round loop and scheduling changes are not copied into
this publication. Draft/talent handling, generalized placement, a live board
postcondition and the intended continuous round cycle remain unfinished.

Integration checked all 31 frozen source hashes and unchanged native/handler
dependencies, original frame hashes and movement/release records. Tests use
fake native APIs; integration performed no capture, window action, controller
launch or desktop input. Private patches, screenshots, profiles, receipts and
machine paths are excluded from public source.
