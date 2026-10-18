# Observation-to-decision software API

[`strategy.session`](../strategy/session.py) connects recognized observation
records to the existing strategy core. A recognizer or controller can call the
Python API directly or pipe JSONL to the CLI. No manual actor or desktop tool is
required by this boundary. It returns machine-readable ranked candidates and a
bound semantic action proposal for the independently implemented game adapter.

```python
from strategy.session import decide_observations

response = decide_observations(request, observation_records)
point = response["points"][-1]
proposal = point["action_proposal"]  # null when unsupported
gaps = point["blocking_gaps"]
```

For a current software decision, supply one point at the actual decision cutoff.
Multiple points support replay and explicit objective comparisons; they are not a
queue of actions. Recognition, UI targeting and independently observed result
verification belong to the software pipeline. Assistant-operated remote clicks
do not validate that pipeline.

## Exact interchange formats

- [Observation schema](../schemas/strategy-observation.schema.json): one object
  per JSONL line, or the same object in `observation_records`.
- [Request schema](../schemas/strategy-session.schema.json): engine, explicit
  rules and one through sixteen named decision points.
- [Response schema](../schemas/strategy-response.schema.json): point results,
  ranked candidates, concrete gap codes and the serialized action proposal.

The standard-library runtime decoders additionally enforce provenance, versions,
numeric finiteness, chronology, evidence freshness, budgets and model support.
The schemas describe interchange shape; they do not verify real game rules.
Duplicate JSON keys and nonfinite constants are rejected. Input files are bounded
to 16 MiB and logs to 2,048 observations. UTF-8 and a Windows UTF-8 BOM are accepted.

Use `source.kind="screen_recognition"` for software-derived evidence. Preserve an
identifiable frame/extractor reference, actual observed and ingested timestamps,
confidence and unknown fields. This new source label does not certify recognition
quality or waive any existing gate. Do not mark OCR as synthetic. A source label
and reference are caller-supplied provenance, not proof that a value is correct.

Start an observed match explicitly with its match-local ID, build/rules context,
round and phase. Unknown context remains null. Each field carries `key`, `status`,
`value` and `confidence`; unknown/ambiguous values are null. Missing fields retain
their prior evidence and are never inferred empty. Emit an explicit bans event
with semantic IDs only when those IDs and scope are actually known. Opponent IDs
are match-local; full and partial board sightings remain distinct. No observation
of a selection/lobby page establishes an active match or board.

Each cutoff rebuilds from records available by both observed and ingested time.
Late-ingested evidence is absent before ingestion, and a new match resets memory.
The response retains the exact own/opponent evidence, ban version, source counts,
available event IDs and excluded-future count. Outcomes are a separate contract
and cannot enter this observation decoder.

## Two engines and the real-rule gap

`reviewed_rules` calls the existing generic hard filter and scorer. It accepts
non-synthetic recognition evidence with an applicable `gameplay` registry; the
registry's reviewed sources, client build, rules version and ban semantics still
have to be supplied and verified. With an empty/unverified registry it returns
the observed state and concrete gaps such as `rules_unavailable`,
`rules_build_or_version_mismatch` and `ban_semantics_unverified`, with no proposal.
No real WXQ/Yixing registry is activated by this feature.

`synthetic_rolling` connects the existing rolling planner, linked formations,
match-scoped opponent memory and explicit terminal-credit objective. It requires
synthetic evidence/worlds plus the separate `--allow-test-rules` opt-in. Both
engines retain the [source-domain fence](STRATEGY_DOMAIN_BOUNDARY.md).

Request `rule_data` is the registry/world object, not a URL or dynamically loaded
script. Policy settings cannot contain `allow_test_rules`. Rolling decision points
also name the opponent and may set the bounded search budget and economy
objective. Those settings cannot silently affect the generic engine.

## Machine decision output

Each point contains:

- `ranking`: ordered candidates, scores, gaps to the best candidate and explicit
  score components. Generic components retain their field/event references and
  reviewed definitions. Rolling ranks cover completed searched paths, not every
  legal action or a proven global optimum when the search budget is exhausted.
- `first_settlement_link_changes`: per supported opponent profile, gained/lost
  pair and threshold links, isolated-value changes and opponent adjustments
  against the current legal board. This compares the first modeled settlement,
  which can require several preparation actions. A prohibited/unsupported root
  is not assigned a legal scoring baseline.
- `economy`, `rounds`, `resource_ledger`: actual modeled spending/income, final
  credits, weighted round utility, switching penalty and terminal reserve value.
  The score equals weighted utility minus switching penalty plus reserve value.
  Reserve weights are explicit assumptions, never inferred interest rules.
- `core_result`: unchanged full advice, search completeness, memory origin,
  confidence, coverage, plausible profiles and all original binding fields.
- `action_proposal`: the immediate semantic `intent`, its required evidence,
  resources, rules/state/ban versions and expiry. Rolling also includes its
  analysis move and memory/world digests. Later path steps remain analysis only.
- `blocking_gaps` and `rejected`: missing support and candidate-specific hard
  constraints. A non-settling fallback hold still reports its unresolved gaps.

`execution_allowed=false` means the strategy is not itself input authorization.
The game adapter must revalidate fresh state/rules, resolve the semantic target
against the current UI, apply the single-controller stop/ownership checks and
verify separate observations of the expected result. The proposal explicitly
requires a reviewed adapter postcondition contract; a score or human-readable
expected result is not that contract. This slice does not claim a completed
recognition-to-game-action loop.

## Runnable synthetic input session

```powershell
python -B -m strategy.session --request examples/strategy_synthetic/session/request.synthetic.json --observations examples/strategy_synthetic/session/observations.synthetic.jsonl --allow-test-rules
```

The CLI can instead consume producer output through `--observations -` and write
JSON with `--output <private-report-path>`. It refuses to overwrite either input.
The caller creates any output parent directory. Keep real records and reports
private; the supplied sample is entirely synthetic.

The sample produces `replace:B->C` at 9 points with guard-supported links, then
`end_round` at 11 when the explicit one-credit reserve is valued at 4. A fresh
breaker sighting changes the best supported result to `end_round` at 7. With a
fresh guard and C prohibited, it selects `replace:B->E` at 8. These are artificial
utilities and no real-game strength, cost or ban semantics are asserted.

The focused session checks exercise the Python and stdin CLI paths, all four
contrasts, full score accounting, links, evidence cutoff/late ingestion, match
reset and software-recognition provenance. The core, domain-boundary, rolling,
memory-origin and prohibited-formation checks also pass: 36 targeted checks, with
native DLL loading blocked. No training, fitting, capture or input is performed.
No dependencies or project-license choice are added; see
[existing notices](../THIRD_PARTY_NOTICES.md).
