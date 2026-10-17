# Capture interface v1

The shared game-state baseline remains `state.schema.json` (`schema_version: "1.0"`). T1 does not change its manual event contract. A capture result is a different envelope, with `schema_version: "capture/1"`; a frame is evidence for a later perception event, not a game-state update.

`window_identity.inspect_window(hwnd, expected_pid)` returns HWND/PID, optional process start time with metadata-error code, class/title, DPI, client geometry in physical screen pixels, window bounds, visibility/minimization, observation time, identity token and geometry token. Tokens are stable hashes of their respective fields, not increasing counters. Process start time can be unavailable, weakening the binding; consumers must preserve that uncertainty. A token cannot detect unobserved change-and-revert between samples.

`capture_backend.capture_one(hwnd, pid, role="unknown", backend="printwindow" | "wgc")` returns:

- `status`, `reason`, `backend`, optional `backend_version`, and `input_enabled: false`.
- `attempt_id`, `frame_id` (null on failure), `image` (null on failure), dimensions and quality.
- `requested_at`, acquisition start/finish, optional `acquired_at`, `completed_at` and monotonic `elapsed_ms`.
- `source_frame_at: null`: these adapters do not expose the capture source's clock. Receipt/request times must not be passed off as the GPU frame's timestamp or proof of freshness.
- `identity_before`, `identity_after`, and accepted `geometry_version`.
- `desktop_effects`: two-endpoint pointer/focus comparison only, not a continuous observation or attribution of changes to the backend.

`candidate_requires_visual_review` means the encoded frame and sampled pixel variation passed technical checks. It does not mean OCR, current game phase, freshness or formal game recognition passed. Caller-supplied `role=game` does not upgrade validation.

Both backends reject hidden/minimized targets, changed identity/geometry, invalid frame dimensions, capture timeout and exceeded cache limits. No desktop-image fallback exists. WGC uses only the pinned plain FramePool route with native mouse/keyboard methods None; capture/input/background-drag/background-keyboard capabilities remain separate.

Downstream perception may refer to `frame_id`, observed evidence time, match/round, confidence and identity/geometry tokens. It should preserve unknown bans/opponents and add its own semantic evidence. Do not put raw private image paths or window/process identifiers into public fixtures.

The future policy may return an **unimplemented action intent**, such as `kind`, domain parameters, `match_id`, expected phase, evidence frame ID and expiry. The operation line will define and validate its executable schema with SafetyGate/InputBroker in T4/T5. No capture API executes intents, and no shared action schema is frozen in T1. Coordinate requirements with the operation line before adding any broker calls.
