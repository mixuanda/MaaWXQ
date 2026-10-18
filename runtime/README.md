# MaaWXQ custom setup software loop

`python -B -m runtime.custom_setup --output <new-private-run-dir> --profile <local-game-profile.json> --reference <reviewed-local-reference.png> --reference-sha256 <sha256> --enable-custom-setup --wait-for-game 120`

For a game that runs at high integrity, the human operator must explicitly authorize and launch MaaWXQ at that level, and add `--allow-elevated-runtime`. The program never elevates itself, modifies UAC/security settings, enables services, or bypasses API failures. Its default rejects an elevated controller unless explicitly enabled. It rejects a target with higher integrity than the controller before any input call.

The private game profile specifies `title`, `class_name` and full `executable_path`. A run discovers exactly one matching window, obtains its PID and process start time, and binds that identity and geometry for the action. The profile and reference image must remain local and must not be committed. A new process after restarting the same configured game is discovered normally; an in-run identity change aborts.

## Software-owned stages

1. Capture the foreground game client through normal screen capture, validating the target before and after. Five occlusion samples reject obvious overlays, but do not prove all pixels unobscured.
2. Recognize the reviewed custom-selection screen by three white-glyph masks: selected custom tab, custom mode tile label, and confirmation label. Current support is the observed 1450x869 client geometry only. Scores are uncalibrated Dice similarities; 0.91 is a conservative prototype threshold, not a probabilistic confidence claim.
3. `runtime.scene.decide` proposes the recognized confirmation center. Unknown scenes return stop. It does not receive click coordinates from the Remote launcher.
4. Recapture and recognize immediately before action; preserve the actual observation time. `GameClickBroker` permits only the explicitly implemented custom-setup transition.
5. Submit one normal mouse click through the inherited tag32/guard/ledger implementation. The independent game adapter validates exact process/image/geometry; the original diagnostic remains byte-identical and self-owned only. A bounded 60ms DOWN/UP interval spans frames and is cancellable. After its own DOWN, the input timestamp necessarily changes; hooks remain active and only the owned UP is allowed. There is no hold/drag interface.
6. Capture and write the result. Missing old-page templates yields an unknown next scene, not proof of leaving the page. The current recognizer cannot positively verify a room transition. Unknown occupancy is never reported as no humans, and no match is started automatically by this version.

The parent of the new private run directory is the shared capture-budget root. Keep runs in that same scoped parent: all PNGs below it count toward 50 files / 64 MiB. Enabled runs reserve space for three supported frames before the first capture; every capture rechecks capacity. A six-MiB per-frame bound covers the supported geometry. The keypad continuation reserves eight frames before starting. Full budgets stop the run without deletion or retry. Cleanup must include the broker and port error lists, an owned release and no held button before result capture can continue.

Remote tools only launch this program and read artifacts. They do not choose or submit the click. The receipt records code hashes, local token and target identity, frame provenance, recognition scores, decisions, native submission counts, owned release and postcondition result.

## Room-code keypad continuation

`python -B -m runtime.room_code --output <new-private-run-dir> --profile <local-game-profile.json> --reference <reviewed-local-keypad-frame.png> --reference-sha256 <sha256> --enable-custom-setup --allow-elevated-runtime`

This continuation recognizes the room-code title, custom tab, and all ten numeric keypad glyphs. It starts only from four empty slots, chooses a random four-digit code, and clicks a recognized digit button once per fresh observation. After every click, including the fourth, it captures and requires the exact occupied-slot count before reporting progress. This is progress detection, not OCR of the entered value. An unknown page after the fourth click remains unverified and stops without retry; it is not treated as a recognized room. Unknown room occupancy remains unknown and no match starts. Local input hooks remain active during the postcondition capture; a foreign-input flag remains visible even after the one-click completion latch. Input-timestamp checks bridge the intervals between brokers. Any unexpected input or entry progress stops the sequence without repeating the click.

On the observed machine the normal `ShowWindowAsync(SW_RESTORE)` request can activate the game. The program records restore and foreground BOOL results, raw last-error values, and actual foreground HWNDs before/after. `SetForegroundWindow` has no documented last-error contract, so its raw zero is not called success. No AttachThreadInput, synthetic Alt-key workaround, lock-timeout change or OS setting change is used.

## Integration contract

### Normal activation through the observed taskbar

`python -B -m runtime.activate_taskbar --output <new-private-run-dir> --profile <local-game-profile.json> --enable-taskbar-activation --allow-elevated-runtime`

This explicit, one-shot transaction discovers the real Explorer taskbar button for the configured game. It requires the observed single-window title, exact AppID/path, Explorer process, taskbar class, UI Automation runtime identity, enabled/onscreen state, bounded button rectangle and native hit-test to the taskbar. It selects the button nearest the current game, captures its actual pixels, and repeats discovery under the existing tag32 hooks/mutex/emergency stop before sending one ordinary short mouse click. Some Windows taskbar providers expose a button rectangle but no clickable point or descendant hit match; in that case the observed rectangle center is used only with the exact native taskbar hit and renewed identity/bounds checks. This limitation is explicit in the receipt.

The target remains the actual Explorer taskbar window; no game HWND, ownership or foreground observation is fabricated. A foreground change before submission, a user/foreign input, timeout, changed button or held input stops the attempt. After DOWN the only remaining event is the owned UP; normal focus movement caused by the taskbar activation is expected. Cleanup and actual game foreground are verified before any later game transaction. It sends no keyboard input, changes no system focus lock or security setting, and has no automatic retry. The original self-owned diagnostic remains unchanged.

Taskbar images share the private run-parent capture budget. Each discovery supports
at most two matching taskbar buttons; enabled activation reserves four bounded
images before discovery. Each button is at most 512x256, with a 600-KiB reservation.
Full 50-image / 64-MiB budgets stop before discovery; no evidence is deleted.



New files owned by the control worker: `backends/game_click.py`, `runtime/` and `test_software_loop.py`. No strategy files or original diagnostic files are changed. Input code is independent of the advisory strategy package.

`maawxq-ui-state/1` is a UI observation, not an invented battle Observation. Its `room_occupancy`, `other_humans_verified_absent`, `room_number` and `game_rules` remain unknown/false until supported by actual recognition. The callable [strategy API](../docs/STRATEGY_SESSION_API.md) accepts the `screen_recognition` source kind; a reviewed battle-observation mapping is still required. Do not relabel this menu state as synthetic or a manual battle observation. There is no evidence here of an executed strategy match.

For incremental control integration use `strategy.advisor.Advisor`: feed `observe(record, now=...)`, request `decide(decision_at=...)`, then call `validate(proposal_id, now=...)` against pending fresh evidence before dispatch. The same interface is available as the persistent `python -B -m strategy.advisor` JSONL service. [Command and response contracts](../schemas/strategy-advisor.schema.json) retain candidate/state/rules/ban/memory/expiry bindings; they do not turn this menu recognizer into a battle recognizer or verify game rules. An unverified real registry reports gaps and no action intent.

For one recognized battle frame, [`strategy.recognition.ingest_frame`](../docs/STRATEGY_RECOGNITION_ADAPTER.md)
builds and atomically ingests source-bound own/ban/opponent events.
`input_requirements` lists the supplied registry's exact fields, costs and available
controller operations. Menu/lobby or host-only frame evidence revokes a stale
intent and retains the real recognition/rule gaps instead of fabricating a match.

Do not auto-repeat an unsuccessful or uncertain click. Inspect the saved state/frames and fix the particular problem before a new run. Keep Ctrl+Alt+F9 available. Any user/foreign input or focus loss after arming revokes the action; cleanup only releases the module's own mouse DOWN.

The existing `capture_backend.capture_one` WGC path remains separate from foreground
input. Its pinned 5.7.2 worker now calls `MaaGlobalSetOption`, preserving strict JSON
stdout instead of emitting deprecated-export warnings. No output-parser relaxation
or mouse/keyboard mode is added. WGC acquisition time is not a source-frame timestamp;
background observation alone does not establish freshness for a game action or
remove the input foreground guard.

## V5 control checkpoint and character-selection block

The later prototype actually filled five bot slots, verified Xingyao room settings,
and started one empty custom test. The first observed battle used Bai Ge, not the
requested Yi Xing. That attempt was exited and must not be reported as a Yi Xing
match or strategy success. No strategy-generated game action has executed.

`begin_custom_selection` is now rejected in both `runtime.lobby.decide` and
`GameClickBroker.validate_context`. The real selection marker, confirmation
transition, and confirmation result are not implemented. This is an unconditional
block until those actual observations support a reviewed implementation. Passing
`requested_player_verified=True`, owning Yi Xing, opening his collection details,
or seeing the skin label “已穿戴” does not unlock start. Room setup and encyclopedia
inspection remain separate from strategy execution.

`runtime.fill_bots` supports bounded bot filling with an independently checked
increment of exactly one occupied bot slot after each addition. Unknown occupants,
unexpected non-target changes, user input, or a failed postcondition stop it.
The reviewed fixed layout is 1450 x 869; other geometries remain unsupported.

Current-client Yi Xing encyclopedia text was captured separately from historical
rule models. Its passive is 棋道万象; 谋而后定 displays rounds 4/8/12 and reward
驭势; the reward card displays cost 6. Private evidence includes exact original
text, source screenshot hashes, capture times, UI context, and null build/version
fields. Displayed text is not an executable rule registry or proof of resolution.

## Minimal observation and strategy handoff

`runtime.observe_minimal_state` accepts an existing real capture record, its UI
recognition record, and a new output directory. It checks the original PNG hash,
creates bounded nearest-neighbor OCR crops, calls installed Windows Chinese OCR,
and writes `maawxq-minimal-state/1`. It has no input or activation API. The sample
actual replay recovered round 4, timer 45, and resource 28; shop OCR failed and is
unknown. The six-region replay took about 16.5 seconds, so this implementation is
not yet a validated realtime decision loop.

The minimal record contains source identity/hash/time; scene; requested and
confirmed character; round/timer/phase; energy; four partially covered shop slots;
and board/hand coverage. Every unresolved value is null. Uncalibrated OCR uses
`status=candidate`, `candidate=<readout>`, `value=null`, and no fabricated numeric
confidence. It never proves empty zones, maps a shop card to the selected player,
or claims a build/rule version from unrelated information. `input_allowed` and
`fresh_for_input` are always false in this read-only milestone.

`runtime.observe_strategy` now runs fresh capture, independent UI recognition,
minimal OCR, and a persistent Advisor instance. OCR candidates are retained as
diagnostic evidence and are not promoted to known strategy fields. Original
capture time is preserved across OCR; the Advisor still enforces its freshness
and rule gates. Actual replay returned abstain. There is no game action adapter
for advisory proposals. `validate_for_dispatch` calls the persistent Advisor's
validation but never enables input by itself.

For integration, retain the integrator's newer native hold/stop fix, combined
cleanup reporting, and capture budgets (50 PNG / 64 MiB). This delta does not
replace `backends/win32_single_click.py` or the self-owned diagnostic. Apply only
the semantic additions to `custom_setup.capture` when that file has newer budget
changes. Private game profiles, images, receipts, and rule-evidence files must
remain outside published source patches.


For the integrated live/replay API, concrete first-purchase field checklist and deterministic inspection example, see [V5 minimal strategy API](../docs/V5_MINIMAL_STRATEGY_API.md).

## Scoped purchase continuation

The [purchase handler API](../docs/PURCHASE_HANDLER_API.md) now implements one
visible legal shop purchase, explicit optional scoring terms, fresh preaction
revalidation and a dual currency-delta/new-hero postcondition. It does not wait
for a global combat model. The guarded adapter defaults off; implementation
tests sent no game input. Necessary numeric OCR now uses one in-memory batch
process, with saved-frame measurements of 1.378 seconds for two dynamic regions
and 1.818 seconds for six regions. The original five-second TTL is unchanged.

The later locally integrated V6 supplies the actual Yi Xing choice/ring/confirm
route. Starting selection requires a fresh bounded same-game observer; the
choice/confirm clicks require the verified recent five-bot custom-origin receipt.
The packaged watcher is import-safe and shares the parent screenshot budget,
including both transition transactions. The control worker independently
confirmed actual Yi Xing selection and entry into battle, while the packaged
watcher still reports its final confirmation postcondition as pending until
independently recognized. This integration did not run another selection or
purchase and does not reinterpret the current talent overlay as a buy phase.

## V8 automatic purchase postcondition

The later control-worker run automatically verified one Sun Bin purchase:
energy 6 to 3 plus a spatially matched new hand card, using the unchanged
PurchaseHandler. [The portable hand matcher and binding API](../docs/hand-appearance-evidence.md)
preserve the actual preaction/after source hashes, predicates and five-second
freshness gate. This specialized two-to-three-card layout is not a generic
inventory reader. A subsequent hand-card click opened details; deployment
remains unverified. Private controllers, images, profiles and retention/deletion
code are excluded. Integration itself sent no game input.

## V9 first-unit drag

[V9](../docs/DEPLOYMENT_V9.md) adds a distinct typed, default-off 300 ms drag
for an automatically purchased hero in the reviewed three-card hand and empty
0/5 board (the V9 capacity-three transcription is corrected by V11). The observed
Li Yuanfang placement was confirmed from original images (hand 3 to 2,
board 0/5 to 1/5), while that historical runtime deployment postcondition
remains false. The portable round-label parser correction was source-only at V9;
continuous strategy, draft/talent states and automatic board verification are
not complete. Native guards, purchase handling and evidence retention are
unchanged; private controllers and patches are not published.

## V11 automatic deployment verification

[V11 evidence and portable API](../docs/DEPLOYMENT_V11.md) records the later live
Niumo purchase and `deployment_verified` result: energy 6 to 3, hand 3 to 2,
population 0/5 to 1/5, owned-unit identity and exact intent/frame bindings.
`runtime.deployment_postcondition` provides a pure binder/verifier, defaulting
to saved replay; replay never becomes a new live game result. The byte-identical
executed bitmap matcher is included without private templates or controllers.
The drag adapter now requires the corrected capacity five and preserves every
other native guard, its default-off state and the one-attempt limit.

The finite control run recognized rounds 3, 4 and 5 and submitted ready clicks,
whose postconditions remain false. Combat and draft-preview observations do not
establish talent choice, continuous purchasing, dynamic formations, a full match
policy or win-rate results. Integration used only offline checks and did not
operate the game. Capture limits and no-deletion policy remain unchanged.

## V12 ready and talent postconditions

[V12 evidence and API](../docs/SUSTAINED_V12.md) records the later live Li Yuanfang
purchase/deployment, three `ready_verified` results in rounds 3/4/5, and two
`talent_selection_verified` results across the debug and fresh custom games.
The V11 ready-pending statements above describe that earlier checkpoint.
`runtime.phase_perception` and `runtime.transition_verification` provide pure
phase, retained-intent, ready and selected-talent checks. Source-bound OCR,
current timestamps, exact window/round and clean owned release are required.
Saved replay defaults cannot be reported as a new live game result. No native
adapter or private controller is added by these modules.

Talent details verify the chosen panel, not reward delivery or future effects.
The old sixth-place debug match is excluded from win-rate samples; the fresh
match remains unsettled in the frozen handoff. Eligible samples are zero.
Additional-unit placement, army development, general talents, opponent-aware
formations and full match strategy remain unfinished. Integration performed
only offline checks, preserving native guards and screenshot retention limits.
