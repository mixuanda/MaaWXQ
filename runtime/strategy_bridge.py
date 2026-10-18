"""Connect partial real screen evidence to a persistent Advisor without input."""
import uuid

from strategy.minimal_screen import project_minimal
from strategy.recognition import ingest_frame


def unverified_configuration():
    return {'schema_version':'strategy-session/1','engine':'reviewed_rules',
            'label':'actual custom match; unresolved gameplay registry',
            'rule_data':{'schema_version':'1.0','game_build':None,'rules_version':'unverified',
                         'domain':'gameplay','ban_semantics_verified':False,'rules':[]}}


class ScreenAdvisorBridge:
    def __init__(self,advisor,*,match_id=None):
        self.advisor=advisor
        self.match_id=match_id or 'custom-observed-'+uuid.uuid4().hex
        self.started=False
        self.index=0
        self.binding=None

    def observe_frame(self,frame,state,*,minimal_state,now,source_mode='saved_replay'):
        """Saved replay is diagnostic only; live ingestion must be explicit."""
        try:
            projection=project_minimal(minimal_state,frame,state,match_id=self.match_id,
                                       now=now,source_mode=source_mode,start_match=not self.started)
            result={'projection':projection,'input_allowed':False,'source_is_synthetic':False,
                    'observations':[],'receipts':[],'decision':None}
            if source_mode=='saved_replay':
                return result|{'status':'replay_projection_only'}
            binding=frame['identity']['identity_version']
            if self.binding is not None and self.binding!=binding:
                raise ValueError('game_identity_changed')
            if not projection['provenance']['fresh_within_5_seconds']:
                self.advisor.invalidate('screen_extraction_older_than_5_seconds',now=now)
                return result|{'status':'fresh_recognition_required'}
            receipt=ingest_frame(self.advisor,projection['recognition_batch'],now=now)
            if receipt['status']!='observed':
                return result|{'status':'not_battle_evidence','recognition':receipt}
            self.binding=binding
            self.started=True
            self.index+=1
            decision=self.advisor.decide(decision_at=now,point_id='capture-'+str(self.index))
            return result|{'status':'advisor_observed_actual_frame','recognition':receipt,
                           'observations':receipt['records'],'receipts':receipt['event_receipts'],'decision':decision}
        except (ValueError,TypeError,KeyError):
            if source_mode=='live_capture':
                self.advisor.invalidate('minimal_screen_projection_invalid',now=now)
            raise

    def validate_for_dispatch(self,proposal_id,*,now,operation,reviewed_handlers):
        validation=self.advisor.validate(proposal_id,now=now)
        if not validation['candidate_valid']:
            return {'status':'strategy_rejected','validation':validation,'input_allowed':False}
        if operation not in reviewed_handlers:
            return {'status':'game_action_adapter_unavailable','validation':validation,'input_allowed':False}
        return {'status':'advisory_candidate_valid','validation':validation,'input_allowed':False}
