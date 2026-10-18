"""Read-only actual screen -> persistent Advisor integration; never dispatch input."""
import argparse,hashlib,json,sys,traceback
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from runtime.custom_setup import capture,dump,now
from runtime.game_profile import inspect_game,process_security
from runtime.lobby import recognize
from runtime.strategy_bridge import ScreenAdvisorBridge,unverified_configuration
from runtime.observe_minimal_state import run_saved
from window_identity import find_windows

def run(args):
    args.output.mkdir(exist_ok=False);r={'started_at':now(),'input_calls':0,'activation_calls':0}
    try:
        security=process_security();r['runtime_security']=security
        if not security['known'] or security['app_container'] or security['ui_access'] or (security['elevated'] and not args.allow_elevated_runtime):raise ValueError('unauthorized_runtime')
        if hashlib.sha256(args.reference.read_bytes()).hexdigest()!=args.reference_sha256:raise ValueError('reference_changed')
        advisor_source=args.advisor_root/'strategy/advisor.py'
        if args.advisor_root.resolve()!=ROOT:raise ValueError('integrated_advisor_source_root_required')
        if hashlib.sha256(advisor_source.read_bytes()).hexdigest()!=args.advisor_sha256:raise ValueError('advisor_source_changed')
        from strategy.advisor import Advisor
        import inspect
        if Path(inspect.getfile(Advisor)).resolve()!=advisor_source.resolve():raise ValueError('imported_advisor_source_mismatch')
        r['advisor_sha256']=args.advisor_sha256
        r['strategy_source_hashes']={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest()
                                     for p in (ROOT/'strategy').rglob('*.py')}
        profile=json.loads(args.profile.read_text(encoding='utf-8'))
        rows=[x for x in find_windows(profile['title'])if x['title']==profile['title'] and x['class_name']==profile['class_name']]
        if len(rows)!=1:raise ValueError('one_game_required')
        row=inspect_game(rows[0]['hwnd'],rows[0]['pid']);r['game_identity']=row
        if any(row[k]!=profile[k]for k in ('title','class_name','executable_path')):raise ValueError('game_changed')
        bridge=ScreenAdvisorBridge(Advisor(unverified_configuration()))
        frame=capture(row,args.output/'battle.png',args.reference,'battle_controls')
        state=recognize(frame);dump(args.output/'capture.json',frame);dump(args.output/'recognition.json',state)
        r['minimal_state']=run_saved(frame,state,args.output/'minimal-state',
                                     source_mode='live_capture',budget_root=args.output.parent)
        r.update(bridge.observe_frame(frame,state,minimal_state=r['minimal_state'],
                                      now=now(),source_mode='live_capture'))
        if r.get('observations'):
            (args.output/'observations.jsonl').write_text(''.join(json.dumps(x,ensure_ascii=False)+'\n'for x in r['observations']),encoding='utf-8')
    except Exception as error:r.update(status='stopped',error=str(error),traceback=traceback.format_exc())
    finally:r['completed_at']=now();dump(args.output/'receipt.json',r)
    return r
if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('output','reference','profile','advisor-root'):p.add_argument('--'+name,type=Path,required=True)
    p.add_argument('--reference-sha256',required=True);p.add_argument('--advisor-sha256',required=True)
    p.add_argument('--allow-elevated-runtime',action='store_true')
    result=run(p.parse_args());print(json.dumps({'status':result['status'],'input_calls':0}))
