# Owned-window diagnostic: one operator entry

**This readiness revision has no new live input evidence.** The previous entry's
2026-10-18 16:12 UTC report passed deadline rejection in a normal user process,
then stopped before click submission with `preexisting_held_input`. It did not
identify the held key. No real click, physical emergency chord or held-button
release has passed. This command is the stable entry; earlier standalone probes
are not required by this procedure.

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

## Five separately confirmed stages

Keep the owned diagnostic window visible. For each stage, read the instructions,
tick its initially unchecked confirmation, and press **Confirm and run this phase
once**. Release every mouse button and key, then keep still. A visible countdown
waits for all sampled inputs to be up and the session input marker to stay
unchanged for one full second. It lists any still-held input categories so you can
release them yourself. This unarmed wait lasts at most 15 seconds after confirmation.
Motion or other input restarts the one-second countdown without extending that
absolute limit. A polling gap over 250 ms also restarts the quiet interval.
Later stages never arm automatically. **Stop and save report** or closing the
window stops the suite; no queued phase may run after stopping.

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
They run with real Windows DLL loading forbidden. The production broker is byte
identical to the previously reviewed version; native evidence remains necessary.

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
