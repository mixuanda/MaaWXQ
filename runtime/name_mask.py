"""Read-only acceptance of the bounded white-name mask and population templates.

These checks do not perform OCR, identify arbitrary names or authorize input.
"""
from copy import deepcopy
import math

from strategy.codec import timestamp

NAME_ROI = (144, 191, 100, 31)
NAME_THRESHOLD = .97


def _number(value, low=-1, high=1):
    return type(value) in (int, float) and math.isfinite(value) and low <= value <= high


def _sha(value):
    return isinstance(value, str) and len(value) == 64 and all(c in '0123456789abcdef' for c in value)


def is_name_match(result):
    """Check full NameMaskCandidate.Result, including ink density and shift."""
    if not isinstance(result, dict):
        return False
    return (_number(result.get('Score'), NAME_THRESHOLD)
            and all(type(result.get(key)) is int and -3 <= result[key] <= 3 for key in ('Dx', 'Dy'))
            and all(type(result.get(key)) is int and 40 <= result[key] <= NAME_ROI[2] * NAME_ROI[3] * .65
                    for key in ('ReferencePixels', 'CurrentPixels')))


def population_template_gate(rows, *, expected_count, capacity_score):
    """Preserve .97 score/.02 competitor gates; scores need reviewed templates.

    This is a template gate, not independent numeric recognition or a dispatch
    decision. A successful name match never substitutes for these measurements.
    """
    if (type(expected_count) is not int or not 0 <= expected_count <= 5
            or not _number(capacity_score, .97) or not isinstance(rows, list) or not 1 <= len(rows) <= 9):
        return False
    values = set()
    for row in rows:
        if (not isinstance(row, dict) or type(row.get('value')) is not int or not 0 <= row['value'] <= 8
                or row['value'] in values or not _number(row.get('score'))):
            return False
        values.add(row['value'])
    ordered = sorted(rows, key=lambda row: row['score'], reverse=True)
    winner = ordered[0]
    return (winner['value'] == expected_count and winner['score'] >= .97
            and all(winner['score'] - row['score'] >= .02 for row in ordered[1:]))


def assess_name_match(reference, current, result, *, now, source_mode='saved_replay'):
    """Bind metadata for a known inspected-panel reference; no name/owner proof.

    The producer must hash both actual bitmaps and use the fixed NAME_ROI with
    the exact mask source. This helper checks the declared bindings and result;
    it does not certify the producer or make a saved reference a current roster.
    """
    if source_mode not in ('saved_replay', 'live_capture'):
        raise ValueError('explicit_name_mask_source_mode_required')
    reference = reference if isinstance(reference, dict) else {}
    current = current if isinstance(current, dict) else {}
    reasons = []
    for frame in (reference, current):
        identity = frame.get('identity') if isinstance(frame.get('identity'), dict) else {}
        client = identity.get('client') if isinstance(identity.get('client'), dict) else {}
        if (not _sha(frame.get('sha256'))
                or any(not isinstance(identity.get(key), str) or not identity[key].strip()
                       for key in ('identity_version', 'geometry_version'))
                or type(client.get('width')) is not int or type(client.get('height')) is not int
                or (client['width'], client['height']) != (1450, 869)):
            reasons.append('invalid_name_frame_binding')
    if current.get('source_mode', source_mode) != source_mode:
        reasons.append('source_mode_mismatch')
    if source_mode == 'live_capture' and current.get('source_capture_reused') is True:
        reasons.append('reused_frame_cannot_be_live')
    if reference.get('sha256') == current.get('sha256'):
        reasons.append('distinct_current_frame_required')
    try:
        if not (timestamp(reference['captured_at']) < timestamp(current['captured_at']) <= timestamp(now)):
            reasons.append('name_frame_order')
        if not 0 <= (timestamp(now) - timestamp(current['captured_at'])).total_seconds() <= 5:
            reasons.append('name_frame_stale_or_future')
    except (KeyError, ValueError, TypeError, AttributeError):
        reasons.append('invalid_name_frame_time')
    if not is_name_match(result):
        reasons.append('white_name_mask_unproven')
    return {'status': 'name_mask_candidate' if not reasons else 'name_mask_unproven', 'reasons': reasons,
            'source_mode': source_mode, 'reference_sha256': reference.get('sha256'),
            'current_sha256': current.get('sha256'), 'roi': list(NAME_ROI),
            'measurement': deepcopy(result) if isinstance(result, dict) else None,
            'name_text': None, 'hero_id': None, 'ownership_verified': False,
            'execution_allowed': False, 'game_postcondition_verified': False, 'blind_retry_allowed': False}
