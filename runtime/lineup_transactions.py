"""Prepare one Advisor-owned buy/deploy and verify actual physical slot changes."""
from copy import deepcopy

from runtime.economy_actions import values, verify_native_result, stamp
from runtime.surface_gate import _score
from strategy.state_projection import bound_record


def target_binding(frame, binding):
    row = bound_record(frame, binding)
    if not row or not _score(row.get('confidence'), .97):
        raise ValueError('current_interactive_slot_binding_required')
    rect, target = row.get('rect', row.get('bounds')), row.get('target')
    if target is None and isinstance(rect, list) and len(rect) == 4 and all(type(x) is int for x in rect):
        target = [rect[0]+rect[2]//2, rect[1]+rect[3]//2]
    if (not isinstance(rect, list) or len(rect) != 4 or any(type(x) is not int for x in rect)
            or not isinstance(target, list) or len(target) != 2 or any(type(x) is not int for x in target)
            or not 0 <= rect[0] <= target[0] < rect[0]+rect[2] <= 1450
            or not 0 <= rect[1] <= target[1] < rect[1]+rect[3] <= 869):
        raise ValueError('actual_bounded_UI_slot_required')
    return list(target)


def zone_ids(own, zone):
    ids = own.get(zone+'_ids')
    if (not isinstance(ids, (list, tuple)) or len(ids) > 32 or len(set(ids)) != len(ids)
            or any(not isinstance(uid, str) or not isinstance(own.get('hero:'+uid), str)
                   or not own['hero:'+uid] for uid in ids)):
        raise ValueError('complete_resolved_'+zone+'_required')
    return list(ids)


def prepare_owned(frame, advice, *, now):
    action = advice.get('action')
    try:
        if action not in ('buy', 'deploy'): raise ValueError('not_buy_or_deploy')
        own = values(frame); context = frame['strategy_batch']['context']; clock = stamp(now)
        if (advice.get('source_mode') != 'live_capture' or advice.get('controller_frame_sha256') != frame['sha256']
                or advice.get('match_id') != context['match_id'] or context.get('phase') != 'preparation'
                or type(context.get('round')) is not int
                or not stamp(frame['captured_at']) <= stamp(advice['decision_at']) <= clock < stamp(advice['expires_at'])
                or not 0 <= (clock-stamp(frame['captured_at'])).total_seconds() <= 5):
            raise ValueError('fresh_current_Advisor_context_required')
        board, hand = zone_ids(own, 'board'), zone_ids(own, 'hand')
        if set(board) & set(hand): raise ValueError('distinct_physical_zones_required')
        credits, currency = own.get('credits'), own.get('currency_id')
        if type(credits) is not int or credits < 0 or not isinstance(currency, str) or not currency:
            raise ValueError('current_resource_required')
        bindings = frame.get('strategy_ui_bindings', {})
        extra = {}
        if action == 'buy':
            offer = advice['offer']; uid = offer['offer_id']; hero = offer['hero_id']; quote = offer['effective_price']
            if (uid not in own.get('offer_ids', ()) or own.get('hero:'+uid) != hero
                    or own.get('price:'+uid) != quote or own.get('currency:'+uid) != currency
                    or offer.get('currency_id') != currency or type(quote) is not int or not 0 <= quote <= credits
                    or advice.get('remaining_credits') != credits-quote
                    or not any(row == offer for row in advice.get('needed_offers', []))):
                raise ValueError('exact_advised_demand_offer_required')
            binding = bindings.get('offers', {}).get(uid, {})
            if binding.get('purchasable_verified') is not True or binding.get('hero_id') != hero:
                raise ValueError('current_purchasable_offer_required')
            target = target_binding(frame, binding)
            zone = bound_record(frame, frame.get('recognized_zones', {}).get('hand'))
            if not zone or zone.get('coverage') != 'full' or zone.get('overflow_checked') is not True:
                raise ValueError('complete_current_hand_slots_required')
            empty = ['hand:'+row['slot_id'] for row in zone['slots']
                     if row.get('kind') == 'empty' and row.get('classification_verified') is True
                     and row.get('legal') is True]
            if not empty or type(own.get('free_hand')) is not int or own['free_hand'] < 1:
                raise ValueError('positive_legal_empty_hand_slot_required')
            extra.update(offer_id=uid, hero_id=hero, empty_hand_ids=empty)
        else:
            uid, hero = advice['unit_id'], advice['hero_id']; quote = 0
            if (uid not in hand or own.get('hero:'+uid) != hero or type(own.get('capacity')) is not int
                    or not len(board) < own['capacity']):
                raise ValueError('advised_owned_unit_and_current_capacity_required')
            binding = bindings.get('hand', {}).get(uid, {})
            if binding.get('hero_id') != hero: raise ValueError('physical_hand_instance_required')
            start = target_binding(frame, binding)
            destination = bindings.get('deployment', {})
            slot = destination.get('board_slot_id')
            if (destination.get('empty_verified') is not True or destination.get('own_board_verified') is not True
                    or destination.get('legal_verified') is not True or not isinstance(slot, str)
                    or not slot.startswith('board:') or slot in board):
                raise ValueError('recognized_empty_destination_required')
            target = target_binding(frame, destination)
            extra.update(unit_id=uid, hero_id=hero, start=start, board_slot_id=slot)
        return dict(ready=True, action=action, target=target, before_frame=frame['sha256'],
                    before_time=frame['captured_at'], prepared_at=now, expires_at=advice['expires_at'],
                    identity_version=frame['identity']['identity_version'], geometry_version=frame['identity']['geometry_version'],
                    match_id=context['match_id'], round=context['round'], before=deepcopy(own), quote=quote,
                    reasons=[], execution_allowed=False, **extra)
    except (KeyError, ValueError, TypeError, AttributeError) as error:
        return dict(ready=False, reasons=[str(error)], execution_allowed=False)


def verify_owned(intent, frame, *, native_result, now):
    reasons = verify_native_result(intent, frame, native_result=native_result, now=now, drag=intent['action']=='deploy')
    receipt = {}
    try:
        own = values(frame); before = intent['before']
        old_board, old_hand = zone_ids(before, 'board'), zone_ids(before, 'hand')
        board, hand = zone_ids(own, 'board'), zone_ids(own, 'hand')
        resource = (own.get('currency_id') == before['currency_id'] and type(own.get('credits')) is int
                    and before['credits']-own['credits'] == intent['quote'])
        if not resource: reasons.append('exact_resource_delta_unverified')
        def same(ids): return all(own.get('hero:'+uid) == before['hero:'+uid] for uid in ids)
        if intent['action'] == 'buy':
            added = set(hand)-set(old_hand)
            physical = (set(board)==set(old_board) and same(old_board) and set(old_hand).issubset(hand)
                        and same(old_hand) and len(added)==1 and added.issubset(intent['empty_hand_ids'])
                        and own.get('hero:'+next(iter(added)))==intent['hero_id'])
        else:
            physical = (set(hand)==set(old_hand)-{intent['unit_id']} and same(hand)
                        and set(board)==set(old_board)|{intent['board_slot_id']} and same(old_board)
                        and own.get('hero:'+intent['board_slot_id'])==intent['hero_id'])
        if not physical: reasons.append('exact_physical_unit_transition_unverified')
        receipt = dict(before_sha256=intent['before_frame'], after_sha256=frame['sha256'],
                       captured_at=frame['captured_at'], resource_delta_verified=resource,
                       physical_unit_transition_verified=physical, quoted_cost=intent['quote'])
    except (KeyError, ValueError, TypeError, AttributeError):
        reasons.append('independent_owned_postcondition_unavailable')
    return dict(verified=not reasons, game_postcondition_verified=not reasons, reasons=reasons,
                receipt=receipt, execution_allowed=False, blind_retry_allowed=False)
