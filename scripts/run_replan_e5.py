"""Run or independently recheck E5; the paired methods share one frozen initial plan."""
import argparse
import json
import os
import sys
import traceback
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from planner.path_safety import guard_writes
from planner.common import BudgetExpired,json_write
from planner.replan_comparison import read,run,recheck
from planner.runner import tree_hashes
from scripts.budget_run import execute,ledger_targets
from scripts.run_improvement import config_inputs


def preflight(source,out,initial,event,ledger=None):
    config=read(source/'effective_config.json')
    protected=[source]+config_inputs(config)
    if initial:protected.append(initial)
    if event:protected.append(event)
    guard_writes([out],protected)
    if out.exists():raise ValueError('E5 output directory must be new')
    if ledger:guard_writes(ledger_targets(ledger),protected+[out])
    return protected


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source',required=True);p.add_argument('--out',required=True);p.add_argument('--ledger')
    p.add_argument('--initial-plan');p.add_argument('--event');p.add_argument('--reference-method',choices=['baseline','improved'],default='baseline')
    p.add_argument('--check-only',action='store_true');p.add_argument('--budget-seconds',type=float,default=120)
    p.add_argument('--worker',action='store_true',help=argparse.SUPPRESS);p.add_argument('--parent-pid',type=int,help=argparse.SUPPRESS)
    a=p.parse_args();source=Path(a.source).resolve();out=Path(a.out).resolve()
    if a.check_only and (a.initial_plan or a.event):raise ValueError('recheck consumes sealed shared inputs; no replacement initial/event allowed')
    if not 1<a.budget_seconds<=300:raise ValueError('budget must be >1 and <=300 seconds')
    initial=None if a.check_only else Path(a.initial_plan or source/f'initial_frozen_{a.reference_method}.json').resolve()
    event=None if a.check_only else Path(a.event or source/'fault_event.json').resolve()
    protected=preflight(source,out,initial,event,None if a.worker else a.ledger)
    if not a.worker:
        if not a.ledger:p.error('--ledger required')
        state=read(a.ledger) if Path(a.ledger).exists() else dict(entries=[])
        cap=min(a.budget_seconds,300,600-sum(e['seconds'] for e in state['entries']))
        if cap<=1:print('BLOCKED: insufficient remaining budget',file=sys.stderr);return 3
        cmd=[sys.executable,'-X','utf8',str(Path(__file__).resolve()),'--worker','--parent-pid',str(os.getpid()),'--source',str(source),'--out',str(out),'--budget-seconds',str(cap)]
        if a.check_only:cmd+=['--check-only']
        else:cmd+=['--initial-plan',str(initial),'--event',str(event),'--reference-method',a.reference_method]
        return execute(a.ledger,cmd,timeout=cap,output=out,protected=protected)
    if a.parent_pid!=os.getppid():raise ValueError('worker requires its live controlling parent')
    try:
        code=recheck(source,out,a.budget_seconds) if a.check_only else run(source,initial,event,a.reference_method,out,a.budget_seconds)
    except Exception as e:
        code=3 if isinstance(e,(FileNotFoundError,BudgetExpired)) else 2
        if out.exists():
            json_write(out/'failure.json',dict(status='BLOCKED' if code==3 else 'FAIL',reason=str(e),exit_code=code))
            (out/'exception.txt').write_text(traceback.format_exc(),encoding='utf-8')
        print(('BLOCKED: ' if code==3 else 'FAIL: ')+str(e),file=sys.stderr)
    if out.exists():json_write(out/'evidence_manifest.json',tree_hashes(out))
    return code


if __name__=='__main__':
    try:code=main()
    except FileNotFoundError as e:print('BLOCKED: '+str(e),file=sys.stderr);code=3
    except (ValueError,OSError,KeyError,TypeError) as e:print('FAIL: '+str(e),file=sys.stderr);code=2
    raise SystemExit(code)
