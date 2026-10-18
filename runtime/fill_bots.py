"""Bounded software-only bot fill. Unknown slots and interrupted postconditions stop."""
import argparse,hashlib,json,sys,time,traceback
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from runtime.custom_setup import capture,dump,now,ensure_capture_capacity
from runtime.cleanup import close_verified
from runtime.game_profile import inspect_game,process_security
from runtime.bot_fill import recognize,decide,verify_step
from window_identity import find_windows
from backends.game_click import GameClickBroker,GameClickEvidence,Binding

def run(output,profile_path,reference,reference_hash,menu_reference,menu_hash,enabled,allow_admin):
    output.mkdir(exist_ok=False)
    r={'started_at':now(),'operator':'MaaWXQ.runtime.fill_bots','remote_role':'launch_only','actions':[],
       'match_started':False,'five_bots_verified':False}
    broker=None;previous_port=None;last_marker=None
    try:
        security=process_security();r['runtime_security']=security
        if not security['known'] or security['app_container'] or security['ui_access'] or (security['elevated'] and not allow_admin):raise RuntimeError('runtime_not_authorized')
        for path,digest in ((reference,reference_hash),(menu_reference,menu_hash)):
            if hashlib.sha256(path.read_bytes()).hexdigest()!=digest:raise RuntimeError('reference_changed')
        r['references']=[{'path':str(path),'sha256':digest} for path,digest in ((reference,reference_hash),(menu_reference,menu_hash))]
        profile=json.loads(profile_path.read_text(encoding='utf-8'))
        rows=[x for x in find_windows(profile['title']) if x['title']==profile['title'] and x['class_name']==profile['class_name']]
        if len(rows)!=1:raise RuntimeError('one_configured_game_required')
        row=inspect_game(rows[0]['hwnd'],rows[0]['pid']);r['game_profile']=row
        if any(row[k]!=profile[k] for k in ('title','class_name','executable_path')):raise RuntimeError('game_profile_changed')
        if security['integrity_rid']<row['process_security']['integrity_rid']:raise RuntimeError('target_integrity_above_controller')
        r['source_hashes']={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in
            (ROOT/'runtime/fill_bots.py',ROOT/'runtime/bot_fill.py',ROOT/'runtime/custom_setup.py',ROOT/'runtime/screen_frame.ps1',ROOT/'backends/game_click.py',ROOT/'backends/win32_single_click.py')}
        for step in range(10):
            r['capture_budget']=ensure_capture_capacity(output.parent,frames=2 if enabled else 1)
            if previous_port is not None and previous_port.activity_marker()!=last_marker:raise RuntimeError('user_input_between_steps')
            frame=capture(row,output/('before-'+str(step)+'.png'),reference,'custom_lobby_fill',menu_reference)
            dump(output/('capture-before-'+str(step)+'.json'),frame)
            if previous_port is not None and previous_port.activity_marker()!=last_marker:raise RuntimeError('user_input_during_capture')
            state=recognize(frame);decision=decide(state);r['last_state']=state
            dump(output/('state-'+str(step)+'.json'),state);dump(output/('decision-'+str(step)+'.json'),decision)
            if decision['action']=='stop':
                r['status']=decision['reason'];r['five_bots_verified']=decision['reason']=='five_bots_verified';return r
            if not enabled:r['status']='observe_only';return r
            ev=GameClickEvidence(Binding.from_observation(frame['identity']),frame['observed_monotonic'],*decision['target'],
                context='custom_setup',operation=decision['operation'],no_other_humans_verified=True,
                scene=state['scene'],frame_sha256=frame['sha256'],recognizer='custom-lobby-fill-glyphs/1',executable_path=row['executable_path'])
            broker=GameClickBroker(ev,observer=inspect_game,enabled=True,max_age=5,max_seconds=2);broker.arm()
            if previous_port is not None and previous_port.activity_marker()!=last_marker:raise RuntimeError('user_input_before_next_click')
            action=broker.click_once();action.update(decision=decision,source_frame=frame['sha256']);r['actions'].append(action)
            dump(output/('action-'+str(step)+'.json'),action)
            if broker.stop_reason!='one_action_completed' or broker.port.held:raise RuntimeError('bot_click_interrupted')
            summary,activity_marker=close_verified(broker)
            action.update(summary)
            time.sleep(.35)
            if broker.port.activity_marker()!=activity_marker:raise RuntimeError('user_input_before_postcondition_capture')
            after=capture(row,output/('after-'+str(step)+'.png'),reference,'custom_lobby_fill',menu_reference)
            dump(output/('capture-after-'+str(step)+'.json'),after)
            next_state=recognize(after);dump(output/('state-after-'+str(step)+'.json'),next_state);r['last_state']=next_state
            if broker.foreign_interrupt.is_set() or broker.port.activity_marker()!=activity_marker:raise RuntimeError('foreign_input_during_postcondition_capture')
            previous_port=broker.port;last_marker=previous_port.activity_marker();broker.close()
            action.update(held=broker.port.held,down_count=broker.port.submitted_event_count,
                owned_up_count=broker.port.owned_release_last_raw_return,cleanup_errors=list(broker.cleanup_errors)+list(broker.port.cleanup_errors),
                postcondition_verified=verify_step(state,decision,next_state))
            dump(output/('action-'+str(step)+'.json'),action)
            if action['held'] or action['cleanup_errors']:raise RuntimeError('bot_click_cleanup_not_confirmed')
            if not action['postcondition_verified']:raise RuntimeError('bot_step_postcondition_not_verified')
        r['status']='bounded_fill_budget_exhausted'
    except BaseException as error:r.update(status='stopped',error=str(error),traceback=traceback.format_exc())
    finally:
        if broker is not None:
            broker.close();r['cleanup_errors']=list(broker.cleanup_errors)+list(broker.port.cleanup_errors if broker.port else [])
            if r['cleanup_errors'] or not broker.release_confirmed or (broker.port and broker.port.held):
                r.update(status='stopped',error='native_cleanup_not_confirmed')
        r['completed_at']=now();dump(output/'receipt.json',r)
    return r

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('output','profile','reference','menu-reference'):p.add_argument('--'+name,type=Path,required=True)
    for name in ('reference-sha256','menu-sha256'):p.add_argument('--'+name,required=True)
    p.add_argument('--enable-custom-setup',action='store_true');p.add_argument('--allow-elevated-runtime',action='store_true')
    a=p.parse_args();print(json.dumps(run(a.output,a.profile,a.reference,a.reference_sha256,a.menu_reference,a.menu_sha256,a.enable_custom_setup,a.allow_elevated_runtime),ensure_ascii=False))
