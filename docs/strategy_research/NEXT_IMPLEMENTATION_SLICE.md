# Next slice: dynamic proposals, short planning and a CPU ranker

Proposed on 2026-10-17 for parent-thread coordination. The user has authorized
lightweight local model attempts. This is a concrete minimum experiment; it does
not start training, download a model, call an API or rent compute in this round.
The initial runtime files remain unchanged. Core edits need a coordinated file
assignment before implementation.

## Available data and honest scope

There are no real labeled decisions or validated copy/combat transitions in the
review package. [claims.draft.json](../../data/rules_review/claims.draft.json)
contains source-scoped facts and explicit gaps. The
[guide/replay ledger](../../data/rules_review/guides_and_replays.json) supplies
review leads with date, patch applicability, prerequisites, counterexamples to
seek and confidence. It contains no expert labels. No currently reviewed complete
high-rank Yixing match has been established; a tournament title or popular guide
is not a verified rank or a representative sample.

Start with **test_rules_not_gameplay** engineering data. Generate labels from a
fully declared synthetic transition/utility function, save its definition and
generator seed, and label every resulting metric as synthetic. A successful
demonstration establishes that the components can learn/compare their declared
toy objective; it says nothing about real playing strength.

## Demonstrate why independent card scores fail

The following is an invented composition comparison, not WXQ rules or card data:

| Synthetic complete formation | Isolated unit values | Declared interaction | Total synthetic utility |
| --- | --- | --- | --- |
| A + B | 1 + 6 | 0 | 7 |
| A + C | 1 + 2 | +8 for the A/C pair | 11 |
| D + C | 5 + 2 | 0 | 7 |

A single-card greedy ranker prefers B over C. The complete formation favors C
because it activates an interaction with A. Replacing A by the individually
stronger D destroys that interaction and lowers total utility. If A is absent,
the ranking can reverse. These are calculable contrast cases, not evidence of
any real synergy threshold.

The candidate evaluator must compute the **marginal whole-team change** after an
operation. Include supported pairwise and higher-order effects, role coverage,
trigger order, temporary/persistent contributions, and which interactions a
replacement removes. A generic faction-count bonus is not assumed: only a
verified mechanic may define a real threshold. A lineup's theoretical terminal
value is unavailable when its intermediate purchases, hand/capacity or resource
path are infeasible.

For the first search fixture, explicitly define this artificial world: two board
slots, A already occupying one, two credits, and offered B/C costing two/one
credits respectively. Buying moves a unit to hand; deploying consumes the free
slot. There are no sale returns, combat transitions or hidden draws in this toy.
Depth-two `buy B -> deploy B` yields utility 7; `buy C -> deploy C` yields 11.
Holding retains A's utility 1. These constants belong only to the toy definition.
The learning target is its complete-formation utility/pairwise ordering, not a
manually invented real-game preference.

Register contrast families before fitting: remove A (B becomes preferable), ban
C (C is rejected), remove the budget (neither purchase is legal), and introduce
a declared toy opponent counter that disables only the A/C interaction (B
becomes preferable). Hide a required cost/resource fact in another family and
require an evidence request/abstention. Every changed preference must have an
inspectable transition or composition reason.

Useful next toy contrasts also change a declared opponent counter, resource
budget, ban, available offer or observation confidence. Define each toy counter
and transition explicitly rather than infer a real matchup. Keep a control pair
that changes only a display name and must retain the same result.

## Minimal implementation and ownership proposal

After the parent confirms file ownership, add new modules rather than replace
the integrated core wholesale:

| Proposed new file | Concrete behavior |
| --- | --- |
| `strategy/planning_interfaces.py` | Typed request/belief/budget/candidate-batch/transition/value/plan interfaces following `PLANNING_EXTENSION.md`; no model runtime or network dependency |
| `strategy/dynamic_candidates.py` | Enumerate actual offers and substitutions supported by supplied rules; include preserve-plan/information alternatives; report omitted operation coverage |
| `strategy/short_planner.py` | Deterministic bounded depth-two exploration of supported local transitions, successor legality, state deduplication and explicit unsupported/timeout fallback |
| `strategy/cpu_ranker.py` | Small CPU pairwise ranking model over structured state/candidate features; versioned serialization and schema checks; no external model download |
| `examples/strategy_synthetic/planning/` | Separate toy transition definitions, contrast families, frozen split manifest and output report, all explicitly test-only |
| `tests/test_strategy_planning.py` | A small set of composition/pivot/order/unknown/budget cases that verify useful behavior rather than increase test counts |

The current core's hard filters remain the independent gate. Apply them before
ranking and at each successor. A provider/model cannot edit bans, prices, rules
or observed state to make a proposal legal. Search returns one immediate
suggestion with contingent analysis, not queued game input.

The dynamic generator should generate both buy/play orders when the declared
toy state supports them, instead of assigning one action per prewritten recipe.
Search must show a case where the lower immediate unit score leads to the better
supported depth-two state. Also show why an apparently attractive pivot fails
when it cannot be afforded or removes an existing interaction.

## CPU learner and comparison contract

Use a compact pairwise logistic ranker first, with deterministic initialization
and standard-library numeric operations sufficient for the toy pilot. Features
must describe the current state and *candidate-induced change*: resource cost,
capacity change, roles gained/lost, active interaction terms, support uncertainty
and declared opponent-response features. Include an interaction ablation. An
additive model over relational features can represent nonadditive formation
effects; a model over independent unit scores cannot recover an omitted relation.

Compare under one frozen request/candidate/evaluation contract:

1. The transparent independent-score baseline, clearly identifying its limitation.
2. Exact short search with the declared synthetic interaction utility.
3. The CPU learned ranker/value estimate, optionally as the search leaf evaluator.

Keep validation and held-out contrast families separate from training families;
split before fitting normalization or choosing settings. Do not report results
on duplicate or adjacent variants as independent data. Pin the toy world, feature
schema, model, splits, seeds and all registered settings. No arbitrary target
accuracy is a playing-strength gate.

The report needs concrete decisions and alternatives, hard rejection reasons,
composition delta breakdown, agreement/regret against the **synthetic** oracle,
candidate coverage, unsupported cases, P50/P95 CPU latency and model size. Compare
with and without interaction features and with and without search at the same
budget. If learning does not improve the registered toy criterion, retain the
clearer baseline and diagnose missing features/data rather than inflate model
size. A neural net or shallow tree becomes a challenger only when there is a
measured reason and a separately scoped implementation.

## What unlocks real strategy evaluation

Resolve the minimum rule subset and obtain permitted manually annotated decisions
using `DECISION_SCENARIOS.md`. Evaluate candidate coverage and blind preferences
before claiming value-model quality. Preserve multiple acceptable actions and
reviewer disagreement. Measure performance by whole matches when independently
authorized; guide agreement, toy labels and replay hindsight are not first-place
or top-three results.

The no-cost local pilot can identify an actual data, feature or CPU bottleneck.
Only a measured useful model and throughput/latency profile can justify a later
GPU budget or provider trial. Neither is needed for this next minimum slice.
