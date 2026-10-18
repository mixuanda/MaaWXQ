"""Room-code keypad recognition and one-step software decision."""
def recognize(frame):
    matches={x['name']:x for x in frame['matches']}
    required={'room_title','custom_tab'}|{'digit_'+n for n in '0123456789'}
    recognized=(len(frame['matches'])==len(required) and set(matches)==required and all(x['score']>=.91 for x in matches.values()))
    slots=frame.get('room_slots',[])
    occupied=[x['occupied'] for x in slots]
    count=sum(occupied)
    ordered=len(slots)==4 and occupied==[True]*count+[False]*(4-count)
    return {'schema':'maawxq-ui-state/1','scene':'room_keypad' if recognized else 'unknown',
            'entry_count':count if ordered and recognized else None,'entry_values':'not_ocr_verified',
            'matches':frame['matches'],'room_slots':slots,'frame_sha256':frame['sha256'],
            'room_occupancy':'unknown','other_humans_verified_absent':False,'room_verified':False}

def decide(state,code,expected_count):
    if (len(code)!=4 or not code.isascii() or not code.isdigit() or state['scene']!='room_keypad'
            or state['entry_count']!=expected_count or not 0<=expected_count<4):
        return {'action':'stop','reason':'unsupported_scene_or_entry_progress'}
    digit=code[expected_count];match=next(x for x in state['matches'] if x['name']=='digit_'+digit)
    return {'action':'click','operation':'room_code_digit','digit':digit,'target':match['center'],
            'source_frame':state['frame_sha256'],'expected_entry_count':expected_count+1}

def verify_progress(state,expected_count):
    """Every digit, including the fourth, needs a recognized postcondition."""
    return (type(expected_count) is int and 1<=expected_count<=4
            and state['scene']=='room_keypad' and state['entry_count']==expected_count)

def progress_report(state,expected_count):
    return {'progress_verified':verify_progress(state,expected_count),'expected_entry_count':expected_count,
            'observed_entry_count':state['entry_count'],'scene':state['scene'],
            'source_frame':state['frame_sha256'],'entry_values_ocr_verified':False,
            'room_verified':False,'match_started':False,'blind_retry_allowed':False}
