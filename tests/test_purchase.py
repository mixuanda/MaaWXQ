"""Synthetic screen fixtures exercise purchase contracts, never native input."""
from copy import deepcopy
from dataclasses import replace
from unittest.mock import Mock
import unittest
from strategy.codec import timestamp
from strategy.purchase import rank_purchases,ScoreTerm,verify_purchase
from runtime.purchase import PurchaseHandler
from backends.purchase_click import PurchaseClickBroker,PurchaseClickEvidence,guarded_executor
from backends.game_click import Binding,NativeUnavailable
from test_win32_single_click import observed,FakePort


def screen(digest='a',at='2026-01-01T00:00:00Z',balance=28,after=False):
    frame={'sha256':digest*64,'captured_at':at,'identity_version':'fixture-game','match_id':'fixture-custom',
           'source_kind':'screen_recognition','source_mode':'live_capture'}
    def seen(value,ref):
        return {'status':'observed','value':value,'confidence':.95,'frame_sha256':frame['sha256'],
                'observed_at':at,'evidence_ref':'fixture-region:'+ref}
    return {'schema':'purchase-screen/1','frame':frame,'mode':seen('custom','mode'),
            'phase':seen('purchase_enabled','phase'),'currencies':[{'id':'energy','balance':seen(balance,'balance')},
                          {'id':'other_coin','balance':seen(999,'other-balance')}],
            'offers':[{'id':'shop-1','hero_id':seen('fixture-A','hero'),'currency_id':seen('energy','currency'),
                       'effective_price':seen(3,'price'),'purchasable':seen(True,'enabled'),'target':seen([50,40],'target')}],
            'hand_slots':[{'id':'hand-1','empty':seen(not after,'empty'),'legal':seen(True,'legal'),
                           'hero_id':seen('fixture-A'if after else'no_hero','hand-hero')}]}


class PurchaseTests(unittest.TestCase):
    def test_confirmed_currency_price_and_slot_produce_a_deterministic_candidate(self):
        result=rank_purchases(screen(),now='2026-01-01T00:00:00Z')
        self.assertEqual(result['status'],'candidate')
        selected=result['candidates'][0]
        self.assertEqual((selected.hero_id,selected.effective_price,selected.balance,selected.currency_id),('fixture-A',3,28,'energy'))
        self.assertEqual(selected.score,-3)
        self.assertIn('minimize_confirmed_price',[term.name for term in selected.score_terms])
        self.assertEqual(selected.empty_legal_slots,('hand-1',))
        self.assertFalse(result['execution_allowed'])

    def test_unknown_changed_or_foreign_bound_fields_cannot_spend(self):
        for change in ('price','currency','phase','free','legal','stale_field','other_hash','insufficient','wrong_currency','future','old'):
            value=screen();now='2026-01-01T00:00:00Z'
            if change in ('price','currency'):
                key='effective_price'if change=='price'else'currency_id'
                value['offers'][0][key].update(status='candidate',value=None,confidence=None)
            elif change=='phase':value['phase']['value']='combat'
            elif change in ('free','legal'):value['hand_slots'][0]['empty'if change=='free'else'legal']['value']=False
            elif change=='stale_field':value['currencies'][0]['balance']['observed_at']='2025-12-31T23:59:59Z'
            elif change=='other_hash':value['offers'][0]['target']['frame_sha256']='b'*64
            elif change=='insufficient':value['currencies'][0]['balance']['value']=2
            elif change=='wrong_currency':value['offers'][0]['currency_id']['value']='unobserved_coin'
            elif change=='future':now='2025-12-31T23:59:59Z'
            elif change=='old':now='2026-01-01T00:00:06Z'
            with self.subTest(change=change):self.assertEqual(rank_purchases(value,now=now)['status'],'stop')
        self.assertEqual(rank_purchases(screen(),now='2026-01-01T00:00:00Z',max_age=60)['status'],'stop')

    def test_explicit_hero_score_can_extend_cost_score_without_game_stat_defaults(self):
        value=screen();other=deepcopy(value['offers'][0]);other['id']='shop-2'
        other['hero_id']['value']='fixture-B';other['effective_price']['value']=4;value['offers'].append(other)
        def scorer(offer):return (ScoreTerm('reviewed-fixture-link',10 if offer['hero_id']=='fixture-B'else 0,'test-rule:link'),)
        result=rank_purchases(value,now=value['frame']['captured_at'],scorer=scorer)
        self.assertEqual(result['candidates'][0].hero_id,'fixture-B')
        self.assertEqual(result['candidates'][0].score,6)
        self.assertEqual(result['candidates'][0].score_terms[-1].source_reference,'test-rule:link')

    def test_dispatch_rechecks_fresh_dynamic_fields_and_is_one_shot(self):
        handler=PurchaseHandler();plan=handler.prepare(screen(),now='2026-01-01T00:00:00Z')
        fresh=screen('c','2026-01-01T00:00:00.500Z')
        execute=Mock(return_value={'sent':True,'cleanup_confirmed':True})
        receipt=handler.dispatch(plan['proposal_id'],fresh,now='2026-01-01T00:00:00.600Z',executor=execute)
        self.assertEqual(receipt['source_frame_sha256'],'c'*64)
        self.assertEqual(execute.call_count,1)
        self.assertEqual(execute.call_args.args[0].expires_at,plan['selected']['expires_at'])
        result=handler.verify(screen('b','2026-01-01T00:00:01Z',25,True),now='2026-01-01T00:00:01Z')
        self.assertEqual(result['status'],'purchase_verified')
        self.assertTrue(result['resource_delta_verified']);self.assertTrue(result['hero_appearance_verified'])
        with self.assertRaisesRegex(ValueError,'no_retry'):
            handler.dispatch(plan['proposal_id'],fresh,now='2026-01-01T00:00:01Z',executor=execute)

    def test_dynamic_change_replay_or_expiry_never_calls_executor(self):
        for change in ('price','balance','hero','slot','replay','expiry'):
            handler=PurchaseHandler();before=screen();fresh=screen('c','2026-01-01T00:00:00.500Z')
            if change=='replay':before['frame']['source_mode']='saved_replay'
            plan=handler.prepare(before,now='2026-01-01T00:00:00Z');execute=Mock()
            if change=='price':fresh['offers'][0]['effective_price']['value']=4
            elif change=='balance':fresh['currencies'][0]['balance']['value']=29
            elif change=='hero':fresh['offers'][0]['hero_id']['value']='fixture-B'
            elif change=='slot':fresh['hand_slots'][0]['legal']['value']=False
            with self.subTest(change=change),self.assertRaises(ValueError):
                handler.dispatch(plan['proposal_id'],fresh,now='2026-01-01T00:00:06Z'if change=='expiry'else'2026-01-01T00:00:01Z',executor=execute)
            execute.assert_not_called()

    def test_each_postcondition_is_required_and_same_old_frame_is_not_proof(self):
        intent=rank_purchases(screen(),now='2026-01-01T00:00:00Z')['candidates'][0]
        for change in ('delta','hero','hash','time','identity','foreign_field','duplicate'):
            after=screen('b','2026-01-01T00:00:01Z',25,True)
            if change=='delta':after['currencies'][0]['balance']['value']=24
            elif change=='hero':after['hand_slots'][0]['hero_id']['value']='fixture-B'
            elif change=='hash':after['frame']['sha256']='a'*64
            elif change=='time':after['frame']['captured_at']='2026-01-01T00:00:00Z'
            elif change=='identity':after['frame']['identity_version']='other-game'
            elif change=='foreign_field':after['hand_slots'][0]['hero_id']['frame_sha256']='c'*64
            elif change=='duplicate':after['hand_slots'].append(deepcopy(after['hand_slots'][0]))
            with self.subTest(change=change):
                result=verify_purchase(intent,after,now='2026-01-01T00:00:01Z')
                self.assertEqual(result['status'],'unverified_stop');self.assertFalse(result['blind_retry_allowed'])

    def test_uncertain_executor_cannot_retry_or_claim_verified(self):
        for receipt in (None,{'sent':False,'cleanup_confirmed':True},{'sent':True,'cleanup_confirmed':False}):
            handler=PurchaseHandler();plan=handler.prepare(screen(),now='2026-01-01T00:00:00Z')
            with self.assertRaises(RuntimeError):
                handler.dispatch(plan['proposal_id'],screen(),now='2026-01-01T00:00:00Z',executor=Mock(return_value=receipt))
            with self.assertRaises(ValueError):handler.verify(screen('b','2026-01-01T00:00:01Z',25,True),now='2026-01-01T00:00:01Z')
            with self.assertRaises(ValueError):handler.dispatch(plan['proposal_id'],screen(),now='2026-01-01T00:00:00Z',executor=Mock())

    def test_native_adapter_default_off_and_guarded_fake_port_one_click(self):
        value=screen();intent=rank_purchases(value,now=value['frame']['captured_at'])['candidates'][0]
        row=observed();row.update(class_name='UnityWndClass',executable_path=r'C:\synthetic\WXQ.exe',identity_version='fixture-game')
        frame={'identity':row,'sha256':'a'*64,'captured_at':value['frame']['captured_at'],'observed_monotonic':10}
        execute=guarded_executor(frame,observer=lambda *a:deepcopy(row),utc_clock=lambda:timestamp(value['frame']['captured_at']))
        with self.assertRaisesRegex(NativeUnavailable,'disabled'):execute(intent)
        evidence=PurchaseClickEvidence(Binding.from_observation(row),10,*intent.target,context='custom_purchase',operation='buy_shop_offer',
            scene='purchase_enabled',recognizer='purchase-screen/1',frame_sha256='a'*64,executable_path=row['executable_path'],purchase=intent)
        broker=PurchaseClickBroker(evidence,observer=lambda *a:deepcopy(row),enabled=True,clock=lambda:10,
                                  utc_clock=lambda:timestamp(value['frame']['captured_at']))
        broker.port_factory=lambda observer:FakePort(observer)
        try:
            broker.arm();broker.click_once();self.assertEqual(len(broker.port.calls),1)
            with self.assertRaises(NativeUnavailable):broker.click_once()
        finally:broker.close()
        for change in ({'purchase':replace(intent,source_mode='saved_replay')},{'x':49},{'scene':'unknown'}):
            bad=PurchaseClickBroker(replace(evidence,**change),observer=Mock(),utc_clock=lambda:timestamp(value['frame']['captured_at']))
            with self.assertRaises(NativeUnavailable):bad.validate_context()


if __name__=='__main__':unittest.main()
