"""One advised transaction through caller-owned guarded callbacks; no native APIs."""
from copy import deepcopy
import uuid

from strategy.codec import timestamp as stamp
from runtime.surface_gate import _frame, _object, _score


def values(frame):
    """Unknown never becomes zero; reject duplicate/conflicting field records."""
    if not _frame(frame): raise ValueError('bound_economy_frame_required')
    batch = _object(frame.get('strategy_batch')); bound = _object(batch.get('frame'))
    if (bound.get('sha256') != frame['sha256'] or bound.get('observed_at') != frame.get('captured_at')
            or batch.get('data_kind') != 'screen_recognition' or bound.get('time_basis') != 'synchronous_visible_capture'
            or frame.get('source_capture_reused') is True):
        raise ValueError('current_live_projection_required')
    rows = batch.get('own_fields'); result = {}; seen = set()
    if not isinstance(rows, list) or len(rows) > 512: raise ValueError('bounded_economy_fields_required')
    for row in rows:
        if not isinstance(row, dict) or not isinstance(row.get('key'), str) or row['key'] in seen:
            raise ValueError('unique_economy_fields_required')
        seen.add(row['key'])
        if row.get('status') == 'observed' and row.get('value') is not None and _score(row.get('confidence'), .8):
            result[row['key']] = row['value']
    return result


def prepare_action(frame, advice, *, now):
    action = _object(advice).get('action'); reasons = []
    if action not in ('refresh', 'level_up'):
        return {'ready': False, 'reasons': ['not_refresh_or_level_up_advice']}
    try:
        own = values(frame); batch = frame['strategy_batch']; context = batch['context']
        captured = stamp(frame['captured_at']); clock = stamp(now)
        if (advice.get('controller_frame_sha256') != frame['sha256'] or advice.get('source_mode') != 'live_capture'
                or advice.get('data_kind') == 'synthetic' or advice.get('match_id') != context['match_id']
                or context.get('phase') != 'preparation' or type(context.get('round')) is not int
                or not 0 <= (clock-captured).total_seconds() <= 5
                or not captured <= stamp(advice['decision_at']) <= clock < stamp(advice['expires_at'])):
            reasons.append('fresh_live_advice_context_required')
        binding = _object(_object(_object(frame.get('strategy_ui_bindings')).get('actions')).get(action))
        target = binding.get('target'); rect = binding.get('rect')
        if (binding.get('status') != 'observed' or binding.get('frame_sha256') != frame['sha256']
                or binding.get('identity_version') != frame['identity']['identity_version']
                or binding.get('geometry_version') != frame['identity']['geometry_version']
                or binding.get('label_verified') is not True or binding.get('enabled_verified') is not True
                or not _score(binding.get('confidence'), .97)
                or not isinstance(target, list) or len(target) != 2 or any(type(v) is not int for v in target)
                or not isinstance(rect, list) or len(rect) != 4 or any(type(v) is not int for v in rect)
                or not 0 <= rect[0] <= target[0] < rect[0]+rect[2] <= 1450
                or not 0 <= rect[1] <= target[1] < rect[1]+rect[3] <= 869):
            reasons.append('current_enabled_UI_target_unverified')
        quote = own.get(action+'_cost'); credits = own.get('credits'); currency = own.get('currency_id')
        expected = _object(advice.get('refresh_budget')).get('observed_cost') if action == 'refresh' else advice.get('level_up_cost')
        if (type(quote) is not int or quote < 0 or type(expected) is not int or quote != expected
                or type(credits) is not int or credits < quote or not isinstance(currency, str) or not currency
                or own.get(action+'_currency_id') != currency):
            reasons.append('observed_quote_currency_or_balance_mismatch')
        if action == 'refresh':
            budget = _object(advice.get('refresh_budget')); ids = own.get('offer_ids')
            if (not isinstance(ids, (list, tuple)) or not ids or len(set(ids)) != len(ids)
                    or any(not isinstance(own.get('hero:'+uid), str) or not own['hero:'+uid] for uid in ids)):
                reasons.append('resolved_current_shop_required')
            if (not advice.get('demands') or advice.get('needed_offers')
                    or any(type(budget.get(key)) is not int or budget[key] < 0 for key in
                           ('max_additional_refreshes','remaining_spend_cap','remaining_count_cap','protected_credits'))
                    or budget.get('max_additional_refreshes', 0) < 1 or budget.get('remaining_count_cap', 0) < 1
                    or (type(quote) is int and budget.get('remaining_spend_cap', -1) < quote)
                    or (type(credits) is int and type(quote) is int and credits-quote < budget.get('protected_credits', 0))):
                reasons.append('lineup_demand_or_refresh_budget_not_satisfied')
        else:
            level = own.get('player_level'); target_level = own.get('level_up_target_level')
            if (type(level) is not int or type(target_level) is not int or not level < target_level
                    or target_level != advice.get('target_player_level')
                    or type(credits) is not int or type(quote) is not int or advice.get('remaining_credits') != credits-quote):
                reasons.append('actual_player_level_quote_not_proven')
    except (KeyError, ValueError, TypeError, AttributeError):
        return {'ready': False, 'reasons': ['invalid_economy_frame_or_advice'], 'execution_allowed': False}
    if reasons: return {'ready': False, 'reasons': reasons, 'execution_allowed': False}
    return {'ready': True, 'action': action, 'target': list(target), 'before_frame': frame['sha256'],
            'before_time': frame['captured_at'], 'prepared_at': now, 'expires_at': advice['expires_at'],
            'identity_version': frame['identity']['identity_version'], 'geometry_version': frame['identity']['geometry_version'],
            'match_id': context['match_id'], 'round': context['round'], 'before': deepcopy(own), 'quote': quote,
            'reasons': [], 'execution_allowed': False}


def verify_native_result(intent, frame, *, native_result, now, drag=False):
    """Shared raw submission/release and current-context check; no sent-only proof."""
    reasons = []; result = _object(native_result)
    try:
        values(frame); context = frame['strategy_batch']['context']
        started = stamp(result['started_at']); released = stamp(result['released_at'])
        captured = stamp(frame['captured_at']); clock = stamp(now)
        submission = _object(result.get('submission')); native = _object(result.get('native_summary'))
        if (result.get('action') != intent['action'] or result.get('before_sha256') != intent['before_frame']
                or native.get('held') is not False or native.get('release_confirmed') is not True or native.get('cleanup_errors') != []
                or type(native.get('down_count')) is not int or native['down_count'] != 2
                or type(native.get('owned_up_count')) is not int or native['owned_up_count'] != 1
                or submission.get('sent') is not True or submission.get('owned_release_confirmed') is not True
                or submission.get('cleanup_errors') != [] or type(submission.get('action_budget_remaining')) is not int
                or submission['action_budget_remaining'] != 0 or submission.get('submission_outcome') !=
                   ('drag_path_submitted_requires_visual_verification' if drag else 'down_and_owned_up_submitted')):
            reasons.append('clean_owned_native_release_unproven')
        if drag:
            moves = result.get('drag_moves')
            if (not isinstance(moves, list) or len(moves) != 10
                    or any(not isinstance(row, dict) or row.get('step') != i+1 or type(row.get('raw_return')) is not int
                           or row['raw_return'] != 1 for i, row in enumerate(moves))):
                reasons.append('complete_owned_drag_path_unproven')
        if (not stamp(intent['before_time']) <= stamp(intent['prepared_at']) <= stamp(intent.get('submitted_at', intent['prepared_at'])) <= started
                or not started < released < captured <= clock or started >= stamp(intent['expires_at'])
                or not 0 <= (started-stamp(intent['before_time'])).total_seconds() <= 5
                or not 0 < (released-started).total_seconds() <= 2
                or not 0 <= (clock-captured).total_seconds() <= 8 or not 0 < (captured-started).total_seconds() <= 8):
            reasons.append('postcondition_must_be_fresh_and_follow_release')
        if (frame['sha256'] == intent['before_frame']
                or frame['identity']['identity_version'] != intent['identity_version']
                or frame['identity']['geometry_version'] != intent['geometry_version']
                or context.get('match_id') != intent['match_id'] or context.get('round') != intent['round']
                or context.get('phase') != 'preparation'):
            reasons.append('same_game_geometry_round_and_preparation_required')
    except (KeyError, ValueError, TypeError, AttributeError):
        reasons.append('invalid_native_postcondition')
    return reasons


def verify_action(intent, frame, *, native_result, now):
    reasons = verify_native_result(intent, frame, native_result=native_result, now=now); receipt = {}
    try:
        own = values(frame); before = intent['before']
        balance = own.get('credits')
        resource_ok = (type(balance) is int and own.get('currency_id') == before['currency_id']
                       and before['credits']-balance == intent['quote'])
        if not resource_ok: reasons.append('exact_resource_delta_unverified')
        receipt = {'before_credits': before['credits'], 'after_credits': balance, 'quoted_cost': intent['quote'],
                   'resource_delta_verified': resource_ok, 'before_sha256': intent['before_frame'],
                   'after_sha256': frame['sha256'], 'captured_at': frame['captured_at']}
        if intent['action'] == 'refresh':
            ids = own.get('offer_ids'); old = before['offer_ids']
            resolved = (isinstance(ids, (list, tuple)) and list(ids) == list(old)
                        and all(isinstance(own.get('hero:'+uid), str) and own['hero:'+uid] for uid in ids))
            changed = resolved and any(own['hero:'+uid] != before['hero:'+uid] for uid in ids)
            receipt['new_shop_verified'] = bool(changed)
            if not changed: reasons.append('changed_resolved_shop_unproven_no_retry')
        else:
            target = before['level_up_target_level']; level = own.get('player_level')
            gained = type(level) is int and level == target and level > before['player_level']
            receipt.update(before_player_level=before['player_level'], after_player_level=level,
                           target_player_level=target, player_level_gain_verified=gained)
            if not gained: reasons.append('quoted_player_level_gain_unverified_no_retry')
    except (KeyError, ValueError, TypeError, AttributeError):
        reasons.append('invalid_independent_economy_postcondition')
    return {'verified': not reasons, 'game_postcondition_verified': not reasons, 'reasons': reasons,
            'receipt': receipt, 'execution_allowed': False, 'blind_retry_allowed': False}


class EconomyActionHandler:
    """Observe/recompute, latch one attempt, call the guarded port, then verify.

    dispatch(frame, intent) must use the existing native ownership guard and
    return actual submission/release receipts. This class never opens a port.
    """
    def __init__(self, bridge): self.bridge = bridge

    def run_one(self, *, observe, dispatch, clock):
        if self.bridge.pending_transaction is not None:
            return {'status': 'pending_no_retry', 'execution_allowed': False}
        before = observe()
        advice = self.bridge.decide(before.get('strategy_batch'), decision_at=clock(), current_frame_sha256=before['sha256'])
        intent = prepare_action(before, advice, now=clock())
        if not intent['ready']: return dict(intent, status='not_submitted')
        transaction_id = uuid.uuid4().hex
        self.bridge.submitted(transaction_id, advice, submitted_at=clock(), before_frame=before)
        try:
            native_result = dispatch(deepcopy(before), deepcopy(self.bridge.pending_transaction['intent']))
            after = observe()
            return self.bridge.complete_economy(transaction_id, after, native_result, now=clock())
        except Exception as error:
            return {'status': 'submitted_outcome_uncertain_no_retry', 'reason': type(error).__name__,
                    'execution_allowed': False, 'blind_retry_allowed': False}
