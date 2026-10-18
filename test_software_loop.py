import unittest,copy,threading,hashlib,json,tempfile,time
from pathlib import Path
from dataclasses import replace
from unittest.mock import Mock,patch
from runtime.scene import state_from_recognition,decide,verify
from backends.game_click import GameClickBroker,GameClickEvidence,GameClickPort
from backends.win32_single_click import Binding,NativeUnavailable
from test_win32_single_click import FakePort,observed
import test_win32_single_click as original_tests
from backends import win32_single_click as native

from runtime import keypad

class LoopTests(unittest.TestCase):
    def test_each_digit_including_fourth_requires_visible_progress(self):
        for count in range(1,5):
            self.assertTrue(keypad.verify_progress({'scene':'room_keypad','entry_count':count},count))
            self.assertFalse(keypad.verify_progress({'scene':'room_keypad','entry_count':count-1},count))
            self.assertFalse(keypad.verify_progress({'scene':'unknown','entry_count':count},count))
        self.assertFalse(keypad.verify_progress({'scene':'room_keypad','entry_count':None},4))
    def test_keypad_requires_recognized_empty_and_ordered_slots(self):
        names=['room_title','custom_tab']+['digit_'+x for x in '0123456789']
        frame=dict(sha256='a'*64,matches=[dict(name=n,score=1.,center=[1,2]) for n in names],room_slots=[dict(occupied=False) for _ in range(4)])
        state=keypad.recognize(frame);self.assertEqual(keypad.decide(state,'6384',0)['digit'],'6')
        frame['room_slots'][1]['occupied']=True
        self.assertEqual(keypad.decide(keypad.recognize(frame),'6384',0)['action'],'stop')
    def test_foreign_input_after_completed_click_remains_visible(self):
        row=observed();e=GameClickEvidence(Binding.from_observation(row),10.,1,1)
        b=GameClickBroker(e,observer=Mock())
        b.stop('one_action_completed');self.assertFalse(b.foreign_interrupt.is_set())
        b.stop('user_or_foreign_mouse_input');self.assertTrue(b.foreign_interrupt.is_set())
        self.assertEqual(b.stop_reason,'one_action_completed')
    def test_fourth_digit_requires_positive_progress_and_does_not_claim_room(self):
        from runtime import room_code as runner
        security=dict(known=True,app_container=False,ui_access=False,elevated=False,integrity_rid=8192)
        row=observed();row.update(title='王者万象棋',class_name='UnityWndClass',
                                  executable_path='C:\\synthetic\\WXQ.exe',process_security=security)
        names=['room_title','custom_tab']+['digit_'+digit for digit in '0123456789']
        def frame(count):
            return dict(identity=row,observed_monotonic=time.monotonic(),sha256='a'*64,
                        matches=[dict(name=name,score=1.,center=[50,40]) for name in names],
                        room_slots=[dict(occupied=index<count) for index in range(4)])
        def broker(*args,**kwargs):
            value=Mock();value.release_confirmed=True;value.cleanup_errors=[]
            value.stop_reason='one_action_completed';value.port.held=False
            value.port.cleanup_errors=[];value.port.submitted_event_count=2
            value.port.owned_release_last_raw_return=1;value.port.activity_marker.return_value=7
            value.foreign_interrupt.is_set.return_value=False
            value.click_once.return_value={'sent':True}
            return value
        for final_count in (3,4):
            with self.subTest(final_count=final_count),tempfile.TemporaryDirectory() as directory:
                root=Path(directory);reference=root/'reference.fixture';reference.write_bytes(b'fixture')
                profile=root/'profile.json';profile.write_text(json.dumps(row),encoding='utf-8')
                frames=[frame(count) for count in (0,1,1,2,2,3,3,final_count)]
                with patch.object(runner,'process_security',return_value=security),patch.object(runner,'find_windows',return_value=[row]),patch.object(runner,'inspect_game',return_value=row),patch.object(runner,'activate_once',return_value={}),patch.object(runner,'capture',side_effect=frames) as capture,patch.object(runner,'GameClickBroker',side_effect=broker) as factory,patch.object(runner.time,'sleep'):
                    result=runner.run(root/'run',reference,hashlib.sha256(b'fixture').hexdigest(),profile,True,False)
                self.assertEqual(factory.call_count,4);self.assertEqual(capture.call_count,8)
                self.assertFalse(result['room_verified']);self.assertFalse(result['match_started'])
                if final_count==3:
                    self.assertEqual(result['error'],'digit_progress_not_verified')
                    self.assertEqual(result['status'],'stopped')
                else:self.assertEqual(result['status'],'four_digit_entry_count_verified_room_requires_recognition')

    def port(self):
        base=original_tests.NativePortFakeApiTests().port()
        p=GameClickPort.__new__(GameClickPort);p.__dict__.update(base.__dict__)
        row=observed();row.update(class_name='UnityWndClass',title='王者万象棋',executable_path='C:\\synthetic\\WXQ.exe')
        p.binding=Binding.from_observation(row);p.executable_path=row['executable_path'];p.observe=lambda *a:copy.deepcopy(row)
        p.abort_event=Mock();p.abort_event.wait.return_value=False
        return p,row
    def test_short_click_separate_down_up_tagged_and_owned(self):
        p,row=self.port();p.user.SendInput.side_effect=[2,1]
        self.assertEqual(p.click(1,60,60,lambda:True),3)
        calls=p.user.SendInput.call_args_list
        self.assertEqual([x.args[0] for x in calls],[2,1]);p.abort_event.wait.assert_called_once_with(.060)
        self.assertEqual([e.mi.dwFlags for e in calls[0].args[1]],[0xC001,2])
        up=native.c.cast(calls[1].args[1],native.c.POINTER(p.Input)).contents
        self.assertEqual((up.type,up.mi.dwFlags,up.mi.dwExtraInfo),(0,4,p.token));self.assertFalse(p.held)
    def test_interruption_releases_only_owned_mouse(self):
        p,row=self.port();p.abort_event.wait.return_value=True;p.user.SendInput.side_effect=[2,1]
        p.click(1,60,60,lambda:True)
        self.assertEqual(p.submission_outcome,'released_after_interrupt');self.assertFalse(p.held)
        self.assertEqual(p.owned_release_attempt_count,1)
    def test_changed_executable_prevents_any_input(self):
        p,row=self.port();row['executable_path']='C:\\another\\WXQ.exe'
        with self.assertRaisesRegex(NativeUnavailable,'game_identity'):p.click(1,60,60,lambda:True)
        p.user.SendInput.assert_not_called()
    def test_partial_move_does_not_release_unowned_button(self):
        p,row=self.port();p.user.SendInput.return_value=1
        with self.assertRaisesRegex(NativeUnavailable,'send_input_incomplete'):p.click(1,60,60,lambda:True)
        self.assertEqual(p.user.SendInput.call_count,1);self.assertFalse(p.held)
    def test_recognition_requires_all_three_regions(self):
        f={'sha256':'a'*64,'matches':[dict(name=n,score=.99,center=[10,20]) for n in ['custom_tab','custom_tile','confirm']]}
        self.assertEqual(decide(state_from_recognition(f))['operation'],'confirm_custom_selection')
        f['matches'][0]['score']=.7
        self.assertEqual(decide(state_from_recognition(f))['action'],'stop')
        f['matches'][0]['score']=.99;f['matches'].append(copy.deepcopy(f['matches'][-1]))
        self.assertEqual(decide(state_from_recognition(f))['action'],'stop')
    def test_template_absence_does_not_prove_exit_room_or_match(self):
        r=verify({'scene':'custom_selection'},{},{'scene':'unknown'},{'sent':True})
        self.assertIsNone(r['selection_screen_exited']);self.assertFalse(r['room_verified']);self.assertFalse(r['match_started'])
        self.assertFalse(r['blind_retry_allowed'])
        same=verify({'scene':'custom_selection'},{},{'scene':'custom_selection'},{'sent':True})
        self.assertFalse(same['selection_screen_exited']);self.assertTrue(same['selection_screen_still_recognized'])
    def test_external_exact_binding_one_click_with_normal_guards(self):
        row=observed();row.update(pid=12345,class_name='UnityWndClass',title='王者万象棋')
        observer=lambda *a:copy.deepcopy(row)
        e=GameClickEvidence(Binding.from_observation(row),10.,50,40,context='custom_setup',operation='confirm_custom_selection',
                            scene='custom_selection',frame_sha256='a'*64,recognizer='custom-selection-glyphs/1',executable_path='C:\\synthetic\\WXQ.exe')
        b=GameClickBroker(e,observer=observer,enabled=True,clock=lambda:10.)
        b.port_factory=lambda obs:FakePort(obs)
        try:
            b.arm();r=b.click_once();self.assertTrue(r['sent']);self.assertEqual(len(b.port.calls),1)
            with self.assertRaises(NativeUnavailable):b.click_once()
        finally:b.close()
    def test_ranked_room_and_wrong_operation_remain_rejected(self):
        row=observed();row['class_name']='UnityWndClass'
        e=GameClickEvidence(Binding.from_observation(row),10.,50,40,context='custom_setup',operation='confirm_custom_selection',
                            scene='custom_selection',frame_sha256='a'*64,recognizer='custom-selection-glyphs/1',executable_path='C:\\synthetic\\WXQ.exe')
        for change in [dict(context='ranked'),dict(scene='unknown'),dict(operation='buy'),dict(frame_sha256='')]:
            b=GameClickBroker(replace(e,**change),observer=Mock(),enabled=True,clock=lambda:10.)
            with self.assertRaises(NativeUnavailable):b.arm()
            self.assertIsNone(b.port)

    def test_capture_budget_reserves_whole_run_and_stops_at_file_or_byte_limit(self):
        from runtime import custom_setup as runtime
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            for index in range(49):(root/(str(index)+'.png')).touch()
            self.assertEqual(runtime.ensure_capture_capacity(root,frames=1)['files'],49)
            with self.assertRaisesRegex(RuntimeError,'capture_budget_full'):
                runtime.ensure_capture_capacity(root,frames=3)
            (root/'49.png').touch()
            with self.assertRaisesRegex(RuntimeError,'capture_budget_full'):
                runtime.ensure_capture_capacity(root,frames=1)
            self.assertEqual(runtime.ensure_capture_capacity(root,frames=0)['files'],50)
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);(root/'frame.png').write_bytes(b'x'*40)
            with patch.object(runtime,'CAPTURE_MAX_BYTES',100),patch.object(runtime,'CAPTURE_FRAME_RESERVE',30):
                runtime.ensure_capture_capacity(root,frames=1)
                with self.assertRaisesRegex(RuntimeError,'capture_budget_full'):
                    runtime.ensure_capture_capacity(root,frames=3)

    def test_port_cleanup_failure_stops_pipeline_before_result_capture(self):
        from runtime import custom_setup as runtime
        security=dict(known=True,app_container=False,ui_access=False,elevated=False,integrity_rid=8192)
        row=observed();row.update(title='王者万象棋',class_name='UnityWndClass',
                                  executable_path='C:\\synthetic\\WXQ.exe',process_security=security)
        frame=dict(identity=row,sha256='a'*64,observed_monotonic=time.monotonic(),
                   matches=[dict(name=name,score=.99,center=[50,40])
                            for name in ['custom_tab','custom_tile','confirm']])
        broker=Mock();broker.release_confirmed=True;broker.cleanup_errors=[]
        broker.stop_reason='one_action_completed'
        broker.port.cleanup_errors=['fixture_port_cleanup_failure'];broker.port.held=False
        broker.port.submission_outcome='down_and_owned_up_submitted'
        broker.port.submitted_event_count=2;broker.port.owned_release_last_raw_return=1
        broker.port.click_timing='fixture';broker.port.down_submitted_at=1.
        broker.port.owned_release_completed_at=1.06
        broker.click_once.return_value={'sent':True}
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);reference=root/'reference.fixture';reference.write_bytes(b'fixture')
            profile=root/'profile.json';profile.write_text(json.dumps(row),encoding='utf-8')
            with patch.object(runtime,'token_metadata',return_value={}),patch.object(runtime,'process_security',return_value=security),patch.object(runtime,'find_windows',return_value=[row]),patch.object(runtime,'inspect_game',return_value=row),patch.object(runtime,'capture',return_value=frame) as capture,patch.object(runtime,'GameClickBroker',return_value=broker):
                result=runtime.run(root/'run',reference,hashlib.sha256(b'fixture').hexdigest(),True,profile=profile)
            self.assertEqual(result['status'],'stopped')
            self.assertEqual(result['error'],'game_click_cleanup_unconfirmed')
            self.assertFalse(result['action']['cleanup_confirmed'])
            self.assertFalse(result['game_success']);self.assertEqual(capture.call_count,2)
            self.assertIn('fixture_port_cleanup_failure',result['cleanup_errors'])

if __name__=='__main__':unittest.main()
