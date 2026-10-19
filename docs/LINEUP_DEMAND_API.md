# Demand-first lineup advice

`Advisor.advise_lineup` chooses a supplied, supported target lineup before
considering purchases. It buys unmet core targets or explicitly named temporary
roles, never arbitrary affordable cards. An owned target in hand is considered
for an empty board slot first. A visible needed card with unknown price/currency,
insufficient funds or no hand space produces a hold rather than a refresh.

The existing `Advisor.observe` / `MatchState` reducer remains the state store.
A BoardState recognizer projects its confirmed fields into that store; no
second history store, UI worker or input implementation is added.

## Python interface

```python
from strategy.contracts import Source
from strategy.lineup import Lineup, Target, Spending, Upgrade, Affinity

# Exact IDs/targets come from the current reviewed recommendation or own plan.
# Do not infer a lineup from a voice label or a shop card's price.
plan = Lineup(
    lineup_id=observed_plan_id,
    source=Source("screen_recognition", recommendation_evidence_ref),
    targets=tuple(Target(hero_id, source, priority=priority)
                  for hero_id, source, priority in observed_core_targets),
    chess_player_id=observed_chess_player_id,
    search_min_level=declared_search_level_preference,
    ban_mapping_source=reviewed_ban_mapping_source,  # Required for nonempty bans.
)
money = Spending(
    reference=declared_budget_policy_ref,
    reserve=protected_general_funds,
    level_reserve=protected_leveling_funds,
    upgrade_reserve=protected_star_copy_funds,
    refresh_spend_cap=maximum_refresh_spend,
    refresh_spent=confirmed_refresh_spend_so_far,
    refresh_count_cap=maximum_refresh_count,
    refresh_count=confirmed_refresh_count_so_far,
)
advice = advisor.advise_lineup(
    [plan], decision_at=current_utc, spending=money,
    upgrades=reviewed_star_recipes, opponent_id=observed_opponent_id,
)
```

The caller owns the persistent refresh counters and updates them from actual
transaction outcomes. Recompute after every new capture or material action.
This advice is not an `Advisor.validate` proposal or an input permit. The
existing native handlers must still check UI legality and postconditions.

## Fields from the current observation

Every value uses the existing `FieldValue`/observation confidence, source and
timestamp contract; unknown OCR remains unknown. Time, round and phase checks
reuse the Advisor policy. Instance IDs must be distinct even for equal heroes.

| Field key | Meaning |
| --- | --- |
| `board_ids`, `hand_ids`, `offer_ids` | Complete observed instance-ID tuples for the relevant zones |
| `hero:<instance_id>` | Resolved hero identity for each board/hand/offer instance |
| `capacity`, `free_hand` | Current board capacity and legal free hand space |
| `credits`, `currency_id` | Explicit observed balance and currency mapping; energy is not silently relabeled |
| `price:<offer_id>`, `currency:<offer_id>` | Current effective price and its currency |
| `refresh_cost`, `refresh_currency_id` | Actual current refresh quote |
| `player_level` | Player/shop level, not a hero property |
| `level_up_cost`, `level_up_currency_id`, `level_up_target_level` | Actual upgrade quote and displayed resulting player level |
| `star:<instance_id>` | Verified unit star level only |
| `quality_tier:<instance_id>` | Separate card quality tier; never substituted for stars/player level |
| `unit_level:<instance_id>` | Separate hero level; never substituted for stars |
| `selected_chess_player_id` | Actual player identity for a player-specific lineup |
| `shop_odds_percent:<quality_tier>` | Optional current UI probabilities by quality tier, reported without guessing individual-hero odds |

Match bans use existing persistent `confirmed_bans` and explicit ban evidence.
Targets carry the reviewed corresponding `ban_tags`; a prohibited core removes
that route. Nonempty bans require `Lineup.ban_mapping_source`; unresolved ban
semantics cannot silently pass as an empty mapping. A later empty report cannot
lift confirmed bans. A missing unrelated
shop identity does not prevent buying a verified needed card, but prevents
claiming that the shop has no useful card and refreshing blindly.

## Goals, upgrades, interactions and pivots

Each `Target` names a core or a `role="transition"` with an explicit `replaces`
tuple of core IDs. A temporary unit is eligible only while its named core is
missing. There is no generic cheapest-filler fallback.

`Target.desired_star` is a strategy goal, not a card tier or a merge recipe.
`Upgrade(hero_id, input_star, output_star, copies_required, source)` must contain
an applicable reviewed rule. No three-copy rule is built in. Known complete-set
deficits get priority over partial duplicate progress; missing composition
targets come first. Unknown recipes prevent speculative duplicate purchases.
Complete sets are reported as opportunities, without automatically merging.
Future copy cost remains unknown; the declared copy reserve protects funds
from unrelated purchases and refreshes.

`Affinity` supplies an independently reviewed interaction, benefiting hero IDs
and current conditions such as talent/equipment tags, an observed active faction
field, or an observed opponent hero. Its `need_bonus` is an ordinal policy
preference, not combat damage or win probability. Unreviewed interactions and
missing conditions are listed as unknown and give no bonus. The module includes
no invented faction table, item stats or talent mechanics.

Lineup fit counts owned targets and visible acquisitions affordable together
after declared reserves, at declared priorities, plus supported affinity
preferences. Ties favor keeping more owned targets. Returned
`pivot_candidates` show retained/missing heroes, with switching cost unknown;
they do not authorize sales, repositioning or a manual Yi Xing copy target.
Player-specific alternatives require the observed player ID. No meta lineup
names or compositions are hardcoded.

Opponent snapshots reuse actual board-observation events. A later note does
not refresh old board evidence; partial views never prove unseen units absent.
History stays match-scoped through the existing reducer. The selected observed
opponent is not assumed to be the next randomly assigned opponent.

## Level first, then bounded search

`search_min_level` is an explicit per-lineup policy preference. A value such as
five can represent user experience awaiting UI verification; it does not assert
a game probability breakpoint. Below that level, the advisor uses only a known
upgrade price/result, respecting reserves, or holds for the missing quote.
No level increment, interest schedule, income or pool distribution is invented.

Once the level preference is met and no demanded offer is visible, refreshes
are limited by remaining spend/count caps and balance after general, leveling
and star-copy reserves. An unknown refresh quote or currency produces hold.
An explicit zero price still needs the finite count cap. The result does not
claim refresh expected value, exact core-card probability or that the whole
balance should be spent. The reported refresh count is an upper bound at the
current quote, not a promise about later prices; only one action is proposed.

User suggestions about Yi Xing/circle lineups, Ying Zheng four-star goals,
Hua Mulan/Luna five-star goals, Li Bai/Shangguan Wan'er four-star goals and
Wu Zetian five-star goals are policy hypotheses awaiting current UI verification.
They are not installed as verified star recipes, quality labels or probability
rules. The caller can supply confirmed recommendation targets and separately
record these desired goals; unknown progression mechanics remain unknown.

Results include `selected_lineup`, `lineup_ranking`, `demands`, `needed_offers`,
`need_score`, `upgrade_gaps`, `refresh_budget` when relevant, reason codes and
evidence references. Actions are `deploy`, `buy`, `level_up`, `refresh` or `hold`.
`execution_allowed` is always false and `strength_estimate` is null. A small
synthetic fixture checks these choices; this is usable policy code, not a live
strength or end-to-end gameplay result.
