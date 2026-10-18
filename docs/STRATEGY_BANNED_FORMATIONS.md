# Do not settle or fund transitions with a prohibited formation

The [project contract](../PLAN.md) treats confirmed current-match bans as hard
constraints before scoring. The rolling model previously checked only an action's
target card/tags. An already deployed prohibited unit could remain on the board,
activate links, earn round utility and advance to future income through
`end_round`, whose action had no target card. That is a concrete inconsistency
inside the declared model, independent of unknown real WXQ parameters.

[`move_reasons`](../strategy/rolling/model.py) now checks the entire active board
before any modeled settlement. Both immediate-action generation and every search
transition use the same gate. A prohibited board cannot finish a round or collect
the next frame's income, and no completed alternative can score that board.

## Before/after decision evidence

These cases reuse the existing synthetic pivot fixture. A/B/C/E have isolated
utility 1/6/2/3. A+C contributes a declared link of 8; A+E contributes 6 against
the guard profile. Replacement pays one credit and two utility points. None of
these numbers is a verified WXQ mechanic or calibrated strategy preference.

| Observed situation | Prior behavior | Corrected behavior |
| --- | --- | --- |
| A/B deployed, C/E held, one credit, guard, no bans | Replace B with C; A/C utility 11 - 2 = 9 | Same legal result; no ban conflict exists |
| Same position, A confirmed prohibited | Still replace B with C and score prohibited A/C at 9 | Replace A with E; legal B/E utility 9 - 2 = 7, with one credit actually paid |
| Same prohibition, zero credits, two-round request with two credits income on entry to round two | Select `end_round`, count prohibited A/B in both rounds and report utility 14 | No supported complete route; return non-settling `hold` and explain the unresolved prohibition. Future income cannot be collected to evade the current gate |
| One credit available for repair, same two-round declaration, explicit reserve target 2/value 3 | Existing reserve preference is unchanged | Repair before settlement: 9 + 9 - 2 + one terminal reserve 6 = 22; ledger pays one credit, receives two, finishes with two |

Unit-tag bans work through the same check: a tag on A identifies A in the conflict
record. A prohibited card held off-board still cannot be bought/deployed, but its
presence does not falsely mark a legal active board as prohibited.

## Repair uses only declared actions and costs

The observed banned unit is not silently removed from state or from scoring
inputs. Existing preparation moves may lead to a legal board through the model's
already declared `replace` operation. Every supported route pays its explicit
credit and switching-utility costs before settlement. There is no added sell,
refund, free removal, new income source or game execution operation.

If no complete legal route is found because of insufficient resources or search
budget, `hold` remains the existing non-mutating fallback. The reasons now state
`banned_board_requires_supported_replacement` and
`hold_does_not_settle_or_resolve_bans`. It has no completed-path utility and is not
permission to end the round. Unknown transition costs still produce abstention;
they are not zero. Unknown board values retain the conservative support behavior.

`Result.root_formation_conflicts` records each observed active unit and its exact
matched confirmed ban IDs/tags. Immediate `end_round` rejection names the unit.
Existing round traces and resource ledgers explain the legal replacement path.
Original observations remain unchanged, and `execution_allowed=false` remains.

New ban observations still invalidate old advice through state/ban/rule bindings
and final revalidation. Stale opponent memory and cancellation do not get waived
to repair a prohibited board. Continuations still require fresh observations and
replanning; they are not queued executable commands.

## Focused validation and real-rule boundary

Three focused methods in [the formation-ban tests](../tests/test_strategy_formation_bans.py)
cover the decision contrasts, tag/held-card distinction, accounting, unsupported
costs, budget fallback and invalidation. The existing rolling, resource-option,
support-scope and memory-origin tests plus two simulation bridge/visibility checks
pass: 29 targeted tests in total. Real Windows DLL loading was rejected during
the run; no fitting, training, downloads, capture or game input occurred.

```powershell
python -B -m unittest discover -s tests -p test_strategy_formation_bans.py -v
python -B -m unittest discover -s tests -p test_strategy_rolling.py -v
```

This enforces consistency for the current declared synthetic unit/tag ban model.
The actual game's ban objects, scope, timing and treatment of an apparently
prohibited owned unit remain unknown until version/mode-applicable rules and
observations are reviewed. A real adapter must resolve contradictory observations
rather than assume a synthetic repair is executable. The existing
[rule draft](../data/rules_review/claims.draft.json) is not activated. This change
does not connect real recognition, input or a game policy and makes no win-rate
claim. Control-worker files, configurations and branches are not changed/merged.

This is original standard-library project code and synthetic evidence with English
documentation. No dependency or project-license choice is added; see
[the existing notices](../THIRD_PARTY_NOTICES.md).
