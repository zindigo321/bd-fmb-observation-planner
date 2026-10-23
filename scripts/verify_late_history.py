"""Run real E4 history attacks against the independent validator; preserve sources."""
import argparse
import copy
import json
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from planner.common import Clock,csv_tasks,json_write
from planner.io_contract import load_tables,parse_utc
from planner.validator import IndependentValidator
from planner.experiment_inputs import verify_seal
from planner.runner import tree_hashes


def verify(source,out):
    source,out=Path(source).resolve(),Path(out).resolve()
    if out==source or out.is_relative_to(source) or source.is_relative_to(out): raise ValueError('output overlaps source')
    before=verify_seal(source); out.mkdir(parents=True,exist_ok=False)
    config=json.loads((source/'effective_config.json').read_text(encoding='utf-8'))
    context=json.loads((source/'evaluation_context.json').read_text(encoding='utf-8'))
    day=parse_utc(context['day']); event=json.loads((source/'fault_event.json').read_text(encoding='utf-8'))
    _,_,windows,_,_=load_tables(source/'standard_input',config)
    clock=Clock(dict(config,budget_seconds=60),out)
    try:
        validator=IndependentValidator(config,day,context['sample'],windows,clock)
        results={}
        for method in ('baseline','improved'):
            initial=json.loads((source/f'initial_frozen_{method}.json').read_text(encoding='utf-8'))
            name='baseline_replanned' if method=='baseline' else 'replanned'
            tasks=csv_tasks(source/f'schedule_{name}.csv')
            history=json.loads((source/f'history_{method}.json').read_text(encoding='utf-8'))
            fragments=history['interrupted']
            assert history['completed'] and history['locked'] and fragments
            tests=[('legal',tasks,fragments,'PASS'),
                   ('delete_completed',[r for r in tasks if r['task_id']!=history['completed'][0]['task_id']],fragments,'FAIL'),
                   ('delete_locked',[r for r in tasks if r['task_id']!=history['locked'][0]['task_id']],fragments,'FAIL'),
                   ('delete_interrupted',tasks,[],'FAIL'),
                   ('forge_interrupted',tasks,fragments+[dict(fragments[0],task_id='FORGED_FRAGMENT')],'FAIL')]
            future={r['satnum'] for r in initial if r['start_s']>event['start_s']}
            forged=None; first_window_legal=None
            for c in csv_tasks(source/'candidates.csv'):
                if c['satnum'] not in future or c['end_s']>=event['start_s'] or c['duration_s']!=120: continue
                if first_window_legal is None: first_window_legal=c
                altered=[dict(r,status='success') for r in tasks if r['satnum']!=c['satnum']]+[c]
                if validator.check(altered)['status']=='PASS': forged=c;break
            resource_isolated=forged is not None
            if forged is None: forged=first_window_legal
            if forged is None: raise ValueError('no pre-fault candidate fixture found')
            for status in ('success','completed','locked'):
                altered=[r for r in tasks if r['satnum']!=forged['satnum']]+[dict(forged,status=status)]
                tests.append(('backfill_'+status,altered,fragments,'FAIL'))
            results[method]={}
            for label,rows,parts,expected in tests:
                report=validator.check(copy.deepcopy(rows),copy.deepcopy(parts),event,original_plan=initial,label=label)
                history_rejected=any('history set' in r['reason'] for r in report['violations'])
                json_write(out/f'{method}_{label}.json',dict(expected=expected,report=report,backfill_resource_isolated=resource_isolated if label.startswith('backfill') else None))
                results[method][label]=dict(expected=expected,actual=report['status'],violations=report['violation_count'],
                                          passed=report['status']==expected and (expected=='PASS' or history_rejected))
        unchanged=before==tree_hashes(source)
        passed=unchanged and all(r['passed'] for tests in results.values() for r in tests.values())
        json_write(out/'history_security.json',dict(status='PASS' if passed else 'FAIL',methods=results,
                   source_unchanged=unchanged,source_hashes_before=before,source_hashes_after=tree_hashes(source)))
        return 0 if passed else 2
    finally: clock.logfile.close()


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--source',required=True);p.add_argument('--out',required=True)
    a=p.parse_args();raise SystemExit(verify(a.source,a.out))
