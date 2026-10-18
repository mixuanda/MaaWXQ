"""Recognize each known lobby slot and fill only independently verified empty slots."""
import math
def recognize(frame):
    matches={x['name']:x for x in frame['matches']}
    required={'lobby_title'}|{'slot_'+str(i)+'_'+kind for i in range(1,6) for kind in ('empty','bot_avatar','bot_label','operation','robot_menu')}
    if (set(matches)!=required or len(matches)!=len(frame['matches'])
            or any(type(x.get('score')) not in (int,float) or not math.isfinite(x['score'])
                   or not 0<=x['score']<=1 for x in matches.values())):
        return {'scene':'unknown','other_humans_verified_absent':False,'slots':[]}
    slots=[]
    for i in range(1,6):
        prefix='slot_'+str(i)+'_'
        empty=matches[prefix+'empty']['score']>=.985
        bot=matches[prefix+'bot_avatar']['score']>=.98 and matches[prefix+'bot_label']['score']>=.95
        slots.append({'slot':i,'kind':('empty' if empty else 'bot') if empty!=bot else 'unknown',
                      'menu_visible':matches[prefix+'robot_menu']['score']>=.95,
                      'operation':matches[prefix+'operation'],'robot_menu':matches[prefix+'robot_menu']})
    valid=matches['lobby_title']['score']>=.95 and all(x['kind']!='unknown' for x in slots)
    return {'schema':'maawxq-ui-state/1','scene':'custom_lobby_fill' if valid else 'unknown',
            'other_humans_verified_absent':valid,'slots':slots,'frame_sha256':frame['sha256'],
            'bot_count':sum(x['kind']=='bot' for x in slots),'match_started':False}

def decide(state):
    if state['scene']!='custom_lobby_fill' or not state['other_humans_verified_absent']:
        return {'action':'stop','reason':'all_slot_identities_required'}
    empty=[x for x in state['slots'] if x['kind']=='empty']
    if not empty:return {'action':'stop','reason':'five_bots_verified'}
    slot=empty[0];menus=[x for x in state['slots'] if x['menu_visible']]
    if menus:
        if len(menus)!=1 or menus[0]['slot']!=slot['slot']:return {'action':'stop','reason':'unexpected_slot_menu'}
        return {'action':'click','operation':'add_room_bot','slot':slot['slot'],'target':slot['robot_menu']['center']}
    if slot['operation']['score']<.92:return {'action':'stop','reason':'slot_operation_not_recognized'}
    return {'action':'click','operation':'open_empty_slot_menu','slot':slot['slot'],'target':slot['operation']['center']}

def verify_step(before,decision,after):
    if after['scene']!='custom_lobby_fill' or not after['other_humans_verified_absent']:return False
    index=decision['slot']-1
    if any(before['slots'][j]['kind']!=after['slots'][j]['kind'] for j in range(5) if j!=index):return False
    if decision['operation']=='open_empty_slot_menu':
        return after['slots'][index]['kind']=='empty' and after['slots'][index]['menu_visible']
    return before['slots'][index]['kind']=='empty' and after['slots'][index]['kind']=='bot' and after['bot_count']==before['bot_count']+1
