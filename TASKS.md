# Implementation tasks

English is authoritative. This is the initial project-management backlog; check boxes represent completed gates, not effort estimates. Astra owns planning/design review, and `gpt-6.1-sol` owns implementation and focused verification.

| ID | Stage | Owner | Status | Dependencies |
|---|---|---|---|---|
| T0 | P0 | Astra planning | Done: inspection and plan | None |
| T1 | P0 | gpt-6.1-sol | Code/offline checks done; native validation paused | T0 |
| T2 | P1 | gpt-6.1-sol | Planned | T1 interface; synthetic work can start earlier |
| T3 | P1 | Astra review, gpt-6.1-sol implementation | Planned | T2, verified current Yixing rules |
| T4 | P2 preparation | gpt-6.1-sol | Planned | T1; no game input required |
| T5 | P2 | One named gpt-6.1-sol executor | Planned | T1, T4, visibly confirmed custom room |
| T6 | P3 | gpt-6.1-sol | Planned | T2, T3, T5 |
| CS1 | Isolation option | gpt-6.1-sol | Offline contract/probe/stop-codec prototype | Independent of ordinary Win32 backend |

## CS1 — Independent ChildSession isolation route

- [x] Add separate disabled configuration and backend interface; prohibit main-preview input and Win32 fallback.
- [x] Implement read-only platform-probe code and per-capability assessment; only fake APIs and synthetic facts have been tested.
- [x] Validate same-child-session placement, unknown/stale evidence and permanently blocked unimplemented native transport.
- [x] Implement/test a bounded authenticated stop-message codec with replay rejection and latched local generation revocation; do not claim IPC delivery or remote release.
- [x] Document Windows/BetterGI provenance without copying GPL implementation source.
- [ ] Obtain specific startup/system-change authorization and explicit permission to resume live testing.
- [ ] Implement/review ActiveX lifecycle, preview-only transport, authenticated named-pipe endpoint, independent watchdog/hotkeys and child-worker held-input release.
- [ ] Validate host noninterference using a harmless owned window, then separately authorized custom-room actions. No live gate has passed.

See [CHILD_SESSION_BACKEND.md](docs/CHILD_SESSION_BACKEND.md). This optional route is not activated by normal Win32 capture configuration.

## T0 — Inspect and plan

- [x] Review the existing prototype without implementing new game features.
- [x] Distinguish the real game from the launcher using one read-only image.
- [x] Record honest capability boundaries and upstream input/cursor findings.
- [x] Specify bounded implementation tasks and a single live executor.

## T1 — Window identity and bounded single-frame capture

Owned files: new `window_identity.py`, `capture_backend.py`, focused capture tests; minimal changes to `capture.py`, configuration and CLI as needed. Keep existing state behavior intact.

- [x] Define target identity with HWND/PID/start time where available, caller role assertion, DPI, client geometry, and a geometry version. Native metadata calls await live validation.
- [x] Add a thin normal-WGC backend candidate with explicit version pinning. Keep the current PrintWindow path as a diagnostic; do not import window-follow/process-suspension variants. Native execution remains unvalidated.
- [x] Return host acquisition timing, dimensions, backend, target identity, quality and error reason. Source-frame time remains unknown; missing/failed frames carry no usable image.
- [x] Preserve 64 MiB/50-file stop limits and exclusive capture locking. No continuous capture loop was introduced; offline tests cover these invariants.
- [ ] Verify one real-game frame visually and record limitations. A screenshot taken by a different API is not this backend's pass.
- [x] Keep input disabled. Check invalid identity, timeout and limit behavior with focused offline tests; no unnecessary game activity.

Live window inspection/capture/input tests were paused by the user on 2026-10-17 to allow login on another device. Code work and offline fixtures may continue. Do not resume live tests without a subsequent user instruction.

Acceptance: one bounded, diagnosable capture path plus honest failure behavior; no focus/input side effects. If WGC is unavailable, report the exact limitation and retain read-only operation. Do not silently substitute desktop capture as a WGC success.

## T2 — Match lifecycle and opponent memory

Owned files: `session_state.py`, `observation.py`, `opponent_memory.py`, schema version, reducer and state tests. Coordinate changes to `main.py` with T1.

- [ ] Add explicit start/end boundaries and source/confidence/frame references.
- [ ] Separate unknown bans from observed-empty bans; preserve confirmed current-match bans independently of freshness TTL.
- [ ] Store append-only observations with round/time and partial/full visibility.
- [ ] Derive the latest reliable state without merging unknown opponents or allowing delayed events to roll state back.
- [ ] Deduplicate by event ID; report malformed JSONL explicitly; retain complete preceding records.
- [ ] Validate fixtures against the declared schema with the format checks actually enabled, or clearly report incomplete validation.

Acceptance: synthetic replay proves match isolation, ban persistence, identity uncertainty, delayed/duplicate events and partial observations. Then gather only the small set of private custom-room observations required for a read-only report. No input to buy/sell/refresh.

## T3 — Verified Yixing rules and explainable recommendations

Owned files: versioned `rules/yixing.json`, `recommend.py`, synthetic recommendation fixtures and tests.

- [ ] Verify chess-player Yixing's current rules from the actual game UI or authoritative current material, with source/version. Never substitute same-named hero rules.
- [ ] Confirm the actual ban object and lifecycle before finalizing semantic IDs.
- [ ] Implement a small candidate set with hard ban/resource/phase filters, transition costs and evidence-based opponent information.
- [ ] Return reasons, alternative choices, unknown fields and evidence ages; abstain or hold when information is insufficient.
- [ ] Add stable transition thresholds so uncertain perception does not cause oscillation.

Acceptance: deterministic replay covers banned routes, a credible opponent change, stale observations, unknown identity and insufficient-information hold. Do not claim measured win-rate improvement.

## T4 — Input lease and independent safety supervisor

Owned files: `input_guard.py`, `input_broker.py`, `safety_supervisor.py`, adapter interface, focused fake-backend tests. No live input during this task.

- [ ] One process mutex/lease; separate it from the capture lock.
- [ ] READ_ONLY/ARMED/RUNNING/PAUSED/STOPPED/FAILED states; a registered global stop hotkey is required for ARMED. Do not use reserved F12.
- [ ] Check stop generation, lease, target identity and geometry immediately before every send.
- [ ] Stop revokes permission, clears the queue, releases only this broker's held-input ledger, and latches the stopped state.
- [ ] UI stop and console termination supplement the hotkey; OCR and long waits must not block supervision.
- [ ] User movement/click/focus change causes immediate yield, with no focus stealing, cursor snapping, BlockInput or ClipCursor.

Acceptance: fake-backend cancellation, post-keydown exception, stale-generation callback, competing owner and focus-loss scenarios release correctly and never send queued follow-up actions. A 200 ms stop-new-actions goal remains unproven until measured.

## T5 — One reversible custom-room input experiment

Single executor: designate explicitly before starting. Other agents perform no UI actions.

- [ ] Refresh window/scene evidence, establish an actual custom room, and bind a fresh identity. The inspected custom-mode selection page is not sufficient.
- [ ] Choose one visibly reversible, non-spending panel operation in the room.
- [ ] Try the normal PostMessage path once; record backend result separately from visible feedback and cursor/focus effects.
- [ ] Track click, drag and keyboard capabilities separately. An untested capability stays unknown.
- [ ] If messages are ineffective, stop. A short foreground-exclusive diagnostic requires explicit supervision and cannot pass the unattended gate. Otherwise stay read-only or evaluate a separately approved isolation route; no silent escalation.
- [ ] Verify pause/stop/release and immediate user takeover without entering ranked/matchmaking, inviting users or changing accounts.

Acceptance: a verified visible postcondition for the selected single action plus a recorded release outcome. Unattended eligibility additionally requires no main-desktop pointer, keyboard or focus interference. No blind repeated clicking or retries of economic actions.

## T6 — One bounded preparation-round loop

- [ ] Connect observed match state, Yixing recommendation, SafetyGate, InputBroker and ActionVerifier.
- [ ] Use a small action allowlist, fresh preconditions, deadlines and a finite action budget.
- [ ] Re-observe after each meaningful action; stop on ambiguity, state change, deadline or user takeover.
- [ ] Never blindly retry purchases, sales or refreshes after uncertain outcomes.
- [ ] End after one preparation round and produce a sanitized report; retain private raw evidence locally within budget.

Acceptance: one custom-room preparation round with attributable decisions, verified feedback and no main-desktop pointer/keyboard/focus interference. This does not authorize or establish full-match unattended play.

## Later research milestone — Yixing strategy evaluation

Research targets for Star-rank-and-above play are first place at least 50% and top-three at least 75%. These are unverified goals, not guarantees, implemented capabilities or authorization for ranked automation. Develop lineup matching, economy/tempo, opponent memory, ban adaptation and transitions. Evaluate a fixed game/rules version, rank band and complete eligible match population; separate tuning/training from held-out evaluation, do not cherry-pick results, and report sample size and confidence intervals. Current live-test authorization remains custom rooms only.
