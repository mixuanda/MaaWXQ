# Replaceable planning and evaluation contracts

Design proposal, 2026-10-17. This incorporates the supplied
`AI_STRATEGY_OPTIONS.md` addendum. The initial core's immediate candidate filtering
and linear scoring are not a search planner or a learned policy. This round
changes no runtime interface; the contracts below reserve the next integration
boundary for review.

## Responsibility boundaries

| Component | Input and output contract | Required behavior |
| --- | --- | --- |
| `CandidateGenerator` | Frozen request, observed state, reviewed rules, belief and budget -> semantic candidate batch with coverage notes | Propose actual available operations, substitutions and short orders. Templates cannot exhaust the space. |
| `BeliefUpdater` | Previous match-local belief plus observations and cutoff -> plausible state scenarios with provenance | Keep facts separate from hypotheses, retain unresolved identities and partial coverage; do not fabricate probabilities. |
| `TransitionModel` | Scenario, legal candidate and frozen rule subset -> supported successor(s), explicit stochastic support, or `Unsupported` | Apply only validated local transitions. Unknown combat or copy semantics stay unsupported. |
| `ValueEstimator` | State/candidate or leaf state, objective and evidence scope -> value components, support status and uncertainty | Permit transparent, learned or external estimates under identical legality constraints; state units and calibration status. |
| `Planner` | Frozen request, legal candidate batch, transition/evaluation interfaces and budget -> one next recommendation plus contingent analysis | Search supported orders within bounds; compare scenarios and stop at unsupported transitions. No executable action queue. |
| `ProposalProvider` | Minimized approved structured request -> untrusted candidate IDs/rank suggestions or unavailable/error | An optional LLM adviser cannot certify rules or bypass any hard filter. |

Each request binds match/state/ban/rule versions, rule-content digest, evidence
watermark and cutoff, policy/objective version, candidate vocabulary, time/node
budget and seed. A learned estimator also binds feature/preprocessing/model/data
versions. Persist these bindings with evaluation results and invalidate them when
the underlying conditions change.

An implementation may use these protocol signatures without taking a dependency
on a model framework:

```python
class CandidateGenerator(Protocol):
    def generate(self, request, state, rules, belief, budget) -> CandidateBatch: ...

class BeliefUpdater(Protocol):
    def update(self, previous, observations, cutoff) -> BeliefState: ...

class TransitionModel(Protocol):
    def step(self, scenario, legal_candidate, rules) -> TransitionResult: ...

class ValueEstimator(Protocol):
    def evaluate(self, state, candidate, objective, support) -> ValueEstimate: ...

class Planner(Protocol):
    def plan(self, request, state, candidates, belief, transitions, evaluator,
             budget) -> PlanResult: ...

class ProposalProvider(Protocol):
    def propose(self, approved_request, capabilities, budget) -> ProposalResult: ...
```

These are interface sketches, not currently importable implementations.
`CandidateBatch` needs candidates, omitted-operation reasons and generator
version. `TransitionResult` needs support/unsupported status, successor evidence
scope, costs, rule IDs and random-outcome provenance. `ValueEstimate` needs
component definitions/units, model support, uncertainty and unavailable values.
`PlanResult` needs the selected immediate candidate or abstention, alternatives,
searched node count, explored depth, time/termination reason, model/rule bindings
and unsupported branches. An empty search is not a successful plan.

## Concrete planning behavior

Start with exact local accounting and short contingent orders. Expand only when
the transition subset is verified. Enumerate each legal successor, re-run legality
on that successor and evaluate the resulting state, not a score copied unchanged
from the root. Deduplicate equivalent states without merging distinct opponent
identities. A node/time budget must terminate search and identify whether it fell
back to a legal baseline, requested evidence or abstained.

Opponent scenarios can have qualitative support or intervals. Probability weights
require a stated origin and held-out checks; unknown next-opponent assignment is
not a uniform distribution by default. Compare actions across plausible states.
When their ranking reverses under a small plausible change, expose that fact and
consider the information most likely to resolve it. Robust choice criteria must
be named and versioned rather than hidden inside a confident explanation.

Value should compare near-term survival, future options, actual marginal
composition effects, opportunity/transition costs and opponent response. Keep
first-place upside and top-three reliability distinct. Do not add unrelated
metrics with undefined units or report heuristic points as placement
probabilities. A model-supported value cannot turn an illegal or unknown-rule
action into an eligible candidate.

## Optional model/provider boundary

The first lightweight local experiment should rank structured state/candidate
pairs or estimate supported leaf values. Begin with a small CPU model and compare
against the same transparent baseline and search budget. A language model is not
required for that task. No fixed model size establishes adequate strategic
capacity; data coverage and held-out behavior decide whether complexity helps.

Model-adviser output is untrusted. Reject unknown candidate IDs, unsupported
operations, stale version bindings and malformed/incomplete responses. Preserve
offline operation on timeout, quota failure or no consent. Do not silently switch
to a paid provider. A failed/uncertain request is not permission to retry a game
action.

Official OpenAI documentation, checked 2026-10-17, now supports optional,
separately consented ChatGPT plan usage for eligible [open-source and locally
hosted apps](https://developers.openai.com/siwc/token-sharing-open-source).
Identity-only sign-in does not grant inference. This project has no such consent
or integration. Do not reuse another client's stored credentials.

Keep an independent SIWC adapter: its [preview
limitations](https://developers.openai.com/siwc/token-sharing-open-source/preview-limitations)
require HTTP streaming and `store: false`; `temperature` and `max_output_tokens`
are unsupported. The adapter must supply required context itself and wait for a
terminal outcome. The [inference
guide](https://developers.openai.com/siwc/token-sharing-open-source/models-and-inference)
requires account-available models and the public Responses endpoint; partial
stream text does not establish successful completion. These technical
capabilities are not authorization to connect an account or send project data.

This design adds no OAuth, token lookup, network model call, private-data upload,
training job or GPU rental. The user has allowed lightweight local model trials;
the next slice below specifies a CPU-only synthetic engineering demonstration
before implementation is coordinated.
