# One visible purchase and batched OCR

V5/V6 continuation. No game input was run during this implementation. This
small handler does not depend on global combat statistics, a complete unit
model, Yi Xing passive targeting, or the generic Advisor's complete rule registry.
It checks the evidence relevant to this single visible transaction. The run
still belongs to an authorized custom room and its own chosen chess player.

## Minimal producer contract

`purchase-screen/1` contains `frame`, `mode`, `phase`, `currencies`, `offers`, and
`hand_slots`. `frame` has SHA256, original `captured_at`, `identity_version`,
local `match_id`, `source_kind="screen_recognition"`, and explicit
`source_mode="live_capture"` or `"saved_replay"`.

Every value below is an evidence object with `status="observed"`, `value`,
explicit `confidence` >= .8, `frame_sha256`, `observed_at` exactly equal to
that capture's timestamp, and a nonempty `evidence_ref` naming its actual UI
region/independent verification. Confidence remains uncalibrated similarity,
not a probability. An OCR candidate/null confidence is insufficient. Do not
convert OCR candidates into observed values just to satisfy this interface.

| Container | Required values |
| --- | --- |
| `mode` | `"custom"` |
| `phase` | `"purchase_enabled"` from positive current controls |
| `currencies[]` | Plain stable `id`, evidence `balance` as nonnegative integer |
| `offers[]` | Plain slot `id`; evidence `hero_id`, `currency_id`, integer `effective_price`, `purchasable=true`, client `target=[x,y]` |
| `hand_slots[]` | Plain slot `id`; evidence `empty=true` and `legal=true` for at least one visible slot |

Only the specified payment currency can fund a candidate. Other unknown shop
offers and unrelated global combat parameters do not block a confirmed offer.
Unknown price/currency/phase or no visible legal empty slot does block it.
The selected hero ID is needed for a meaningful result check. This first
handler expects a new unit in a hand slot observed empty before the purchase;
fusion, refunds, other payment routes and unknown destination effects are not
claimed as successful.

After action, provide another `purchase-screen/1` with a strictly newer time,
different hash, same identity/match, the specified currency's balance, and
`hand_slots[].hero_id` evidence for the purchased hero in a previously empty
legal slot. Both the exact effective-price resource delta and one unique hero
appearance are mandatory. A missing/partial result stops; no blind retry.

See `tests/test_purchase.py::screen` for a complete, wholly synthetic transport
fixture. Its numbers and IDs are test inputs, not real game parameters.

## Callable API

```python
from runtime.purchase import PurchaseHandler

handler = PurchaseHandler()  # One transaction, including uncertain outcomes.
proposal = handler.prepare(before, now=decision_utc_iso)
if proposal["selected"] is not None:
    # Controller captures and independently recognizes preaction again.
    submitted = handler.dispatch(
        proposal["proposal_id"], preaction, now=dispatch_utc_iso,
        executor=guarded_purchase_executor,
    )
    verified = handler.verify(after, now=verification_utc_iso)
```

`strategy.purchase.rank_purchases(snapshot, now=..., scorer=None)` is the pure
ranking interface. Default score is `-effective_price`, explicitly labelled
cost minimization. An optional scorer receives a detached resolved offer dict
and returns a bounded sequence of `ScoreTerm(name, value, source_reference)`.
This can incrementally add reviewed hero preference or synergy evidence;
the handler does not manufacture unit strength, combat utility or weights.
Each score contribution remains visible in the returned plan.

`backends.purchase_click.guarded_executor(capture_record, observer=inspect_game,
enabled=False)` returns the actual guarded callback. It sends nothing on import
or factory creation. The owning controller must explicitly enable it within
its existing authorization; the adapter inherits exact process/geometry/hit
tests, interruption hooks, tag32 ownership, short click and emergency stop.
The original broker and diagnostic are unchanged. Dispatch rechecks price,
currency, balance, hero, target and empty slots against the fresh frame. Old
replay cannot be used to dispatch. The original plan's five-second expiry
cannot be extended through recapture or a larger caller TTL.

## Faster saved-frame OCR

`runtime.batch_ocr.read_regions(frame, new_output, names=("round", "energy"))`
starts one PowerShell/Windows OCR process for all requested small regions.
`runtime.observe_minimal_state.run_saved` now uses those two necessary dynamic
regions by default. Pass `region_names=tuple(REGIONS)` for the six-region
diagnostic. The original source hash/time remain unchanged. Crops stay in
memory, so no new PNG files consume the shared screenshot budget.

`read_regions(..., regions={name: (x,y,w,h)}, cache=previous_batch_json)` also
accepts an explicitly reviewed regional layout for later price/control OCR.
It validates source/profile hashes, geometry, unique regions and returned pixel
hashes. Only `shop_*_name` regions may hit the static cache, and only when actual
BGRA pixels, coordinates, scale, language and Windows version are identical.
Dynamic round/energy/price/control regions always run OCR again before action.
Cache results remain candidates, and static names are not a selected-player
proof or stable hero ID by themselves.

One actual saved frame was measured, without capture/input: six regions
1.818 s, two dynamic regions 1.378 s, six with four static cache hits 1.484 s.
The older six-crop/process implementation's recorded time was about 16.53 s.
This is a saved-frame wall-time benchmark, not an end-to-end live latency
guarantee. The readouts remained round 4 / timer 45 / energy 28; names still
failed strict identification. Confidence stays null and TTL remains 5 s.
