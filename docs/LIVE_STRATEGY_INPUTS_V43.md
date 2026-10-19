# V43 state and Lingbao input for the V42 control host

This change fills the input side of the guarded feedback loop. It does not
provide a new capture/OCR backend, acquire desktop ownership or contain a game
lineup. It consumes the sole controller's actual measurements and an explicit
selection from observed Lingbao recommendations. Missing inputs remain named
gaps; they are never replaced by guessed boards, empty hands or default budgets.

## V42-host-1 compatibility

The reviewed private host exposes `LiveProviders.capture(path, regions, anchors)`
returning `frame/facts/ocr/phase`, then calls `attach_current_state`. These return
keys and the native guard callbacks remain compatible. Its identity, custom-room
origin, permission, persistent ledger, lease and capture-budget checks are still
required. The host's prepared snapshot pins V42 commit `73e7bf2`; do not overwrite
that running or frozen source tree with V43 files. Its owner must build a new
reviewed snapshot/fingerprint and preserve the original match ledger semantics.
This change did not modify the private host, ledger, package or reference images.

```python
from runtime.live_perception import LivePerceptionAdapter

capture = LivePerceptionAdapter(
    authorized_existing_capture_and_measure,
    clock=utc_iso,
)
# Pass capture to the host's LiveProviders only in the authorized control owner.
# There is no call to capture here and no worker is started by construction.
```

The wrapper calls the supplied provider once for each host observation and
normalizes its result. The raw frame must be explicitly live, original and no
older than five seconds, with an advancing original capture time. The host still
checks the actual file hash, reserved path, monotonic time and active origin.
No unsupported Windows, Resident, PowerShell, ADB or emulator route is selected.

## Recognition transport

The provider may keep supplying the established recognized records directly in
`frame`, or return an optional `recognition` object with:

- `schema_version="perception-frame/1"`;
- original `frame_sha256`, `captured_at`, `identity_version`, `geometry_version`;
- `zones` keyed by board/hand and `fields` keyed by existing Advisor field names;
- optional `bans`, `opponents`, `deployment`, `close_shop`, `match_origin`;
- optional current `facts` and `phase` for the existing projection interface.

The common envelope supplies only transport bindings to its child records. It
does not supply their observed status, confidence, complete coverage, heroes,
empty/legality classification, slot identities or semantic sources. Those must
come from the detector. Conflicting direct/enveloped records, mixed frame/time
tokens or older opponent timestamps are rejected. Partial zones stay partial;
the small hero-template catalog cannot turn an unmatched card into an empty slot.

The mapping is direct: zones/fields/bans/opponents become the established
`recognized_*` records; deployment becomes `recognized_deployment`, close_shop
becomes `recognized_shop_close`, and match_origin becomes
`recognized_match_origin`. The latter still requires the actual custom-room
receipt hash and continuity proof checked by the host. It is not reconstructed
from PID or a screenshot. Physical IDs must persist across captures.

`facts` retains current round/button/timer/energy/shop/offer values; nested offer
`ui_binding` records receive the same transport bindings. Missing facts or OCR
are returned as empty dictionaries without being stamped current. Existing
nonempty facts/OCR must already have the original frame hash/time. OCR retains
the existing `values` dictionary and is not run or emulated by this module.

Capacity now always requires an explicit current `recognized_fields.capacity`
record. The old high `v14.capacity` similarity no longer supplies a constant
five. The existing positive zero-population proof can establish an empty board,
but cannot establish capacity, player level, hero identities or legal coordinates.
An explicit conflicting record capture time is also rejected by `bound_record`.

## Compile an observed Lingbao selection

`strategy.lingbao.compile_lingbao_selection(catalog, selection, spending, now=...)`
returns either `status="ready"` with an existing `v41-lineup-policy/1` policy,
or `status="pending"`, `policy=null` and specific gaps. It performs no IO and
does not choose the first catalog entry automatically.

The catalog is `lingbao-catalog/1`, provider `in_game_lingbao`, with original
`frame.sha256/captured_at/identity_version/geometry_version` and `plans`:

- Each entry has a stable `lineup_id`, an observed `name` record, selected plan
  target `coverage="full"`, and explicit `targets`.
- Each target's `hero_id` is an observed string record. Name/hero records require
  status observed and confidence at least .97; explicit binding tokens, when
  supplied, must agree with the catalog envelope. Unknown text is not completed
  from a dictionary or a spoken guess.
- `role`, `count` and `priority` are explicit composition/policy inputs. A
  transition names its `replaces` core heroes. Optional `desired_star` is a
  policy goal and supplies no synthesis recipe. No target count, priority or
  hero is silently filled in.
- Optional `chess_player_id` is an observed catalog record; actual current player
  selection still comes from live state. Optional ban tags require an explicit
  reviewed-rule `ban_mapping_source`. Without a verified mapping the existing
  Advisor also holds when a later match ban cannot be resolved.

`selection` supplies ordered, unique `plan_ids` that were actually present in the
catalog, a nonempty selection `reference`, and optional `search_min_levels` keyed
by selected plan. Several selected plans feed the existing dynamic Advisor; this
does not add a second scorer or reset the opponent/bans store. A missing search
minimum remains unknown for leveling/search, while supported buys/deployment can
still proceed. This catalog is a sourced configuration snapshot, not a current
battle frame; it is frozen with its evidence for the reviewed client.

`spending` is the existing explicit match policy: reference, budget_scope match,
reserve, upgrade_reserve, level_reserve, refresh_spend_cap, refresh_count_cap.
Null or absent values produce exact missing-key gaps instead of zero defaults.
Counts/priorities/reserves are planning choices, not inferred prices, interest
or probabilities. No actual lineup or source image is included in this change.

```python
from strategy.lingbao import compile_lingbao_selection

prepared = compile_lingbao_selection(
    actual_observed_catalog, explicit_selection, explicit_spending,
    now=utc_iso(),
)
if prepared["policy"] is None:
    show_missing_inputs(prepared["gaps"])
else:
    # Freeze prepared["policy"] and its original catalog evidence with the host.
    # Construct the existing guarded host; do not mutate an active frozen policy.
    policy = prepared["policy"]
```

## Explain holds without blocking unrelated actions

`state_readiness(frame)` and projected `input_status` provide separate
`decision_missing`, per-action `action_missing`, `host_missing`, observed/unknown
field names and projection gaps. Runtime holds and completed feedback include
this report. It is diagnostic only, never an input permit. For example, absent
player-level/paid-refresh readers can block upgrade/search without preventing
an otherwise supported current target purchase. An unknown hand, by contrast,
blocks the composition decision rather than being replaced by the old roster.

No full match, live screen read, OCR, native input, simulated game results or
production change was performed. Minimal offline validation connects the input
adapter and compiled selection to the real existing Advisor, checks missing and
mixed data, and preserves the affected guarded feedback path with native APIs
forbidden. Real complete detection, actual catalog/selection, current economic
UI readers, supported live providers and sole-controller handoff remain required
before the allowed custom-match acceptance.
