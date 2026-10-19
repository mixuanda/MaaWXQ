"""V41 transport/receipt adapter for the integrator's existing lineup Advisor.

No input imports and no second scoring policy. Recognition batches retain their
capture time; card quality, unit upgrade level and player level remain separate.
"""
from copy import deepcopy
from datetime import datetime, timedelta
import json
from pathlib import Path
from strategy.advisor import Advisor
from strategy import lineup as lineup_api
from strategy.contracts import Source
from strategy.recognition import ingest_frame


CURRENT_FIELDS = (
    'board_ids', 'hand_ids', 'offer_ids', 'capacity', 'free_hand', 'credits',
    'currency_id', 'player_level', 'refresh_cost', 'refresh_currency_id',
    'level_up_cost', 'level_up_target_level', 'level_up_currency_id',
)
SPENDING_FIELDS = (
    'reserve', 'upgrade_reserve', 'level_reserve', 'refresh_spend_cap',
    'refresh_count_cap',
)


def timestamp(value):
    at = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if at.tzinfo is None:
        raise ValueError('timezone_required')
    return at


def hold(reason, **extra):
    return dict(schema_version='lineup-demand-advice/1', action='hold',
                reasons=[reason], execution_allowed=False, **extra)


def load_policy(path):
    data = json.loads(Path(path).read_text(encoding='utf-8-sig'))
    return validate_policy(data)


def validate_policy(data):
    if data.get('schema_version') != 'v41-lineup-policy/1':
        raise ValueError('lineup_policy_schema_unknown')
    if data.get('recommendation_provider') != 'in_game_lingbao':
        raise ValueError('explicit_in_game_recommendation_source_required')
    if not data.get('plans'):
        raise ValueError('observed_lingbao_lineups_missing')
    # These are declared policy budgets, not asserted game costs or interest.
    spending = data.get('spending', {})
    if spending.get('budget_scope') != 'match':
        raise ValueError('refresh_budget_must_cover_whole_match')
    if any(type(spending.get(k)) is not int or spending[k] < 0 for k in SPENDING_FIELDS):
        raise ValueError('explicit_level_reserve_and_refresh_caps_required')
    if not spending.get('reference'):
        raise ValueError('spending_policy_reference_required')
    return data


class LineupBridge:
    def __init__(self, policy, *, allow_test_rules=False):
        self.policy = deepcopy(validate_policy(policy))
        self.allow_test_rules = allow_test_rules
        self.api = lineup_api
        self.Source = Source
        self.ingest_frame = ingest_frame
        self.advisor = Advisor({
            'schema_version': 'strategy-session/1', 'engine': 'reviewed_rules',
            'rule_data': {'schema_version': '1.0', 'domain': 'gameplay', 'rules': []},
        }, allow_test_rules=allow_test_rules)
        self.plans = tuple(self._plan(raw) for raw in policy['plans'])
        self.upgrades = tuple(self._upgrade(raw) for raw in policy.get('upgrades', []))
        self.refresh_spent = self.refresh_count = 0
        self.receipts = {}
        self.last_advice = None
        self.match_id = None
        self.awaiting_after = None
        self.pending_transaction = None

    @classmethod
    def from_file(cls, path):
        return cls(load_policy(path))

    def _source(self, raw):
        source = self.Source(**raw)
        allowed = ('screen_recognition', 'reviewed_rule', 'manual_annotation')
        if source.kind not in allowed and not (self.allow_test_rules and source.kind == 'synthetic'):
            raise ValueError('unsupported_lineup_fact_source')
        return source

    def _plan(self, raw):
        item = deepcopy(raw)
        item['source'] = self._source(item['source'])
        if item.get('ban_mapping_source') is not None:
            item['ban_mapping_source'] = self._source(item['ban_mapping_source'])
        targets = []
        for row in item['targets']:
            target = dict(row)
            target['source'] = self._source(target['source'])
            for key in ('replaces', 'ban_tags'):
                target[key] = tuple(target.get(key, ()))
            targets.append(self.api.Target(**target))
        item['targets'] = tuple(targets)
        affinities = []
        for row in item.get('affinities', []):
            affinity = dict(row)
            affinity['source'] = self._source(affinity['source'])
            affinity['conditions'] = tuple(tuple(x) for x in affinity['conditions'])
            affinity['hero_ids'] = tuple(affinity['hero_ids'])
            affinities.append(self.api.Affinity(**affinity))
        item['affinities'] = tuple(affinities)
        return self.api.Lineup(**item)

    def _upgrade(self, raw):
        # An OCR label "level" or user-spoken "star" is not a merge recipe.
        if self.policy.get('unit_upgrade_semantics_verified') is not True:
            raise ValueError('unit_upgrade_semantics_unverified')
        item = dict(raw)
        item['source'] = self._source(item['source'])
        return self.api.Upgrade(**item)

    def spending(self):
        policy = self.policy['spending']
        return self.api.Spending(policy['reference'],
            **{key: policy[key] for key in SPENDING_FIELDS},
            refresh_spent=self.refresh_spent, refresh_count=self.refresh_count)

    def decide(self, batch, *, decision_at, current_frame_sha256, source_mode='live_capture', opponent_id=None):
        """Consume the producer's existing recognition contract, without backfilling.

        Missing complete hand/shop identity coverage stays unknown. In particular,
        absence from the small template catalog cannot establish an empty hand.
        """
        if source_mode != 'live_capture':
            return hold('saved_projection_cannot_mutate_live_bridge')
        self.last_advice = None
        if self.pending_transaction is not None:
            return hold('submitted_transaction_postcondition_pending')
        if not batch:
            return hold('current_boardstate_recognition_batch_missing')
        data = deepcopy(batch)
        frame = data['frame']
        captured, at = timestamp(frame['observed_at']), timestamp(decision_at)
        if frame['sha256'] != current_frame_sha256:
            raise ValueError('strategy_frame_does_not_match_controller_frame')
        if source_mode == 'live_capture':
            if data['data_kind'] != 'screen_recognition' or frame['time_basis'] != 'synchronous_visible_capture':
                raise ValueError('saved_or_synthetic_frame_cannot_drive_live_advice')
            if not 0 <= (at-captured).total_seconds() <= 5:
                return hold('strategy_capture_not_current')
        elif source_mode != 'offline_replay':
            raise ValueError('explicit_source_mode_required')
        if self.awaiting_after is not None and captured <= self.awaiting_after:
            return hold('fresh_observation_after_transaction_required')
        match_id = data['context']['match_id']
        if self.match_id is not None and match_id != self.match_id:
            raise ValueError('create_new_bridge_for_new_match_no_budget_reset_in_place')
        self.match_id = match_id
        # The first actual batch starts state. Repeated frames never restart it.
        data['start_match'] = self.advisor.state.lifecycle != 'active'
        provided = {field['key'] for field in data['own_fields']}
        previously_current = {x.field.key for x in self.advisor.state.fields}
        for key in sorted((set(CURRENT_FIELDS) | previously_current) - provided):
            data['own_fields'].append(dict(key=key, status='unknown', value=None, confidence=None))
        receipt = self.ingest_frame(self.advisor, data, now=at)
        if receipt['blocking_gaps']:
            result = hold('recognition_pending', blocking_gaps=receipt['blocking_gaps'])
        else:
            result = self.advisor.advise_lineup(self.plans, decision_at=at,
                spending=self.spending(), upgrades=self.upgrades, opponent_id=opponent_id)
        result.update(controller_frame_sha256=current_frame_sha256,
                      source_mode=source_mode, decision_at=decision_at,
                      recommendation_provider=self.policy['recommendation_provider'])
        if result.get('expires_at') and source_mode == 'live_capture':
            result['expires_at'] = min(timestamp(result['expires_at']), captured+timedelta(seconds=5)).isoformat()
        self.last_advice = deepcopy(result)
        self.awaiting_after = None
        return result

    def submitted(self, transaction_id, advice, *, submitted_at, before_frame=None):
        """Receipt bookkeeping only. Caller still owns actual UI verification."""
        if self.pending_transaction is not None or transaction_id in self.receipts:
            raise ValueError('transaction_already_pending_or_recorded')
        if advice != self.last_advice or advice.get('action') not in ('buy', 'deploy', 'refresh', 'level_up'):
            raise ValueError('transaction_must_correspond_to_latest_advice')
        if advice.get('source_mode') != 'live_capture':
            raise ValueError('offline_advice_has_no_submission_path')
        at = timestamp(submitted_at)
        if not timestamp(advice['decision_at']) <= at <= timestamp(advice['expires_at']):
            raise ValueError('transaction_advice_expired')
        intent = None
        if advice['action'] in ('refresh', 'level_up'):
            from .economy_actions import prepare_action
            intent = prepare_action(before_frame, advice, now=submitted_at)
            if not intent['ready']:
                raise ValueError('economy_transaction_not_prepared:' + ','.join(intent['reasons']))
        self.pending_transaction = dict(id=transaction_id, advice=deepcopy(advice), submitted_at=submitted_at)
        self.pending_transaction['intent'] = intent
        if intent is not None:
            self.pending_transaction['intent']['submitted_at'] = submitted_at
        self.awaiting_after = at

    def completed(self, transaction_id, *, verified, receipt, observed_at):
        pending = self.pending_transaction
        if pending is None or pending['id'] != transaction_id:
            raise ValueError('transaction_receipt_not_pending')
        if not verified:
            # Keep pending. Neither a replay nor a fresh frame retries uncertainty.
            return hold('submitted_transaction_outcome_uncertain')
        raise ValueError('independent_postcondition_required_not_a_caller_verified_boolean')

    def complete_economy(self, transaction_id, after_frame, native_result, *, now):
        """Derive success from the new frame and clean release, never a sent flag."""
        from .economy_actions import verify_action
        pending = self.pending_transaction
        if pending is None or pending['id'] != transaction_id or pending.get('intent') is None:
            raise ValueError('prepared_economy_transaction_not_pending')
        result = verify_action(pending['intent'], after_frame, native_result=native_result, now=now)
        if not result['verified']:
            return dict(result, status='submitted_outcome_uncertain_no_retry')
        if pending['advice']['action'] == 'refresh':
            self.refresh_count += 1; self.refresh_spent += pending['intent']['quote']
        observed_at = after_frame['captured_at']
        self.receipts[transaction_id] = dict(pending, receipt=deepcopy(result['receipt']), observed_at=observed_at)
        self.pending_transaction = None
        self.awaiting_after = timestamp(observed_at)
        return dict(result, status='recorded', refresh_spent=self.refresh_spent, refresh_count=self.refresh_count)


def select_purchase(advice, offers):
    """Resolve Advisor's selected instance to one already-recognized UI slot."""
    if advice.get('action') != 'buy':
        return None
    selected = advice['offer']
    matches = [row for row in offers if row.get('offer_id') == selected['offer_id']
               and row.get('name') == selected['hero_id'] and row.get('price') == selected['effective_price']]
    if len(matches) != 1:
        raise ValueError('advised_offer_not_uniquely_bound_to_current_shop')
    return matches[0]
