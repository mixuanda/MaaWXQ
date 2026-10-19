"""Advisory shop/detail ordering and pure shop-close evidence verification."""
import math

from runtime.name_mask import population_template_gate
from runtime.round_label import parse_round_label
from strategy.codec import timestamp


def _score(value, minimum=-1):
    return type(value) in (int, float) and math.isfinite(value) and minimum <= value <= 1


def _sha(value):
    return isinstance(value, str) and len(value) == 64 and all(c in '0123456789abcdef' for c in value)


def _object(value):
    return value if isinstance(value, dict) else {}


def _frame(frame):
    frame = _object(frame); identity = _object(frame.get('identity')); client = _object(identity.get('client'))
    return (_sha(frame.get('sha256'))
            and all(isinstance(identity.get(key), str) and bool(identity[key].strip()) for key in ('identity_version', 'geometry_version'))
            and type(client.get('width')) is int and type(client.get('height')) is int
            and (client['width'], client['height']) == (1450, 869))


def count_matches(frame, expected):
    return population_template_gate(_object(_object(frame).get('v14')).get('counts'),
                                    expected_count=expected, capacity_score=1)


def inspect_surface(frame, expected_count, target_cell):
    """Suggest one surface operation; population failure cannot grant deployment.

    This pure gate does not check wall-clock freshness or grant input. The sole
    controller must bind the custom origin, references and current capture,
    reserve evidence and use its existing guarded one-attempt transaction.
    """
    evidence = {'current_frame_sha256': _object(frame).get('sha256')}
    def result(action, reason):
        return {'action': action, 'reason': reason, 'evidence': evidence,
                'execution_allowed': False, 'blind_retry_allowed': False}
    if (not _frame(frame) or type(expected_count) is not int or not 0 <= expected_count <= 4
            or (target_cell is not None and (type(target_cell) is not int or not 1 <= target_cell <= 5))):
        return result('stop', 'invalid_surface_binding_or_scope')
    rows = frame.get('matches'); matches = {}
    if not isinstance(rows, list):
        return result('stop', 'invalid_surface_anchors')
    for row in rows:
        if (not isinstance(row, dict) or not isinstance(row.get('name'), str) or row['name'] in matches
                or not _score(row.get('score'))):
            return result('stop', 'invalid_surface_anchors')
        matches[row['name']] = row['score']
    v = _object(frame.get('v14'))
    labels = sorted(('phase_ready', 'phase_start'), key=lambda key: matches.get(key, 0), reverse=True)
    prep = matches.get(labels[0], 0) >= .97 and matches.get(labels[0], 0) - matches.get(labels[1], 0) >= .02
    own = matches.get('own_portrait', 0) >= .985
    shop = sum(matches.get('price_' + str(i), 0) >= .97 for i in range(4)) >= 2
    owner = v.get('owner'); panel = _score(owner, .97)
    known_panel = panel and any(_score(v.get(key), .97) for key in ('panel_name', 'panel_name_white'))
    capacity = v.get('capacity') if _score(v.get('capacity')) else None
    evidence.update(own_player=own, preparation_control=prep, shop_visible=shop,
                    owned_panel=panel, known_panel=known_panel, fresh_count_matches=count_matches(frame, expected_count),
                    capacity_score=capacity)
    if not prep:
        return result('wait', 'current_preparation_control_not_proven')
    if not _score(owner):
        return result('stop', 'current_panel_presence_unknown')
    if panel:
        return result('dismiss_owned_panel' if known_panel else 'stop',
                      'known_current_owned_detail' if known_panel else 'current_panel_identity_unknown')
    if not own:
        return result('wait', 'current_own_player_not_proven')
    if shop:
        return result('dismiss_shop', 'current_shop_and_own_preparation_control')
    if not evidence['fresh_count_matches'] or not _score(capacity, .97):
        return result('stop', 'uncovered_current_population_or_capacity_unknown')
    if target_cell is not None:
        cells = v.get('cells')
        found = [row.get('score') for row in cells if isinstance(row, dict) and type(row.get('id')) is int
                 and row['id'] == target_cell] if isinstance(cells, list) else []
        evidence['current_empty_cell_score'] = found[0] if len(found) == 1 and _score(found[0]) else None
        if len(found) != 1 or not _score(found[0], .97):
            return result('stop', 'current_target_empty_cell_unknown')
    return result('deployment_surface_ready', 'current_uncovered_count_capacity_empty_cell_and_own_player')


def verify_shop_close(before, after, *, expected_count, target_cell, title_anchor, submission, native,
                      started_at, released_at, now, before_round_text='', after_round_text='', source_mode='saved_replay'):
    """Verify only shop disappearance/restored surface, never a deployment.

    The exact before/after round-header pixel comparison must be hash-bound.
    Numeric round OCR can be unknown for this close only; deployment still
    needs a newly parsed current round and independent preaction validation.
    """
    if source_mode not in ('saved_replay', 'live_capture'):
        raise ValueError('explicit_shop_close_source_mode_required')
    b = _object(before); a = _object(after); anchor = _object(title_anchor)
    s = _object(submission); n = _object(native); reasons = []
    old = inspect_surface(before, expected_count, target_cell); new = inspect_surface(after, expected_count, target_cell)
    if old['action'] != 'dismiss_shop' or new['action'] != 'deployment_surface_ready':
        reasons.append('shop_close_or_restored_surface_unproven')
    if not _frame(before) or not _frame(after) or b.get('sha256') == a.get('sha256'):
        reasons.append('distinct_bound_shop_frames_required')
    bi = _object(b.get('identity')); ai = _object(a.get('identity'))
    if any(not isinstance(bi.get(key), str) or bi.get(key) != ai.get(key) for key in ('identity_version', 'geometry_version')):
        reasons.append('shop_close_window_changed')
    if any(frame.get('source_mode', source_mode) != source_mode for frame in (b, a)):
        reasons.append('source_mode_mismatch')
    if source_mode == 'live_capture' and any(frame.get('source_capture_reused') is True for frame in (b, a)):
        reasons.append('reused_frame_cannot_be_live')
    if (anchor.get('before_sha256') != b.get('sha256') or anchor.get('after_sha256') != a.get('sha256')
            or anchor.get('roi') != [678, 7, 60, 30] or not _score(anchor.get('score'), .97)):
        reasons.append('same_round_title_binding_required')
    prior_round = parse_round_label(before_round_text); later_round = parse_round_label(after_round_text)
    if prior_round is not None and later_round is not None and prior_round != later_round:
        reasons.append('shop_close_crossed_round')
    try:
        source = timestamp(b['captured_at']); start = timestamp(started_at); released = timestamp(released_at)
        captured = timestamp(a['captured_at']); current = timestamp(now)
        if not 0 <= (start - source).total_seconds() <= 5 or not start < released < captured <= current:
            reasons.append('shop_close_frame_order')
        if not 0 <= (current - captured).total_seconds() <= 8 or not 0 < (captured - start).total_seconds() <= 8:
            reasons.append('shop_close_frame_stale')
    except (KeyError, ValueError, TypeError, AttributeError):
        reasons.append('shop_close_timestamp')
    if (s.get('sent') is not True or s.get('owned_release_confirmed') is not True or s.get('cleanup_errors') != []
            or type(s.get('action_budget_remaining')) is not int or s['action_budget_remaining'] != 0
            or s.get('submission_outcome') != 'down_and_owned_up_submitted'
            or n.get('held') is not False or n.get('release_confirmed') is not True or n.get('cleanup_errors') != []
            or type(n.get('down_count')) is not int or n['down_count'] != 2
            or type(n.get('owned_up_count')) is not int or n['owned_up_count'] != 1):
        reasons.append('shop_close_release_unproven')
    evidence_verified = not reasons; live_verified = evidence_verified and source_mode == 'live_capture'
    return {'status': 'shop_close_verified' if live_verified else 'shop_close_replay_verified' if evidence_verified else 'shop_close_unverified_no_retry',
            'reasons': reasons, 'evidence_verified': evidence_verified, 'game_postcondition_verified': live_verified,
            'source_mode': source_mode, 'before_sha256': b.get('sha256'), 'after_sha256': a.get('sha256'),
            'restored_surface': new, 'before_round': prior_round, 'after_round': later_round,
            'numeric_round_required_for_deployment': True, 'deployment_verified': False,
            'execution_allowed': False, 'blind_retry_allowed': False}
