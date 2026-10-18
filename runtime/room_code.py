"""Software enters a generated four-digit code, verifying progress after each click."""
import argparse,hashlib,json,secrets,sys,time,traceback
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from runtime.custom_setup import capture,dump,now,ensure_capture_capacity
from runtime.game_profile import process_security,inspect_game,activate_once
from runtime.keypad import recognize,decide,progress_report
from window_identity import find_windows
from backends.game_click import GameClickBroker,GameClickEvidence,Binding

def run(output,reference,reference_hash,profile,enabled,allow_admin):
    output.mkdir(parents=True,exist_ok=False)
    r=dict(schema='maawxq-software-room-code/1',started_at=now(),operator='MaaWXQ.runtime.room_code',
           decision_origin='runtime.keypad.decide',remote_role='launch_only',actions=[],room_verified=False,match_started=False)
    broker=None
    try:
        security=process_security();r['runtime_security']=security
        if not security['known'] or security['app_container'] or security['ui_access'] or (security['elevated'] and not allow_admin):raise RuntimeError('runtime_not_authorized')
        if hashlib.sha256(reference.read_bytes()).hexdigest()!=reference_hash:raise RuntimeError('reference_hash_changed')
        r['reference']={'path':str(reference),'sha256':reference_hash}
        paths=[ROOT/'runtime/room_code.py',ROOT/'runtime/keypad.py',ROOT/'runtime/custom_setup.py',ROOT/'runtime/screen_frame.ps1',ROOT/'runtime/game_profile.py',ROOT/'backends/game_click.py',ROOT/'backends/win32_single_click.py']
        r['source_hashes']={str(x.relative_to(ROOT)):hashlib.sha256(x.read_bytes()).hexdigest() for x in paths}
        rows=[x for x in find_windows('王者万象棋') if x['title']=='王者万象棋' and x['class_name']=='UnityWndClass']
        if len(rows)!=1:raise RuntimeError('one_exact_game_window_required')
        row=inspect_game(rows[0]['hwnd'],rows[0]['pid']);r['game_profile']=row
        expected=json.loads(profile.read_text(encoding='utf-8'))
        if any(row[k]!=expected[k] for k in ['title','class_name','executable_path']):raise RuntimeError('configured_game_changed')
        if security['integrity_rid']<row['process_security']['integrity_rid']:raise RuntimeError('target_integrity_above_controller')
        r['capture_budget']=ensure_capture_capacity(output.parent,frames=8 if enabled else 1)
        r['activation']=activate_once(row)
        frame=capture(row,output/'before.png',reference,'room_keypad');dump(output/'capture-before.json',frame)
        state=recognize(frame);dump(output/'state-before.json',state)
        if not enabled:r['status']='observe_only';return r
        if state['scene']!='room_keypad' or state['entry_count']!=0:raise RuntimeError('empty_recognized_room_keypad_required')
        code=''.join(secrets.SystemRandom().sample('123456789',4));r['selected_room_code']=code
        previous_port=None;last_marker=None
        for index in range(4):
            if index:
                if previous_port.activity_marker()!=last_marker:raise RuntimeError('user_input_between_steps')
                frame=capture(row,output/('preaction-'+str(index)+'.png'),reference,'room_keypad')
                dump(output/('capture-preaction-'+str(index)+'.json'),frame)
                if previous_port.activity_marker()!=last_marker:raise RuntimeError('user_input_during_preaction_capture')
            state=recognize(frame);decision=decide(state,code,index)
            dump(output/('state-'+str(index)+'.json'),state);dump(output/('decision-'+str(index)+'.json'),decision)
            if decision['action']!='click':raise RuntimeError('keypad_progress_changed')
            ev=GameClickEvidence(Binding.from_observation(frame['identity']),frame['observed_monotonic'],*decision['target'],
                context='custom_setup',operation='room_code_digit',scene='room_keypad',digit=decision['digit'],
                frame_sha256=frame['sha256'],recognizer='room-keypad-glyphs/1',executable_path=row['executable_path'])
            broker=GameClickBroker(ev,observer=inspect_game,enabled=True,max_age=5.0,max_seconds=2.0)
            broker.arm()
            if previous_port is not None and previous_port.activity_marker()!=last_marker:raise RuntimeError('user_input_before_next_click')
            action=broker.click_once()
            action.update(digit=decision['digit'],target=decision['target'],source_frame=frame['sha256'],
                          stop_reason=broker.stop_reason,held=broker.port.held,
                          cleanup_errors=list(broker.cleanup_errors)+list(broker.port.cleanup_errors),
                          down_count=broker.port.submitted_event_count,owned_up_count=broker.port.owned_release_last_raw_return)
            r['actions'].append(action);dump(output/('action-'+str(index)+'.json'),action)
            if (broker.stop_reason!='one_action_completed' or action['held'] or action['cleanup_errors']
                    or not broker.release_confirmed):raise RuntimeError('click_interrupted_or_unclean')
            time.sleep(.35)
            after=capture(row,output/('after-'+str(index)+'.png'),reference,'room_keypad');dump(output/('capture-after-'+str(index)+'.json'),after)
            next_state=recognize(after);dump(output/('state-after-'+str(index)+'.json'),next_state);r['last_state']=next_state
            if broker.foreign_interrupt.is_set():raise RuntimeError('foreign_input_during_postcondition_capture')
            previous_port=broker.port;last_marker=previous_port.activity_marker()
            broker.close();action['cleanup_confirmed']=(broker.release_confirmed and not broker.cleanup_errors
                                                       and not broker.port.cleanup_errors and not broker.port.held)
            dump(output/('action-'+str(index)+'.json'),action)
            if not action['cleanup_confirmed']:raise RuntimeError('game_click_cleanup_unconfirmed')
            progress=progress_report(next_state,index+1);action['progress']=progress
            dump(output/('verification-'+str(index)+'.json'),progress)
            if not progress['progress_verified']:raise RuntimeError('digit_progress_not_verified')
        r['status']='four_digit_entry_count_verified_room_requires_recognition'
    except BaseException as e:r.update(status='stopped',error=str(e),traceback=traceback.format_exc())
    finally:
        if broker is not None:
            broker.close()
            r['cleanup_errors']=list(broker.cleanup_errors)+list(broker.port.cleanup_errors if broker.port else [])
            r['held']=broker.port.held if broker.port else False
        r['completed_at']=now();dump(output/'receipt.json',r)
    return r

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output',type=Path,required=True);p.add_argument('--reference',type=Path,required=True)
    p.add_argument('--reference-sha256',required=True);p.add_argument('--profile',type=Path,required=True)
    p.add_argument('--enable-custom-setup',action='store_true');p.add_argument('--allow-elevated-runtime',action='store_true')
    a=p.parse_args();print(json.dumps(run(a.output,a.reference,a.reference_sha256,a.profile,a.enable_custom_setup,a.allow_elevated_runtime),ensure_ascii=False))
if __name__=='__main__':main()
