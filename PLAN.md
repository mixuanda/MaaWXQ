# MaaWXQ plan

Updated: 2026-10-17. English is authoritative; optional translations must not redefine the requirements. Astra owns planning and major design reviews. `gpt-6.1-sol` owns subsequent implementation and focused testing.

## 1. Outcome and acceptance target

The user's long-term research targets are first-place rate >=50% and top-three rate >=75% with chess-player Yixing at Star rank and above. They are unverified objectives, not present capability or authorization to automate ranked play. Future evaluation must fix game/rules version, rank band and eligibility criteria; include all complete eligible games, separate training/tuning from held-out evaluation, and report sample sizes and confidence intervals. Do not infer superiority over expert players from LLM reasoning.

Build an observation-first Windows assistant for Wangzhe Wanxiangqi, starting with **chess-player Yixing**, per-match bans, opponent lineup memory, and explainable transitions between viable lineups.

**Unattended automation must not disturb the main desktop's mouse, keyboard input, or focus.** This is a release gate, not a preference. Foreground SendInput may be used only for an explicitly supervised diagnostic; it cannot satisfy the unattended goal. If background input is unsupported, stop automated actions and evaluate an isolated-session option. Never silently fall back to taking the user's pointer or focus.

The current deliverable is a small offline prototype and an executable plan. It is not a completed game bot. Preserve Python and add thin interfaces rather than replacing the whole stack before proving the capture/input assumptions.

## 2. Inspected baseline

Implementation update: the T1 identity and single-frame adapter code plus offline invariants are available. The user has paused all live game window/capture/input tests to use another device; code/offline work continues. Ordinary WGC is pinned to MaaFw 5.7.2, whose manager selects plain FramePool. Native WGC execution and target metadata remain unvalidated. See [VALIDATION.md](VALIDATION.md), [the capture contract](docs/CAPTURE_INTERFACE.md), and [third-party notices](THIRD_PARTY_NOTICES.md).

| Area | Verified or observed | Remaining uncertainty |
|---|---|---|
| Real game | One read-only OS window-region image on 2026-10-17 showed the custom-mode selection page | Not an active room or match; no Yixing, bans or opponent recognition |
| Capture | Existing explicit PrintWindow wrapper and bounded local cache | No real-game WGC/PrintWindow acceptance; the visible image used another API |
| Earlier launcher result | `printwindow_failed`, `image=null` | Does not predict the real game's behavior |
| State | Offline reducer, two manual event types, append-only history, timestamps/freshness, JSONL replay | No match lifecycle, stable opponent identity, perception or strategy |
| Controls | Capture/input flags false; no game input implementation | No release, pause, stop or action-verification implementation |
| Repository | No Git history existed in this directory or its parents at inspection | Public preparation must retain only reviewed source, documentation and synthetic fixtures |

Private evidence stores machine identifiers and the image outside Git. Public validation notes are in [VALIDATION.md](VALIDATION.md). No game input, focus change, window movement, launch, login or installation was performed during this inspection.

### Existing files

- `main.py`: initialization, manual opponent/ban events, replay, freshness and read-only title enumeration. Keep its unknown-value and append-only principles.
- `state.schema.json`: current output snapshot schema. A raw initial internal state lacks evaluated fields; do not conflate it with a completed output snapshot.
- `capture.py`: one-shot worker, 12-second timeout and exclusive capture lock. This lock is not an input lease.
- `capture_window.ps1`: HWND/PID checks, visibility/minimization checks, bounded image output, center-occlusion hint and low-color heuristic. Neither heuristic proves full, current, semantically correct game content.
- `config.json`: safe defaults, Yixing chess-player identity, 120-second engineering TTL and 64 MiB/50-file limits.
- `test_state.py` and `examples/events.jsonl`: offline tests and synthetic data; not evidence of real-game automation.

## 3. Operating boundaries

1. Input experiments are limited to custom rooms. A custom-mode selection page is not a room. Re-observe and establish the allowed room before any experiment.
2. Do not enter ranked play or matchmaking, invite people, spend money, change accounts or automate login. A room-navigation allowance does not authorize invitations or paid operations.
3. Do not read game process memory, inject into the game, bypass anti-cheat, install drivers, suspend processes, force window following, block input or confine the cursor.
4. One executor controls the game window. Other agents may research or edit separately owned files, but may not send UI input. Do not resume an older task as a competing writer.
5. Default to read-only. Pause and latched emergency stop must exist before live input. Unknown state blocks dependent actions rather than being filled with guesses.
6. Keep working files, dependencies and real-time cache on the local C-drive SSD for the initial deployment. Do not move the project/runtime to the D-drive HDD. Do not scan or move game installations. No NAS integration in the first milestone.
7. Preserve **64 MiB and 50 files**, counting all files under `cache/`; stop at either limit without deleting existing user files. Give JSONL/debug logging its own explicit bounded budget, rather than evading the capture budget by moving files elsewhere.
8. Desktop-duplication/child-session isolation is an optional, high-priority research candidate, not enabled now. No RDP configuration, new account, firewall/service change, system patch or credential/UAC change is authorized by this implementation plan. Evaluate prerequisites before seeking approval for concrete system changes.
9. No broad implementation, long-running test loops, large model training, unrelated websites, or speculative full-game datasets in the first milestone.

## 4. Comparing control approaches

Separate five questions: where pixels come from, how input is delivered, whether the physical pointer/focus changes, whether the game accepts it, and whether cancellation releases it. A single `background=true` flag cannot represent these properties.

| Approach | Useful property | Limitation | Initial decision |
|---|---|---|---|
| MAA application | Mature game workflow structure; device-side ADB input is isolated from the host pointer | MAA also has a Win32 controller; it is inaccurate to call MAA ADB-only. Arknights tasks and device support do not establish WXQ compatibility | Learn architecture; do not modify existing MAA installations or import game-specific task assets |
| ADB/device execution | If a supported game/device path exists, input need not use the main desktop pointer | Availability of a WXQ Android/emulator version, supported account flow and device capture/input is unknown | Keep as a conditional route, not an assumed solution or a reason to install an emulator now |
| MaaFramework normal WGC + normal PostMessage | Candidate thin capture/control layer for native Windows | Capture and individual input capabilities require separate tests; a successful message send is not a game postcondition | First native backend candidate; start with one read-only frame |
| MaaFramework special message variants | Upstream offers additional window/cursor handling | `WithWindowPos`/`MouseLockFollow` paths include real `SetCursorPos`, window following and process suspension/resumption in reviewed code | Exclude these variants from the initial adapter; never treat a no-grab label as a noninterference guarantee |
| BetterGI ordinary channels | Separate foreground SendInput and background PostMessage, plus held-input bookkeeping and cleanup | Not universally background; the reviewed PostMessage channel does not support relative motion, scrolling or middle/side buttons | Reuse design ideas, not the running app or upstream source files |
| BetterGI child-session desktop duplication | Potential session isolation using ChildSession and localhost RDP ActiveX | Not a VM and not a generic guarantee. RDP-specific capture/release behavior and reported cross-session interference need testing | Prioritized optional isolation study; no system changes yet |
| Foreground SendInput | Can diagnose compatibility under supervision | Uses the current desktop input stream; may disturb cursor/focus, and is subject to integrity restrictions | Supervised, short diagnostic only; never a passing unattended mode |

### What to borrow from BetterGI

- Use a held-key/button ledger, cancellation-aware cleanup, and `try/finally` around task execution.
- Make foreground and background channels explicit, with unsupported capabilities reported rather than simulated by hidden fallback.
- Its desktop-duplication Alt/focus-loss/exception release logic is scoped to the RDP child-session path; it must not be described as a universal native-game background solution.

### Desktop-duplication candidate gate

Upstream issue [#3631](https://github.com/babalae/better-genshin-impact/issues/3631#issuecomment-5575963320) contains a report concerning BetterGI 0.64.0 on Windows 11 Pro build 26200: child-session dragging using SendInput/mouse_event could be disturbed when the host pointer entered the duplicate-window rectangle. This is a user report, not proof that every current version reproduces it or that a maintainer has confirmed a fix. It prevents us from declaring isolation already solved.

Before enabling such a route, document the supported OS/build, required settings and credentials, software provenance, resource/GPU costs, target-game behavior, and rollback. Assess view-only display with RDP input disabled as a hypothesis. The reviewed main-branch commit contains WatchMode, while the reviewed latest stable release [0.66.0](https://github.com/babalae/better-genshin-impact/releases/tag/0.66.0) (2026-09-26, commit `0af68c28f6b0e714d5304625ce644736d508022e`) does not; do not advertise it as an available stable-package feature. Independently test main-desktop pointer and focus noninterference, including crossing the displayed session rectangle, before passing the unattended gate. Any required system/security configuration needs a separate concrete approval.

Do not auto-elevate to bypass SendInput/UIPI limitations. Do not use `BlockInput`, `ClipCursor`, process suspension, focus-stealing loops, or cursor restoration as substitutes for isolation. A low-level mouse hook, if considered for observing takeover, must remain short and cannot be the sole safety mechanism.

For a future child-session route, the game and executor must run in the same child session; the main session should have read-only preview and an IPC stop channel. First inspect existing components, GPU/RAM and sessions without changing settings. Validate clicks and drags against a harmless self-owned test window while the main desktop remains usable, including pointer crossings over the preview rectangle, before trying a game custom room. Any interference fails the isolation gate. BetterGI's game-mouse mode can capture the host pointer and is unsuitable for this unattended requirement. Do not assume RDPWrap, drivers, a second Windows installation or a fixed RAM/VRAM overhead is needed. See [Microsoft child sessions](https://learn.microsoft.com/en-us/windows/win32/termserv/child-sessions) and the [pinned BetterGI session documentation](https://github.com/huiyadanli/bettergi-docs/blob/f39308e9f33afcdb289efe8780081fe715787679/src/feats/command/session.md).

## 5. Minimal architecture

```text
WindowIdentity -> CaptureBackend -> Perception -> MatchState -> YixingPolicy
                                                           |
                                                           v
                                                      action intent
                                                           |
                                                           v
SafetySupervisor -> SafetyGate -> sole InputBroker -> ActionVerifier
       |                               |
       +------ revoke lease/stop ------+
```

- **WindowIdentity:** HWND, owning PID, process start time if accessible, role evidence, DPI, client geometry and geometry version. A missing executable path stays unknown. Refresh identity at session start; invalidate coordinates when identity/geometry changes.
- **CaptureBackend:** one bounded frame, backend/version, timestamp, identity, dimensions, quality and reason. WGC is the first candidate; PrintWindow remains diagnostic. No implicit focus/restore/move operations.
- **Perception:** read-only phase, round, bans, own board/resources and visible opponent observations. Unknown/low-confidence values are first-class results.
- **MatchState:** match boundary, append-only evidence, opponent `last_seen`, confidence, visibility scope and derived latest reliable state.
- **YixingPolicy:** versioned rules and a small set of candidate routes; returns recommendations or intent, never raw Win32 calls.
- **SafetyGate:** validates room/mode, state freshness, action allowlist, budgets, lease and stop generation.
- **InputBroker:** the only component allowed to send input; maintains a process mutex, lease, capability-specific channels and held-input ledger.
- **ActionVerifier:** checks a visible postcondition after each meaningful action and distinguishes backend result from game outcome.
- **SafetySupervisor:** independent stop/takeover path that is not blocked by OCR, strategy, capture timeouts or long waits.

Keep interfaces small and preserve the existing CLI. A full GUI, service, agent platform or database is unnecessary for this milestone. Evaluate dependency/release version and license before adding a backend; the reviewed development commit is not automatically the installed SDK version.

## 6. Data contracts

### Capture and capability evidence

Use per-capability `unknown/pass/fail` records for foreground/background capture, click, drag and keyboard, with backend version and tested conditions. An untested operation remains unknown. Do not infer background drag from background click, or minimized capture from unobscured capture.

Frames should carry `frame_id`, `observed_at`, `identity`, `geometry_version`, `backend`, `dimensions`, `quality`, `image_or_null` and `reason`. A stationary valid UI may produce identical pixels; animation alone does not prove semantic validity. Timestamp/source guarantees and observed UI changes must support the conclusion.

Coordinates are client-relative with explicit DPI/border transforms. Never reuse a screenshot's raw desktop coordinates after a resize, window replacement, phase change or DPI change. The current inspection image includes window borders and is not an action map.

### Match lifecycle and bans

Events should include a schema version, event ID, match ID, observation/ingestion timestamps, source, frame reference and confidence, plus a typed payload. Add explicit `match_started` and `match_ended` boundaries. A manually established local match ID is acceptable if its source is recorded; it is not a fabricated game ID.

Confirm the actual game's ban objects, screen location and lifetime before defining final semantic IDs. The existing `lineups` field contains manual labels, not a validated rule taxonomy. Distinguish unknown bans, observed-empty bans and confirmed banned items. Confirmed current-match bans are hard constraints and must not expire into permission after the 120-second freshness TTL. A new or uncertain match boundary invalidates dependent recommendations and queued actions.

### Opponent memory

- Preserve every observation, with opponent identity evidence, round/time, confidence and partial/full coverage.
- Distinguish chess-player and hero entities. Missing IDs stay unknown; do not resolve them solely from names.
- Do not merge unknown opponents or identical display names automatically. Prefer a reliable match-local slot/ID supported by visible evidence.
- Record units, stars, equipment and positions only when actually visible. A missing unit in a partial view does not mean it was sold.
- Derive the latest reliable state by observation time/round and completeness, rather than the last JSONL line. Retain late observations without regressing the live view; deduplicate known event IDs.
- Report malformed JSONL explicitly and preserve preceding complete records. Do not silently turn a truncated event into a valid observation.
- Keep stale observations as history; reduce their decision weight and request another look. Time and round age should be distinct from information being absent.

### Yixing and dynamic lineup transitions

First verify the current **chess-player Yixing** ability, triggers and constraints using current authoritative material or the actual game encyclopedia. Do not substitute same-named hero rules. Record source and game/rules version; these facts were not established by the inspection frame.

Begin with a small, explainable candidate set. Each route specifies required pieces/traits, substitutes, resource requirements, transition cost, ban dependencies and provenance. Filter hard bans, phase restrictions and resource constraints before scoring Yixing fit, owned investment, observed competition/threat, economy and execution time. Weights are engineering assumptions until evaluated, not measured win-rate claims.

Return the current route, alternatives, hard-rejection reasons, evidence ages, unknown fields, transition cost and a reversible next step. Hold or abstain if information is insufficient. Reevaluate on meaningful confirmed state changes; use transition thresholds/stability windows to avoid oscillation from uncertain recognition. Only information actually observed in accessible game UI enters opponent reasoning.

## 7. Input lease and emergency behavior

1. Use a process mutex and exclusive lease containing owner/session identity. A capture lock is insufficient. Only the broker can send input.
2. States: `READ_ONLY -> ARMED -> RUNNING -> PAUSED/STOPPED/FAILED`. Default READ_ONLY. A successfully registered independent global emergency hotkey and validated permitted room are prerequisites for ARMED. Do not use Windows-reserved F12; check the chosen hotkey for conflicts.
3. Immediately before every send, recheck stop generation, active lease, target identity, geometry version, allowed phase, freshness and action budget. A late callback from an older generation cannot send input.
4. Emergency stop order: revoke permission, invalidate queued work, release only input in this broker's held-down ledger, then latch stopped. Never send a blanket all-keys-up into an unrelated application.
5. Record and pair each key/button down with up, including exception, cancellation, focus-loss, disconnect and target-destruction paths. Release failures must be visible and terminate further execution.
6. User movement, click or task switching causes immediate yield. Do not steal focus back, snap the pointer back or suppress physical input. If reliable takeover detection cannot be established, do not pass continuous execution.
7. UI stop and console termination supplement the global hotkey. OCR and capture waits cannot block supervision. Use short cancellable waits and bounded input durations.
8. Pause discards pending intent. Resume requires new identity/phase/geometry evidence; it must not continue an old action sequence blindly.
9. Do not stop or reconfigure other running automation software. If another input owner conflicts, pause MaaWXQ and report the conflict.
10. Stopping new sends within 200 ms is an initial **measurement target**, not a verified property. Record actual stop latency and held-input release separately.

## 8. Phases and gates

| Phase | Deliverable | Acceptance gate | Failure behavior |
|---|---|---|---|
| P0: real-game frames | Inspection evidence, this plan, then thin identity/single-frame capture adapter | Real game visually confirmed; chosen backend itself produces a current valid frame; budgets and clear error states preserved; no focus/input effects | Remain read-only and report unavailable capabilities |
| P1: observe and advise | Read-only real-match observations, bans, opponent memory, verified Yixing rules, recommendations | Synthetic replay proves invariants; a small set of private observations supports actual UI recognition; recommendations cite current/unknown evidence | Keep manual annotation or abstain; no policy execution |
| P2: one custom-room input | Offline-tested safeguards followed by one reversible, non-spending panel operation in a confirmed room | Visible pre/postcondition, per-capability result, released input and user takeover; no pointer/focus disturbance for unattended eligibility | Stop ineffective message path; supervised diagnostic or separately approved isolation study only |
| P3: one preparation round | Bounded allowlisted observe/decide/act/verify loop | Every meaningful action has feedback; finite time/action budgets; stop/lease checks hold; main desktop remains undisturbed | Return to read-only recommendations; do not claim whole-match automation |

Safety preparation can run before P1 is complete, and offline data work can proceed while a capture backend is being diagnosed. Real input cannot bypass P2 safeguards; strategy execution cannot bypass P1 evidence. An autonomous full-match loop is outside the initial acceptance scope.

## 9. Focused verification

- **Capture:** valid game frame; invalid/replaced identity; minimized/unavailable/timeout states; single-frame and cumulative limit checks; exclusive writer. No silent eviction, focus change or capture-loop expansion.
- **State:** new-match reset; unknown vs observed-empty bans; TTL cannot lift bans; unknown opponent isolation; delayed/duplicate events; partial view is not deletion; corrupt final JSONL row reported.
- **Policy:** deterministic replay; banned route excluded; credible opponent change can alter advice; stale/uncertain evidence can cause hold; transition cost prevents oscillation.
- **Safety:** fake-backend tests for cancellation before send, exception after down, stale generation, competing lease and focus-loss; actual hotkey registration and release before live input.
- **Live action:** record attempt, backend return, observed postcondition and final conclusion separately. No blind retries of purchases, sales or shop refreshes after uncertain outcomes. Use one harmless reversible panel operation first.
- **Isolation:** explicit host pointer/focus noninterference, including child-session display boundary interactions if that route is chosen. Background capture alone is insufficient.

Tests must target changed invariants. Do not write tests that merely repeat the implementation, rerun broad suites without cause, or leave the game running as a substitute for evidence.

## 10. Repository and task management

Publish a minimal **public** repository containing reviewed original code, English documentation and necessary synthetic fixtures only. Inspect existing Git state before initialization; never overwrite unrelated history. Verify the authenticated owner and same-name repository before creation. Review both staged paths and actual content before the first commit/push.

Exclude captures/cache, real replay data, logs, account/game identifiers, absolute machine paths, credentials, `.env` files and downloaded third-party assets. Preserve private baseline/evidence outside Git. Use a GitHub no-reply identity for project commits rather than publishing a private email address. Do not choose a license without the owner's decision.

Use [TASKS.md](TASKS.md) as the initial backlog and [VALIDATION.md](VALIDATION.md) for evidence. Keep each task independently reviewable, with owned files, dependencies and stop conditions. Do not create redundant management documents or an external project board solely for appearance.

The next implementation task is **T1**, assigned to `gpt-6.1-sol`: build a bounded single-frame identity/capture interface with input still disabled. Before editing, compare the working tree against the documented baseline. Later tasks add state/memory and Yixing advice, then input protection and one supervised custom-room experiment.

Open questions: exact game/version and installation path; WGC availability; background click/drag/keyboard acceptance; minimized/occluded behavior; Yixing's current rules; actual ban semantics; stable opponent identification; suitability and prerequisites of an isolated child session. None are answered by the one inspection image.

## 11. Pinned research references

These are upstream research baselines, not dependencies already installed in MaaWXQ. No upstream source was copied into this repository.

- [MAA, commit 366f261c85890237ab0e8b3a1bd040f2e3949f8d](https://github.com/MaaAssistantArknights/MaaAssistantArknights/tree/366f261c85890237ab0e8b3a1bd040f2e3949f8d): both device/ADB architecture and Win32Controller are relevant; do not describe it as ADB-only.
- [MaaFramework, commit 06f59428e0a79566765b8f25cc6ef2296fcf4e2e](https://github.com/MaaXYZ/MaaFramework/tree/06f59428e0a79566765b8f25cc6ef2296fcf4e2e): review normal FramePoolWGC, controller stopping, and the distinction between ordinary message input and special `MessageInput.cpp` window/cursor/process handling. The source review identified process-suspension/cursor paths around lines 596–619, 672–695 and 1473–1486; exclude them from the initial adapter.
- [BetterGI, commit b3f90e70494320639eeccc8c559612d02d2d9ef0](https://github.com/babalae/better-genshin-impact/tree/b3f90e70494320639eeccc8c559612d02d2d9ef0): `Core/Input/Backends/Win32/PostMessageChannel.cs` documents unsupported operations; `Core/Input/InputChannelBase.cs` lines 119–170 provide ledger/cleanup context; `GameTask/TaskRunner.cs` lines 83–112 provide finalization context; `Service/Instance/MessageHandlers/RelativeMouseMessageHandler.cs` lines 378–466 concern the RDP-specific release path.
- [BetterGI issue #3631](https://github.com/babalae/better-genshin-impact/issues/3631#issuecomment-5575963320): treat the reported child-session interference as a condition to investigate, not a universal finding or a confirmed fix.
- [Microsoft SendInput](https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-sendinput): insertion into the input stream is not a semantic game postcondition; integrity/UIPI restrictions must not trigger automatic elevation.

Recheck implementation and observed behavior when changing dependency versions. No source-level claim is a replacement for target-game postcondition tests or main-desktop noninterference evidence.
