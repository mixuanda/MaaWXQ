"""Whole-layout talent evidence, bounded stability polling and detail recovery."""
import math

from runtime.surface_gate import inspect_surface, _frame
from runtime.transition_verification import _ocr_text, compact
from strategy.codec import timestamp


def talent_layout(frame):
    """Require one complete family; do not assemble three mixed footer votes."""
    if not isinstance(frame, dict):
        return {'kind': 'unknown', 'families': []}
    banks = []
    values = frame.get('v14') if isinstance(frame.get('v14'), dict) else {}
    for rows, key in [(frame.get('matches'), 'name'), (values.get('anchors'), 'id')]:
        if rows is None:
            rows = []
        if not isinstance(rows, list):
            return {'kind': 'unknown', 'families': []}
        bank = {}
        for row in rows:
            if (not isinstance(row, dict) or not isinstance(row.get(key), str) or row[key] in bank
                    or type(row.get('score')) not in (int, float) or not math.isfinite(row['score'])
                    or not -1 <= row['score'] <= 1):
                return {'kind': 'unknown', 'families': []}
            bank[row[key]] = row['score']
        banks.append(bank)
    families = [('legacy', banks[0], ['talent_footer_' + str(i) for i in range(1, 4)]),
                ('current', banks[1], ['current_talent_footer_' + str(i) for i in range(3)]),
                ('reviewed', banks[1], ['reviewed_talent_footer_' + str(i) for i in range(3)]),
                ('gold', banks[1], ['gold_talent_footer_' + str(i) for i in range(3)])]
    full = [name for name, bank, keys in families if all(bank.get(key, -1) >= .97 for key in keys)]
    if full:
        return {'kind': 'three_candidates', 'families': full}
    complete = [(bank, keys) for _, bank, keys in families if all(key in bank for key in keys)]
    partial = any(bank.get(key, -1) >= .97 for _, bank, keys in families for key in keys)
    return {'kind': 'not_three_candidates' if complete and not partial else 'unknown', 'families': []}


def assess_selected_detail(frame, ocr, *, expected_name, effect_fragment, now, source_mode='saved_replay'):
    """Exact current detail candidate; an information preview is not a commit."""
    if source_mode not in ('saved_replay', 'live_capture'):
        raise ValueError('explicit_talent_detail_source_mode_required')
    reasons = []; name = description = None
    if not _frame(frame):
        reasons.append('bound_talent_frame_required')
    if isinstance(frame, dict) and (frame.get('source_mode', source_mode) != source_mode
                                   or (source_mode == 'live_capture' and frame.get('source_capture_reused') is True)):
        reasons.append('talent_detail_source_mode_mismatch')
    try:
        if not 0 <= (timestamp(now) - timestamp(frame['captured_at'])).total_seconds() <= 8:
            reasons.append('talent_detail_stale_or_future')
        name = _ocr_text(ocr.get('name'), frame['sha256'], [267, 415, 223, 40])
        description = _ocr_text(ocr.get('description'), frame['sha256'], [267, 475, 223, 65])
    except (KeyError, TypeError, ValueError, AttributeError):
        reasons.append('talent_detail_ocr_or_time_binding')
    if (not isinstance(expected_name, str) or not 1 <= len(expected_name) <= 128
            or not isinstance(effect_fragment, str) or not 4 <= len(compact(effect_fragment) or '') <= 256
            or name != compact(expected_name) or description is None or compact(effect_fragment) not in description):
        reasons.append('exact_talent_name_effect_required')
    if talent_layout(frame)['kind'] != 'not_three_candidates':
        reasons.append('candidate_layout_or_unknown_animation')
    identity = frame.get('identity', {}) if isinstance(frame, dict) else {}
    return {'detail_matched': not reasons, 'reasons': reasons,
            'frame_sha256': frame.get('sha256') if isinstance(frame, dict) else None,
            'captured_at': frame.get('captured_at') if isinstance(frame, dict) else None,
            'identity_version': identity.get('identity_version'), 'geometry_version': identity.get('geometry_version'),
            'selected_name': name, 'selected_description': description,
            'source_mode': source_mode, 'execution_allowed': False, 'selection_commit_verified': False, 'rewards_verified': False}


def stability_decision(observations):
    """At most three fresh post-selection captures; never suggest another click."""
    if not isinstance(observations, list) or not 1 <= len(observations) <= 3:
        raise ValueError('one_to_three_postcondition_observations_required')
    previous = None; binding = None
    for row in observations:
        if not isinstance(row, dict):
            raise ValueError('bound_stability_observation_required')
        sha = row.get('frame_sha256')
        current_binding = (row.get('identity_version'), row.get('geometry_version'))
        if (not isinstance(sha, str) or len(sha) != 64 or any(c not in '0123456789abcdef' for c in sha)
                or any(not isinstance(value, str) or not value for value in current_binding)
                or (binding is not None and current_binding != binding)):
            raise ValueError('same_game_stability_frames_required')
        binding = current_binding
        current = timestamp(row['captured_at'])
        if previous is not None and current <= previous:
            raise ValueError('new_capture_time_required')
        previous = current
    matched = any(row.get('detail_matched') is True for row in observations)
    return {'action': 'detail_seen' if matched else 'wait_read_only' if len(observations) < 3 else 'stop_no_retry',
            'captures_used': len(observations), 'captures_remaining': 3 - len(observations),
            'native_retry_allowed': False, 'execution_allowed': False}


def verify_detail_return(detail, after, close_step, *, expected_count, deadline_at, now, source_mode='saved_replay'):
    """Verify exact detail -> owned release -> fresh preparation within deadline.

    This verifies recovery, not talent ranking, reward delivery or a new choice.
    Unknown animation can only wait read-only under the original shared budget.
    """
    if source_mode not in ('saved_replay', 'live_capture'):
        raise ValueError('explicit_talent_return_source_mode_required')
    reasons = []; step = close_step if isinstance(close_step, dict) else {}
    state = inspect_surface(after, expected_count, None)
    ev = state['evidence']; native = step.get('native_summary', {}); submission = step.get('submission', {})
    if (not isinstance(detail, dict) or detail.get('detail_matched') is not True
            or step.get('before') != detail.get('frame_sha256')
            or step.get('operation') not in ('dismiss_verified_selected_talent_detail', 'dismiss_recovered_verified_talent',
                                            'dismiss_local_verified_talent_detail')):
        reasons.append('exact_detail_close_binding_required')
    if (not isinstance(detail, dict) or detail.get('source_mode') != source_mode
            or (isinstance(after, dict) and (after.get('source_mode', source_mode) != source_mode
                or (source_mode == 'live_capture' and after.get('source_capture_reused') is True)))):
        reasons.append('talent_return_source_mode_mismatch')
    if (not ev.get('preparation_control') or not ev.get('own_player') or not ev.get('fresh_count_matches')
            or type(ev.get('capacity_score')) not in (int, float) or ev['capacity_score'] < .97
            or talent_layout(after)['kind'] != 'not_three_candidates'):
        reasons.append('preparation_return_pending')
    try:
        identity = after['identity']
        if any(identity[key] != detail[key] for key in ('identity_version', 'geometry_version')):
            reasons.append('talent_return_window_changed')
        before = timestamp(detail['captured_at']); start = timestamp(step['started_at'])
        released = timestamp(step['completed_at']); current = timestamp(after['captured_at'])
        deadline = timestamp(deadline_at); clock = timestamp(now)
        if not before <= start < released < current <= clock <= deadline or not 0 <= (start - before).total_seconds() <= 5:
            reasons.append('talent_return_order_or_deadline')
        if not 0 <= (clock - current).total_seconds() <= 8 or not 0 < (deadline - released).total_seconds() <= 600:
            reasons.append('bounded_fresh_recovery_required')
    except (KeyError, TypeError, ValueError, AttributeError):
        reasons.append('talent_return_binding_or_time')
    if (not isinstance(native, dict) or not isinstance(submission, dict) or native.get('held') is not False
            or native.get('release_confirmed') is not True or native.get('cleanup_errors') != []
            or submission.get('sent') is not True or submission.get('owned_release_confirmed') is not True
            or submission.get('cleanup_errors') != [] or type(submission.get('action_budget_remaining')) is not int
            or submission['action_budget_remaining'] != 0 or submission.get('submission_outcome') != 'down_and_owned_up_submitted'
            or type(native.get('down_count')) is not int or native['down_count'] != 2
            or type(native.get('owned_up_count')) is not int or native['owned_up_count'] != 1):
        reasons.append('talent_close_release_unproven')
    valid = not reasons
    return {'status': 'talent_detail_return_verified' if valid and source_mode == 'live_capture' else
                     'talent_detail_return_replay_verified' if valid else 'talent_return_unverified_no_retry',
            'reasons': reasons, 'evidence_verified': valid, 'source_mode': source_mode,
            'game_postcondition_verified': valid and source_mode == 'live_capture',
            'execution_allowed': False, 'native_retry_allowed': False, 'rewards_verified': False,
            'five_unit_verified': False}
