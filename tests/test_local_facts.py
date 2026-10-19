from copy import deepcopy
import unittest

from runtime.local_facts import (hand_names, agree_hands, talent_facts, same_talent_facts,
                                 selected_talent_text, parse_rank, preparation_read_gate)


class LocalFactsTests(unittest.TestCase):
    def raw(self, name='牛魔', x=500, sha='a'):
        return {'image_sha256': sha * 64, 'regions': [
            {'name': 'hand_left', 'text': name, 'lines': [{'words': [
                {'text': name, 'x': x, 'y': 840, 'width': 40, 'height': 20}]}]},
            {'name': 'hand_right', 'text': '', 'lines': []}]}

    def texts(self):
        return {'name0': '加速成长', 'description0': '指定一名英雄的等级提高五级。',
                'name1': '双人游', 'description1': '随机获得2张2一3阶英雄牌。',
                'name2': '银算盘', 'description2': '出售场上英雄时随机提高等级。'}

    def test_exact_canonical_labels_only_are_candidates_without_input_permission(self):
        result = hand_names(self.raw())
        self.assertEqual(result['heroes'][0]['name'], '牛魔')
        self.assertFalse(result['execution_allowed']); self.assertFalse(result['game_postcondition_verified'])
        for name in ('未识别英雄', '大棒', '超级牛魔'):
            self.assertEqual(hand_names(self.raw(name))['heroes'], [])

    def test_separated_words_cannot_be_joined_across_cards(self):
        raw = self.raw(); words = raw['regions'][0]['lines'][0]['words']
        words[:] = [{'text': '孙', 'x': 500, 'y': 840, 'width': 12, 'height': 20},
                    {'text': '尚香', 'x': 518, 'y': 840, 'width': 24, 'height': 20}]
        self.assertEqual(hand_names(raw)['heroes'][0]['name'], '孙尚香')
        words[1]['x'] = 600
        self.assertEqual(hand_names(raw)['heroes'], [])

    def test_outside_label_band_and_malformed_word_boxes_do_not_become_cards(self):
        raw = self.raw(); raw['regions'][0]['lines'][0]['words'][0]['y'] = 700
        self.assertEqual(hand_names(raw)['heroes'], [])
        for key, value in [('x', float('nan')), ('height', -1), ('width', True), ('y', 860)]:
            raw = self.raw(); raw['regions'][0]['lines'][0]['words'][0][key] = value
            with self.assertRaises(ValueError): hand_names(raw)

    def test_both_named_regions_and_original_source_hash_are_required(self):
        raw = self.raw(); raw['regions'].pop()
        with self.assertRaises(ValueError): hand_names(raw)
        raw = self.raw(); raw['regions'][1]['name'] = 'hand_left'
        with self.assertRaises(ValueError): hand_names(raw)
        raw = self.raw(); raw['image_sha256'] = 'unknown'
        with self.assertRaises(ValueError): hand_names(raw)
        with self.assertRaises(ValueError): hand_names(self.raw(), ['Unsupported'])

    def test_two_frames_must_agree_nearby_and_exclude_already_deployed_names(self):
        first = hand_names(self.raw()); second = hand_names(self.raw(x=502, sha='b'))
        self.assertEqual(len(agree_hands(first, second, [])), 1)
        self.assertEqual(agree_hands(first, second, ['牛魔']), [])
        self.assertEqual(agree_hands(first, hand_names(self.raw(x=520, sha='b')), []), [])
        with self.assertRaises(ValueError): agree_hands(first, first, [])
        second['heroes'][0]['rect'] = [500, 791, 24, 38]
        with self.assertRaises(ValueError): agree_hands(first, second, [])

    def test_same_named_cards_in_two_positions_are_not_collapsed_into_one(self):
        raw = self.raw(); words = raw['regions'][0]['lines'][0]['words']
        words.append(dict(words[0], x=800))
        first = hand_names(raw); raw['image_sha256'] = 'b' * 64; second = hand_names(raw)
        self.assertEqual(len(agree_hands(first, second, [])), 2)

    def test_fixed_readable_lexical_rule_prefers_immediate_heroes_and_ties_leftmost(self):
        result = talent_facts(self.texts()); self.assertEqual(result['selected_index'], 1)
        self.assertFalse(result['execution_allowed'])
        values = self.texts(); values['description0'] = values['description1']
        self.assertEqual(talent_facts(values)['selected_index'], 0)

    def test_three_complete_stable_choices_are_required_instead_of_vacuous_zip(self):
        first = talent_facts(self.texts()); second = deepcopy(first)
        self.assertTrue(same_talent_facts(first, second))
        for rows in ([], first['candidates'][:2], [None, None, None]):
            second['candidates'] = rows; self.assertFalse(same_talent_facts(first, second))
        second = deepcopy(first); second['selected_index'] = 0
        self.assertFalse(same_talent_facts(first, second))
        values = self.texts(); values['description2'] = '?'
        with self.assertRaises(ValueError): talent_facts(values)

    def test_selected_text_requires_exact_name_effect_fragment_and_ordered_numbers(self):
        chosen = talent_facts(self.texts())['candidates'][1]
        fields = {'name': chosen['name'], 'description': chosen['description']}
        result = selected_talent_text(fields, chosen)
        self.assertTrue(result['text_matched']); self.assertFalse(result['selection_commit_verified'])
        self.assertFalse(result['rewards_verified'])
        for changes in ({'name': '银算盘'}, {'description': '随机获得3张2一2阶英雄牌。'}, {'description': '2张2一3'}):
            self.assertFalse(selected_talent_text(fields | changes, chosen)['text_matched'])

    def test_rank_text_retains_sixth_and_unknown_without_inventing_a_result(self):
        for text in ('第6名', '笋6名', '第六名'):
            self.assertEqual(parse_rank(text), 6)
        for text in ('第7名', '第16名', '?', '', None, '第6名 第1名'):
            self.assertIsNone(parse_rank(text))

    def test_preparation_reads_wait_reset_when_readable_and_latch_after_third_failure(self):
        gate = preparation_read_gate(None, '', 0)
        self.assertFalse(gate['ready']); self.assertFalse(gate['execution_allowed']); self.assertFalse(gate['stop'])
        gate = preparation_read_gate(None, '', gate['consecutive_unreadable'])
        self.assertFalse(gate['stop'])
        self.assertEqual(preparation_read_gate(5, '开战', gate['consecutive_unreadable'])['consecutive_unreadable'], 0)
        gate = preparation_read_gate(None, '', gate['consecutive_unreadable']); self.assertTrue(gate['stop'])
        self.assertTrue(preparation_read_gate(5, '开战', 3)['stop'])
        for streak in (-1, 4, True):
            with self.assertRaises(ValueError): preparation_read_gate(5, '开战', streak)


if __name__ == '__main__': unittest.main()
