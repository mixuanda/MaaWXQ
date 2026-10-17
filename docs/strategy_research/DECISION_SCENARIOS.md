# Situation-dependent decision review

Research specification, 2026-10-17. These are questions to annotate and compare,
not claimed Yixing tactics. No real decision labels or match outcomes have yet
been supplied. The current synthetic linear scorer is an infrastructure baseline;
it neither simulates these situations nor demonstrates strategic flexibility.

## The comparison cases

| Case | Competing supported options | Evidence that can change the preference | Missing-rule gate |
| --- | --- | --- | --- |
| D01 Spend or preserve options | An available immediate improvement versus conserving resources for later choices | Current health, improvement usable now, remaining energy, actual offered cards, threat range and reversible substitutes | G03/G08/G09/G12; no invented income breakpoint |
| D02 Continue or pivot | Improve the present formation, substitute a role, or begin a feasible transition | Actual board/hand/shop, confirmed bans, missing roles, verified interactions and total transition cost | G07/G08/G09; banned routes disappear before evaluation |
| D03 Respond to opposition | Reposition or improve against plausible observed threats versus retain broader flexibility | Which match-local opponents were seen, their evidence age, actual coverage and supported alternative matchups | G09/G10/G12; a scouted opponent is not a selected matchup |
| D04 Use or defer a copy opportunity | Use an actually available ability, preserve resources, or request missing evidence | Verified trigger window, effective cost, legal pool, useful resulting options, hand/board space and competing plans | G01-G07; no copy action until all critical mechanics are resolved |
| D05 Upgrade or use current offers | Pay an observed upgrade cost versus acquire/play an actually available card | Current capacity, next verified unlock, currently offered value, resource runway and near-term risk | G08/G09/G12; no assumed shop-odds or upgrade table |
| D06 Compete for an auction offer | A legal bounded bid versus passing and preserving alternatives | Exact offer, legal limits, observed resource budget, timing and verified settlement effects | G08/G11; no all-in rule or guessed dividend formula |
| D07 Gather information or decide | Review an unresolved field/opponent versus select a robust supported action | Which unknowns reverse the ranking, observation time cost and remaining deadline | G10; never request a live capture while current pause applies |

For each case, annotate at least two feasible options when they exist. A fixed
lineup recipe is an optional proposal seed, not a complete candidate space.
Retain alternative roles and short action orders that the observed position
actually permits. Never invent a shop card, future opponent board or random draw
to make an option look attractive.

## Prove useful adaptation with contrast pairs

Create matched cases from independently reviewed decision points or explicitly
marked synthetic transitions. Change one relevant feature while retaining its
source/version bindings:

- Replace a visible opponent threat; compare which supported action changes and
  why. Do not require a switch when both actions remain equally good.
- Change available resources, a real offer or transition capacity; recompute
  affordability and opportunity cost rather than follow a round script.
- Add a confirmed ban; no model score can rescue its dependent route.
- Remove a critical fact; the policy should expose uncertainty or abstain rather
  than silently fill the missing value.
- Change only an opponent display name or event arrival duplication; identity
  and strategic preference should remain stable.
- Change the patch or effective rule content; expire old proposals rather than
  reuse an old guide as current knowledge.

Human review records whether the choice *should* change, can remain tied, or is
unanswerable. Count justified adaptation and candidate coverage, not action-change
frequency or prose quality. Keep disagreements and counterexamples.

## Annotation templates and freeze/reveal

The [decision template](../../data/rules_review/decision_point.template.json) is
an unfilled research form, not runtime Observation JSON. The [outcome
template](../../data/rules_review/outcome.template.json) is a separate sealed
channel. Both are explicitly ineligible for inference.

1. Assign anonymous match, replay-family and decision IDs. Resolve permission,
   server/mode/build and cutoff time; unknown values remain null.
2. Expand each observed field using `field_annotation_shape`: status, value,
   source/event reference, `last_seen`, round, phase, coverage and confidence.
   Null confidence is uncalibrated/unknown, not certainty. An observed empty list
   needs positive evidence; an unobserved list stays null.
3. Keep each resolved opponent under a match-local ID. Store unresolved sightings
   separately. Record visible units, levels, equipment/effects and positions only
   when actually observable. A partial board never proves other units absent.
4. Freeze the decision-only record before viewing later frames or outcomes.
   Annotate supported alternatives, rule gaps, costs and what would reverse a
   preference. Leave hypothetical counterfactual results unknown.
5. Conduct blind review with policy identity and outcome hidden. Store acceptable
   actions, pairwise preferences/ties, missing alternatives and disagreements.
6. Reveal and link the separate outcome afterward. Record what a human actually
   chose, deviations, uncertain transitions and eventual results. Do not label
   every action in a winning match as good or infer an unchosen action's result.

The public files are empty templates. Do not fill them with account IDs, raw
capture paths, private replays or identifying match details. Build permissioned
private records separately and publish only explicitly cleared derivatives.
While game observation is paused, these forms can be completed from already
permitted, available evidence; they do not authorize new screen acquisition.

## Learning-ready labels without fabricated expertise

Whole matches and duplicate replay families stay in one split; adjacent frames
cannot populate both training and test. Use chronological/patch holdouts for
later real-data experiments. Candidate coverage is measured before ranking;
otherwise a perfect ranker can still miss the useful action.

An expert preference, actual human action, observed local transition, eventual
placement and synthetic oracle label are different targets. Record their origin
explicitly. Unknown behavior probabilities remain null. A guide suggestion is a
reviewable proposal, not an expert label automatically accepted by the learner.

The next CPU demonstration may use synthetic labels derived from declared test
transitions. Its result can demonstrate learnability, ranking integration and
latency only. No synthetic agreement score is evidence of real Yixing strength.
