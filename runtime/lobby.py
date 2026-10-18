"""The reviewed empty custom-lobby frame supports opening AI settings only."""
import math

def recognize(frame):
    matches={x['name']:x for x in frame['matches']}
    if (len(matches)!=len(frame['matches']) or any(type(x.get('score')) not in (int,float)
            or not math.isfinite(x['score']) or not 0<=x['score']<=1 for x in matches.values())):
        return {'schema':'maawxq-ui-state/1','scene':'unknown','frame_sha256':frame['sha256'],
                'reason':'invalid_recognition_regions','other_humans_verified_absent':False,
                'room_verified':False,'match_started':False,'requested_player_verified':False,
                'recognizer':'invalid-regions/1','matches':frame['matches']}
    choices={'yixing_character_choice':{'selection_title','yixing_name','picker_context','yixing_target'},
             'yixing_character_confirm':{'selection_title','selected_yixing','selected_marker','confirm_label'}}
    if frame.get('layout') in choices:
        layout=frame['layout'];valid=set(matches)==choices[layout] and all(x['score']>=.95 for x in matches.values())
        return {'schema':'maawxq-ui-state/1','scene':layout if valid else 'unknown',
                'other_humans_verified_absent':False,'room_verified':False,'match_started':False,
                'requested_player_verified':False,'frame_sha256':frame['sha256'],
                'recognizer':layout+'-glyphs/1','matches':frame['matches']}
    back_layouts={
        'encyclopedia_back':{'back','encyclopedia_title','tournament_tab','chess_cards_tab'},
        'yixing_details_back':{'back','collection_title','yixing_title','classic_skin','equipped'},
        'chess_collection_back':{'back','collection_title','players_tab','strength_tab','yixing_name'},
    }
    if frame.get('layout') in back_layouts:
        layout=frame['layout'];required=back_layouts[layout]
        valid=set(matches)==required and all(x['score']>=.95 for x in matches.values())
        return {'schema':'maawxq-ui-state/1','scene':layout if valid else 'unknown',
                'other_humans_verified_absent':False,'room_verified':False,'match_started':False,
                'requested_player_verified':False,'frame_sha256':frame['sha256'],
                'recognizer':layout+'-glyphs/1','matches':frame['matches']}
    if frame.get('layout')=='yixing_secret_reward':
        required={'encyclopedia_title','tournament_tab','chess_cards_tab','yixing_row','mission_name','mission_rounds','reward_label'}
        valid=set(matches)==required and all(x['score']>=.95 for x in matches.values())
        return {'schema':'maawxq-ui-state/1','scene':'yixing_secret_reward' if valid else 'unknown',
                'other_humans_verified_absent':False,'room_verified':False,'match_started':False,
                'requested_player_verified':False,'frame_sha256':frame['sha256'],
                'recognizer':'yixing-secret-reward-glyphs/1','matches':frame['matches']}
    if frame.get('layout')=='yixing_rules_secret':
        required={'encyclopedia_title','tournament_tab','chess_cards_tab','yixing_row','passive_label','secret_icon'}
        valid=set(matches)==required and all(x['score']>=.95 for x in matches.values())
        return {'schema':'maawxq-ui-state/1','scene':'yixing_rules_secret' if valid else 'unknown',
                'other_humans_verified_absent':False,'room_verified':False,'match_started':False,
                'requested_player_verified':False,'frame_sha256':frame['sha256'],
                'recognizer':'yixing-rules-secret-glyphs/1','matches':frame['matches']}
    if frame.get('layout')=='yixing_ability_tooltip':
        required={'yixing_title','copy_heroes','passive_name','secret_label','view_details'}
        valid=set(matches)==required and all(x['score']>=.95 for x in matches.values())
        return {'schema':'maawxq-ui-state/1','scene':'yixing_ability_tooltip' if valid else 'unknown',
                'other_humans_verified_absent':False,'room_verified':False,'match_started':False,
                'requested_player_verified':False,'frame_sha256':frame['sha256'],
                'recognizer':'yixing-ability-tooltip-glyphs/1','matches':frame['matches']}
    if frame.get('layout')=='yixing_skill_tab':
        required={'yixing_title','copy_heroes','skill_icon','secret_label','exclusive_label'}
        valid=set(matches)==required and all(x['score']>=.95 for x in matches.values())
        return {'schema':'maawxq-ui-state/1','scene':'yixing_skill_tab' if valid else 'unknown',
                'other_humans_verified_absent':False,'room_verified':False,'match_started':False,
                'frame_sha256':frame['sha256'],'recognizer':'yixing-skill-tab-glyphs/1','matches':frame['matches']}
    if frame.get('layout')=='yixing_details':
        required={'yixing_title','classic_skin','equipped','skills_tab'}
        valid=set(matches)==required and all(x['score']>=.95 for x in matches.values())
        return {'schema':'maawxq-ui-state/1','scene':'yixing_details' if valid else 'unknown',
                'other_humans_verified_absent':False,'room_verified':False,'match_started':False,'yixing_owned':valid,
                'frame_sha256':frame['sha256'],'recognizer':'yixing-details-glyphs/1','matches':frame['matches']}
    if frame.get('layout')=='chess_collection':
        required={'collection_title','players_tab','strength_tab','yixing_name','yixing_portrait'}
        valid=set(matches)==required and all(x['score']>=.95 for x in matches.values())
        return {'schema':'maawxq-ui-state/1','scene':'chess_collection' if valid else 'unknown',
                'other_humans_verified_absent':False,'room_verified':False,'match_started':False,
                'frame_sha256':frame['sha256'],'recognizer':'chess-collection-glyphs/1','matches':frame['matches']}
    if frame.get('layout') in ('main_hub','main_hub_modes'):
        required={'chess_players','cards','formation','start'}
        valid=set(matches)==required and all(x['score']>=.95 for x in matches.values())
        return {'schema':'maawxq-ui-state/1','scene':frame['layout'] if valid else 'unknown',
                'other_humans_verified_absent':False,'room_verified':False,'match_started':False,
                'frame_sha256':frame['sha256'],'recognizer':'main-hub-glyphs/1','matches':frame['matches']}
    if frame.get('layout')=='custom_results':
        required={'custom_result_title','composition_tab','return_lobby'}
        valid=set(matches)==required and all(x['score']>=.95 for x in matches.values())
        return {'schema':'maawxq-ui-state/1','scene':'custom_results' if valid else 'unknown',
                'other_humans_verified_absent':False,'room_verified':False,'match_started':False,'match_ended':valid,
                'frame_sha256':frame['sha256'],'recognizer':'custom-results-glyphs/1','matches':frame['matches']}
    if frame.get('layout')=='ended_battle':
        required={'ranking_label','rank_six','exit_now','spectate'}
        valid=set(matches)==required and all(x['score']>=.95 for x in matches.values())
        return {'schema':'maawxq-ui-state/1','scene':'ended_battle' if valid else 'unknown',
                'other_humans_verified_absent':False,'room_verified':False,'match_started':False,'match_ended':valid,
                'frame_sha256':frame['sha256'],'recognizer':'ended-battle-glyphs/1','matches':frame['matches']}
    if frame.get('layout')=='exit_confirmation':
        required={'prompt_title','exit_explanation','continue_waiting','confirm_exit'}
        valid=set(matches)==required and all(x['score']>=.95 for x in matches.values())
        return {'schema':'maawxq-ui-state/1','scene':'exit_confirmation' if valid else 'unknown',
                'other_humans_verified_absent':False,'room_verified':False,'match_started':valid,
                'frame_sha256':frame['sha256'],'recognizer':'custom-exit-confirmation-glyphs/1','matches':frame['matches']}
    if frame.get('layout')=='battle_settings':
        required={'graphics_tab','device_load_label','exit_battle'}
        valid=set(matches)==required and all(x['score']>=.95 for x in matches.values())
        return {'schema':'maawxq-ui-state/1','scene':'battle_settings' if valid else 'unknown',
                'other_humans_verified_absent':False,'room_verified':False,'match_started':valid,
                'frame_sha256':frame['sha256'],'recognizer':'battle-settings-glyphs/1','matches':frame['matches']}
    if frame.get('layout')=='battle_controls':
        required={'battle_settings','own_portrait','statistics'}
        valid=set(matches)==required and all(x['score']>=.95 for x in matches.values())
        return {'schema':'maawxq-ui-state/1','scene':'battle_controls' if valid else 'unknown',
                'other_humans_verified_absent':False,'room_verified':False,'match_started':valid,
                'requested_player_verified':False,'frame_sha256':frame['sha256'],'recognizer':'battle-controls-glyphs/1','matches':frame['matches']}
    if frame.get('layout')=='encyclopedia':
        required={'encyclopedia_title','novice_tab','official_label','encyclopedia_close'}
        valid=set(matches)==required and all(x['score']>=.95 for x in matches.values())
        return {'schema':'maawxq-ui-state/1','scene':'encyclopedia_overlay' if valid else 'unknown',
                'other_humans_verified_absent':False,'room_verified':False,'match_started':False,
                'frame_sha256':frame['sha256'],'recognizer':'encyclopedia-overlay-glyphs/1','matches':frame['matches']}
    if frame.get('layout') in ('custom_lobby_ready','custom_lobby_start'):
        required={'lobby_title','room_settings','start_game'}|{'bot_'+kind+'_'+str(i)for kind in ('avatar','label')for i in range(1,6)}
        valid=set(matches)==required and all(x['score']>=(.985 if name.startswith('bot_avatar') else .95)for name,x in matches.items())
        return {'schema':'maawxq-ui-state/1','scene':'full_bot_custom_lobby' if valid else 'unknown',
                'other_humans_verified_absent':valid,'room_verified':valid,'match_started':False,
                'bot_count':5 if valid else None,'start_requested':frame['layout']=='custom_lobby_start',
                'frame_sha256':frame['sha256'],'recognizer':'full-bot-lobby-glyphs/1','matches':frame['matches']}
    if frame.get('layout') in ('room_options','room_options_close'):
        names={'newbie','bronze','silver','gold','platinum','diamond','xingyao','wangzhe'}
        required={'room_options_title','difficulty_label','room_options_close'}|{'difficulty_'+name for name in names}
        choices=frame.get('settings_choices',[])
        selected=[x['name'] for x in choices if x['selected']]
        valid=(set(matches)==required and all(x['score']>=.92 for x in matches.values())
               and len(choices)==8 and {x['name'] for x in choices}==names and len(selected)==1)
        return {'schema':'maawxq-ui-state/1','scene':'room_options' if valid else 'unknown',
                'other_humans_verified_absent':False,'room_verified':valid,'match_started':False,
                'selected_bot_difficulty':selected[0] if valid else None,'settings_choices':choices,
                'close_requested':frame['layout']=='room_options_close',
                'frame_sha256':frame['sha256'],'recognizer':'room-options-glyphs/1','matches':frame['matches']}
    if frame.get('layout')=='custom_lobby_onebot':
        required={'lobby_title','room_settings','bot_label_1','bot_avatar_1'}|{'empty_'+str(i) for i in range(2,6)}
        valid=set(matches)==required and all(x['score']>=(.985 if name.startswith(('empty_','bot_avatar')) else .95) for name,x in matches.items())
        return {'schema':'maawxq-ui-state/1','scene':'custom_lobby_with_bots' if valid else 'unknown',
                'other_humans_verified_absent':valid,'room_verified':valid,'match_started':False,
                'bot_slots':[1] if valid else None,'empty_other_slots':4 if valid else None,'bot_difficulty':'unknown',
                'frame_sha256':frame['sha256'],'recognizer':'custom-lobby-bots-glyphs/1','matches':frame['matches']}
    if frame.get('layout')=='guidance_settings':
        required={'settings_back','settings_title','ai_master','lingbao_selected'}
        valid=set(matches)==required and all(x['score']>=.95 for x in matches.values())
        return {'schema':'maawxq-ui-state/1','scene':'guidance_settings' if valid else 'unknown',
                'other_humans_verified_absent':False,'room_verified':False,'match_started':False,
                'frame_sha256':frame['sha256'],'recognizer':'guidance-settings-glyphs/1','matches':frame['matches']}
    required={'lobby_title','ai_settings','start_game'}|{'empty_'+str(i) for i in range(1,6)}
    room_options=frame.get('layout')=='empty_lobby_options'
    if room_options:required.add('room_settings')
    slot_menu=frame.get('layout')=='custom_lobby_slot'
    bot_menu=frame.get('layout')=='custom_lobby_bot_menu'
    if slot_menu:required.add('empty_slot_menu')
    if bot_menu:required.add('empty_slot_robot')
    valid=(set(matches)==required and all(x['score']>=(.985 if name.startswith('empty_') else .95)
                                        for name,x in matches.items()))
    return {'schema':'maawxq-ui-state/1','scene':'empty_custom_lobby' if valid else 'unknown',
            'other_humans_verified_absent':valid,'empty_other_slots':5 if valid else None,
            'room_verified':valid,'match_started':False,'frame_sha256':frame['sha256'],
            'recognizer':'empty-custom-lobby-glyphs/1','matches':frame['matches'],'slot_menu_supported':slot_menu,'bot_menu_supported':bot_menu,'room_options_requested':room_options}

def decide(state,selection_observer_sha256=None):
    if state['scene'] in ('yixing_character_choice','yixing_character_confirm'):
        confirm=state['scene']=='yixing_character_confirm'
        target=next(x for x in state['matches'] if x['name']==('confirm_label' if confirm else 'yixing_target'))['center']
        return {'action':'click','operation':'confirm_yixing_selection' if confirm else 'select_owned_yixing',
                'target':target,'source_frame':state['frame_sha256']}
    if state['scene']=='main_hub_modes':
        target=next(x for x in state['matches'] if x['name']=='start')['center']
        return {'action':'click','operation':'open_game_mode_selection','target':target,'source_frame':state['frame_sha256']}
    if state['scene'] in ('encyclopedia_back','yixing_details_back','chess_collection_back'):
        target=next(x for x in state['matches'] if x['name']=='back')['center']
        return {'action':'click','operation':'return_from_'+state['scene'][:-5],'target':target,'source_frame':state['frame_sha256']}
    if state['scene']=='yixing_secret_reward':
        target=next(x for x in state['matches'] if x['name']=='reward_label')['center']
        return {'action':'click','operation':'inspect_yixing_reward_rules','target':target,'source_frame':state['frame_sha256']}
    if state['scene']=='yixing_rules_secret':
        target=next(x for x in state['matches'] if x['name']=='secret_icon')['center']
        return {'action':'click','operation':'inspect_yixing_secret_rules','target':target,'source_frame':state['frame_sha256']}
    if state['scene']=='yixing_ability_tooltip':
        target=next(x for x in state['matches'] if x['name']=='view_details')['center']
        return {'action':'click','operation':'view_yixing_passive_details','target':target,'source_frame':state['frame_sha256']}
    if state['scene']=='yixing_skill_tab':
        target=next(x for x in state['matches'] if x['name']=='skill_icon')['center']
        return {'action':'click','operation':'inspect_yixing_ability_text','target':target,'source_frame':state['frame_sha256']}
    if state['scene']=='yixing_details':
        target=next(x for x in state['matches'] if x['name']=='skills_tab')['center']
        return {'action':'click','operation':'inspect_owned_yixing_skills','target':target,'source_frame':state['frame_sha256']}
    if state['scene']=='chess_collection':
        target=next(x for x in state['matches'] if x['name']=='yixing_name')['center']
        return {'action':'click','operation':'open_yixing_details','target':target,'source_frame':state['frame_sha256']}
    if state['scene']=='main_hub':
        target=next(x for x in state['matches'] if x['name']=='chess_players')['center']
        return {'action':'click','operation':'open_chess_player_collection','target':target,'source_frame':state['frame_sha256']}
    if state['scene']=='custom_results':
        target=next(x for x in state['matches'] if x['name']=='return_lobby')['center']
        return {'action':'click','operation':'return_to_lobby_from_results','target':target,'source_frame':state['frame_sha256']}
    if state['scene']=='ended_battle':
        target=next(x for x in state['matches'] if x['name']=='exit_now')['center']
        return {'action':'click','operation':'leave_ended_custom_battle','target':target,'source_frame':state['frame_sha256']}
    if state['scene']=='exit_confirmation':
        target=next(x for x in state['matches'] if x['name']=='confirm_exit')['center']
        return {'action':'click','operation':'confirm_exit_custom_battle','target':target,'source_frame':state['frame_sha256']}
    if state['scene']=='battle_settings':
        target=next(x for x in state['matches'] if x['name']=='exit_battle')['center']
        return {'action':'click','operation':'request_exit_custom_battle','target':target,'source_frame':state['frame_sha256']}
    if state['scene']=='battle_controls':
        target=next(x for x in state['matches'] if x['name']=='battle_settings')['center']
        return {'action':'click','operation':'open_battle_settings','target':target,'source_frame':state['frame_sha256']}
    if state['scene']=='encyclopedia_overlay':
        target=next(x for x in state['matches'] if x['name']=='encyclopedia_close')['center']
        return {'action':'click','operation':'close_encyclopedia','target':target,'source_frame':state['frame_sha256']}
    if state['scene']=='full_bot_custom_lobby' and state['other_humans_verified_absent'] is True and state['bot_count']==5:
        # Enter selection only while a fresh bounded observer is watching it.
        # Collection ownership or a caller-supplied boolean is not sufficient.
        if state['start_requested'] and not selection_observer_sha256:
            return {'action':'stop','reason':'yixing_selection_confirmation_not_implemented'}
        start=state['start_requested'];control='start_game' if start else 'room_settings'
        target=next(x for x in state['matches'] if x['name']==control)['center']
        return {'action':'click','operation':'begin_custom_selection' if start else 'open_room_settings','target':target,'source_frame':state['frame_sha256']}
    if state['scene']=='room_options':
        if state.get('close_requested') and state['selected_bot_difficulty']=='xingyao':
            target=next(x for x in state['matches'] if x['name']=='room_options_close')['center']
            return {'action':'click','operation':'close_verified_room_options','target':target,'source_frame':state['frame_sha256']}
        if state['selected_bot_difficulty']=='xingyao':return {'action':'stop','reason':'xingyao_already_selected'}
        target=next(x for x in state['settings_choices'] if x['name']=='xingyao')['center']
        return {'action':'click','operation':'select_xingyao_bot_difficulty','target':target,'source_frame':state['frame_sha256']}
    if state['scene']=='custom_lobby_with_bots' and state['other_humans_verified_absent'] is True:
        target=next(x for x in state['matches'] if x['name']=='room_settings')['center']
        return {'action':'click','operation':'open_room_settings','target':target,'source_frame':state['frame_sha256']}
    if state['scene']=='guidance_settings':
        target=next(x for x in state['matches'] if x['name']=='settings_back')['center']
        return {'action':'click','operation':'return_from_guidance_settings','target':target,'source_frame':state['frame_sha256']}
    if state['scene']!='empty_custom_lobby' or state['other_humans_verified_absent'] is not True:
        return {'action':'stop','reason':'empty_custom_lobby_not_verified'}
    slot=state.get('slot_menu_supported') is True
    if state.get('room_options_requested') is True:
        control=next(x for x in state['matches'] if x['name']=='room_settings')
        return {'action':'click','operation':'open_room_settings','target':control['center'],'source_frame':state['frame_sha256']}
    if state.get('bot_menu_supported') is True:
        control=next(x for x in state['matches'] if x['name']=='empty_slot_robot')
        return {'action':'click','operation':'open_bot_selection','target':control['center'],'source_frame':state['frame_sha256']}
    control=next(x for x in state['matches'] if x['name']==('empty_slot_menu' if slot else 'ai_settings'))
    return {'action':'click','operation':'open_empty_slot_menu' if slot else 'open_ai_settings','target':control['center'],'source_frame':state['frame_sha256']}
