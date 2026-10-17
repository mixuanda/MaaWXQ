# Validation record

This file records evidence, not intended capabilities. Private images, machine identifiers, and absolute local paths are excluded from the repository.

## Baseline before public preparation

The existing prototype's local record reported three passing offline unit tests, successful demo/replay/capture-plan commands, and JSON syntax validation of `state.schema.json`. An independent JSON Schema engine had not been used. These checks concern offline state behavior only.

The existing PrintWindow diagnostic returned:

- Invalid target: `capture_unavailable`, `window_not_found`, `image=null`.
- Confirmed launcher: `capture_unavailable`, `printwindow_failed`, `image=null`.
- Artificially exhausted cache budget: `cache_limit_reached`, `image=null`, with no new image saved.

The launcher failure must not be generalized to the real game's capture behavior.

## Read-only inspection on 2026-10-17

- Reviewed configuration, state reducer/schema, capture wrapper/worker, tests, and synthetic events.
- Confirmed capture/input flags remain false and no input/OCR/policy integration exists.
- A separate OS `CopyFromScreen` window-region capture visibly showed the **real game**, on the **custom-mode selection page**. It did not show an active custom room or match.
- Exactly one game-region screenshot was taken during this inspection. No game input, focus change, window movement, launch, installation, or login was performed.
- The image is retained privately outside the repository. It is not a PrintWindow or WGC result and does not validate any input backend.
- The inspected capture cache had two small non-image files. No capture lock was present. No Git repository existed in this directory or its parents at inspection time.

## Capability status

During public-repository preparation, the three existing unit tests were rerun successfully, and `demo`, synthetic JSONL replay and `capture-plan` completed. No game capture/input test was added. The capture-plan guidance text was updated to request a fresh real-game frame instead of assuming the game was still downloading; runtime control logic is unchanged.

| Capability | Status | Evidence scope |
|---|---|---|
| Offline state/replay | Baseline implemented | Synthetic data and existing unit tests |
| Real-game visual presence | Observed | One visible custom-mode selection frame |
| Real-game PrintWindow capture | Unknown | Launcher failure is separate evidence |
| WGC capture | Unknown | No adapter installed or tested |
| Background click | Unknown | No game input performed |
| Background drag | Unknown | No game input performed |
| Background keyboard | Unknown | No game input performed |
| Minimization/occlusion behavior | Unknown | No controlled capability experiment |
| Match/bans/opponent perception | Not implemented | No labeled in-match observations |
| Yixing policy/dynamic transition | Not implemented | Current game rules not yet verified |
| Pause/stop/input release | Not implemented | No input broker exists |

## T1 code and paused live validation — 2026-10-17

- Added `window_identity.py`, `capture_backend.py`, an explicit backend-selecting CLI and a native WGC worker candidate. The identity API uses query-limited process metadata, client/DPI geometry and stable identity/geometry tokens. These native calls have not yet received a live-target check.
- The result envelope records before/after identity, host acquisition/completion timing and clear failure reasons. `source_frame_at` remains null because neither wrapper exposes the GPU frame's timestamp.
- One additional real-game PrintWindow attempt **before the pause** returned `printwindow_failed`, `image=null`. It does not establish WGC failure. No new real-game frame was obtained.
- Verified the official MaaFw 5.7.2 wheel checksum and extracted it into a private ignored local directory; no global package, driver or system installation occurred. Native WGC/controller execution has not occurred. Version selection avoids the pseudo-minimize wrapper used by the reviewed later release.
- **14 offline unit tests passed:** 11 capture/identity tests and the 3 existing state tests. Synthetic observers/workers exercise changed identity/geometry, hidden/minimized targets, timeouts and owned-file cleanup, cache byte/count limits including late writers, lock contention, frame dimensions and non-validation semantics. They make no Win32/game calls.
- User instruction then paused all live window inspections, screenshots and input/login tests. Only code, offline tests and static documentation/license review continued. Do not resume live tests without a subsequent user instruction.
- WGC real-game capture, native metadata correctness, occlusion/minimization behavior and mouse/focus noninterference remain **unknown**. All input capabilities remain **unknown/unimplemented**. T1 is not fully accepted until an actual native frame is verified when testing is allowed again.

The public source/runtime attribution audit is documented in [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md); no native binary, real capture, raw event log or machine-specific identifier is committed.

## Independent ChildSession prototype — offline only

Eight focused tests passed for default-disabled/no-probe behavior, unsafe configuration rejection, fake WTS metadata without calling the enabling API, same-child-session checks, nonoperational behavior even with positive reported evidence, synthetic/stale/future/failed capability rejection, authenticated stop/replay behavior, and tampered/foreign/duplicate/oversized message rejection.

The offline CLI reports disabled by default. With explicitly synthetic supported facts, it still reports blocked, operational false, input permitted false and native transport unimplemented. Local protocol stop changes the generation/latch but explicitly does not claim transport delivery or remote input release. No native platform/session probe, RDP/ChildSession activation, game/window capture/input/login, system-setting change or new dependency occurred during this change. Runtime isolation and all live capability gates remain unknown.

## Reproduction and future evidence

Run from the project root:

```powershell
python -B -m unittest -v
python -X utf8 main.py demo
python -X utf8 main.py replay --events examples/events.jsonl
python -X utf8 main.py capture-plan
```

For each future live experiment, record the backend/version, current target identity in a **private** record, allowed mode, precondition, attempted action, backend result, visible postcondition, pointer/focus effect, stop/release outcome, and final `unknown/pass/fail` conclusion. Never equate API success with game acceptance. Public reports must be sanitized.
