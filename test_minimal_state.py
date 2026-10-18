import unittest
from runtime.minimal_state import extract,REGIONS

class MinimalStateTests(unittest.TestCase):
    def setUp(self):
        self.frame={'image':'synthetic-test-only.png','sha256':'a'*64,'identity':{'identity_version':'test'},'captured_at':'2026-01-01T00:00:00+00:00'}
        self.state={'scene':'battle_controls','match_started':True,'frame_sha256':'a'*64}
    def bundle(self,key,text):
        return {'roi':{'source_sha256':'a'*64,'image_sha256':'b'*64,'source_rect':REGIONS[key]},'ocr':{'image_sha256':'b'*64,'status':'recognized','text':text}}
    def test_shop_yixing_is_not_selected_chess_player_and_empty_board_is_not_inferred(self):
        r=extract(self.frame,self.state,{'shop_2_name':self.bundle('shop_2_name','弈 星'),'energy':self.bundle('energy','28')},now='2026-01-01T00:00:00+00:00')
        self.assertEqual(r['shop']['slots'][1]['name']['candidate'],'弈星')
        self.assertEqual(r['resources']['energy']['candidate'],28)
        self.assertIsNone(r['resources']['energy']['value']);self.assertIsNone(r['selection']['confirmed']['value'])
        self.assertIsNone(r['board']['entities']);self.assertFalse(r['input_allowed'])
    def test_wrong_hash_position_or_future_is_rejected(self):
        for change in ('hash','position'):
            b=self.bundle('energy','28')
            if change=='hash':b['ocr']['image_sha256']='c'*64
            else:b['roi']['source_rect']=(0,0,20,20)
            with self.assertRaises(ValueError):extract(self.frame,self.state,{'energy':b},now='2026-01-01T00:00:00Z')
        with self.assertRaises(ValueError):extract(self.frame,self.state,{},now='2025-12-31T23:59:59Z')
    def test_replay_keeps_age_and_malformed_ocr_unknown(self):
        r=extract(self.frame,self.state,{'round':self.bundle('round','第 4 回 台 45s'),'energy':self.bundle('energy','2B')},now='2026-01-01T01:00:00Z')
        self.assertEqual(r['age_seconds'],3600);self.assertIsNone(r['round']['candidate']);self.assertIsNone(r['resources']['energy']['candidate'])
    def test_round_and_timer_do_not_invent_phase(self):
        r=extract(self.frame,self.state,{'round':self.bundle('round','第 4 回合 45s')},now='2026-01-01T00:00:00Z')
        self.assertEqual(r['round']['candidate'],4);self.assertEqual(r['timer_seconds']['candidate'],45)
        self.assertIsNone(r['phase']['value']);self.assertFalse(r['fresh_for_input'])

if __name__=='__main__':unittest.main()
