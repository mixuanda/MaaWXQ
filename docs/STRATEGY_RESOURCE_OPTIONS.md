# Joint resource, composition and opponent decisions

This slice changes the strategy core's comparison objective, not the simulator.
It adds the missing option value of retaining resources to the existing
opponent-conditioned formation evaluation and replacement costs. All demonstrated
prices, interactions and utilities remain `test_rules_not_gameplay`.

## The decision gap

The previous search enforced affordability and deducted declared replacement
utility costs. Leftover credits had zero terminal utility, so it could not
compare a supported board improvement against explicitly valuing future choices
preserved by cash. That objective is retained as the default baseline. Nonzero
resource preferences now require a named, visible assumption rather than a
hidden threshold or an invented game-economy rule.

`EconomyObjective(reserve_target=2, value_per_credit=3)` means:

```text
terminal resource value = min(final credits, 2) * 3
joint value = sum(weighted supported round formation values)
              - declared switching utility costs
              + terminal resource value
```

The two-credit target and three utility points per credit are deliberately
declared test assumptions. They are not interest, a real income breakpoint,
survival value, win probability or a calibrated WXQ recommendation. Credits are
not created by this calculation. Resource payments still occur in the existing
transition ledger, independently of the scoring preference.

The value is added **once at the completed horizon**, not once per round or per
action. This avoids repeatedly rewarding the same retained credit. Spending can
still win when its useful interaction outweighs the resource option lost. Spare
credits above the stated target have no reserve value in this simple assumption.

## Existing interface and explanations

```python
from strategy.rolling.economy import EconomyObjective
from strategy.rolling.search import Budget, plan

result = plan(
    observed_state, declared_world, opponent_id,
    now=decision_time, policy=explicit_test_policy,
    budget=Budget(horizon=1),
    economy=EconomyObjective(reserve_target=2, value_per_credit=3),
)
```

Default `EconomyObjective()` values both settings at zero, preserving the
previous objective. Invalid, missing or nonfinite settings are rejected. The
target's supported range `[0, 256]` is a configuration bound, not a game wallet
limit. Passing unknown credit evidence still abstains; it never becomes zero.

Each result records the immutable economy objective, version, units and explicit
assumption origin. Each completed alternative exposes `terminal_resource_value`
and `resource_value_delta_from_root` alongside round formation components,
opponent profiles, switching utility cost and the existing resource ledger.
The delta is final reserve value minus its value at the observed root; in a
multi-round declared-income model it can include an income-driven change.
It must not be mislabeled as only a purchase cost.

Candidate generation, ban filtering and final state/rule/memory validation remain
independent. Unknown real mechanics cannot be made legal by a reserve score.
Changing the objective requires replanning. Action revalidation checks legality
and evidence binding; it does not certify an old ranking under new preferences.

## Distinguishing scenario results

The tests reuse the existing synthetic pivot world. A/B/C/E have isolated values
1/6/2/3 and prices 0/2/1/1. A+C gains a declared pair value of 8; A+E gains 6.
The declared guard profile permits those links; the breaker disables them.
Replacement costs one credit plus two utility points. Only the credits/board/
hand/opponent evidence stated below changes. The same B/C offers are used in
the shopping cases; no generated card or opponent ID receives special handling.

| Observed situation | Recommendation with the explicit reserve assumption | Joint utility and explanation |
| --- | --- | --- |
| Empty board, 2 credits, guard, B/C offered | End the modeled round | 6 retained-resource points; B is affordable but ties at 6, so preserve rather than spend on a tie |
| Empty board, 5 credits, guard, same offers | Buy B, then deploy | 6 formation + 6 reserve = 12; the purchase leaves the target reserve intact |
| A deployed, 2 credits, guard, same offers | Buy C, then deploy | 11 formation + 3 reserve = 14; useful existing support justifies spending |
| A deployed, 2 credits, fresh breaker view, same offers | End the modeled round | 1 formation + 6 reserve = 7; the previously valuable A/C link is disabled |
| A deployed, 5 credits, breaker, same offers | Buy B, then deploy | 7 formation + 6 reserve = 13 |
| A deployed, 2 credits, partial view containing only the shared enemy marker | End the modeled round | Both guard and breaker remain plausible; worst-case value does not assume unseen units absent |
| A/B deployed, C/E held, 2 credits, guard | Keep the formation/end round | 7 formation + 6 reserve = 13; the legal C pivot gives 11 - 2 + 3 = 12 |
| Same formation/hand/opponent, 5 credits | Replace B with C | 11 - 2 + 6 = 15; payment leaves the reserve intact |
| Same richer pivot state, C confirmed banned | Replace B with E | 10 - 2 + 6 = 14; the C route is hard-rejected before scoring |

`end_round` is the existing toy settlement operation, not a command to an actual
game client. These results establish supported contrasts under the declared
objective, not that saving or pivoting at these amounts is good real gameplay.

A fresh opponent-change event changes the recommendation and invalidates the
old advice. A 21-second-old opponent memory, unknown resources or cancellation
returns no selected advice. A two-round preserve path receives two board points
plus one reserve value of six, totaling eight: it does not double-count reserves.

## Validation and direct reuse

```powershell
python -B -m unittest discover -s tests -p test_strategy_economy.py -v
python -B -m unittest discover -s tests -p test_strategy_rolling.py -v
# Full offline regression, including the existing small synthetic CPU fits:
python -B -m unittest test_state test_capture test_child_session test_child_control
python -B -m unittest discover -s tests -p "test_strategy_*.py" -v
```

Five focused methods cover the cash/support contrasts, refreshed/partial
opponents, replacement tradeoffs, single terminal valuation/unknown gates, and
an opt-in policy using the existing `ToySimulator` and audited episode runner.
The ten existing rolling tests and two existing simulation bridge/visibility
tests also pass. Those focused checks require no ranker fitting. The complete
98-test offline regression passes, including the pre-existing small synthetic
CPU ranker fits and CLI checks. An integration guard rejected any `ctypes.WinDLL`
call and recorded zero such calls. No external model was downloaded and no game
interaction or real-data training was performed.
Scenario preference and component accounting are the evidence; method count is
not a measure of strategy strength.

The simulator's default policy is unchanged. A caller can pass the new objective
when invoking the existing core, as in the tested policy closure; no simulator
feature, default gameplay parameter or external dependency is added. This slice
does not modify the separate live-game task or any capture/input file.

## Real-rule boundary and later evidence

The [official October 15 v1.6.1 announcement](https://www.taptap.cn/moment/859509109601339933?group_id=399839)
states Yixing's Yushi energy cost changes from 8 to 6 and reports a level-six
talent-description correction. That is version-scoped publisher evidence;
the running build/mode/effective cost still require the separate live review.
The existing [rule-review draft](../data/rules_review/claims.draft.json) keeps
current-client applicability unknown. This resource objective implements no
copying action, hardcodes neither copy cost, and promotes no draft game rule.

Health, damage/survival risk, held-card option value, unknown future shops,
real interactions and empirically calibrated reserve preferences remain gaps.
The current model cannot claim first-place or top-three improvement. Nonzero
defaults should not be enabled for real play from these toy contrasts alone.

For later human review or post-training work, preserve visible decision-time
state, source/cutoff and memory coverage, legal/rejected alternatives, objective
settings/version, score components, policy commit and actual intervention.
Keep later outcomes in a separate channel. The same engine seed/source digest
does not identify a changed strategy objective or policy commit. A chosen action
or high toy utility is not an expert label. This change provides explanatory
fields in the existing result; it does not start a data platform or training run.
