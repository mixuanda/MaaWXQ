"""Demand-first lineup advice over the existing match/evidence store.

Targets and interactions are supplied from reviewed UI/rules, never a built-in
meta lineup. Priority numbers express policy preference, not combat strength.
"""
from collections import Counter
from dataclasses import dataclass
from datetime import timedelta

from .contracts import Source, identifier, number
from .policy import Policy, _evidence_reasons


@dataclass(frozen=True)
class Target:
    hero_id: str
    source: Source
    priority: int = 1
    count: int = 1
    role: str = 'core'
    replaces: tuple[str, ...] = ()
    ban_tags: tuple[str, ...] = ()
    desired_star: int | None = None

    def __post_init__(self):
        identifier(self.hero_id)
        if self.role not in ('core', 'transition') or type(self.count) is not int or not 1 <= self.count <= 8:
            raise ValueError('explicit bounded lineup role/count required')
        if type(self.priority) is not int or not 1 <= self.priority <= 100:
            raise ValueError('positive ordinal policy priority required')
        if self.desired_star is not None and (type(self.desired_star) is not int or not 1 <= self.desired_star <= 99):
            raise ValueError('desired star is a policy goal, distinct from card quality or player level')
        if self.role == 'transition' and not self.replaces:
            raise ValueError('transition target must name the core need it temporarily replaces')
        for values in (self.replaces, self.ban_tags):
            if not isinstance(values, tuple) or len(set(values)) != len(values):
                raise ValueError('distinct immutable target tags required')
            for value in values: identifier(value)


@dataclass(frozen=True)
class Affinity:
    """A sourced interaction plus a declared ordinal preference bonus.

    Examples: a reviewed talent/equipment-to-hero link, a faction condition or
    an opponent counter. Conditions refer to actual evidence fields, not names
    guessed by this module. Absence in a partial opponent view stays unknown.
    """
    affinity_id: str
    source: Source
    conditions: tuple[tuple[str, str | int | bool], ...]
    hero_ids: tuple[str, ...]
    need_bonus: int = 1

    def __post_init__(self):
        identifier(self.affinity_id)
        if not isinstance(self.conditions, tuple) or not self.conditions or len(self.conditions) > 8:
            raise ValueError('bounded explicit interaction conditions required')
        for path, value in self.conditions:
            if not path.startswith(('self.', 'opponent.')):
                raise ValueError('interaction uses self/opponent evidence fields')
            identifier(path.split('.', 1)[1])
            if not isinstance(value, str) and type(value) is not bool and not number(value):
                raise ValueError('interaction requires an observed scalar/tag condition')
        if not isinstance(self.hero_ids, tuple) or not self.hero_ids:
            raise ValueError('interaction must identify its benefiting heroes')
        if len(set(self.hero_ids)) != len(self.hero_ids):
            raise ValueError('interaction hero IDs must be distinct')
        if type(self.need_bonus) is not int or not 0 <= self.need_bonus <= 100:
            raise ValueError('ordinal interaction preference must be bounded')


@dataclass(frozen=True)
class Lineup:
    lineup_id: str
    source: Source
    targets: tuple[Target, ...]
    affinities: tuple[Affinity, ...] = ()
    chess_player_id: str | None = None
    search_min_level: int | None = None
    ban_mapping_source: Source | None = None

    def __post_init__(self):
        identifier(self.lineup_id)
        if not isinstance(self.targets, tuple) or not 1 <= len(self.targets) <= 16:
            raise ValueError('bounded explicit lineup targets required')
        if len({x.hero_id for x in self.targets}) != len(self.targets):
            raise ValueError('combine duplicate lineup targets explicitly')
        core = {x.hero_id for x in self.targets if x.role == 'core'}
        if not core or any(not set(x.replaces) <= core for x in self.targets):
            raise ValueError('transition must reference this lineup core')
        if not isinstance(self.affinities, tuple) or len(self.affinities) > 16:
            raise ValueError('bounded sourced interactions required')
        if len({x.affinity_id for x in self.affinities}) != len(self.affinities):
            raise ValueError('interaction IDs must be distinct')
        if self.chess_player_id is not None: identifier(self.chess_player_id)
        if self.search_min_level is not None and (type(self.search_min_level) is not int or not 0 <= self.search_min_level <= 99):
            raise ValueError('search minimum is an explicit policy preference, not a probability table')


@dataclass(frozen=True)
class Upgrade:
    hero_id: str
    input_star: int
    output_star: int
    copies_required: int
    source: Source

    def __post_init__(self):
        identifier(self.hero_id)
        if (any(type(v) is not int for v in (self.input_star, self.output_star, self.copies_required))
                or not 1 <= self.input_star < self.output_star <= 99 or not 2 <= self.copies_required <= 16):
            raise ValueError('explicit reviewed upgrade inputs required; no default merge rule')


@dataclass(frozen=True)
class Spending:
    """Caller policy, not interest, income, shop odds or an expected-value model."""
    reference: str
    reserve: int = 0
    upgrade_reserve: int = 0
    level_reserve: int = 0
    refresh_spend_cap: int = 0
    refresh_spent: int = 0
    refresh_count_cap: int = 0
    refresh_count: int = 0

    def __post_init__(self):
        identifier(self.reference)
        for value in (self.reserve, self.upgrade_reserve, self.level_reserve, self.refresh_spend_cap, self.refresh_spent,
                      self.refresh_count_cap, self.refresh_count):
            if type(value) is not int or not 0 <= value <= 100000:
                raise ValueError('nonnegative bounded explicit spending policy required')


def opponent_snapshots(state, *, now, policy=Policy()):
    """Reuse reducer history; a note cannot refresh an older board observation."""
    result = []
    for memory in state.opponents:
        events = [event for event in state.events if event.kind == 'opponent'
                  and event.opponent_id == memory.opponent_id and event.observed_at <= now
                  and event.ingested_at <= now and any(f.key in ('hero_ids', 'board_ids', 'unit_ids') for f in event.fields)]
        if not events: continue
        origin = max(events, key=lambda event: (event.observed_at, event.round or -1))
        fields = {item.field.key: item for item in memory.fields if item.event_id == origin.event_id}
        reasons = []
        if origin.source.kind == 'synthetic' and not policy.allow_test_rules:
            reasons.append('synthetic_opponent_requires_opt_in')
        for key in ('hero_ids', 'board_ids', 'unit_ids'):
            if key in fields:
                reasons.extend(_evidence_reasons(fields[key], state, now, policy, 'opponent.' + key))
        result.append({'opponent_id': memory.opponent_id, 'event_id': origin.event_id,
                       'observed_at': origin.observed_at.isoformat(), 'coverage': origin.coverage,
                       'age_seconds': (now-origin.observed_at).total_seconds(), 'usable': not reasons,
                       'fields': {key: item.field.value for key, item in fields.items()
                                  if not _evidence_reasons(item, state, now, policy, 'opponent.' + key)},
                       'history_event_ids': [event.event_id for event in events], 'reasons': reasons,
                       'source_reference': origin.source.reference,
                       'unseen_units_absent': origin.coverage == 'full', 'next_opponent_predicted': False})
    return result


def advise_lineup(state, plans, *, now, spending, upgrades=(), opponent_id=None, policy=Policy()):
    """Choose a supported goal, then deploy/buy only its unmet core or transition.

    Refresh is considered only when no demanded offer is visible. It uses the
    observed price and explicit remaining spend/count/reserve budgets. Every
    result is advisory and must be recomputed after a transaction/new frame.
    """
    if not isinstance(spending, Spending) or not isinstance(plans, (tuple, list)) or len(plans) > 16:
        raise ValueError('bounded lineups and explicit Spending policy required')
    if not isinstance(upgrades, (tuple, list)) or len(upgrades) > 16:
        raise ValueError('bounded sourced upgrade rules required')
    unknowns = set(); refs = set(); source_kinds = set(); rejected = []; fields = {item.field.key: item for item in state.fields}

    def source(value):
        if (not isinstance(value, Source) or value.kind not in ('screen_recognition', 'reviewed_rule', 'manual_annotation', 'synthetic')
                or (value.kind == 'synthetic' and not policy.allow_test_rules)):
            raise ValueError('explicit supported source required; synthetic plans need opt-in')
        refs.add(value.reference); source_kinds.add(value.kind)

    def get(key):
        item = fields.get(key)
        reasons = _evidence_reasons(item, state, now, policy, 'self.' + key)
        if reasons:
            unknowns.update(reasons); return None
        source(item.source); return item.field.value

    snapshots = opponent_snapshots(state, now=now, policy=policy)
    opponent = next((row for row in snapshots if row['opponent_id'] == opponent_id and row['usable']), None)

    def output(action='hold', reasons=(), **extra):
        return {'schema_version': 'lineup-demand-advice/1', 'action': action, 'reasons': list(reasons),
                'unknowns': sorted(unknowns), 'evidence_refs': sorted(refs), 'rejected_plans': rejected,
                'data_kind': 'synthetic' if 'synthetic' in source_kinds else 'evidence_based_advisory',
                'opponent_snapshots': snapshots, 'match_id': state.match_id, 'state_version': state.state_version,
                'ban_version': state.ban_version, 'expires_at': (now+timedelta(seconds=policy.advice_ttl_seconds)).isoformat(),
                'execution_allowed': False, 'strength_estimate': None, **extra}

    if (state.lifecycle != 'active' or state.last_seen is None or state.phase not in ('preparation', 'purchase_enabled')
            or not 0 <= (now-state.last_seen).total_seconds() <= policy.max_state_age_seconds
            or state.context_confidence is None or state.context_confidence < policy.min_confidence):
        return output(reasons=['current_preparation_context_unknown'])
    bans = state.ban_evidence
    if bans is None or bans.field.status != 'observed' or bans.field.confidence is None or bans.field.confidence < .8:
        return output(reasons=['current_match_bans_unknown'])
    source(bans.source)
    zones = [get(key) for key in ('board_ids', 'hand_ids', 'offer_ids')]
    if any(not isinstance(zone, tuple) or len(zone) > 32 for zone in zones):
        return output(reasons=['board_hand_or_shop_coverage_unknown'])
    board, hand, offers = zones
    if len(set(board+hand+offers)) != len(board+hand+offers):
        return output(reasons=['distinct_instance_ids_required'])
    heroes = {uid: get('hero:' + uid) for uid in board+hand+offers}
    if any(not isinstance(heroes[uid], str) for uid in board+hand):
        return output(reasons=['resolved_owned_unit_identities_required'])
    owned = Counter(heroes[uid] for uid in board+hand); deployed = Counter(heroes[uid] for uid in board)
    capacity = get('capacity'); free_hand = get('free_hand')
    if type(capacity) is not int or not len(board) <= capacity <= 32:
        return output(reasons=['current_capacity_unknown_or_inconsistent'])
    credits = get('credits'); currency = get('currency_id')
    ranked = []
    for index, plan in enumerate(plans):
        source(plan.source)
        for target in plan.targets: source(target.source)
        if state.confirmed_bans:
            mapping = plan.ban_mapping_source
            if mapping is None or mapping.kind not in ('reviewed_rule', 'synthetic'):
                rejected.append({'lineup_id': plan.lineup_id, 'reasons': ['ban_to_target_mapping_unknown']}); continue
            source(mapping)
        blocked = [t.hero_id for t in plan.targets if t.role == 'core' and set(t.ban_tags) & set(state.confirmed_bans)]
        if blocked or sum(t.count for t in plan.targets if t.role == 'core') > capacity:
            rejected.append({'lineup_id': plan.lineup_id, 'reasons': ['core_banned' if blocked else 'target_exceeds_capacity'], 'heroes': blocked}); continue
        if plan.chess_player_id is not None and get('selected_chess_player_id') != plan.chess_player_id:
            rejected.append({'lineup_id': plan.lineup_id, 'reasons': ['requested_chess_player_not_observed']}); continue
        bonuses = Counter(); matched = []; uncertain = []
        for affinity in plan.affinities:
            source(affinity.source); values = []
            if affinity.source.kind not in ('reviewed_rule', 'synthetic'):
                uncertain.append(affinity.affinity_id); continue
            for path, expected in affinity.conditions:
                scope, key = path.split('.', 1)
                value = get(key) if scope == 'self' else (opponent['fields'].get(key) if opponent else None)
                if value is None or (scope == 'opponent' and isinstance(value, tuple) and expected not in value
                                     and opponent['coverage'] != 'full'):
                    values.append(None)
                else: values.append(expected in value if isinstance(value, tuple) else value == expected)
            if all(value is True for value in values):
                matched.append(affinity.affinity_id)
                for hero in affinity.hero_ids: bonuses[hero] += affinity.need_bonus
            elif any(value is None for value in values): uncertain.append(affinity.affinity_id)
        core = [t for t in plan.targets if t.role == 'core']
        coverage = sum(min(owned[t.hero_id], t.count)*t.priority for t in core)
        available_cash = max(0, credits-spending.reserve-spending.level_reserve-spending.upgrade_reserve) if type(credits) is int else 0
        reachable = 0
        for target in sorted(core, key=lambda t: -t.priority):
            missing = max(0, target.count-owned[target.hero_id]); prices = []
            for uid in offers:
                if heroes[uid] != target.hero_id: continue
                price = get('price:' + uid)
                if type(price) is int and price >= 0 and isinstance(currency, str) and get('currency:' + uid) == currency:
                    prices.append(price)
            for price in sorted(prices)[:missing]:
                if price <= available_cash:
                    available_cash -= price; reachable += target.priority
        fit = coverage+reachable+sum(bonuses[t.hero_id] for t in core)
        ranked.append((fit, coverage, -index, plan, bonuses, matched, uncertain))
    if not ranked:
        return output(reasons=['no_supported_lineup_targets'])
    ranked.sort(key=lambda row: row[:3], reverse=True)
    _, _, _, selected, bonuses, matched, uncertain = ranked[0]
    gaps = []; demands = {}; opportunities = []
    for target in selected.targets:
        if set(target.ban_tags) & set(state.confirmed_bans): continue
        missing = max(0, target.count-owned[target.hero_id])
        if target.role == 'transition' and not any(
                owned[t.hero_id] < t.count for t in selected.targets if t.hero_id in target.replaces): continue
        if missing: demands[(target.hero_id, None)] = (target, missing, 'composition')
        if target.role == 'core':
            rules = [rule for rule in upgrades if rule.hero_id == target.hero_id]
            if target.desired_star is None:
                if owned[target.hero_id]: unknowns.add('star_goal_unknown:' + target.hero_id)
                continue
            if not rules and owned[target.hero_id]: unknowns.add('upgrade_rule_unknown:' + target.hero_id)
            for rule in rules:
                source(rule.source)
                if rule.output_star > target.desired_star: continue
                if rule.source.kind not in ('reviewed_rule', 'synthetic'):
                    unknowns.add('upgrade_rule_not_ui_verified:' + target.hero_id); continue
                stars = [get('star:' + uid) for uid in board+hand if heroes[uid] == target.hero_id]
                if any(type(star) is not int for star in stars): continue
                if any(star >= rule.output_star for star in stars): continue
                remaining = max(0, rule.copies_required-stars.count(rule.input_star))
                gaps.append({'hero_id': target.hero_id, 'input_star': rule.input_star, 'missing_copies': remaining,
                             'source_reference': rule.source.reference, 'total_future_copy_cost': None})
                if remaining: demands[(target.hero_id, rule.input_star)] = (target, remaining, 'upgrade')
                else: opportunities.append({'hero_id': target.hero_id, 'reason': 'reviewed_upgrade_set_complete', 'execution_allowed': False})
    common = {'selected_lineup': selected.lineup_id, 'lineup_ranking': [
        {'lineup_id': row[3].lineup_id, 'fit_score': row[0], 'owned_coverage': row[1],
         'matched_affinities': row[5], 'unknown_affinities': row[6]} for row in ranked],
        'upgrade_gaps': gaps, 'upgrade_opportunities': opportunities,
        'targets': [{'hero_id': t.hero_id, 'role': t.role, 'count': t.count, 'desired_star': t.desired_star,
                     'source_reference': t.source.reference} for t in selected.targets],
        'demands': [{'hero_id': hero, 'input_star': star, 'role': t.role, 'missing': count,
                     'desired_star': t.desired_star,
                     'need_score': t.priority+bonuses[hero], 'kind': kind}
                    for (hero, star), (t, count, kind) in demands.items()],
        'pivot_candidates': [{'lineup_id': row[3].lineup_id,
                              'retain_hero_ids': sorted({heroes[uid] for uid in board} & {t.hero_id for t in row[3].targets if t.role == 'core'}),
                              'missing_hero_ids': [t.hero_id for t in row[3].targets if t.role == 'core' and owned[t.hero_id] < t.count],
                              'switch_cost': None} for row in ranked],
        'scoring_scope': 'ordinal_target_fit_not_combat_strength', 'policy_reference': spending.reference}
    odds = {}
    for key in fields:
        if key.startswith('shop_odds_percent:'):
            value = get(key)
            if number(value) and 0 <= value <= 100: odds[key.split(':', 1)[1]] = value
    common['shop_probability_evidence'] = {'observed_quality_percent': odds, 'individual_hero_probability': None,
                                           'future_level_probability': None}
    # Fill owned target cards first; never deploy an arbitrary filler.
    for role in ('core',):
        eligible = [uid for uid in hand for target in selected.targets if target.role == role
                    and target.hero_id == heroes[uid] and deployed[target.hero_id] < target.count
                    and not set(target.ban_tags) & set(state.confirmed_bans)]
        if eligible and len(board) < capacity:
            return output('deploy', ['owned_core_fills_selected_lineup'], unit_id=eligible[0], hero_id=heroes[eligible[0]], **common)
    needed = []; rejected_offers = []
    for uid in offers:
        matching = [(target, count, kind, star) for (hero, star), (target, count, kind) in demands.items()
                    if hero == heroes[uid] and (star is None or get('star:' + uid) == star)]
        if not matching:
            rejected_offers.append({'offer_id': uid, 'reason': 'identity_unknown' if heroes[uid] is None else 'not_needed_for_selected_lineup'}); continue
        target, count, kind, star = max(matching, key=lambda row: (row[0].role == 'core', row[2] == 'composition', row[1] == 1))
        price = get('price:' + uid)
        needed.append({'offer_id': uid, 'hero_id': heroes[uid], 'role': target.role, 'need_kind': kind,
                       'missing_copies': count, 'completes_upgrade': kind == 'upgrade' and count == 1,
                       'need_score': target.priority+bonuses[target.hero_id], 'effective_price': price,
                       'currency_id': get('currency:' + uid)})
    needed.sort(key=lambda row: (row['role'] == 'core', row['need_kind'] == 'composition', row['completes_upgrade'], row['need_score']), reverse=True)
    common.update(needed_offers=needed, rejected_offers=rejected_offers)
    for offer in needed:
        protected = spending.reserve + spending.level_reserve + (0 if offer['need_kind'] == 'upgrade' else spending.upgrade_reserve)
        price = offer['effective_price']
        if (type(credits) is int and type(price) is int and price >= 0 and isinstance(currency, str)
                and offer['currency_id'] == currency and credits-price >= protected and type(free_hand) is int and free_hand > 0):
            return output('buy', ['needed_target_affordable_with_declared_reserve'], offer=offer, remaining_credits=credits-price, **common)
    # A named transition is permitted only while its declared core replacement is missing.
    if len(board) < capacity:
        for uid in hand:
            target = next((t for t in selected.targets if t.hero_id == heroes[uid] and t.role == 'transition'), None)
            if (target and deployed[target.hero_id] < target.count
                    and not set(target.ban_tags) & set(state.confirmed_bans)
                    and any(owned[t.hero_id] < t.count for t in selected.targets if t.hero_id in target.replaces)):
                return output('deploy', ['explicit_transition_fills_temporary_role'], unit_id=uid, hero_id=target.hero_id,
                              replaces=list(target.replaces), **common)
    if needed:
        return output(reasons=['needed_offer_visible_hold_for_cost_space_or_reserve'], **common)
    if not demands:
        return output(reasons=['selected_lineup_has_no_supported_unmet_need'], **common)
    if any(heroes[uid] is None for uid in offers):
        return output(reasons=['unresolved_shop_card_might_be_needed_no_blind_refresh'], **common)
    level = get('player_level')
    minimum = selected.search_min_level
    common['level_policy'] = {'player_level': level, 'search_min_level': minimum, 'source_reference': selected.source.reference,
                              'interpretation': 'declared_search_preference_not_shop_probability_or_unit_star'}
    if minimum is None or type(level) is not int:
        return output(reasons=['search_level_preference_or_current_level_unknown'], **common)
    if level < minimum:
        quote = get('level_up_cost'); target_level = get('level_up_target_level')
        if (type(quote) is int and quote >= 0 and type(target_level) is int and level < target_level <= minimum
                and type(credits) is int and isinstance(currency, str) and get('level_up_currency_id') == currency
                and credits-quote >= spending.reserve+spending.upgrade_reserve):
            return output('level_up', ['below_declared_search_level_use_observed_upgrade_quote'],
                          level_up_cost=quote, target_player_level=target_level, remaining_credits=credits-quote, **common)
        return output(reasons=['below_search_level_protect_leveling_funds_or_observe_quote'], **common)
    refresh_cost = get('refresh_cost')
    if (type(credits) is not int or type(refresh_cost) is not int or refresh_cost < 0
            or not isinstance(currency, str) or get('refresh_currency_id') != currency):
        return output(reasons=['refresh_price_or_currency_unknown'], **common)
    available = max(0, credits-spending.reserve-spending.upgrade_reserve-spending.level_reserve)
    spend_left = max(0, spending.refresh_spend_cap-spending.refresh_spent)
    count_left = max(0, spending.refresh_count_cap-spending.refresh_count)
    permitted = count_left if refresh_cost == 0 else min(count_left, available//refresh_cost, spend_left//refresh_cost)
    refresh = {'observed_cost': refresh_cost, 'remaining_spend_cap': spend_left, 'remaining_count_cap': count_left,
               'protected_credits': spending.reserve+spending.upgrade_reserve+spending.level_reserve, 'max_additional_refreshes': permitted,
               'expected_card_value': None, 'pool_probabilities': None}
    if permitted and type(free_hand) is int and free_hand > 0:
        return output('refresh', ['no_demanded_shop_card_search_within_explicit_budget'], refresh_budget=refresh, **common)
    return output(reasons=['refresh_budget_or_hand_space_exhausted'], refresh_budget=refresh, **common)
