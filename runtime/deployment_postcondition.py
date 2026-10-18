"""Pure, intent-bound evidence checks for the reviewed first-unit deployment.

No capture, window, inspection click or input API is opened here. Pixel and
ownership producers must bind their results to original screenshots. Saved
replay is the default and never reports a newly verified live game action.
"""
from copy import deepcopy
import hashlib
import json
import math
import uuid

from strategy.codec import timestamp


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'),
                                    ensure_ascii=False, allow_nan=False).encode('utf-8')).hexdigest()


def _sha(value):
    return isinstance(value, str) and len(value) == 64 and all(c in '0123456789abcdef' for c in value)


def _text(value):
    return isinstance(value, str) and 0 < len(value) <= 256 and value.strip().casefold() not in ('', 'unknown', '?')


def _number(value, low, high):
    return type(value) in (int, float) and math.isfinite(value) and low <= value <= high


def _integer(value, expected):
    return type(value) is int and value == expected


def _mode(source_mode):
    if source_mode not in ('saved_replay', 'live_capture'):
        raise ValueError('explicit_deployment_source_mode_required')


def _valid_intent(intent):
    if not isinstance(intent, dict):
        return False
    try:
        timestamp(intent['source_capture_utc'])
    except (KeyError, ValueError, TypeError, AttributeError):
        return False
    return (intent.get('schema') == 'deployment-intent/1'
            and all(_text(intent.get(key)) for key in ('intent_id', 'hero_id', 'match_id', 'identity_version', 'geometry_version'))
            and _sha(intent.get('source_frame_sha256'))
            and _sha(intent.get('shop_frame_sha256'))
            and type(intent.get('offer_slot')) is int and 0 <= intent['offer_slot'] <= 3
            and all(_integer(intent.get(key), value) for key, value in
                    [('source_hand_count', 3), ('source_board_count', 0), ('capacity', 5), ('submission_limit', 1)])
            and isinstance(intent.get('destination'), list)
            and len(intent['destination']) == 2
            and all(_integer(v, e) for v, e in zip(intent['destination'], (710, 555))))


def intent_from(frame, *, match_id, hero_id, shop_frame_sha256, offer_slot):
    """Bind a fresh 3-card/empty-5-capacity source to the actual purchased shop.

    The sole controller supplies the actual successful purchase and recognized
    source context. This constructor does not independently recognize that UI,
    authorize a drag or create a verified purchase result.
    """
    identity = frame['identity']
    if (identity['client']['width'], identity['client']['height']) != (1450, 869):
        raise ValueError('unsupported_deployment_geometry')
    intent = {'schema': 'deployment-intent/1', 'intent_id': str(uuid.uuid4()),
              'match_id': match_id, 'hero_id': hero_id,
              'source_frame_sha256': frame['sha256'], 'source_capture_utc': frame['captured_at'],
              'shop_frame_sha256': shop_frame_sha256,
              'offer_slot': offer_slot,
              'identity_version': identity['identity_version'], 'geometry_version': identity['geometry_version'],
              'source_hand_count': 3, 'source_board_count': 0, 'capacity': 5,
              'destination': [710, 555], 'submission_limit': 1}
    if not _valid_intent(intent):
        raise ValueError('invalid_deployment_intent')
    return intent


def frame_ref(frame):
    return {'sha256': frame['sha256'], 'captured_at': frame['captured_at'],
            'identity_version': frame['identity']['identity_version'],
            'geometry_version': frame['identity']['geometry_version']}


def bind_inspected_evidence(intent, post, identity, *, inspection_target, shop_frame_sha256,
                            source_mode='saved_replay'):
    """Bind exact pixel results from post-drag and selected-owned-unit frames.

    Inputs are original producer records: post.deployment_pixels contains hand
    removal/new-component measurements; identity.deployment_detail contains the
    purchased shop-art comparison. The selected-unit population and owner label
    must come from that same identity frame. This helper performs no inspection.
    """
    _mode(source_mode)
    if not _valid_intent(intent):
        raise ValueError('invalid_deployment_intent')
    for frame in (post, identity):
        if frame.get('source_mode', source_mode) != source_mode:
            raise ValueError('deployment_source_mode_mismatch')
        client = frame['identity']['client']
        if (client['width'], client['height']) != (1450, 869):
            raise ValueError('unsupported_deployment_geometry')
    pixels = post['deployment_pixels']
    art = identity['deployment_detail']
    evidence = {'intent_sha256': digest(intent), 'match_id': intent['match_id'], 'hero_id': intent['hero_id'],
                'source_mode': source_mode, 'post_frame': frame_ref(post), 'identity_frame': frame_ref(identity),
                'hand': deepcopy(pixels['hand']), 'new_unit': deepcopy(pixels['new_unit']),
                'board': dict(identity['detail_board'], before=0, after=1, capacity=5,
                              frame_sha256=identity['sha256'], source='unobscured_selected_owned_unit_frame'),
                'inspection_target': deepcopy(inspection_target),
                'unit': dict(art, hero_id=intent['hero_id'], method='inspected_shop_art',
                             owner_score=identity['unit_owner_score'], shop_sha256=shop_frame_sha256)}
    if any(frame.get('source_capture_reused') is True for frame in (post, identity)):
        evidence['source_capture_reused'] = True
    return evidence


def verify_deployment(intent, submission, evidence, *, now, source_mode='saved_replay'):
    """Check this narrow evidence contract; never submit or retry an action.

    Live acceptance requires explicit live_capture and a current wall clock.
    Retrospective tests pass their historical clock only as saved_replay. The
    caller must preserve the original live receipt separately from replay.
    """
    _mode(source_mode)
    reasons = []
    valid_intent = _valid_intent(intent)
    if not valid_intent:
        reasons.append('invalid_intent')
    i = intent if isinstance(intent, dict) else {}
    s = submission if isinstance(submission, dict) else {}
    e = evidence if isinstance(evidence, dict) else {}
    try:
        bound_digest = digest(intent)
    except (ValueError, TypeError):
        bound_digest = None
    if bound_digest is None or e.get('intent_sha256') != bound_digest:
        reasons.append('intent_binding')
    for key, reason in [('match_id', 'match_binding'), ('hero_id', 'hero_binding')]:
        if not _text(e.get(key)) or e.get(key) != i.get(key):
            reasons.append(reason)
    if e.get('source_mode') != source_mode:
        reasons.append('source_mode_mismatch')
    if source_mode == 'live_capture' and e.get('source_capture_reused') is True:
        reasons.append('reused_frame_cannot_be_live')
    if (s.get('sent') is not True or s.get('owned_release_confirmed') is not True
            or s.get('cleanup_errors') != [] or not _integer(s.get('action_budget_remaining'), 0)
            or s.get('submission_outcome') != 'drag_path_submitted_requires_visual_verification'):
        reasons.append('unclean_submission')
    try:
        source_time = timestamp(i['source_capture_utc'])
        released = timestamp(s['released_at'])
        current = timestamp(now)
        if not 0 < (released - source_time).total_seconds() <= 5:
            reasons.append('submission_source_stale_or_out_of_order')
    except (KeyError, ValueError, TypeError, AttributeError):
        reasons.append('submission_timestamp')
        source_time = released = current = None
    frame_times = {}
    for name, maximum_age in [('post_frame', 10), ('identity_frame', 5)]:
        f = e.get(name) if isinstance(e.get(name), dict) else {}
        if any(not _text(f.get(key)) or f.get(key) != i.get(key) for key in ('identity_version', 'geometry_version')):
            reasons.append(name + '_identity')
        if not _sha(f.get('sha256')) or f.get('sha256') == i.get('source_frame_sha256'):
            reasons.append(name + '_new_capture')
        try:
            captured = timestamp(f['captured_at'])
            frame_times[name] = captured
            if released is None or current is None or not released < captured <= current:
                reasons.append(name + '_order')
            elif (current - captured).total_seconds() > maximum_age:
                reasons.append(name + '_stale')
            if released is not None and (captured - released).total_seconds() > 15:
                reasons.append(name + '_action_window')
        except (KeyError, ValueError, TypeError, AttributeError):
            reasons.append(name + '_timestamp')
    post_ref = e.get('post_frame') if isinstance(e.get('post_frame'), dict) else {}
    identity_ref = e.get('identity_frame') if isinstance(e.get('identity_frame'), dict) else {}
    if (post_ref.get('sha256') == identity_ref.get('sha256')
            or (len(frame_times) == 2 and frame_times['identity_frame'] <= frame_times['post_frame'])):
        reasons.append('new_inspection_frame_required')

    hand = e.get('hand') if isinstance(e.get('hand'), dict) else {}
    if (hand.get('Known') is not True or not _integer(hand.get('BeforeCount'), 3)
            or not _integer(hand.get('AfterCount'), 2)):
        reasons.append('hand_transition')
    for name, x, y in [('Passive', 610, 774), ('Equipment', 744, 778)]:
        match = hand.get(name) if isinstance(hand.get(name), dict) else {}
        if (not _number(match.get('Score'), .97, 1) or not _number(match.get('X'), x - 3, x + 3)
                or not _number(match.get('Y'), y - 3, y + 3)
                or not _number(match.get('Scale'), 1 - 1e-9, 1 + 1e-9)):
            reasons.append('hand_preserved_' + name.lower())
    if any(not _number(hand.get(key), -1, 1) or hand[key] >= .75
           for key in ('BeforePassiveHero', 'BeforeEquipmentHero')):
        reasons.append('hand_hero_removal')

    board = e.get('board') if isinstance(e.get('board'), dict) else {}
    if (not all(_integer(board.get(key), expected) for key, expected in [('before', 0), ('after', 1), ('capacity', 5)])
            or not _number(board.get('one_score'), .97, 1)
            or not _number(board.get('zero_score'), -1, .90)
            or not _number(board.get('capacity_score'), .97, 1)):
        reasons.append('board_transition')
    identity_frame = e.get('identity_frame') if isinstance(e.get('identity_frame'), dict) else {}
    if board.get('frame_sha256') != identity_frame.get('sha256') or not _sha(board.get('frame_sha256')):
        reasons.append('board_frame_binding')
    unit = e.get('unit') if isinstance(e.get('unit'), dict) else {}
    if (unit.get('Known') is not True or unit.get('hero_id') != i.get('hero_id')
            or unit.get('method') != 'inspected_shop_art' or not _number(unit.get('Score'), .92, 1)
            or type(unit.get('Slot')) is not int or unit['Slot'] != i.get('offer_slot')):
        reasons.append('target_unit_identity')
    if (not _number(unit.get('OtherScore'), -1, 1) or not _number(unit.get('Margin'), .12, 2)
            or not _number(unit.get('Score'), -1, 1)
            or abs(unit['Score'] - unit['OtherScore'] - unit['Margin']) > 1e-9):
        reasons.append('target_unit_ambiguity')
    if not _number(unit.get('owner_score'), .97, 1):
        reasons.append('target_unit_ownership')
    if not _sha(unit.get('shop_sha256')) or unit.get('shop_sha256') != i.get('shop_frame_sha256'):
        reasons.append('purchased_shop_binding')

    component = e.get('new_unit') if isinstance(e.get('new_unit'), dict) else {}
    position = [component.get(key) for key in ('X', 'Y', 'Width', 'Height', 'CenterX', 'CenterY')]
    valid_position = all(type(v) is int for v in position)
    if valid_position:
        x, y, width, height, cx, cy = position
        valid_position = (25 <= width <= 180 and 30 <= height <= 165 and 610 <= x
                          and x + width <= 810 and 435 <= y and y + height <= 610
                          and x <= cx < x + width and y <= cy < y + height)
    if (component.get('Known') is not True or not valid_position
            or type(component.get('Pixels')) is not int or component['Pixels'] < 250
            or (valid_position and component['Pixels'] > position[2] * position[3])):
        reasons.append('new_unit_at_drop')
    if (not isinstance(e.get('inspection_target'), list) or len(e['inspection_target']) != 2
            or any(type(v) is not int for v in e['inspection_target'])
            or e['inspection_target'] != [component.get('CenterX'), component.get('CenterY')]):
        reasons.append('inspection_target_binding')

    evidence_verified = not reasons
    live_verified = evidence_verified and source_mode == 'live_capture'
    status = ('deployment_verified' if live_verified else
              'deployment_replay_verified' if evidence_verified else 'deployment_unverified')
    return {'status': status, 'reasons': reasons, 'intent_id': i.get('intent_id'),
            'hero_id': i.get('hero_id'), 'match_id': i.get('match_id'), 'source_mode': source_mode,
            'evidence_verified': evidence_verified, 'blind_retry_allowed': False,
            'game_postcondition_verified': live_verified}
