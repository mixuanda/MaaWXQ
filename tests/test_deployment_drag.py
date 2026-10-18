"""Fake native API checks only. No native library, hook or input is opened."""
from copy import deepcopy
from dataclasses import replace
import ctypes
import unittest
from unittest.mock import Mock
from strategy.codec import timestamp
from backends.game_click import Binding,NativeUnavailable
from backends.deployment_drag import DeployEvidence,DeploymentDragPort,DeploymentDragBroker,guarded_executor
import test_software_loop as software_fixtures
from test_win32_single_click import FakePort


class DeploymentDragTests(unittest.TestCase):
    def port(self):
        base,row=software_fixtures.LoopTests().port()
        row['client'].update(width=1450,height=869)
        value=DeploymentDragPort.__new__(DeploymentDragPort);value.__dict__.update(base.__dict__)
        value.binding=Binding.from_observation(row);value.observe=lambda *args:deepcopy(row)
        value.destination=(710,555);value.drag_moves=[];value.gesture='one_bounded_drag_300ms/1'
        value.user.GetSystemMetrics.side_effect=lambda index:{76:0,77:0,78:1920,79:1080}[index]
        return value,row

    def evidence(self):
        _,row=self.port()
        evidence=DeployEvidence(Binding.from_observation(row),10,844,813,
            context='custom_deployment',operation='deploy_owned_hand_hero',scene='preparation_empty_own_board',
            recognizer='owned-hero-and-empty-board/1',frame_sha256='a'*64,executable_path=row['executable_path'],
            no_other_humans_verified=True,end_x=710,end_y=555,hero_id='fixture-hero',match_id='fixture-custom',
            capture_utc='2026-01-01T00:00:00Z',source_match=.96,empty_board_match=.99,capacity_match=.99,
            capacity=5,occupied=0,phase_match=.99,phase_margin=.04,purchase_verified=True)
        return evidence,row

    def test_drag_has_one_down_ten_tagged_moves_and_only_one_owned_up(self):
        value,row=self.port();value.user.SendInput.side_effect=[2]+[1]*11
        value.user.GetAsyncKeyState.side_effect=lambda code:0x8000 if code==1 and value.held else 0
        self.assertEqual(value.click(1,854,833,lambda:True),13)
        calls=value.user.SendInput.call_args_list
        self.assertEqual([call.args[0]for call in calls],[2]+[1]*11)
        self.assertEqual([event.mi.dwFlags for event in calls[0].args[1]],[0xC001,2])
        for call in calls[1:-1]:
            move=ctypes.cast(call.args[1],ctypes.POINTER(value.Input)).contents
            self.assertEqual((move.mi.dwFlags,move.mi.dwExtraInfo),(0xC001,value.token))
        up=ctypes.cast(calls[-1].args[1],ctypes.POINTER(value.Input)).contents
        self.assertEqual((up.mi.dwFlags,up.mi.dwExtraInfo),(4,value.token))
        self.assertEqual(len(value.drag_moves),10)
        self.assertEqual((value.drag_moves[-1]['x'],value.drag_moves[-1]['y']),(720,575))
        self.assertEqual(value.owned_release_attempt_count,1);self.assertFalse(value.held)

    def test_partial_initial_move_does_not_release_an_unowned_mouse_button(self):
        value,_=self.port();value.user.SendInput.return_value=1
        with self.assertRaisesRegex(NativeUnavailable,'drag_down_incomplete'):value.click(1,854,833,lambda:True)
        self.assertEqual(value.user.SendInput.call_count,1);self.assertFalse(value.held)
        self.assertEqual(value.drag_moves,[])

    def test_virtual_desktop_origin_and_client_offset_are_preserved(self):
        value,row=self.port();row['client'].update(screen_x=-1800,screen_y=1177)
        value.binding=Binding.from_observation(row)
        value.user.GetSystemMetrics.side_effect=lambda index:{76:-1920,77:-1080,78:3840,79:3240}[index]
        value.user.SendInput.side_effect=[2]+[1]*11
        value.click(1,-956,1990,lambda:True)
        self.assertEqual((value.drag_moves[-1]['x'],value.drag_moves[-1]['y']),(-1090,1732))
        last_move=value.user.SendInput.call_args_list[-2]
        event=ctypes.cast(last_move.args[1],ctypes.POINTER(value.Input)).contents
        self.assertEqual(event.mi.dx,round(830*65535/3839))
        self.assertEqual(event.mi.dy,round(2812*65535/3239))

    def test_abort_mid_drag_stops_moving_and_releases_owned_down_once(self):
        value,_=self.port();value.user.SendInput.side_effect=[2,1,1,1]
        value.abort_event.wait.side_effect=[False,False,True]
        with self.assertRaisesRegex(NativeUnavailable,'drag_revoked_during_move'):value.click(1,854,833,lambda:True)
        self.assertEqual(len(value.drag_moves),2);self.assertEqual(value.user.SendInput.call_count,4)
        self.assertFalse(value.held);self.assertEqual(value.owned_release_attempt_count,1)

    def test_failed_or_uncertain_segment_is_not_repeated_and_owned_hold_is_released(self):
        for outcome in (0,OSError('fixture send failure')):
            value,_=self.port();value.user.SendInput.side_effect=[2,outcome,1]
            with self.subTest(outcome=type(outcome).__name__),self.assertRaises((NativeUnavailable,OSError)):
                value.click(1,854,833,lambda:True)
            self.assertEqual(value.user.SendInput.call_count,3);self.assertEqual(len(value.drag_moves),1)
            self.assertEqual(value.drag_moves[0]['raw_return'],None if isinstance(outcome,Exception)else 0)
            self.assertFalse(value.held)

    def test_foreign_key_or_permission_revocation_prevents_submission(self):
        value,_=self.port()
        with self.assertRaises(NativeUnavailable):value.click(1,854,833,lambda:False)
        value.user.SendInput.assert_not_called()

    def test_target_loss_during_drag_stops_and_releases_only_our_down(self):
        value,_=self.port();value.user.SendInput.side_effect=[2,1,1]
        value.user.GetAncestor.side_effect=[1,1,2]
        with self.assertRaisesRegex(NativeUnavailable,'drag_target_or_permission_changed'):
            value.click(1,854,833,lambda:True)
        self.assertEqual(len(value.drag_moves),1);self.assertEqual(value.user.SendInput.call_count,3)
        self.assertFalse(value.held);self.assertEqual(value.owned_release_attempt_count,1)

    def test_release_failure_retains_the_owned_hold_until_cleanup_succeeds(self):
        value,_=self.port();value.user.SendInput.side_effect=[2]+[1]*10+[0]
        with self.assertRaisesRegex(NativeUnavailable,'drag_owned_release_failed'):
            value.click(1,854,833,lambda:True)
        self.assertTrue(value.held);self.assertEqual(value.owned_release_last_raw_return,0)
        self.assertEqual(len(value.drag_moves),10)
        value.user.SendInput.side_effect=None;value.user.SendInput.return_value=1
        self.assertTrue(value.release_owned());self.assertFalse(value.held)
        value,_=self.port();value.user.GetAsyncKeyState.side_effect=lambda code:0x8000 if code==16 else 0
        with self.assertRaises(NativeUnavailable):value.click(1,854,833,lambda:True)
        value.user.SendInput.assert_not_called()

    def test_default_off_explicit_drag_budget_and_utc_revalidation(self):
        evidence,row=self.evidence();at=timestamp(evidence.capture_utc)
        execute=guarded_executor(evidence,observer=lambda *args:deepcopy(row),utc_clock=lambda:at)
        with self.assertRaisesRegex(NativeUnavailable,'disabled'):execute()
        with self.assertRaisesRegex(ValueError,'no_retry'):execute()
        broker=DeploymentDragBroker(evidence,observer=lambda *args:deepcopy(row),enabled=True,
                                     clock=lambda:10,utc_clock=lambda:at)
        broker.port_factory=lambda observer:FakePort(observer)
        try:
            with self.assertRaisesRegex(NativeUnavailable,'explicit_drag'):broker.click_once()
            broker.arm();result=broker.drag_once()
            self.assertFalse(result['game_postcondition_verified']);self.assertFalse(result['blind_retry_allowed'])
            self.assertEqual(result['released_at'],at.isoformat())
            with self.assertRaises(NativeUnavailable):broker.drag_once()
        finally:broker.close()
        late=DeploymentDragBroker(evidence,observer=Mock(return_value=row),clock=lambda:10,
                                   utc_clock=lambda:timestamp('2026-01-01T00:00:06Z'))
        with self.assertRaises(NativeUnavailable):late.validate_context()
        with self.assertRaises(NativeUnavailable):late._check()

    def test_changed_context_or_unreviewed_layout_is_rejected(self):
        evidence,row=self.evidence()
        changes=[{'purchase_verified':False},{'no_other_humans_verified':False},{'occupied':1},{'capacity':4},{'capacity':3},
                 {'source_match':.91},{'empty_board_match':.96},{'phase_margin':.01},{'phase_match':.96},
                 {'end_x':711},{'x':844.0},{'source_match':float('nan')},{'context':'custom_purchase'},
                 {'binding':replace(evidence.binding,width=1920)},{'capture_utc':'invalid'}]
        for update in changes:
            broker=DeploymentDragBroker(replace(evidence,**update),observer=Mock(),utc_clock=lambda:timestamp(evidence.capture_utc))
            with self.subTest(update=tuple(update)),self.assertRaises(NativeUnavailable):broker.validate_context()
        for options in ({'max_age':6},{'max_seconds':3}):
            with self.assertRaises(ValueError):DeploymentDragBroker(evidence,observer=Mock(),**options)


if __name__=='__main__':unittest.main()
