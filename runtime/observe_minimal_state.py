"""Read saved real capture and OCR selected regions; no input/activation APIs."""
import argparse,hashlib,json,sys
from pathlib import Path
from datetime import datetime,timezone
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from runtime.minimal_state import extract
from runtime.custom_setup import ensure_capture_capacity
from runtime.batch_ocr import read_regions

def run_saved(frame,state,output,*,source_mode='saved_replay',budget_root=None,region_names=('round','energy'),cache=None):
    if source_mode not in ('saved_replay','live_capture'):raise ValueError('unsupported_source_mode')
    output.mkdir(exist_ok=False)
    budget_root=Path(budget_root) if budget_root is not None else output.parent
    source=Path(frame['image'])
    if hashlib.sha256(source.read_bytes()).hexdigest()!=frame['sha256']:raise ValueError('capture_file_changed')
    if state.get('frame_sha256')!=frame['sha256']:raise ValueError('recognition_frame_changed')
    bundles={}
    timing=None
    if state.get('scene')=='battle_controls' and state.get('match_started')is True:
        ensure_capture_capacity(budget_root,frames=0)
        bundles,timing=read_regions(frame,output/'batch',names=region_names,cache=cache)
    result=extract(frame,state,bundles,now=datetime.now(timezone.utc).isoformat())
    result['source_capture_reused']=source_mode=='saved_replay'
    result['source_mode']=source_mode
    result['saved_image_processed']=True
    result['live_execution_claimed']=False
    result['ocr_timing']=({'process_wall_seconds':timing['process_wall_seconds'],'regions':len(timing['regions']),
                           'engine_elapsed_ms':timing['elapsed_ms'],'static_name_cache_hits':timing['cache_hits']}
                          if timing is not None else None)
    with (output/'minimal-state.json').open('x',encoding='utf-8')as f:json.dump(result,f,ensure_ascii=False,indent=2)
    return result

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    for field in ('capture','state','output'):parser.add_argument('--'+field,type=Path,required=True)
    args=parser.parse_args()
    result=run_saved(json.loads(args.capture.read_text(encoding='utf-8')),json.loads(args.state.read_text(encoding='utf-8')),args.output)
    print(json.dumps({'status':result['extraction_status'],'input_calls':0,'output':str(args.output/'minimal-state.json')}))
