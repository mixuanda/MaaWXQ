"""Three focused fixture checks; callbacks never open native/capture ports."""
from copy import deepcopy
from datetime import datetime, timezone, timedelta
import hashlib
import unittest

from runtime.economy_actions import EconomyActionHandler, prepare_action, verify_action
from runtime.economy_ui import EconomyUI
from runtime.lineup_bridge import LineupBridge
from strategy.state_projection import project_frame

AT=datetime(2026,1,1,tzinfo=timezone.utc)
def at(seconds=0): return (AT+timedelta(seconds=seconds)).isoformat()

def policy():
    source={'kind':'screen_recognition','reference':'fixture-only:not-an-actual-Lingbao-observation'}
    return {'schema_version':'v41-lineup-policy/1','recommendation_provider':'in_game_lingbao',
            'plans':[{'lineup_id':'fixture-plan','source':source,'search_min_level':5,
                      'targets':[{'hero_id':'wanted','source':source}]}],
            'spending':{'reference':'fixture-policy','budget_scope':'match','reserve':2,'upgrade_reserve':0,
                        'level_reserve':0,'refresh_spend_cap':4,'refresh_count_cap':1}}

def observed(frame,value=None):
    return {'status':'observed','confidence':1,'value':value,'frame_sha256':frame['sha256'],
            'identity_version':'fixture-window','geometry_version':'fixture-geometry'}

def frame(seconds=0, *, energy=20, level=5, names=None, roundno=3):
    names=names or ['junk-a','junk-b','junk-c','junk-d']
    f={'sha256':hashlib.sha256(repr((seconds,energy,level,names,roundno)).encode()).hexdigest(),
       'captured_at':at(seconds),'identity':{'identity_version':'fixture-window','geometry_version':'fixture-geometry',
                                              'client':{'width':1450,'height':869}},
       'matches':[{'name':'own_portrait','score':1},{'name':'phase_start','score':1}],
       'v14':{'capacity':1,'counts':[{'value':0,'score':1}],'anchors':[
           {'id':'economy_free_refresh_label','score':1},{'id':'economy_upgrade_label','score':1}]},
       'numbers':{'energy':{'Known':energy is not None,'Value':energy if energy is not None else 0}}}
    f['recognized_zones']={'hand':dict(observed(f),coverage='full',overflow_checked=True,free_slots=2,
                    slots=[{'slot_id':'0','kind':'empty','classification_verified':True}])}
    f['recognized_bans']=observed(f,[])
    f['recognized_fields']={'capacity':observed(f,5),'player_level':observed(f,level),'level_up_target_level':observed(f,5)}
    ui={key:observed(f,value) for key,value in [('player_level',level),('level_up_target_level',5),('refresh_cost',2),('level_up_cost',8)]}
    ui['actions']={action:dict(observed(f),label_verified=True,enabled_verified=True,rect=[20,20,80,40],target=[40,40])
                   for action in ('refresh','level_up')}
    facts={'frame_sha256':f['sha256'],'captured_at':f['captured_at'],'round':roundno,'button':'开战','energy':energy,
           'shop_visible':True,'offers':[{'slot':i,'name':name,'price':3}for i,name in enumerate(names)]}
    mapping={'verified':True,'currency_id':'fixture-energy','source':'fixture-reviewed-currency-mapping'}
    projection=project_frame(f,facts,match_id='fixture-match',processed_at=f['captured_at'],phase='preparation',
                             currency_mapping=mapping,ui=ui,source_mode='live_capture')
    f.update(strategy_batch=projection['batch'],strategy_ui_bindings=projection['ui_bindings'])
    return f,facts,ui,mapping

def advice(bridge,f,seconds=.1):
    return bridge.decide(f['strategy_batch'],decision_at=at(seconds),current_frame_sha256=f['sha256'])

def native(f,action='refresh'):
    return {'action':action,'before_sha256':f['sha256'],'started_at':at(.2),'released_at':at(.3),
            'submission':{'sent':True,'owned_release_confirmed':True,'cleanup_errors':[],
                          'action_budget_remaining':0,'submission_outcome':'down_and_owned_up_submitted'},
            'native_summary':{'held':False,'release_confirmed':True,'cleanup_errors':[],
                              'down_count':2,'owned_up_count':1}}


class StateEconomyBridgeTests(unittest.TestCase):
    def test_unknowns_instances_and_current_UI_quotes_are_not_filled_from_defaults(self):
        f,facts,ui,mapping=frame(energy=None)
        del f['recognized_zones']['hand']
        p=project_frame(f,facts,match_id='fixture-match',processed_at=at(),phase='preparation',currency_mapping=mapping,ui=ui)
        values={x['key']:x for x in p['batch']['own_fields']}
        self.assertEqual(values['credits']['status'],'unknown');self.assertIsNone(values['credits']['value'])
        self.assertEqual(values['hand_ids']['status'],'unknown');self.assertEqual(values['board_ids']['value'],[])
        f['v14']['counts']=[{'value':2,'score':1}]
        self.assertEqual(project_frame(f,facts,match_id='fixture-match',processed_at=at(),phase='preparation')['batch']['own_fields'][0]['status'],'unknown')
        f['recognized_zones']['hand']=dict(observed(f),coverage='full',overflow_checked=True,free_slots=0,
            slots=[{'slot_id':str(i),'kind':'hero','hero_id':'same','template_id':'same-template',
                    'bounds':[400+i*100,780,80,60]}for i in range(2)])
        p=project_frame(f,facts,match_id='fixture-match',processed_at=at(),phase='preparation')
        self.assertEqual(len(p['ui_bindings']['hand']),2)
        ui_reader=EconomyUI.__new__(EconomyUI)
        ui_reader.profile={'reference':'fixture','actions':{'free_refresh':{'rect':[20,20,80,40],'target':[40,40]}}}
        labels={'frame_sha256':f['sha256'],'captured_at':f['captured_at'],
                'values':{'refresh_label':'免费刷新','refresh_counter':'×2','upgrade_button':'5升级'}}
        out=ui_reader.parse(f,labels)
        self.assertEqual(out['refresh_cost']['value'],0);self.assertEqual(out['level_up_cost']['value'],5)
        self.assertNotIn('player_level',out);self.assertNotIn('level_up',out['actions'])

    def test_policy_is_recomputed_budget_survives_rounds_and_uncertain_dispatch_stays_pending(self):
        bridge=LineupBridge(policy());before,_,_,_=frame();a=advice(bridge,before)
        tampered=deepcopy(a);tampered['refresh_budget']['protected_credits']=0
        with self.assertRaises(ValueError):bridge.submitted('bad',tampered,submitted_at=at(.1),before_frame=before)
        after,_,_,_=frame(1,energy=18,names=['new-junk','junk-b','junk-c','junk-d'])
        observations=iter([before,after]);times=iter([at(.1),at(.1),at(.1),at(1.1)]);calls=[]
        def dispatch(f,intent): calls.append(intent['action']);return native(f)
        result=EconomyActionHandler(bridge).run_one(observe=lambda:next(observations),dispatch=dispatch,clock=lambda:next(times))
        self.assertEqual(result['status'],'recorded');self.assertEqual((bridge.refresh_count,bridge.refresh_spent),(1,2))
        next_round,_,_,_=frame(2,energy=18,roundno=4)
        self.assertEqual(advice(bridge,next_round,2.1)['action'],'hold')
        # A new frame missing a prior price explicitly revokes that old price.
        later,_,_,_=frame(3,energy=18,roundno=4)
        fields=later['strategy_batch']['own_fields'];fields[:]=[row for row in fields if row['key']!='price:shop:0']
        advice(bridge,later,3.1)
        self.assertEqual(next(x for x in bridge.advisor.state.fields if x.field.key=='price:shop:0').field.status,'unknown')
        uncertain=LineupBridge(policy());a=advice(uncertain,before)
        uncertain.submitted('pending',a,submitted_at=at(.1),before_frame=before)
        with self.assertRaises(ValueError):uncertain.completed('pending',verified=True,receipt={'sent':True},observed_at=at(1))
        unchanged,_,_,_=frame(1,energy=18)
        self.assertFalse(uncertain.complete_economy('pending',unchanged,native(before),now=at(1.1))['verified'])
        self.assertEqual(EconomyActionHandler(uncertain).run_one(observe=lambda:self.fail('must not recapture/retry'),dispatch=dispatch,clock=lambda:at(2))['status'],'pending_no_retry')
        self.assertEqual(calls,['refresh'])

    def test_postcondition_requires_release_and_exact_player_level_not_unit_level(self):
        before,_,_,_=frame(level=4);bridge=LineupBridge(policy());a=advice(bridge,before)
        intent=prepare_action(before,a,now=at(.1));self.assertTrue(intent['ready'])
        after,_,_,_=frame(1,level=5,energy=12)
        self.assertTrue(verify_action(intent,after,native_result=native(before,'level_up'),now=at(1.1))['verified'])
        wrong,_,_,_=frame(1,level=4,energy=12)
        wrong['strategy_batch']['own_fields'].append({'key':'unit_level:hero','status':'observed','value':5,'confidence':1})
        self.assertFalse(verify_action(intent,wrong,native_result=native(before,'level_up'),now=at(1.1))['verified'])
        release=native(before,'level_up');release['released_at']=at(1.2)
        self.assertFalse(verify_action(intent,after,native_result=release,now=at(1.3))['verified'])


if __name__=='__main__':unittest.main()
