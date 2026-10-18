# Connect recognized frame fields to the strategy advisor

[`strategy.recognition`](../strategy/recognition.py) converts one explicit
recognizer result into match-start, own-state, ban and opponent observations.
The controller supplies recognized field values; this module does not perform
pixel recognition or invent game rules. It applies a complete frame atomically
through `Advisor.observe_batch`, then the normal advisor can rank supported moves.

```python
from strategy.recognition import ingest_frame, input_requirements

needs = input_requirements(registry_record, controller_operations=implemented_operations)
receipt = ingest_frame(advisor, recognized_frame_batch, now=received_at)
if receipt["status"] == "observed":
    point = advisor.decide(decision_at=cutoff)
    # Apply pending fresh evidence, validate the proposal, resolve the actual UI
    # and verify its observed result in the controller.
```

The [frame batch schema](../schemas/strategy-recognition.schema.json) reuses the
existing field/observation definitions. The
[synthetic batch](../examples/strategy_synthetic/session/frame-batch.synthetic.json)
is runnable against the existing synthetic session configuration and produces
the explained `replace:B->C` choice at nine artificial utility points. Its data
kind is explicitly synthetic; it is not an observed real match.

## What the real producer supplies

Use `data_kind=screen_recognition`, an actual frame SHA256, extractor version,
observed/ingested times and a stated time basis. A positive active-battle scene
is required before creating match evidence. A menu, keypad or lobby never
creates a match-start or board, even if some UI fields are recognized.

`host_acquisition_only` and an unavailable semantic observation time remain
pending. In particular the current WGC acquisition timestamp must not be silently
promoted to a source-frame timestamp. `synchronous_visible_capture` describes an
actual visible capture observation; `verified_source_frame_timestamp` requires
that timestamp to be independently available. These are producer-supplied facts,
not proof derived from a label. Preserve unknowns when the basis is unsupported.

Context supplies match-local identity, round, phase, confidence and known build/
rules version. `start_match=true` is an explicit lifecycle assertion after an
active match is recognized. Versions can remain null, which preserves observed
facts but cannot satisfy a matching reviewed gameplay registry. Never infer a
player/card identity merely from a display name.

Own fields and each opponent's fields keep their explicit status, value and
confidence. Missing fields retain earlier evidence; they do not imply zero,
sale or empty space. Ban evidence is emitted only when explicitly supplied,
including an unknown ban field when that is the actual recognition result.
Opponent identity and full/partial coverage are explicit. No source confidence
is inferred from a template similarity score.

The source reference binds frame hash, extractor and time basis. Event IDs bind
the entire batch content, so exact retransmission is idempotent. An invalid
member cannot partly update the advisor. A menu/uncertain frame revokes the
current proposal handle without fabricating a match-end or erasing prior facts.
The advisor also suspends reissuance until a newer, sufficiently confident
state/match context is ingested. Recalling `decide` on the old snapshot cannot
revive the suspended intent. The controller obtains supported new evidence
before using a new decision.
The JSONL service also accepts `observe_batch` and `invalidate` commands.

## Concrete remaining rule and operation gaps

`input_requirements` returns each supplied rule's exact field paths, predicates,
resource costs, score definitions, source and verification state. A controller
operation inventory marks which semantic operations it actually supports. This
is a capability/recognition checklist, not permission to dispatch a rule merely
because its metadata says verified.

The current game adapter implements custom-selection confirmation, keypad digits
and a separate taskbar activation transaction. It does not implement battle
buy/sell/refresh/deploy/copy operations or their result contracts. The real
recognizer has not supplied an active battle or resolved own/opponent board,
resources, capacity, chess-player ability state and semantic bans to this module.

The tracked [rule draft](../data/rules_review/claims.draft.json) is still
`draft_not_executable`, with `runtime_eligible=false` and null client build/mode.
Its unresolved items directly relevant to usable Yi Xing decisions are:

- G01: running build, balance version, server and mode applicability.
- G02/G03/G05/G06: copy availability/order, effective payment/modifiers/refunds,
  copied properties/duration and capacity/overflow interactions.
- G04/G07: eligible opponent/hero pool and control/randomness, plus ban objects,
  scope, acquisition/copy exceptions and semantic IDs.
- G08/G09: actual income, prices/returns/upgrades/refresh distribution, entity IDs,
  keyword order and formation interactions.
- G10/G12: opponent scenario coverage and validated combat/damage/outcomes.

The generic registry currently expresses fixed reviewed resource costs. A
conditional ability discount needs reviewed rule branches tied to observed skill
state, or a separately implemented dynamic-cost model; this adapter does not
guess that expression. The manifest reports dynamic-cost expressions, combat
outcome modeling and a UI postcondition contract as unsupported capabilities.
Observed UI fields may be recorded before these gaps are resolved, while real
action proposals remain unsupported.

Four focused tests cover a complete frame-to-ranked-decision path, duplicate
delivery, atomic failure, unknown resources, real-source ingestion, exact rule
dependencies and revocation after a lobby/host-only frame. The local V4 package
passes 109 relevant offline tests with native API/Tk creation blocked; Python
compilation and both PowerShell helper syntax checks pass. No input or capture
is performed by this integration.
