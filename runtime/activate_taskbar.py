"""Software chooses and revalidates the real taskbar button before one normal click."""
import argparse,hashlib,json,subprocess,sys,time,traceback
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from runtime.custom_setup import now,dump,ensure_capture_capacity
from runtime.game_profile import inspect_game,process_security
from window_identity import find_windows
from backends.taskbar_activate import TaskbarActivationPort,select_button,same_button,validate_button

def observe(profile,directory):
    budget_root=directory.parent.parent
    ensure_capture_capacity(budget_root,frames=2,frame_reserve=600*1024)
    directory.mkdir(exist_ok=False)
    started=time.monotonic()
    command=['powershell.exe','-NoProfile','-NonInteractive','-File',str(ROOT/'runtime/taskbar_observe.ps1'),
             '-GameTitle',profile['title'],'-GameExe',profile['executable_path'],'-CaptureDirectory',str(directory)]
    result=subprocess.run(command,capture_output=True,encoding='utf-8',errors='strict',timeout=8,
                          creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    if result.returncode:raise RuntimeError('taskbar_observation_failed:'+result.stderr[-1000:])
    data=json.loads(result.stdout);data['observed_monotonic']=started
    data['capture_budget']=ensure_capture_capacity(budget_root,frames=0)
    dump(directory/'observation.json',data)
    return data

def run(output,profile_path,enabled,allow_admin):
    output.mkdir(exist_ok=False)
    result={'started_at':now(),'operator':'MaaWXQ.runtime.activate_taskbar','remote_role':'launch_only',
            'input_attempted':False,'game_input_calls':0,'game_foreground_verified':False}
    port=None
    try:
        security=process_security();result['runtime_security']=security
        if security['app_container'] or security['ui_access'] or (security['elevated'] and not allow_admin):
            raise RuntimeError('activation_runtime_not_authorized')
        profile=json.loads(profile_path.read_text(encoding='utf-8'))
        rows=[x for x in find_windows(profile['title']) if x['title']==profile['title'] and x['class_name']==profile['class_name']]
        if len(rows)!=1:raise RuntimeError('one_configured_game_window_required')
        game=inspect_game(rows[0]['hwnd'],rows[0]['pid']);result['game_before']=game
        if any(game[k]!=profile[k] for k in ('title','class_name','executable_path')):raise RuntimeError('configured_game_changed')
        if game['desktop']['foreground_hwnd']==game['hwnd']:
            result.update(status='game_already_foreground_no_input',game_foreground_verified=True);return result
        result['source_hashes']={str(x.relative_to(ROOT)):hashlib.sha256(x.read_bytes()).hexdigest() for x in
            (ROOT/'runtime/activate_taskbar.py',ROOT/'runtime/taskbar_observe.ps1',ROOT/'backends/taskbar_activate.py',ROOT/'backends/win32_single_click.py')}
        result['capture_budget']=ensure_capture_capacity(output.parent,frames=4 if enabled else 2,
                                                        frame_reserve=600*1024)
        first=observe(profile,output/'before');button=select_button(first,profile,game)
        result['selected_button']=button
        if not enabled:result['status']='observe_only';return result
        port=TaskbarActivationPort(button,profile,game,first['observed_monotonic'],first['foreground_hwnd'])
        port.arm()
        latest=observe(profile,output/'preaction')
        candidates=[x for x in latest['matches'] if x['runtime_id']==button['runtime_id']]
        if len(candidates)!=1:raise RuntimeError('selected_taskbar_button_disappeared')
        validate_button(candidates[0],profile)
        port.refresh_evidence(candidates[0],latest['observed_monotonic'])
        result['input_attempted']=True;result['action']=port.click_once()
        if not port.close() or port.cleanup_errors or port.held:raise RuntimeError('activation_cleanup_not_confirmed')
        result['cleanup_confirmed']=True
        if (result['action']['submission_outcome']!='down_and_owned_up_submitted'
                or result['action']['stop_reason']!='one_activation_click_completed'):
            raise RuntimeError('activation_interrupted_no_followup_input')
        deadline=time.monotonic()+1.5
        while True:
            after=inspect_game(game['hwnd'],game['pid'])
            if after['identity_version']!=game['identity_version']:raise RuntimeError('game_identity_changed_after_activation')
            result['game_after']=after
            if after['desktop']['foreground_hwnd']==game['hwnd'] and after['visible'] and not after['minimized']:
                result['game_foreground_verified']=True;break
            if time.monotonic()>=deadline:break
            time.sleep(.05)
        result['status']='game_foreground_verified' if result['game_foreground_verified'] else 'activation_not_verified_no_retry'
    except BaseException as error:result.update(status='stopped',error=str(error),traceback=traceback.format_exc())
    finally:
        if port is not None:
            port.close();result['native_summary']={'outcome':port.submission_outcome,'down_count':port.submitted_event_count,
                'owned_up_count':port.owned_release_last_raw_return,'held':port.held,'stop_reason':port.stop_reason,
                'cleanup_errors':port.cleanup_errors}
        result['completed_at']=now();dump(output/'receipt.json',result)
    return result

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output',type=Path,required=True);p.add_argument('--profile',type=Path,required=True)
    p.add_argument('--enable-taskbar-activation',action='store_true');p.add_argument('--allow-elevated-runtime',action='store_true')
    a=p.parse_args();print(json.dumps(run(a.output,a.profile,a.enable_taskbar_activation,a.allow_elevated_runtime),ensure_ascii=False))
