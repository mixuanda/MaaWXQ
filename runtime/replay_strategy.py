"""Project a saved V5 minimal state and evaluate only an isolated replay Advisor."""
import argparse,json
from pathlib import Path
from strategy.advisor import Advisor
from strategy.minimal_screen import project_minimal
from strategy.recognition import frame_records
from runtime.strategy_bridge import unverified_configuration


def replay(minimal,frame,state,*,now):
    projection=project_minimal(minimal,frame,state,match_id='isolated-screen-replay',
                               now=now,source_mode='saved_replay',start_match=True)
    batch=frame_records(projection['recognition_batch'])
    advisor=Advisor(unverified_configuration())
    if batch['records']:
        advisor.observe_batch(batch['records'],now=now)
        decision=advisor.decide(decision_at=now,point_id='saved-frame')
    else:
        decision=None
    return {'schema_version':'strategy-screen-replay/1','projection':projection,
            'observation_receipt':batch,'decision':decision,'input_allowed':False,
            'persistent_live_advisor_mutated':False,'native_input_calls':0}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for key in ('minimal','frame','recognition','output'):
        parser.add_argument('--'+key,type=Path,required=True)
    parser.add_argument('--now',required=True,help='actual replay decision cutoff; original capture time stays unchanged')
    args=parser.parse_args()
    def read(path):return json.loads(path.read_text(encoding='utf-8'))
    result=replay(read(args.minimal),read(args.frame),read(args.recognition),now=args.now)
    with args.output.open('x',encoding='utf-8')as stream:
        json.dump(result,stream,ensure_ascii=False,indent=2,allow_nan=False)
    print(json.dumps({'status':'saved_replay_only','input_calls':0,'output':str(args.output)}))


if __name__=='__main__':main()
