"""Optional experiment paths and evidence display; synthetic fixtures only."""
import copy
import json
from pathlib import Path
import shutil
import subprocess
import sys
import pytest
from planner.common import csv_tasks, json_write, utc_at
from planner.experiment_inputs import changes_by_target, fault_impact, load_fixed_event, prepare_frozen, check_candidates
from planner.io_contract import parse_utc
from planner.runner import tree_hashes
from scripts.build_demo import build

ROOT=Path(__file__).resolve().parents[1]
DAY=parse_utc('2026-08-03T06:00:00Z')


def cli(*args):
    return subprocess.run([sys.executable,'-X','utf8',str(ROOT/'smoke_test.py'),'--config',str(ROOT/'configs/synthetic.yaml'),*map(str,args)],
                          cwd=ROOT,capture_output=True,text=True,encoding='utf-8',timeout=30)


def physical_event():
    return dict(station_id=7,start_s=120,end_s=600,start_utc=utc_at(DAY,120),end_utc=utc_at(DAY,600))


@pytest.mark.parametrize('change',[
    dict(station_id=99),dict(station_id=True),dict(start_s=-1),dict(start_s=600),
    dict(end_s=3601),dict(start_s=120.5),dict(start_utc='2026-08-03T06:03:00Z')])
def test_fixed_event_rejects_invalid_physical_parameters(tmp_path,change):
    event=tmp_path/'event.json'; json_write(event,dict(physical_event(),**change))
    result=cli('--fault-event',event,'--out',tmp_path/'rejected')
    assert result.returncode==2,result.stdout+result.stderr
    failure=json.loads((tmp_path/'rejected/failure.json').read_text())
    assert failure['status']=='FAIL' and 'fixed fault' in failure['reason']


@pytest.fixture(scope='module')
def synthetic_run(tmp_path_factory):
    root=tmp_path_factory.mktemp('demo')
    event=root/'event.json'; json_write(event,dict(physical_event(),affected_future=['SOURCE_ONLY']))
    source=root/'run'; result=cli('--fault-event',event,'--out',source)
    assert result.returncode==0,result.stdout+result.stderr
    return source


def summary_for(tmp_path,source):
    summary=tmp_path/'summary.json'
    json_write(summary,dict(cases=[dict(id='synthetic',seed=42,scenario='early',directory=str(source))]))
    return summary


def test_fixed_event_ignores_foreign_plan_annotations(synthetic_run):
    event=json.loads((synthetic_run/'fault_event.json').read_text())
    for key,value in physical_event().items(): assert event[key]==value
    assert 'affected_future' not in event
    impacts=json.loads((synthetic_run/'fault_impacts.json').read_text())
    for method in ('baseline','improved'):
        assert impacts[method]==fault_impact(csv_tasks(synthetic_run/f'schedule_{method}.csv'),event)
        assert 'SOURCE_ONLY' not in json.dumps(impacts[method])


@pytest.mark.parametrize('options',[
    ['--event','unused.json'],['--reuse-source','unused','--check-only','--source','unused'],
    ['--fault-event','unused.json','--evaluate','unused.csv']])
def test_run_and_evaluation_event_options_are_separate(tmp_path,options):
    result=cli(*options,'--out',tmp_path/'out')
    assert result.returncode==2
    assert not (tmp_path/'out').exists()


def test_candidate_reuse_rejects_different_semantics(tmp_path,synthetic_run):
    rows=csv_tasks(synthetic_run/'candidates.csv'); changed=copy.deepcopy(rows)
    changed[0]['start_s']+=1
    shutil.copyfile(synthetic_run/'candidates.csv',tmp_path/'candidates.csv')
    with pytest.raises(ValueError,match='differs from frozen candidates'):
        check_candidates(changed,dict(reuse_source=str(synthetic_run)),tmp_path,{})


def test_frozen_source_rejects_relabelled_seed(tmp_path,synthetic_run):
    config=json.loads((synthetic_run/'effective_config.json').read_text())
    config.update(reuse_source=str(synthetic_run),seed=17)
    with pytest.raises(ValueError,match='parameter mismatch: seed'):
        prepare_frozen(config,tmp_path,None)


def test_net_changes_ignore_status_and_id_but_detect_movement():
    a=dict(satnum=1,station_id=7,start_utc='a',end_utc='b',duration_s=120,task_id='before',status='success')
    b=dict(a,satnum=2); c=dict(a,satnum=3)
    result=changes_by_target([a,b,c],[dict(a,task_id='after',status='completed'),dict(b,station_id=9),dict(a,satnum=4)])
    assert result['counts']==dict(added=1,deleted=1,retained=1,moved_or_duration_changed=1)
    assert result['net_adjusted_target_count']==3


def test_demo_from_actual_synthetic_run_and_source_readonly(tmp_path,synthetic_run):
    before=tree_hashes(synthetic_run); summary=summary_for(tmp_path,synthetic_run)
    out=tmp_path/'demo'; assert build(summary,out)==0
    html=(out/'index.html').read_text(encoding='utf-8')
    assert '"synthetic":true' in html and '合成契约示例' in html
    assert 'supplied_windows_only' in html
    assert json.loads((out/'demo_data_check.json').read_text())['status']=='PASS'
    assert tree_hashes(synthetic_run)==before
    with pytest.raises(ValueError,match='inside sealed source'): build(summary,synthetic_run/'nested_demo')
    assert tree_hashes(synthetic_run)==before
    with pytest.raises(ValueError,match='must be new'): build(summary,out)


@pytest.mark.parametrize('kind',['missing','empty','fail','blocked','forged_score','forged_rate'])
def test_demo_errors_never_display_success(tmp_path,synthetic_run,kind):
    source=tmp_path/'source'; shutil.copytree(synthetic_run,source)
    summary=summary_for(tmp_path,source)
    if kind=='missing': (source/'metrics.json').unlink()
    elif kind=='empty': json_write(summary,dict(cases=[]))
    else:
        metrics=json.loads((source/'metrics.json').read_text())
        if kind in ('fail','blocked'): metrics['status']=kind.upper()
        elif kind=='forged_score': metrics['plans']['baseline']['task_score']+=100
        else: metrics['plans']['baseline']['coverage_all']['rate']=0.1
        json_write(source/'metrics.json',metrics)
    # Seal the intentionally invalid fixture to exercise semantic checks, not just integrity.
    (source/'evidence_manifest.json').unlink(); json_write(source/'evidence_manifest.json',tree_hashes(source))
    out=tmp_path/'demo'; result=build(summary,out)
    expected='BLOCKED' if kind in ('missing','empty','blocked') else 'FAIL'
    report=json.loads((out/'demo_data_check.json').read_text())
    assert result==(3 if expected=='BLOCKED' else 2)
    assert report['status']==expected and report['issues']
    assert '"status":"'+expected+'"' in (out/'index.html').read_text(encoding='utf-8')


def test_ledger_caps_remaining_budget_and_refuses_unresolved_run(tmp_path,monkeypatch):
    from scripts import budget_run
    ledger=tmp_path/'ledger.json'
    json_write(ledger,dict(budget_seconds=600,entries=[dict(seconds=595,status='PASS')]))
    limits=[]
    def fake_run(command,**kwargs):
        limits.append(kwargs['timeout']); return dict(exit_code=0,timed_out=False)
    monkeypatch.setattr(budget_run,'run_guarded',fake_run)
    assert budget_run.execute(ledger,['synthetic'],timeout=300)==0
    assert limits==[5]
    state=json.loads(ledger.read_text()); state['entries'][-1]['status']='RUNNING'; json_write(ledger,state)
    with pytest.raises(ValueError,match='unresolved'): budget_run.execute(ledger,['synthetic'])
    assert len(limits)==1
