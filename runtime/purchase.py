"""One-shot purchase session. Inject the guarded executor; nothing runs on import."""
from strategy.codec import timestamp
from strategy.purchase import rank_purchases,equivalent_purchase,verify_purchase
from dataclasses import replace
import uuid
import threading


class PurchaseHandler:
    def __init__(self):
        self._intent=None;self._proposal=None;self._attempted=False;self._receipt=None;self._submission_confirmed=False
        self._owner=threading.get_ident()

    def _require_owner(self):
        if threading.get_ident()!=self._owner:raise ValueError('purchase_handler_requires_single_owner_thread')

    def prepare(self,snapshot,*,now,scorer=None):
        self._require_owner()
        if self._attempted:raise ValueError('purchase_session_already_attempted')
        self._intent=self._proposal=None
        ranking=rank_purchases(snapshot,now=now,scorer=scorer)
        self._intent=ranking['candidates'][0]if ranking['candidates']else None
        self._proposal=uuid.uuid4().hex if self._intent else None
        return {'status':ranking['status'],'proposal_id':self._proposal,
                'selected':self._intent.to_dict()if self._intent else None,
                'ranking':[row.to_dict()for row in ranking['candidates']],
                'rejected':ranking['rejected'],'reason':ranking.get('reason'),'execution_allowed':False}

    def dispatch(self,proposal_id,preaction,*,now,executor):
        self._require_owner()
        if self._attempted:raise ValueError('purchase_session_already_attempted_no_retry')
        if not self._intent or proposal_id!=self._proposal:raise ValueError('purchase_proposal_unknown_or_superseded')
        if self._intent.source_mode!='live_capture':raise ValueError('replay_cannot_dispatch')
        if timestamp(now)>timestamp(self._intent.expires_at):raise ValueError('purchase_intent_expired')
        ranking=rank_purchases(preaction,now=now)
        fresh=next((row for row in ranking['candidates']if equivalent_purchase(row,self._intent)),None)
        if fresh is None:raise ValueError('purchase_preconditions_changed_or_unknown')
        if fresh.source_mode!='live_capture':raise ValueError('replay_cannot_dispatch')
        fresh=replace(fresh,expires_at=self._intent.expires_at,score=self._intent.score,
                      score_terms=self._intent.score_terms)
        self._attempted=True  # An uncertain callback outcome is consumed too.
        self._intent=fresh
        receipt=executor(fresh)
        self._receipt=dict(receipt)if isinstance(receipt,dict)else None
        if not self._receipt or self._receipt.get('sent')is not True or self._receipt.get('cleanup_confirmed')is not True:
            raise RuntimeError('purchase_submission_or_owned_cleanup_unconfirmed_no_retry')
        self._submission_confirmed=True
        return {'status':'purchase_submitted_requires_dual_postcondition','receipt':dict(self._receipt),
                'source_frame_sha256':fresh.frame_sha256,'execution_allowed':False}

    def verify(self,after,*,now):
        self._require_owner()
        if not self._submission_confirmed:
            raise ValueError('confirmed_purchase_submission_required')
        return verify_purchase(self._intent,after,now=now)
