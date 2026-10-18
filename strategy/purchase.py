"""One visible purchase: frame-bound legality and transparent deterministic scores.

No combat model, unit parameters, automatic OCR promotion, or input dependency.
"""
from dataclasses import dataclass,asdict
from datetime import timedelta
import math
from .codec import timestamp


def _id(value):
    if not isinstance(value,str) or not value.strip():raise ValueError('resolved_identifier_required')
    return value


def _number(value):
    return type(value) in (int,float) and math.isfinite(value)


def field(snapshot,record,*,minimum=.8):
    frame=snapshot['frame']
    if (not isinstance(record,dict) or record.get('status')!='observed' or record.get('value')is None
            or not _number(record.get('confidence')) or not minimum<=record['confidence']<=1
            or record.get('frame_sha256')!=frame['sha256'] or record.get('observed_at')!=frame['captured_at']
            or not record.get('evidence_ref')):
        raise ValueError('field_unknown_uncertain_or_not_bound_to_current_capture')
    return record['value']


def check_frame(snapshot,*,now,max_age=5,live=False):
    if not _number(max_age)or not 0<max_age<=5:raise ValueError('purchase_ttl_must_not_exceed_5_seconds')
    if snapshot.get('schema')!='purchase-screen/1':raise ValueError('unsupported_purchase_screen')
    frame=snapshot['frame'];digest=frame.get('sha256')
    if not isinstance(digest,str) or len(digest)!=64 or any(c not in '0123456789abcdef'for c in digest):
        raise ValueError('invalid_purchase_frame_hash')
    for key in ('identity_version','match_id'):_id(frame.get(key))
    if frame.get('source_kind')!='screen_recognition' or frame.get('source_mode')not in ('live_capture','saved_replay'):
        raise ValueError('explicit_screen_source_mode_required')
    age=(timestamp(now)-timestamp(frame['captured_at'])).total_seconds()
    if not 0<=age<=max_age:raise ValueError('purchase_frame_stale_or_future')
    if live and frame['source_mode']!='live_capture':raise ValueError('replay_cannot_dispatch')
    return frame


@dataclass(frozen=True)
class ScoreTerm:
    name:str
    value:float
    source_reference:str

    def __post_init__(self):
        _id(self.name);_id(self.source_reference)
        if not _number(self.value):raise ValueError('nonfinite_purchase_score')


@dataclass(frozen=True)
class PurchaseIntent:
    frame_sha256:str
    captured_at:str
    expires_at:str
    identity_version:str
    match_id:str
    source_mode:str
    offer_slot:str
    hero_id:str
    currency_id:str
    balance:int
    effective_price:int
    target:tuple[int,int]
    empty_legal_slots:tuple[str,...]
    score:float
    score_terms:tuple[ScoreTerm,...]
    evidence_refs:tuple[str,...]

    def to_dict(self):return asdict(self)


def rank_purchases(snapshot,*,now,scorer=None,max_age=5):
    """Scorer receives a detached resolved offer and returns explicit ScoreTerms.

    Default score is negative confirmed price, labelled as cost minimization.
    Optional hero/synergy terms are caller supplied, never claimed as game stats.
    Unknown legality/price/currency/phase stops that candidate before scoring.
    """
    try:
        frame=check_frame(snapshot,now=now,max_age=max_age)
        if field(snapshot,snapshot['mode'])!='custom':raise ValueError('custom_mode_not_observed')
        if field(snapshot,snapshot['phase'])!='purchase_enabled':raise ValueError('purchase_phase_not_observed')
        currencies=snapshot['currencies'];hands=snapshot['hand_slots'];offers=snapshot['offers']
        if any(not isinstance(rows,list) or len(rows)>32 for rows in (currencies,hands,offers)):
            raise ValueError('bounded_purchase_arrays_required')
        for rows in (currencies,hands,offers):
            keys=[_id(row['id'])for row in rows]
            if len(keys)!=len(set(keys)):raise ValueError('duplicate_purchase_slot_or_currency')
        empty=[]
        for slot in hands:
            try:
                if field(snapshot,slot['empty'])is True and field(snapshot,slot['legal'])is True:empty.append(slot['id'])
            except ValueError:pass
        if not empty:raise ValueError('visible_legal_empty_hand_slot_required')
    except (ValueError,KeyError,TypeError)as error:
        return {'status':'stop','candidates':[],'rejected':[],'reason':str(error),'execution_allowed':False}
    candidates=[];rejected=[]
    for offer in offers:
        try:
            hero=_id(field(snapshot,offer['hero_id']))
            currency=_id(field(snapshot,offer['currency_id']))
            price=field(snapshot,offer['effective_price'])
            balance_row=next((row for row in currencies if row['id']==currency),None)
            if balance_row is None:raise ValueError('specified_currency_balance_unknown')
            balance=field(snapshot,balance_row['balance'])
            if type(price)is not int or price<0 or type(balance)is not int or balance<price:
                raise ValueError('invalid_price_or_insufficient_specified_currency')
            if field(snapshot,offer['purchasable'])is not True:raise ValueError('offer_not_visibly_purchasable')
            target=field(snapshot,offer['target'])
            if not isinstance(target,(list,tuple))or len(target)!=2 or any(type(n)is not int or n<0 for n in target):
                raise ValueError('invalid_recognized_purchase_target')
            terms=[ScoreTerm('minimize_confirmed_price',-price,'frame:'+frame['sha256'])]
            resolved={'offer_slot':offer['id'],'hero_id':hero,'currency_id':currency,'effective_price':price,'balance':balance}
            if scorer is not None:
                extra=tuple(scorer(dict(resolved)))
                if len(extra)>32 or any(not isinstance(term,ScoreTerm)for term in extra):raise ValueError('explicit_bounded_score_terms_required')
                terms.extend(extra)
            score=math.fsum(term.value for term in terms)
            if not math.isfinite(score):raise ValueError('nonfinite_total_score')
            refs=[snapshot['mode']['evidence_ref'],snapshot['phase']['evidence_ref'],balance_row['balance']['evidence_ref']]
            refs.extend(offer[key]['evidence_ref']for key in ('hero_id','currency_id','effective_price','purchasable','target'))
            refs.extend(slot[key]['evidence_ref']for slot in hands if slot['id']in empty for key in ('empty','legal'))
            candidates.append(PurchaseIntent(frame['sha256'],frame['captured_at'],
                (timestamp(frame['captured_at'])+timedelta(seconds=max_age)).isoformat(),
                frame['identity_version'],frame['match_id'],frame['source_mode'],offer['id'],hero,currency,
                balance,price,tuple(target),tuple(sorted(empty)),score,tuple(terms),tuple(refs)))
        except (ValueError,KeyError,TypeError)as error:rejected.append({'offer_slot':offer.get('id'),'reason':str(error)})
    candidates.sort(key=lambda row:(-row.score,row.effective_price,row.offer_slot))
    return {'status':'candidate'if candidates else'stop','candidates':candidates,'rejected':rejected,
            'scoring_scope':'visible_purchase_cost_plus_explicit_caller_terms','execution_allowed':False}


def equivalent_purchase(left,right):
    keys=('identity_version','match_id','offer_slot','hero_id','currency_id','balance','effective_price','target','empty_legal_slots')
    return all(getattr(left,key)==getattr(right,key)for key in keys)


def verify_purchase(intent,after,*,now):
    """Require exact currency delta AND new hero in a previously legal empty slot."""
    currency_ok=appearance_ok=False;reasons=[];destination=None;actual_delta=None
    try:
        frame=check_frame(after,now=now,live=True)
        if (frame['identity_version']!=intent.identity_version or frame['match_id']!=intent.match_id
                or timestamp(frame['captured_at'])<=timestamp(intent.captured_at)or frame['sha256']==intent.frame_sha256):
            raise ValueError('postcondition_capture_not_new_same_game_and_match')
        currencies=after['currencies'];slots=after['hand_slots']
        if len({row['id']for row in currencies})!=len(currencies)or len({row['id']for row in slots})!=len(slots):
            raise ValueError('duplicate_postcondition_evidence')
        balance=next(row['balance']for row in currencies if row['id']==intent.currency_id)
        value=field(after,balance)
        if type(value)is not int:raise ValueError('postcondition_currency_not_integer')
        actual_delta=intent.balance-value;currency_ok=actual_delta==intent.effective_price
        appeared=[]
        for slot in slots:
            if slot['id']in intent.empty_legal_slots:
                try:
                    if field(after,slot['hero_id'])==intent.hero_id:appeared.append(slot['id'])
                except (KeyError,ValueError):pass
        appearance_ok=len(appeared)==1
        destination=appeared[0]if appearance_ok else None
        if not currency_ok:reasons.append('specified_currency_delta_not_equal_to_effective_price')
        if not appearance_ok:reasons.append('new_purchased_hero_not_uniquely_observed_in_previously_empty_slot')
    except (ValueError,KeyError,TypeError,StopIteration)as error:reasons.append(str(error)or'missing_postcondition_currency')
    verified=currency_ok and appearance_ok and not reasons
    return {'status':'purchase_verified'if verified else'unverified_stop','resource_delta_verified':currency_ok,
            'hero_appearance_verified':appearance_ok,'actual_resource_delta':actual_delta,'destination_slot':destination,
            'reasons':reasons,'blind_retry_allowed':False,'execution_allowed':False}
