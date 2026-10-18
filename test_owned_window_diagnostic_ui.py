"""Consent-flow tests only: no Tk window or native Windows API may be created."""
from unittest import TestCase, main
from unittest.mock import patch
from tools import owned_window_diagnostic as diagnostic

class Value:
    def __init__(self, value=False): self.value=value
    def get(self): return self.value
    def set(self, value): self.value=value

class Widget:
    def __init__(self): self.options={}
    def configure(self, **kwargs): self.options.update(kwargs)
    def focus_set(self): pass

class Root:
    def __init__(self): self.callbacks=[]
    def after(self, ms, callback): self.callbacks.append((ms, callback))
    def update_idletasks(self): pass
    def winfo_id(self): return 1

class ConsentFlow(TestCase):
    def setUp(self):
        self.native_guard=patch.object(diagnostic.c,"WinDLL",side_effect=AssertionError("Native API forbidden"))
        self.native_guard.start()
        self.addCleanup(self.native_guard.stop)
        self.probe_patch=patch.object(diagnostic,"PrearmInputProbe",return_value=object())
        self.probe=self.probe_patch.start()
        self.addCleanup(self.probe_patch.stop)

    def suite(self, index=0):
        s=diagnostic.Suite.__new__(diagnostic.Suite)
        s.index=index; s.active=None; s.ending=False; s.auto_group_consent=None
        s.events=[]; s.root=Root(); s.confirm=Value()
        s.heading=Value(); s.instructions=Value(); s.status=Value()
        s.check=Widget(); s.run_button=Widget(); s.target=Widget()
        s.result={"phases":{k:{"status":"not_run"} for k,_,_ in diagnostic.PHASES}}
        s.save=lambda: None
        s.fail=lambda error: (_ for _ in ()).throw(AssertionError(str(error)))
        return s

    def test_no_phase_runs_without_initial_checkbox(self):
        s=self.suite(); s.show_phase(); s.confirm_phase()
        self.assertIsNone(s.active)
        self.assertIsNone(s.auto_group_consent)
        self.assertEqual(s.root.callbacks,[])
        self.assertEqual(s.result["status"],"awaiting_automatic_group_confirmation")

    def test_one_real_confirmation_covers_only_first_three_and_is_not_recreated(self):
        s=self.suite(); s.confirm.set(True); s.confirm_phase()
        original_time=s.active["confirmed_at_utc"]
        consent=s.auto_group_consent
        self.assertEqual(consent["phases"],["deadline","click","focus"])
        self.assertFalse(s.active["confirmed_individually"])
        for index,name in [(1,"click"),(2,"focus")]:
            s.active=None; s.index=index; s.root.callbacks.clear(); s.show_phase()
            self.assertFalse(s.confirm.get())
            self.assertEqual(s.check.options["state"],"disabled")
            self.assertEqual(s.root.callbacks[0][0],750)
            s.root.callbacks.pop(0)[1]()
            self.assertEqual(s.active["confirmation_mode"],"automatic_group")
            self.assertEqual(s.active["confirmed_at_utc"],original_time)
            self.assertFalse(s.active["confirmed_individually"])
            self.assertIs(s.auto_group_consent,consent)
            self.assertEqual(s.result["status"],"phase_prearm_wait:"+name)

    def test_physical_stage_never_autostarts_and_requires_its_own_checkbox(self):
        s=self.suite(); s.confirm.set(True); s.confirm_phase()
        for index,name in [(3,"emergency"),(4,"owned_release")]:
            s.active=None; s.index=index; s.root.callbacks.clear(); s.show_phase()
            self.assertEqual(s.root.callbacks,[])
            self.assertFalse(s.confirm.get())
            s.confirm_phase()
            self.assertIsNone(s.active)
            s.confirm.set(True); s.confirm_phase()
            self.assertTrue(s.active["confirmed_individually"])
            self.assertEqual(s.active["confirmation_mode"],"individual_physical")
            self.assertEqual(s.result["status"],"phase_prearm_wait:"+name)

    def test_cancelled_scheduled_continuation_cannot_start(self):
        s=self.suite(); s.confirm.set(True); s.confirm_phase()
        s.active=None; s.index=1; s.root.callbacks.clear(); s.show_phase()
        callback=s.root.callbacks[0][1]
        s.ending=True; callback()
        self.assertIsNone(s.active)

    def test_group_consent_cannot_authorize_physical_phase(self):
        s=self.suite(); s.confirm.set(True); s.confirm_phase()
        consent=s.auto_group_consent
        s.active=None; s.index=3; s.start_phase(consent)
        self.assertIsNone(s.active)

    def test_bilingual_prompts_distinguish_press_hold_and_release(self):
        phases={name:(title,text) for name,title,text in diagnostic.PHASES}
        emergency=phases["emergency"][1]
        owned=phases["owned_release"][1]
        self.assertIn("Ctrl+Alt+F9",emergency)
        self.assertIn("松开这三个键",emergency)
        self.assertIn("不要提前按键",emergency)
        self.assertIn("按住键盘右侧 Shift",owned)
        self.assertIn("现在松开右 Shift",owned)
        self.assertIn("Do not touch the mouse",owned)
        for name,(title,text) in phases.items():
            self.assertTrue(any("\u4e00"<=ch<="\u9fff" for ch in title+text))
            self.assertIn("/",title)

    def test_real_target_down_shows_current_key_action_but_ending_never_does(self):
        for index,key in [(3,"Ctrl+Alt+F9"),(4,"Shift")]:
            s=self.suite(index); s.active={"event_start":0}
            s.status.set("等待事件"); s.target_event("down")
            self.assertIn(key,s.status.get())
            self.assertIn("需要你操作",s.status.get())
            s.ending=True; s.status.set("已经结束"); s.target_event("down")
            self.assertEqual(s.status.get(),"已经结束")

    def test_chinese_display_preserves_key_names_and_hides_translation(self):
        value="当前状态：已按下\n下一步：同时按 Ctrl+Alt+F9\nNOW press Ctrl+Alt+F9."
        self.assertEqual(diagnostic.chinese_prompt(value),"当前状态：已按下\n下一步：同时按 Ctrl+Alt+F9")
        self.assertEqual(diagnostic.chinese_prompt("自动检查 / Automatic checks"),"自动检查")
if __name__=="__main__": main()
