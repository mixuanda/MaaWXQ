"""Synthetic feature records, no game captures/templates or input APIs."""
from copy import deepcopy
import unittest
from runtime.purchase_recognition import (classify_phase_labels,numeric_candidate,
                                         assess_purchase_features,ConsecutivePurchaseFrames)


def number(value):
    text=str(value)
    return {'Known':True,'Value':value,'Text':text,'Components':len(text),'Score':.99,'Margin':.2}


def frame(digest='a',at='2026-01-01T00:00:00Z'):
    names=['phase_ready','phase_start','own_portrait','currency_icon','empty_slot','round_header']+['price_'+str(i)for i in range(4)]+['hero_0','hero_1']
    matches=[{'name':name,'score':1 if name!='phase_start'else .954631}for name in names]
    return {'sha256':digest*64,'captured_at':at,'identity':{'identity_version':'fixture-game'},'matches':matches,
            'numbers':{'energy':number(6),'prices':[number(3)for _ in range(4)]}}


HEROES={'hero_0':{'slot':0,'hero_id':'fixture-A'},'hero_1':{'slot':1,'hero_id':'fixture-B'}}


class PurchaseRecognitionTests(unittest.TestCase):
    def test_competing_label_resolves_the_recorded_point_954631_confusion_without_lowering_threshold(self):
        value=frame();result=classify_phase_labels(value)
        self.assertEqual(result['label'],'phase_ready')
        self.assertGreaterEqual(result['score'],.97)
        rows={row['name']:row for row in value['matches']}
        rows['phase_start']['score']=1;rows['phase_ready']['score']=.954631
        self.assertEqual(classify_phase_labels(value)['label'],'phase_start')
        rows['phase_ready']['score']=.99
        self.assertEqual(classify_phase_labels(value)['status'],'unknown')
        value['matches'].pop(1)
        self.assertEqual(classify_phase_labels(value)['status'],'unknown')

    def test_full_features_need_numbers_shop_anchors_and_original_freshness(self):
        value=frame();at=value['captured_at']
        result=assess_purchase_features(value,HEROES,now=at,source_mode='live_capture')
        self.assertEqual(result['candidate']['hero_id'],'fixture-A')
        self.assertEqual((result['candidate']['balance'],result['candidate']['price']),(6,3))
        self.assertFalse(result['execution_allowed'])
        for case in ('unknown_energy','one_shop_price','portrait','duplicate','nan','ambiguous_hero','stale'):
            current=deepcopy(value);now=at;heroes=deepcopy(HEROES)
            if case=='unknown_energy':current['numbers']['energy']['Known']=False
            elif case=='one_shop_price':
                for record in current['numbers']['prices'][1:]:record['Known']=False
            elif case=='portrait':next(row for row in current['matches']if row['name']=='own_portrait')['score']=.98
            elif case=='duplicate':current['matches'].append(deepcopy(current['matches'][0]))
            elif case=='nan':current['matches'][0]['score']=float('nan')
            elif case=='ambiguous_hero':heroes['hero_1']['slot']=0
            elif case=='stale':now='2026-01-01T00:00:06Z'
            with self.subTest(case=case):
                self.assertIsNone(assess_purchase_features(current,heroes,now=now,source_mode='live_capture')['candidate'])

    def test_unknown_zero_and_inconsistent_numeric_payload_never_become_known_numbers(self):
        for case in ('unknown','text','components','score','margin','bool','oversize'):
            value=number(6)
            if case=='unknown':value.update(Known=False,Value=0)
            elif case=='text':value['Text']='8'
            elif case=='components':value['Components']=2
            elif case=='score':value['Score']=.89
            elif case=='margin':value['Margin']=.079
            elif case=='bool':value['Value']=True
            elif case=='oversize':value=number(100)
            with self.subTest(case=case):self.assertIsNone(numeric_candidate(value))
        self.assertEqual(numeric_candidate(number(0))['value'],0)

    def test_stability_requires_distinct_consecutive_same_offer_frames_and_clears_on_unknown(self):
        gate=ConsecutivePurchaseFrames();first=frame();second=frame('b','2026-01-01T00:00:01Z')
        def assess(value):return assess_purchase_features(value,HEROES,now=value['captured_at'],source_mode='live_capture')
        self.assertEqual(gate.observe(assess(first))['status'],'pending')
        self.assertEqual(gate.observe(assess(first))['status'],'pending')
        self.assertEqual(gate.observe(assess(second))['status'],'stable_candidate')
        gate.observe({'status':'unknown'})
        self.assertEqual(gate.observe(assess(second))['status'],'pending')
        third=frame('c','2026-01-01T00:00:02Z');third['numbers']['energy']=number(7)
        self.assertEqual(gate.observe(assess(third))['status'],'pending')
        replay=assess_purchase_features(frame('d','2026-01-01T00:00:03Z'),HEROES,now='2026-01-01T00:10:00Z')
        self.assertEqual(replay['source']['source_mode'],'saved_replay')
        self.assertEqual(gate.observe(replay)['status'],'pending')

    def test_malformed_transport_returns_unknown_without_reusing_old_candidates(self):
        for case in ('timestamp','match','hero_entry','components'):
            value=frame();heroes=deepcopy(HEROES)
            if case=='timestamp':value['captured_at']=None
            elif case=='match':value['matches'][0]=None
            elif case=='hero_entry':heroes['hero_0']=None
            elif case=='components':value['numbers']['energy']['Components']=True
            with self.subTest(case=case):
                result=assess_purchase_features(value,heroes,now='2026-01-01T00:00:00Z',source_mode='live_capture')
                self.assertEqual(result['status'],'unknown');self.assertIsNone(result['candidate'])


if __name__=='__main__':unittest.main()
