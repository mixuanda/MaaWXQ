import unittest
from runtime.round_label import parse_round_label


class RoundLabelTests(unittest.TestCase):
    def test_only_full_or_abbreviated_round_unit_in_the_verified_roi_is_accepted(self):
        for text in ('第3回合','3回合','3 回','第 3 回'):
            self.assertEqual(parse_round_label(text),3)
        for text in ('3','0回合','100回合','第3回合39s','战斗3','回3','3回合确认',None,3):
            self.assertIsNone(parse_round_label(text))


if __name__=='__main__':unittest.main()
