# Contributing

MaaWXQ is an early experimental prototype. Keep changes small, explain the user-visible behavior, and distinguish offline evidence from real-game validation.

English is authoritative for documentation, identifiers, comments, and task descriptions. Translations are welcome as separate files. Preserve literal game UI labels where needed for matching; do not translate them inside recognition data.

## Workflow

1. Select a task from [TASKS.md](TASKS.md) and identify the files it owns.
2. Check the working tree before editing. Do not overwrite unrelated changes or run a second writer against the same files.
3. Keep input disabled unless the applicable custom-room gate in [PLAN.md](PLAN.md) has passed. A code reviewer or parallel research agent must not operate the game window.
4. Run the existing offline tests when state or capture behavior changes, plus a focused check for the changed invariant. Do not run long game loops to validate a small change.
5. Report what changed, evidence, remaining uncertainty, and stop/rollback behavior. A backend return value is not a verified game action.

Astra handles planning and major design review. `gpt-6.1-sol` handles implementation and focused testing. Parallel work must have distinct file ownership, and live input always has one executor.

## Public-data review

Before committing or pushing, inspect both the paths and contents:

```powershell
git status --short
git diff --cached --name-only
git diff --cached --check
git diff --cached
git ls-files
```

Stage explicit paths instead of all local files. `.gitignore` does not remove files already tracked and is not a substitute for content review. Never commit screenshots, raw matches, account/game identifiers, private machine paths, logs, credentials, `.env` files, or downloaded third-party/game assets. Keep reproduction data synthetic and anonymous. The existing `examples/events.jsonl` is synthetic.

Do not add or change a license without a maintainer decision. Do not copy upstream source into this repository as a shortcut; link to pinned sources and review dependency licenses before adding dependencies.

## Input and data boundaries

Experiments may use custom rooms only. Do not add ranked/matchmaking flows, invitations, spending, account changes, memory reads, injection, anti-cheat bypasses, drivers, process suspension, forced window following, `BlockInput`, or `ClipCursor`. Login is manual. Cancelled or uncertain purchases/sales/refreshes must never be blindly retried.

Bug reports should describe sanitized steps and observed states. Do not attach credentials, private captures, or identifiable replays to public issues. No private reporting channel or security-support SLA is currently advertised; do not invent one.
