# Bind opponent coverage to the board observation

An opponent summary can combine fields from multiple observations. Previously,
rolling assessment used that summary's `coverage` to interpret `board_ids`, even
when the board came from a different event at the same timestamp. A note-only
`full` observation followed by a same-time `partial` board therefore made the
partial board look complete. Unseen counter units could be incorrectly excluded.

[`assess`](../strategy/rolling/memory.py) now resolves the board field's originating
event and checks its match, opponent, source, observation time, round, phase and
exact field content. Its **own coverage** determines full/partial interpretation.
Missing, ambiguous, mismatched or not-yet-ingested origins yield no belief/advice.
Explicit origin build/rules versions must match the immutable match context.

The memory digest includes the original board event as well as the cached summary
and memory policy. An altered coverage assertion cannot reuse an old evidence
digest merely because the summary and state version stayed unchanged in a bad
cache. Normal reduction still rejects rewriting an existing event ID.

## Reproduced before/after decisions

The tests extend the existing synthetic pivot fixture: the guard profile is
`enemy-base/guard`, and the breaker profile contains those markers plus `breaker`.
The latter disables the existing synthetic links. A is deployed, B/C are held,
one credit remains, and the board capacity is two. This is declared test data,
not a description of WXQ units or real counter mechanics.

| Same-time observations, in order | Previous decision | Corrected decision |
| --- | --- | --- |
| Note-only `full`, then board `partial` | Treat board as full; deploy C for the assumed 11-point guard result | Keep guard and breaker plausible; deploy B for supported worst-case utility 7 |
| Note-only `partial`, then board `full` | Treat board as partial; deploy B | Use the actual full board evidence; deploy C with utility 11 |

Partial evidence is not always treated as full, and full evidence is not always
downgraded. Interpretation follows the exact board observation. No probability,
new utility weight or opponent-transition rule is introduced.

The same JSON boundary cases also show:

- A 21-second-old board fails the existing 20-second engineering memory limit.
  A newer unrelated note cannot refresh it. A new partial board restores B advice
  with the new board event ID and age zero.
- A fresh full guard board supports C. Confirming C prohibited switches advice to
  B, and the previous C advice fails ban-version validation.
- Explicit JSON build/rules mismatches are rejected by the reducer without
  changing the previous state. Omitting those fields inherits the match context;
  it does not fabricate a new observation of the running client's version.

## Decision evidence and adapter contract

`Belief` already carries board event IDs, source references, last seen, age,
coverage, supported profiles and its digest. It now also exposes confidence,
phase, match-context build/rules versions and the board event's explicitly
observed versions. `observed_game_build` / `observed_rules_version` remain null
when omitted; `coverage_origin=board_observation_event` identifies the coverage
source. The result/advice still bind world/rule content, state, ban version and
horizon; final revalidation checks them independently.

For a replayable decision, retain the actual `Observation` stream and its cutoff.
Do not reconstruct a board from just an `OpponentMemory` summary or discard its
source event. Minimum applicable input remains:

| Evidence | Required content |
| --- | --- |
| Match context | Unique match start, applicable reviewed build/rules version, current round/phase and context confidence |
| Opponent board | Match-local opponent ID, event/source references, observed/ingested times, board IDs/status/confidence, round/phase, explicit full/partial coverage |
| Bans | Explicit observed banned tags, confidence, current match and applicable semantics/version; retain all confirming events because accumulated bans can outlive the latest ban record |
| Own decision state | All operation-required resources, zones, slots and costs from the [live handoff](STRATEGY_LIVE_HANDOFF.md), without defaulting unknowns |

Confirmed bans still persist for the match; board freshness and candidate expiry
remain separate gates. The latest ban record alone is not a complete provenance
index for every older confirmed tag, so replay must preserve the existing event
stream. This increment adds no data platform or new collection loop.

## Focused verification and limits

Four focused methods in [`test_strategy_memory_origin.py`](../tests/test_strategy_memory_origin.py)
exercise JSON decoding, reduction, memory assessment, planning and revalidation.
They cover the decision contrasts above and missing/mismatched origin refusal.
Ten existing rolling, five resource-option, five support-scope and two simulator
bridge/visibility tests also pass: 26 targeted tests in total, with zero native
DLL calls and no fitting, training, downloads or game interaction.

```powershell
python -B -m unittest discover -s tests -p test_strategy_memory_origin.py -v
python -B -m unittest discover -s tests -p test_strategy_rolling.py -v
```

This fixes a concrete evidence-chain error needed before real observations can
be trusted. It does not connect real recognition or execution: rolling advice
remains synthetic-only and `execution_allowed=false`. Actual client applicability,
real card identities/links/costs and live postconditions remain unknown until
separately reviewed. No win-rate or real-game acceptance claim follows.

This is original standard-library project work with synthetic fixtures and English
documentation. No copied upstream implementation or dependency is added, and no
project license is selected or changed. See [the existing notices](../THIRD_PARTY_NOTICES.md).
