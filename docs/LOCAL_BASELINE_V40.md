# V40: local gameplay reached settlement; automatic player selection remains open

The V40 private baseline ran to sixth-place settlement with local templates and
Windows OCR, zero runtime model/fact calls and zero gameplay input stops. Its
confirmed army was Niumo, Kuang Tie, Yi Xing and Yao: four units, not five. It
selected and verified Twin Tour once, closed the detail and continued playing.
This is a minimal local gameplay baseline, not end-to-end autonomous acceptance
or evidence of a strong strategy.

## All four registered attempts

| Version / run ID | Rank | Confirmed units | Gameplay stops | Result |
| --- | --- | --- | --- | --- |
| V37 / 20261019T021536012370Z | 6 | 2 | 1 | Unreadable preparation round; input stopped, settlement observed |
| V38 / 20261019T022919005437Z | Unknown | 3 | 1 | Capture byte budget refused; later file-use error prevented a rank result |
| V39 / 20261019T024335310094Z | 6 | 3 | 1 | Transient information title disappeared; input stopped, settlement observed |
| V40 / 20261019T025806738706Z | 6 | 4 | 0 | One gameplay controller continued to settlement |

Runtime model and external fact counters are zero in all four attempts. None of
the failures or unknown ranks is replaced or excluded. These local attempts
remain separate from the older three review-assisted sixth-place baselines.
No win-rate or strategy-quality claim is inferred from either group.

V40 ran from 02:58:06 to 03:13:14 UTC, including setup. Runtime sources remained
unchanged. Three unreadable preparation observations were skipped and later
recovered; they were not three consecutive failures. Eleven unknown-phase
observations waited for new frames. Zero gameplay stops does not mean every
frame was recognized. The final release was clean, and the frozen 03:13:44
worker snapshot was empty.

## Portable behavior now available

`runtime.local_facts` contains the deterministic OCR rules used by this baseline,
without private files, capture workers, model clients or input executors:

- `hand_names` reads exact names from the reviewed 20-name lexicon and bounded
  hand-label word boxes. `agree_hands` requires distinct frame hashes and nearby
  matching labels. Unknown names are skipped. These remain text/position
  candidates; they cannot prove a hero card, ownership, freshness or a deployable
  slot. Current image/template checks are still required.
- `talent_facts` orders three readable choices by a fixed lexical rule: immediate
  hero gain, other immediate gain, then listed effect words, with leftmost ties.
  It does not estimate combat value, hidden statistics or opponent counters.
  `same_talent_facts` requires all three choices; empty/truncated comparisons
  cannot pass as agreement.
- `selected_talent_text` requires the exact name, a shared effect-text fragment
  and the same ordered numerals. It only compares supplied text. Original
  frame/ROI/OCR bindings and the selected-panel postcondition remain separate;
  text overlap does not prove reward delivery or full semantic equivalence.
- `preparation_read_gate` waits without input on unreadable preconditions and
  latches off after three consecutive failures. A later readable value cannot
  automatically clear the stopped state. `parse_rank` preserves an unknown or
  ambiguous rank instead of inventing a result.

`runtime.talent_information.bind_persistent_information` addresses the observed
information-title disappearance. First, exact OCR identifies the centered
derived card using the reviewed full-title and description regions. Then the
same source frame binds its persistent internal card name and description to
fresh comparisons, both still at .97. The wider transient-title ROI is allowed
only at its exact reviewed coordinates. This does not relax the two-region,
hash, geometry, freshness or deadline requirements.

The local OCR detail-close operation also uses the existing bound release and
preparation-return verifier. These public helpers expose no game input. The
private one-run launcher and its machine-specific assets are not imported, so
this is not a portable installation of that private runner.

## Actual live coverage and remaining acceptance gaps

V40 verified Twin Tour's candidate text and selected name/effect/numerals, then
closed its detail and resumed round 6. It did **not** exercise the information
book branch. The persistent-region fix has saved-frame positive/negative
coverage only; V40's successful talent selection cannot be counted as a live
test of that branch. The earlier unreadable-title failure remains preserved.

All four setup selection observers stopped with
`selection_capture_budget_exhausted`, `selection_confirmed=false` and no actions.
They submitted zero selection inputs. This was a budget stop, not a permission
denial or uncertain selection submission. Setup nevertheless continued, and
the private runner's success code checked gameplay completion without including
that failed observer. That exit code does not certify the entire setup flow.

A post-run saved-image audit found the Yi Xing player portrait and its
`YI XING / 棋道万象` ability card in V40. This establishes the observed player,
not successful automatic switching from an arbitrary configuration. A deployed
army hero named Yi Xing is also separate evidence and cannot prove player
selection. The current private entry depends on the existing default player.
This integration does not repair or replace that private setup orchestration.

The next setup implementation must include selection outcome in overall
acceptance and verify the requested current player before allowing gameplay.
The information book still needs a bounded live run that actually reaches its
branch. Strategy remains initial purchase, verified filling and fixed text-rule
talents, without accepted economy, upgrades, merging, equipment or opponent-aware
formation policy. Sixth place and the unfilled fifth slot remain actual results.

## Integration boundary

The reviewed 75-file private source patch and frozen evidence were hash-checked;
443 registered runtime source/asset hashes matched before integration edits.
The private patch was reconstructed in memory for integrity checking and was not
applied to this public worktree. Validation covered the changed OCR rules,
numeric checks, unreadable-read latch and persistent information bindings.
No additional live game or expanded replay campaign was run for this integration.

No private images, nicknames, machine paths, learned catalogs, raw receipts or
controllers are published. Native input dependencies and the owned-window
diagnostic remain unchanged. The private run's larger capture allowances and
retention implementation are excluded: public limits remain 50 PNGs and 64 MiB,
stop-on-full with no deletion.
