"""Pre-write isolation regressions; all attack targets are synthetic temporary fixtures."""
import json
import os
from pathlib import Path
import subprocess
import sys
import pytest
import yaml
from planner.common import json_write
from planner.path_safety import tree_snapshot
from planner.runner import tree_hashes

ROOT=Path(__file__).resolve().parents[1]


def fixture_spec(root):
    raw=root/'raw';raw.mkdir();(raw/'input.txt').write_text('synthetic only')
    event=root/'event.json';json_write(event,dict(station_id=1,start_s=2,end_s=10))
    sources=[];items=[]
    for seed in (42,17,23):
        source=root/f'source_{seed}';source.mkdir();(source/'empty_directory').mkdir()
        config=dict(seed=seed,input_dir=str(raw),cache_dir=str(root/'cache'))
        path=root/f'config_{seed}.yaml';path.write_text(yaml.safe_dump(config))
        json_write(source/'effective_config.json',config)
        json_write(source/'frozen_sample.json',dict(seed=seed,selected={'high':[seed],'medium':[],'low':[]}))
        json_write(source/'fault_event.json',dict(station_id=1,start_s=2,end_s=10))
        json_write(source/'input_hashes.json',{'synthetic':'fixture'})
        for name in ('windows.csv','candidates.csv'):(source/name).write_text('synthetic\n')
        json_write(source/'evidence_manifest.json',tree_hashes(source))
        sources.append(source);items.append(dict(seed=seed,source=str(source),config=str(path)))
    spec=root/'spec.json';json_write(spec,dict(seeds=items,late_fault=str(event)))
    return spec,sources


def invoke(spec,out,ledger=None,stage=None):
    command=[sys.executable,'-X','utf8',str(ROOT/'scripts/run_improvement.py'),'--spec',str(spec),'--out',str(out)]
    if ledger is not None:command+=['--ledger',str(ledger)]
    if stage:command+=[stage]
    return subprocess.run(command,cwd=ROOT,capture_output=True,text=True,encoding='utf-8',timeout=30)


@pytest.mark.parametrize('kind',['equal','inside','dotdot','second_source','third_source','case_alias','raw_input','ledger_inside','ledger_event','prepare'])
def test_rejected_paths_leave_entire_fixture_tree_unchanged(tmp_path,kind):
    spec,sources=fixture_spec(tmp_path);source=sources[0]
    out=tmp_path/'new_output';ledger=tmp_path/'ledger.json';stage=None
    if kind=='equal':out=source
    elif kind=='inside':out=source/'nested'
    elif kind=='dotdot':out=source/'empty_directory'/'..'/'nested'
    elif kind=='second_source':out=sources[1]/'nested'
    elif kind=='third_source':out=sources[2]/'nested'
    elif kind=='case_alias':
        if os.name!='nt':pytest.skip('Windows case-insensitive alias test')
        out=Path(str(source).swapcase())/'nested'
    elif kind=='raw_input':out=tmp_path/'raw'/'nested'
    elif kind=='ledger_inside':ledger=sources[2]/'ledger.json'
    elif kind=='ledger_event':ledger=tmp_path/'event.json'
    else:out=source/'nested';stage='--prepare';ledger=None
    before=tree_snapshot(tmp_path)
    result=invoke(spec,out,ledger,stage)
    assert result.returncode==2,result.stdout+result.stderr
    assert 'FAIL:' in result.stderr
    assert tree_snapshot(tmp_path)==before,'including empty directories, no write may precede rejection'


def test_automatic_log_and_atomic_temporary_file_are_protected(tmp_path):
    from scripts.budget_run import execute
    source=tmp_path/'raw';source.mkdir();protected=source/'evidence.txt';protected.write_text('unchanged')
    ledger=tmp_path/'ledger.json'
    # A hardlink at the automatic log destination must not truncate the input.
    os.link(protected,tmp_path/'command_01.log')
    before=tree_snapshot(tmp_path)
    with pytest.raises(ValueError):execute(ledger,['never-run'],protected=[source])
    assert tree_snapshot(tmp_path)==before
    # Separate fixture for the ledger's atomic replacement path.
    other=tmp_path/'other';other.mkdir();temp=other/'ledger.tmp';os.link(protected,temp)
    before=tree_snapshot(tmp_path)
    with pytest.raises(ValueError,match='overlaps'):execute(other/'ledger.json',['never-run'],protected=[protected])
    assert tree_snapshot(tmp_path)==before


def test_valid_adjacent_prefix_directory_can_prepare(tmp_path):
    spec,sources=fixture_spec(tmp_path);before=[tree_snapshot(s) for s in sources]
    out=tmp_path/'source_42_result'
    result=invoke(spec,out,stage='--prepare')
    assert result.returncode==0,result.stdout+result.stderr
    assert (out/'frozen_inputs.json').is_file()
    assert [tree_snapshot(s) for s in sources]==before
    second=invoke(spec,out,stage='--prepare')
    assert second.returncode==2 and 'must be new' in second.stderr


def test_summary_cannot_write_inside_sealed_case(tmp_path):
    spec,sources=fixture_spec(tmp_path);source=sources[0]
    json_write(source/'frozen_inputs.json',dict(spec_path=str(spec),cases=[dict(id='nested_case',source=str(source),config=str(tmp_path/'config_42.yaml'),event=str(tmp_path/'event.json'))]))
    before=tree_snapshot(tmp_path)
    result=invoke(spec,source,stage='--summarize')
    assert result.returncode==2 and 'sealed evidence' in result.stderr
    assert tree_snapshot(tmp_path)==before


def test_windows_junction_alias_cannot_write_to_source(tmp_path):
    if os.name!='nt':pytest.skip('Windows directory junction test')
    spec,sources=fixture_spec(tmp_path);alias=tmp_path/'alias'
    command="New-Item -ItemType Junction -Path '"+str(alias).replace("'","''")+"' -Target '"+str(sources[1]).replace("'","''")+"' | Out-Null"
    created=subprocess.run(['powershell','-NoProfile','-Command',command],capture_output=True,text=True,timeout=15)
    if created.returncode:pytest.skip('junction unavailable: '+created.stderr)
    before=tree_snapshot(tmp_path)
    result=invoke(spec,alias/'nested',tmp_path/'ledger.json')
    assert result.returncode==2,result.stdout+result.stderr
    assert tree_snapshot(tmp_path)==before
