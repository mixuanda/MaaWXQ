# ChildSession control core — offline contract

**Status: reusable state machine and authenticated codecs tested only with synthetic clocks/adapters.** No native input, Windows IPC endpoint, session activation, RDP connection, preview or game access is implemented by this change. `ChildSessionBackend` remains disabled and refuses live execution. All actual window/capture/input/login tests remain paused. No network port, credential, privilege or system setting is created or changed.

## Modules and hard boundary

- `control.py`: immutable session binding, bounded action lease/queue, heartbeat and hold deadlines, generation fencing, stop latch, owned-input ledger and resource cleanup.
- `control_protocol.py`: bounded authenticated heartbeat/action envelopes and monotonic sequence validation. Acceptance and core application are serialized on this lane so concurrently received messages cannot reverse their accepted order. Its accepted/queued results are local model results, not transport acknowledgments.
- `stop_protocol.py`: independent priority stop lane. Sequence acceptance is atomic and occurs before potentially slow cleanup, preventing a late older callback from rolling its replay watermark backward.
- `ports.py`: future local-IPC/native interfaces and disconnected defaults. No concrete Windows adapter exists.

The default core cannot grant an action lease or call input. Even ports claiming to be a future native/Windows IPC implementation are rejected. An explicit `simulation=True` plus `scope="synthetic"` ports allows unit-test model submissions only. Reports retain `operational=false`, `sent=false`, `execution_confirmed=false` and no remote-release acknowledgment. Scope labels are not an OS sandbox or proof of adapter honesty; synthetic ports must never wrap actual OS input.

## Binding, heartbeat and lease

`SessionBinding` requires resolved IDs: worker and game share one nonzero child session, distinct from the main session. It also binds connection ID, worker instance, window identity version and geometry version. The core cannot replace its binding in place. Supplied IDs/tokens are not verified Windows evidence; a future child-local adapter must derive and recheck them from actual process/session identity after explicit live-test authorization.

Every request includes action ID, lease ID, stop generation and binding digest. The core checks current binding before dispatch and independently during active supervisor ticks. A changed session, worker, window or geometry latches stopped; old requests cannot be rebound automatically. Unknown identity is not an allowed execution context.

Heartbeat freshness and lease deadlines use the receiver's monotonic clock; message issue times are separately checked by the codec. A heartbeat cannot revive an expired lease or a stopped worker. New lease IDs supersede old idle leases; a busy queue, held input or in-flight submission prevents replacement. Old lease IDs and duplicate action IDs are rejected.

Defaults are engineering limits, not measured guarantees: heartbeat timeout 1 second, maximum lease 1 second, held-input limit 0.5 seconds, at most 16 actions/queued requests and 256 seen action IDs per connection. The error detail list is bounded to 16 entries with a separate total counter. Receipt of a heartbeat never extends an existing lease's expiry. Budget exhaustion stops further submissions and triggers owned-input cleanup.

No background thread or polling loop starts on construction/import. A future independent supervisor must call `tick()` regularly, independently of OCR, preview, transport reads and action processing. Dispatch paths also check deadlines. Without that future scheduling/transport implementation, there is no real-time watchdog or demonstrated 200 ms stop latency.

## Stop and in-flight completion

Local stop first increments the generation once, latches stopped, revokes the lease and clears queued requests. Cleanup occurs after state revocation and outside the short state lock. There is no resume/reset method: reconnect requires a new reviewed binding and protocol instance. Late authenticated actions/heartbeats are rejected even if their message sequence is newer than the stop request.

The priority stop codec has a sequence space independent of action/heartbeat ordering, so a large action sequence cannot suppress a valid fresh stop. Both codecs check HMAC-SHA256, message size, schema, connection/session binding, timestamps and replay order; they do not provide an IPC transport, peer ACL or startup authorization. Valid authenticated messages can still be rejected by the core. A codec success is never evidence that an input occurred.

Before each synthetic adapter call, the core reserves budget and records an intended down event. The adapter receives a fast generation/lease permit callback that performs no adapter I/O or cleanup; a future adapter must fence immediately at the irreversible submission boundary. The core also rechecks after completion. A callback that completes after stop is reported blocked/uncertain and any same-binding owned down is cleaned up; it is never upgraded to successful execution.

In-flight ledger entries remain pending during stop rather than being falsely marked released. Once a pending call returns, cleanup is attempted. The core cannot forcibly cancel an arbitrary blocking Python/native callback. Future adapters need bounded/cancellable calls and child-local independent release supervision; tests with fake callbacks do not establish native timing or eliminate the OS submission race.

## Held inputs and cleanup

The current action vocabulary is deliberately limited to key/button down/up with bounded numeric codes. There is no process launch, arbitrary command, coordinate move, scroll or drag implementation. Unknown operations are rejected. The higher-level game-mode/action SafetyGate and native acceptance tests are still required before any actual execution path can be added.

Only a recorded key/button can be released. Duplicate downs and unowned ups are rejected. Errors after a down attempt preserve the ledger and latch stop, allowing a same-binding release attempt. If binding has changed or the native endpoint is disconnected, the core does not send an up into an unknown session; the unresolved ledger remains visible and `remote_release_confirmed` stays false.

Transport loss revokes the lease; a still-connected same-binding local adapter may clean its own model ledger without the transport. Release failures remain pending and visible. `close()` attempts both resource closes even if an ordinary close callback fails and is idempotent; context-manager exit performs cleanup on action errors/interrupts. Adapter-returned release/submission results are model facts only, not game postconditions or remote release receipts.

## Future Windows IPC obligations

The future adapter should implement bounded local named-pipe reads and cancellation, restrictive existing-user/process/session ACLs, peer-instance/session verification and an exclusive child-worker owner mutex. These are **not implemented** by the protocols or the per-core lease. Do not expose a network listener or equate a pipe name/HMAC alone with trusted peer identity. Connection secrets/tokens must be ephemeral and never stored in public configuration or logs; no real key generation/storage is performed by this prototype.

The main session remains preview-only plus stop, and the game/executor stay in the selected child session. Neither a missing channel nor a rejected action permits foreground/Win32 fallback. Actual startup, credentials, system changes and resumed live testing require separate user authorization. No BetterGI implementation code was copied, and no dependency/license choice changed.

## Offline verification

```powershell
python -B -m unittest test_child_control test_child_session -v
```

The 14 control tests and 8 existing backend tests use synthetic ports/clocks only. They cover disconnected/live-path rejection, owned down/up bookkeeping, permanent stop/queue invalidation, heartbeat/lease/hold deadlines, session change, adapter and close errors, unresolved release, in-flight stop fencing and late cleanup, ordered concurrent control application, independent stop sequence ordering, message tampering/staleness/replay, replaced leases and interrupt cleanup. They do not establish a working desktop-duplication backend, real IPC acknowledgments, native input, noninterference or playing strength.

Parent design: [CHILD_SESSION_BACKEND.md](CHILD_SESSION_BACKEND.md). The public Win32 backend, strategy code and shared state schema are unchanged by this control-core step.
