"""Portable purchase-feature diagnostics; templates stay private and no input runs.

Ported from the frozen control-worker repair. Similarities are uncalibrated.
These results are candidates, not observed PurchaseHandler fields or permits.
"""
from datetime import datetime
import math


def _number(value):
    return type(value)in(int,float)and math.isfinite(value)


def _time(value):
    if not isinstance(value,str):raise ValueError('timestamp_string_required')
    result=datetime.fromisoformat(value.replace('Z','+00:00'))
    if result.tzinfo is None or result.utcoffset()is None:raise ValueError('timezone_required')
    return result


def _matches(frame):
    rows=frame['matches']
    if not isinstance(rows,list)or len(rows)>128:raise ValueError('bounded_match_array_required')
    result={}
    for row in rows:
        if not isinstance(row,dict):raise ValueError('match_object_required')
        name=row.get('name');score=row.get('score')
        if (not isinstance(name,str)or not name or name in result
                or not _number(score)or not 0<=score<=1):raise ValueError('invalid_or_duplicate_match')
        result[name]=row
    return result


def classify_phase_labels(frame):
    """Compare Prepare AND Start Battle; a close wrong label cannot win alone."""
    try:
        matches=_matches(frame)
        rows=sorted(((name,matches[name]['score'])for name in ('phase_ready','phase_start')),
                    key=lambda item:(-item[1],item[0]))
        (label,score),(_,other)=rows
        known=score>=.97 and score-other>=.02
        return {'status':'recognized'if known else'unknown','label':label if known else None,
                'score':score,'other_score':other,'margin':score-other,
                'confidence_calibrated':False,'execution_allowed':False}
    except (KeyError,TypeError,ValueError)as error:
        return {'status':'unknown','label':None,'reason':str(error),'execution_allowed':False}


def numeric_candidate(record):
    """Never turn the classifier's unknown/default Value=0 into a known zero."""
    if not isinstance(record,dict):return None
    text=record.get('Text');value=record.get('Value')
    if (record.get('Known')is not True or type(value)is not int or not 0<=value<100
            or not isinstance(text,str)or not 1<=len(text)<=2 or any(c not in '0123456789'for c in text)
            or int(text)!=value or type(record.get('Components'))is not int or record['Components']!=len(text)
            or not _number(record.get('Score'))or not .90<=record['Score']<=1
            or not _number(record.get('Margin'))or not .08<=record['Margin']<=1):return None
    return {'value':value,'text':text,'score':record['Score'],'margin':record['Margin'],
            'confidence_calibrated':False}


def assess_purchase_features(frame,hero_mapping,*,now,source_mode='saved_replay',
                             expected_balance=None,expected_price=None):
    """Combine phase competitors, shop visibility, numeric components and anchors.

    hero_mapping maps private template names to {slot: 0..3, hero_id: ...}.
    Optional expected values constrain a reviewed trial; no 6/3 game defaults.
    A live frame must retain its original time within five seconds. Replay is
    explicit and remains advisory. No custom-mode origin or hand receipt is
    invented by this image-only module.
    """
    result={'status':'unknown','candidate':None,'phase':classify_phase_labels(frame),'execution_allowed':False}
    try:
        matches=_matches(frame);digest=frame['sha256'];identity=frame['identity']['identity_version']
        if not isinstance(digest,str)or len(digest)!=64 or any(c not in '0123456789abcdef'for c in digest):raise ValueError('frame_hash_required')
        if not isinstance(identity,str)or not identity:raise ValueError('game_identity_required')
        if source_mode not in ('live_capture','saved_replay'):raise ValueError('explicit_source_mode_required')
        age=(_time(now)-_time(frame['captured_at'])).total_seconds()
        result['source']={'frame_sha256':digest,'captured_at':frame['captured_at'],'identity_version':identity,
                          'source_mode':source_mode,'age_seconds':age}
        if age<0 or(source_mode=='live_capture'and age>5):raise ValueError('frame_stale_or_future')
        if result['phase']['status']!='recognized':raise ValueError('phase_competitors_unknown')
        if not isinstance(hero_mapping,dict)or not 1<=len(hero_mapping)<=32:raise ValueError('bounded_private_hero_mapping_required')
        for name,entry in hero_mapping.items():
            if (not isinstance(entry,dict)or name not in matches or type(entry.get('slot'))is not int or not 0<=entry['slot']<4
                    or not isinstance(entry.get('hero_id'),str)or not entry['hero_id']):raise ValueError('invalid_or_missing_hero_template')
        for name,minimum in (('own_portrait',.985),('currency_icon',.97),('empty_slot',.97),('round_header',.97)):
            if matches[name]['score']<minimum:raise ValueError('anchor_unknown:'+name)
        energy=numeric_candidate(frame['numbers']['energy']);prices=frame['numbers']['prices']
        if energy is None:raise ValueError('currency_number_unknown')
        if not isinstance(prices,list)or len(prices)!=4:raise ValueError('four_price_regions_required')
        values=[numeric_candidate(record)for record in prices]
        visible=[i for i,value in enumerate(values)if value is not None and matches['price_'+str(i)]['score']>=.97]
        if len(visible)<2:raise ValueError('shop_not_independently_visible')
        for value in (expected_balance,expected_price):
            if value is not None and(type(value)is not int or value<0):raise ValueError('invalid_reviewed_trial_constraint')
        if expected_balance is not None and energy['value']!=expected_balance:raise ValueError('reviewed_balance_changed')
        for slot in range(4):
            names=[name for name,entry in hero_mapping.items()if entry['slot']==slot and matches[name]['score']>=.97]
            price=values[slot]
            if (slot not in visible or len(names)!=1 or price is None or energy['value']<price['value']
                    or(expected_price is not None and price['value']!=expected_price)):continue
            name=names[0]
            result.update(status='candidate',candidate={'slot':slot,'hero_id':hero_mapping[name]['hero_id'],
                'hero_template':name,'balance':energy['value'],'price':price['value'],
                'phase_label':result['phase']['label'],'numeric_confidence':min(energy['score'],price['score'])})
            return result
        raise ValueError('no_unambiguous_reviewed_offer')
    except (KeyError,TypeError,ValueError)as error:
        return result|{'reason':str(error)}


class ConsecutivePurchaseFrames:
    """Require two consecutive distinct frames; unknown evidence clears history."""
    def __init__(self):self._previous=None

    def observe(self,result):
        previous=self._previous;self._previous=None
        if result.get('status')!='candidate' or not result.get('candidate')or not result.get('source'):
            return {'status':'pending','reason':'current_features_unknown','execution_allowed':False}
        current={'candidate':dict(result['candidate']),'source':dict(result['source'])}
        self._previous=current
        def signature(row):
            candidate=row['candidate'];source=row['source']
            return tuple(candidate[key]for key in ('slot','hero_id','balance','price','phase_label'))+(source['identity_version'],source['source_mode'])
        stable=False
        if previous is not None:
            delta=(_time(current['source']['captured_at'])-_time(previous['source']['captured_at'])).total_seconds()
            stable=(signature(current)==signature(previous)and 0<delta<=5
                    and current['source']['frame_sha256']!=previous['source']['frame_sha256'])
        return {'status':'stable_candidate'if stable else'pending','candidate':current['candidate'],
                'source':current['source'],'execution_allowed':False}
