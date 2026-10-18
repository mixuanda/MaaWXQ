"""One software-owned transition from a freshly recognized empty lobby to AI settings."""
import argparse,hashlib,json,sys,time,traceback
from datetime import datetime,timezone
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from runtime.custom_setup import capture,dump,now,ensure_capture_capacity
from runtime.cleanup import close_verified
from runtime.game_profile import inspect_game,process_security
from runtime.lobby import recognize,decide
from window_identity import find_windows
from backends.game_click import GameClickBroker,GameClickEvidence,Binding

def run(output,reference,reference_hash,profile_path,enabled,allow_admin,layout='custom_lobby',selection_observer=None,selection_origin=None):
    output.mkdir(exist_ok=False)
    result={'started_at':now(),'operator':'MaaWXQ.runtime.lobby_setup','remote_role':'launch_only',
            'input_attempted':False,'match_started':False,'configuration_verified':False}
    broker=None
    try:
        security=process_security();result['runtime_security']=security
        if not security['known'] or security['app_container'] or security['ui_access'] or (security['elevated'] and not allow_admin):raise RuntimeError('runtime_not_authorized')
        if hashlib.sha256(reference.read_bytes()).hexdigest()!=reference_hash:raise RuntimeError('reference_changed')
        profile=json.loads(profile_path.read_text(encoding='utf-8'))
        rows=[x for x in find_windows(profile['title']) if x['title']==profile['title'] and x['class_name']==profile['class_name']]
        if len(rows)!=1:raise RuntimeError('one_configured_game_required')
        row=inspect_game(rows[0]['hwnd'],rows[0]['pid']);result['game_profile']=row
        if any(row[k]!=profile[k] for k in ('title','class_name','executable_path')):raise RuntimeError('configured_game_changed')
        if security['integrity_rid']<row['process_security']['integrity_rid']:raise RuntimeError('target_integrity_above_controller')
        result['reference']={'path':str(reference),'sha256':reference_hash}
        result['source_hashes']={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in
            (ROOT/'runtime/lobby_setup.py',ROOT/'runtime/lobby.py',ROOT/'runtime/screen_frame.ps1',ROOT/'backends/game_click.py',ROOT/'backends/win32_single_click.py')}
        result['capture_budget']=ensure_capture_capacity(output.parent,frames=3 if enabled else 1)
        frame=capture(row,output/'before.png',reference,layout);dump(output/'capture-before.json',frame)
        state=recognize(frame);dump(output/'state-before.json',state)
        if not enabled:result['status']='observe_only';return result
        frame=capture(row,output/'preaction.png',reference,layout);dump(output/'capture-preaction.json',frame)
        observer_sha=''
        if layout=='custom_lobby_start' and selection_observer is not None:
            if (selection_observer.parent/'observer-done.json').exists():raise RuntimeError('selection_observer_finished')
            raw=selection_observer.read_bytes();observation=json.loads(raw)
            age=(datetime.now(timezone.utc)-datetime.fromisoformat(observation['captured_at'].replace('Z','+00:00'))).total_seconds()
            if (observation['schema']!='selection-transition-observer/1' or observation['input_calls']!=0
                    or not 0<=age<=5 or observation['deadline_monotonic']-time.monotonic()<20
                    or observation['frame']['identity']['identity_version']!=row['identity_version']):
                raise RuntimeError('fresh_bounded_selection_observer_required')
            observer_sha=hashlib.sha256(raw).hexdigest();result['selection_observer']=observation
            result['selection_confirmed']=False
        state=recognize(frame);decision=decide(state,observer_sha);dump(output/'state-preaction.json',state);dump(output/'decision.json',decision)
        result.update(state=state,decision=decision)
        if decision['action']!='click':raise RuntimeError(decision.get('reason','recognized_setup_transition_required'))
        origin_sha=''
        if layout in ('yixing_character_choice','yixing_character_confirm'):
            if selection_origin is None:raise RuntimeError('custom_selection_origin_required')
            raw=selection_origin.read_bytes();origin=json.loads(raw)
            age=(datetime.now(timezone.utc)-datetime.fromisoformat(origin['completed_at'])).total_seconds()
            if (not 0<=age<=120 or origin['decision']['operation']!='begin_custom_selection'
                    or origin['state'].get('bot_count')!=5 or origin['state'].get('other_humans_verified_absent')is not True
                    or origin['native_summary']['held'] or origin['native_summary']['cleanup_errors']
                    or origin['native_summary']['owned_up_count']!=1
                    or origin['game_profile']['identity_version']!=row['identity_version']):
                raise RuntimeError('verified_recent_empty_custom_origin_required')
            origin_sha=hashlib.sha256(raw).hexdigest();result['selection_origin_sha256']=origin_sha
            state['other_humans_verified_absent']=True
        ev=GameClickEvidence(Binding.from_observation(frame['identity']),frame['observed_monotonic'],*decision['target'],
            context='custom_setup',operation=decision['operation'],no_other_humans_verified=state['other_humans_verified_absent'],
            scene=state['scene'],frame_sha256=frame['sha256'],recognizer=state['recognizer'],executable_path=row['executable_path'],selection_observer_sha256=observer_sha,custom_selection_origin_sha256=origin_sha)
        broker=GameClickBroker(ev,observer=inspect_game,enabled=True,max_age=5,max_seconds=2)
        broker.arm();result['input_attempted']=True;action=broker.click_once();result['action']=action
        if broker.stop_reason!='one_action_completed' or broker.port.held:raise RuntimeError('lobby_click_interrupted')
        result['native_summary'],activity_marker=close_verified(broker)
        time.sleep(.35)
        if broker.port.activity_marker()!=activity_marker:raise RuntimeError('user_input_before_postcondition_capture')
        after=capture(row,output/'after.png',reference,layout);dump(output/'capture-after.json',after)
        state_after=recognize(after);dump(output/'state-after.json',state_after)
        if broker.foreign_interrupt.is_set() or broker.port.activity_marker()!=activity_marker:raise RuntimeError('foreign_input_during_postcondition_capture')
        result.update(state_after=state_after,status='setup_page_changed_requires_recognition' if state_after['scene']=='unknown' else 'setup_page_unchanged_no_retry')
        if decision['operation']=='select_xingyao_bot_difficulty' and state_after.get('selected_bot_difficulty')=='xingyao':
            result.update(status='bot_difficulty_xingyao_verified',configuration_verified=True)
    except BaseException as error:result.update(status='stopped',error=str(error),traceback=traceback.format_exc())
    finally:
        if broker is not None:
            broker.close()
            errors=list(broker.cleanup_errors)+list(broker.port.cleanup_errors if broker.port else [])
            if errors or not broker.release_confirmed or (broker.port and broker.port.held):result.update(status='stopped',error='native_cleanup_not_confirmed')
            result['native_summary']={'down_count':broker.port.submitted_event_count if broker.port else None,
                'owned_up_count':broker.port.owned_release_last_raw_return if broker.port else None,
                'held':broker.port.held if broker.port else False,'cleanup_errors':errors,
                'last_input_marker':broker.port.activity_marker() if broker.port else None,
                'stop_reason':broker.stop_reason}
        result['completed_at']=now();dump(output/'receipt.json',result)
    return result

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output',required=True,type=Path);p.add_argument('--profile',required=True,type=Path)
    p.add_argument('--reference',required=True,type=Path);p.add_argument('--reference-sha256',required=True)
    p.add_argument('--enable-custom-setup',action='store_true');p.add_argument('--allow-elevated-runtime',action='store_true')
    p.add_argument('--selection-observer',type=Path)
    p.add_argument('--selection-origin',type=Path)
    p.add_argument('--layout',choices=['custom_lobby','custom_lobby_slot','custom_lobby_bot_menu','custom_lobby_onebot','custom_lobby_ready','custom_lobby_start','guidance_settings','room_options','room_options_close','encyclopedia','battle_controls','battle_settings','exit_confirmation','ended_battle','custom_results','main_hub','main_hub_modes','chess_collection','yixing_details','yixing_skill_tab','yixing_ability_tooltip','yixing_rules_secret','yixing_secret_reward','encyclopedia_back','yixing_details_back','chess_collection_back','empty_lobby_options','yixing_character_choice','yixing_character_confirm'],default='custom_lobby')
    a=p.parse_args();print(json.dumps(run(a.output,a.reference,a.reference_sha256,a.profile,a.enable_custom_setup,a.allow_elevated_runtime,a.layout,a.selection_observer,a.selection_origin),ensure_ascii=False))
