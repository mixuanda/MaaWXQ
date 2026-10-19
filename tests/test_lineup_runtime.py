"""Focused feedback/guard wiring fixtures. No Windows or capture call is allowed."""
from copy import deepcopy
from contextlib import ExitStack
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from test_state_economy_bridge import at, frame as old_frame, observed, policy as old_policy, native
from backends.lineup_actions import LineupClickBroker, LineupDragBroker, GuardedLineupExecutor
from runtime.economy_ui import EconomyUI
from runtime.lineup_runtime import LineupRuntime
from runtime.lineup_transactions import prepare_owned, verify_owned
from runtime.lineup_bridge import LineupBridge
from strategy.state_projection import project_frame


def policy():
    p = old_policy(); p['spending']['level_reserve'] = 8
    p['plans'][0]['targets'] = [dict(hero_id=hero, source=p['plans'][0]['source'])
                               for hero in ('wanted', 'second', 'third', 'fourth', 'fifth')]
    return p


def frame(second, *, credits=78, level=5, hand=(), board=(), names=None, shop=True):
    f, facts, ui, mapping = old_frame(second, energy=credits, level=level, names=names)
    f['source_mode'] = 'live_capture'; facts.update(timer=30, shop_visible=shop, shop_hidden_verified=not shop)
    f['identity'].update(hwnd=1, pid=2, process_started_at='fixture-process', class_name='UnityWndClass',
                         visible=True, minimized=False, title='王者万象棋', executable_path='C:\\fixture\\wxq.exe',
                         desktop={'foreground_hwnd':1})
    f['identity']['client'].update(screen_x=0, screen_y=0); f['observed_monotonic'] = 1.0
    slots=[]
    for i in range(3):
        slots.append(dict(slot_id=str(i), kind='hero' if i < len(hand) else 'empty',
                          hero_id=hand[i] if i < len(hand) else None, template_id='fixture-card',
                          bounds=[450+i*100,780,80,60], classification_verified=True, legal=True))
    f['recognized_zones']['hand']=dict(observed(f), coverage='full',overflow_checked=True,
                                       free_slots=3-len(hand),slots=slots)
    f['recognized_zones']['board']=dict(observed(f),coverage='full',overflow_checked=True,
        slots=[dict(slot_id=str(i),kind='hero',hero_id=hero) for i,hero in enumerate(board)])
    f['recognized_fields']['capacity']=observed(f,4)
    f['recognized_deployment']=dict(observed(f),empty_verified=True,own_board_verified=True,legal_verified=True,
                                    board_slot_id='board:'+str(len(board)),
                                    rect=[600+len(board)*100,480,80,80],target=[640+len(board)*100,520])
    for offer in facts['offers']:
        offer['ui_binding']=dict(observed(f),hero_id=offer['name'],purchasable_verified=True,
                                  rect=[260+offer['slot']*200,40,190,280],target=[350+offer['slot']*200,180])
    p=project_frame(f,facts,match_id='fixture-match',processed_at=at(second),phase='preparation',
                    currency_mapping=mapping,ui=ui,source_mode='live_capture')
    f.update(strategy_batch=p['batch'],strategy_ui_bindings=p['ui_bindings'])
    return f


def submission(drag=False):
    return dict(sent=True, owned_release_confirmed=True, cleanup_errors=(),action_budget_remaining=0,
                submission_outcome='drag_path_submitted_requires_visual_verification' if drag else 'down_and_owned_up_submitted')


def summary():
    return dict(held=False,release_confirmed=True,cleanup_errors=[],down_count=2,owned_up_count=1)


class LineupRuntimeTests(unittest.TestCase):
    def test_actual_adapter_wiring_levels_refreshes_buys_only_targets_then_closes_once(self):
        offers=['wanted','second','junk-c','junk-d']; bought=['sold-a','second','junk-c','junk-d']
        sold=['sold-a','sold-b','junk-c','junk-d']
        states=[frame(0,level=4),frame(1,credits=70),frame(2,credits=70),
                frame(3,credits=68,names=offers),frame(4,credits=68,names=offers),
                frame(5,credits=65,hand=('wanted',),names=bought),frame(6,credits=65,hand=('wanted',),names=bought),
                frame(7,credits=62,hand=('wanted','second'),names=sold),frame(8,credits=62,hand=('wanted','second'),names=sold),
                frame(9,credits=62,hand=('wanted','second'),shop=False),frame(10,credits=62,hand=('wanted','second'),shop=False),
                frame(11,credits=62,hand=('second',),board=('wanted',),shop=False),
                frame(12,credits=62,hand=('second',),board=('wanted',),shop=False),
                frame(13,credits=62,board=('wanted','second'),shop=False)]
        # Physical slot IDs must persist when the other hand card is deployed.
        for f in states[11:13]:
            zone=f['recognized_zones']['hand'];zone['slots'][0],zone['slots'][1]=zone['slots'][1],zone['slots'][0]
            zone['slots'][0]['slot_id']='0';zone['slots'][1]['slot_id']='1'
            fields=f['strategy_batch']['own_fields']
            for row in fields:
                if row['key']=='hand_ids':row['value']=['hand:1']
                if row['key']=='hero:hand:0':row['key']='hero:hand:1'
            bindings=f['strategy_ui_bindings']['hand'];b=bindings.pop('hand:0');b.update(slot_id='1',bounds=[550,780,80,60]);bindings['hand:1']=b
        frames=iter(states); state={'time':0}; calls=[]; reservations=[]
        def clock():state['time']+=.001;return at(state['time'])
        def observe():
            f=next(frames);state['time']=states.index(f)+.01;return f
        def reserve(f,intent):
            reservations.append(intent['action'])
            return dict(custom_room_verified=True,no_other_humans_verified=True,postcondition_reserved=True,
                        attempt_charged=True,match_id='fixture-match',frame_sha256=f['sha256'])
        def arm(broker):
            broker.validate_context()  # Exercise the actual typed binding checks.
            broker.port=SimpleNamespace(drag_moves=[])
        def click(broker):
            drag=broker.evidence.operation=='deploy';calls.append(broker.evidence.operation)
            if drag:broker.port.drag_moves=[dict(step=i,raw_return=1) for i in range(1,11)]
            return submission(drag)
        def close_shop(f,advice):
            calls.append('close_shop')
            return dict(action='close_shop',before_sha256=f['sha256'],started_at=clock(),released_at=clock(),
                        submission=dict(submission(),cleanup_errors=[]),native_summary=summary())
        with ExitStack() as stack:
            stack.enter_context(patch('ctypes.WinDLL',side_effect=AssertionError('native calls forbidden'),create=True))
            for cls,method in ((LineupClickBroker,'click_once'),(LineupDragBroker,'drag_once')):
                stack.enter_context(patch.object(cls,'arm',arm));stack.enter_context(patch.object(cls,method,click))
                stack.enter_context(patch.object(cls,'close',lambda b:None))
            stack.enter_context(patch('backends.lineup_actions.close_verified',lambda b:(summary(),'fixture-marker')))
            runtime=LineupRuntime(policy(),observe=observe,observer=lambda *a:self.fail('native observer forbidden'),
                                  before_input=reserve,clock=clock,enabled=True,close_shop=close_shop)
            results=runtime.run(max_steps=7)
        self.assertEqual([r['status'] for r in results],['recorded']*4+['shop_closed_for_advised_deployment']+['recorded']*2,results)
        self.assertEqual(calls,['level_up','refresh','buy','buy','close_shop','deploy','deploy'])
        self.assertEqual(reservations,['level_up','refresh','buy','buy','deploy','deploy'])
        self.assertEqual((runtime.bridge.refresh_count,runtime.bridge.refresh_spent),(1,2))

    def test_paid_quote_and_player_level_have_independent_current_readers(self):
        ui=EconomyUI.__new__(EconomyUI)
        ui.profile={'reference':'fixture-only-layout','scalar_readers':{
            'player_level':{'anchor_id':'level','pattern':r'棋手等级(?P<value>\d{1,2})','semantic_source':'fixture player label'},
            'level_up_target_level':{'anchor_id':'target','pattern':r'升至(?P<value>\d{1,2})级','semantic_source':'fixture target label'}},
            'quote_readers':{'refresh_cost':{'text_key':'paid','anchor_id':'refresh','pattern':r'(?P<value>\d{1,3})刷新','semantic_source':'fixture current price'}},
            'actions':{'paid_refresh':{'enabled_anchor_id':'enabled','rect':[20,20,80,40],'target':[40,40]}}}
        f=frame(0);f['v14']['anchors']=[dict(id=x,score=1) for x in ('level','target','refresh','enabled')]
        ocr=dict(frame_sha256=f['sha256'],captured_at=f['captured_at'],values={'player_level':'棋手等级4','level_up_target_level':'升至5级','paid':'3刷新'})
        out=ui.parse(f,ocr);self.assertEqual(out['player_level']['value'],4);self.assertEqual(out['refresh_cost']['value'],3)
        self.assertIn('refresh',out['actions'])
        ocr['values']['player_level']='3/4';out=ui.parse(f,ocr);self.assertNotIn('player_level',out)
        ocr['values']['paid']='刷新';out=ui.parse(f,ocr);self.assertNotIn('refresh_cost',out)
        ocr['frame_sha256']='f'*64;self.assertEqual(ui.parse(f,ocr)['actions'],{})

    def test_unknown_submission_is_latched_and_disabled_runtime_never_observes(self):
        reads=[]
        def observe():reads.append(1);return frame(0,level=4)
        runtime=LineupRuntime(policy(),observe=observe,observer=lambda *a:None,before_input=lambda *a:None,clock=lambda:at(.1))
        self.assertEqual(runtime.step()['status'],'automatic_input_disabled');self.assertEqual(reads,[])
        runtime.enabled=True
        def fail(*args):raise RuntimeError('fixture uncertain dispatch')
        runtime.dispatch=fail
        self.assertEqual(runtime.step()['status'],'submitted_outcome_uncertain_no_retry')
        self.assertEqual(runtime.step()['status'],'pending_no_retry');self.assertEqual(reads,[1])
        calls=[]
        def rejected_host(*args):calls.append(1);raise RuntimeError('fixture host refused before native')
        executor=GuardedLineupExecutor(runtime.bridge,observer=lambda *a:self.fail('no native port'),
                                       before_input=rejected_host,enabled=True,clock=lambda:at(.1))
        intent=runtime.bridge.pending_transaction['intent']
        with self.assertRaisesRegex(RuntimeError,'fixture host refused'):executor(frame(0,level=4),intent)
        with self.assertRaisesRegex(RuntimeError,'already_attempted_no_retry'):executor(frame(0,level=4),intent)
        self.assertEqual(calls,[1])

    def test_existing_same_hero_image_does_not_prove_receipt_of_another_copy(self):
        p=policy();p['plans'][0]['targets'][0]['count']=2
        before=frame(0,credits=30,hand=('wanted',),names=['wanted','junk-b','junk-c','junk-d'])
        bridge=LineupBridge(p)
        advice=bridge.decide(before['strategy_batch'],decision_at=at(.1),current_frame_sha256=before['sha256'])
        self.assertEqual(advice['action'],'buy')
        intent=prepare_owned(before,advice,now=at(.1));self.assertTrue(intent['ready'])
        raw=native(before,'buy')
        unchanged=frame(1,credits=27,hand=('wanted',))
        self.assertFalse(verify_owned(intent,unchanged,native_result=raw,now=at(1.1))['verified'])
        received=frame(1,credits=27,hand=('wanted','wanted'))
        self.assertTrue(verify_owned(intent,received,native_result=raw,now=at(1.1))['verified'])


if __name__=='__main__':unittest.main()
