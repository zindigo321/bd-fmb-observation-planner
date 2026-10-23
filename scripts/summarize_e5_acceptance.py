"""Summarize E5 delivery gates and verify protected old artifacts including directories."""
import argparse
import json
import sys
import xml.etree.ElementTree as ET
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from planner.common import digest,json_write
from planner.path_safety import tree_snapshot,guard_writes
from planner.experiment_inputs import verify_seal


def summarize(root):
    root=Path(root).resolve()
    targets=[root/name for name in ('protected_after.json','protected_after.json.tmp','acceptance.json','acceptance.json.tmp')]
    guard_writes(targets)
    def read(name):return json.loads((root/name).read_text(encoding='utf-8'))
    before=read('protected_before.json')
    guard_writes(targets,[root/'protected_before.json',*before.keys()])
    protection={}
    for path,expected in before.items():
        after=tree_snapshot(Path(path))
        protection[path]=dict(unchanged=expected==after,entries=len(after),before=expected,after=after)
    json_write(root/'protected_after.json',protection)
    old_reproduction=read('before_fix/reproduction.json');path_fix=read('path_fix_verification.json')
    regression=read('e3_e4_regression.json');e5=read('E5_common_baseline/summary.json')
    for directory in (root/'E5_common_baseline',*[root/'experiments'/n for n in regression['tables']]):verify_seal(directory)
    conditions=read('E5_common_baseline/shared/contract.json')
    fair=all(read(f'E5_common_baseline/conditions_{m}.json')['inputs_before']==read(f'E5_common_baseline/conditions_{m}.json')['inputs_after']==conditions for m in ('baseline','improved'))
    history=read('E5_history_security/history_security.json');recheck=read('E5_recheck/recheck.json')
    demo=read('demo/demo_data_check.json');browser=read('browser/browser_checks.json')
    suite=ET.parse(root/'pytest_e5.xml').getroot().find('testsuite')
    tests_ok=int(suite.attrib['tests'])>0 and all(int(suite.attrib[k])==0 for k in ('failures','errors','skipped'))
    junction=next(c for c in suite.findall('testcase') if c.attrib['name']=='test_windows_junction_alias_cannot_write_to_source')
    gates=dict(p1_reproduced_on_copy='PASS' if old_reproduction['exit_code']==2 and not old_reproduction['source_unchanged'] else 'FAIL',
               p1_fixed_no_tree_writes=path_fix['status'],windows_junction='PASS' if not list(junction) else 'FAIL',
               common_conditions='PASS' if fair else 'FAIL',e5_execution=e5['status'],e5_independent_recheck=recheck['status'],
               e5_history_attacks=history['status'],e3_e4_regression=regression['status'],demo_data=demo['status'],demo_browser=browser['status'],
               tests='PASS' if tests_ok else 'FAIL',old_inputs_and_demo='PASS' if all(v['unchanged'] for v in protection.values()) else 'FAIL',
               team1_data='PENDING_EXTERNAL',team3_confirmation='PENDING_EXTERNAL',optional_evaluator='BLOCKED',
               supplementary_improved_initial='NOT_RUN',clean_environment_install='NOT_RUN',optical_conditions='NOT_VERIFIED')
    initial=e5['origin']['initial_file_sha256']
    json_write(root/'acceptance.json',dict(gates=gates,pytest_count=int(suite.attrib['tests']),pytest_seconds=float(suite.attrib['time']),
        browser_checks=len(browser['checks']),history_cases=sum(len(v) for v in history['methods'].values()),
        recheck_files=recheck['source_file_count'],recheck_directories=recheck['source_directory_count'],
        common_initial_sha256=initial,common_conditions=e5['shared_conditions'],gain=e5['gain'],
        initial_score=e5['initial_score'],rows=e5['rows'],budget_ledger=str(root/'run_ledger.json'),
        protected_before=str(root/'protected_before.json'),protected_after=str(root/'protected_after.json')))
    required=[v for k,v in gates.items() if k not in ('team1_data','team3_confirmation','optional_evaluator','supplementary_improved_initial','clean_environment_install','optical_conditions')]
    return 0 if all(v=='PASS' for v in required) else 2


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--round',required=True)
    a=p.parse_args()
    try:code=summarize(a.round)
    except FileNotFoundError as e:print('BLOCKED: '+str(e),file=sys.stderr);code=3
    except (ValueError,OSError,KeyError,TypeError) as e:print('FAIL: '+str(e),file=sys.stderr);code=2
    raise SystemExit(code)
