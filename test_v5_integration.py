"""Offline V5 integration checks. All native/input dependencies are substituted."""
from copy import deepcopy
import hashlib,json,tempfile,unittest
from pathlib import Path
from unittest.mock import Mock,patch
from test_win32_single_click import observed
from runtime import lobby_setup,fill_bots,observe_minimal_state
from runtime.lobby import recognize,decide
from runtime.bot_fill import recognize as bot_recognize,decide as bot_decide
from test_bot_fill import frame as bot_frame


class V5IntegrationTests(unittest.TestCase):
    def test_view_details_is_a_deterministic_inspection_with_positive_evidence(self):
        names=('yixing_title','copy_heroes','passive_name','secret_label','view_details')
        frame={'layout':'yixing_ability_tooltip','sha256':'a'*64,
               'matches':[{'name':name,'score':.99,'center':[500,200]}for name in names]}
        state=recognize(frame)
        decision=decide(state)
        self.assertEqual(decision['operation'],'view_yixing_passive_details')
        self.assertEqual(decision['target'],[500,200])
        self.assertFalse(state['requested_player_verified'])
        self.assertFalse(state['match_started'])
        for row in frame['matches']:
            row['score']=0
            self.assertEqual(decide(recognize(frame))['action'],'stop')
            row['score']=.99
        frame['matches'].append(deepcopy(frame['matches'][-1]))
        self.assertEqual(decide(recognize(frame))['action'],'stop')

    def test_duplicate_or_nonfinite_bot_evidence_does_not_authorize_input(self):
        for corrupt in ('duplicate','nan','above_one'):
            frame=bot_frame()
            if corrupt=='duplicate':frame['matches'].append(deepcopy(frame['matches'][0]))
            else:frame['matches'][0]['score']=float('nan') if corrupt=='nan' else 1.1
            self.assertEqual(bot_decide(bot_recognize(frame))['action'],'stop')

    def test_lobby_and_fill_stop_before_postcondition_capture_on_port_cleanup_failure(self):
        security=dict(known=True,app_container=False,ui_access=False,elevated=False,integrity_rid=8192)
        row=observed();row.update(title='fixture',class_name='UnityWndClass',executable_path=r'C:\synthetic\WXQ.exe',process_security=security)
        source_frame=dict(identity=row,observed_monotonic=1,sha256='a'*64)
        state={'scene':'yixing_ability_tooltip','other_humans_verified_absent':False,
               'recognizer':'yixing-ability-tooltip-glyphs/1','frame_sha256':'a'*64}
        decision={'action':'click','operation':'view_yixing_passive_details','target':[1,1]}
        for runner in (lobby_setup,fill_bots):
            with self.subTest(runner=runner.__name__),tempfile.TemporaryDirectory()as directory:
                root=Path(directory);reference=root/'reference.fixture';reference.write_bytes(b'fixture')
                profile=root/'profile.json';profile.write_text(json.dumps(row),encoding='utf-8')
                digest=hashlib.sha256(b'fixture').hexdigest()
                broker=Mock();broker.stop_reason='one_action_completed';broker.release_confirmed=True
                broker.cleanup_errors=[];broker.port.cleanup_errors=['fixture_port_close_failure']
                broker.port.held=False;broker.port.submitted_event_count=2;broker.port.owned_release_last_raw_return=1
                broker.port.activity_marker.return_value=7
                broker.click_once.return_value={'sent':True}
                with patch.object(runner,'process_security',return_value=security),patch.object(runner,'find_windows',return_value=[row]),patch.object(runner,'inspect_game',return_value=row),patch.object(runner,'capture',return_value=source_frame)as capture,patch.object(runner,'recognize',return_value=state),patch.object(runner,'decide',return_value=decision),patch.object(runner,'GameClickBroker',return_value=broker),patch.object(runner.time,'sleep'):
                    if runner is lobby_setup:
                        result=runner.run(root/'run',reference,digest,profile,True,False)
                        self.assertEqual(capture.call_count,2)
                    else:
                        result=runner.run(root/'run',profile,reference,digest,reference,digest,True,False)
                        self.assertEqual(capture.call_count,1)
                self.assertEqual(result['status'],'stopped')
                self.assertIn('native_cleanup_not_confirmed',result['error'])

    def test_ocr_crops_share_full_capture_budget_and_do_not_start_ocr_when_full(self):
        with tempfile.TemporaryDirectory()as directory:
            root=Path(directory);image=root/'source.png';image.write_bytes(b'fixture')
            for i in range(50):(root/f'{i}.png').touch()
            frame={'image':str(image),'sha256':hashlib.sha256(b'fixture').hexdigest()}
            state={'frame_sha256':frame['sha256'],'scene':'battle_controls','match_started':True}
            with patch.object(observe_minimal_state,'read_regions')as batch:
                with self.assertRaisesRegex(RuntimeError,'capture_budget_full'):
                    observe_minimal_state.run_saved(frame,state,root/'ocr',budget_root=root)
                batch.assert_not_called()

    def test_parameterized_selection_watcher_is_safe_to_import(self):
        import runtime.selection_watch as watcher
        self.assertTrue(callable(watcher.main))


if __name__=='__main__':unittest.main()
