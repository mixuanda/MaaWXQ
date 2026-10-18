"""Reproducible software loop. Remote launch is not part of decision or action."""
import argparse,hashlib,json,os,subprocess,sys,time,traceback,uuid
from pathlib import Path
from datetime import datetime,timezone
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from window_identity import inspect_window,find_windows
from tools.owned_window_diagnostic import token_metadata,ordinary_token
from backends.game_click import Binding,GameClickEvidence,GameClickBroker
from runtime.scene import state_from_recognition,decide,verify
from runtime.game_profile import inspect_game,activate_once,process_security

def now():return datetime.now(timezone.utc).isoformat()
def dump(path,value):path.write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding='utf-8')

CAPTURE_MAX_FILES=50
CAPTURE_MAX_BYTES=64*1024*1024
CAPTURE_FRAME_RESERVE=6*1024*1024  # Above the supported 1450x869 RGBA PNG bound.

def ensure_capture_capacity(root,frames=1):
    """Shared run-parent budget; stop when full, never delete old evidence."""
    root=Path(root).resolve()
    if root==Path(root.anchor):raise RuntimeError('capture_budget_requires_scoped_parent')
    if type(frames) is not int or not 0<=frames<=8:raise ValueError('invalid_capture_reservation')
    count=used=0
    for path in root.rglob('*.png'):
        count+=1;used+=path.stat().st_size
        if count>CAPTURE_MAX_FILES or used>CAPTURE_MAX_BYTES:break
    if count+frames>CAPTURE_MAX_FILES or used+frames*CAPTURE_FRAME_RESERVE>CAPTURE_MAX_BYTES:
        raise RuntimeError('capture_budget_full_no_input_or_retry')
    return dict(files=count,bytes=used,max_files=CAPTURE_MAX_FILES,max_bytes=CAPTURE_MAX_BYTES,
                reserved_frames=frames,per_frame_reserve=CAPTURE_FRAME_RESERVE)

def capture(row,out,reference,layout='custom_selection'):
    ensure_capture_capacity(out.parent.parent)
    before=inspect_game(row['hwnd'],row['pid']);Binding.from_observation(before)
    if before['identity_version']!=row['identity_version']:raise RuntimeError('target_identity_changed')
    started=time.monotonic();cl=before['client']
    command=['powershell.exe','-NoProfile','-NonInteractive','-File',str(ROOT/'runtime/screen_frame.ps1'),
             '-Hwnd',str(row['hwnd']),'-ExpectedPid',str(row['pid']),'-X',str(cl['screen_x']),'-Y',str(cl['screen_y']),
             '-Width',str(cl['width']),'-Height',str(cl['height']),'-Output',str(out),'-Reference',str(reference),'-Layout',layout]
    p=subprocess.run(command,capture_output=True,encoding='utf-8',errors='replace',timeout=12,
                     creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    if p.returncode:raise RuntimeError('capture_failed:'+p.stderr[-1000:])
    result=json.loads(p.stdout);after=inspect_game(row['hwnd'],row['pid'])
    if (Binding.from_observation(after)!=Binding.from_observation(before)
            or after['executable_path']!=before['executable_path']):raise RuntimeError('capture_geometry_changed')
    result.update(identity=after,observed_monotonic=started,sha256=hashlib.sha256(out.read_bytes()).hexdigest(),
                  capture_budget=ensure_capture_capacity(out.parent.parent,frames=0))
    return result

def run(output,reference,reference_sha256,enabled,activate=False,wait_for_game=0,profile=None,allow_elevated=False):
    output.mkdir(parents=True,exist_ok=False)
    r=dict(schema='maawxq-software-loop/1',started_at=now(),pid=os.getpid(),runtime_token=token_metadata(),
           operator='MaaWXQ.runtime.custom_setup',decision_origin='runtime.scene.decide',
           remote_role='launch_and_debug_only',input_attempted=False,game_success=False)
    broker=None
    try:
        security=process_security();r['runtime_security']=security
        if (not security['known'] or security['app_container'] or security['ui_access']
                or (security['elevated'] and not allow_elevated)):
            raise RuntimeError('runtime_token_not_explicitly_allowed')
        r['elevated_runtime_explicitly_enabled']=allow_elevated
        if hashlib.sha256(reference.read_bytes()).hexdigest()!=reference_sha256:raise RuntimeError('reference_hash_changed')
        r['reference']={'path':str(reference),'sha256':reference_sha256,'source':'locally_reviewed_game_frame'}
        r['source_hashes']={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in
            [ROOT/'runtime/custom_setup.py',ROOT/'runtime/scene.py',ROOT/'runtime/game_profile.py',ROOT/'runtime/screen_frame.ps1',ROOT/'backends/game_click.py',ROOT/'backends/win32_single_click.py']}
        rows=[x for x in find_windows('王者万象棋') if x['title']=='王者万象棋' and x['class_name']=='UnityWndClass']
        if len(rows)!=1:raise RuntimeError('one_exact_game_window_required')
        rows[0]=inspect_game(rows[0]['hwnd'],rows[0]['pid']);r['game_profile']=rows[0]
        if profile is None:raise RuntimeError('explicit_local_game_profile_required')
        expected=json.loads(profile.read_text(encoding='utf-8'))
        for key in ['class_name','title','executable_path']:
            if rows[0][key]!=expected[key]:raise RuntimeError('authorized_game_profile_changed:'+key)
        if security['integrity_rid']<rows[0]['process_security']['integrity_rid']:
            raise RuntimeError('target_integrity_above_controller_no_input_attempted')
        if activate:r['activation']=activate_once(rows[0])
        if wait_for_game:
            deadline=time.monotonic()+wait_for_game
            dump(output/'waiting-for-game.json',dict(status='waiting_for_user_foreground',deadline_seconds=wait_for_game,input_calls=0))
            while True:
                current=inspect_game(rows[0]['hwnd'],rows[0]['pid'])
                if current['identity_version']!=rows[0]['identity_version']:raise RuntimeError('game_changed_while_waiting')
                if (current['visible'] and not current['minimized'] and current['desktop']['foreground_hwnd']==current['hwnd']):break
                if time.monotonic()>=deadline:raise RuntimeError('waiting_for_game_foreground_timed_out')
                time.sleep(.2)
        r['capture_budget']=ensure_capture_capacity(output.parent,frames=3 if enabled else 1)
        frame=capture(rows[0],output/'before.png',reference);dump(output/'capture-before.json',frame)
        state=state_from_recognition(frame);decision=decide(state)
        dump(output/'state-before.json',state);dump(output/'decision.json',decision)
        r.update(state=state,decision=decision)
        if not enabled or decision['action']!='click':
            r['status']='observe_only' if not enabled else 'unsupported_scene';return r
        # Recapture, recognize and decide again immediately before arming; never relabel an old image fresh.
        frame=capture(rows[0],output/'preaction.png',reference);dump(output/'capture-preaction.json',frame)
        state=state_from_recognition(frame);decision=decide(state)
        dump(output/'state-preaction.json',state);dump(output/'decision-preaction.json',decision)
        if decision['action']!='click':raise RuntimeError('preaction_scene_changed')
        ev=GameClickEvidence(Binding.from_observation(frame['identity']),frame['observed_monotonic'],
            *decision['target'],context='custom_setup',operation=decision['operation'],
            scene=state['scene'],frame_sha256=frame['sha256'],recognizer=state['source']['recognizer'],
            executable_path=frame['identity']['executable_path'])
        broker=GameClickBroker(ev,observer=inspect_game,enabled=True,max_age=5.0,max_seconds=2.0)
        broker.arm();r['input_attempted']=True
        action=broker.click_once();broker.close()
        action.update(stop_reason=broker.stop_reason,
                      cleanup_confirmed=(broker.release_confirmed and not broker.cleanup_errors
                                         and not broker.port.cleanup_errors and not broker.port.held),
                      source_frame=frame['sha256'],operation=decision['operation'],target=decision['target'],
                      native_down_count=broker.port.submitted_event_count,
                      native_owned_up_count=broker.port.owned_release_last_raw_return,
                      click_timing=broker.port.click_timing,
                      down_submitted_at=broker.port.down_submitted_at,
                      up_completed_at=broker.port.owned_release_completed_at)
        dump(output/'action.json',action);r['action']=action
        if not action['cleanup_confirmed']:raise RuntimeError('game_click_cleanup_unconfirmed')
        time.sleep(.8)
        after=capture(rows[0],output/'after.png',reference);dump(output/'capture-after.json',after)
        next_state=state_from_recognition(after);dump(output/'state-after.json',next_state)
        result=verify(state,decision,next_state,action);dump(output/'verification.json',result)
        r.update(status=result['status'],verification=result,next_state=next_state)
    except BaseException as e:r.update(status='stopped',error=str(e),traceback=traceback.format_exc())
    finally:
        if broker is not None:
            broker.close();r['cleanup_errors']=list(broker.cleanup_errors)+list(broker.port.cleanup_errors if broker.port else [])
            if broker.port is not None:r['native_summary']=dict(outcome=broker.port.submission_outcome,
                down_count=broker.port.submitted_event_count,owned_up_count=broker.port.owned_release_last_raw_return,
                held=broker.port.held,stop_reason=broker.stop_reason)
        r['completed_at']=now();dump(output/'receipt.json',r)
    return r

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output',type=Path,required=True);p.add_argument('--reference',type=Path,required=True)
    p.add_argument('--reference-sha256',required=True);p.add_argument('--enable-custom-setup',action='store_true')
    p.add_argument('--activate-game',action='store_true')
    p.add_argument('--wait-for-game',type=float,default=0);p.add_argument('--profile',type=Path,required=True)
    p.add_argument('--allow-elevated-runtime',action='store_true',help='Explicit operator authorization required; never elevates itself')
    a=p.parse_args()
    if not 0<=a.wait_for_game<=120:p.error('wait must be 0..120 seconds')
    print(json.dumps(run(a.output,a.reference,a.reference_sha256,a.enable_custom_setup,a.activate_game,a.wait_for_game,a.profile,a.allow_elevated_runtime),ensure_ascii=False))
if __name__=='__main__':main()
