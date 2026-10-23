"""Collect separate acceptance gates from this round's actual evidence files."""
import argparse
import json
import sys
import xml.etree.ElementTree as ET
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from planner.common import digest,json_write
from planner.experiment_inputs import verify_seal
from planner.runner import tree_hashes


def summarize(root):
    root=Path(root).resolve()
    def read(path): return json.loads((root/path).read_text(encoding='utf-8'))
    summary=read('experiments/summary.json')
    for case in summary['cases']: verify_seal(case['directory'])
    sources=read('experiments/frozen_inputs.json')['sources']
    sources_unchanged=all(tree_hashes(Path(s['path']))==s['hashes_before'] for s in sources.values())
    config=read('experiments/E4_seed42_late/effective_config.json')
    actual={p.name:dict(sha256=digest(p),bytes=p.stat().st_size) for p in Path(config['input_dir']).iterdir() if p.is_file()}
    raw_unchanged=actual==read('experiments/E4_seed42_late/frozen_sample.json')['input_hashes']
    history=read('history_security_v2/history_security.json')
    recheck=read('recheck_late/recheck.json')
    delivery=read('delivery_verification/verification.json')
    demo=read('demo_delivery/demo_data_check.json');browser=read('browser_delivery/browser_checks.json')
    tests=ET.parse(root/'pytest_pass.xml').getroot().find('testsuite')
    test_pass=int(tests.attrib['tests'])>0 and int(tests.attrib['failures'])==int(tests.attrib['errors'])==int(tests.attrib['skipped'])==0
    gates=dict(algorithm_execution=summary['acceptance']['algorithm_execution'],independent_legality=summary['acceptance']['independent_legality'],
               history_preservation=history['status'],demo_data=demo['status'],browser_interaction=browser['status'],
               readonly_recheck=recheck['status'],default_and_fresh_directory=delivery['status'],
               pytest='PASS' if test_pass else 'FAIL',protected_inputs='PASS' if sources_unchanged and raw_unchanged and delivery['requirements_lock_unchanged'] else 'FAIL',
               team1_data_delivery='PENDING_EXTERNAL',team3_interface_confirmation='PENDING_EXTERNAL',optional_evaluator='BLOCKED',
               clean_environment_install='NOT_RUN',video='NOT_RUN')
    code_root=Path(__file__).resolve().parents[1]
    paths=[code_root/'smoke_test.py',code_root/'requirements.txt',code_root/'requirements-dev.txt']
    for name in ('planner','scripts','tests','configs','demo'):
        paths += [p for p in (code_root/name).rglob('*') if p.is_file() and '__pycache__' not in p.parts]
    destination=root/'acceptance.json'
    if destination.exists(): raise ValueError('acceptance evidence already exists')
    json_write(destination,dict(gates=gates,pytest_count=int(tests.attrib['tests']),pytest_seconds=float(tests.attrib['time']),
        browser_check_count=len(browser['checks']),recheck_file_count=recheck['source_file_count'],
        history_cases=sum(len(v) for v in history['methods'].values()),source_runs_unchanged=sources_unchanged,raw_inputs_unchanged=raw_unchanged,
        budget_ledger=str(root/'run_ledger.json'),demo=str(root/'demo_delivery/index.html'),
        code_hashes={p.relative_to(code_root).as_posix():digest(p) for p in paths},
        note='Separate gates; external confirmation, legacy evaluator, clean install and video are not claimed as passed.'))
    required=[v for k,v in gates.items() if k not in ('team1_data_delivery','team3_interface_confirmation','optional_evaluator','clean_environment_install','video')]
    return 0 if all(v=='PASS' for v in required) else 2


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--round',required=True)
    a=p.parse_args();raise SystemExit(summarize(a.round))
