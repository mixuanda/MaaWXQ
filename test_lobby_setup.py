import unittest
from dataclasses import replace
from unittest.mock import Mock
from runtime.lobby import recognize,decide
from backends.game_click import GameClickEvidence,GameClickBroker,Binding,NativeUnavailable
from test_win32_single_click import observed
class LobbyTests(unittest.TestCase):
    def test_selection_click_requires_all_visible_anchors(self):
        layouts={'yixing_character_choice':['selection_title','yixing_name','picker_context','yixing_target'],
                 'yixing_character_confirm':['selection_title','selected_yixing','selected_marker','confirm_label']}
        for layout,names in layouts.items():
            frame={'layout':layout,'sha256':'f'*64,'matches':[{'name':n,'score':1,'center':[447,790]}for n in names]}
            state=recognize(frame)
            self.assertEqual(decide(state)['action'],'click')
            self.assertFalse(state['requested_player_verified'])
            self.assertFalse(state['other_humans_verified_absent'])
            for row in frame['matches']:
                row['score']=.94
                self.assertEqual(decide(recognize(frame))['action'],'stop')
                row['score']=1
    def test_selection_adapter_requires_custom_origin_and_absence(self):
        row=observed();row['class_name']='UnityWndClass'
        evidence=GameClickEvidence(Binding.from_observation(row),10,447,790,context='custom_setup',
            operation='select_owned_yixing',scene='yixing_character_choice',frame_sha256='e'*64,
            recognizer='yixing_character_choice-glyphs/1',executable_path=r'C:\Synthetic\WXQ.exe',
            no_other_humans_verified=True,custom_selection_origin_sha256='d'*64)
        GameClickBroker(evidence,observer=Mock()).validate_context()
        for change in ({'custom_selection_origin_sha256':''},{'custom_selection_origin_sha256':'X'*64},
                       {'no_other_humans_verified':False},{'operation':'confirm_yixing_selection'},
                       {'recognizer':'unverified'},{'scene':'ranked_selection'}):
            with self.assertRaises(NativeUnavailable):GameClickBroker(replace(evidence,**change),observer=Mock()).validate_context()
    def test_observer_permit_only_unlocks_complete_five_bot_custom_start(self):
        names=['lobby_title','room_settings','start_game']+['bot_'+kind+'_'+str(i)for kind in ('avatar','label')for i in range(1,6)]
        frame={'layout':'custom_lobby_start','sha256':'e'*64,'matches':[{'name':n,'score':1,'center':[3,4]}for n in names]}
        state=recognize(frame)
        self.assertEqual(decide(state,'a'*64)['operation'],'begin_custom_selection')
        frame['matches'].pop()
        self.assertEqual(decide(recognize(frame),'a'*64)['action'],'stop')
    def test_full_lobby_cannot_start_without_real_yixing_confirmation(self):
        names=['lobby_title','room_settings','start_game']+['bot_'+kind+'_'+str(i)for kind in ('avatar','label')for i in range(1,6)]
        frame={'layout':'custom_lobby_start','sha256':'e'*64,'matches':[{'name':n,'score':1,'center':[3,4]}for n in names]}
        state=recognize(frame)
        self.assertEqual(decide(state)['reason'],'yixing_selection_confirmation_not_implemented')
        state.update(requested_player_verified=True,yixing_owned=True,skin_equipped=True)
        self.assertEqual(decide(state)['action'],'stop')
        for row in frame['matches']:
            row['score']=0;self.assertEqual(decide(recognize(frame))['action'],'stop');row['score']=1
    def test_start_adapter_blocks_even_when_lobby_evidence_is_complete(self):
        row=observed();row['class_name']='UnityWndClass'
        ev=GameClickEvidence(Binding.from_observation(row),10,1,1,context='custom_setup',operation='begin_custom_selection',
            scene='full_bot_custom_lobby',no_other_humans_verified=True,frame_sha256='a'*64,
            recognizer='full-bot-lobby-glyphs/1',executable_path=r'C:\Synthetic\WXQ.exe')
        with self.assertRaisesRegex(NativeUnavailable,'yixing_selection_confirmation_not_implemented'):
            GameClickBroker(ev,observer=Mock()).validate_context()
        with self.assertRaises(NativeUnavailable):GameClickBroker(replace(ev,no_other_humans_verified=False),observer=Mock()).validate_context()
    def test_difficulty_requires_all_labels_and_exact_one_selected(self):
        ranks=['newbie','bronze','silver','gold','platinum','diamond','xingyao','wangzhe']
        names=['room_options_title','difficulty_label','room_options_close']+['difficulty_'+x for x in ranks]
        frame={'layout':'room_options','sha256':'d'*64,'matches':[{'name':n,'score':1,'center':[3,4]} for n in names],
               'settings_choices':[{'name':n,'center':[3,4],'selected':n=='newbie'} for n in ranks]}
        self.assertEqual(decide(recognize(frame))['operation'],'select_xingyao_bot_difficulty')
        frame['settings_choices'][6]['selected']=True
        self.assertEqual(decide(recognize(frame))['action'],'stop')
        frame['settings_choices'][0]['selected']=False
        self.assertEqual(decide(recognize(frame))['reason'],'xingyao_already_selected')
        frame['layout']='room_options_close'
        self.assertEqual(decide(recognize(frame))['operation'],'close_verified_room_options')
    def test_bot_and_all_remaining_empty_slots_required_for_room_settings(self):
        names=['lobby_title','room_settings','bot_label_1','bot_avatar_1']+['empty_'+str(i) for i in range(2,6)]
        frame={'layout':'custom_lobby_onebot','sha256':'c'*64,'matches':[{'name':n,'score':1,'center':[3,4]} for n in names]}
        state=recognize(frame);self.assertEqual(decide(state)['operation'],'open_room_settings')
        self.assertEqual(state['bot_difficulty'],'unknown')
        for row in frame['matches']:
            row['score']=0;self.assertEqual(decide(recognize(frame))['action'],'stop');row['score']=1
    def test_guidance_settings_supports_only_return_navigation(self):
        names=['settings_back','settings_title','ai_master','lingbao_selected']
        frame={'layout':'guidance_settings','sha256':'b'*64,'matches':[{'name':n,'score':1,'center':[3,4]} for n in names]}
        state=recognize(frame)
        self.assertEqual(decide(state)['operation'],'return_from_guidance_settings')
        self.assertFalse(state['room_verified'])
        frame['matches'].pop()
        self.assertEqual(decide(recognize(frame))['action'],'stop')
    def test_each_other_slot_and_lobby_context_are_required(self):
        names=['lobby_title','ai_settings','start_game']+['empty_'+str(i) for i in range(1,6)]
        frame={'sha256':'a'*64,'matches':[{'name':n,'score':1,'center':[3,4]} for n in names]}
        self.assertEqual(decide(recognize(frame))['operation'],'open_ai_settings')
        for item in frame['matches']:
            item['score']=0
            self.assertEqual(decide(recognize(frame))['action'],'stop')
            item['score']=1
        frame['layout']='custom_lobby_bot_menu'
        self.assertEqual(decide(recognize(frame))['action'],'stop')
        frame['matches'].append({'name':'empty_slot_robot','score':1,'center':[3,4]})
        self.assertEqual(decide(recognize(frame))['operation'],'open_bot_selection')
    def test_lobby_adapter_rejects_missing_absence_evidence_and_start_match(self):
        row=observed();row['class_name']='UnityWndClass'
        evidence=GameClickEvidence(Binding.from_observation(row),10,1,1,context='custom_setup',operation='open_ai_settings',
            scene='empty_custom_lobby',no_other_humans_verified=True,frame_sha256='a'*64,
            recognizer='empty-custom-lobby-glyphs/1',executable_path=r'C:\Synthetic\WXQ.exe')
        GameClickBroker(evidence,observer=Mock()).validate_context()
        for update in ({'no_other_humans_verified':False},{'operation':'start_game'},{'scene':'unknown'}):
            with self.assertRaises(NativeUnavailable):GameClickBroker(replace(evidence,**update),observer=Mock()).validate_context()
if __name__=='__main__':unittest.main()
