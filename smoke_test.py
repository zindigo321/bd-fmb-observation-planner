#!/usr/bin/env python3
"""Unified bounded entry point. All outputs must be new directories."""
import argparse
import json
import os
import sys
import time
import traceback
from pathlib import Path
import yaml
from planner.config import normalize
from planner.process_guard import run_guarded


def write_json(path,obj):
    path.write_text(json.dumps(obj,ensure_ascii=False,indent=2),encoding='utf-8')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config',default='configs/smoke.yaml')
    parser.add_argument('--out',default=None)
    parser.add_argument('--check-only',action='store_true')
    parser.add_argument('--source',help='read-only prior run directory')
    parser.add_argument('--evaluate',metavar='TASKS_CSV')
    parser.add_argument('--initial-plan')
    parser.add_argument('--event')
    parser.add_argument('--interrupted')
    parser.add_argument('--optional-evaluator',action='store_true')
    parser.add_argument('--seed',type=int)
    parser.add_argument('--method',choices=['baseline','improved','both'])
    parser.add_argument('--input-dir')
    parser.add_argument('--input-mode',choices=['tle','windows'])
    parser.add_argument('--worker',action='store_true',help=argparse.SUPPRESS)
    args=parser.parse_args()
    out=Path(args.out or ('outputs/run_'+time.strftime('%Y%m%d_%H%M%S')+'_'+str(time.time_ns()%1000000))).resolve()
    try:
        if sum(bool(x) for x in [args.check_only,args.evaluate,args.optional_evaluator])>1:
            raise ValueError('select only one run mode')
        if args.check_only and not args.source: raise ValueError('--check-only requires --source')
        c=normalize(yaml.safe_load(Path(args.config).read_text(encoding='utf-8')))
        for k in ('seed','method','input_dir','input_mode'):
            if getattr(args,k) is not None: c[k]=getattr(args,k)
        c=normalize(c)
        read_paths=[Path(c['input_dir']),Path(args.config).resolve()]
        for value in (args.source,args.evaluate,args.initial_plan,args.event,args.interrupted):
            if value: read_paths.append(Path(value).resolve())
        if c.get('frozen_sample'): read_paths.append(Path(c['frozen_sample']).resolve())
        cache=Path(c['cache_dir']).resolve()
        if cache==out or cache.is_relative_to(out) or out.is_relative_to(cache):
            raise ValueError('cache and run output must be separate directories')
        if any(cache==p or cache.is_relative_to(p) for p in read_paths):
            raise ValueError('cache must not write inside input or source paths')
        if any(out==p or out.is_relative_to(p) or p.is_relative_to(out) for p in read_paths):
            raise ValueError('output must be separate from all input/source paths')
        if args.worker:
            # Only a fresh directory prepared by our live parent may enter the worker.
            # A manually supplied hidden flag must never bypass no-overwrite checks.
            launch=json.loads((out/'launch.json').read_text(encoding='utf-8'))
            if launch.get('parent_pid') != os.getppid() or set(p.name for p in out.iterdir()) != {'launch.json','console.log'}:
                raise ValueError('worker requires a fresh parent-owned launch directory')
            return worker(args,c,out)
        out.mkdir(parents=True,exist_ok=False)
    except FileNotFoundError as e:
        print('BLOCKED: '+str(e),file=sys.stderr)
        return 3
    except (ValueError,OSError,KeyError,TypeError,yaml.YAMLError) as e:
        print('FAIL: '+str(e),file=sys.stderr)
        return 2
    write_json(out/'launch.json',dict(command=[sys.executable,*sys.argv],budget_seconds=c['budget_seconds'],parent_pid=os.getpid()))
    command=[sys.executable,'-X','utf8','-u',str(Path(__file__).resolve()),*sys.argv[1:]]
    if args.out is None: command+=['--out',str(out)]
    command+=['--worker']
    try:
        receipt=run_guarded(command,timeout=float(c['budget_seconds']),log_path=out/'console.log')
    except Exception as e:
        receipt=dict(exit_code=3,timed_out=False,reason=str(e))
    write_json(out/'execution.json',receipt)
    if receipt.get('timed_out'):
        write_json(out/'failure.json',dict(status='BLOCKED',reason='deadline expired; entire process tree terminated',exit_code=3))
    from planner.runner import tree_hashes
    write_json(out/'evidence_manifest.json',tree_hashes(out))
    print(json.dumps(dict(output=str(out),**receipt),ensure_ascii=False))
    return receipt['exit_code']


def worker(args,config,out):
    from planner.common import Clock, BudgetExpired
    from planner.runner import run,recheck,evaluate,versions
    clock=Clock(config,out)
    try:
        write_json(out/'versions.json',versions())
        write_json(out/'effective_config.json',config)
        clock.log('START '+json.dumps([sys.executable,*sys.argv],ensure_ascii=False))
        if args.optional_evaluator:
            write_json(out/'optional_evaluator.json',dict(status='BLOCKED',reason='legacy rule SHA256 mismatch and unsupported earliest_midpoint_prioritize_future; see docs/optional_evaluator.md'))
            return 3
        if args.check_only: return recheck(Path(args.source).resolve(),out,clock)
        if args.evaluate: return evaluate(config,out,clock,args.evaluate,args.initial_plan,args.event,args.interrupted)
        return run(config,out,clock)
    except Exception as e:
        code=3 if isinstance(e,(BudgetExpired,FileNotFoundError)) else 2
        write_json(out/'failure.json',dict(status='BLOCKED' if code==3 else 'FAIL',reason=str(e),exit_code=code))
        (out/'exception.txt').write_text(traceback.format_exc(),encoding='utf-8')
        clock.log('STOP '+str(e))
        return code
    finally:
        clock.log('END')
        clock.logfile.close()


if __name__=='__main__':
    raise SystemExit(main())
