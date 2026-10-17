# Synthetic composition planning and CPU ranking

Every unit, price, slot, interaction, opponent counter and label is
**test_rules_not_gameplay**. This is a runnable engineering comparison. It has no
real Yixing decisions, game outcomes, learned combat model or measured playing
strength. Real copying/ban/economy mechanics are not inferred from this fixture.

## Run

Python 3.10 or newer and the standard library suffice. From the repository root:

```powershell
python -B -m strategy.planning --fixture examples/strategy_synthetic/planning/benchmark.json --allow-test-rules
python -B -m unittest discover -s tests -p "test_strategy_*.py" -v
```

The explicit test flag enables two tiny local CPU fits and the comparison.
The full strategy test-discovery command also performs synthetic fits in the
planning test setup. The separate `AvailabilityTests` class uses exact evaluation
only and does not fit a model.
Without it, the CLI abstains and does not train. No model weights or framework
are downloaded; no network, capture, UI, credentials, GPU or API is used. Output
goes to stdout unless an explicit `--output` path is supplied. To regenerate a
local report:

```powershell
python -B -m strategy.planning --fixture examples/strategy_synthetic/planning/benchmark.json --allow-test-rules --timing-repeats 3 --output examples/strategy_synthetic/planning/comparison_report.json
```

The committed `comparison_report.json` records the measured demonstration:
choices, alternatives' composition breakdowns, root hard rejections, model
coefficients and provenance, training losses, CPU/wall fit time and P50/P95
planning wall latency. Timings vary by machine and load; the fixture, choices,
feature definitions, seeds and fitted coefficients are reproducible. The sampled
timings describe small local engineering operations, not real-time game latency.

## What changes the choice

The declared toy starts with A on a two-slot board and two credits. B costs two
credits and has isolated value 6. C costs one and has isolated value 2. A has
isolated value 1; A/C together activate a declared +8 interaction. Buying puts a
unit into hand; deployment is a separate step. The fixture fully declares its
small transition subset, including replacement/discard behavior.

| Contrast | Independent-card evaluation | Interaction-aware two-step plan |
| --- | --- | --- |
| A present, B/C offered | Buy B, then deploy: total toy utility 7 | Buy C, then deploy: total 11 |
| A absent | Buy B | Buy B |
| C banned | Buy B; C is hard-rejected | Buy B; C is hard-rejected |
| No credits | Hold | Hold |
| Declared opponent disables A/C | Buy B | Buy B |
| Normal/counter opponents both plausible | Buy B | Buy B under the named worst-case criterion |
| A/C deployed, stronger isolated D in hand | Replace A with D: total 7 | Hold A/C: total 11 |
| A/D deployed and C offered, three slots | Buy C | Buy C; show both pair and three-unit interactions |
| Required resource unknown | Abstain | Abstain |

Depth-one interaction evaluation holds when a purchase has not yet produced
supported board value. Depth two can compare the subsequent deployment. Equal
values prefer holding rather than arbitrary spending. These choices follow the
declared toy objective; credits and undeployed units have no terminal utility in
this limited horizon. That simplification is not an economy rule for WXQ.

## Actual implementation

`strategy/planning/model.py` declares the synthetic world and exact local
transitions' state/value representation. Pairwise and higher-order interactions
require all named units. `formation_value` explains isolated value, activated
interactions and roles. `candidates.py` enumerates current offers, hand deployments,
and board substitutions; it does not enumerate two fixed lineup recipes. Every
node binds the actual board/hand/offer evidence and reuses the integrated core's
hard filter. Simulated facts remain tree-local predictions and are never merged
into an observed match.

`search.py` evaluates supported successors at depth one or two, with explicit
node/time limits and deduplication scoped to each first action. Multiple declared
opponent scenarios use worst-case value without invented probability weights.
The planner returns one immediate candidate; its continuation labels have
`analysis_only: true`, and every result has `execution_allowed: false`.

The evaluator is replaceable through its immutable version/domain/feature binding,
`score(FormationValue)` and `contributions(FormationValue)` methods. The supplied
evaluators are isolated-card points, exact declared interaction utility, and a
learned CPU ranker. Model estimates never replace the independent legality gate.
Unknown real rules are not supported: `ToyWorld` accepts only the explicit test
domain, requires declared verification, and the policy requires opt-in.

## What the CPU model learns

`ranker.py` uses bounded pairwise logistic SGD over three structured features:
isolated formation value, active pair interaction value and active higher-order
interaction value. These interaction features are supplied from the declared toy
rules. **The model learns ranking weights, not game rules or new synergies.**

The frozen training families enumerate legal-sized toy formations and label them
using their declared utility. Non-tied within-family pairs create the learning
target. Feature scaling uses training families only. The different A/B/C/D
demonstration world is held out; all its contrast variants share one family and
are not independent games. Model JSON includes the feature version, domain,
training-family IDs, data digest, coefficients, scaling, seed and epoch budget.
No pickle or external runtime is needed.

The comparison includes an interaction-feature ablation. On the recorded toy
cases, the full ranker retains the A/C choice and the value of preserving its
link; the ablation falls back to the independent-card preference. This is a
representation/learning sanity check. It does not establish that training helps
real decisions, that the supplied features are sufficient, or that exact search
needs a learned replacement. The report retains the simpler exact baseline.

## Cancellation, fallbacks and final validation

Budgets are cooperative: checks surround each bounded local operation. Node/time
exhaustion or an unavailable evaluator returns a freshly validated hold from the
original observed state when still eligible. Cancellation returns no selected
action. A caller-supplied arbitrary blocking evaluator cannot be preempted by this
loop; this is not an input watchdog or a hard real-time deadline guarantee. CPU
fitting also has an epoch/pair/time budget and cancellation, returning no partial
model when stopped.

Immediately before returning advice, the planner runs the hard filter again.
Callers can supply `latest_snapshot()` returning the latest observed state and
rule world. Changed bans, state/rules versions, content, expiry, unavailable
snapshot or cancellation revoke the result. A stored action can also be checked
with `revalidate`. Neither check grants execution permission or implements input.
Ordinary evaluator errors, including I/O failures, use the gated hold fallback;
ordinary final-snapshot errors abstain. Process interrupts are not swallowed.

Focused tests demonstrate the meaningful composition contrasts, successor-based
candidate generation, forged-target rejection, model round trip and ban
independence, budgets/cancellation, stale/unknown rules, and a final ban/rule
change. The CLI also runs with capture, input, network and heavyweight model
imports blocked. These are offline invariant checks, not live game tests.

Before real strategy evaluation, the project still needs version-bound copying,
capacity, bans, economy, keyword/interactions and opponent evidence; permitted
decision-time annotations; blind labels and independent full-match evaluation.
The rule-review drafts remain inactive. No first-place/top-three percentage is
claimed by this demonstration.
