"""Bind the specialized live-art hand transition to a purchase; no input APIs."""
import hashlib
import math
from strategy.codec import timestamp
from runtime.purchase_recognition import numeric_candidate


def matcher_labels(hero_ids):
    """ASCII identities for the C# matcher; unknown offers remain competitors."""
    if not isinstance(hero_ids,(list,tuple))or len(hero_ids)!=4:
        raise ValueError('four_offer_identities_required')
    result=[]
    for index,hero in enumerate(hero_ids):
        if hero is None or(isinstance(hero,str)and hero.strip().casefold()in ('','unknown','unresolved','?')):
            result.append('unknown-slot-'+str(index))
        elif not isinstance(hero,str)or len(hero)>256:
            raise ValueError('bounded_hero_identity_required')
        else:result.append('hero-'+hashlib.sha256(hero.encode('utf-8')).hexdigest())
    return result


def _finite(value,low,high):
    return type(value)in(int,float)and math.isfinite(value)and low<=value<=high


def _digest(value):
    if not isinstance(value,str)or len(value)!=64 or any(c not in '0123456789abcdef'for c in value):
        raise ValueError('lowercase_frame_sha256_required')
    return value


def _match(hand,key,x,y,radius,minimum,scales):
    row=hand[key]
    if (not _finite(row.get('Score'),minimum,1)or not _finite(row.get('X'),x-radius,x+radius)
            or not _finite(row.get('Y'),y-radius,y+radius)
            or not any(_finite(row.get('Scale'),scale-1e-9,scale+1e-9)for scale in scales)):
        raise ValueError('hand_match_constraints_not_met:'+key)
    return row['Score']


def make_snapshot(intent,after,*,source_sha256,source_mode='saved_replay'):
    """Use the ACTUAL dispatched intent and the same preaction bitmap as C#.

    The producer must hash/bind both bitmaps before accepting HandAppearance's
    result. This helper independently checks the reported predicates/bindings;
    PurchaseHandler.verify still checks current time, currency delta and hero.
    Replay is the default and cannot be silently promoted to live verification.
    """
    if source_mode not in ('saved_replay','live_capture'):raise ValueError('explicit_source_mode_required')
    if after.get('source_mode')is not None and after['source_mode']!=source_mode:
        raise ValueError('postcondition_source_mode_mismatch')
    if source_mode=='live_capture'and after.get('source_capture_reused')is True:
        raise ValueError('reused_frame_cannot_be_live_postcondition')
    if source_sha256!=_digest(intent['frame_sha256']):raise ValueError('hand_art_source_not_bound_to_purchase')
    digest=_digest(after['sha256'])
    if digest==source_sha256 or timestamp(after['captured_at'])<=timestamp(intent['captured_at']):
        raise ValueError('new_postcondition_frame_required')
    if after['identity']['identity_version']!=intent['identity_version']:
        raise ValueError('hand_postcondition_identity_changed')
    client=after['identity']['client']
    if (client['width'],client['height'])!=(1450,869):raise ValueError('unsupported_hand_geometry')
    hand=after['hand_appearance'];energy=numeric_candidate(after['numbers']['energy'])
    if (hand.get('Known')is not True or type(hand.get('BeforeCount'))is not int
            or type(hand.get('AfterCount'))is not int or(hand['BeforeCount'],hand['AfterCount'])!=(2,3)):
        raise ValueError('observed_two_to_three_transition_required')
    _match(hand,'Passive',556,774,3,.97,(1,))
    _match(hand,'Equipment',689,778,3,.97,(1,))
    received=_match(hand,'Received',795,787,6,.92,(.585,.595,.605,.615))
    if (not _finite(hand.get('DistinctHeroMargin'),.12,2)
            or not _finite(hand.get('BeforePassiveHero'),-1,1)or hand['BeforePassiveHero']>=.75
            or not _finite(hand.get('BeforeEquipmentHero'),-1,1)or hand['BeforeEquipmentHero']>=.75):
        raise ValueError('distinct_new_hero_constraints_not_met')
    scores=hand.get('OfferScores')
    if (not isinstance(scores,list)or len(scores)!=4 or any(not _finite(score,-1,1)for score in scores)
            or not any(abs(score-received)<=1e-9 for score in scores)):
        raise ValueError('purchased_offer_comparison_required')
    if energy is None:raise ValueError('observed_postcondition_currency_required')
    slots=intent['empty_legal_slots']
    if not isinstance(slots,(list,tuple))or len(slots)!=1 or not isinstance(slots[0],str)or not slots[0]:
        raise ValueError('single_logical_receiving_slot_required')
    def observed(value,score,evidence):
        return {'status':'observed','value':value,'confidence':score,
                'confidence_kind':'uncalibrated_component_or_live_art_similarity',
                'frame_sha256':digest,'observed_at':after['captured_at'],'evidence_ref':evidence}
    return {'schema':'purchase-screen/1','frame':{'sha256':digest,'captured_at':after['captured_at'],
             'identity_version':after['identity']['identity_version'],'match_id':intent['match_id'],
             'source_kind':'screen_recognition','source_mode':source_mode},
            'currencies':[{'id':intent['currency_id'],'balance':observed(energy['value'],energy['score'],'numeric-components:'+digest)}],
            'hand_slots':[{'id':slots[0],'hero_id':observed(intent['hero_id'],received,
             'live-shop-art-and-two-to-three-hand-transition:'+source_sha256+':'+digest)}],
            'execution_allowed':False}
