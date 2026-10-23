"""Serial command ledger with a cumulative wall-clock budget and process-tree guard."""
import argparse
import json
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from planner.process_guard import run_guarded
from planner.path_safety import guard_writes


def stamp():
    return datetime.now(timezone(timedelta(hours=8))).isoformat()


def ledger_targets(ledger_path,count=1):
    path=Path(ledger_path).resolve()
    ledger=json.loads(path.read_text(encoding='utf-8')) if path.exists() else dict(budget_seconds=600,entries=[])
    if ledger['budget_seconds']!=600: raise ValueError('this round has a fixed 600-second budget')
    if any(e.get('status')=='RUNNING' for e in ledger['entries']): raise ValueError('previous command unresolved; reconcile ledger before continuing')
    targets=[path,path.with_suffix('.tmp')]
    for i in range(len(ledger['entries'])+1,len(ledger['entries'])+1+count):
        log=path.parent/f'command_{i:02d}.log'
        if log.exists() or log.is_symlink(): raise ValueError('command log already exists: '+str(log))
        targets.append(log)
    return targets


def execute(ledger_path, command, *, timeout=300, output=None, cwd=None, protected=()):
    ledger_path=Path(ledger_path).resolve()
    guard_writes(ledger_targets(ledger_path),protected)
    ledger_path.parent.mkdir(parents=True,exist_ok=True)
    ledger=json.loads(ledger_path.read_text(encoding='utf-8')) if ledger_path.exists() else dict(budget_seconds=600,entries=[])
    if ledger['budget_seconds'] != 600: raise ValueError('this round has a fixed 600-second budget')
    if any(e.get('status')=='RUNNING' for e in ledger['entries']): raise ValueError('previous command unresolved; reconcile ledger before continuing')
    used=sum(e['seconds'] for e in ledger['entries'])
    limit=min(300,float(timeout),600-used)
    if limit<=0:
        print('BLOCKED: cumulative compute/test budget exhausted',flush=True)
        return 3
    index=len(ledger['entries'])+1
    log=ledger_path.parent/f'command_{index:02d}.log'
    if log.exists(): raise ValueError('command log already exists')
    entry=dict(command=command,cwd=str(Path(cwd or '.').resolve()),start=stamp(),
               timeout_seconds=limit,output_dir=str(output) if output else None,log=str(log),status='RUNNING',seconds=0)
    ledger['entries'].append(entry)
    def save():
        ledger['used_seconds']=sum(e['seconds'] for e in ledger['entries'])
        ledger['remaining_seconds']=max(0,600-ledger['used_seconds'])
        tmp=ledger_path.with_suffix('.tmp')
        tmp.write_text(json.dumps(ledger,ensure_ascii=False,indent=2),encoding='utf-8'); tmp.replace(ledger_path)
    save()
    started=time.perf_counter()
    try:
        result=run_guarded(command,timeout=limit,log_path=log,cwd=cwd)
        entry.update(result,status='PASS' if result['exit_code']==0 else 'BLOCKED' if result['timed_out'] or result['exit_code']==3 else 'FAIL')
    except Exception as e:
        entry.update(exit_code=2,status='FAIL',reason=str(e))
    finally:
        entry.update(seconds=time.perf_counter()-started,end=stamp())
        save()
    print(json.dumps(dict(index=index,**entry,remaining_seconds=ledger['remaining_seconds']),ensure_ascii=False),flush=True)
    return entry['exit_code']


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--ledger',required=True); p.add_argument('--timeout',type=float,default=300)
    p.add_argument('--output'); p.add_argument('--cwd'); p.add_argument('command',nargs=argparse.REMAINDER)
    a=p.parse_args(); cmd=a.command[1:] if a.command[:1]==['--'] else a.command
    if not cmd: p.error('command required after --')
    try: code=execute(a.ledger,cmd,timeout=a.timeout,output=a.output,cwd=a.cwd)
    except (ValueError,OSError,KeyError,TypeError) as e: print('FAIL: '+str(e),file=sys.stderr);code=2
    raise SystemExit(code)
