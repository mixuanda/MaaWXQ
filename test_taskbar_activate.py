import copy,threading,unittest,tempfile
from pathlib import Path
from unittest.mock import Mock,patch
from backends.taskbar_activate import TaskbarActivationPort,validate_button,same_button,select_button
from backends.win32_single_click import NativeUnavailable
import test_win32_single_click as original_tests

PROFILE={'title':'王者万象棋','executable_path':r'C:\synthetic\WXQ.exe'}
def button():
    return {'taskbar_hwnd':11,'taskbar_pid':22,'explorer_path':r'C:\Windows\explorer.exe',
      'name':'王者万象棋 - 1 个运行窗口','automation_id':'Appid: '+PROFILE['executable_path'],
      'class_name':'Taskbar.TaskListButtonAutomationPeer','process_id':22,'runtime_id':[42,7,4,9],
      'control_type':'ControlType.Button','enabled':True,'offscreen':False,
      'rectangle':[40,40,44,48],'point':[60,60],'point_root_hwnd':11}

class TaskbarTests(unittest.TestCase):
    def test_full_capture_budget_prevents_taskbar_discovery_subprocess(self):
        from runtime import activate_taskbar as runtime
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            for index in range(50):(root/(str(index)+'.png')).touch()
            with patch.object(runtime.subprocess,'run') as process:
                with self.assertRaisesRegex(RuntimeError,'capture_budget_full'):
                    runtime.observe(PROFILE,root/'run'/'before')
            process.assert_not_called()
    def test_unrelated_application_group_or_hit_is_rejected(self):
        validate_button(button(),PROFILE)
        for change in ({'name':'Other app - 1 个运行窗口'},{'name':'王者万象棋 - 2 个运行窗口'},
                       {'automation_id':'Appid: another.exe'},{'point_root_hwnd':88},
                       {'explorer_path':r'C:\synthetic-other\explorer.exe'},{'offscreen':True},{'enabled':False},
                       {'point':[85,60]},{'process_id':99}):
            with self.subTest(change=change),self.assertRaises(NativeUnavailable):validate_button(button()|change,PROFILE)
    def test_moved_or_replaced_button_cannot_reuse_evidence(self):
        first=button()
        for change in ({'runtime_id':[42,7,4,10]},{'rectangle':[42,40,44,48]},{'point':[61,60]},
                       {'taskbar_pid':23},{'taskbar_hwnd':12}):
            self.assertFalse(same_button(first,first|change))
    def port(self):
        p=TaskbarActivationPort.__new__(TaskbarActivationPort)
        p.__dict__.update(original_tests.NativePortFakeApiTests().port().__dict__)
        p.button=button();p.game={'hwnd':99};p.deadline=5;p.attempted=False;p.down_attempted=False
        p.stopped=threading.Event();p.stop_lock=threading.Lock();p.stop_reason=None;p._check_target=Mock()
        return p
    def test_exact_one_click_and_only_own_up(self):
        p=self.port();p.user.SendInput.side_effect=[2,1]
        result=p.click_once()
        self.assertFalse(p.held);self.assertEqual(result['native_owned_up_count'],1)
        self.assertEqual([call.args[0] for call in p.user.SendInput.call_args_list],[2,1])
        with self.assertRaisesRegex(NativeUnavailable,'budget_exhausted'):p.click_once()
    def test_partial_move_never_releases_unowned_button(self):
        p=self.port();p.user.SendInput.return_value=1
        with self.assertRaisesRegex(NativeUnavailable,'incomplete'):p.click_once()
        self.assertEqual(p.user.SendInput.call_count,1);self.assertFalse(p.held)
    def test_stop_during_owned_down_wakes_and_releases(self):
        p=self.port()
        def send(count,*args):
            if count==2:p.stop('emergency_hotkey')
            return count
        p.user.SendInput.side_effect=send
        result=p.click_once()
        self.assertEqual(result['submission_outcome'],'released_after_interrupt')
        self.assertEqual(p.owned_release_attempt_count,1);self.assertFalse(p.held)
    def test_final_revalidation_failure_prevents_submission(self):
        p=self.port();p._check_target.side_effect=[None,NativeUnavailable('taskbar_point_obscured_or_changed')]
        with self.assertRaisesRegex(NativeUnavailable,'obscured'):p.click_once()
        p.user.SendInput.assert_not_called()

if __name__=='__main__':unittest.main()
