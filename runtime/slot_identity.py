"""Distinct current slots and reviewed template identities; no input APIs."""
import math


def _sha(value):
    return isinstance(value, str) and len(value) == 64 and all(c in '0123456789abcdef' for c in value)


def _label(value):
    return isinstance(value, str) and 0 < len(value) <= 256 and value == value.strip() and value.casefold() not in ('', '?', 'unknown')


def template_registry(rows):
    """An image hash alone is insufficient: different heroes can share an image.

    Each reviewed template binds hero, original image and exact fingerprint ROI.
    The caller must independently validate the original bytes/visual semantics.
    """
    if not isinstance(rows, list) or not 2 <= len(rows) <= 64:
        raise ValueError('bounded_competing_template_catalog_required')
    registry = {}; regions = {}
    for row in rows:
        if not isinstance(row, dict) or not _label(row.get('id')) or not _label(row.get('hero_id')) or not _sha(row.get('sha256')):
            raise ValueError('bound_template_identity_required')
        rect = row.get('roi')
        if (not isinstance(rect, list) or len(rect) != 4 or any(type(v) is not int for v in rect)
                or rect[2:] != [24, 38] or not 280 <= rect[0] <= 1216 or not 776 <= rect[1] <= 831):
            raise ValueError('reviewed_hand_fingerprint_roi_required')
        key = (row['sha256'], tuple(rect))
        if row['id'] in registry or (key in regions and regions[key] != row['hero_id']):
            raise ValueError('template_alias_or_duplicate_identity')
        regions[key] = row['hero_id']; registry[row['id']] = dict(row, roi=tuple(rect))
    if len({row['hero_id'] for row in registry.values()}) < 2:
        raise ValueError('distinct_hero_competitors_required')
    return registry


def resolve_hand_slots(frame_sha256, slots, templates):
    """Resolve complete per-slot comparisons; do not coalesce separate cards.

    Global best-match rows without current-slot bounds/coverage are insufficient.
    Multiple templates of one hero compete as one identity inside the same slot;
    two physical cards of that hero still retain two different slot IDs.
    """
    registry = template_registry(templates)
    if not _sha(frame_sha256) or not isinstance(slots, list) or not 1 <= len(slots) <= 16:
        raise ValueError('bounded_current_slot_observations_required')
    seen = set(); rectangles = []; result = []
    for slot in slots:
        if (not isinstance(slot, dict) or not _label(slot.get('slot_id')) or slot['slot_id'] in seen
                or slot.get('frame_sha256') != frame_sha256):
            raise ValueError('distinct_bound_slot_id_required')
        rect = slot.get('bounds')
        if (not isinstance(rect, list) or len(rect) != 4 or any(type(v) is not int for v in rect)
                or not 260 <= rect[0] < rect[0] + rect[2] <= 1250
                or not 760 <= rect[1] < rect[1] + rect[3] <= 869 or not 1 <= rect[2] <= 200 or not 1 <= rect[3] <= 109):
            raise ValueError('bounded_visible_hand_slot_required')
        for old in rectangles:
            if max(old[0], rect[0]) < min(old[0] + old[2], rect[0] + rect[2]) and max(old[1], rect[1]) < min(old[1] + old[3], rect[1] + rect[3]):
                raise ValueError('overlapping_slot_identity_ambiguous')
        seen.add(slot['slot_id']); rectangles.append(rect)
        scores = slot.get('scores'); scored = {}; heroes = {}
        if not isinstance(scores, list) or len(scores) != len(registry):
            raise ValueError('complete_per_slot_competitor_coverage_required')
        for row in scores:
            if (not isinstance(row, dict) or not _label(row.get('template_id')) or row['template_id'] not in registry or row['template_id'] in scored
                    or row.get('frame_sha256') != frame_sha256 or type(row.get('score')) not in (int, float)
                    or not math.isfinite(row['score']) or not -1 <= row['score'] <= 1):
                raise ValueError('invalid_current_slot_score')
            scored[row['template_id']] = row['score']; hero = registry[row['template_id']]['hero_id']
            heroes[hero] = max(heroes.get(hero, -1), row['score'])
        ordered = sorted(heroes.items(), key=lambda item: item[1], reverse=True)
        winner, score = ordered[0]; margin = score - ordered[1][1]
        known = score >= .94 and margin >= .10
        result.append({'slot_id': slot['slot_id'], 'frame_sha256': frame_sha256, 'bounds': list(rect),
                       'hero_id': winner if known else None, 'score': score, 'distinct_hero_margin': margin,
                       'execution_allowed': False, 'game_postcondition_verified': False})
    return result
