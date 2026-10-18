"""Targeted tag-boundary/strict-guard tests. DLLs and input are always mocked."""
import concurrent.futures
import ctypes as c
import threading
import unittest
from unittest.mock import Mock, patch
import test_owned_mouse_tags as existing

d=existing.diagnostic
n=d.native

class InputTags32Tests(unittest.TestCase):
    def setUp(self):
        self.tags=patch.object(n,'_USED_INPUT_TAGS',set())
        self.tags.start();self.addCleanup(self.tags.stop)

    def test_full_uint32_range_including_even_and_high_bit_values(self):
        values=[0,1,2,0x7fffffff,0x80000000,0xffffffff]
        with patch.object(n.secrets,'randbits',side_effect=values) as entropy:
            self.assertEqual([n._new_input_tag() for _ in range(5)],values[1:])
        self.assertTrue(all(call.args==(32,) for call in entropy.call_args_list))
        self.assertEqual(n._USED_INPUT_TAGS,set(values[1:]))

    def test_retires_old_tags_and_rejects_duplicate_draws(self):
        with patch.object(n.secrets,'randbits',side_effect=[22,22,22,44]):
            self.assertEqual(n._new_input_tag(),22)
            self.assertEqual(n._new_input_tag(),44)
        self.assertEqual(n._USED_INPUT_TAGS,{22,44})

    def test_repeating_entropy_and_budget_exhaustion_fail_closed(self):
        with patch.object(n.secrets,'randbits',return_value=0) as entropy:
            with self.assertRaisesRegex(n.NativeUnavailable,'unique_input_tag_unavailable'):
                n._new_input_tag()
            self.assertEqual(entropy.call_count,32)
        with patch.object(n,'_INPUT_TAG_LIMIT',0),patch.object(n.secrets,'randbits') as entropy:
            with self.assertRaisesRegex(n.NativeUnavailable,'input_tag_budget_exhausted'):
                n._new_input_tag()
            entropy.assert_not_called()

    def test_concurrent_allocations_cannot_reuse_one_value(self):
        values=iter(v for i in range(1,65) for v in (i,i))
        with patch.object(n.secrets,'randbits',side_effect=lambda bits:next(values)):
            with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
                tags=list(pool.map(lambda _:n._new_input_tag(),range(64)))
        self.assertEqual(len(set(tags)),64)
        self.assertEqual(set(tags),set(range(1,65)))

    def test_exact_full_value_and_injected_flag_still_required(self):
        cases=[(1,0x87654321,False),(0,0x87654321,True),(1,0x87654320,True),(1,0,True)]
        if c.sizeof(c.c_void_p)==8:
            cases.extend([(1,0x187654321,True),(1,0xffffffff87654321,True)])
        for flags,observed,foreign in cases:
            with self.subTest(flags=flags,observed=observed):
                port=existing.MouseTagEvidenceTests().port()
                port.token=port.created_token=0x87654321
                stop=Mock();callback=existing.MouseTagEvidenceTests().callback(port,stop)
                event=port.MouseHook();event.flags=flags;event.extra=observed
                callback(0,0x201,c.addressof(event))
                if foreign:stop.assert_called_once_with('user_or_foreign_mouse_input')
                else:stop.assert_not_called()
                port.user.SendInput.assert_not_called()
                port.user.CallNextHookEx.assert_called_once()

    def test_prior_broker_tag_is_not_owned_by_the_next_broker(self):
        fixture=existing.MouseTagEvidenceTests()
        first,second=fixture.port(),fixture.port()
        self.assertNotEqual(first.token,second.token)
        stop=Mock();callback=fixture.callback(second,stop)
        event=second.MouseHook();event.flags=1;event.extra=first.token
        callback(0,0x201,c.addressof(event))
        stop.assert_called_once_with('user_or_foreign_mouse_input')

    def test_uint32_high_bit_survives_batch_and_only_owned_release(self):
        port=existing.MouseTagEvidenceTests().port()
        port.token=port.created_token=0xffffffff
        port.user.SendInput.return_value=3
        port.click(1,60,60,lambda:True)
        _,events,_=port.user.SendInput.call_args.args
        self.assertEqual([x.mi.dwExtraInfo for x in events],[0xffffffff]*3)
        port.user.SendInput.reset_mock()
        port.held=False;port.release_owned();port.user.SendInput.assert_not_called()
        port.held=True;port.user.SendInput.return_value=1
        self.assertTrue(port.release_owned())
        count,event,_=port.user.SendInput.call_args.args
        event=c.cast(event,c.POINTER(port.Input)).contents
        self.assertEqual((count,event.type,event.mi.dwFlags,event.mi.dwExtraInfo),(1,0,4,0xffffffff))
        self.assertFalse(port.held)
        port.user.SendInput.reset_mock();port.release_owned();port.user.SendInput.assert_not_called()

    def test_diagnostic_reports_actual_allocator_and_requires_real_emergency_evidence(self):
        port=existing.MouseTagEvidenceTests().port()
        self.assertEqual(port.ownership_snapshot()['token_generation'],n.INPUT_TAG_GENERATION)
        row=existing.existing.DiagnosticTests().hold_row()
        row['registered_hotkey_received']=False
        self.assertFalse(d.phase_passes('emergency',row))

if __name__=='__main__':unittest.main()
