# Yixing rule evidence review

Reviewed on 2026-10-17. English is authoritative. This research adds no executable
game rule, input capability, training result or playing-strength claim. The
integrated advisory core remains unchanged in this research round.

## What the sources establish

The useful new primary source is the [official publisher's October 15 v1.6.1
announcement](https://www.taptap.cn/moment/859509109601339933?group_id=399839).
It announces Yixing's **Yushi (驭势) energy cost changing from 8 to 6**, and a
correction to his level-six talent description. The corrected full text is not
given. The author's link resolves to the publisher listed in TapTap's [certified
official moderator roster](https://www.taptap.cn/group/399839/info). This is
publisher evidence, rather than an anonymous repost.

These are source-scoped facts F02/F03, not a complete current action rule. The
running client, server, mode, later changes, effective cost modifiers, available
targets and copy outcome remain unverified. The patch is the latest balance
announcement located in this bounded review, not a guarantee of the latest
deployed version. Its date header displays October 14 without a year; the
effective-date year is inferred from dated 2026 events in the same article.

The [official novice guide](https://wxq.qq.com/cp/a202609xszy/) supports broad
planning concepts: round-level opponent assignment, energy carryover, upgrading,
card effects and factions. It has no explicit patch binding. Exact transition
tables and exceptions remain gaps. The [test-server
FAQ](https://wxq.qq.com/cp/a202609tyf/) explicitly distinguishes experimental
designs from production. Neither a guide nor test-server content establishes
the user's present match rules.

The developer-authored [App Store
description](https://apps.apple.com/cn/app/%E7%8E%8B%E8%80%85%E4%B8%87%E8%B1%A1%E6%A3%8B/id1614798032)
names Yixing among chess players. Its visible package label is `1.1.1`, dated
August 27 without a displayed year. Package labels and balance-announcement
labels have different meanings; do not infer the installed build by comparing
those strings. User reviews on the listing are not publisher rule evidence.

The normalized statements, provenance, locators, date limitations and unknowns
are in [sources.json](../../data/rules_review/sources.json) and
[claims.draft.json](../../data/rules_review/claims.draft.json). `runtime_eligible`
is false throughout. This review schema is deliberately different from the
strategy runtime registry, preventing accidental activation.

## Rule gaps and their decision impact

| Gap | Missing evidence | What must wait |
| --- | --- | --- |
| G01 Version context | Installed build, live patch, production/test server and mode | Any real action-rule activation |
| G02 Trigger and timing | Full current passive/secret ability text, reward availability and phase order | Scheduling a copy or a multi-step plan around one |
| G03 Effective cost | Current modifiers, payment point and failure/refund behavior | Reliable resource accounting for Yushi |
| G04 Target pool | Which opponent/units qualify, random selection, ties and player control | Target-specific or expected copied value |
| G05 Copy semantics | Destination, persistence, levels, equipment, effects, awakening and corrected talent text | Valuing a copied unit or assuming it joins combat |
| G06 Capacity | Hand/board limits, overflow and trigger order | Reserving slots or selling to enable copying |
| G07 Bans | Object/category, match scope, semantic IDs and copy/acquisition exceptions | Applying real ban coverage safely |
| G08 Economy | Versioned income, prices, sales, upgrades, refreshes and odds | Comparing exact economic sequences |
| G09 Composition | Resolved entity IDs, keyword order, faction interactions and positioning | Marginal synergy or formation value |
| G10 Opponents | Coverage, unseen changes and actual possible matchups | Calibrated threats or a known next opponent |
| G11 Auctions | Availability, payment, dividends and timing | Bid optimization |
| G12 Combat | Validated battle/damage/placement transitions | Win probabilities, full-game planning or RL labels |

The new cost evidence reduces one narrow gap. It does not resolve the surrounding
dependencies. No copying round, target count, inherited property, unverified
cost modifier, ban effect or economy breakpoint is filled from memory.

## Why older guides stay outside the rule registry

The [3DM Yixing article](https://shouyou.3dmgame.com/gl/634057.html), displayed as
2026-08-27, mixes a board-control introduction with chess-player copying in its
body. It attributes an origin to TapTap without a resolved original. A [second
3DM overview](https://shouyou.3dmgame.com/gl/634052.html) on the same displayed
date describes a different eligible pool. No conflicting numeric claim is
selected as true. Their strategic opinions are hypotheses without sampled
high-rank outcomes or version-bound counterexamples.

The [Ali213 Yixing page](https://m.ali213.net/news/gl2609/1804857.html), displayed
as 2026-09-02, places him among hero cards and describes damage. It cannot supply
chess-player rules. Keep `chess_player`, `hero` and the original Honor of Kings
MOBA entity distinct even when their display names match.

The [official site's dynamic catalog](https://wxq.qq.com/cp/a20260707sfgw/index.html)
and its linked team list contain static placeholder names, descriptions and
statistics before population. Those placeholders were excluded. A recent crawl,
URL path date or changing page chrome is not a dataset observation date. No
lineup ranking, win rate or stale third-party feed was promoted.

## Review procedure and remaining access limits

Public web retrieval could not render the Tencent guide pages, but a direct
read-only HTTPS fetch returned their authored HTML. The source ledger stores
retrieval date and byte hashes, not complete pages or game assets. Hidden scripts
were not run, and installers, videos, images and external scripts were not saved.
The source author profile was challenge-protected; the announcement's author
link plus the publicly readable certified roster established attribution.

This is a bounded source review, not an exhaustive search. It did not observe
the running game, verify an installed patch, perform an ability test or access a
private account. Those unavailable observations remain unknown; no blocked
live action was retried. Independent annotation, planner design and review-data
work can proceed using the gaps explicitly.

Promote a rule only when its source statement, interpretation, applicable version
and transition regression are all reviewed. Until then, preserve the draft and
keep the corresponding real-game candidate unavailable.
