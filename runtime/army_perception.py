"""Read-only army pixel candidates and retained visual-review bindings.

This module never promotes manual review to an automatic deployment result.
Population template similarity is not a numeric population observation.
"""
from copy import deepcopy
import hashlib
import math

from runtime.phase_perception import classify
from strategy.codec import timestamp


def _object(value):
    return value if isinstance(value, dict) else {}


def _sha(value):
    return isinstance(value, str) and len(value) == 64 and all(c in '0123456789abcdef' for c in value)


def _number(value, low, high):
    return type(value) in (int, float) and math.isfinite(value) and low <= value <= high


def hand_match_candidate(match):
    """Check the observed 24x38 hand fingerprint, not the hero's name/ownership."""
    m = _object(match)
    scales = (.85, .90, .925, .95, .975, 1, 1.025, 1.05, 1.075, 1.10, 1.15)
    if (m.get('Known') is not True or not _number(m.get('Score'), .94, 1)
            or not _number(m.get('Margin'), .10, 1)
            or not any(_number(m.get('Scale'), scale - 1e-9, scale + 1e-9) for scale in scales)
            or any(type(m.get(key)) is not int for key in ('X', 'Y', 'Width', 'Height'))
            or (m['Width'], m['Height']) != (24, 38)
            or not 277 <= m['X'] <= 1219 or not 776 <= m['Y'] <= 816):
        return None
    return {key: m[key] for key in ('Score', 'Margin', 'Scale', 'X', 'Y', 'Width', 'Height')} | {
        'center': [round(m['X'] + m['Width'] * m['Scale'] / 2),
                   round(m['Y'] + m['Height'] * m['Scale'] / 2)],
        'hero_id': None, 'ownership_verified': False}


def assess_army_frame(frame, *, reference_sha256s, now, source_mode='saved_replay'):
    """Retain bounded current template candidates; never return an input intent.

    The producer must hash the actual hand/board/population reference bitmaps
    and bind all pixel results to the original frame. Reference hashes alone
    do not prove the reference contents or the current roster.
    """
    if source_mode not in ('saved_replay', 'live_capture'):
        raise ValueError('explicit_army_source_mode_required')
    frame = _object(frame); identity = _object(frame.get('identity')); client = _object(identity.get('client'))
    reasons = []
    if (not _sha(frame.get('sha256')) or any(not isinstance(identity.get(key), str) or not identity[key].strip()
                                           for key in ('identity_version', 'geometry_version'))
            or type(client.get('width')) is not int or type(client.get('height')) is not int
            or (client['width'], client['height']) != (1450, 869)):
        reasons.append('invalid_army_frame_binding')
    if frame.get('source_mode', source_mode) != source_mode:
        reasons.append('source_mode_mismatch')
    if source_mode == 'live_capture' and frame.get('source_capture_reused') is True:
        reasons.append('reused_frame_cannot_be_live')
    try:
        if not 0 <= (timestamp(now) - timestamp(frame['captured_at'])).total_seconds() <= 5:
            reasons.append('army_frame_stale_or_future')
    except (KeyError, ValueError, TypeError, AttributeError):
        reasons.append('invalid_army_capture_time')
    refs = _object(reference_sha256s)
    if set(refs) != {'hand', 'board', 'population'} or not all(_sha(value) for value in refs.values()):
        reasons.append('bound_template_reference_hashes_required')
    phase = classify(frame)
    if phase['phase'] != 'preparation':
        reasons.append('positive_preparation_required')
    pixels = _object(frame.get('army')); hand = hand_match_candidate(pixels.get('hand'))
    if hand is None:
        reasons.append('unproven_hand_fingerprint')
    similarities = {key: pixels.get(key) if _number(pixels.get(key), -1, 1) else None
                    for key in ('empty', 'population', 'capacity')}
    if any(value is None or value < .97 for value in similarities.values()):
        reasons.append('empty_cell_or_population_template_unproven')
    return {'schema': 'army-perception/1', 'status': 'army_perception_candidate' if not reasons else 'army_perception_unknown',
            'reasons': reasons, 'frame_sha256': frame.get('sha256'), 'captured_at': frame.get('captured_at'),
            'source_mode': source_mode, 'reference_sha256s': deepcopy(refs), 'phase': phase,
            'hand_candidate': hand, 'template_similarities': similarities,
            'population_value': None, 'capacity_value': None, 'roster_verified': False,
            'execution_allowed': False, 'game_postcondition_verified': False, 'blind_retry_allowed': False}


def bind_roster_review(review, image_bytes):
    """Bind retained original bytes to historical manual review, without input.

    A surviving digest or capture record cannot replace missing original bytes.
    The result does not certify the review's visual semantics, a current match
    roster, fresh action eligibility or an automatic game postcondition.
    """
    r = _object(review); reasons = []
    original_status = r.get('automatic_status_preserved', r.get('original_status'))
    if original_status not in ('unit_identity_unverified_no_retry', 'unit_identity_verified_population_requires_review'):
        reasons.append('original_automatic_status_required')
    if not _sha(r.get('sha256')):
        reasons.append('original_review_image_hash_required')
    missing = image_bytes is None
    original_available = (isinstance(image_bytes, bytes) and 0 < len(image_bytes) <= 16 * 1024 * 1024
                          and hashlib.sha256(image_bytes).hexdigest() == r.get('sha256'))
    if missing:
        reasons.append('original_review_image_unavailable')
    elif not isinstance(image_bytes, bytes) or not 0 < len(image_bytes) <= 16 * 1024 * 1024:
        reasons.append('bounded_original_review_bytes_required')
    elif hashlib.sha256(image_bytes).hexdigest() != r.get('sha256'):
        reasons.append('original_review_image_changed')
    before, after, capacity = (r.get(key) for key in ('population_before', 'population_after', 'capacity'))
    roster = r.get('known_roster')
    if (any(type(value) is not int for value in (before, after, capacity))
            or not 1 <= before < after <= 4 or after != before + 1 or capacity != 5):
        reasons.append('reviewed_population_transition_required')
    valid_roster = (isinstance(roster, list) and type(after) is int and len(roster) == after
                    and all(isinstance(hero, str) and 0 < len(hero) <= 128 and hero.strip()
                            and hero.strip().casefold() not in ('unknown', '?') for hero in roster))
    if valid_roster:
        valid_roster = len(set(roster)) == len(roster) and r.get('confirmed_name') in roster
    if not valid_roster:
        reasons.append('distinct_reviewed_roster_required')
    if r.get('method') != 'assistant_visual_image_review':
        reasons.append('explicit_visual_review_method_required')
    return {'status': 'review_source_unavailable' if missing else 'retained_visual_review_bound' if not reasons else 'review_unbound',
            'reasons': reasons, 'original_automatic_status': original_status,
            'image_sha256': r.get('sha256'), 'original_image_available': original_available,
            'population_after': after, 'capacity': capacity,
            'known_roster': deepcopy(roster) if valid_roster else None,
            'review_method': r.get('method'), 'execution_allowed': False,
            'game_postcondition_verified': False, 'blind_retry_allowed': False}
