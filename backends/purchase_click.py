"""Explicit custom-room purchase adapter, using existing native guards unchanged."""
from dataclasses import dataclass
from datetime import datetime,timezone
from strategy.codec import timestamp
from strategy.purchase import PurchaseIntent
from backends.game_click import GameClickBroker,GameClickEvidence,Binding,NativeUnavailable
from runtime.cleanup import close_verified


@dataclass(frozen=True)
class PurchaseClickEvidence(GameClickEvidence):
    purchase:PurchaseIntent|None=None


class PurchaseClickBroker(GameClickBroker):
    def __init__(self,*args,utc_clock=None,**kwargs):
        self.utc_clock=utc_clock or(lambda:datetime.now(timezone.utc))
        super().__init__(*args,**kwargs)

    def validate_context(self):
        e=self.evidence;p=getattr(e,'purchase',None)
        if (not isinstance(e,PurchaseClickEvidence)or not isinstance(p,PurchaseIntent)
                or e.context!='custom_purchase' or e.operation!='buy_shop_offer'
                or e.scene!='purchase_enabled' or e.recognizer!='purchase-screen/1'
                or e.frame_sha256!=p.frame_sha256 or (e.x,e.y)!=p.target
                or e.binding.class_name!='UnityWndClass' or not e.executable_path.casefold().endswith('\\wxq.exe')
                or type(p.effective_price)is not int or type(p.balance)is not int
                or not 0<=p.effective_price<=p.balance or not p.empty_legal_slots
                or not p.hero_id or not p.currency_id or not p.match_id
                or not 0<(timestamp(p.expires_at)-timestamp(p.captured_at)).total_seconds()<=5
                or p.source_mode!='live_capture' or not timestamp(p.captured_at)<=self.utc_clock()<=timestamp(p.expires_at)):
            raise NativeUnavailable('unsupported_or_stale_custom_purchase')


def guarded_executor(frame,*,observer,enabled=False,utc_clock=None):
    """Factory only. Returned callback can send ONE click when explicitly enabled."""
    def execute(intent):
        if (frame['sha256']!=intent.frame_sha256 or frame['captured_at']!=intent.captured_at
                or frame['identity']['identity_version']!=intent.identity_version):
            raise ValueError('purchase_native_frame_binding_mismatch')
        ev=PurchaseClickEvidence(Binding.from_observation(frame['identity']),frame['observed_monotonic'],
             *intent.target,context='custom_purchase',operation='buy_shop_offer',scene='purchase_enabled',
             frame_sha256=intent.frame_sha256,recognizer='purchase-screen/1',
             executable_path=frame['identity']['executable_path'],purchase=intent)
        broker=PurchaseClickBroker(ev,observer=observer,enabled=enabled,utc_clock=utc_clock,max_age=5,max_seconds=2)
        cleanup_finished=False
        try:
            broker.arm();receipt=broker.click_once();summary,_=close_verified(broker)
            cleanup_finished=True
            return receipt|{'cleanup_confirmed':True,'native_summary':summary}
        finally:
            if not cleanup_finished:broker.close()
    return execute
