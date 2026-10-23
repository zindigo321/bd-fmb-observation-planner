"""Local real-data regression evidence. No real IDs or source data embedded."""
import argparse
import json
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from planner.common import Clock, csv_tasks, json_write, digest
from planner.io_contract import load_tables, parse_utc
from planner.validator import IndependentValidator
from planner.scheduler import replay_state, future_candidates, schedule


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--source',required=True)
    parser.add_argument('--reference',required=True)
    parser.add_argument('--out',required=True)
    parser.add_argument('--target-id',type=int)
    args=parser.parse_args()
    source,reference,out=map(lambda x:Path(x).resolve(),(args.source,args.reference,args.out))
    if any(out==p or out.is_relative_to(p) or p.is_relative_to(out) for p in (source,reference)):
        raise ValueError('verification output must be separate')
    out.mkdir(parents=True,exist_ok=False)
    config=json.loads((source/'effective_config.json').read_text(encoding='utf-8'))
    context=json.loads((source/'evaluation_context.json').read_text(encoding='utf-8'))
    day=parse_utc(context['day'])
    _,_,windows,_,_=load_tables(source/'standard_input',config)
    clock=Clock(dict(config,budget_seconds=60),out)
    try:
        v=IndependentValidator(config,day,context['sample'],windows,clock)
        initial=csv_tasks(source/'schedule_improved.csv')
        candidates=csv_tasks(source/'candidates.csv')
        event=dict(station_id=1,start_s=3600,end_s=10800)
        completed,locked,fragments,_=replay_state(initial,event,day)
        legal=schedule(future_candidates(candidates,completed+locked,event),'improved',fixed=completed+locked,interrupted=fragments,clock=clock)
        report=v.check(legal,fragments,event,original_plan=initial,label='nonempty_history')
        json_write(out/'nonempty_history.json',report)
        future_ids={r['satnum'] for r in initial if r['start_s']>event['start_s']}
        options=[c for c in candidates if c['satnum'] in future_ids and c['end_s']<event['start_s'] and c['duration_s']==120
                 and (args.target_id is None or c['satnum']==args.target_id)]
        forged=None
        # Establish feasibility of the altered table without history claims before testing provenance.
        for candidate in options:
            baseline=[dict(r,status='success') for r in legal if r['satnum']!=candidate['satnum']]
            check=v.check(baseline+[candidate])
            if check['status']=='PASS':
                forged=candidate
                break
        if forged is None: raise ValueError('no resource/geometrically legal backfill fixture found')
        results={}
        for status in ('completed','locked','success','new_success'):
            mutated=[r for r in legal if r['satnum']!=forged['satnum']]+[dict(forged,status=status)]
            result=v.check(mutated,fragments,event,original_plan=initial,label='forged_'+status)
            json_write(out/f'forged_{status}.json',result)
            results[status]=dict(status=result['status'],violation_count=result['violation_count'])
        comparison={name:dict(identical=digest(source/name)==digest(reference/name),
                              actual_sha256=digest(source/name),reference_sha256=digest(reference/name))
                    for name in ('schedule_baseline.csv','schedule_improved.csv','schedule_baseline_replanned.csv','schedule_replanned.csv','candidates.csv')}
        passed=report['status']=='PASS' and bool(completed) and all(r['status']=='FAIL' for r in results.values()) and all(r['identical'] for r in comparison.values())
        json_write(out/'verification.json',dict(status='PASS' if passed else 'FAIL',comparison=comparison,
            nonempty_history_count=len(completed),forged_fixture=forged,adversarial=results))
        return 0 if passed else 2
    finally:
        clock.logfile.close()


if __name__=='__main__': raise SystemExit(main())
