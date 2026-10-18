"""Pure retained-intent ready/talent postconditions; no capture or input APIs."""
from copy import deepcopy
import math
import uuid

from runtime.deployment_postcondition import digest, frame_ref
from runtime.phase_perception import classify
from runtime.round_label import parse_round_label
from strategy.codec import timestamp

READY_REGIONS = {'round': [678, 7, 60, 30], 'ready_button': [1358, 686, 50, 35]}
TALENT_REGIONS = {'selected_name': [267, 415, 223, 40], 'selected_description': [267, 475, 223, 65]}


def _object(value):
    return value if isinstance(value, dict) else {}


def _sha(value):
    return isinstance(value, str) and len(value) == 64 and all(c in '0123456789abcdef' for c in value)


def _text(value, maximum=4096):
    return isinstance(value, str) and 0 < len(value) <= maximum and bool(value.strip())


def _score(value, minimum=-1):
    return type(value) in (int, float) and math.isfinite(value) and minimum <= value <= 1


def compact(value):
    return ''.join(value.split()) if isinstance(value, str) and len(value) <= 4096 else None


def _mode(value):
    if value not in ('saved_replay', 'live_capture'):
        raise ValueError('explicit_transition_source_mode_required')


def _frame(frame):
    frame = _object(frame)
    identity = _object(frame.get('identity'))
    client = _object(identity.get('client'))
    try:
        timestamp(frame['captured_at'])
    except (KeyError, ValueError, TypeError, AttributeError):
        return False
    return (_sha(frame.get('sha256')) and all(_text(identity.get(key), 256) for key in ('identity_version', 'geometry_version'))
            and type(client.get('width')) is int and type(client.get('height')) is int
            and (client['width'], client['height']) == (1450, 869))


def _ocr_text(bundle, frame_sha256, rect):
    bundle = _object(bundle); roi = _object(bundle.get('roi')); ocr = _object(bundle.get('ocr'))
    if (not _sha(frame_sha256) or roi.get('kind') != 'in_memory_bgra8' or roi.get('source_sha256') != frame_sha256
            or roi.get('source_rect') != rect or type(roi.get('scale')) is not int or roi['scale'] != 3
            or not _sha(roi.get('pixel_sha256')) or ocr.get('status') != 'recognized'
            or ocr.get('frame_sha256') != frame_sha256 or ocr.get('pixel_sha256') != roi.get('pixel_sha256')
            or ocr.get('cache_hit') is not False or not isinstance(ocr.get('text'), str) or len(ocr['text']) > 4096):
        raise ValueError('unbound_or_cached_transition_ocr')
    return compact(ocr['text'])


def _candidate_layout(frame):
    rows = _object(frame).get('matches')
    expected = {'name_' + str(i) for i in range(3)} | {'description_' + str(i) for i in range(3)}
    if not isinstance(rows, list) or len(rows) != 6:
        return None
    scores = {}
    for row in rows:
        row = _object(row)
        if not isinstance(row.get('name'), str) or row['name'] not in expected or row['name'] in scores or not _score(row.get('score')):
            return None
        scores[row['name']] = row['score']
    return all(score >= .97 for score in scores.values()) if set(scores) == expected else None


def _intent(frame, operation, match_id, details, source_mode):
    _mode(source_mode)
    if not _frame(frame) or not _text(match_id, 256) or match_id.strip().casefold() in ('unknown', '?'):
        raise ValueError('bound_transition_source_and_match_required')
    if frame.get('source_mode', source_mode) != source_mode:
        raise ValueError('transition_source_mode_mismatch')
    return {'schema': 'ui-transition-intent/1', 'intent_id': str(uuid.uuid4()), 'operation': operation,
            'match_id': match_id, 'source_frame': frame_ref(frame), 'source_mode': source_mode,
            'details': deepcopy(details), 'submission_limit': 1}


def make_ready_intent(before, *, match_id, ocr, source_mode='saved_replay'):
    """Use original bound header/button OCR; never click an already-Cancel UI."""
    phase = classify(before)
    if phase.get('phase') != 'preparation' or phase.get('one_unit_verified') is not True:
        raise ValueError('recognized_preparation_and_deployed_unit_required')
    if not _frame(before):
        raise ValueError('bound_transition_source_required')
    texts = {key: _ocr_text(_object(ocr).get(key), before['sha256'], rect) for key, rect in READY_REGIONS.items()}
    round_number = parse_round_label(texts['round'])
    if round_number is None or texts['ready_button'] not in ('准备', '开战'):
        raise ValueError('exact_ready_control_and_round_required')
    return _intent(before, 'ready_retained_unit', match_id,
                   {'round': round_number, 'button_text': texts['ready_button']}, source_mode)


def make_talent_intent(before, *, match_id, candidates, selected_index, verification_fragment,
                       source_mode='saved_replay'):
    """Bind three explicitly reviewed readable candidates; no talent ranking."""
    if (not isinstance(candidates, list) or len(candidates) != 3 or type(selected_index) is not int
            or not 0 <= selected_index < 3 or _candidate_layout(before) is not True):
        raise ValueError('three_current_reviewed_talents_required')
    if any(not _text(_object(row).get('name'), 128) or not _text(_object(row).get('description'), 2048) for row in candidates):
        raise ValueError('readable_talent_names_and_descriptions_required')
    if (len({compact(row['name']) for row in candidates}) != 3 or not _text(verification_fragment, 256)
            or compact(verification_fragment) not in compact(candidates[selected_index]['description'])):
        raise ValueError('distinct_candidates_and_selected_description_fragment_required')
    return _intent(before, 'choose_reviewed_talent', match_id,
                   {'candidates': candidates, 'selected_index': selected_index,
                    'verification_fragment': compact(verification_fragment)}, source_mode)


def _common(intent, expected_digest, after, submission, native, *, operation, started_at, now, source_mode):
    _mode(source_mode)
    i = _object(intent); s = _object(submission); n = _object(native); source = _object(i.get('source_frame'))
    reasons = []
    try:
        if not _sha(expected_digest) or digest(intent) != expected_digest:
            reasons.append('intent_binding')
    except (ValueError, TypeError):
        reasons.append('intent_binding')
    if (i.get('schema') != 'ui-transition-intent/1' or i.get('operation') != operation
            or not _text(i.get('intent_id'), 256) or not _text(i.get('match_id'), 256)
            or type(i.get('submission_limit')) is not int or i['submission_limit'] != 1
            or not _sha(source.get('sha256'))):
        reasons.append('invalid_transition_intent')
    if i.get('source_mode') != source_mode or _object(after).get('source_mode', source_mode) != source_mode:
        reasons.append('source_mode_mismatch')
    if source_mode == 'live_capture' and _object(after).get('source_capture_reused') is True:
        reasons.append('reused_frame_cannot_be_live')
    if not _frame(after):
        reasons.append('invalid_after_frame')
    a = _object(after); identity = _object(a.get('identity'))
    if not _sha(a.get('sha256')) or a.get('sha256') == source.get('sha256'):
        reasons.append('new_after_capture_required')
    if any(not _text(source.get(key), 256) or source.get(key) != identity.get(key)
           for key in ('identity_version', 'geometry_version')):
        reasons.append('window_binding')
    try:
        begin = timestamp(started_at); current = timestamp(now)
        captured = timestamp(a['captured_at']); source_time = timestamp(source['captured_at'])
        if not 0 <= (begin - source_time).total_seconds() <= 5:
            reasons.append('source_freshness')
        if not begin < captured <= current or (current - captured).total_seconds() > 8 or (captured - begin).total_seconds() > 8:
            reasons.append('post_frame_freshness')
    except (KeyError, ValueError, TypeError, AttributeError):
        reasons.append('transition_timestamp')
    if (s.get('sent') is not True or s.get('owned_release_confirmed') is not True or s.get('cleanup_errors') != []
            or type(s.get('action_budget_remaining')) is not int or s['action_budget_remaining'] != 0
            or s.get('submission_outcome') != 'down_and_owned_up_submitted'):
        reasons.append('unclean_submission')
    if (n.get('held') is not False or n.get('release_confirmed') is not True or n.get('cleanup_errors') != []
            or type(n.get('down_count')) is not int or n['down_count'] != 2
            or type(n.get('owned_up_count')) is not int or n['owned_up_count'] != 1):
        reasons.append('native_release')
    return reasons


def _result(intent, after, reasons, source_mode, name, **extra):
    evidence_verified = not reasons
    live_verified = evidence_verified and source_mode == 'live_capture'
    try:
        intent_digest = digest(intent)
    except (ValueError, TypeError):
        intent_digest = None
    return {'status': name + ('_verified' if live_verified else '_replay_verified' if evidence_verified else '_unverified_no_retry'),
            'game_postcondition_verified': live_verified, 'evidence_verified': evidence_verified, 'reasons': reasons,
            'intent_id': _object(intent).get('intent_id'), 'intent_sha256': intent_digest,
            'match_id': _object(intent).get('match_id'), 'source_mode': source_mode,
            'before_sha256': _object(_object(intent).get('source_frame')).get('sha256'),
            'after_sha256': _object(after).get('sha256'), 'blind_retry_allowed': False, **extra}


def verify_ready(intent, after, *, intent_sha256, ocr, submission, native, started_at, now,
                 source_mode='saved_replay'):
    """Accept only a same-round exact Cancel control or positive combat anchors."""
    reasons = _common(intent, intent_sha256, after, submission, native, operation='ready_retained_unit',
                      started_at=started_at, now=now, source_mode=source_mode)
    details = _object(_object(intent).get('details')); round_number = details.get('round')
    if (type(round_number) is not int or not 1 <= round_number <= 99 or details.get('button_text') not in ('准备', '开战')):
        reasons.append('invalid_ready_intent')
    post_round = None; button = None
    try:
        text = {key: _ocr_text(_object(ocr).get(key), _object(after).get('sha256'), rect) for key, rect in READY_REGIONS.items()}
        post_round = parse_round_label(text['round']); button = text['ready_button']
    except ValueError:
        reasons.append('ready_ocr_binding')
    phase = classify(after); method = None
    if post_round == round_number and type(round_number) is int:
        if button == '取消' and phase['phase'] == 'preparation':
            method = 'same_round_cancel_control'
        elif phase['phase'] == 'battle_or_resolution':
            method = 'same_round_combat'
    if method is None:
        reasons.append('ready_postcondition')
    return _result(intent, after, reasons, source_mode, 'ready', round=round_number,
                   post_round=post_round, button_text=button, method=method)


def verify_talent(intent, after, *, intent_sha256, ocr, submission, native, started_at, now,
                  source_mode='saved_replay'):
    """Verify selected detail only; no assertion of reward delivery or utility."""
    reasons = _common(intent, intent_sha256, after, submission, native, operation='choose_reviewed_talent',
                      started_at=started_at, now=now, source_mode=source_mode)
    details = _object(_object(intent).get('details')); candidates = details.get('candidates'); selected = details.get('selected_index')
    valid = (isinstance(candidates, list) and len(candidates) == 3 and type(selected) is int and 0 <= selected < 3
             and all(_text(_object(row).get('name'), 128) and _text(_object(row).get('description'), 2048) for row in candidates)
             and _text(details.get('verification_fragment'), 256))
    expected_name = None; fragment = None
    if valid:
        expected_name = compact(candidates[selected]['name']); fragment = compact(details['verification_fragment'])
        valid = (len({compact(row['name']) for row in candidates}) == 3
                 and fragment in compact(candidates[selected]['description']))
    if not valid:
        reasons.append('invalid_talent_intent')
    layout = _candidate_layout(after)
    if layout is not False:
        reasons.append('three_candidate_layout_not_removed')
    name = description = None
    try:
        name = _ocr_text(_object(ocr).get('selected_name'), _object(after).get('sha256'), TALENT_REGIONS['selected_name'])
        description = _ocr_text(_object(ocr).get('selected_description'), _object(after).get('sha256'), TALENT_REGIONS['selected_description'])
    except ValueError:
        reasons.append('talent_ocr_binding')
    if not valid or name != expected_name or description is None or fragment not in description:
        reasons.append('selected_talent_detail')
    return _result(intent, after, reasons, source_mode, 'talent_selection', selected_name=name,
                   selected_description=description, rewards_verified=False, future_effects_verified=False)
