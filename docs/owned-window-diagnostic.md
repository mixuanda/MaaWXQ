# Owned-window diagnostic: one operator entry

**The current allocator has not yet passed a live input run.** The previous
entry's 2026-10-18 16:33 UTC report passed deadline rejection and the readiness
wait, then delivered one DOWN/UP to the target with a native batch return of 3.
The click phase failed because the hook marked both events as injected but their
token did not match; physical emergency and owned-only release did not run.
This command remains the stable entry; earlier standalone probes are not needed.
Retain that report: it does not validate the updated allocator below. The next
owned-window run belongs to the single control worker after integration; do not
repeat the unchanged failing version or infer physical-key success from the UI.

From the repository directory in an ordinary **non-administrator Windows
PowerShell**, use the existing Python installation:

```powershell
python -B -X utf8 .\tools\owned_window_diagnostic.py --enable-once
```

Run it yourself in your normal desktop session. Do not launch an unrestricted
helper from the restricted agent shell or change privileges, permissions or
security settings to make it run. The entry refuses elevated, AppContainer,
UIAccess or unknown token contexts. No administrator launch is required.
If preflight or any stage fails, return its report rather than retrying.

## One approval for automatic checks, separate physical-key confirmation

The Chinese window shows the current status and one next action in large text.
Keep it visible. Check the initially unchecked consent box and press the primary
start button once to authorize only Deadline, Click and Focus. These first three
checks continue automatically after a passing stage. Each of the two physical-key
stages then pauses for its own unchecked readiness confirmation. Confirm readiness
first; press the named test keys only when the large current-action prompt asks.
Technical report details are collapsed by default; Stop remains available.

Release every mouse button and key, then keep still. Before each stage, a visible
countdown waits for all sampled inputs to be up and the session input marker to
stay unchanged for one full second. If input is held, release it yourself. This
unarmed wait lasts at most 15 seconds after that stage starts its readiness wait.
Motion or other input restarts the one-second countdown without extending that
absolute limit. A polling gap over 250 ms also restarts the quiet interval.
The automatic-group authorization never covers either physical-key stage.
Stopping or closing the window prevents every queued continuation; a failed stage
is never retried automatically.

This wait is read-only: it does not open input guards, take an input lease, send
input or force key/button releases. It stops on lost foreground, unavailable
input-marker information or timeout. It rechecks immediately before constructing
the broker, and the diagnostic port checks held categories again before the
production port's unchanged check. Input arriving in the final race can still
cause a safe refusal. No failed arm or submission is retried automatically.

| Stage | Your action | Evidence required to pass |
| --- | --- | --- |
| Deadline | Keep still | Delayed attempt rejected for deadline expiry; zero native submission and zero target events |
| Click | Keep still | Native batch return 3, tagged own hook DOWN/UP, and exactly one DOWN/UP delivered to the fixed blue widget |
| Focus | Keep still while a second owned window gets focus | Foreground actually changes to that owned window; old target rejects for lost foreground, with no submission or widget event |
| Emergency chord | Wait for target DOWN; physically press and release Ctrl+Alt+F9 | Physical F9 DOWN/UP, matching registered hotkey, keyboard-triggered stop, own left release and real widget UP; Ctrl/Alt/F9 all released before completion |
| Owned-only release | Wait for DOWN; press and **hold Right Shift**; release it only after the display asks | Physical Shift DOWN precedes stop; own left button releases while Shift stays down for at least 100 ms; physical Shift UP follows the rendered prompt |

The last two stages intentionally submit a test-only move/left-DOWN batch to the
process's own fixed widget. The inherited supervisor and four-second deadline
remain active. You do not need to click or release the physical mouse. The shared
pointer moves: this is foreground control, not cursor isolation. No keyboard event
is injected, and cleanup never releases your Right Shift or other keyboard keys.

Ctrl or Alt can trigger the existing takeover stop before F9. The emergency stage
keeps that early stop and separately requires the registered `WM_HOTKEY`; it does
not claim the hotkey alone caused release. Deadline-triggered release cannot pass
as an emergency trigger. Both native release-return and real widget-UP latencies
must be at most 250 ms for these samples to pass; this is not a timing guarantee.

If DOWN never appears, do not provide a physical trigger. Let the bounded stage
stop. Unknown, incomplete or uncertain submission is never retried as an action.
Any cleanup can only release the ledger's possibly owned left button. If a guard
reports incomplete cleanup, stop using the entry and return the full report.

## Return one complete report

The final JSON is printed and saved atomically under the Git-ignored
`local/owned-window-diagnostic/` directory. The console shows the exact file path.
Return the complete JSON, including unrun phases and cleanup fields. If saving
fails, cleanup still runs and the console JSON reports the write failure; copy
that JSON. Keep reports private rather than adding them to a public commit.

The report includes source hashes, token status, native counts, real widget
events, limited hook/hotkey evidence, timing, preserved Shift state and all broker
cleanup results. It logs only the named test keys or the category `other`; no
typed text, arbitrary key codes, pointer paths, screenshots or account data are
collected. Native event insertion counts alone never pass a delivery stage.

`ui_revision=chinese-current-step/2` records the Chinese current-step interface.
`automatic_group_consent` records the single approval for the first three checks;
each phase records its confirmation mode, original confirmation time and phase
start time. Group-approved phases are not reported as individually confirmed.
The two physical stages still record their own individual confirmation.

`readiness_revision=bounded-release-and-quiet/1` adds a per-phase `input_readiness`
summary: the wait/quiet durations, sample/reset counts, observed category union
and final held categories. Named categories identify mouse buttons, modifiers,
Enter/Space/Escape and lock keys; every other key is only `keyboard.other`.
There is no per-key timeline, text, arbitrary virtual-key code or pointer path.
`open_input_precheck` records the categories sampled just before opening the real
guard. If the production guard refuses after that clear sample, a separately
labeled later sample must not be treated as the exact original refusal cause.
The last-input timestamp is used only for inequality comparisons in memory;
it is not a globally ordered event clock and is not retained in the report.

`ownership_diagnostics_revision=full-width-mouse-tags/1` adds per-port ABI sizes,
alignment/offsets, token width, and mouse extra-info comparisons. The first
foreign mouse observation is retained separately; a bounded trace keeps at most
16 recent mouse observations, including MOVE without its coordinates. Extra-info
values are compared at their full pointer width. Reports include bit lengths,
full/low-32 equality, zero/sign-extension comparisons and per-port keyed
fingerprints, never raw tags, the private fingerprint key, pointer paths or text.
Formatting/hashing runs outside the hook callback; the callback only copies
scalar evidence after the existing foreign-input stop decision.
Snapshot copying briefly locks the bounded records so an incomplete guard cleanup
cannot produce mixed counters/records; hashing and formatting occur after unlock.

A low-32 match or a zero/sign-extension pattern is diagnostic evidence, never
permission to accept the event. `injected=true` alone does not establish its
origin. Complete-token equality, injection-flag checks, action budget, native
send, owned release and acceptance rules are unchanged. The port retains its
passive observation hook; the diagnostic's source pin follows the reviewed broker.

The allocator now creates the complete tag with `secrets.randbits(32)`, rejects
zero and never reuses an allocated tag within the process lifetime. It retains
retired tags under a separate lock so an old broker's delayed event cannot match
a later allocation. Even values and bit-31-set values are supported. At 65,536
retained values, or after 32 zero/duplicate draws, allocation fails closed.
`token_generation=uniform_nonzero_uint32_no_process_reuse/1` reports this change.

Two previous owned-window runs observed zero extension of the submitted tag's
low 32 bits on this machine, while the ctypes send buffers retained all submitted
bits. The exact native component responsible remains unknown. Generating a
complete 32-bit value addresses that observed transport boundary without masking
received values or accepting high-word/sign-extension aliases. This does not
establish how every Windows installation transports extra information.

Process-local uniqueness does not imply uniqueness across other applications or
process restarts. These random tags correlate events; they are not authentication
and cannot distinguish deliberately forged exact tags. Native success with the
new allocator remains unverified until an owned-window run shows exact full-value
MOVE/DOWN/UP matches, one widget DOWN/UP and confirmed cleanup. Real emergency and
Right Shift evidence is still required for their stages, and the game gate stays
closed. The allocator/guard regression suite plus the Chinese UI checks pass
70 offline tests with real Windows API and Tk window creation blocked; compilation
passes and the entire broker plus existing port guard methods are AST-identical.

The entry does not call [GetMessageExtraInfo](https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-getmessageextrainfo). That API reads the current thread's
message-queue extra information, while a low-level hook receives its event data
via [MSLLHOOKSTRUCT](https://learn.microsoft.com/en-us/windows/win32/api/winuser/ns-winuser-msllhookstruct). Calling the queue API from a different thread, or after Tk
has queued a callback, would not establish the original hook event's ownership.
It is not used as a replacement or fallback ownership signal.

All five accepted stages and complete cleanup are required for
`all_phases_passed=true`. Early failure saves a partial report and leaves later
stages `not_run`. A report-write failure also prevents an all-passed result.
The same entry has a noninteractive `--check-only` mode and defaults to disabled
without a mode flag; neither creates a window or registers input guards.

## Reviewed scope and remaining limits

No external-window identifier, executable, coordinates, game, remote endpoint,
elevation or fallback option is accepted. Actual targets must belong to this
process. The production click broker, single-owner lease, stop behavior and hard
custom-room rejection remain in place. Only passive diagnostic signals and
release counters/timestamps were added to the native port.

Integration corrected false-positive focus/receipt acceptance, post-stop callbacks,
release-before-prompt timing, report storage and write-error cleanup. Fake API and
report tests verify those paths without loading real Windows DLLs. They do not
certify native ABI, Tk/Windows message delivery or operation in a normal process.
The [focused offline checks](../test_owned_window_diagnostic.py) include long-held
confirmation inputs, high-bit semantics, privacy-safe categories, quiet-window
resets, timeout, focus loss, canceled/stale callbacks, and final input races.
They run with real Windows DLL loading forbidden. Additional tag-evidence tests
check native layout, full-width send-buffer bytes and the actual Python hook
branch against full matches, low-32 matches, sign extension and non-injected
events. The production input/stop decisions remain unchanged; the only native
port addition is passive post-decision mouse-tag observation. The Chinese UI and
consent integration passes 31 focused offline checks with native API loading and
Tk window creation blocked, including the
[consent-flow tests](../test_owned_window_diagnostic_ui.py). Compile checks pass;
the readiness gate, broker, complete-token ownership comparison, acceptance and
cleanup logic remain unchanged. A separate worker inspected the owned-window
layout at 96 DPI; this is rendering evidence, not a passed physical-input test or
validation at every DPI. Integration does not launch the diagnostic or send input.

Split DOWN submission can race the inherited last-input marker, which can also
observe our own injected event. Such revocation fails the test; the guard is not
suppressed to produce a passing sample. A blocked observer or in-flight native
call can delay cleanup. Hard kills, arbitrary multi-key ledgers, every device/DPI,
background input, anti-cheat behavior and game postconditions are unvalidated.

This executor remains unable to run active stages: its shell is AppContainer and
supported native desktop bindings are unavailable. No runtime repair or permission
change is implied. A complete self-window pass still **does not enable game input**.
The [experimental backend limits](EXPERIMENTAL_SINGLE_CLICK.md) and separate
custom-room review remain applicable. No third-party code/dependency or project
license change is introduced; see [the notices](../THIRD_PARTY_NOTICES.md).
