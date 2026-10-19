"""Minimal input -> actual Advisor checks; no acquisition or native APIs."""
from copy import deepcopy
import unittest

from test_state_economy_bridge import at
from test_lineup_runtime import frame as fixture_frame, policy as fixture_policy
from runtime.live_perception import normalize_bundle, LivePerceptionAdapter, state_readiness
from runtime.lineup_bridge import LineupBridge
from runtime.lineup_runtime import attach_current_state
from runtime.economy_ui import EconomyUI
from strategy.lingbao import compile_lingbao_selection


def catalog():
    observed=lambda value:dict(status='observed',value=value,confidence=1)
    return dict(schema_version='lingbao-catalog/1',recommendation_provider='in_game_lingbao',
                frame=dict(sha256='c'*64,captured_at=at(),identity_version='fixture-window',geometry_version='fixture-geometry'),
                plans=[dict(lineup_id='fixture-observed',name=observed('fixture observed recommendation'),coverage='full',
                            targets=[dict(hero_id=observed('wanted'),role='core',count=1,priority=10)])])


def selection():return dict(plan_ids=['fixture-observed'],reference='fixture operator selection',search_min_levels={})


def raw_bundle():
    f=fixture_frame(0,credits=30,names=['wanted','junk-b','junk-c','junk-d'])
    f.pop('strategy_batch');f.pop('strategy_ui_bindings')
    tokens=dict(frame_sha256=f['sha256'],captured_at=f['captured_at'],
                identity_version=f['identity']['identity_version'],geometry_version=f['identity']['geometry_version'])
    fields=f.pop('recognized_fields');fields.pop('player_level');fields.pop('level_up_target_level')
    zones=f.pop('recognized_zones');bans=f.pop('recognized_bans');destination=f.pop('recognized_deployment')
    facts=dict(round=3,timer=30,button='开战',energy=30,shop_visible=True,offers=[])
    for i,hero in enumerate(['wanted','junk-b','junk-c','junk-d']):
        facts['offers'].append(dict(slot=i,name=hero,price=3,
            ui_binding=dict(status='observed',confidence=1,hero_id=hero,purchasable_verified=True,
                            rect=[260+i*200,40,190,280],target=[350+i*200,180])))
    packet=dict(schema_version='perception-frame/1',**tokens,zones=zones,fields=fields,bans=bans,
                deployment=destination,facts=facts,phase='preparation')
    return dict(frame=f,recognition=packet,ocr=dict(frame_sha256=f['sha256'],captured_at=f['captured_at'],values={}))


def project(bundle):
    ui=EconomyUI.__new__(EconomyUI);ui.profile=dict(reference='fixture empty readers',scalar_readers={},actions={})
    return attach_current_state(bundle['frame'],bundle['facts'],bundle['ocr'],ui_reader=ui,
        match_id='fixture-match',processed_at=at(.1),phase=bundle['phase'],
        currency_mapping=dict(verified=True,currency_id='fixture-energy',source='fixture reviewed mapping'),source_mode='live_capture')


class LiveStrategyInputTests(unittest.TestCase):
    def test_host_bundle_and_lingbao_selection_drive_the_existing_advisor_without_level_defaults(self):
        compiled=compile_lingbao_selection(catalog(),selection(),fixture_policy()['spending'],now=at(.1))
        self.assertEqual(compiled['status'],'ready',compiled)
        calls=[]
        def provider(*args):calls.append(args);return raw_bundle()
        adapter=LivePerceptionAdapter(provider,clock=lambda:at(.1))
        bundle=adapter('fixture-output.png',{},[]);self.assertEqual(len(calls),1)
        f=project(bundle);bridge=LineupBridge(compiled['policy'])
        advice=bridge.decide(f['strategy_batch'],decision_at=at(.1),current_frame_sha256=f['sha256'])
        self.assertEqual((advice['action'],advice['offer']['hero_id']),('buy','wanted'))
        status=state_readiness(f)
        self.assertIn('player_level',status['action_missing']['level_up'])
        self.assertNotIn('player_level',status['action_missing']['buy'])
        self.assertIn('current_match_origin_continuity',status['host_missing'])
        with self.assertRaisesRegex(ValueError,'time_must_advance'):adapter('another.png',{},[])

    def test_partial_zones_failed_zero_and_legacy_capacity_remain_unknown(self):
        raw=raw_bundle();packet=raw['recognition']
        packet['zones']['hand']['coverage']='partial'
        packet['zones']['board']['coverage']='partial'
        packet['fields'].pop('capacity')
        packet['facts']['energy']=None
        raw['frame']['numbers']['energy']=dict(Known=False,Value=0)
        raw['frame']['v14']['capacity']=1
        f=project(normalize_bundle(raw,now=at(.1)))
        fields={row['key']:row for row in f['strategy_batch']['own_fields']}
        for key in ('hand_ids','board_ids','capacity','credits'):
            self.assertEqual(fields[key]['status'],'unknown',key)
        self.assertIn('capacity',f['input_status']['decision_missing'])
        packet['fields']['credits']=dict(status='observed',value=0,confidence=1)
        f=project(normalize_bundle(raw,now=at(.1)))
        self.assertEqual(next(row for row in f['strategy_batch']['own_fields'] if row['key']=='credits')['value'],0)
        bad=deepcopy(raw);bad['recognition']['zones']['hand']['frame_sha256']='f'*64
        with self.assertRaisesRegex(ValueError,'mixed_capture_recognition'):normalize_bundle(bad,now=at(.1))

    def test_missing_selection_budget_or_unreadable_recommendation_never_produces_policy(self):
        data=catalog();budget=fixture_policy()['spending']
        empty=compile_lingbao_selection(data,{},dict(budget,refresh_spend_cap=None),now=at(.1))
        self.assertIsNone(empty['policy']);self.assertIn('explicit_selected_plan_ids',empty['gaps'])
        self.assertIn('spending.refresh_spend_cap',empty['gaps'])
        data['plans'][0]['targets'][0]['hero_id']=dict(status='unknown',value=None,confidence=None)
        result=compile_lingbao_selection(data,selection(),budget,now=at(.1))
        self.assertIsNone(result['policy']);self.assertIn('plans.fixture-observed.targets.0.hero_id',result['gaps'])
        data=catalog();data['plans'][0]['coverage']='partial'
        result=compile_lingbao_selection(data,selection(),budget,now=at(.1))
        self.assertIsNone(result['policy']);self.assertIn('plans.fixture-observed.complete_target_coverage',result['gaps'])


if __name__=='__main__':unittest.main()
