"""Observe real selection, choose Yi Xing, verify its visible ring, then confirm."""
from pathlib import Path
import argparse,hashlib,json,os,sys,time,threading
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from runtime.custom_setup import capture,dump,now,ensure_capture_capacity
from runtime.game_profile import inspect_game,process_security
from runtime.lobby import recognize
from runtime.lobby_setup import run as transition
from backends.game_click import GameClickPort,Binding
from window_identity import find_windows

def main():
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('output','origin','reference','profile'):p.add_argument('--'+name,type=Path,required=True)
    p.add_argument('--enable-custom-selection',action='store_true');p.add_argument('--allow-elevated-runtime',action='store_true');p.add_argument('--reference-sha256',required=True);a=p.parse_args();a.output.mkdir(exist_ok=False)
    r={'started_at':now(),'operator':'MaaWXQ.auto_pick_yixing','remote_role':'launch_only','actions':[],
       'selection_confirmed':False,'strategic_actions':0}
    try:
        if not a.enable_custom_selection:raise ValueError('explicit_selection_enable_required')
        token=process_security()
        if token.get('elevated') and not a.allow_elevated_runtime:raise ValueError('elevated_runtime_not_authorized')
        if not token['known'] or token['app_container'] or token['ui_access']:raise ValueError('unsupported_runtime')
        if hashlib.sha256(a.reference.read_bytes()).hexdigest()!=a.reference_sha256:raise ValueError('reference_changed')
        profile_path=a.profile;profile=json.loads(profile_path.read_text(encoding='utf-8'))
        rows=[x for x in find_windows(profile['title'])if x['title']==profile['title'] and x['class_name']==profile['class_name']]
        if len(rows)!=1:raise ValueError('one_game_required')
        row=inspect_game(rows[0]['hwnd'],rows[0]['pid'])
        if any(row[k]!=profile[k]for k in ('title','class_name','executable_path')):raise ValueError('game_changed')
        if token['integrity_rid']<row['process_security']['integrity_rid']:raise ValueError('target_integrity_above_controller')
        probe=GameClickPort(inspect_game,Binding.from_observation(row),row['executable_path'],threading.Event())
        deadline=time.monotonic()+75;origin=None;marker=None
        for i in range(40):
            if time.monotonic()>=deadline:raise ValueError('selection_wait_timeout')
            ensure_capture_capacity(a.output.parent,frames=1)
            if a.origin.exists() and origin is None:
                origin=json.loads(a.origin.read_text(encoding='utf-8'))
                marker=origin.get('native_summary',{}).get('last_input_marker')
                if marker is None:raise ValueError('origin_input_marker_required')
            if marker is not None and probe.activity_marker()!=marker:raise ValueError('user_input_after_custom_start')
            frame=capture(row,a.output/('watch-'+str(i)+'.png'),a.reference,'yixing_character_choice');state=recognize(frame)
            latest={'schema':'selection-transition-observer/1','pid':os.getpid(),'input_calls':0,'activation_calls':0,
                    'captured_at':frame['captured_at'],'frame':frame,'state':state,'deadline_monotonic':deadline}
            dump(a.output/('watch-'+str(i)+'.json'),latest)
            dump(a.output/'latest.next.json',latest);os.replace(a.output/'latest.next.json',a.output/'latest.json')
            if marker is not None and probe.activity_marker()!=marker:raise ValueError('user_input_during_selection_capture')
            if state['scene']=='yixing_character_choice' and origin is not None:
                ensure_capture_capacity(a.output.parent,frames=6)
                pick=transition(a.output.parent/(a.output.name+'-pick'),a.reference,a.reference_sha256,profile_path,True,a.allow_elevated_runtime,'yixing_character_choice',selection_origin=a.origin)
                r['actions'].append(pick)
                if pick.get('status')=='stopped' or pick.get('native_summary',{}).get('held') or pick.get('native_summary',{}).get('cleanup_errors'):raise ValueError('selection_click_not_clean')
                marker=pick['native_summary']['last_input_marker']
                if probe.activity_marker()!=marker:raise ValueError('user_input_before_confirmation')
                confirm=transition(a.output.parent/(a.output.name+'-confirm'),a.reference,a.reference_sha256,profile_path,True,a.allow_elevated_runtime,'yixing_character_confirm',selection_origin=a.origin)
                r['actions'].append(confirm)
                if confirm.get('status')=='stopped':raise ValueError('selection_confirmation_not_submitted')
                r.update(status='yixing_ring_verified_confirmation_submitted',selected_ring_verified=True,confirmation_postcondition_pending=True)
                break
        else:raise ValueError('selection_capture_budget_exhausted')
    except Exception as error:r.update(status='stopped',error=str(error))
    finally:r['completed_at']=now();dump(a.output/'observer-done.json',r)


if __name__=='__main__':main()
