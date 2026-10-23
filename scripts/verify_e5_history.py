"""Verify real E5 history attacks on a disposable copy, never on source evidence."""
import argparse
import copy
import json
import shutil
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from planner.common import Clock,BudgetExpired,csv_tasks,json_write
from planner.experiment_inputs import verify_seal
from planner.path_safety import guard_writes,tree_snapshot
from planner.replan_comparison import read,validator_for,assert_contract,paired_method


def verify(source,out):
    source=Path(source).resolve();out=Path(out).resolve()
    config=read(source/'effective_config.json');guard_writes([out],[source,Path(config['input_dir'])])
    if out.exists():raise ValueError('attack evidence output must be new')
    verify_seal(source);before=tree_snapshot(source);out.mkdir(parents=True,exist_ok=False)
    fixture=out/'fixture_copy';shutil.copytree(source,fixture);fixture_before=tree_snapshot(fixture)
    clock=Clock(dict(config,budget_seconds=60),out)
    try:
        validator,_,_,_=validator_for(fixture,clock)
        bundle=read(fixture/'shared/bundle.json');expected=read(fixture/'shared/contract.json');assert_contract(bundle,expected)
        initial,event,fragments=bundle['initial'],bundle['event'],bundle['interrupted']
        future_ids={r['satnum'] for r in initial if r['start_s']>=event['start_s']}
        forged=next((c for c in bundle['candidates'] if c['satnum'] in future_ids and c['end_s']<event['start_s'] and c['duration_s']==120),None)
        if forged is None:raise ValueError('no pre-fault candidate fixture')
        geometry_control=validator.check([forged],label='backfill_candidate_alone')
        if geometry_control['status']!='PASS':raise ValueError('backfill must be individually window/geometrically legal')
        json_write(out/'backfill_geometry_control.json',geometry_control)
        results={}
        for method in ('baseline','improved'):
            tasks=csv_tasks(fixture/f'schedule_{method}.csv')
            completed=next(r for r in tasks if r['status']=='completed');locked=next(r for r in tasks if r['status']=='locked')
            cases=[('legal',tasks,fragments,'PASS'),
                   ('delete_completed',[r for r in tasks if r['task_id']!=completed['task_id']],fragments,'FAIL'),
                   ('delete_locked',[r for r in tasks if r['task_id']!=locked['task_id']],fragments,'FAIL'),
                   ('delete_interrupted',tasks,[],'FAIL'),
                   ('forge_interrupted',tasks,fragments+[dict(fragments[0],task_id='FORGED_COPY_ONLY')],'FAIL')]
            for status in ('new_success','completed','locked'):
                cases.append(('backfill_'+status,[r for r in tasks if r['satnum']!=forged['satnum']]+[dict(forged,status=status)],fragments,'FAIL'))
            results[method]={}
            for name,rows,parts,wanted in cases:
                report=validator.check(copy.deepcopy(rows),copy.deepcopy(parts),event,original_plan=copy.deepcopy(initial),label=name)
                history_rejected=any('history set' in r['reason'] for r in report['violations'])
                passed=report['status']==wanted and (wanted=='PASS' or history_rejected)
                results[method][name]=dict(expected=wanted,actual=report['status'],passed=passed,history_rejected=history_rejected)
                json_write(out/f'{method}_{name}.json',report)
        fake=copy.deepcopy(bundle);fake['origin']['source']='different-source-copy'
        mismatch_rejected=False
        try:paired_method(fake,'improved',expected,clock)
        except ValueError:mismatch_rejected=True
        unchanged=tree_snapshot(source)==before and tree_snapshot(fixture)==fixture_before
        passed=unchanged and mismatch_rejected and all(r['passed'] for cases in results.values() for r in cases.values())
        json_write(out/'history_security.json',dict(status='PASS' if passed else 'FAIL',methods=results,source_tree_unchanged=unchanged,
            source_before=before,source_after=tree_snapshot(source),fixture_tree_unchanged=tree_snapshot(fixture)==fixture_before,
            common_source_mismatch_rejected=mismatch_rejected,backfill_fixture='individually TLE/window legal; resource isolation is not claimed'))
        return 0 if passed else 2
    finally:clock.logfile.close()


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--source',required=True);p.add_argument('--out',required=True)
    a=p.parse_args()
    try:code=verify(a.source,a.out)
    except (FileNotFoundError,BudgetExpired) as e:print('BLOCKED: '+str(e),file=sys.stderr);code=3
    except (ValueError,OSError,KeyError,TypeError) as e:print('FAIL: '+str(e),file=sys.stderr);code=2
    raise SystemExit(code)
