# Keep synthetic mechanics inside synthetic strategy evidence

The shared `decide()` entry previously required explicit opt-in for
`test_rules_not_gameplay`, but that opt-in did not require synthetic observations.
Matching build/version strings could therefore allow manually labelled evidence
to be scored under synthetic rules. The rolling adapter already rejected
non-synthetic observations; the generic entry needed the same domain boundary.

The reverse boundary also had a gap: a `gameplay` registry rejected synthetic
events, but did not inspect sources in cached own fields, opponent fields or ban
evidence. A faulty adapter rebuilding caches could mix domains while its event
stream appeared acceptable.

## Source checks before scoring

The shared hard gate now inspects every observation source and cached evidence
source, including own fields, all remembered opponent fields and the current ban
field. It rejects:

- Any non-synthetic evidence under `test_rules_not_gameplay`, even with
  `allow_test_rules=True`: `non_synthetic_evidence_not_test_rules`.
- Any synthetic evidence under `gameplay`, including cache-only contamination:
  `synthetic_evidence_not_gameplay`.

The check is conservative across the whole retained state, including fields not
used by the highest-scoring candidate. It does not drop inconvenient observations
or silently relabel evidence. A rejected candidate has no score or components,
and no candidate is selected when this global boundary fails.

Existing rules still require the correct rule-source kind for the registry
domain. Observed build and rules version must match the registry, and
`ban_semantics_verified=False` rejects all candidates. Test opt-in waives none of
these requirements. Candidate bindings retain the registry content fingerprint,
domain, state version, ban version and expiry for revalidation.

## Fixture evidence

All cases below are derived from the existing synthetic core scenario. Changing
source labels exercises contract paths; it does not turn the fixture into real
client evidence or establish that any gameplay rule was reviewed.

| Fixture case | Before | After |
| --- | --- | --- |
| All synthetic evidence, synthetic rules, explicit opt-in | Synthetic advisory selected | Same advisory selected |
| Same fixture labelled `manual_annotation`, `legacy_manual` or `reviewed_rule`, synthetic rules, explicit opt-in | Advisory could be selected under synthetic mechanics | No advisory; source-domain rejection before scoring |
| Synthetic registry with only one non-synthetic history/cache source | No complete source-domain check | No advisory for history, own cache, opponent cache or ban cache contamination |
| Fixture registry labelled `gameplay`, manual fixture history, only one synthetic cached source | Cache contamination was not checked | No advisory; synthetic source rejected in every cache location |
| Either fixture domain, unknown ban semantics or mismatched build/version | No advisory | Still no advisory, including with test opt-in |

To make the lossy-advice risk concrete, the test renames the fixture's preferred
operation to `fixture_discard_existing_unit`. Before the fix, the manually
labelled fixture selected that fictional proposal. After the fix, every candidate
is rejected without a score. This label is test data, not an implemented discard
operation; no state transition or game action is performed. All results retain
`execution_allowed=false`, and rejection leaves the input state unchanged.

## Unknown real ban semantics remain a blocker

The [prohibited-formation model](STRATEGY_BANNED_FORMATIONS.md) enforces only its
declared synthetic unit/tag semantics. This change does not activate those
semantics for the real client. It neither removes observed units nor assumes a
sale, refund, replacement cost or permission to settle a real board.

Actual ban objects, scope, timing, mode and applicability to a specific client
version still need reviewed evidence. The existing
[rule draft](../data/rules_review/claims.draft.json) remains inactive. An adapter
must preserve source and version provenance, keep unknown semantics unverified,
and resolve conflicting observations before supplying real advice. It must never
relabel real observations as synthetic to obtain a recommendation.

Source kinds, references and the verified flag are metadata supplied by callers;
they do not prove that an annotation or rule is true. The fixture-only positive
control for the `gameplay` code path makes no claim about actual WXQ rules. A
reviewed real-rule ingestion workflow remains future work.

## Focused validation

Four [domain-boundary tests](../tests/test_strategy_domain_boundary.py) cover
opt-in, both source directions, all four evidence locations, unknown ban semantics,
build/version mismatches and state immutability. The core, rolling and
prohibited-formation suites plus the two simulation strategy-bridge checks pass:
28 targeted tests total. Real Windows DLL loading is blocked during this offline
run; no fitting, training, capture, game input or downloads are needed.

```powershell
python -B -m unittest discover -s tests -p test_strategy_domain_boundary.py -v
python -B -m unittest discover -s tests -p test_strategy_core.py -v
```

Only the shared strategy gate, these tests and this document change. No control
worker files, configuration or branches are changed or merged. No dependency or
project-license choice is added; see [the existing notices](../THIRD_PARTY_NOTICES.md).
