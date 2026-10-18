"""Synthetic hand matcher results exercise binding; no pixels or input APIs."""
from copy import deepcopy
import unittest
from runtime.hand_postcondition import make_snapshot,matcher_labels
from runtime.purchase import PurchaseHandler
from test_purchase import screen
from test_purchase_recognition import number


def after_record():
    return {'sha256':'c'*64,'captured_at':'2026-01-01T00:00:01Z',
            'identity':{'identity_version':'fixture-game','client':{'width':1450,'height':869}},
            'numbers':{'energy':number(25)},'hand_appearance':{
             'Known':True,'BeforeCount':2,'AfterCount':3,'Passive':{'Score':.99,'X':556,'Y':774,'Scale':1},
             'Equipment':{'Score':.99,'X':689.5,'Y':778,'Scale':1},
             'Received':{'Score':.96,'X':793,'Y':787,'Scale':.605},'DistinctHeroMargin':.76,
             'BeforePassiveHero':.1,'BeforeEquipmentHero':.2,'OfferScores':[.96,.1,.15,.2]}}


class HandPostconditionTests(unittest.TestCase):
    def setUp(self):
        self.handler=PurchaseHandler();self.plan=self.handler.prepare(screen(),now='2026-01-01T00:00:00Z')
        self.dispatched=None
        def executor(intent):self.dispatched=intent.to_dict();return {'sent':True,'cleanup_confirmed':True}
        self.handler.dispatch(self.plan['proposal_id'],screen('b','2026-01-01T00:00:00.500Z'),
                              now='2026-01-01T00:00:00.600Z',executor=executor)

    def test_spatial_transition_and_currency_reach_the_unchanged_dual_verifier(self):
        post=make_snapshot(self.dispatched,after_record(),source_sha256='b'*64,source_mode='live_capture')
        result=self.handler.verify(post,now='2026-01-01T00:00:01.100Z')
        self.assertEqual(result['status'],'purchase_verified')
        self.assertTrue(result['resource_delta_verified']);self.assertTrue(result['hero_appearance_verified'])
        self.assertEqual(result['actual_resource_delta'],3);self.assertFalse(result['blind_retry_allowed'])
        self.assertEqual(post['hand_slots'][0]['hero_id']['frame_sha256'],'c'*64)

    def test_replay_stale_frames_and_wrong_actual_dispatch_source_cannot_verify(self):
        replay=make_snapshot(self.dispatched,after_record(),source_sha256='b'*64)
        self.assertEqual(replay['frame']['source_mode'],'saved_replay')
        self.assertEqual(self.handler.verify(replay,now='2026-01-01T00:00:01Z')['status'],'unverified_stop')
        with self.assertRaises(ValueError):make_snapshot(self.plan['selected'],after_record(),source_sha256='b'*64,source_mode='live_capture')
        live=make_snapshot(self.dispatched,after_record(),source_sha256='b'*64,source_mode='live_capture')
        self.assertEqual(self.handler.verify(live,now='2026-01-01T00:00:07Z')['status'],'unverified_stop')

    def test_known_flag_cannot_waive_the_independent_art_predicates(self):
        for case in ('passive','equipment','received','margin','old_hero','count','location','scale','offer_scores','currency','nan','identity','geometry','time','reused','source_mode'):
            value=after_record();hand=value['hand_appearance']
            if case in ('passive','equipment','received'):hand[case.capitalize()]['Score']=.91
            elif case=='margin':hand['DistinctHeroMargin']=.11
            elif case=='old_hero':hand['BeforePassiveHero']=.75
            elif case=='count':hand['AfterCount']=4
            elif case=='location':hand['Received']['X']=900
            elif case=='scale':hand['Received']['Scale']=.7
            elif case=='offer_scores':hand['OfferScores']=[.2,.1,.15,.2]
            elif case=='currency':value['numbers']['energy']['Known']=False
            elif case=='nan':hand['Received']['Score']=float('nan')
            elif case=='identity':value['identity']['identity_version']='foreign-game'
            elif case=='geometry':value['identity']['client']['width']=1920
            elif case=='time':value['captured_at']='2026-01-01T00:00:00.400Z'
            elif case=='reused':value['source_capture_reused']=True
            elif case=='source_mode':value['source_mode']='saved_replay'
            with self.subTest(case=case),self.assertRaises(ValueError):
                make_snapshot(self.dispatched,value,source_sha256='b'*64,source_mode='live_capture')

    def test_currency_delta_is_still_checked_by_core_after_valid_art(self):
        value=after_record();value['numbers']['energy']=number(24)
        post=make_snapshot(self.dispatched,value,source_sha256='b'*64,source_mode='live_capture')
        result=self.handler.verify(post,now='2026-01-01T00:00:01Z')
        self.assertTrue(result['hero_appearance_verified']);self.assertFalse(result['resource_delta_verified'])
        self.assertEqual(result['status'],'unverified_stop')

    def test_unknown_offer_labels_stay_distinct_and_known_duplicates_share_ascii_identity(self):
        labels=matcher_labels(['fixture-hero','fixture-hero',None,'unknown'])
        self.assertEqual(labels[0],labels[1]);self.assertNotEqual(labels[2],labels[3])
        self.assertTrue(all(label.isascii()and "'"not in label for label in labels))
        self.assertEqual(len(set(matcher_labels([None]*4))),4)
        with self.assertRaises(ValueError):matcher_labels(['only-one'])


if __name__=='__main__':unittest.main()
