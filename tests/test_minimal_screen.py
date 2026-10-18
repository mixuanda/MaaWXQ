"""Synthetic minimal records exercise real-source transport, never a game result."""
from copy import deepcopy
import unittest
from strategy.advisor import Advisor
from strategy.minimal_screen import project_minimal
from runtime.minimal_state import extract,REGIONS
from runtime.strategy_bridge import ScreenAdvisorBridge,unverified_configuration
from runtime.replay_strategy import replay


class MinimalScreenTests(unittest.TestCase):
    def setUp(self):
        self.at='2026-01-01T00:00:00Z'
        self.frame={'sha256':'a'*64,'captured_at':self.at,'image':'synthetic-fixture.png',
                    'identity':{'identity_version':'fixture-game'}}
        self.state={'scene':'battle_controls','match_started':True,'frame_sha256':'a'*64,
                    'matches':[{'name':key,'score':.98} for key in ('battle_settings','own_portrait','statistics')]}
        def bundle(key,text):
            return {'roi':{'source_sha256':'a'*64,'image_sha256':'b'*64,'source_rect':REGIONS[key]},
                    'ocr':{'status':'recognized','image_sha256':'b'*64,'text':text}}
        self.minimal=extract(self.frame,self.state,{'round':bundle('round','第4回合45s'),
                                                  'energy':bundle('energy','28')},now=self.at)
        self.minimal['source_capture_reused']=False
        self.minimal['source_mode']='live_capture'
        self.advisor=Advisor(unverified_configuration())
        self.bridge=ScreenAdvisorBridge(self.advisor,match_id='fixture-custom')

    def test_candidates_survive_live_projection_but_do_not_become_strategy_facts(self):
        result=self.bridge.observe_frame(self.frame,self.state,minimal_state=self.minimal,
                                          now=self.at,source_mode='live_capture')
        self.assertEqual(result['status'],'advisor_observed_actual_frame')
        projection=result['projection']
        self.assertEqual(projection['field_evidence']['round']['candidate'],4)
        self.assertEqual(projection['field_evidence']['timer_seconds']['candidate'],45)
        self.assertEqual(projection['field_evidence']['resources.energy']['candidate'],28)
        self.assertIsNone(self.advisor.state.round)
        self.assertIsNone(next(x.field.value for x in self.advisor.state.fields if x.field.key=='credits'))
        self.assertEqual(self.advisor.state.fields[0].source.kind,'screen_recognition')
        self.assertIsNone(result['decision']['action_proposal'])
        self.assertEqual(next(row['candidate']for row in projection['first_action_requirements']['inputs']
                              if row['path']=='resources.energy'),28)
        self.assertFalse(result['input_allowed'])

    def test_replay_keeps_original_time_and_cannot_mutate_the_live_advisor(self):
        self.minimal['source_capture_reused']=True
        result=self.bridge.observe_frame(self.frame,self.state,minimal_state=self.minimal,
                                          now='2026-01-01T00:20:00Z')
        self.assertEqual(result['status'],'replay_projection_only')
        self.assertIsNone(self.advisor.state.match_id)
        record=replay(self.minimal,self.frame,self.state,now='2026-01-01T00:20:00Z')
        self.assertEqual(record['projection']['provenance']['age_seconds'],1200)
        self.assertEqual(record['observation_receipt']['records'][0]['observed_at'],self.at)
        self.assertIsNone(record['decision']['action_proposal'])
        with self.assertRaisesRegex(ValueError,'reused frame'):
            self.bridge.observe_frame(self.frame,self.state,minimal_state=self.minimal,
                                      now=self.at,source_mode='live_capture')

    def test_mismatch_future_and_slow_live_ocr_cannot_issue_a_proposal(self):
        for key,value in (('captured_at','2026-01-01T00:00:01Z'),('processed_at','2026-01-01T00:00:01Z')):
            minimal=deepcopy(self.minimal);minimal[key]=value
            with self.assertRaises(ValueError):
                project_minimal(minimal,self.frame,self.state,match_id='fixture',now=self.at)
        result=self.bridge.observe_frame(self.frame,self.state,minimal_state=self.minimal,
                                          now='2026-01-01T00:00:16Z',source_mode='live_capture')
        self.assertEqual(result['status'],'fresh_recognition_required')
        self.assertIsNone(self.advisor.state.match_id)
        self.assertEqual(self.advisor.decide(decision_at='2026-01-01T00:00:16Z')['blocking_gaps'][0]['code'],
                         'fresh_recognition_required')

    def test_unknown_scene_and_duplicate_regions_suspend_previous_context(self):
        for duplicate in (False,True):
            state=deepcopy(self.state);minimal=deepcopy(self.minimal)
            if duplicate:state['matches'].append(deepcopy(state['matches'][0]))
            else:state.update(scene='unknown',match_started=False);minimal['scene']='unknown'
            result=self.bridge.observe_frame(self.frame,state,minimal_state=minimal,
                                              now=self.at,source_mode='live_capture')
            self.assertEqual(result['status'],'not_battle_evidence')
            self.assertIsNone(self.advisor.decide(decision_at=self.at)['action_proposal'])

    def test_explicitly_verified_fields_are_not_lost_and_energy_is_still_separate(self):
        def known(value):return {'status':'observed','value':value,'confidence':.94}
        minimal=deepcopy(self.minimal)
        minimal.update(round=known(4),phase=known('planning'),game_build=known('fixture-build'),
                       rules_version=known('fixture-rules'))
        minimal['strategy_fields']={'credits':known(27),'hand_ids':known(['fixture-unit'])}
        batch=project_minimal(minimal,self.frame,self.state,match_id='fixture',now=self.at)['recognition_batch']
        self.assertEqual(batch['context']['context_confidence'],.94)
        self.assertEqual(batch['context']['round'],4)
        self.assertEqual(next(x['value'] for x in batch['own_fields'] if x['key']=='credits'),27)
        self.assertEqual(minimal['resources']['energy']['candidate'],28)


if __name__=='__main__':unittest.main()
