"""Small explicit UI-state boundary. Similarity scores are not calibrated confidence."""
def state_from_recognition(frame):
    matches=frame.get('matches',[])
    byname={r['name']:r for r in matches}
    required={'custom_tab','custom_tile','confirm'}
    matched=(len(matches)==len(required) and set(byname)==required and all(r['score']>=.91 for r in matches))
    return {'schema':'maawxq-ui-state/1','scene':'custom_selection' if matched else 'unknown',
            'source':{'kind':'screen_template_match','frame_sha256':frame['sha256'],
                      'recognizer':'custom-selection-glyphs/1'},
            'matches':matches,'room_occupancy':'unknown','room_number':None,
            'other_humans_verified_absent':False,'game_rules':'unknown'}

def decide(state):
    if state['scene']!='custom_selection':return {'action':'stop','reason':'unsupported_scene'}
    confirm=next(x for x in state['matches'] if x['name']=='confirm')
    return {'action':'click','operation':'confirm_custom_selection','context':'custom_setup',
            'reason':'recognized_custom_tab_tile_and_confirm_glyphs','target':confirm['center'],
            'expected_postcondition':'custom_selection_exited','source_frame':state['source']['frame_sha256']}

def verify(before,decision,after,submission):
    # Failing to recognize the old page is not positive evidence of leaving it.
    still_recognized=after['scene']=='custom_selection'
    return {'selection_screen_exited':False if still_recognized else None,
            'selection_screen_still_recognized':still_recognized,'next_scene':after['scene'],
            'room_verified':False,'match_started':False,
            'status':'selection_not_recognized_next_scene_unknown' if not still_recognized else 'postcondition_not_verified',
            'blind_retry_allowed':False}
