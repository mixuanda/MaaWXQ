"""Bounded local OCR text candidates; no capture, input, model or network APIs."""
import math
import re

from runtime.transition_verification import _sha, compact

HERO_NAMES = ('墨子', '大乔', '姜子牙', '嬴政', '孙尚香', '孙膑', '干将莫邪', '弈星', '曜', '李元芳',
              '牛魔', '狂铁', '猪八戒', '白起', '芈月', '苏烈', '蔡文姬', '镜', '马可波罗', '鬼谷子')
HAND_REGIONS = {'hand_left': [280, 839, 650, 30], 'hand_right': [900, 839, 350, 30]}
TALENT_REGIONS = {label + str(i): rect for i, x in enumerate([380, 642, 905]) for label, rect in
                  [('name', [x, 415, 210, 35]), ('description', [x, 465, 210, 75])]}


def chinese(value):
    return ''.join(re.findall(r'[\u4e00-\u9fff]', value))


def _word(word):
    if not isinstance(word, dict) or not isinstance(word.get('text'), str) or not 0 < len(word['text']) <= 128:
        return False
    if any(type(word.get(k)) not in (int, float) or not math.isfinite(word[k]) for k in ('x', 'y', 'width', 'height')):
        return False
    return (0 <= word['x'] < word['x'] + word['width'] <= 1450
            and 0 <= word['y'] < word['y'] + word['height'] <= 869)


def hand_names(raw, lexicon=HERO_NAMES):
    """Read exact labels in the hand-name band, without certifying hero cards.

    OCR producers must validate source bytes, ROIs, scale and original geometry.
    A name/position candidate cannot replace current art, ownership or slot checks.
    """
    if not isinstance(lexicon, (list, tuple, set, frozenset)) or not lexicon or not set(lexicon) <= set(HERO_NAMES):
        raise ValueError('reviewed_canonical_hero_lexicon_required')
    if not isinstance(raw, dict) or not _sha(raw.get('image_sha256')):
        raise ValueError('hand_ocr_source_hash_required')
    regions = raw.get('regions')
    if (not isinstance(regions, list) or len(regions) != 2
            or any(not isinstance(r, dict) or not isinstance(r.get('name'), str) for r in regions)
            or {r['name'] for r in regions} != set(HAND_REGIONS)):
        raise ValueError('both_hand_name_regions_required')
    found = []; labels = []
    for region in regions:
        text = compact(region.get('text')); lines = region.get('lines')
        if text is None or not isinstance(lines, list) or len(lines) > 32:
            raise ValueError('bounded_hand_ocr_lines_required')
        labels.append({'region': region['name'], 'text': text})
        for line in lines:
            words = line.get('words') if isinstance(line, dict) else None
            if not isinstance(words, list) or len(words) > 64 or any(not _word(w) for w in words):
                raise ValueError('bounded_absolute_ocr_word_boxes_required')
            words = sorted(words, key=lambda w: w['x'])
            for start in range(len(words)):
                text = ''
                for end in range(start, min(start + 5, len(words))):
                    word = words[end]
                    if end > start and not -2 <= word['x'] - (words[end-1]['x'] + words[end-1]['width']) <= 14:
                        break
                    text += compact(word['text'])
                    left = words[start]['x']; right = word['x'] + word['width']; center = (left + right) / 2
                    if (text not in lexicon or not 300 <= center <= 1228 or not 4 <= right - left <= 105
                            or not all(838 <= w['y'] < 869 for w in words[start:end+1])):
                        continue
                    if any(h['name'] == text and abs(h['center_x'] - center) < 10 for h in found):
                        continue
                    found.append({'name': text, 'center_x': center,
                                  'name_box': [left, min(w['y'] for w in words[start:end+1]), right-left,
                                               max(w['height'] for w in words[start:end+1])],
                                  'rect': [round(center)-12, 791, 24, 38]})
    if len(found) > 32:
        raise ValueError('bounded_hand_name_candidates_required')
    return {'heroes': sorted(found, key=lambda h: h['center_x']), 'raw_labels': labels,
            'frame_sha256': raw['image_sha256'], 'confidence_calibrated': False,
            'execution_allowed': False, 'game_postcondition_verified': False}


def agree_hands(first, second, deployed):
    """Two distinct source hashes and nearby exact labels yield candidates only."""
    for result in (first, second):
        if not isinstance(result, dict) or not _sha(result.get('frame_sha256')) or not isinstance(result.get('heroes'), list):
            raise ValueError('two_bound_hand_candidate_sets_required')
        if len(result['heroes']) > 32 or any(not isinstance(h, dict) or h.get('name') not in HERO_NAMES
                or type(h.get('center_x')) not in (int, float) or not math.isfinite(h['center_x'])
                or not 300 <= h['center_x'] <= 1228 or h.get('rect') != [round(h['center_x'])-12, 791, 24, 38]
                for h in result['heroes']):
            raise ValueError('bounded_current_hand_candidates_required')
    if first['frame_sha256'] == second['frame_sha256']:
        raise ValueError('two_distinct_hand_frames_required')
    if not isinstance(deployed, (list, tuple, set, frozenset)) or len(deployed) > 5 or any(n not in HERO_NAMES for n in deployed):
        raise ValueError('bounded_current_deployed_names_required')
    return [dict(h) for h in second['heroes'] if h['name'] not in deployed and any(
        x['name'] == h['name'] and abs(x['center_x']-h['center_x']) <= 3 for x in first['heroes'])]


def talent_facts(values):
    """Fixed lexical ordering of three readable effects; no strength estimate."""
    if not isinstance(values, dict):
        raise ValueError('three_readable_talent_texts_required')
    candidates = []
    for i in range(3):
        name = compact(values.get('name'+str(i))); desc = compact(values.get('description'+str(i)))
        if name is None or desc is None or not 2 <= len(chinese(name)) <= 12 or len(chinese(desc)) < 8:
            raise ValueError('local_talent_text_unreadable')
        fragments = sorted(re.findall(r'[\u4e00-\u9fff]{4,}', desc), key=lambda text: -len(text))
        if not fragments:
            raise ValueError('local_talent_effect_fragment_missing')
        score = 0
        if desc.startswith(('获得', '随机获得')):
            score = 3 if '英雄' in desc and '英雄等级' not in desc else 2
        elif any(key in desc for key in ('能量', '攻速', '伤害', '等级')):
            score = 1
        candidates.append({'name': name, 'description': desc, 'verification_fragment': fragments[0][:8], 'lexical_score': score})
    return {'candidates': candidates, 'selected_index': max(range(3), key=lambda i: (candidates[i]['lexical_score'], -i)),
            'policy': 'readable immediate-gain lexical priority, then leftmost; no hidden stats', 'execution_allowed': False}


def same_talent_facts(first, second):
    """Empty/truncated zip comparisons must never count as stable three choices."""
    for value in (first, second):
        if (not isinstance(value, dict) or not isinstance(value.get('candidates'), list) or len(value['candidates']) != 3
                or type(value.get('selected_index')) is not int or value['selected_index'] not in range(3)
                or any(not isinstance(row, dict) or not compact(row.get('name')) or not compact(row.get('description'))
                       for row in value['candidates'])):
            return False
    return first['selected_index'] == second['selected_index'] and all(
        x['name'] == y['name'] and x['description'] == y['description']
        for x, y in zip(first['candidates'], second['candidates']))


def selected_talent_text(fields, chosen):
    """Text-only overlap/ordered-numeral check; not selection or reward proof."""
    if not isinstance(fields, dict) or not isinstance(chosen, dict):
        raise ValueError('chosen_and_selected_texts_required')
    name = compact(fields.get('name')); desc = compact(fields.get('description'))
    expected = compact(chosen.get('name')); before = compact(chosen.get('description'))
    if not name or not desc or not expected or not before:
        return {'text_matched': False, 'execution_allowed': False}
    body = before.replace(expected, '')
    fragments = {text[i:i+4] for text in re.findall(r'[\u4e00-\u9fff]{4,}', body) for i in range(len(text)-3)}
    shared = sorted(text for text in fragments if text in desc)
    old_numbers = re.findall(r'\d+', before); new_numbers = re.findall(r'\d+', desc)
    return {'text_matched': name == expected and bool(shared) and old_numbers == new_numbers,
            'name': name, 'description': desc, 'shared_effect_fragments': shared,
            'numbers_before': old_numbers, 'numbers_after': new_numbers,
            'execution_allowed': False, 'selection_commit_verified': False, 'rewards_verified': False}


def parse_rank(value):
    value = compact(value)
    matches = re.findall(r'(?<!\d)第?([1-6一二三四五六])名', value) if value else []
    if len(matches) != 1:
        return None
    return int(matches[0]) if matches[0].isdigit() else '一二三四五六'.index(matches[0]) + 1


def preparation_read_gate(round_number, button, consecutive_unreadable):
    """Three unreadable preconditions latch off; valid preconditions grant no input."""
    if type(consecutive_unreadable) is not int or not 0 <= consecutive_unreadable <= 3:
        raise ValueError('bounded_preparation_read_streak_required')
    ready = (consecutive_unreadable < 3 and type(round_number) is int and 1 <= round_number <= 99
             and button in ('准备', '开战', '取消'))
    streak = 0 if ready else min(3, consecutive_unreadable + 1)
    return {'ready': ready, 'consecutive_unreadable': streak, 'stop': streak == 3,
            'decision': 'ready' if ready else 'input_stop' if streak == 3 else 'wait_for_new_frame_no_input',
            'execution_allowed': False}
