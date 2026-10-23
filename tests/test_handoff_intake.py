"""Intake and portable workflow boundary tests; only synthetic inputs are modified."""
import json
from pathlib import Path
import shutil
import subprocess
import sys
import zipfile

import pytest
import yaml
from planner.path_safety import tree_snapshot
from scripts.build_handoff import archive, extract_verified, verify_archive

ROOT=Path(__file__).resolve().parents[1]


def cli(script, *args):
    return subprocess.run([sys.executable,'-X','utf8',str(ROOT/'scripts'/script),*map(str,args)],
                          cwd=ROOT,capture_output=True,text=True,encoding='utf-8',timeout=30)


def fixture(root):
    data=root/'received';shutil.copytree(ROOT/'examples/synthetic',data)
    (data/'empty').mkdir()
    return data


@pytest.mark.parametrize('mutation,code', [('missing',3),('duplicate_target',2),('duplicate_station',2),
    ('duplicate_window',2),('unknown_target',2),('unknown_station',2),('utc',2),('score',2),('metadata',2),('alpha5',2)])
def test_intake_invalid_input_is_read_only_and_reports_first_error(tmp_path,mutation,code):
    data=fixture(tmp_path)
    if mutation=='missing':(data/'windows.csv').unlink()
    elif mutation.startswith('duplicate_'):
        name={'duplicate_target':'targets.csv','duplicate_station':'stations.csv','duplicate_window':'windows.csv'}[mutation]
        text=(data/name).read_text(encoding='utf-8');(data/name).write_text(text+text.splitlines()[1]+'\n',encoding='utf-8')
    elif mutation in ('unknown_target','unknown_station','utc'):
        text=(data/'windows.csv').read_text(encoding='utf-8')
        old,new={'unknown_target':('900001','999999'),'unknown_station':(',7,',',99,'),
                 'utc':('2026-08-03T06:00:00Z','2026-08-03T06:00:00+00:00')}[mutation]
        (data/'windows.csv').write_text(text.replace(old,new,1),encoding='utf-8')
    elif mutation=='metadata':
        p=data/'metadata.json';d=json.loads(p.read_text());d['time_precision_s']=0.5;p.write_text(json.dumps(d))
    else:
        p=data/'targets.csv';text=p.read_text();p.write_text(text.replace('high,5','high,4') if mutation=='score' else text.replace('900001','A0001'))
    before=tree_snapshot(data);out=tmp_path/'report'
    result=cli('inspect_team1_input.py','--input-dir',data,'--out',out,'--source-label','unconfirmed synthetic fixture')
    assert result.returncode==code,result.stdout+result.stderr
    report=json.loads((out/'inspection.json').read_text(encoding='utf-8'))
    assert report['status']==('BLOCKED' if code==3 else 'FAIL') and report['errors']
    assert report['checked_scope']=='NOT_COMPLETED'
    assert report['input_unchanged'] and tree_snapshot(data)==before
    assert not (out/'prepared_windows.yaml').exists()


def test_intake_all_rows_statistics_and_explicit_selection(tmp_path):
    data=fixture(tmp_path);before=tree_snapshot(data);out=tmp_path/'report'
    result=cli('inspect_team1_input.py','--input-dir',data,'--out',out,'--source-label','synthetic, not teammate delivery',
               '--station-ids',9,'--start-utc','2026-08-03T06:10:00Z','--end-utc','2026-08-03T06:30:00Z')
    assert result.returncode==0,result.stdout+result.stderr
    report=json.loads((out/'inspection.json').read_text(encoding='utf-8'))
    assert report['counts']==dict(targets=3,stations=2,windows=4)
    assert report['window_duration_seconds']==dict(min=119,max=720,median=615.0,less_than_120=1,can_fit_120=3,can_fit_240=3)
    assert report['checked_scope']=='ALL_FOUR_FILES_ALL_ROWS' and not report['physical_conditions_independently_verified']
    config=yaml.safe_load((out/'prepared_windows.yaml').read_text(encoding='utf-8'))
    assert config['station_ids']==[9] and config['horizon_seconds']==1200 and config['start_utc']=='2026-08-03T06:10:00Z'
    assert report['planning_selection']['explicit_subset'] and report['planning_selection']['windows']==2
    assert len(report['files'])==4 and all(len(x['sha256'])==64 and x['bytes']>0 for x in report['files'].values())
    assert report['input_unchanged'] and tree_snapshot(data)==before


@pytest.mark.parametrize('extra', [['--station-ids','123'],['--end-utc','2026-08-03T08:00:00Z']])
def test_intake_rejects_unavailable_station_or_outside_horizon(tmp_path,extra):
    data=fixture(tmp_path);before=tree_snapshot(data);out=tmp_path/'report'
    result=cli('inspect_team1_input.py','--input-dir',data,'--out',out,'--source-label','synthetic',*extra)
    assert result.returncode==2 and tree_snapshot(data)==before
    report=json.loads((out/'inspection.json').read_text())
    assert report['status']=='FAIL' and not (out/'prepared_windows.yaml').exists()


@pytest.mark.parametrize('script', ['inspect_team1_input.py','team3_run.py'])
def test_new_entry_rejects_nested_output_before_any_directory_write(tmp_path,script):
    data=fixture(tmp_path);before=tree_snapshot(tmp_path)
    args=['--input-dir',data,'--out',data/'new'/'nested']
    args+=['--source-label','synthetic'] if script=='inspect_team1_input.py' else ['--config',ROOT/'configs/synthetic.yaml']
    result=cli(script,*args) if script=='inspect_team1_input.py' else cli(script,'windows',*args)
    assert result.returncode==2
    assert tree_snapshot(tmp_path)==before


def test_intake_timeout_is_blocked_and_never_certifies_full_read(tmp_path):
    data=fixture(tmp_path);before=tree_snapshot(data);out=tmp_path/'timed'
    result=cli('inspect_team1_input.py','--input-dir',data,'--out',out,'--source-label','synthetic','--budget-seconds','0.001')
    assert result.returncode==3
    report=json.loads((out/'inspection.json').read_text())
    assert report['status']=='BLOCKED' and report['checked_scope']=='NOT_COMPLETED'
    assert tree_snapshot(data)==before


def test_workflow_stops_after_failed_planning(tmp_path):
    data=fixture(tmp_path);p=data/'targets.csv';p.write_text(p.read_text().replace('high,5','high,4'))
    out=tmp_path/'workflow';before=tree_snapshot(data)
    result=cli('team3_run.py','windows','--input-dir',data,'--config',ROOT/'configs/synthetic.yaml','--out',out)
    assert result.returncode==2,result.stdout+result.stderr
    report=json.loads((out/'workflow.json').read_text())
    assert report['status']=='FAIL' and len(report['commands'])==1
    assert not (out/'recheck').exists() and not (out/'evaluate_baseline').exists()
    assert tree_snapshot(data)==before


def test_workflow_requires_complete_fault_evaluation_provenance(tmp_path):
    before=tree_snapshot(tmp_path)
    result=cli('team3_run.py','evaluate','--input-dir',ROOT/'examples/synthetic','--config',ROOT/'configs/synthetic.yaml',
               '--tasks',ROOT/'examples/synthetic/targets.csv','--event',ROOT/'configs/late_fault.json','--out',tmp_path/'out')
    assert result.returncode==2 and tree_snapshot(tmp_path)==before


def test_archive_roundtrip_manifest_and_corruption_rejection(tmp_path):
    path=tmp_path/'source.zip'
    payload={'docs/中文 name.md':('合成包\n'.encode(),'synthetic test','fixture')}
    receipt=archive(path,payload,dict(source_commit='synthetic-test-only'))
    manifest=verify_archive(path)
    assert set(manifest['files'])==set(payload) and manifest['manifest_excludes_self']
    destination=tmp_path/'解压 含空格'
    extract_verified(path,destination)
    assert (destination/'docs/中文 name.md').read_bytes()==payload['docs/中文 name.md'][0]
    assert path.with_suffix('.zip.sha256').read_text().startswith(receipt['sha256'])
    bad=tmp_path/'corrupt.zip'
    with zipfile.ZipFile(path) as original, zipfile.ZipFile(bad,'w') as modified:
        for name in original.namelist():modified.writestr(name,b'changed' if name!='MANIFEST.json' else original.read(name))
    with pytest.raises(ValueError,match='hash mismatch'):verify_archive(bad)
    with pytest.raises(ValueError):extract_verified(bad,tmp_path/'must_not_exist')
    assert not (tmp_path/'must_not_exist').exists()


def test_archive_rejects_traversal_before_creating_zip(tmp_path):
    path=tmp_path/'unsafe.zip'
    with pytest.raises(ValueError,match='unsafe'):
        archive(path,{'../outside':(b'bad','synthetic','fixture')},dict(source_commit='synthetic'))
    assert not path.exists()
