"""Partial, provenance-bound UI state; uncalibrated OCR is never an action permit."""
from datetime import datetime
import re

REGIONS={'round':(679,12,95,23),'energy':(1357,789,46,32),
         'shop_1_name':(338,188,103,29),'shop_2_name':(542,188,103,29),
         'shop_3_name':(747,188,103,29),'shop_4_name':(951,188,103,29)}

def unknown(reason='not_extracted'):
    return {'status':'unknown','value':None,'candidate':None,'reason':reason,'confidence':None}

def candidate(value,text,roi):
    return {'status':'candidate','value':None,'candidate':value,'raw_text':text,
            'confidence':None,'confidence_kind':'uncalibrated','requires_independent_validation':True,
            'roi_image_sha256':roi.get('image_sha256'),'roi_pixel_sha256':roi.get('pixel_sha256'),
            'source_rect':roi['source_rect']}

def extract(frame,state,roi_ocr,*,now):
    if state.get('frame_sha256')!=frame.get('sha256'):raise ValueError('state_frame_mismatch')
    captured=datetime.fromisoformat(frame['captured_at'].replace('Z','+00:00'))
    current=datetime.fromisoformat(now.replace('Z','+00:00'))
    age=(current-captured).total_seconds()
    if age<0:raise ValueError('future_capture')
    result={'schema':'maawxq-minimal-state/1','captured_at':frame['captured_at'],
            'processed_at':now,'age_seconds':age,'fresh_for_input':False,'input_allowed':False,
            'source':{'kind':'screen_recognition','image':frame['image'],'sha256':frame['sha256'],
                      'identity_version':frame['identity']['identity_version']},
            'scene':state['scene'],'game_build':unknown('not_visible'),'rules_version':unknown('not_visible'),
            'selection':{'requested':'yixing','confirmed':unknown('no_selection_confirmation_evidence')},
            'round':unknown(),'timer_seconds':unknown(),'phase':unknown('phase_not_independently_verified'),
            'resources':{'energy':unknown()},'shop':{'slots':[{'slot':i,'name':unknown(),'entity_id':unknown(),'cost':unknown()}for i in range(1,5)],'coverage':'partial'},
            'board':{'entities':None,'coverage':'unknown'},'hand':{'entities':None,'coverage':'unknown'},
            'execution':{'setup_actions_executed':False,'strategy_actions_executed':False}}
    if state.get('scene')!='battle_controls' or state.get('match_started')is not True:
        result['extraction_status']='non_battle';return result
    result['extraction_status']='partial_uncalibrated_ocr'
    for key,bundle in roi_ocr.items():
        roi,ocr=bundle['roi'],bundle['ocr']
        if key not in REGIONS or tuple(roi['source_rect'])!=REGIONS[key]:raise ValueError('unreviewed_ocr_region')
        if roi['source_sha256']!=frame['sha256']:
            raise ValueError('ocr_frame_or_crop_mismatch')
        if roi.get('kind')=='in_memory_bgra8':
            if not roi.get('pixel_sha256')or roi['pixel_sha256']!=ocr.get('pixel_sha256')or ocr.get('frame_sha256')!=frame['sha256']:
                raise ValueError('ocr_frame_or_crop_mismatch')
        elif roi.get('image_sha256')!=ocr.get('image_sha256'):
            raise ValueError('ocr_frame_or_crop_mismatch')
        if ocr.get('status')!='recognized':continue
        text=''.join(ocr.get('text','').split())
        if key=='round':
            match=re.fullmatch(r'第(\d{1,2})回合[|｜]?(\d{1,3})[sS秒]',text)
            if match:
                result['round']=candidate(int(match[1]),text,roi)
                result['timer_seconds']=candidate(int(match[2]),text,roi)
        elif key=='energy' and re.fullmatch(r'\d{1,3}',text):
            result['resources']['energy']=candidate(int(text),text,roi)
        elif re.fullmatch(r'shop_[1-4]_name',key) and re.fullmatch(r'[\u4e00-\u9fff]{1,6}',text):
            result['shop']['slots'][int(key[5])-1]['name']=candidate(text,text,roi)
        elif re.fullmatch(r'shop_[1-4]_cost',key) and re.fullmatch(r'\d{1,2}',text):
            result['shop']['slots'][int(key[5])-1]['cost']=candidate(int(text),text,roi)
    return result
