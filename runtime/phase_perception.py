"""Pure checks of the reviewed phase anchors; never authorizes game input."""
import math


def classify(frame):
    unknown = {'phase': 'unknown', 'confidence': None}
    if not isinstance(frame, dict) or not isinstance(frame.get('matches'), list):
        return unknown
    matches = {}
    for row in frame['matches']:
        if (not isinstance(row, dict) or not isinstance(row.get('name'), str) or row['name'] in matches
                or type(row.get('score')) not in (int, float) or not math.isfinite(row['score'])
                or not -1 <= row['score'] <= 1):
            return unknown
        matches[row['name']] = row['score']
    required = {'phase_ready', 'phase_start', 'own_portrait', 'one_unit',
                'battle_labels', 'battle_header', 'draft_preview'}
    required.update('price_' + str(i) for i in range(4))
    required.update('draft_bot_' + str(i) for i in range(1, 6))
    required.update('talent_footer_' + str(i) for i in range(1, 4))
    if not required <= matches.keys():
        return unknown
    m = matches
    winner, competitor = sorted(('phase_ready', 'phase_start'), key=lambda key: m[key], reverse=True)
    preparation = m[winner] >= .97 and m[winner] - m[competitor] >= .02
    shop = sum(m['price_' + str(i)] >= .97 for i in range(4)) >= 2
    own = m['own_portrait'] >= .985
    if own and preparation and shop:
        return {'phase': 'preparation', 'label': winner, 'one_unit_verified': m['one_unit'] >= .97,
                'confidence': m[winner]}
    draft_bots = sum(m['draft_bot_' + str(i)] >= .97 for i in range(1, 6))
    if m['draft_preview'] >= .97 and draft_bots >= 2:
        return {'phase': 'draft_preview', 'confidence': m['draft_preview'], 'visible_bot_labels': draft_bots}
    if all(m[key] >= .97 for key in ('talent_footer_1', 'talent_footer_2', 'talent_footer_3')):
        return {'phase': 'talent_selection', 'confidence': min(m['talent_footer_' + str(i)] for i in range(1, 4))}
    bars = frame.get('enemy_health_bars', 0)
    if type(bars) is not int or bars < 0:
        return unknown
    if (own and not preparation and m['battle_labels'] >= .97 and m['draft_preview'] < .97
            and (m['battle_header'] >= .97 or bars >= 1)):
        return {'phase': 'battle_or_resolution', 'confidence': m['battle_labels'],
                'evidence': 'resolution_flag' if m['battle_header'] >= .97 else 'enemy_health_bars',
                'enemy_health_bars': bars}
    return unknown
