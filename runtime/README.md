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

New files owned by the control worker: `backends/game_click.py`, `runtime/` and `test_software_loop.py`. No strategy files or original diagnostic files are changed. Input code is independent of the advisory strategy package.

`maawxq-ui-state/1` is a UI observation, not an invented battle Observation. Its `room_occupancy`, `other_humans_verified_absent`, `room_number` and `game_rules` remain unknown/false until supported by actual recognition. The callable [strategy API](../docs/STRATEGY_SESSION_API.md) accepts the `screen_recognition` source kind; a reviewed battle-observation mapping is still required. Do not relabel this menu state as synthetic or a manual battle observation. There is no evidence here of an executed strategy match.

For incremental control integration use `strategy.advisor.Advisor`: feed `observe(record, now=...)`, request `decide(decision_at=...)`, then call `validate(proposal_id, now=...)` against pending fresh evidence before dispatch. The same interface is available as the persistent `python -B -m strategy.advisor` JSONL service. [Command and response contracts](../schemas/strategy-advisor.schema.json) retain candidate/state/rules/ban/memory/expiry bindings; they do not turn this menu recognizer into a battle recognizer or verify game rules. An unverified real registry reports gaps and no action intent.

Do not auto-repeat an unsuccessful or uncertain click. Inspect the saved state/frames and fix the particular problem before a new run. Keep Ctrl+Alt+F9 available. Any user/foreign input or focus loss after arming revokes the action; cleanup only releases the module's own mouse DOWN.

The existing `capture_backend.capture_one` WGC path remains separate from foreground
input. Its pinned 5.7.2 worker now calls `MaaGlobalSetOption`, preserving strict JSON
stdout instead of emitting deprecated-export warnings. No output-parser relaxation
or mouse/keyboard mode is added. WGC acquisition time is not a source-frame timestamp;
background observation alone does not establish freshness for a game action or
remove the input foreground guard.
