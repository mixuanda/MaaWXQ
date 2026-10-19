from copy import deepcopy
import unittest
from runtime.slot_identity import template_registry, resolve_hand_slots


class SlotIdentityTests(unittest.TestCase):
    def templates(self):
        return [{'id': 'a-old', 'hero_id': 'hero-a', 'sha256': 'a' * 64, 'roi': [600, 794, 24, 38]},
                {'id': 'a-new', 'hero_id': 'hero-a', 'sha256': 'b' * 64, 'roi': [700, 794, 24, 38]},
                {'id': 'b', 'hero_id': 'hero-b', 'sha256': 'a' * 64, 'roi': [800, 794, 24, 38]}]

    def slot(self, slot_id='left', x=600):
        return {'slot_id': slot_id, 'bounds': [x, 790, 50, 60], 'frame_sha256': 'f' * 64,
                'scores': [{'template_id': key, 'score': value, 'frame_sha256': 'f' * 64}
                           for key, value in [('a-old', .928), ('a-new', .999), ('b', .5)]]}

    def test_alternate_template_of_same_hero_can_succeed_without_hiding_competitors(self):
        result = resolve_hand_slots('f' * 64, [self.slot()], self.templates())
        self.assertEqual(result[0]['hero_id'], 'hero-a'); self.assertFalse(result[0]['execution_allowed'])

    def test_same_image_different_rois_can_name_different_heroes_but_same_roi_cannot(self):
        self.assertEqual(len(template_registry(self.templates())), 3)
        rows = self.templates(); rows[2]['roi'] = rows[0]['roi']
        with self.assertRaisesRegex(ValueError, 'alias'): template_registry(rows)

    def test_different_heroes_competing_for_same_slot_remain_unknown(self):
        slot = self.slot(); slot['scores'][2]['score'] = .98
        self.assertIsNone(resolve_hand_slots('f' * 64, [slot], self.templates())[0]['hero_id'])

    def test_same_hero_in_two_physical_slots_keeps_two_slot_identities(self):
        result = resolve_hand_slots('f' * 64, [self.slot(), self.slot('right', 800)], self.templates())
        self.assertEqual([x['slot_id'] for x in result], ['left', 'right'])
        self.assertEqual([x['hero_id'] for x in result], ['hero-a', 'hero-a'])

    def test_missing_competitors_or_unbound_stale_scores_cannot_claim_a_slot(self):
        for change in ('missing', 'stale', 'duplicate', 'nan'):
            slot = self.slot()
            if change == 'missing': slot['scores'].pop()
            elif change == 'stale': slot['scores'][0]['frame_sha256'] = 'e' * 64
            elif change == 'duplicate': slot['scores'][0] = deepcopy(slot['scores'][1])
            else: slot['scores'][0]['score'] = float('nan')
            with self.subTest(change=change), self.assertRaises(ValueError): resolve_hand_slots('f' * 64, [slot], self.templates())

    def test_overlapping_or_duplicate_slot_ids_cannot_be_double_counted(self):
        for other in (self.slot(), self.slot('overlap', 610)):
            with self.assertRaises(ValueError): resolve_hand_slots('f' * 64, [self.slot(), other], self.templates())


if __name__ == '__main__': unittest.main()
