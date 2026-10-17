# MaaWXQ

An experimental Windows observation and strategy-assistance prototype for **Wangzhe Wanxiangqi (王者万象棋)**, starting with the **Yixing chess player (棋手弈星)**.

**Status: offline state prototype with a diagnostic one-shot capture entry point.** There is no OCR, MaaFramework integration, recommendation engine, input controller, or autonomous match play yet. The project is independent and is not an official game tool or a completed MAA integration.

English is the authoritative project language. Translations may be added; the English version takes precedence if they differ. Chinese game labels in configuration, fixtures, and source are intentional UI/domain strings.

## What works today

- Offline initialization and JSONL replay of synthetic opponent observations and opening-ban labels.
- Append-only opponent history, explicit unknown values, timezone-aware timestamps, and configurable freshness reporting.
- Separate identities for the Yixing chess player and a same-named hero; unknown IDs are never guessed from names.
- Read-only Windows title enumeration and an explicit one-shot PrintWindow diagnostic.
- Capture cache limits of **64 MiB and 50 files**, stopping at either limit without evicting existing user files.

On 2026-10-17, a separate OS window-region screenshot was visually confirmed to show the real game's custom-mode selection page. This was **not an in-room input test**, and did not validate PrintWindow, WGC, background input, or in-match recognition. An earlier launcher PrintWindow attempt failed with `image=null`; that failure does not establish how the game itself behaves. See [VALIDATION.md](VALIDATION.md).

## Quick start

Python 3.10 or newer is required. The current prototype uses only the Python standard library. Windows and Windows PowerShell are required only for window inspection and capture.

Run from the repository root:

```powershell
python -X utf8 main.py demo
python -X utf8 main.py replay --events examples/events.jsonl
python -X utf8 main.py capture-plan
python -B -m unittest -v
```

These commands do not send game input. The supplied event file is synthetic. Its historical timestamps will normally produce `stale` output; this is expected.

To enumerate visible matching Windows titles:

```powershell
python -X utf8 main.py windows
```

An empty list may reflect desktop/session isolation. A matching title does not establish whether a window is a launcher or the game.

For an explicitly requested diagnostic capture, obtain a **fresh HWND and owning PID**, verify the intended window, and replace the placeholders:

```powershell
python -X utf8 capture.py --hwnd <CURRENT_HWND> --pid <CURRENT_PID> --role unknown
```

`--role game` is only a caller assertion, not visual validation. The worker does not focus, restore, move, or click the window and has no desktop-capture fallback. Successful pixel capture remains `candidate_requires_visual_review`; black/low-detail frames, invalid identities, minimization, worker errors, timeouts, and cache exhaustion are reported separately. The Python entry point owns the capture lock; do not invoke the PowerShell worker directly.

## Configuration and data

`config.json` contains shareable defaults. `capture_enabled` and `input_enabled` are false. No capture loop or input implementation exists, and changing those flags does not create one. The explicit `capture.py` command is independent of those flags.

`cache/` is created as needed. Its limit counts **all files**, not just images. A stale `.capture.lock` stops capture; inspect the owning process before manually removing a stale lock. Real-time files should remain on a local SSD. `archive_dir` is null, and no archive/NAS writes are implemented.

Do not publish captures, account identifiers, raw match replays, logs, machine-specific paths, credentials, or downloaded game/third-party assets. The committed JSONL fixture is synthetic and explicitly allowlisted in `.gitignore`. A local override loader is not implemented yet; ignored `*.local.*` files are reserved for future machine-specific configuration.

The 120-second freshness threshold is an engineering default, not a verified game rule. The future policy must preserve confirmed current-match bans independently of this TTL. See [PLAN.md](PLAN.md) for the planned contract.

## Roadmap and collaboration

1. **P0:** verify real-game frames and add a bounded, read-only capture adapter.
2. **P1:** build match-scoped observations, opponent memory, verified Yixing rules, and explainable recommendations.
3. **P2:** validate pause/stop/release safeguards, then one reversible input in a custom room.
4. **P3:** attempt one bounded preparation-round loop with visible postconditions.

Detailed gates and implementation tickets are in [PLAN.md](PLAN.md) and [TASKS.md](TASKS.md). Astra owns planning and major design reviews; `gpt-6.1-sol` handles implementation and focused verification. Only one executor may control the game window at a time.

Input experiments are restricted to custom rooms. Ranked play, matchmaking, invitations, spending, account changes, process-memory access, injection, anti-cheat bypasses, drivers, process suspension, forced window movement, and cursor blocking are outside the project plan. Login remains manual. Unattended operation must leave the main desktop's pointer, keyboard and focus undisturbed; foreground input is only a supervised diagnostic. Child-session isolation remains an unverified option requiring separate review of any system changes. No zero-risk or universal-background-operation claim is made.

Read [CONTRIBUTING.md](CONTRIBUTING.md) before proposing changes. No license has been selected yet; public visibility should not be interpreted as an open-source license grant. No third-party source or game assets are bundled.
