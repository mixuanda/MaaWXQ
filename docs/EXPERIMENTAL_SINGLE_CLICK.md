# Experimental single-click diagnostic: unverified and default off

This saves a reviewed diagnostic candidate, not a working game-input backend.
[`SingleClickBroker`](../backends/win32_single_click.py) is an opt-in, one-attempt
foreground mouse diagnostic for a window owned by the calling process.
Construction, import and the default `enabled=False` broker open no native port.
The existing [`config.json`](../config.json) keeps `input_enabled=false` and
`capture_enabled=false`. No main command, ChildSession adapter or strategy policy
imports or enables this diagnostic. For the single user-operated self-window
entry, use the [owned-window diagnostic instructions](owned-window-diagnostic.md).
Its native stages remain unverified and never enable game input.

`custom_room` is rejected even when a caller asserts that no other humans are
present and the operation is reversible. The native port additionally checks the
actual window PID against its own process before submission. Merely calling a
game window a self-test cannot pass that native check.

## Review changes to the handed-off candidate

The original candidate had 13 fake-port tests. Integration corrected these
specific boundaries in the two new files without changing the existing backends:

| Finding | Correction and offline evidence |
| --- | --- |
| A slow observation could cross the deadline after the first time check | Recheck age, deadline, stop, input marker and guard health after observation; a synthetic slow observer prevents submission |
| Client origin relied only on a caller's geometry-version label | Bind actual observed screen origin as well as width/height; a changed origin with the same label is rejected |
| A Windows mutex can be acquired recursively by the same owning thread | Add a process-local lease as well as the named mutex; a second local owner is rejected |
| Closing on another thread could silently fail mutex release | Require broker lifecycle and native open/click/close on the owner thread; wrong-thread close revokes and leaves owner cleanup available |
| Cleanup exceptions or supervisor startup failure could skip stop or subsequent teardown | Latch stop before release, clean up after failed thread startup, attempt both unhooks independently, expose cleanup errors and retain ownership/callback references when teardown is uncertain |
| Submission exceptions could be confused with proof of zero input | Record `submission_outcome` and the native event count separately; an uncertain call retains its possibly-owned button ledger until release |
| A failed arming attempt could be retried on the same broker | Latch the arm attempt; creating a new broker still cannot bypass default/context/native gates |

The final native permission callback runs after foreground, point/root-window,
PID and already-held-input checks. The broker rechecks complete observed
HWND/PID/process-start/class/geometry identity against its original binding.
Its observer must supply fresh, trustworthy metadata; a timestamp or a caller
assertion does not establish a semantic game state.

## What the diagnostic would do

An enabled permitted self-test requires successful takeover hooks and emergency
Ctrl+Alt+F9 registration, followed by fresh evidence and foreground checks. One
native call then submits a tagged mouse move, left-down and left-up batch. There
is no action retry, drag, keyboard typing, focus activation, cursor restoration,
purchase or match-start operation. Partial or exceptional submission retains a
possibly-owned left button for visible cleanup; it never releases arbitrary keys.

This uses the **shared foreground cursor**. It supplies no separate desktop,
background game control or cursor isolation. The mutex only coordinates
cooperating brokers. Takeover hooks observe foreign mouse/keyboard activity and
pass it onward; they do not suppress user input or record key content.

Callers must create, arm, click and close on one thread and use structured cleanup
even if arming fails. `stop()` may be called from another thread; it only revokes.
The independent supervisor can request owned-button cleanup after revocation.
`release_confirmed`, broker/port `cleanup_errors` and `submission_outcome` must be
examined together. `sent=False` after an exception is not proof of zero input.
An incomplete cleanup keeps exclusivity rather than authorizing another broker.

The final check and `SendInput` are not one atomic OS operation. Focus or input
can change in the remaining gap, and an already in-flight native call cannot be
interrupted. Cleanup can wait for its ledger lock; bounded release/stop latency
has not been established. An observer can also block. Hook-thread liveness does
not prove a hook is still installed, and the last-input marker is an additional
session-scoped check rather than reliable attribution of physical input. It can
also see the diagnostic's own injected events and conservatively revoke.
These limits preclude calling this candidate operational or takeover-safe.

## Actual runtime evidence and blocker

The independent native task reported the following attempt on a harmless
self-owned test window. This integration did not repeat it or operate a desktop.

| Evidence | Result |
| --- | --- |
| Target selection, foreground and complete identity | Passed for that self-test attempt |
| Mouse and keyboard takeover-hook setup | Returned handles |
| Emergency `RegisterHotKey` | Raw return 0, immediately captured Win32 error 5 (access denied) |
| Native `SendInput` / native click attempts / game input | **0 / 0 / 0** |
| Reported owned release | True because nothing was held; no reported cleanup errors |
| Native click, visual postcondition, physical takeover and stop latency | **Not validated** |

The later read-only diagnosis reports an AppContainer token, no elevation and no
UIAccess; it does not establish which precise policy caused the denial. The
original attempt preceded these integration corrections and is not validation of
the revised code. A separately requested user-run registration-only probe in an
ordinary non-administrator PowerShell remains pending. This repository change
does not add or run that probe, modify permissions or try a different input path.

Do not remove the emergency gate, substitute another hotkey to evade the denial,
elevate, change security settings or retry under the same denied conditions.
Normal-user hotkey registration alone would still not validate clicking or
physical takeover. Any further authorized native test belongs to the sole live
executor after the runtime blocker is resolved. Game/custom-room support remains
hard-blocked pending a separate reviewed extension and evidence.

## Offline verification

```powershell
python -B -m unittest test_win32_single_click -v
python -B -m unittest test_state test_capture test_child_session test_child_control test_win32_single_click
python -B -m unittest discover -s tests -p "test_strategy_*.py" -v
```

The focused suite has 31 tests: the original broker checks plus fake API cases
for complete/partial/uncertain batches, native PID gating, final revocation,
held-input refusal, owner-thread/lease behavior and failed cleanup. Fake DLL
functions and inert callback objects inspect bookkeeping and structure fields;
they do not certify native ABI, hook delivery, Windows permissions or UI effects.
The registration-error test models error 5 without invoking `RegisterHotKey`.

The complete 129-test offline regression passes with an integration guard that
rejects real `ctypes.WinDLL` loading during imports and tests. Existing small
synthetic CPU ranker-fit tests are included. No external model, capture, window
inspection or real native input is used by that regression.

The [strategy live handoff](STRATEGY_LIVE_HANDOFF.md) still applies: recognized
state, reviewed real rules, semantic action targets and observed postconditions
are not connected by this candidate. Toy advice remains advice only.

## API references used for review

- [SendInput](https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-sendinput): event insertion counts do not prove application behavior; events in one submitted batch are inserted serially.
- [RegisterHotKey](https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-registerhotkey): zero reports failure; a null HWND binds delivery to the calling thread's queue.
- [CreateMutexW](https://learn.microsoft.com/en-us/windows/win32/api/synchapi/nf-synchapi-createmutexw) and [ReleaseMutex](https://learn.microsoft.com/en-us/windows/win32/api/synchapi/nf-synchapi-releasemutex): ownership is thread-specific and acquisition can be recursive.
- [LowLevelMouseProc](https://learn.microsoft.com/en-us/windows/win32/winmsg/lowlevelmouseproc): callbacks need a message loop and must return promptly; timed-out hooks can be removed silently.
- [GetLastInputInfo](https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-getlastinputinfo): the information belongs to the calling session and timestamps can reflect injected input.
