"""Read-only information-panel geometry, separate from selected-talent summary."""
from runtime.transition_verification import _frame, _ocr_text, _object, _score, _sha, compact
from strategy.codec import timestamp

CENTER_TITLE_RECT = [500, 45, 450, 50]
CENTER_DESCRIPTION_RECT = [613, 467, 225, 75]
CENTER_PERSISTENT_NAME_RECT = [610, 400, 230, 52]


def _rect(value):
    return (isinstance(value, list) and len(value) == 4 and all(type(v) is int for v in value)
            and 0 <= value[0] < value[0] + value[2] <= 1450
            and 0 <= value[1] < value[1] + value[3] <= 869
            and (10 <= value[2] <= 400 or value == CENTER_TITLE_RECT) and 10 <= value[3] <= 200)


def bind_persistent_information(identity):
    """After exact full-title OCR, bind the same frame's durable card regions.

    Only the reviewed centered derived-card layout is supported. The transient
    title may disappear; the internal card name AND effect must still match a
    fresh frame. The original bitmap/ROI producer remains independently checked.
    """
    old = _object(identity)
    if (old.get('information_matched') is not True or not _sha(old.get('frame_sha256'))
            or old.get('name_rect') != CENTER_TITLE_RECT or old.get('description_rect') != CENTER_DESCRIPTION_RECT
            or not isinstance(old.get('name'), str) or not old['name'].endswith('衍生卡')):
        raise ValueError('exact_centered_derived_card_identity_required')
    return dict(old, name_rect=list(CENTER_PERSISTENT_NAME_RECT), description_rect=list(CENTER_DESCRIPTION_RECT),
                ocr_identity_regions={'name': list(CENTER_TITLE_RECT), 'description': list(CENTER_DESCRIPTION_RECT)},
                persistent_identity_regions={'name': list(CENTER_PERSISTENT_NAME_RECT), 'description': list(CENTER_DESCRIPTION_RECT)},
                execution_allowed=False, selection_commit_verified=False, rewards_verified=False)


def assess_information(frame, ocr, *, expected_name, effect_fragment, name_rect, description_rect,
                       now, source_mode='saved_replay'):
    """Bind the ACTUAL readable preview rectangles; never infer a selection.

    A preview's detailed effect and a selected talent's short summary can differ.
    Selection still needs its own bound summary check at the selected-detail ROIs.
    """
    if source_mode not in ('saved_replay', 'live_capture'):
        raise ValueError('explicit_information_source_mode_required')
    f = _object(frame); identity = _object(f.get('identity')); reasons = []
    name = description = None
    if not _frame(f):
        reasons.append('bound_information_frame_required')
    if f.get('source_mode', source_mode) != source_mode or (source_mode == 'live_capture' and f.get('source_capture_reused') is True):
        reasons.append('information_source_mode_mismatch')
    valid_rects = _rect(name_rect) and _rect(description_rect)
    if valid_rects:
        x, y, w, h = name_rect; a, b, c, d = description_rect
        valid_rects = not (max(x, a) < min(x + w, a + c) and max(y, b) < min(y + h, b + d))
    if not valid_rects:
        reasons.append('actual_separate_information_rectangles_required')
    try:
        if not 0 <= (timestamp(now) - timestamp(f['captured_at'])).total_seconds() <= 8:
            reasons.append('information_frame_stale_or_future')
        if valid_rects:
            name = _ocr_text(_object(ocr).get('name'), f['sha256'], name_rect)
            description = _ocr_text(_object(ocr).get('description'), f['sha256'], description_rect)
    except (KeyError, TypeError, ValueError, AttributeError):
        reasons.append('information_ocr_or_time_binding')
    fragment = compact(effect_fragment)
    if (not isinstance(expected_name, str) or not 1 <= len(expected_name) <= 128 or name != compact(expected_name)
            or not isinstance(fragment, str) or not 4 <= len(fragment) <= 256
            or description is None or fragment not in description):
        reasons.append('exact_information_name_and_effect_required')
    return {'information_matched': not reasons, 'reasons': reasons, 'source_mode': source_mode,
            'frame_sha256': f.get('sha256'), 'captured_at': f.get('captured_at'),
            'identity_version': identity.get('identity_version'), 'geometry_version': identity.get('geometry_version'),
            'name_rect': list(name_rect) if valid_rects else None,
            'description_rect': list(description_rect) if valid_rects else None,
            'name': name, 'description': description,
            'execution_allowed': False, 'selection_commit_verified': False, 'rewards_verified': False}


def information_still_current(binding, current, comparisons, *, now, deadline_at, source_mode='saved_replay'):
    """Require BOTH hash/ROI-bound comparisons; an empty set cannot pass.

    Fresh capture after a bounded fact review must revalidate the actual panel.
    If the overlay disappeared at a round change, stop without another close.
    No native executor or full talent transaction is provided here.
    """
    if source_mode not in ('saved_replay', 'live_capture'):
        raise ValueError('explicit_information_source_mode_required')
    old = _object(binding); new = _object(current); reasons = []
    if old.get('information_matched') is not True or not _sha(old.get('frame_sha256')) or not _frame(new):
        reasons.append('verified_information_and_current_frame_required')
    if (old.get('source_mode') != source_mode or new.get('source_mode', source_mode) != source_mode
            or (source_mode == 'live_capture' and new.get('source_capture_reused') is True)):
        reasons.append('information_source_mode_mismatch')
    identity = _object(new.get('identity'))
    if any(not isinstance(old.get(key), str) or not old[key] or old[key] != identity.get(key)
           for key in ('identity_version', 'geometry_version')):
        reasons.append('information_window_changed')
    try:
        source = timestamp(old['captured_at']); captured = timestamp(new['captured_at'])
        clock = timestamp(now); deadline = timestamp(deadline_at)
        if not source < captured <= clock < deadline or not 0 < (deadline - source).total_seconds() <= 600:
            reasons.append('information_original_deadline_or_order')
        if not 0 <= (clock - captured).total_seconds() <= 8 or not 0 < (captured - source).total_seconds() <= 60:
            reasons.append('fresh_information_after_bounded_review_required')
    except (KeyError, TypeError, ValueError, AttributeError):
        reasons.append('information_capture_time_binding')
    fields = {'name': old.get('name_rect'), 'description': old.get('description_rect')}
    seen = set()
    if not isinstance(comparisons, list) or len(comparisons) != 2:
        reasons.append('both_information_comparisons_required')
    else:
        for row in comparisons:
            row = _object(row); key = row.get('field')
            if (not isinstance(key, str) or key not in fields or key in seen or not _rect(fields.get(key))
                    or row.get('reference_sha256') != old.get('frame_sha256')
                    or row.get('frame_sha256') != new.get('sha256') or row.get('roi') != fields.get(key)
                    or not _score(row.get('score'), .97)):
                reasons.append('information_changed_or_comparison_unbound')
            if isinstance(key, str):
                seen.add(key)
        if seen != set(fields):
            reasons.append('both_information_comparisons_required')
    return {'information_current': not reasons, 'reasons': reasons, 'source_mode': source_mode,
            'execution_allowed': False, 'native_retry_allowed': False, 'game_postcondition_verified': False,
            'selection_commit_verified': False, 'rewards_verified': False}
