"""Verify default compatibility and reproduce prepared evidence in a fresh source directory."""
import argparse
import importlib.metadata
import json
import shutil
import sys
from pathlib import Path
import yaml
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from planner.common import digest,json_write
from planner.experiment_inputs import verify_seal
from planner.process_guard import run_guarded
from planner.runner import tree_hashes

ROOT=Path(__file__).resolve().parents[1]
TABLES=['candidates.csv']+[f'schedule_{n}.csv' for n in ('baseline','improved','baseline_replanned','replanned')]


def compare(a,b):
    result={name:dict(reference_sha256=digest(a/name),actual_sha256=digest(b/name),
                      identical=(a/name).read_bytes()==(b/name).read_bytes()) for name in TABLES}
    if not all(r['identical'] for r in result.values()): raise ValueError('task/candidate byte regression')
    return result


def verify(round_dir,out):
    round_dir=Path(round_dir).resolve();out=Path(out).resolve()
    out.mkdir(parents=True,exist_ok=False)
    source=ROOT/'outputs/E0_seed42'
    default=round_dir/'default_regression';verify_seal(default)
    default_compare=compare(source,default)
    reference=round_dir/'experiments/E3_seed42';before=verify_seal(reference)
    # Copy maintained code only. Real prepared inputs are read at their original absolute paths.
    workspace=out/'workspace';workspace.mkdir()
    ignore=shutil.ignore_patterns('__pycache__','*.pyc','.pytest_cache')
    for name in ('planner','scripts','configs','demo','examples'):
        shutil.copytree(ROOT/name,workspace/name,ignore=ignore)
    for name in ('smoke_test.py','requirements.txt','requirements-dev.txt'):
        shutil.copyfile(ROOT/name,workspace/name)
    config=json.loads((reference/'effective_config.json').read_text(encoding='utf-8'))
    config.update(input_dir=str(Path(config['input_dir']).resolve()),cache_dir=str(out/'cache'),budget_seconds=90)
    for key in ('reuse_source','fault_event_path','frozen_sample'): config.pop(key,None)
    path=workspace/'reproduce.yaml';path.write_text(yaml.safe_dump(config),encoding='utf-8')
    reproduced=out/'result'
    cmd=[sys.executable,'-X','utf8',str(workspace/'smoke_test.py'),'--config',str(path),
         '--reuse-source',str(source),'--fault-event',str(reference/'fault_event.json'),'--out',str(reproduced)]
    receipt=run_guarded(cmd,timeout=90,log_path=out/'reproduction.log',cwd=workspace)
    json_write(out/'reproduction_execution.json',dict(command=cmd,cwd=str(workspace),**receipt))
    if receipt['exit_code']!=0: return receipt['exit_code']
    verify_seal(reproduced);reproduced_compare=compare(reference,reproduced)
    metrics=json.loads((reproduced/'metrics.json').read_text(encoding='utf-8'))
    if metrics['status']!='PASS' or any(r['evaluation_scope']!='raw_TLE_per_second' for r in metrics['plans'].values()):
        raise ValueError('reproduction requires actual TLE validation')
    unchanged=tree_hashes(reference)==before
    lock_unchanged=digest(ROOT/'requirements-lock.txt')==json.loads((round_dir/'session_start.json').read_text())['requirements_lock_sha256']
    if not unchanged or not lock_unchanged: raise ValueError('protected source changed')
    json_write(out/'verification.json',dict(status='PASS',default_byte_comparison=default_compare,
        default_cache=json.loads((default/'cache.json').read_text()),
        reproduction_byte_comparison=reproduced_compare,reproduction_independent_checks={k:v['status'] for k,v in metrics['plans'].items()},
        fresh_source_directory=str(workspace),reproduced_result=str(reproduced),
        environment='existing environment, fresh source directory; no clean environment installation performed',
        test_dependency=importlib.metadata.version('pytest'),source_unchanged=unchanged,requirements_lock_unchanged=lock_unchanged))
    return 0


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--round',required=True);p.add_argument('--out',required=True)
    a=p.parse_args();raise SystemExit(verify(a.round,a.out))
