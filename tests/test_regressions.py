"""Synthetic contract/security fixtures only; no real target data committed."""
import copy
import ctypes
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
import pytest
import yaml
from planner.common import Clock, utc_at
from planner.config import normalize
from planner.io_contract import load_tables, read_standard_tasks, parse_utc
from planner.process_guard import run_guarded
from planner.runner import tree_hashes, cached_windows
from planner.scheduler import schedule, replay_state, make_candidates
from planner.validator import IndependentValidator

ROOT=Path(__file__).resolve().parents[1]
DAY=parse_utc('2026-08-03T00:00:00Z')


class QuietClock:
    def check(self,*args,**kwargs): pass
    def log(self,*args): pass


def task(n,sid,a,duration=120,status='success',task_id=None):
    return dict(task_id=task_id or f'SYN_T{n}',candidate_id=f'SYN_C{n}',window_id=f'SYN_W{n}',
                satnum=n,station_id=sid,priority='high',start_s=a,end_s=a+duration,
                duration_s=duration,points_int=15 if duration==120 else 25,score=3.0 if duration==120 else 5.0,
                start_utc=utc_at(DAY,a),end_utc=utc_at(DAY,a+duration),status=status)


@pytest.fixture
def history_case():
    original=[task(1,1,0),task(2,2,200),task(3,1,200),task(4,1,600),task(5,3,600)]
    records=[dict(satnum=n,priority='high',full_score=5) for n in range(1,7)]
    stations=[dict(station_id=n) for n in (1,2,3)]
    windows=[dict(window_id=f'SYN_W{n}',satnum=n,station_id=1 if n in (1,3,4,6) else 2 if n==2 else 3,start_s=0,end_s=2000) for n in range(1,7)]
    v=IndependentValidator.from_tables(dict(horizon_seconds=2000),DAY,records,stations,windows,QuietClock())
    event=dict(station_id=1,start_s=250,end_s=500)
    successes=[dict(original[0],status='completed'),dict(original[1],status='locked'),dict(original[3],status='new_success')]
    fragment=dict(original[2],status='interrupted',end_s=250,duration_s=50,end_utc=utc_at(DAY,250),
                  score=0.0,points_int=0,planned_end_s=320,planned_duration_s=120,planned_end_utc=utc_at(DAY,320))
    return v,original,event,successes,[fragment]


def test_legitimate_history_and_derived_score(history_case):
    v,original,event,tasks,fragments=history_case
    result=v.check(tasks,fragments,event,original_plan=original)
    assert result['status']=='PASS',result['violations']
    assert result['task_score']==9 and result['coverage']==3


@pytest.mark.parametrize('status',['completed','locked','success','new_success'])
def test_forged_history_rejected_even_with_planner_claim(history_case,status):
    v,original,event,tasks,fragments=history_case
    # Target 5 was scheduled at 600, but fabricated at 20; geometrically/resource legal.
    fake=task(5,3,20,status=status)
    result=v.check(tasks+[fake],fragments,event,expected_history=tasks+[fake],original_plan=original)
    assert result['status']=='FAIL'
    assert any('history set' in r['reason'] for r in result['violations'])


@pytest.mark.parametrize('mutation',['delete_completed','delete_locked','delete_fragment','extra_fragment',
                                   'change_time','change_status','change_window','change_fragment','duplicate'])
def test_history_exact_set_mutations(history_case,mutation):
    v,original,event,tasks,fragments=history_case
    tasks,fragments=copy.deepcopy(tasks),copy.deepcopy(fragments)
    if mutation=='delete_completed': tasks.pop(0)
    elif mutation=='delete_locked': tasks.pop(1)
    elif mutation=='delete_fragment': fragments.clear()
    elif mutation=='extra_fragment': fragments.append(dict(fragments[0],task_id='EXTRA'))
    elif mutation=='change_time': tasks[0]=dict(task(1,1,1),status='completed')
    elif mutation=='change_status': tasks[0]['status']='success'
    elif mutation=='change_window': tasks[0]['window_id']='FORGED'
    elif mutation=='change_fragment': fragments[0]['planned_end_s']+=1
    else: tasks.append(dict(tasks[0]))
    result=v.check(tasks,fragments,event,original_plan=original)
    assert result['status']=='FAIL'
    assert any('history set' in r['reason'] for r in result['violations'])


@pytest.mark.parametrize('sid',[1,2])
def test_fault_exact_start_is_not_history(history_case,sid):
    v,_,_,_,_=history_case
    n=1 if sid==1 else 2
    original=[task(n,sid,250)]
    event=dict(station_id=1,start_s=250,end_s=500)
    completed,locked,fragments,cancelled=replay_state(original,event,DAY)
    assert not completed and not locked and not fragments and len(cancelled)==1
    tasks=[] if sid==1 else [dict(original[0],status='new_success')]
    assert v.check(tasks,[],event,original_plan=original)['status']=='PASS'
    assert v.check([dict(original[0],status='locked')],[],event,original_plan=original)['status']=='FAIL'


def test_fault_exact_end_is_completed(history_case):
    v,_,_,_,_=history_case
    original=[task(1,1,130)]
    event=dict(station_id=1,start_s=250,end_s=500)
    completed,locked,fragments,cancelled=replay_state(original,event,DAY)
    assert len(completed)==1 and not locked and not fragments and not cancelled
    assert v.check(completed,fragments,event,original_plan=original)['status']=='PASS'


def test_missing_original_and_self_reported_scores_rejected(history_case):
    v,original,event,tasks,fragments=history_case
    assert v.check(tasks,fragments,event)['status']=='FAIL'
    tasks[2]['score']=9999
    tasks[2]['points_int']=49995
    result=v.check(tasks,fragments,event,original_plan=original)
    assert result['status']=='FAIL' and result['task_score']==9


@pytest.mark.parametrize('event',[{'station_id':99,'start_s':250,'end_s':500},
                                 {'station_id':1,'start_s':500,'end_s':250},
                                 {'station_id':1,'start_s':250.0,'end_s':500},
                                 {'station_id':1,'start_s':250,'end_s':2501},
                                 {'station_id':1,'start_s':250,'end_s':500,'start_utc':'2026-08-03T00:00:00Z'}])
def test_invalid_fault_rejected(history_case,event):
    v,original,_,tasks,fragments=history_case
    with pytest.raises(ValueError): v.check(tasks,fragments,event,original_plan=original)


@pytest.fixture
def tables(tmp_path):
    folder=tmp_path/'input'
    shutil.copytree(ROOT/'examples/synthetic',folder)
    config=normalize(yaml.safe_load((ROOT/'configs/synthetic.yaml').read_text(encoding='utf-8')))
    config['input_dir']=str(folder)
    return folder,config


def test_normal_tables_short_window_arbitrary_stations_and_nonmidnight(tables,tmp_path):
    folder,config=tables
    records,stations,windows,day,meta=load_tables(folder,config)
    assert day.hour==6 and {s['station_id'] for s in stations}=={7,9}
    assert next(w for w in windows if w['window_id']=='SYN_SHORT')['duration_s']==119
    candidates=make_candidates(windows,records,config,day,tmp_path/'results',QuietClock())
    assert not any(c['window_id']=='SYN_SHORT' for c in candidates)
    for method in ('baseline','improved'):
        tasks=schedule(candidates,method,clock=QuietClock())
        v=IndependentValidator.from_tables(config,day,records,stations,windows,QuietClock())
        assert v.check(tasks)['status']=='PASS'
        assert len(tasks)==3


@pytest.mark.parametrize('mutation',['missing_column','duplicate_column','missing_value','bad_time','unknown_target','unknown_station','duplicate','backwards','bad_priority','bad_metadata','boolean_precision'])
def test_invalid_tables_rejected(tables,mutation):
    folder,config=tables
    path=folder/'windows.csv'
    text=path.read_text(encoding='utf-8')
    if mutation=='missing_column': text=text.replace('target_id','WRONG')
    elif mutation=='duplicate_column': text=text.replace('window_id,target_id','target_id,target_id')
    elif mutation=='missing_value': text=text.replace('SYN_W1,900001','SYN_W1,')
    elif mutation=='bad_time': text=text.replace('2026-08-03T06:00:00Z','2026-99-03T06:00:00Z')
    elif mutation=='unknown_target': text=text.replace('900001','800000')
    elif mutation=='unknown_station': text=text.replace(',7,',',42,')
    elif mutation=='duplicate': text=text.replace('SYN_W2','SYN_W1')
    elif mutation=='backwards': text=text.replace('2026-08-03T06:12:00Z','2026-08-03T05:00:00Z')
    elif mutation=='bad_priority': (folder/'targets.csv').write_text('target_id,priority,full_score\n1,high,3\n',encoding='utf-8')
    elif mutation=='boolean_precision':
        metadata=json.loads((folder/'metadata.json').read_text())
        metadata['time_precision_s']=True
        (folder/'metadata.json').write_text(json.dumps(metadata))
    else: (folder/'metadata.json').write_text('{}',encoding='utf-8')
    path.write_text(text,encoding='utf-8')
    with pytest.raises((ValueError,KeyError)): load_tables(folder,config)


def cli(*args):
    return subprocess.run([sys.executable,'-X','utf8',str(ROOT/'smoke_test.py'),*map(str,args)],cwd=ROOT,
                          capture_output=True,text=True,encoding='utf-8',timeout=30)


def test_source_evidence_readonly_and_no_overwrite(tmp_path):
    source=tmp_path/'run'
    args=['--config',ROOT/'configs/synthetic.yaml']
    result=cli(*args,'--out',source)
    assert result.returncode==0,result.stdout+result.stderr
    before=tree_hashes(source)
    result=cli(*args,'--check-only','--source',source,'--out',tmp_path/'recheck')
    assert result.returncode==0,result.stdout+result.stderr
    assert tree_hashes(source)==before
    assert json.loads((tmp_path/'recheck/recheck.json').read_text(encoding='utf-8'))['source_unchanged']
    for output in (source,source/'nested'):
        assert cli(*args,'--check-only','--source',source,'--out',output).returncode==2
        assert tree_hashes(source)==before
    assert cli(*args,'--out',source).returncode==2
    assert tree_hashes(source)==before
    assert cli(*args,'--worker','--out',source).returncode==2
    assert tree_hashes(source)==before
    with (source/'schedule_baseline.csv').open('a',encoding='utf-8') as f: f.write('\n')
    assert cli(*args,'--check-only','--source',source,'--out',tmp_path/'tampered_check').returncode==2


def test_external_evaluation_ignores_self_score(tmp_path):
    source=tmp_path/'run'
    args=['--config',ROOT/'configs/synthetic.yaml']
    assert cli(*args,'--out',source).returncode==0
    tasks=(source/'tasks_baseline.csv').read_text(encoding='utf-8').replace(',5.0,',',99999.0,')
    path=tmp_path/'submitted.csv'; path.write_text(tasks,encoding='utf-8')
    assert cli(*args,'--evaluate',path,'--out',tmp_path/'eval').returncode==0
    report=json.loads((tmp_path/'eval/evaluation.json').read_text(encoding='utf-8'))
    assert report['task_score']==10.0
    assert cli(*args,'--evaluate',source/'tasks_baseline_replanned.csv',
               '--initial-plan',source/'tasks_baseline.csv','--event',source/'fault_event.json',
               '--interrupted',source/'interrupted_baseline.csv','--out',tmp_path/'eval_dynamic').returncode==0


def test_timeout_terminates_descendant_tree(tmp_path):
    child=tmp_path/'child.py'; parent=tmp_path/'parent.py'; pidfile=tmp_path/'pid.txt'
    child.write_text('import os,time,pathlib\npathlib.Path('+repr(str(pidfile))+').write_text(str(os.getpid()))\ntime.sleep(30)\n')
    parent.write_text('import subprocess,sys,time\nsubprocess.Popen([sys.executable,'+repr(str(child))+'])\ntime.sleep(30)\n')
    receipt=run_guarded([sys.executable,str(parent)],timeout=1.2,log_path=tmp_path/'log.txt')
    assert receipt['timed_out'] and receipt['exit_code']==3 and receipt['seconds']<5
    assert pidfile.exists(),'descendant must have actually launched'
    pid=int(pidfile.read_text())
    if os.name=='nt':
        api=ctypes.WinDLL('kernel32',use_last_error=True)
        api.OpenProcess.restype=ctypes.c_void_p
        api.GetExitCodeProcess.argtypes=[ctypes.c_void_p,ctypes.POINTER(ctypes.c_ulong)]
        api.CloseHandle.argtypes=[ctypes.c_void_p]
        handle=api.OpenProcess(0x1000,False,pid)
        if handle:
            code=ctypes.c_ulong()
            try:
                assert api.GetExitCodeProcess(handle,ctypes.byref(code))
                assert code.value!=259,'descendant is still active'
            finally: api.CloseHandle(handle)
    else:
        with pytest.raises(ProcessLookupError): os.kill(pid,0)


def test_cli_timeout_keeps_partial_evidence(tmp_path):
    config=yaml.safe_load((ROOT/'configs/synthetic.yaml').read_text(encoding='utf-8'))
    config.update(budget_seconds=0.05,save_margin_seconds=0)
    path=tmp_path/'tiny_budget.yaml'; path.write_text(yaml.safe_dump(config))
    out=tmp_path/'timeout'
    result=cli('--config',path,'--out',out)
    assert result.returncode==3,result.stdout+result.stderr
    assert json.loads((out/'execution.json').read_text())['timed_out']
    assert json.loads((out/'failure.json').read_text())['status']=='BLOCKED'
    assert (out/'console.log').exists() and (out/'evidence_manifest.json').exists()


def test_invalid_yaml_returns_fail(tmp_path):
    path=tmp_path/'broken.yaml'; path.write_text('seed: [broken')
    result=cli('--config',path,'--out',tmp_path/'invalid')
    assert result.returncode==2
    assert 'FAIL:' in result.stderr


def test_missing_config_returns_blocked(tmp_path):
    result=cli('--config',tmp_path/'missing.yaml','--out',tmp_path/'unused')
    assert result.returncode==3
    assert 'BLOCKED:' in result.stderr


def test_cache_identity_includes_scenario_and_detects_tamper(tmp_path,monkeypatch):
    import planner.runner as runner
    config=normalize(yaml.safe_load((ROOT/'configs/synthetic.yaml').read_text(encoding='utf-8')))
    config['cache_dir']=str(tmp_path/'cache')
    calls=[]
    class DummyGeometry:
        def __init__(self,*args): self.errors=[]
    def build(*args): calls.append(True); return []
    monkeypatch.setattr(runner,'Geometry',DummyGeometry)
    monkeypatch.setattr(runner,'build_windows',build)
    out=tmp_path/'out'; out.mkdir()
    sample=dict(input_hashes={'synthetic':'abc'},selected={'high':[1],'medium':[],'low':[]})
    stations=[dict(station_id=7)]
    def get(c=config,s=sample,st=stations,d=DAY): return cached_windows(c,[],st,d,s,out,QuietClock())
    get(); get(); assert len(calls)==1
    get(s=dict(sample,selected={'high':[2],'medium':[],'low':[]}))
    get(s=dict(sample,input_hashes={'synthetic':'xyz'}))
    get(st=[dict(station_id=9)])
    get(c=dict(config,horizon_seconds=1800))
    get(c=dict(config,coarse_step_seconds=15))
    get(c=dict(config,elevation_degrees=[11,85]))
    get(d=parse_utc('2026-08-04T00:00:00Z'))
    assert len(calls)==8
    get()
    location=Path(json.loads((out/'cache.json').read_text())['path'])
    (location/'windows.json').write_text('[{}]')
    with pytest.raises(ValueError,match='hash mismatch'): get()


def test_validator_has_no_scheduler_dependency():
    import ast
    parsed=ast.parse((ROOT/'planner/validator.py').read_text(encoding='utf-8'))
    assert not any(isinstance(n,ast.ImportFrom) and n.module=='scheduler' for n in ast.walk(parsed))
    assert not any(isinstance(n,ast.Call) and isinstance(n.func,ast.Name) and n.func.id in
                   {'planner_conflict','objective','schedule','greedy','replay_state'} for n in ast.walk(parsed))
