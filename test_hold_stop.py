import ast,ctypes as c,threading,unittest
from pathlib import Path
from unittest.mock import Mock,patch
import test_owned_mouse_tags as existing
d=existing.diagnostic

def keyboard(key,at,injected=False,message=0x100):
    return dict(kind='keyboard',key=key,at=at,injected=injected,message=message)

class StopTests(unittest.TestCase):
    def broker(self,reason='user_or_foreign_keyboard_input'):
        b=Mock();b.stopped=threading.Event();b.stopped.set();b.stop_monotonic=2.;b.stop_reason=reason
        return b
    def test_foreign_injection_precedes_correct_right_shift(self):
        b=self.broker();a=[keyboard('other',1.9,True),keyboard('RightShift',3.8)]
        self.assertEqual(d.unexpected_hold_stop('owned_release',b,a,[dict(kind='down',at=1.)]),'foreign_injected_keyboard')
    def test_expected_right_shift_or_emergency_ctrl_keeps_release_observation(self):
        for name,key in [('owned_release','RightShift'),('emergency','Ctrl')]:
            self.assertIsNone(d.unexpected_hold_stop(name,self.broker(),[keyboard(key,1.9)],[dict(kind='down',at=1.)]))
    def test_late_or_premature_trigger_cannot_rescue_stopped_attempt(self):
        for trigger,down in [(2.1,1.),(.9,1.)]:
            self.assertEqual(d.unexpected_hold_stop('owned_release',self.broker(),[keyboard('RightShift',trigger)],[dict(kind='down',at=down)]),'stopped_before_expected_physical_trigger')
    def test_wrong_key_deadline_and_later_injection_are_interruptions(self):
        self.assertEqual(d.unexpected_hold_stop('owned_release',self.broker(),[keyboard('other',1.9)],[dict(kind='down',at=1.)]),'unexpected_physical_key')
        self.assertTrue(d.unexpected_hold_stop('owned_release',self.broker('diagnostic_deadline_expired'),[],[]).startswith('unexpected_stop:'))
        self.assertEqual(d.unexpected_hold_stop('owned_release',self.broker(),[keyboard('RightShift',1.9),keyboard('other',2.2,True)],[dict(kind='down',at=1.)]),'foreign_injected_keyboard')
    def test_stopped_hold_cancels_poll_and_queued_down_prompt(self):
        s=d.Suite.__new__(d.Suite);s.index=4;s.ending=False;s.active={'broker_index':0,'event_start':0}
        b=self.broker();b.port.audit_snapshot.return_value=[keyboard('other',1.9,True)]
        s.current_broker=Mock(return_value=b);s.events=[];s.root=Mock();s.target=Mock();s.status=Mock()
        def fail(error):s.ending=True
        s.fail=Mock(side_effect=fail)
        s.target_event('down')
        self.assertTrue(s.ending);s.fail.assert_called_once()
        self.assertNotIn('现在按住',s.status.set.call_args.args[0])
        s.root.after.assert_not_called();s.poll_hold();s.root.after.assert_not_called()
    def test_first_foreign_metadata_is_bounded_and_has_no_text_or_raw_tag(self):
        p=existing.MouseTagEvidenceTests().port()
        p._diagnostic_foreign_keyboard(0x100,0x87,0x64,0x12,1234,False)
        p._diagnostic_foreign_keyboard(0x101,0x88,0x65,0x90,1235,False)
        row=p.foreign_keyboard_snapshot()
        self.assertEqual((row['vk'],row['scan_code'],row['flags'],row['native_tick_ms']),(0x87,0x64,0x12,1234))
        self.assertTrue(row['injected']);self.assertFalse(row['full_tag_equal'])
        self.assertNotIn('text',row);self.assertNotIn('extra',row)
        row['vk']=0;self.assertEqual(p.foreign_keyboard_snapshot()['vk'],0x87)
    def test_real_callback_stops_before_metadata_and_does_not_submit(self):
        p=existing.MouseTagEvidenceTests().port();order=[]
        source=Path(d.native.__file__).read_text(encoding='utf-8')
        tree=ast.parse(source);cls=next(n for n in tree.body if isinstance(n,ast.ClassDef) and n.name=='WindowsClickPort')
        opened=next(n for n in cls.body if isinstance(n,ast.FunctionDef) and n.name=='open')
        loop=next(n for n in opened.body if isinstance(n,ast.FunctionDef) and n.name=='hook_loop')
        callback=next(n for n in loop.body if isinstance(n,ast.FunctionDef) and n.name=='keyboard')
        stop=lambda reason:order.append('stop')
        original=p._diagnostic_foreign_keyboard
        p._diagnostic_foreign_keyboard=lambda *a:(order.append('metadata'),original(*a))
        ns={'self':p,'stop':stop,'c':c};exec(compile(ast.Module(body=[callback],type_ignores=[]),'<callback-only>','exec'),ns)
        event=p.KeyboardHook();event.vk=0x87;event.scan=0x64;event.flags=0x10;event.time=1234;event.extra=0
        ns['keyboard'](0,0x100,c.addressof(event))
        self.assertEqual(order,['stop','metadata']);p.user.SendInput.assert_not_called();p.user.CallNextHookEx.assert_called_once()

if __name__=='__main__':unittest.main()
